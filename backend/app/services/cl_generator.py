"""Cover Letter Generator — produces tailored cover letters via Claude."""
from __future__ import annotations

import logging
import json
import re
import time
import uuid
from dataclasses import asdict
from typing import Any, Callable

from pathlib import Path

from ..prompts import render_prompt
from ..schemas.tailor import CoverLetterResult, JDAnalysisResult, TailoredCVResult
from ..skills.skill_loader import SkillLoader, SkillRegistry
from .llm_client import LLMClient
from ..agents.tools.context_budgets import CL_BODY, CL_SNIPPET
from .jd_analyser import _split_jinja_output
from .writing_contracts import (
    COVER_LETTER_GENERATION_PROMPT,
    COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT,
    COVER_LETTER_REPAIR_PROMPT,
    EVIDENCE_SCHEMA_VERSION,
    FINAL_COMPLIANCE_REMINDER,
    SHARED_FACTUALITY_CONTRACT,
    SHARED_NUMERIC_FIDELITY_CONTRACT,
    EvidenceItem,
    GenerationProvenance,
    ValidationIssue,
    ValidationResult,
    build_evidence_ledger,
    evidence_records,
    validate_numeric_fidelity,
)
from .writing_workflow import (
    AttemptDiagnostic,
    CoverLetterContentPlan,
    CreateContentPlanInput,
    DraftGeneration,
    GenerateDraftInput,
    RepairSpecificFailureInput,
    SelectEvidenceInput,
    ValidateDraftInput,
    WorkflowDiagnostics,
    build_job_requirements,
    create_content_plan,
    select_evidence,
    select_repair_action,
    unused_evidence_ids,
    validate_content_plan,
)

logger = logging.getLogger(__name__)

_MAX_WORDS = 350
_MIN_WORDS = 250
_TARGET_WORD_RANGE = "285-315"
_SKILLS_DIR = Path(__file__).parent.parent / "skills"

COVER_LETTER_WORD_RE = re.compile(
    r"""
    (?:https?://|www\.)[^\s<>()]+
    |[\w.+-]+@[\w.-]+\.[^\W\d_]{2,}
    |(?:[^\W\d_]\.){2,}
    |(?:[£$€¥])?\d+(?:[.,]\d+)*(?:[kmb])?(?:%|\+)?
       (?:[-–—]\d+(?:[.,]\d+)*(?:[kmb])?(?:%|\+)?)?
       (?:/[A-Za-z]+)?
    |[^\W\d_]+(?:['’][^\W\d_]+)*(?:-[^\W\d_]+)*
    """,
    re.UNICODE | re.VERBOSE | re.IGNORECASE,
)

_FORMAL_SECTORS = frozenset(
    {"construction", "finance", "government", "energy", "defence", "defense",
     "infrastructure", "utilities", "public sector", "legal", "banking"}
)
_CONVERSATIONAL_SECTORS = frozenset(
    {"technology", "tech", "startup", "creative", "media", "advertising",
     "design", "gaming", "software", "saas"}
)

_NUMERIC_TOKEN_RE = re.compile(
    r"(?:[£$€¥])?\d+(?:[.,]\d+)*(?:[kmb])?(?:%|\+)?"
    r"(?:[-–—]\d+(?:[.,]\d+)*(?:[kmb])?(?:%|\+)?)?"
    r"(?:/[A-Za-z]+)?",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(r"\[[^\]]+\]|\bPLACEHOLDER\b|\bTODO\b", re.IGNORECASE)


def select_tone_variant(jd_analysis: "JDAnalysisResult") -> str:
    """Return 'A' (formal) or 'B' (conversational) based on JD sector.

    Formal sectors (A): construction, finance, government, energy, defence.
    Conversational sectors (B): tech, startup, creative.
    Defaults to 'A' when sector is absent or unrecognised.
    """
    sector = (getattr(jd_analysis, "sector", None) or "").lower()
    if any(s in sector for s in _CONVERSATIONAL_SECTORS):
        return "B"
    return "A"


def _default_skill_loader() -> SkillLoader:
    return SkillLoader(SkillRegistry(_SKILLS_DIR))


def _latest_observation(client: Any) -> Any | None:
    observations = vars(client).get("observations")
    if isinstance(observations, (list, tuple)) and observations:
        return observations[-1]
    return None


def _model_id(client: Any) -> str | None:
    spec = vars(client).get("spec")
    for field in ("id", "model"):
        value = getattr(spec, field, None)
        if isinstance(value, str) and value:
            return value
    try:
        from ..agents.tools.profile_loader import load_profile  # noqa: PLC0415

        value = load_profile().llm.primary_model
        return value if isinstance(value, str) and value else None
    except Exception:
        return None


def count_cover_letter_body_words(text: str) -> int:
    """Count substantive cover-letter body words using the PR1 contract tokenizer."""
    normalized = " ".join(text.split())
    count = 0
    for match in COVER_LETTER_WORD_RE.findall(normalized):
        token = match.rstrip(".,;:!?") if match.startswith(("http://", "https://", "www.")) else match
        if token:
            count += 1
    return count


def _body_word_count(paragraphs: list[str]) -> int:
    return count_cover_letter_body_words(" ".join(paragraphs))


def _length_issue(result: CoverLetterResult) -> str:
    return f"Cover letter body has {result.word_count} words; expected 250-350."


def _paragraph_word_counts(result: CoverLetterResult) -> list[int]:
    return [count_cover_letter_body_words(paragraph) for paragraph in result.body_paragraphs]


def _length_repair_instruction(result: CoverLetterResult, defect: str) -> str:
    paragraph_counts = _paragraph_word_counts(result)
    if defect == "under_length":
        guidance_minimums = [45, 75, 70, 55, 30]
        short = [
            f"paragraph {index + 1}: {count} words"
            for index, count in enumerate(paragraph_counts)
            if index < len(guidance_minimums) and count < guidance_minimums[index]
        ]
        return (
            f"The previous draft was {result.word_count} body words. It is below the 250-word minimum. "
            "Repair only this defect and return a complete replacement JSON letter with five body paragraphs. "
            f"Use a target of {_TARGET_WORD_RANGE} body words. "
            f"Paragraphs below guidance budget: {', '.join(short) if short else 'not calculated'}. "
            "Add concrete approved evidence already present in the tailored CV or personal details; do not add filler, "
            "unsupported claims, or new numeric claims. Preserve all existing immutable numeric tokens and valid claims."
        )

    longest = sorted(
        ((count, index + 1) for index, count in enumerate(paragraph_counts)),
        reverse=True,
    )[:2]
    longest_text = ", ".join(f"paragraph {index}: {count} words" for count, index in longest)
    return (
        f"The previous draft was {result.word_count} body words. It is above the 350-word maximum. "
        "Repair only this defect and return a complete replacement JSON letter with five body paragraphs. "
        f"Use a target of {_TARGET_WORD_RANGE} body words; compress the longest paragraphs "
        f"({longest_text or 'not calculated'}) without deleting required evidence. "
        "Preserve all immutable numeric tokens."
    )


def _numeric_repair_instruction(result: CoverLetterResult) -> str:
    issues = "; ".join(result.grounding_issues)
    return (
        "The previous draft failed numeric-fidelity validation. "
        f"Issues: {issues}. "
        "Repair only the numeric issue. If an approved immutable token was changed, restore it exactly. "
        "If a numeric token is unsupported, remove it or replace it with approved non-numeric wording. "
        "Do not add new numbers, estimates, rounded values, or inferred claims. Preserve all other valid content."
    )


def _repair_instruction(result: CoverLetterResult, defect: str) -> str:
    if defect in {"unsupported_numeric_token", "mutated_numeric_token"}:
        return _numeric_repair_instruction(result)
    if defect == "missing_required_fields":
        return (
            "The previous draft failed required-field or placeholder validation. "
            "Repair only that defect. Return non-empty subject, greeting, body paragraphs, "
            "and sign-off without placeholders. Preserve all valid evidence and numbers."
        )
    return _length_repair_instruction(result, defect)


class CoverLetterGenerator:
    """Generates and refines cover letters for job applications."""

    def __init__(self, claude_client: LLMClient, skill_loader: SkillLoader | None = None) -> None:
        self._client = claude_client
        self._skill_loader = skill_loader or _default_skill_loader()

    def select_evidence(self, stage_input: SelectEvidenceInput):
        return select_evidence(stage_input.ledger)

    def create_content_plan(
        self,
        stage_input: CreateContentPlanInput,
    ) -> CoverLetterContentPlan:
        return create_content_plan(
            stage_input.selection,
            stage_input.requirements,
        )

    async def generate_draft(
        self,
        stage_input: GenerateDraftInput,
    ) -> DraftGeneration:
        prompt_metadata = (
            COVER_LETTER_REPAIR_PROMPT
            if stage_input.repair_instruction
            else COVER_LETTER_GENERATION_PROMPT
        )
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "cl_generation.j2",
                jd_analysis=stage_input.jd_analysis.model_dump(),
                tailored_cv=stage_input.tailored_cv.model_dump(),
                personal=stage_input.personal,
                variant=stage_input.variant,
                trim_instruction=stage_input.repair_instruction,
                skill_instructions=stage_input.skill_instructions,
                approved_evidence=evidence_records(stage_input.evidence_ledger),
                content_plan=stage_input.content_plan.to_dict(),
                unused_approved_evidence=evidence_records(
                    stage_input.unused_evidence
                ),
                shared_factuality_contract=SHARED_FACTUALITY_CONTRACT,
                shared_numeric_fidelity_contract=SHARED_NUMERIC_FIDELITY_CONTRACT,
                prompt_metadata=asdict(prompt_metadata),
                final_compliance_reminder=FINAL_COMPLIANCE_REMINDER,
            )
        )
        started = time.monotonic()
        raw: dict[str, Any] = await self._client.complete_json(
            system_prompt,
            user_prompt,
            max_tokens=CL_BODY.max_output,
        )
        latency_ms = (time.monotonic() - started) * 1000
        observation = _latest_observation(self._client)
        return DraftGeneration(
            draft=_parse_cover_letter(raw),
            latency_ms=latency_ms,
            input_tokens=getattr(observation, "prompt_tokens", None),
            output_tokens=getattr(observation, "completion_tokens", None),
        )

    def validate_draft(
        self,
        stage_input: ValidateDraftInput,
    ) -> ValidationResult:
        result = stage_input.draft
        issues = list(stage_input.content_plan_validation.issues)
        grounding_messages = _validate_cover_letter_grounding(
            result,
            stage_input.tailored_cv,
            stage_input.personal,
            stage_input.jd_text,
        )
        for message in grounding_messages:
            if "mutated immutable numeric token" in message:
                code = "mutated_numeric_token"
                gate = "numeric_fidelity"
            elif "unsupported numeric token" in message:
                code = "unsupported_numeric_token"
                gate = "numeric_fidelity"
            else:
                code = "missing_required_fields"
                gate = "placeholder"
            issues.append(
                ValidationIssue(
                    gate=gate,
                    code=code,
                    severity="blocking",
                    message=message,
                )
            )

        required = (
            result.subject_line.strip(),
            result.greeting.strip(),
            result.sign_off.strip(),
            " ".join(result.body_paragraphs).strip(),
        )
        if not all(required):
            issues.append(
                ValidationIssue(
                    gate="required_fields",
                    code="missing_required_fields",
                    severity="blocking",
                    message="Cover letter is missing one or more required fields.",
                )
            )

        if result.word_count < _MIN_WORDS:
            issues.append(
                ValidationIssue(
                    gate="body_length",
                    code="under_length",
                    severity="blocking",
                    message=_length_issue(result),
                    expected=f"{_MIN_WORDS}-{_MAX_WORDS}",
                    observed=str(result.word_count),
                )
            )
        elif result.word_count > _MAX_WORDS:
            issues.append(
                ValidationIssue(
                    gate="body_length",
                    code="over_length",
                    severity="blocking",
                    message=_length_issue(result),
                    expected=f"{_MIN_WORDS}-{_MAX_WORDS}",
                    observed=str(result.word_count),
                )
            )

        deduplicated: list[ValidationIssue] = []
        seen = set()
        for issue in issues:
            key = (issue.gate, issue.code, issue.message)
            if key not in seen:
                seen.add(key)
                deduplicated.append(issue)
        return ValidationResult(
            passed=not any(
                issue.severity == "blocking" for issue in deduplicated
            ),
            issues=tuple(deduplicated),
            metrics={
                "body_word_count": result.word_count,
                "paragraph_count": len(result.body_paragraphs),
                "blocking_issue_count": sum(
                    issue.severity == "blocking" for issue in deduplicated
                ),
            },
        )

    async def repair_specific_failure(
        self,
        stage_input: RepairSpecificFailureInput,
    ) -> DraftGeneration:
        unused = (
            stage_input.unused_evidence
            if stage_input.repair_action == "under_length"
            else ()
        )
        generation_input = stage_input.generation_input
        return await self.generate_draft(
            GenerateDraftInput(
                content_plan=generation_input.content_plan,
                evidence_ledger=generation_input.evidence_ledger,
                jd_analysis=generation_input.jd_analysis,
                tailored_cv=generation_input.tailored_cv,
                personal=generation_input.personal,
                variant=generation_input.variant,
                skill_instructions=generation_input.skill_instructions,
                jd_text=generation_input.jd_text,
                repair_instruction=_repair_instruction(
                    stage_input.draft,
                    stage_input.repair_action,
                ),
                unused_evidence=unused,
            )
        )

    def render_document(
        self,
        result: CoverLetterResult,
        renderer: Callable[[], tuple[str, int]],
    ) -> tuple[str, int]:
        """Run the explicit render stage only for a passing workflow result."""
        if result.validation_status not in {"passed", "repaired"}:
            raise ValueError("Cover letter workflow is not ready to render")
        return renderer()

    async def generate(
        self,
        jd_analysis: JDAnalysisResult,
        tailored_cv: TailoredCVResult,
        personal: dict[str, Any],
        variant: str = "A",
        jd_text: str = "",
    ) -> CoverLetterResult:
        """Generate a cover letter for the given JD and tailored CV.

        Args:
            jd_analysis: Parsed JD analysis.
            tailored_cv: CV tailored to the JD.
            personal: Personal details dict from master CV.
            variant: "A" (formal) or "B" (conversational).

        Returns:
            CoverLetterResult, trimmed to <= 350 words.
        """
        contract = self._skill_loader.contract("cover-letter")
        if contract is None:
            raise ValueError("Cover-letter skill contract is unavailable")
        skill_instructions = self._skill_loader.instructions("cover-letter")
        evidence_source = tailored_cv.model_dump(mode="json")
        evidence_source["personal"] = personal
        evidence_ledger = build_evidence_ledger(evidence_source)
        selection = self.select_evidence(
            SelectEvidenceInput(ledger=evidence_ledger)
        )
        requirements = build_job_requirements(jd_analysis)
        content_plan = self.create_content_plan(
            CreateContentPlanInput(
                selection=selection,
                requirements=requirements,
            )
        )
        plan_validation = validate_content_plan(
            content_plan,
            selection.evidence_ids,
            tuple(item.id for item in requirements),
        )
        run_id = str(uuid.uuid4())
        model_id = _model_id(self._client)
        if not plan_validation.passed:
            result = _empty_failure_result(plan_validation)
            diagnostics = WorkflowDiagnostics(
                run_id=run_id,
                task=COVER_LETTER_GENERATION_PROMPT.task_name,
                skill_id=contract.skill_id,
                skill_version=contract.skill_version,
                prompt_metadata=COVER_LETTER_GENERATION_PROMPT,
                model_id=model_id,
                attempts=(),
                final_state="review_required",
            )
            _attach_workflow_provenance(
                result,
                evidence_ledger,
                content_plan,
                plan_validation,
                diagnostics,
            )
            return result

        base_input = GenerateDraftInput(
            content_plan=content_plan,
            evidence_ledger=evidence_ledger,
            jd_analysis=jd_analysis,
            tailored_cv=tailored_cv,
            personal=personal,
            variant=variant,
            skill_instructions=skill_instructions,
            jd_text=jd_text,
        )
        unused_ids = set(unused_evidence_ids(selection, content_plan))
        unused_evidence = tuple(
            item for item in selection.evidence if item.id in unused_ids
        )
        attempts: list[AttemptDiagnostic] = []
        repairs: list[str] = []
        generated = await self.generate_draft(base_input)
        first_pass_word_count = generated.draft.word_count

        while True:
            result = generated.draft
            validation = self.validate_draft(
                ValidateDraftInput(
                    draft=result,
                    tailored_cv=tailored_cv,
                    personal=personal,
                    evidence_ledger=evidence_ledger,
                    content_plan_validation=plan_validation,
                    jd_text=jd_text,
                )
            )
            attempt_number = len(attempts) + 1
            repair_type = repairs[-1] if repairs else None
            attempts.append(
                AttemptDiagnostic(
                    attempt_number=attempt_number,
                    repair_type=repair_type,
                    input_tokens=generated.input_tokens,
                    output_tokens=generated.output_tokens,
                    latency_ms=generated.latency_ms,
                    validation=validation,
                    computed_body_count=result.word_count,
                )
            )
            result.attempt_count = attempt_number
            result.repair_count = len(repairs)
            result.first_pass_word_count = first_pass_word_count
            result.validation_issues = [
                issue.message
                for issue in validation.issues
                if issue.severity == "blocking"
            ]
            result.grounding_issues = [
                issue.message
                for issue in validation.issues
                if issue.severity == "blocking"
                and issue.gate in {
                    "numeric_fidelity",
                    "placeholder",
                    "required_fields",
                    "content_plan_ids",
                }
            ]
            if validation.passed:
                result.validation_status = (
                    "repaired" if repairs else "passed"
                )
                final_state = result.validation_status
                diagnostics = WorkflowDiagnostics(
                    run_id=run_id,
                    task=COVER_LETTER_GENERATION_PROMPT.task_name,
                    skill_id=contract.skill_id,
                    skill_version=contract.skill_version,
                    prompt_metadata=COVER_LETTER_GENERATION_PROMPT,
                    model_id=model_id,
                    attempts=tuple(attempts),
                    final_state=final_state,
                )
                _attach_workflow_provenance(
                    result,
                    evidence_ledger,
                    content_plan,
                    validation,
                    diagnostics,
                )
                return result

            repair_action = select_repair_action(
                validation,
                contract.allowed_repair_actions,
                tuple(repairs),
            )
            if (
                repair_action is None
                or attempt_number >= contract.maximum_attempts
            ):
                result.validation_status = contract.safe_failure_state
                diagnostics = WorkflowDiagnostics(
                    run_id=run_id,
                    task=COVER_LETTER_GENERATION_PROMPT.task_name,
                    skill_id=contract.skill_id,
                    skill_version=contract.skill_version,
                    prompt_metadata=COVER_LETTER_GENERATION_PROMPT,
                    model_id=model_id,
                    attempts=tuple(attempts),
                    final_state="review_required",
                )
                _attach_workflow_provenance(
                    result,
                    evidence_ledger,
                    content_plan,
                    validation,
                    diagnostics,
                )
                return result

            logger.info(
                "Cover letter %d words — requesting %s repair (variant %s)",
                result.word_count,
                repair_action.replace("_", "-"),
                variant,
            )
            repairs.append(repair_action)
            generated = await self.repair_specific_failure(
                RepairSpecificFailureInput(
                    repair_action=repair_action,
                    draft=result,
                    generation_input=base_input,
                    unused_evidence=unused_evidence,
                )
            )

    async def regenerate_paragraph(
        self,
        paragraph_index: int,
        instruction: str,
        current_letter: CoverLetterResult,
        jd_analysis: JDAnalysisResult,
    ) -> CoverLetterResult:
        """Regenerate a single paragraph of an existing cover letter.

        Args:
            paragraph_index: 0-3 index of the paragraph to replace.
            instruction: User guidance for the regeneration.
            current_letter: The current full cover letter.
            jd_analysis: JD analysis for context.

        Returns:
            Updated CoverLetterResult with the new paragraph.
        """
        paragraphs = current_letter.body_paragraphs
        current_para = paragraphs[paragraph_index] if paragraph_index < len(paragraphs) else ""
        evidence_ledger = build_evidence_ledger(
            {"summary": "\n".join(current_letter.body_paragraphs)}
        )
        system = "\n\n".join(
            (
                "You are an expert cover letter writer. Rewrite only the specified paragraph.",
                SHARED_FACTUALITY_CONTRACT,
                SHARED_NUMERIC_FIDELITY_CONTRACT,
                "PROMPT METADATA:\n"
                + json.dumps(
                    asdict(COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT),
                    sort_keys=True,
                ),
            )
        )

        user = (
            "APPROVED_EVIDENCE:\n"
            f"{json.dumps(evidence_records(evidence_ledger), ensure_ascii=False, sort_keys=True)}\n\n"
            f"Current paragraph {paragraph_index + 1}:\n{current_para}\n\n"
            f"Instruction: {instruction}\n\n"
            f"JD role: {jd_analysis.role_title}\n"
            f"Key keywords: {', '.join(jd_analysis.ats_keywords.technical[:10])}\n\n"
            f"Return JSON: {{\"paragraph\": \"<rewritten paragraph>\"}}\n\n"
            f"{FINAL_COMPLIANCE_REMINDER}"
        )
        raw: dict[str, Any] = await self._client.complete_json(system, user, max_tokens=CL_SNIPPET.max_output)
        new_para = raw.get("paragraph", current_para)

        new_paragraphs = list(paragraphs)
        if paragraph_index < len(new_paragraphs):
            new_paragraphs[paragraph_index] = new_para
        else:
            new_paragraphs.append(new_para)

        result = CoverLetterResult(
            subject_line=current_letter.subject_line,
            greeting=current_letter.greeting,
            body_paragraphs=new_paragraphs,
            sign_off=current_letter.sign_off,
            word_count=_body_word_count(new_paragraphs),
            key_keywords_used=current_letter.key_keywords_used,
            grounding_issues=list(current_letter.grounding_issues),
        )
        numeric_validation = validate_numeric_fidelity(
            [new_para],
            evidence_ledger,
        )
        result.grounding_issues = list(
            dict.fromkeys(
                [
                    *result.grounding_issues,
                    *(
                        issue.message
                        for issue in numeric_validation.issues
                        if issue.severity == "blocking"
                    ),
                ]
            )
        )
        result.generation_provenance = GenerationProvenance(
            prompt_metadata=COVER_LETTER_PARAGRAPH_REGENERATION_PROMPT,
            evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
            source_evidence_ids=tuple(item.id for item in evidence_ledger),
            validation=numeric_validation,
        )
        return result


def _parse_cover_letter(raw: dict[str, Any]) -> CoverLetterResult:
    """Convert raw Claude JSON into CoverLetterResult."""
    paragraphs: list[str] = raw.get("body_paragraphs", [])

    return CoverLetterResult(
        subject_line=raw.get("subject_line", "Application"),
        greeting=raw.get("greeting", "Dear Hiring Manager,"),
        body_paragraphs=paragraphs,
        sign_off=raw.get("sign_off", "Yours sincerely,"),
        word_count=_body_word_count(paragraphs),
        key_keywords_used=raw.get("key_keywords_used", []),
        grounding_issues=raw.get("grounding_issues", []),
    )


def _empty_failure_result(validation: ValidationResult) -> CoverLetterResult:
    return CoverLetterResult(
        subject_line="",
        greeting="",
        body_paragraphs=[],
        sign_off="",
        word_count=0,
        grounding_issues=[
            issue.message
            for issue in validation.issues
            if issue.severity == "blocking"
        ],
        validation_status="review_required",
        validation_issues=[
            issue.message
            for issue in validation.issues
            if issue.severity == "blocking"
        ],
        attempt_count=0,
    )


def _attach_workflow_provenance(
    result: CoverLetterResult,
    evidence_ledger: tuple[EvidenceItem, ...],
    content_plan: CoverLetterContentPlan,
    validation: ValidationResult,
    diagnostics: WorkflowDiagnostics,
) -> None:
    result.generation_provenance = GenerationProvenance(
        prompt_metadata=COVER_LETTER_GENERATION_PROMPT,
        evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
        source_evidence_ids=tuple(item.id for item in evidence_ledger),
        validation=validation,
        content_plan=content_plan.to_dict(),
        workflow=diagnostics.to_dict(),
    )


def _source_text(tailored_cv: TailoredCVResult, personal: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(tailored_cv.summary)
    for skill_group in tailored_cv.skills:
        if isinstance(skill_group, dict):
            parts.append(str(skill_group.get("category") or skill_group.get("display_name") or ""))
            parts.extend(str(item) for item in skill_group.get("items", []) if item)
    for exp in tailored_cv.experience:
        parts.extend([exp.role, exp.company, exp.period])
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
    parts.extend(str(value) for value in personal.values() if value)
    return " ".join(parts)


def _normalise_numeric_token(token: str) -> str:
    return " ".join(token.strip().rstrip(".,;:!?").split()).lower()


def _numeric_tokens(text: str) -> list[str]:
    return [
        token
        for token in (_normalise_numeric_token(match) for match in _NUMERIC_TOKEN_RE.findall(text))
        if token
    ]


def _mutated_numeric_forms(token: str) -> set[str]:
    forms: set[str] = set()
    if token.endswith("+"):
        forms.add(token[:-1])
    if token.endswith("%"):
        forms.add(token[:-1])
    currency_match = re.match(r"^[£$€¥](.+)$", token)
    if currency_match:
        forms.add(currency_match.group(1))
    return {item for item in forms if item and item != token}


def _validate_cover_letter_grounding(
    result: CoverLetterResult,
    tailored_cv: TailoredCVResult,
    personal: dict[str, Any],
    jd_text: str = "",
) -> list[str]:
    text = " ".join(
        [result.subject_line, result.greeting, result.sign_off] + result.body_paragraphs
    )
    body_text = " ".join(result.body_paragraphs)
    candidate_tokens = set(_numeric_tokens(_source_text(tailored_cv, personal)))
    employer_tokens = set(_numeric_tokens(jd_text))
    generated_tokens = _numeric_tokens(body_text)
    generated_token_set = set(generated_tokens)
    issues: list[str] = []
    if _PLACEHOLDER_RE.search(text):
        issues.append("Cover letter contains placeholder text.")

    for expected in sorted(candidate_tokens):
        observed = sorted(_mutated_numeric_forms(expected) & generated_token_set)
        if observed and expected not in generated_token_set:
            issues.append(
                f"Cover letter mutated immutable numeric token '{expected}' as '{observed[0]}'."
            )

    for token in _NUMERIC_TOKEN_RE.findall(body_text):
        normalized = _normalise_numeric_token(token)
        if normalized not in candidate_tokens and normalized not in employer_tokens:
            issues.append(f"Cover letter unsupported numeric token '{token}'.")
    return issues
