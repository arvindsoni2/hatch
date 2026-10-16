"""Durable CV workflow: routed calls, validated staging, fenced publication."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import uuid
import zipfile

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from sqlalchemy import select

from app.agents.tools import llm_factory
from app.agents.tools.context_budgets import GENERIC
from app.models.cv_publication import CVPublication
from app.repositories.document_repository import DocumentRepository
from app.runtime import RuntimeMode
from app.runtime.context import ContextRegistry, ContextResolver
from app.runtime.control import ConstraintSet, ControlPlane
from app.runtime.contracts import ExecutionResultCode
from app.runtime.evaluation.models import ExecutionRecord
from app.runtime.execution import CapabilityDescriptor, CapabilityRegistry, ExecutionGateway, IdempotencyClass, SideEffectClass
from app.runtime.execution.adapters.native import NativeCapabilityAdapter
from app.runtime.intelligence import ModelRegistry, ModelRouter, RoutingPreference
from app.runtime.workflow.models import TaskAttemptRecord, WorkflowStepRecord
from app.runtime_bindings.context import ProfileYamlContextProvider, ResumeContextProvider, JobPostingContextProvider
from app.runtime_bindings.context.models import ContextSourceMetadata
from app.runtime_bindings.tasks.cv_tailor import CV_TAILOR_V1, CVTailorInput, CVTailorInvocation, CVTailorOutput, validate_cv_tailor_output
from app.schemas.tailor import ATSScoreResult, JDAnalysisResult, TailoredCVResult
from app.services.ats_optimiser import ATSOptimiser
from app.services.cv_tailor import CVTailor, _parse_tailored_cv
from app.services.docx_cv_builder import _build_cv_spec
from app.services.generation_privacy import metadata_capture
from app.services.jd_analyser import JDAnalyser
from app.services.master_cv_validator import normalise_master_cv


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def cv_content(cv: TailoredCVResult) -> dict:
    """Only content rendered in the canonical artifact participates in comparison."""
    return cv.model_dump(include={"summary", "skills", "experience", "education", "certifications"})


def content_hash(cv: TailoredCVResult) -> str:
    return digest(cv_content(cv))


def read_artifact_cv(path: str) -> TailoredCVResult:
    with zipfile.ZipFile(path) as archive:
        return TailoredCVResult.model_validate_json(archive.read("hatch/cv.json"))


class CVRuntimeError(ValueError):
    """A stable, content-free error at every caller boundary."""


class JsonOutput(BaseModel):
    value: dict


class ArtifactOutput(BaseModel):
    publication_ref: str
    artifact_hash: str
    artifact_bytes: int
    section_count: int


class ArtifactInvocation(CVTailorInput):
    idempotency_key: str


@dataclass
class CVTailorRuntimeResult:
    code: ExecutionResultCode
    reason_code: str
    output: CVTailorOutput | None = None
    artifact_ref: str | None = None
    execution_id: str | None = None
    run_id: str | None = None
    repair_count: int = 0
    analysis: JDAnalysisResult | None = None
    ats: ATSScoreResult | None = None
    document: object | None = None


class RoutedCVClient:
    """The services' JSON interface, with every call authorized by the gateway."""

    def __init__(self, workflow, stage):
        self.workflow, self.stage = workflow, stage
        self.last_json_attempt_count = 1
        self.model = "runtime-selected"

    async def complete_json(
        self, system, user, max_tokens=GENERIC.max_output, **kwargs
    ):
        return await self.workflow.model_call(self.stage, system, user, max_tokens)


class DurableCVTailorRuntime:
    """One product composition, with no model-selection or persistence callbacks."""

    def __init__(self, kernel, *, factory, worker_id, master_cv, profile,
                 job_description, builder, template_id="ats_classic", design_settings=None,
                 custom_instructions=None, heartbeat_seconds=5, model_timeout=1800):
        self.kernel, self.factory, self.worker_id = kernel, factory, worker_id
        self.master = normalise_master_cv(deepcopy(master_cv))
        self.profile = profile.model_copy(deep=True)
        self.jd = job_description
        self.builder, self.template = builder, template_id
        self.design = deepcopy(design_settings)
        self.instructions = custom_instructions
        self.heartbeat_seconds, self.model_timeout = heartbeat_seconds, model_timeout
        self.execution_id = None
        self.claim = self.request = self.package = self.run_record = None
        self.publication = None

    async def _claim(self):
        now = self.kernel.clock.now()
        claim = await self.kernel.claim_run(self.run_record.id, self.worker_id, now)
        if claim:
            return claim
        async with self.factory.session_factory() as db:
            attempt = await db.scalar(select(TaskAttemptRecord).join(WorkflowStepRecord).where(
                WorkflowStepRecord.workflow_run_id == self.run_record.id
            ).order_by(TaskAttemptRecord.attempt_number.desc()).limit(1))
        if attempt:
            claim = await self.kernel.reclaim(attempt.id, self.worker_id, now)
            if claim:
                return claim
            await self.kernel.reconcile(now, recovery_backoff_seconds=1)
            claim = await self.kernel.claim_outcome_unknown(attempt.id, self.worker_id, now)
            if claim:
                return claim
        raise CVRuntimeError("cv_tailor_claim_unavailable")

    async def run(self, request: CVTailorInput, *, mode: RuntimeMode):
        self.request = request
        self.run_record = await self.kernel.start_run(
            CV_TAILOR_V1, input_ref=request.model_dump(),
            domain_ref={"domain_type": "application", "domain_id": request.application_ref},
            mode=mode.value,
            run_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"cv.tailor:1:{mode.value}:{request.delivery_ref}")),
        )
        published = await self._published()
        if published:
            return published
        self.claim = await self._claim()
        heartbeat = asyncio.create_task(self._renew(asyncio.current_task()))
        try:
            with metadata_capture():
                async with self.factory.session_factory() as db:
                    ready = await db.scalar(select(CVPublication).where(
                        CVPublication.run_id == self.run_record.id, CVPublication.state == "staged",
                    ).order_by(CVPublication.created_at.desc()).limit(1))
                if ready is not None:
                    self.publication = ready
                    return await self._publish(ready)
                if self.claim.purpose == "reconciliation":
                    await self._discard_incomplete()
                    raise CVRuntimeError("cv_artifact_incomplete")
                await self._prepare()
                analysis = await JDAnalyser(RoutedCVClient(self, "analyse")).analyse(self.jd)
                cv, repairs = await self._generate(analysis)
                spec = _build_cv_spec(cv, analysis, self.master.get("personal", {}), self.template, self.design)
                cv = _parse_tailored_cv(spec)
                if mode is RuntimeMode.NEW:
                    self.publication = await self._render(cv, analysis)
                from app.services.tailor_service import _cv_to_plain_text, _master_cv_evidence_bank
                ats = await ATSOptimiser(RoutedCVClient(self, "evaluate")).score(
                    _cv_to_plain_text(cv), analysis, evidence_bank=_master_cv_evidence_bank(self.master),
                    target_score=self.profile.tailoring.ats_target_score,
                )
                await self._record_evaluation(cv, ats)
                if mode is RuntimeMode.SHADOW:
                    if not await self.kernel.finalize(self.claim, {"result_ref": "sha256:" + content_hash(cv)}, now=self.kernel.clock.now()):
                        raise CVRuntimeError("cv_tailor_claim_lost")
                    return CVTailorRuntimeResult(ExecutionResultCode.SUCCESS, "cv_tailor_valid", CVTailorOutput(tailored_cv=cv),
                        execution_id=self.execution_id, run_id=self.run_record.id, repair_count=repairs, analysis=analysis, ats=ats)
                _, ats_details = _safe_snapshot(analysis, ats)
                self.publication.projection_json = {**self.publication.projection_json,
                    "ats_details": ats_details, "ats_score": ats.overall_score}
                async with self.factory.transaction() as uow:
                    saved = await uow.session.get(CVPublication, self.publication.id)
                    saved.projection_json, saved.state = self.publication.projection_json, "staged"
                    await uow.commit()
                self.publication.state = "staged"
                result = await self._publish(self.publication)
                result.analysis, result.ats, result.repair_count = analysis, ats, repairs
                return result
        except asyncio.CancelledError:
            await self._discard_incomplete()
            if self.publication is None or self.publication.state != "staged":
                await self.kernel.fail_terminal(self.claim, "cv_tailor_cancelled", self.kernel.clock.now())
            raise
        except Exception as error:
            await self._discard_incomplete()
            reason = str(error) if isinstance(error, CVRuntimeError) else "cv_tailor_failed"
            attempt = await self.kernel.get_attempt(self.claim.task_attempt_id)
            if self.publication is None or self.publication.state != "staged":
                if attempt and attempt.status != "outcome_unknown":
                    await self.kernel.fail_terminal(self.claim, reason, self.kernel.clock.now())
            return CVTailorRuntimeResult(ExecutionResultCode.PERMANENT_FAILURE, reason,
                execution_id=self.execution_id, run_id=self.run_record.id)
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def _renew(self, owner):
        while True:
            await asyncio.sleep(self.heartbeat_seconds)
            try:
                renewed = await self.kernel.renew_claim(self.claim, self.kernel.clock.now())
            except Exception:
                renewed = False
            if not renewed:
                owner.cancel()
                return

    async def _prepare(self):
        # R4 providers consume the SAME frozen product-owned source values that
        # feed generation, not unrelated profile/resume defaults.
        candidate = {k: self.master.get(k) for k in ("experience", "skills", "summary_variants")}
        resume = json.dumps(self.master, sort_keys=True, separators=(",", ":"))
        if len(resume) + 2 * len(self.jd) > 4 * 32768:
            raise CVRuntimeError("cv_tailor_context_budget_exceeded")
        async def job_source(_, capability):
            return ContextSourceMetadata(source_ref=self.request.job_ref, descriptor=capability.replace(".", "-"),
                provenance={"source_version": hashlib.sha256(self.jd.encode()).hexdigest()}, freshness=None,
                sensitivity="confidential", token_estimate=max(1, len(self.jd) // 4), confidence=1.0,
                content_hash=hashlib.sha256(self.jd.encode()).hexdigest())
        registry = ContextRegistry()
        registry.register(ProfileYamlContextProvider(lambda: candidate))
        registry.register(ResumeContextProvider(lambda: resume))
        registry.register(JobPostingContextProvider(job_source))
        resolver = ContextResolver(self.factory, registry)
        attempt = await self.kernel.get_attempt(self.claim.task_attempt_id)
        if attempt.context_package_id:
            self.package = await resolver.load(attempt.context_package_id)
            expected = {"profile.yaml": digest(candidate), "resume.store": hashlib.sha256(resume.encode()).hexdigest(),
                        "job.posting": hashlib.sha256(self.jd.encode()).hexdigest()}
            if any(item.content_hash != expected[item.provider_id] for item in self.package.items):
                raise CVRuntimeError("cv_tailor_context_changed")
        else:
            self.package = await resolver.resolve(self.claim.task_attempt_id, CV_TAILOR_V1.context_requirements, budget=32768)
        self.policy = ControlPlane().evaluate(task_spec=CV_TAILOR_V1, system=ConstraintSet(
            allowed_capabilities=frozenset({"cv.tailor.analyse", "cv.tailor.generate", "cv.tailor.repair",
                "cv.tailor.fallback", "cv.tailor.evaluate", "artifact.render_cv"})))
        async with self.factory.transaction() as uow:
            await uow.evaluations.record_policy_decision(task_attempt_id=self.claim.task_attempt_id,
                policy_id="cv.tailor.policy", policy_version=1, decision=self.policy.decision, reason_code="cv_tailor_declared_policy")
            await uow.commit()
        self.models = ModelRegistry.from_configured_models()

    async def _invoke(self, capability, output_model, handler, *, role, routed=True, artifact=False):
        registry = CapabilityRegistry()
        routing = ModelRouter(self.models).route(CV_TAILOR_V1, self.policy, RoutingPreference.prefer("configured-primary")) if routed else None
        model = routing.selected_descriptor if routing else None
        if routed and model is None:
            raise CVRuntimeError("cv_tailor_model_unavailable")
        if routing:
            async with self.factory.transaction() as uow:
                await ModelRouter(self.models).persist_decision(uow.evaluations, task_attempt_id=self.claim.task_attempt_id,
                    capability_id=capability, decision=routing)
                await uow.commit()
        async def invoke(payload, context):
            return await handler(model)
        registry.register(CapabilityDescriptor(capability_id=capability, version=1,
            input_model=CVTailorInvocation if routed else ArtifactInvocation if artifact else CVTailorInput, output_model=output_model,
            side_effect_class=SideEffectClass.ARTIFACT_GENERATION if artifact else SideEffectClass.READ_ONLY_EXTERNAL if routed else SideEffectClass.PURE,
            idempotency_class=IdempotencyClass.IDEMPOTENT_WITH_KEY if artifact else IdempotencyClass.IDEMPOTENT, requires_data_egress=bool(model and model.local_or_cloud == "cloud"),
            uses_model_routing=routed, uses_provider_routing=routed, default_timeout_seconds=75 if artifact else self.model_timeout),
            NativeCapabilityAdapter(invoke))
        async with self.factory.session_factory() as db:
            previous = set(await db.scalars(select(ExecutionRecord.id).where(ExecutionRecord.task_attempt_id == self.claim.task_attempt_id)))
        result = await ExecutionGateway(registry=registry, kernel=self.kernel, model_registry=self.models).invoke(
            self.claim, capability_id=capability, payload={**self.request.model_dump(),
                **({"idempotency_key": "publication:" + self.claim.id} if artifact else {}),
                **({"model_id": model.model_id, "provider": model.provider} if model else {})},
            policy=self.policy, selection_proof=routing.selection_proof if routing else None)
        async with self.factory.transaction() as uow:
            records = list(await uow.session.scalars(select(ExecutionRecord).where(ExecutionRecord.task_attempt_id == self.claim.task_attempt_id)))
            fresh = [record for record in records if record.id not in previous]
            if fresh:
                record = fresh[0]
                record.parent_execution_id, record.execution_role = self.execution_id, role
                if model:
                    record.model_id, record.model_version, record.provider = model.model_id, model.version, model.provider
                record.metadata_json = {**(record.metadata_json or {}), "context_package_id": self.package.id,
                                        "context_hash": self.package.content_hash}
                self.execution_id = record.id
                await uow.commit()
        if result.code is not ExecutionResultCode.SUCCESS:
            raise CVRuntimeError(result.reason_code)
        return result.output

    async def model_call(self, stage, system, user, max_tokens):
        async def call(model):
            config = self.profile.llm
            if config.provider != model.provider or model.model_name not in {config.primary_model, config.triage_model}:
                raise CVRuntimeError("cv_tailor_model_config_changed")
            config = config.model_copy(update={"max_retries": 0})
            if model.model_id == "configured-triage" and config.triage_base_url:
                config = config.model_copy(update={"base_url": config.triage_base_url})
            client = llm_factory._build_model(model.model_name, config)
            response = await client.bind(max_tokens=max_tokens).ainvoke([
                SystemMessage(content=system + "\nReturn only valid JSON."), HumanMessage(content=user)])
            text = re.sub(r"<think>.*?</think>", "", str(response.content), flags=re.DOTALL).strip()
            if text.startswith("```"):
                text = "\n".join(text.splitlines()[1:-1])
            try:
                return JsonOutput(value=json.loads(text))
            except Exception:
                raise CVRuntimeError("cv_tailor_json_invalid") from None
        result = await self._invoke("cv.tailor." + stage, JsonOutput, call,
            role={"generate": "primary", "repair": "repair", "evaluate": "evaluator"}.get(stage, "tool"))
        return result.value

    async def _generate(self, analysis):
        from app.services.tailor_service import _candidate_source_statements
        statements = _candidate_source_statements(self.master)
        for index, stage in enumerate(("generate", "repair", "fallback")):
            try:
                if stage == "fallback":
                    async def fallback(_):
                        cv = _parse_tailored_cv({**self.master,
                            "summary": next(iter((self.master.get("summary_variants") or {}).values()), self.master.get("summary", "")),
                            "skills": list(self.master["skills"].values()) if isinstance(self.master.get("skills"), dict) else self.master.get("skills", []),
                            "experience": [{**item, "achievements": [a.get("text", "") if isinstance(a, dict) else a for a in item.get("achievements", [])]} for item in self.master.get("experience", [])]})
                        return CVTailorOutput(tailored_cv=cv)
                    output = await self._invoke("cv.tailor.fallback", CVTailorOutput, fallback, role="fallback", routed=False)
                else:
                    instructions = self.instructions or ""
                    if index:
                        instructions += "\nUse only exact source statements. Repair unsupported or missing claims."
                    cv = await CVTailor(RoutedCVClient(self, stage), master_cv_loader=lambda: deepcopy(self.master)).tailor(
                        analysis, self.request.variant, instructions)
                    output = CVTailorOutput(tailored_cv=cv)
                validation = validate_cv_tailor_output(output, source_claims=statements)
                from app.services.grounding_validator import validate
                blocking, _ = validate(output.tailored_cv, self.master)
                valid = validation.code is ExecutionResultCode.SUCCESS and not blocking and not output.tailored_cv.blocking_issues
                async with self.factory.transaction() as uow:
                    await uow.evaluations.record_validation(task_attempt_id=self.claim.task_attempt_id, execution_id=self.execution_id,
                        validator_id="cv_tailor.deterministic", validator_version=1, status="passed" if valid else "failed",
                        reason_codes_json=["cv_tailor_valid" if valid else "cv_tailor_unsupported_claim"], metrics_json={})
                    await uow.commit()
                if valid:
                    return output.tailored_cv, min(index, 1)
            except CVRuntimeError as error:
                if str(error) in {"claim_lost", "cv_tailor_claim_lost"}:
                    raise
        raise CVRuntimeError("cv_tailor_validation_failed")

    async def _render(self, cv, analysis):
        from app.services.tailor_service import _validate_rendered_cv_artifact
        application_id = self.request.application_ref.removeprefix("application:")
        staged, final = self.builder.staging_paths(application_id, 0, self.request.variant, self.claim.id)
        row = CVPublication(id=self.claim.id, run_id=self.run_record.id, attempt_id=self.claim.task_attempt_id,
            owner_fence=self.claim.fencing_token, state="reserved", staged_path=staged, final_path=final,
            projection_json={"application_id": application_id, "variant": self.request.variant,
                "template_id": self.template, "jd_analysis_snapshot": json.dumps({"digest": digest(analysis.model_dump())}),
                "content_hash": content_hash(cv)})
        async with self.factory.transaction() as uow:
            uow.session.add(row)
            await uow.commit()
        self.publication = row
        async def render(_):
            task = asyncio.create_task(asyncio.to_thread(self.builder.build_staged, cv, analysis, self.master.get("personal", {}),
                application_id, 0, self.request.variant, self.template, self.design, attempt_id=self.claim.id))
            try:
                actual, intended, _ = await asyncio.shield(task)
                if (actual, intended) != (staged, final):
                    raise CVRuntimeError("cv_artifact_binding_invalid")
                with zipfile.ZipFile(staged, "a") as archive:
                    archive.writestr("hatch/cv.json", json.dumps(cv_content(cv)))
                size = Path(staged).stat().st_size
                checked = _validate_rendered_cv_artifact(staged, size, cv, template_id=self.template, design_settings=self.design)
                async with self.factory.transaction() as uow:
                    saved = await uow.session.get(CVPublication, row.id)
                    saved.state, saved.artifact_hash, saved.byte_count = "validated", checked["sha256"], size
                    saved.section_count, saved.content_hash = checked["section_count"], content_hash(cv)
                    await uow.commit()
                row.state, row.artifact_hash, row.byte_count = "validated", checked["sha256"], size
                row.section_count, row.content_hash = checked["section_count"], content_hash(cv)
                return ArtifactOutput(publication_ref=row.id, artifact_hash=row.artifact_hash, artifact_bytes=size, section_count=row.section_count)
            except BaseException:
                # Cancelling a thread wrapper cannot stop its renderer. Join it
                # before deleting the path that belongs to this claim.
                with suppress(Exception, asyncio.CancelledError):
                    await asyncio.shield(task)
                if row.state != "validated":
                    self.builder.discard_staged(staged)
                raise
        await self._invoke("artifact.render_cv", ArtifactOutput, render, role="artifact", routed=False, artifact=True)
        async def verify_receipt(uow):
            saved = await uow.session.get(CVPublication, row.id)
            path = Path(row.staged_path)
            return bool(
                saved is not None
                and saved.state == "validated"
                and saved.owner_fence == self.claim.fencing_token
                and saved.artifact_hash
                and saved.byte_count
                and path.is_file()
                and path.stat().st_size == saved.byte_count
                and hashlib.sha256(path.read_bytes()).hexdigest() == saved.artifact_hash
            )
        if not await self.kernel.acknowledge_execution_receipt(
            self.claim,
            receipt_ref="artifact:" + row.id,
            verify_receipt=verify_receipt,
            now=self.kernel.clock.now(),
        ):
            raise CVRuntimeError("cv_artifact_receipt_unverified")
        async with self.factory.transaction() as uow:
            await uow.evaluations.record_validation(task_attempt_id=self.claim.task_attempt_id, execution_id=self.execution_id,
                validator_id="cv_tailor.artifact_contract", validator_version=1, status="passed",
                reason_codes_json=["cv_artifact_valid"], metrics_json={"byte_count": row.byte_count, "section_count": row.section_count})
            await uow.commit()
        return row

    async def _record_evaluation(self, cv, ats):
        async with self.factory.transaction() as uow:
            record = await uow.session.get(ExecutionRecord, self.execution_id)
            await uow.evaluations.record_evaluation(task_attempt_id=self.claim.task_attempt_id,
                execution_id=record.id, evaluation_execution_id=record.id,
                evaluator_id="cv.tailor.ats", evaluator_version=1, evaluator_type="model",
                evaluation_spec_id="cv.tailor.ats", evaluation_spec_version=1,
                evaluator_model_id=record.model_id, evaluator_model_version=record.model_version,
                result="passed" if ats.passed_target else "review_required", status="completed",
                scores_json={"ats_score": ats.overall_score}, reason_codes_json=["cv_ats_evaluated"],
                validation_metrics_json={})
            await uow.commit()

    async def _publish(self, row):
        path = Path(row.final_path) if Path(row.final_path).exists() else Path(row.staged_path)
        if not path.is_file() or path.stat().st_size != row.byte_count or hashlib.sha256(path.read_bytes()).hexdigest() != row.artifact_hash:
            raise CVRuntimeError("cv_artifact_reconciliation_conflict")
        cv = read_artifact_cv(str(path))
        if content_hash(cv) != row.content_hash:
            raise CVRuntimeError("cv_artifact_content_mismatch")
        projected = None
        async def project(uow):
            nonlocal projected
            saved = await uow.session.get(CVPublication, row.id)
            if saved.document_id:
                raise CVRuntimeError("cv_artifact_already_published")
            if not Path(row.final_path).exists():
                self.builder.promote_staged(row.staged_path, row.final_path)
            elif hashlib.sha256(Path(row.final_path).read_bytes()).hexdigest() != row.artifact_hash:
                raise CVRuntimeError("cv_artifact_promotion_conflict")
            values = row.projection_json
            repo = DocumentRepository(uow.session)
            version = await repo.get_latest_version(values["application_id"], "cv") + 1
            projected = await repo.create(application_id=values["application_id"], document_type="cv", version=version,
                file_path=row.final_path, file_size_bytes=row.byte_count, variant_label=values["variant"],
                ats_score=values["ats_score"], ats_details=values["ats_details"], jd_analysis_snapshot=values["jd_analysis_snapshot"],
                tailoring_params=json.dumps({"runtime_mode": "new", "template_id": values["template_id"],
                    "variant": values["variant"], "content_hash": row.content_hash, "run_id": row.run_id,
                    "artifact_hash": row.artifact_hash, "byte_count": row.byte_count, "section_count": row.section_count}), status="generated")
            saved.document_id, saved.state = projected.id, "published"
        accepted = await self.kernel.finalize(self.claim, {"result_ref": "artifact:" + row.id,
            "artifact_hash": row.artifact_hash, "artifact_bytes": row.byte_count, "section_count": row.section_count,
            "artifact_location_hash": hashlib.sha256(row.final_path.encode()).hexdigest()}, projection=project, now=self.kernel.clock.now())
        if not accepted:
            raise CVRuntimeError("cv_tailor_claim_lost")
        self.builder.discard_staged(row.staged_path)
        return CVTailorRuntimeResult(ExecutionResultCode.SUCCESS, "cv_tailor_valid",
            CVTailorOutput(tailored_cv=cv, artifact_ref="artifact:" + projected.id, artifact_bytes=row.byte_count,
                artifact_hash=row.artifact_hash, section_count=row.section_count), artifact_ref="artifact:" + projected.id,
            execution_id=self.execution_id, run_id=row.run_id, document=projected,
            ats=ATSScoreResult.model_validate_json(row.projection_json["ats_details"]))

    async def _published(self):
        async with self.factory.session_factory() as db:
            row = await db.scalar(select(CVPublication).where(CVPublication.run_id == self.run_record.id, CVPublication.state == "published"))
            if not row:
                return None
            doc = await DocumentRepository(db).get_by_id(row.document_id)
        if not doc or not Path(row.final_path).is_file() or hashlib.sha256(Path(row.final_path).read_bytes()).hexdigest() != row.artifact_hash:
            raise CVRuntimeError("cv_artifact_reconciliation_conflict")
        cv = read_artifact_cv(row.final_path)
        return CVTailorRuntimeResult(ExecutionResultCode.SUCCESS, "cv_tailor_replayed", CVTailorOutput(tailored_cv=cv,
            artifact_ref="artifact:" + doc.id, artifact_bytes=row.byte_count, artifact_hash=row.artifact_hash, section_count=row.section_count),
            artifact_ref="artifact:" + doc.id, run_id=row.run_id, document=doc,
            ats=ATSScoreResult.model_validate_json(row.projection_json["ats_details"]))

    async def _discard_incomplete(self):
        async with self.factory.transaction() as uow:
            rows = list(await uow.session.scalars(select(CVPublication).where(CVPublication.run_id == self.run_record.id,
                CVPublication.state.in_(("reserved", "validated")))))
            for row in rows:
                if row.id == self.claim.id or (self.claim.purpose == "reconciliation" and row.attempt_id == self.claim.task_attempt_id):
                    self.builder.discard_staged(row.staged_path)
                    row.state = "aborted"
            await uow.commit()


def _safe_snapshot(analysis, ats):
    from app.services.tailor_service import _safe_runtime_snapshot
    return _safe_runtime_snapshot(analysis, ats)
