"""Tailor Service — orchestrates the full 3-stage Claude pipeline for CV and cover letter generation."""
from __future__ import annotations

import json
import logging
import uuid
import hashlib
import zipfile
from xml.etree import ElementTree
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.document_repository import DocumentRepository
from ..schemas.document import GeneratedDocumentRead
from ..schemas.tailor import (
    ATSScoreResult,
    CoverLetterResult,
    JDAnalysisResult,
    JDAnalysisResponse,
    TailoredCVResult,
    TailorResultBundle,
)
from ..observability import get_telemetry, trace_workflow
from .ats_optimiser import ATSOptimiser
from .cl_generator import CoverLetterGenerator, select_tone_variant
from .llm_client import LLMClient
from .cv_tailor import CVTailor
from .docx_cl_builder import DocxCLBuilder
from .docx_cv_builder import DocxCVBuilder
from .jd_analyser import JDAnalyser
from .master_cv_store import load_master_cv
from .writing_contracts import GenerationProvenance
from ..agents.tools.profile_loader import load_profile
from ..runtime import RuntimeMode
from ..runtime.storage.sqlite import SQLiteRuntimeUnitOfWorkFactory
from ..runtime.workflow import WorkflowKernel
from ..runtime.migration import resolve_runtime_mode
from ..runtime_bindings.migration.cv_tailor import DurableCVTailorRuntime
from ..runtime_bindings.tasks.cv_tailor import CVTailorInput
from .generation_privacy import metadata_capture, metadata_only
from ..database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Default ATS score target used when profile.yaml is absent or incomplete.
_ATS_TARGET_SCORE = 80


def _load_master_cv() -> dict[str, Any]:
    return load_master_cv()


def _load_personal() -> dict[str, Any]:
    return load_master_cv().get("personal", {})


def _candidate_source_statements(master: dict[str, Any]) -> tuple[str, ...]:
    """Return only master-CV statements allowed to support rendered prose."""
    statements: list[str] = []
    summary = master.get("summary")
    if isinstance(summary, str) and summary.strip():
        statements.append(summary)
    for statement in (master.get("summary_variants") or {}).values():
        if isinstance(statement, str) and statement.strip():
            statements.append(statement)
    for experience in master.get("experience", []):
        if not isinstance(experience, dict):
            continue
        for achievement in experience.get("achievements", []):
            text = achievement.get("text") if isinstance(achievement, dict) else achievement
            if isinstance(text, str) and text.strip():
                statements.append(text)
    return tuple(dict.fromkeys(statements))


def _tailoring_params(
    values: dict[str, Any],
    generated: Any,
) -> str:
    """Serialize runtime metadata only; preserve the legacy compatibility format."""
    if values.get("runtime_mode") not in {RuntimeMode.NEW.value, RuntimeMode.SHADOW.value}:
        provenance = getattr(generated, "generation_provenance", None)
        if isinstance(provenance, GenerationProvenance):
            values = {**values, "generation_provenance": provenance.to_dict()}
        return json.dumps(values)
    safe: dict[str, Any] = {}
    for key in ("variant", "template_id", "runtime_mode", "delivery_ref"):
        value = values.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
    if values.get("custom_instructions"):
        safe["custom_instructions_hash"] = hashlib.sha256(
            str(values["custom_instructions"]).encode()
        ).hexdigest()
    if values.get("design_settings") is not None:
        safe["design_settings_hash"] = hashlib.sha256(
            json.dumps(values["design_settings"], sort_keys=True, default=str).encode()
        ).hexdigest()
    render_metadata = values.get("render_metadata")
    if isinstance(render_metadata, dict):
        safe["render"] = {
            key: value for key, value in render_metadata.items()
            if key in {"path_hash", "sha256", "byte_count", "section_count"}
            and isinstance(value, (str, int))
        }
    provenance = getattr(generated, "generation_provenance", None)
    if isinstance(provenance, GenerationProvenance):
        source = provenance.to_dict()
        safe["provenance"] = {
            "schema_version": provenance.evidence_schema_version,
            "claim_count": len(provenance.claims),
            "digest": hashlib.sha256(
                json.dumps(source, sort_keys=True, default=str).encode()
            ).hexdigest(),
        }
    return json.dumps(safe, sort_keys=True)


def _validate_rendered_cv_artifact(
    staged_path: str, expected_size: int, tailored_cv: TailoredCVResult,
    *, template_id: str | None = None, design_settings: dict | None = None,
) -> dict[str, Any]:
    """Verify the concrete staged DOCX before it is projected as a document."""
    path = Path(staged_path)
    if not path.is_file() or path.stat().st_size < 1 or path.stat().st_size != expected_size:
        raise ValueError("cv_tailor_rendered_artifact_invalid")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        with zipfile.ZipFile(path) as docx:
            if docx.getinfo("word/document.xml").file_size > 10_000_000:
                raise ValueError("cv_tailor_rendered_artifact_invalid")
            xml = docx.read("word/document.xml")
            if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
                raise ValueError("cv_tailor_rendered_artifact_invalid")
            root = ElementTree.fromstring(xml)
            rendered_text = " ".join("".join(root.itertext()).split())
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ValueError("cv_tailor_rendered_artifact_invalid") from exc
    # ElementTree itertext handles DOCX XML escaping and text split over runs.
    # Every candidate-rendered section is checked before projection; only the
    # resulting counts and hash reach product/runtime metadata.
    from .docx_cv_builder import _build_cv_spec
    from .cv_tailor import _parse_tailored_cv
    spec = _build_cv_spec(tailored_cv, JDAnalysisResult(role_title=""), {}, template_id, design_settings)
    tailored_cv = _parse_tailored_cv(spec)
    sections = [tailored_cv.summary]
    for group in tailored_cv.skills:
        if isinstance(group, dict):
            sections.append(group.get("category") or group.get("display_name") or group.get("name") or "")
            sections.extend(str(item) for item in group.get("items", ()) if item)
    for item in tailored_cv.experience:
        sections.extend((item.role, item.company, item.period, *item.achievements))
    for item in tailored_cv.education:
        sections.extend((item.qualification, item.institution, item.year, item.field, item.location, *item.details))
    sections.extend(tailored_cv.certifications)
    if any(value and " ".join(value.split()) not in rendered_text for value in sections):
        raise ValueError("cv_tailor_rendered_artifact_sections_invalid")
    return {
        "path_hash": hashlib.sha256(str(path).encode()).hexdigest(),
        "sha256": digest,
        "byte_count": expected_size,
        "section_count": len(sections),
    }


def _safe_runtime_snapshot(analysis: JDAnalysisResult, ats: ATSScoreResult) -> tuple[str, str]:
    """Document fields are telemetry-like sinks on the NEW path: store metrics only."""
    jd = json.dumps({"digest": hashlib.sha256(
        analysis.model_dump_json().encode()).hexdigest()}, sort_keys=True)
    score = json.dumps({"overall_score": ats.overall_score, "attempts": ats.attempts,
                        "target_score": ats.target_score, "passed_target": ats.passed_target}, sort_keys=True)
    return jd, score


def _cover_letter_failure_detail(
    result: CoverLetterResult,
) -> dict[str, Any] | None:
    """Return safe validation metadata when a draft must be withheld."""
    ready = result.validation_status in {"passed", "repaired"}
    if ready and not result.grounding_issues:
        return None
    return {
        "error": "Cover letter failed validation — document withheld.",
        "final_state": result.validation_status,
        "attempt_count": result.attempt_count,
        "issues": result.validation_issues or result.grounding_issues,
    }


def _master_cv_text(master: dict[str, Any]) -> str:
    """Flatten master CV to a single lowercased string for keyword containment checks."""
    parts: list[str] = []
    for exp in master.get("experience", []):
        if isinstance(exp, dict):
            parts.extend([exp.get("role", ""), exp.get("company", "")])
            for ach in exp.get("achievements", []):
                parts.append(ach.get("text", "") if isinstance(ach, dict) else str(ach))
    skills = master.get("skills", {})
    if isinstance(skills, dict):
        for grp in skills.values():
            if isinstance(grp, dict):
                parts.extend(grp.get("items", []))
    elif isinstance(skills, list):
        for grp in skills:
            if isinstance(grp, dict):
                parts.extend(grp.get("items", []))
    parts.extend(master.get("certifications", []))
    return " ".join(str(p) for p in parts if p).lower()


def _master_cv_evidence_bank(master: dict[str, Any]) -> str:
    """Compact source evidence for ATS suggestions and grounded retries."""
    parts: list[str] = []
    for exp in master.get("experience", []):
        if not isinstance(exp, dict):
            continue
        heading = " - ".join(
            str(value)
            for value in (exp.get("role"), exp.get("company"), exp.get("period") or exp.get("dates"))
            if value
        )
        if heading:
            parts.append(heading)
        for ach in exp.get("achievements", []):
            text = ach.get("text", "") if isinstance(ach, dict) else str(ach)
            if text:
                parts.append(f"* {text}")
    skills = master.get("skills", {})
    skill_groups = skills.values() if isinstance(skills, dict) else skills
    if isinstance(skill_groups, list) or not isinstance(skill_groups, dict):
        for group in skill_groups or []:
            if isinstance(group, dict):
                category = group.get("category") or group.get("display_name") or "Skills"
                items = ", ".join(str(item) for item in group.get("items", []) if item)
                if items:
                    parts.append(f"{category}: {items}")
    certs = ", ".join(str(cert) for cert in master.get("certifications", []) if cert)
    if certs:
        parts.append(f"Certifications: {certs}")
    return "\n".join(parts)


def _partition_ats_keywords(
    missing_critical: list[str], master_text: str
) -> tuple[list[str], list[str]]:
    """Split missing ATS keywords into those grounded in master CV vs genuine gaps.

    Returns:
        (grounded, gaps) — grounded keywords can be reinforced in re-tailoring;
        gaps are honest skill gaps the user needs to fill themselves.
    """
    grounded: list[str] = []
    gaps: list[str] = []
    for kw in missing_critical:
        if kw.lower() in master_text:
            grounded.append(kw)
        else:
            gaps.append(kw)
    return grounded, gaps


def _build_retry_instructions(
    base_instructions: str | None,
    grounded_keywords: list[str],
    suggestions: list[str],
    target_score: int,
) -> str:
    parts = [base_instructions.strip()] if base_instructions else []
    parts.append(
        "ATS IMPROVEMENT RETRY: The previous draft scored below "
        f"{target_score}. Reinforce only these keywords because they are already "
        f"supported by the master CV: {', '.join(grounded_keywords)}. "
        "Place them naturally in the summary, skills, or existing bullets where truthful. "
        "Do not add unsupported skills, employers, certifications, metrics, or new claims."
    )
    grounded_suggestions = [
        suggestion for suggestion in suggestions[:3]
        if not suggestion.lower().startswith("add ")
    ]
    if grounded_suggestions:
        parts.append("Grounded ATS suggestions to consider: " + " | ".join(grounded_suggestions))
    return "\n\n".join(parts)


class TailorService:
    """Orchestrates JD analysis → CV tailoring → ATS scoring → docx generation."""

    def __init__(self) -> None:
        self._claude = LLMClient()
        self._jd_analyser = JDAnalyser(self._claude)
        self._cv_tailor = CVTailor(self._claude)
        self._cl_generator = CoverLetterGenerator(self._claude)
        self._ats_optimiser = ATSOptimiser(self._claude)
        self._cv_builder = DocxCVBuilder()
        self._cl_builder = DocxCLBuilder()
        self._runtime_factory = SQLiteRuntimeUnitOfWorkFactory(AsyncSessionLocal)

    def _tailoring_config(self) -> tuple[int, int]:
        try:
            config = load_profile().tailoring
            return config.ats_target_score, config.ats_retry_limit
        except Exception:
            return _ATS_TARGET_SCORE, 1

    async def _tailor_and_score(
        self,
        analysis: JDAnalysisResult,
        variant: str,
        custom_instructions: str | None = None,
    ) -> tuple[TailoredCVResult, ATSScoreResult]:
        """Create a grounded CV, retrying only for supported ATS gaps."""
        target_score, retry_limit = self._tailoring_config()
        master = _load_master_cv()
        master_text = _master_cv_text(master)
        evidence_bank = _master_cv_evidence_bank(master)
        attempt = 1
        retry_instructions = custom_instructions
        best_cv: TailoredCVResult | None = None
        best_score: ATSScoreResult | None = None
        review_notes: list[str] = []

        while True:
            tailored_cv = await self._cv_tailor.tailor(analysis, variant, retry_instructions)
            if tailored_cv.blocking_issues:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "Tailored CV failed grounding checks — document withheld.",
                        "issues": ["cv_grounding_failed"] if metadata_only.get() else tailored_cv.blocking_issues,
                        "hint": "Review the source CV evidence or re-run tailoring.",
                    },
                )

            ats_result = await self._ats_optimiser.score(
                _cv_to_plain_text(tailored_cv),
                analysis,
                evidence_bank=evidence_bank,
                target_score=target_score,
            )
            grounded, gaps = _partition_ats_keywords(ats_result.missing_critical, master_text)
            ats_result.attempts = attempt
            ats_result.target_score = target_score
            ats_result.passed_target = ats_result.overall_score >= target_score
            ats_result.grounded_improvements = grounded
            ats_result.unsupported_gaps = gaps
            ats_result.review_notes = [
                *review_notes,
                *([f"Unsupported JD gaps left for review: {', '.join(gaps)}"] if gaps else []),
            ]

            if best_score is None or ats_result.overall_score > best_score.overall_score:
                best_cv = tailored_cv
                best_score = ats_result

            if ats_result.overall_score >= target_score:
                return tailored_cv, ats_result
            if attempt > retry_limit or not grounded:
                logger.info(
                    "ATS score %d is below target %d; preserving best grounded CV for review%s",
                    best_score.overall_score,
                    target_score,
                    f" with unsupported gaps: {best_score.unsupported_gaps}" if best_score.unsupported_gaps and not metadata_only.get() else "",
                )
                return best_cv or tailored_cv, best_score or ats_result

            review_notes.append(
                f"Attempt {attempt} scored {ats_result.overall_score}; retrying with grounded keywords: {', '.join(grounded)}."
            )
            retry_instructions = _build_retry_instructions(
                custom_instructions,
                grounded,
                ats_result.improvement_suggestions,
                target_score,
            )
            attempt += 1

    async def analyse_job(self, job_id: str, db: AsyncSession) -> JDAnalysisResponse:
        """Run JD analysis for a job posting and compute skill match.

        Args:
            job_id: UUID of the JobPosting record.
            db: Active async DB session.

        Returns:
            JDAnalysisResponse with analysis + skill_match.

        Raises:
            HTTPException 404 if job not found.
        """
        try:
            analysis = await self._jd_analyser.analyse_from_job_posting(job_id, db)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        master_cv = _load_master_cv()
        skill_match = self._jd_analyser.compute_skill_match(analysis, master_cv)

        return JDAnalysisResponse(
            job_id=job_id,
            analysis=analysis,
            skill_match=skill_match,
        )

    async def analyse_jd_text(self, job_description: str, job_url: str | None = None) -> JDAnalysisResponse:
        """Analyse a raw JD text (not tied to a saved job posting).

        Args:
            job_description: Raw JD text.
            job_url: Optional URL to fetch text from if description is empty.

        Returns:
            JDAnalysisResponse.
        """
        analysis = await self._jd_analyser.analyse(job_description, job_url)
        master_cv = _load_master_cv()
        skill_match = self._jd_analyser.compute_skill_match(analysis, master_cv)
        return JDAnalysisResponse(
            job_id="adhoc",
            analysis=analysis,
            skill_match=skill_match,
        )

    @trace_workflow("cv_tailoring")
    async def generate_cv(
        self,
        application_id: str,
        variant: str,
        jd_text: str,
        db: AsyncSession,
        custom_instructions: str | None = None,
        template_id: str | None = None,
        design_settings: dict | None = None,
        _resolved_mode: RuntimeMode | None = None,
        request_ref: str | None = None,
        delivery_ref: str | None = None,
        _capture: dict | None = None,
    ) -> GeneratedDocumentRead:
        """Resolve one CV migration mode before invoking its sole visible writer."""
        mode = _resolved_mode or resolve_runtime_mode("cv_tailor")
        request_ref = request_ref or ("request:" + hashlib.sha256(delivery_ref.encode()).hexdigest() if delivery_ref else f"request:{uuid.uuid4()}")
        delivery_ref = delivery_ref or request_ref.replace("request:", "delivery:", 1)
        if mode is RuntimeMode.LEGACY:
            return await self._generate_cv_legacy(
                application_id,
                variant,
                jd_text,
                db,
                custom_instructions,
                template_id,
                design_settings,
            )
        if mode is RuntimeMode.SHADOW:
            captured = {}
            with metadata_capture():
                visible = await self._generate_cv_legacy(
                application_id,
                variant,
                jd_text,
                db,
                custom_instructions,
                template_id,
                design_settings,
                runtime_mode=RuntimeMode.SHADOW,
                _capture=captured,
            )
            try:
                await self._evaluate_cv_runtime(
                    application_id,
                    variant,
                    jd_text,
                    custom_instructions,
                    legacy_document=visible,
                    legacy_capture=captured, template_id=template_id,
                    design_settings=design_settings, request_ref=request_ref,
                    delivery_ref=delivery_ref,
                )
            except Exception:
                # SHADOW is observational: it must never alter the already
                # committed legacy document or turn a successful request red.
                logger.warning("cv_tailor_shadow_runtime_failed")
            if _capture is not None:
                _capture.update(captured)
            return visible
        return await self._generate_cv_runtime(
            application_id,
            variant,
            jd_text,
            db,
            custom_instructions,
            template_id,
            design_settings,
            request_ref=request_ref, delivery_ref=delivery_ref, capture=_capture,
        )

    async def _generate_cv_legacy(
        self,
        application_id: str,
        variant: str,
        jd_text: str,
        db: AsyncSession,
        custom_instructions: str | None = None,
        template_id: str | None = None,
        design_settings: dict | None = None,
        runtime_mode: RuntimeMode | None = None,
        _capture: dict | None = None,
    ) -> GeneratedDocumentRead:
        """Generate a tailored CV and persist the document record.

        Preserves honest ATS gaps for user review instead of fabricating keywords.

        Args:
            application_id: UUID of the Application.
            variant: "A" or "B".
            jd_text: Full job description text.
            db: Active async DB session.
            custom_instructions: Optional extra guidance for Claude.

        Returns:
            GeneratedDocumentRead for the saved .docx record.
        """
        if design_settings:
            template_id = design_settings["template_id"]
        if not template_id:
            try:
                template_id = load_profile().tailoring.default_template_id
            except Exception:
                template_id = "ats_classic"
        from .resume_template_registry import resolve_template  # noqa: PLC0415
        template, template_warning = resolve_template(template_id)
        template_id = template["id"]
        if template_warning:
            logger.warning(template_warning)
        doc_repo = DocumentRepository(db)
        analysis = await self._jd_analyser.analyse(jd_text)
        tailored_cv, ats_result = await self._tailor_and_score(
            analysis, variant, custom_instructions
        )
        if runtime_mode is RuntimeMode.SHADOW:
            jd_snapshot, ats_details = _safe_runtime_snapshot(analysis, ats_result)
        else:
            jd_snapshot, ats_details = (
                json.dumps(analysis.model_dump()),
                json.dumps(ats_result.model_dump()),
            )

        personal = _load_personal()
        version = await doc_repo.get_latest_version(application_id, "cv") + 1
        with get_telemetry().stage_span("cv_tailoring", "render_document"):
            file_path, file_size = self._cv_builder.build(
                tailored_cv,
                analysis,
                personal,
                application_id,
                version,
                variant,
                template_id,
            )

        if runtime_mode is RuntimeMode.SHADOW:
            from .docx_cv_builder import _build_cv_spec
            from .cv_tailor import _parse_tailored_cv
            from ..runtime_bindings.migration.cv_tailor import cv_content
            rendered = _parse_tailored_cv(_build_cv_spec(tailored_cv, analysis, personal, template_id))
            with zipfile.ZipFile(file_path, "a") as archive:
                archive.writestr("hatch/cv.json", json.dumps(cv_content(rendered)))
            file_size = Path(file_path).stat().st_size
            if _capture is not None:
                _capture.update(cv=rendered, ats=ats_result, analysis=analysis)

        with get_telemetry().stage_span(
            "cv_tailoring",
            "persist_document",
        ) as span:
            doc = await doc_repo.create(
                application_id=application_id,
                document_type="cv",
                version=version,
                file_path=file_path,
                file_size_bytes=file_size,
                jd_analysis_snapshot=jd_snapshot,
                tailoring_params=_tailoring_params(
                    {
                        "variant": variant,
                        "custom_instructions": custom_instructions,
                        "template_id": template_id or "ats_classic",
                        **({"runtime_mode": runtime_mode.value} if runtime_mode else {}),
                    },
                    tailored_cv,
                ),
                ats_score=ats_result.overall_score,
                ats_details=ats_details,
                variant_label=variant,
                status="generated",
            )
            await db.commit()
            span.set_attribute("hatch.ai.document.id", str(doc.id))
        return doc

    async def _run_cv_runtime(
        self, application_id, variant, jd_text, custom_instructions, template_id,
        design_settings, *, mode, request_ref, delivery_ref,
    ):
        from .resume_template_registry import resolve_template
        template, _ = resolve_template((design_settings or {}).get("template_id") or template_id or load_profile().tailoring.default_template_id)
        runtime = DurableCVTailorRuntime(
            WorkflowKernel(self._runtime_factory), factory=self._runtime_factory,
            worker_id=f"cv-tailor-{uuid.uuid4().hex}",
            master_cv=_load_master_cv(), profile=load_profile(),
            job_description=jd_text, builder=self._cv_builder,
            template_id=template["id"], design_settings=design_settings,
            custom_instructions=custom_instructions,
        )
        from ..runtime_bindings.migration.cv_tailor import digest
        result = await runtime.run(CVTailorInput(
            application_ref=f"application:{application_id}", job_ref="job:adhoc",
            variant=variant, request_ref=request_ref, delivery_ref=delivery_ref,
            input_hash=digest({"jd": jd_text, "instructions": custom_instructions,
                "template": template["id"], "design": design_settings}),
        ), mode=mode)
        return runtime, result

    async def _evaluate_cv_runtime(
        self, application_id, variant, jd_text, custom_instructions, *,
        legacy_document, legacy_capture, template_id, design_settings,
        request_ref, delivery_ref,
    ):
        from ..runtime_bindings.migration.cv_tailor import content_hash
        runtime, result = await self._run_cv_runtime(
            application_id, variant, jd_text, custom_instructions, template_id,
            design_settings, mode=RuntimeMode.SHADOW, request_ref=request_ref,
            delivery_ref=delivery_ref,
        )
        if runtime.claim is None:
            return result
        async with self._runtime_factory.transaction() as uow:
            # A real observed legacy completion, linked to the same comparison
            # attempt. It is not a claim that legacy used runtime generation.
            legacy_execution = await uow.evaluations.record_execution(
                task_attempt_id=runtime.claim.task_attempt_id,
                execution_role="primary", capability_id="cv.tailor.legacy",
                capability_version=1, result_class="success",
                metadata_json={"document_ref": legacy_document.id,
                    "result_hash": content_hash(legacy_capture["cv"])},
            )
            legacy_hash = content_hash(legacy_capture["cv"])
            runtime_hash = content_hash(result.output.tailored_cv) if result.output else None
            await uow.shadow.record(
                slice_name="cv_tailor", domain_type="application",
                domain_id_hash="sha256:" + hashlib.sha256(application_id.encode()).hexdigest(),
                legacy_execution_ref=legacy_execution.id,
                runtime_execution_id=result.execution_id,
                legacy_result_hash="sha256:" + legacy_hash,
                runtime_result_hash="sha256:" + runtime_hash if runtime_hash else None,
                comparison_status=("same" if legacy_hash == runtime_hash else "different") if runtime_hash else "runtime_failed",
                metrics_json={"reason_code": result.reason_code, "runtime_committed": False,
                    "legacy_score": legacy_capture["ats"].overall_score,
                    "runtime_score": result.ats.overall_score if result.ats else None,
                    "repair_count": result.repair_count},
            )
            await uow.commit()
        return result

    async def _generate_cv_runtime(
        self, application_id, variant, jd_text, db, custom_instructions,
        template_id, design_settings, *, request_ref, delivery_ref, capture=None,
    ):
        _, result = await self._run_cv_runtime(
            application_id, variant, jd_text, custom_instructions, template_id,
            design_settings, mode=RuntimeMode.NEW, request_ref=request_ref,
            delivery_ref=delivery_ref,
        )
        if result.document is None:
            raise HTTPException(status_code=422, detail={"error": "cv_tailor_withheld", "reason_code": result.reason_code})
        if capture is not None:
            capture.update(cv=result.output.tailored_cv, ats=result.ats,
                analysis=result.analysis or JDAnalysisResult(role_title=jd_text.splitlines()[0][:200] if jd_text else ""))
        return result.document

    @trace_workflow("cover_letter_generation")
    async def generate_cover_letter(
        self,
        application_id: str,
        variant: str,
        jd_text: str,
        db: AsyncSession,
        _cv_context: dict | None = None,
        _runtime_mode: RuntimeMode | None = None,
        _delivery_ref: str | None = None,
    ) -> GeneratedDocumentRead:
        """Generate a tailored cover letter and persist the document record.

        Args:
            application_id: UUID of the Application.
            variant: "A" or "B".
            jd_text: Full job description text.
            db: Active async DB session.

        Returns:
            GeneratedDocumentRead for the saved .docx record.
        """
        from sqlalchemy import select
        doc_repo = DocumentRepository(db)
        if _runtime_mode is not None and _delivery_ref:
            from ..models.document import GeneratedDocument
            existing = await db.scalars(
                select(GeneratedDocument).where(
                    GeneratedDocument.application_id == application_id,
                    GeneratedDocument.document_type == "cover_letter",
                    GeneratedDocument.variant_label == variant,
                ).order_by(GeneratedDocument.version.desc())
            )
            for candidate in existing:
                try:
                    params = json.loads(candidate.tailoring_params or "{}")
                except (TypeError, ValueError):
                    continue
                if params.get("delivery_ref") == _delivery_ref:
                    return GeneratedDocumentRead.model_validate(candidate)
        if _cv_context is None:
            analysis = await self._jd_analyser.analyse(jd_text)
            tailored_cv, _ = await self._tailor_and_score(analysis, variant)
        else:
            analysis, tailored_cv = _cv_context["analysis"], _cv_context["cv"]

        personal = _load_personal()
        cl_variant = select_tone_variant(analysis)
        cover_letter = await self._cl_generator.generate(
            analysis, tailored_cv, personal, cl_variant, jd_text=jd_text
        )
        failure_detail = _cover_letter_failure_detail(cover_letter)
        if failure_detail:
            raise HTTPException(
                status_code=422,
                detail={"error": "cover_letter_validation_failed"} if _runtime_mode else failure_detail,
            )

        version = await doc_repo.get_latest_version(application_id, "cover_letter") + 1
        with get_telemetry().stage_span(
            "cover_letter_generation",
            "render_document",
        ):
            file_path, file_size = self._cl_generator.render_document(
                cover_letter,
                lambda: self._cl_builder.build(
                    cover_letter,
                    analysis,
                    personal,
                    application_id,
                    version,
                    variant,
                ),
            )

        with get_telemetry().stage_span(
            "cover_letter_generation",
            "persist_document",
        ) as span:
            doc = await doc_repo.create(
                application_id=application_id,
                document_type="cover_letter",
                version=version,
                file_path=file_path,
                file_size_bytes=file_size,
                jd_analysis_snapshot=_safe_runtime_snapshot(analysis, _cv_context["ats"])[0] if _cv_context else json.dumps(analysis.model_dump()),
                tailoring_params=_tailoring_params(
                    {"variant": variant, **({"runtime_mode": _runtime_mode.value} if _runtime_mode else {}),
                     **({"delivery_ref": _delivery_ref} if _delivery_ref else {})},
                    cover_letter,
                ),
                variant_label=variant,
                status="generated",
            )
            await db.commit()
            span.set_attribute("hatch.ai.document.id", str(doc.id))
        return doc

    async def _create_manual_application(
        self,
        job_title: str,
        company_name: str | None,
        job_url: str | None,
        jd_text: str | None,
        db: AsyncSession,
    ) -> str:
        """Create a JobPosting + Application for a manually-sourced internet job.

        If a JobPosting already exists for the given URL it is reused (no
        duplicate created). A new Application is always created so each
        tailoring attempt is independently tracked.

        Returns:
            The new Application UUID (string).
        """
        from ..models.job import JobPosting  # noqa: PLC0415
        from ..models.application import Application  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415

        effective_url = job_url or f"manual://{uuid.uuid4()}"

        result = await db.execute(
            select(JobPosting).where(JobPosting.url == effective_url)
        )
        job = result.scalar_one_or_none()

        if job is None:
            job = JobPosting(
                id=str(uuid.uuid4()),
                title=job_title or "Manual Job",
                company=company_name,
                url=effective_url,
                source="manual",
                description=jd_text,
            )
            db.add(job)
            await db.flush()

        app = Application(
            id=str(uuid.uuid4()),
            job_id=job.id,
            status="discovered",
            agent_created=False,
            approval_status="pending",
            notes="Created via Resume Tailoring page",
        )
        db.add(app)
        await db.flush()
        await db.commit()
        logger.info("Auto-created application %s", app.id)
        return app.id

    async def generate_all(
        self,
        application_id: str | None,
        variant: str,
        jd_text: str,
        db: AsyncSession,
        generate_variants: bool = False,
        job_title: str | None = None,
        company_name: str | None = None,
        job_url: str | None = None,
        custom_instructions: str | None = None,
        template_id: str | None = None,
        design_settings: dict | None = None,
        _resolved_mode: RuntimeMode | None = None,
        request_ref: str | None = None,
        delivery_ref: str | None = None,
    ) -> TailorResultBundle:
        """Run the full pipeline: JD analysis → CV → Cover letter.

        Args:
            application_id: UUID of an existing Application, or None to
                auto-create a pipeline entry from the job metadata below.
            variant: "A" or "B".
            jd_text: Full JD text.
            db: Active async DB session.
            generate_variants: If True, also generate variant B.
            job_title: Used only when application_id is None.
            company_name: Used only when application_id is None.
            job_url: Used only when application_id is None.

        Returns:
            TailorResultBundle with document IDs and scores.
        """
        mode = _resolved_mode or resolve_runtime_mode("cv_tailor")
        if design_settings:
            template_id = design_settings["template_id"]
        if not template_id:
            try:
                template_id = load_profile().tailoring.default_template_id
            except Exception:
                template_id = "ats_classic"
        from .resume_template_registry import resolve_template  # noqa: PLC0415
        template, template_warning = resolve_template(template_id)
        template_id = template["id"]
        if template_warning:
            logger.warning(template_warning)
        if not application_id:
            application_id = await self._create_manual_application(
                job_title=job_title or "Manual Job",
                company_name=company_name,
                job_url=job_url,
                jd_text=jd_text,
                db=db,
            )
        # Auto-resolve JD from the linked job posting when caller omits jd_text
        if not jd_text and application_id:
            from sqlalchemy import select  # noqa: PLC0415
            from ..models.application import Application  # noqa: PLC0415
            from ..models.job import JobPosting  # noqa: PLC0415
            app_r = await db.execute(select(Application).where(Application.id == application_id))
            _app = app_r.scalar_one_or_none()
            if _app and _app.job_id:
                job_r = await db.execute(select(JobPosting).where(JobPosting.id == _app.job_id))
                _job = job_r.scalar_one_or_none()
                if _job:
                    jd_text = _job.description or _job.title or ""
                    if not job_url:
                        job_url = _job.url
        # Non-legacy package/SSE callers use the same already-bound CV entry
        # boundary. The cover-letter flow remains product legacy scope; it
        # never becomes a second CV writer.
        if mode is not RuntimeMode.LEGACY:
            results = []
            variants = [variant, "B" if variant == "A" else "A"] if generate_variants else [variant]
            identity = delivery_ref or f"delivery:{uuid.uuid4()}"
            for label in variants:
                captured = {}
                with metadata_capture():
                    cv_doc = await self.generate_cv(
                        application_id, label, jd_text, db, custom_instructions,
                        template_id, design_settings, _resolved_mode=mode,
                        request_ref=request_ref or identity.replace("delivery:", "request:", 1),
                        delivery_ref=f"{identity}:{label.lower()}", _capture=captured,
                    )
                    cl_doc = await self.generate_cover_letter(application_id, label, jd_text, db,
                        _cv_context=captured, _runtime_mode=mode,
                        _delivery_ref=f"{identity}:{label.lower()}")
                results.append((cv_doc, cl_doc, captured))
            cv_doc, cl_doc, captured = results[0]
            return TailorResultBundle(
                application_id=application_id, cv_document_id=cv_doc.id,
                cl_document_id=cl_doc.id, ats_score=captured["ats"], analysis=captured["analysis"],
                skill_match=self._jd_analyser.compute_skill_match(captured["analysis"], _load_master_cv()),
                review={"cv_runtime_mode": mode.value, "variants": [
                    {"variant": cv.variant_label, "cv_document_id": cv.id, "cl_document_id": cl.id}
                    for cv, cl, _ in results]},
            )
        telemetry = get_telemetry()
        doc_repo = DocumentRepository(db)
        with telemetry.workflow_span("cv_tailoring") as cv_workflow_span:
            analysis = await self._jd_analyser.analyse(jd_text, job_url)
            logger.info("Tailor package %s: JD analysis complete", application_id)
            master_cv = _load_master_cv()
            skill_match = self._jd_analyser.compute_skill_match(analysis, master_cv)

            tailored_cv, ats_result = await self._tailor_and_score(
                analysis, variant, custom_instructions
            )
            logger.info(
                "Tailor package %s: CV content and ATS score complete (%d)",
                application_id,
                ats_result.overall_score,
            )
            personal = _load_personal()

            cv_version = await doc_repo.get_latest_version(application_id, "cv") + 1
            with telemetry.stage_span("cv_tailoring", "render_document"):
                cv_path, cv_size = self._cv_builder.build(
                    tailored_cv,
                    analysis,
                    personal,
                    application_id,
                    cv_version,
                    variant,
                    template_id,
                    design_settings,
                )
            cv_doc = await doc_repo.create(
                application_id=application_id,
                document_type="cv",
                version=cv_version,
                file_path=cv_path,
                file_size_bytes=cv_size,
                jd_analysis_snapshot=json.dumps(analysis.model_dump()),
                tailoring_params=_tailoring_params(
                    {
                        "variant": variant,
                        "custom_instructions": custom_instructions,
                        "template_id": template_id or "ats_classic",
                        "design_settings": design_settings,
                    },
                    tailored_cv,
                ),
                ats_score=ats_result.overall_score,
                ats_details=json.dumps(ats_result.model_dump()),
                variant_label=variant,
                status="generated",
            )
            logger.info(
                "Tailor package %s: CV document created",
                application_id,
            )
            with telemetry.workflow_span(
                "cover_letter_generation"
            ) as cl_workflow_span:
                cl_variant = select_tone_variant(analysis)
                cover_letter = await self._cl_generator.generate(
                    analysis,
                    tailored_cv,
                    personal,
                    cl_variant,
                    jd_text=jd_text,
                )
                failure_detail = _cover_letter_failure_detail(cover_letter)
                if failure_detail:
                    raise HTTPException(
                        status_code=422,
                        detail=failure_detail,
                    )
                logger.info(
                    "Tailor package %s: cover letter content complete",
                    application_id,
                )
                cl_version = (
                    await doc_repo.get_latest_version(
                        application_id,
                        "cover_letter",
                    )
                    + 1
                )
                with telemetry.stage_span(
                    "cover_letter_generation",
                    "render_document",
                ):
                    cl_path, cl_size = self._cl_generator.render_document(
                        cover_letter,
                        lambda: self._cl_builder.build(
                            cover_letter,
                            analysis,
                            personal,
                            application_id,
                            cl_version,
                            variant,
                            design_settings,
                        ),
                    )
                with telemetry.stage_span(
                    "cv_tailoring",
                    "persist_document",
                ) as cv_persist_span:
                    with telemetry.stage_span(
                        "cover_letter_generation",
                        "persist_document",
                    ) as cl_persist_span:
                        cl_doc = await doc_repo.create(
                            application_id=application_id,
                            document_type="cover_letter",
                            version=cl_version,
                            file_path=cl_path,
                            file_size_bytes=cl_size,
                            jd_analysis_snapshot=json.dumps(
                                analysis.model_dump()
                            ),
                            tailoring_params=_tailoring_params(
                                {
                                    "variant": variant,
                                    "template_id": template_id,
                                    "design_settings": design_settings,
                                    "regeneration_instruction": (
                                        custom_instructions
                                    ),
                                },
                                cover_letter,
                            ),
                            variant_label=variant,
                            status="generated",
                        )
                        from .tailoring_review import (  # noqa: PLC0415
                            build_review,
                            save_review,
                        )

                        review = build_review(
                            application_id=application_id,
                            analysis=analysis,
                            skill_match=skill_match,
                            ats=ats_result,
                            tailored=tailored_cv,
                            cv_document_id=cv_doc.id,
                            cl_document_id=cl_doc.id,
                            template_id=template_id,
                            variant=variant,
                        )
                        from .cv_quality_gate import (  # noqa: PLC0415
                            post_generation_quality,
                            pre_generation_quality,
                        )

                        review["quality_gate"] = {
                            "pre_generation": pre_generation_quality(
                                analysis,
                                master_cv,
                                template_id,
                            ),
                            "post_generation": post_generation_quality(
                                cv_path,
                                tailored_cv,
                                analysis,
                                master_cv,
                            ),
                            "document_id": cv_doc.id,
                            "pack_version": cv_version,
                        }
                        await save_review(db, review)
                        await db.commit()
                        cv_workflow_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cv_doc.id),
                        )
                        cl_workflow_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cl_doc.id),
                        )
                        cv_persist_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cv_doc.id),
                        )
                        cl_persist_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cl_doc.id),
                        )
        logger.info("Tailor package %s: package committed", application_id)

        return TailorResultBundle(
            application_id=application_id,
            cv_document_id=cv_doc.id,
            cl_document_id=cl_doc.id,
            ats_score=ats_result,
            analysis=analysis,
            skill_match=skill_match,
            review=review,
        )

    async def stream_progress(
        self,
        application_id: str,
        variant: str,
        jd_text: str,
        db: AsyncSession,
    ) -> AsyncGenerator[str, None]:
        """Yield SSE events for the full pipeline, then generate documents.

        Yields:
            Server-Sent Events strings like "data: {...}\n\n"
        """

        def sse(stage: str, pct: int, message: str = "") -> str:
            payload = json.dumps({"stage": stage, "pct": pct, "message": message})
            return f"data: {payload}\n\n"

        mode = resolve_runtime_mode("cv_tailor")
        if mode is not RuntimeMode.LEGACY:
            # SSE is an entry point, not a bypass: bind the mode once and
            # delegate the CV write to generate_all's common boundary.
            yield sse("tailoring_cv", 40, "Tailoring CV...")
            try:
                bundle = await self.generate_all(
                    application_id, variant, jd_text, db, _resolved_mode=mode
                )
            except HTTPException as exc:
                yield sse("error", 0, json.dumps(exc.detail))
                return
            yield sse("complete", 100, json.dumps({
                "cv_document_id": bundle.cv_document_id,
                "cl_document_id": bundle.cl_document_id,
                "ats_score": bundle.ats_score.overall_score,
            }))
            return

        telemetry = get_telemetry()
        doc_repo = DocumentRepository(db)
        yield sse("analysing_jd", 10, "Analysing job description...")
        with telemetry.workflow_span("cv_tailoring") as cv_workflow_span:
            analysis = await self._jd_analyser.analyse(jd_text)

            yield sse("skill_match", 25, "Computing skill match...")
            master_cv = _load_master_cv()
            self._jd_analyser.compute_skill_match(analysis, master_cv)

            yield sse("tailoring_cv", 40, "Tailoring CV with Claude...")
            try:
                tailored_cv, ats_result = await self._tailor_and_score(
                    analysis,
                    variant,
                )
            except HTTPException as exc:
                telemetry.mark_current_error(
                    "cv_tailoring_failed",
                    "workflow_error",
                )
                yield sse("error", 0, json.dumps(exc.detail))
                return

            yield sse(
                "scoring_ats",
                55,
                "Running ATS scoring and grounded improvements...",
            )
            personal = _load_personal()
            yield sse("generating_cl", 70, "Generating cover letter...")
            with telemetry.workflow_span(
                "cover_letter_generation"
            ) as cl_workflow_span:
                cl_variant = select_tone_variant(analysis)
                cover_letter = await self._cl_generator.generate(
                    analysis,
                    tailored_cv,
                    personal,
                    cl_variant,
                    jd_text=jd_text,
                )
                failure_detail = _cover_letter_failure_detail(cover_letter)
                if failure_detail:
                    telemetry.mark_current_error(
                        "cover_letter_validation_failed",
                        "validation_failure",
                    )
                    yield sse(
                        "error",
                        0,
                        json.dumps(failure_detail),
                    )
                    return

                yield sse("building_docx", 85, "Building .docx documents...")
                cv_version = (
                    await doc_repo.get_latest_version(application_id, "cv")
                    + 1
                )
                with telemetry.stage_span("cv_tailoring", "render_document"):
                    cv_path, cv_size = self._cv_builder.build(
                        tailored_cv,
                        analysis,
                        personal,
                        application_id,
                        cv_version,
                        variant,
                    )
                cl_version = (
                    await doc_repo.get_latest_version(
                        application_id,
                        "cover_letter",
                    )
                    + 1
                )
                with telemetry.stage_span(
                    "cover_letter_generation",
                    "render_document",
                ):
                    cl_path, cl_size = self._cl_generator.render_document(
                        cover_letter,
                        lambda: self._cl_builder.build(
                            cover_letter,
                            analysis,
                            personal,
                            application_id,
                            cl_version,
                            variant,
                        ),
                    )
                with telemetry.stage_span(
                    "cv_tailoring",
                    "persist_document",
                ) as cv_persist_span:
                    cv_doc = await doc_repo.create(
                        application_id=application_id,
                        document_type="cv",
                        version=cv_version,
                        file_path=cv_path,
                        file_size_bytes=cv_size,
                            jd_analysis_snapshot=json.dumps(
                                analysis.model_dump()
                            ),
                        tailoring_params=_tailoring_params(
                            {"variant": variant},
                            tailored_cv,
                        ),
                        ats_score=ats_result.overall_score,
                        ats_details=json.dumps(ats_result.model_dump()),
                        variant_label=variant,
                    )
                    with telemetry.stage_span(
                        "cover_letter_generation",
                        "persist_document",
                    ) as cl_persist_span:
                        cl_doc = await doc_repo.create(
                            application_id=application_id,
                            document_type="cover_letter",
                            version=cl_version,
                            file_path=cl_path,
                            file_size_bytes=cl_size,
                        jd_analysis_snapshot=json.dumps(
                            analysis.model_dump()
                        ),
                            tailoring_params=_tailoring_params(
                                {"variant": variant},
                                cover_letter,
                            ),
                            variant_label=variant,
                        )
                        await db.commit()
                        cv_workflow_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cv_doc.id),
                        )
                        cl_workflow_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cl_doc.id),
                        )
                        cv_persist_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cv_doc.id),
                        )
                        cl_persist_span.set_attribute(
                            "hatch.ai.document.id",
                            str(cl_doc.id),
                        )

        yield sse(
            "complete",
            100,
            json.dumps({
                "cv_document_id": cv_doc.id,
                "cl_document_id": cl_doc.id,
                "ats_score": ats_result.overall_score,
            }),
        )

    async def get_document_history(
        self, application_id: str, doc_type: str | None, db: AsyncSession
    ) -> list[GeneratedDocumentRead]:
        """Return all documents for an application.

        Args:
            application_id: UUID of the application.
            doc_type: Filter by "cv" or "cover_letter", or None for all.
            db: Active async DB session.

        Returns:
            List of GeneratedDocumentRead, newest first.
        """

        doc_repo = DocumentRepository(db)
        items = await doc_repo.list_by_application(application_id, doc_type)
        # Convert DocumentListItem → GeneratedDocumentRead via id lookups
        results: list[GeneratedDocumentRead] = []
        for item in items:
            full = await doc_repo.get_by_id(item.id)
            if full:
                results.append(full)
        return results

    async def download_document(self, document_id: str, db: AsyncSession) -> tuple[str, str]:
        """Return (file_path, filename) for a generated document.

        Args:
            document_id: UUID of the document.
            db: Active async DB session.

        Returns:
            Tuple of (absolute file path, filename for Content-Disposition).

        Raises:
            HTTPException 404 if document or file not found.
        """
        doc_repo = DocumentRepository(db)
        doc = await doc_repo.get_by_id(document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = doc.file_path
        if not file_path or not Path(file_path).exists():
            raise HTTPException(status_code=404, detail="Document file not found on disk")

        filename = Path(file_path).name
        return file_path, filename


def _cv_to_plain_text(tailored_cv: Any) -> str:
    """Convert a TailoredCVResult to plain text for ATS scoring."""
    parts = [tailored_cv.summary]
    for skill_group in tailored_cv.skills:
        if isinstance(skill_group, dict):
            parts.append(skill_group.get("category") or skill_group.get("display_name", ""))
            parts.extend(skill_group.get("items", []))
    for exp in tailored_cv.experience:
        parts.append(f"{exp.role} at {exp.company} ({exp.period})")
        parts.extend(exp.achievements)
    for edu in getattr(tailored_cv, "education", []):
        parts.extend([
            getattr(edu, "qualification", ""),
            getattr(edu, "field", ""),
            getattr(edu, "institution", ""),
            getattr(edu, "year", ""),
        ])
        parts.extend(getattr(edu, "details", []) or [])
    parts.extend(tailored_cv.certifications)
    return " ".join(str(p) for p in parts if p)
