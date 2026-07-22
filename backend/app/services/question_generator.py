"""Strict, bounded interview-question generation for Coach sessions."""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Iterator

from ..agents.tools.context_budgets import QUESTION_GEN
from ..config import settings
from ..observability import get_telemetry, trace_stage
from ..prompts import render_prompt
from ..schemas.coach import CompanyResearchResponse, QuestionPresentation, SessionConfig
from .coach_contracts import (
    CoachDiagnostic,
    CoachGateCode,
    configured_model_id,
    run_with_stage_deadline,
)
from .jd_analyser import _split_jinja_output
from .llm_client import LLMClient
from .master_cv_store import load_master_cv
from .prompt_catalog import prompt_contract_block, prompt_metadata

logger = logging.getLogger(__name__)

_CATEGORY_WEIGHTS = {
    "Technical": 0.30,
    "Behavioural": 0.25,
    "Situational": 0.15,
    "Domain": 0.10,
    "Culture": 0.10,
    "Commercial": 0.10,
}
_ALLOWED_DIFFICULTIES = {"easy", "medium", "hard"}
_PROMPT_INJECTION_RE = re.compile(
    r"\b(?:ignore|disregard|override)\b.{0,40}\b(?:instruction|prompt|system|previous)\b",
    re.IGNORECASE,
)
_CANDIDATE_ASSERTION_RE = re.compile(
    r"\b(?:given|based on)\s+your\b|"
    r"\byour\s+\d+(?:\.\d+)?\b|"
    r"\byour\s+(?:experience|achievement|role|work)\s+(?:at|with)\b",
    re.IGNORECASE,
)


def _load_candidate_summary() -> str:
    """Load a condensed candidate summary from the master CV for prompt context."""
    try:
        cv = load_master_cv()
        personal = cv.get("personal", {})
        summary_variants = cv.get("summary_variants", {})
        summary = next(iter(summary_variants.values()), "")
        skills = cv.get("skills", {})
        if isinstance(skills, dict):
            skills_text = "; ".join(
                cat.get("display_name", "") + ": " + ", ".join(cat.get("items", [])[:5])
                for cat in skills.values()
                if isinstance(cat, dict)
            )
        else:
            skills_text = ""
        name = personal.get("full_name", "Candidate")
        return f"{name}\n\nSummary: {summary[:500]}\n\nKey Skills: {skills_text[:500]}"
    except Exception as exc:
        logger.warning("Failed to load master CV for question generation: %s", exc)
        return "Candidate"


@dataclass(frozen=True)
class QuestionGenerationResult:
    """Validated questions plus initial, optional repair, and final diagnostics."""

    questions: list[QuestionPresentation]
    initial_diagnostic: CoachDiagnostic
    repair_diagnostic: CoachDiagnostic | None
    final_diagnostic: CoachDiagnostic

    def __iter__(self) -> Iterator[QuestionPresentation]:
        return iter(self.questions)

    def __len__(self) -> int:
        return len(self.questions)

    def __getitem__(self, index: int) -> QuestionPresentation:
        return self.questions[index]


class QuestionGenerationContractError(ValueError):
    """Raised when no exact, fully validated question set can be activated."""

    def __init__(self, result: QuestionGenerationResult) -> None:
        self.result = result
        super().__init__("Coach question generation contract was not satisfied")


@dataclass(frozen=True)
class _Validation:
    accepted: list[QuestionPresentation]
    gate_codes: list[CoachGateCode]


def _unique_gates(gates: list[CoachGateCode]) -> list[CoachGateCode]:
    return list(dict.fromkeys(gates))


def _normalise_question(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


def _extract_question_items(raw: Any) -> list[Any] | None:
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, dict):
        return None
    for key in ("questions", "items", "data", "interview_questions"):
        if key in raw:
            return raw[key] if isinstance(raw[key], list) else None
    list_values = [value for value in raw.values() if isinstance(value, list)]
    return list_values[0] if len(list_values) == 1 else None


def _validate_questions(
    raw: Any,
    expected_count: int,
    requirement_ids: tuple[str, ...],
) -> _Validation:
    items = _extract_question_items(raw)
    if items is None:
        return _Validation([], ["coach_question_parse_invalid"])

    accepted: list[QuestionPresentation] = []
    gates: list[CoachGateCode] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            gates.append("coach_question_parse_invalid")
            continue

        item_gates: list[CoachGateCode] = []
        text = item.get("text")
        text = text.strip() if isinstance(text, str) else ""
        normalized = _normalise_question(text)
        if not normalized:
            item_gates.append("coach_question_parse_invalid")
        elif normalized in seen:
            item_gates.append("coach_question_duplicate")
        else:
            seen.add(normalized)

        category = item.get("category")
        if category not in _CATEGORY_WEIGHTS:
            item_gates.append("coach_question_category_invalid")

        difficulty = item.get("difficulty")
        if difficulty not in _ALLOWED_DIFFICULTIES:
            item_gates.append("coach_question_difficulty_invalid")

        requirement_id = item.get("requirement_id")
        if not isinstance(requirement_id, str) or requirement_id not in requirement_ids:
            item_gates.append("coach_question_requirement_unknown")

        if _PROMPT_INJECTION_RE.search(text):
            item_gates.append("coach_question_prompt_injection_followed")
        if _CANDIDATE_ASSERTION_RE.search(text):
            item_gates.append("coach_question_candidate_claim")
        if item.get("model_answer") not in (None, ""):
            item_gates.append("coach_question_parse_invalid")

        if item_gates:
            gates.extend(item_gates)
            continue

        context = item.get("context")
        accepted.append(
            QuestionPresentation(
                id=f"q_{len(accepted) + 1}",
                text=text,
                category=category,
                difficulty=difficulty,
                context=context if isinstance(context, str) else None,
                requirement_id=requirement_id,
                num=len(accepted) + 1,
                total=expected_count,
            )
        )

    if len(items) != expected_count or len(accepted) != expected_count:
        gates.append("coach_question_count_mismatch")
    return _Validation(accepted, _unique_gates(gates))


def _diagnostic(
    *,
    stage: str,
    prompt_id: str,
    outcome: str,
    gate_codes: list[CoachGateCode],
    duration_ms: int,
    model_id: str,
) -> CoachDiagnostic:
    metadata = prompt_metadata(prompt_id)
    return CoachDiagnostic(
        stage=stage,
        outcome=outcome,
        execution_mode="llm",
        prompt_id=metadata.prompt_id,
        prompt_version=metadata.prompt_version,
        output_schema_version=metadata.schema_version,
        model_id=model_id,
        attempt_count=1,
        repair_count=0,
        gate_codes=gate_codes,
        duration_ms=duration_ms,
    )


def _final_diagnostic(
    *, outcome: str, attempts: int, repair_count: int, gates: list[CoachGateCode]
) -> CoachDiagnostic:
    return CoachDiagnostic(
        stage="question_generation",
        outcome=outcome,
        execution_mode="deterministic",
        attempt_count=attempts,
        repair_count=repair_count,
        gate_codes=_unique_gates(gates),
        duration_ms=0,
    )


class QuestionGeneratorService:
    """Generate an exact question set with at most one targeted repair."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    async def _invoke(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        timeout_seconds: int,
    ) -> tuple[Any, int]:
        started = time.monotonic()
        try:
            raw = await run_with_stage_deadline(
                self._client.complete_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=QUESTION_GEN.max_output,
                ),
                timeout_seconds,
            )
        except Exception:
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=configured_model_id(self._client),
                duration_ms=(time.monotonic() - started) * 1000,
                outcome="failed",
            )
            raise
        duration_ms = int((time.monotonic() - started) * 1000)
        get_telemetry().record_model_call(
            workflow="coach_generation",
            provider=type(self._client).__name__,
            model_id=configured_model_id(self._client),
            duration_ms=duration_ms,
        )
        return raw, duration_ms

    @trace_stage("coach_generation", "generate_initial")
    async def generate(
        self,
        config: SessionConfig,
        company_name: str,
        role_title: str,
        company_research: CompanyResearchResponse | None = None,
        jd_text: str | None = None,
    ) -> QuestionGenerationResult:
        candidate_summary = _load_candidate_summary()
        research_dict = (
            company_research.model_dump(mode="json")
            if company_research and company_research.verification_state != "not_verified"
            else {}
        )
        requirements = _build_requirements(jd_text or role_title)
        requirement_ids = tuple(item["requirement_id"] for item in requirements)
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "question_generation.j2",
                question_count=config.question_count,
                role_title=role_title,
                company_name=company_name,
                company_research=research_dict,
                jd_text=jd_text or "",
                candidate_summary=candidate_summary,
                difficulty=config.difficulty,
                requirements=requirements,
                prompt_contract=prompt_contract_block("question_generation"),
            )
        )

        try:
            raw, duration_ms = await self._invoke(
                system_prompt,
                user_prompt,
                timeout_seconds=settings.HATCH_COACH_TIMEOUT_QUESTION_GENERATION_SECONDS,
            )
        except TimeoutError:
            initial = _diagnostic(
                stage="question_generation",
                prompt_id="question_generation",
                outcome="unavailable",
                gate_codes=["coach_stage_timeout"],
                duration_ms=0,
                model_id=configured_model_id(self._client),
            )
            result = QuestionGenerationResult(
                [], initial, None,
                _final_diagnostic(
                    outcome="unavailable", attempts=1, repair_count=0,
                    gates=["coach_stage_timeout"],
                ),
            )
            raise QuestionGenerationContractError(result) from None
        except Exception:
            initial = _diagnostic(
                stage="question_generation",
                prompt_id="question_generation",
                outcome="unavailable",
                gate_codes=["coach_stage_failed"],
                duration_ms=0,
                model_id=configured_model_id(self._client),
            )
            result = QuestionGenerationResult(
                [], initial, None,
                _final_diagnostic(
                    outcome="unavailable", attempts=1, repair_count=0,
                    gates=["coach_stage_failed"],
                ),
            )
            raise QuestionGenerationContractError(result) from None

        initial_validation = _validate_questions(
            raw, config.question_count, requirement_ids
        )
        initial = _diagnostic(
            stage="question_generation",
            prompt_id="question_generation",
            outcome=("completed" if not initial_validation.gate_codes else "invalid_output"),
            gate_codes=initial_validation.gate_codes,
            duration_ms=duration_ms,
            model_id=configured_model_id(self._client),
        )
        for gate in initial_validation.gate_codes:
            get_telemetry().record_validation_failure("coach_generation", gate)
        if not initial_validation.gate_codes:
            return QuestionGenerationResult(
                initial_validation.accepted,
                initial,
                None,
                _final_diagnostic(
                    outcome="completed", attempts=1, repair_count=0, gates=[]
                ),
            )

        retained = initial_validation.accepted
        if len(retained) >= config.question_count:
            retained = []
        retained_hashes = [
            hashlib.sha256(_normalise_question(question.text).encode()).hexdigest()[:12]
            for question in retained
        ]
        repair_system, repair_user = _split_jinja_output(
            render_prompt(
                "question_generation_repair.j2",
                prompt_contract=prompt_contract_block("question_generation_repair"),
                additional_count=config.question_count - len(retained),
                allowed_categories=list(_CATEGORY_WEIGHTS),
                allowed_requirement_ids=list(requirement_ids),
                findings=initial_validation.gate_codes,
                retained_question_hashes=retained_hashes,
                role_title=role_title,
                company_name=company_name,
                company_research=research_dict,
                jd_text=jd_text or "",
                candidate_summary=candidate_summary,
                difficulty=config.difficulty,
            )
        )
        try:
            repair_raw, repair_duration = await self._invoke(
                repair_system,
                repair_user,
                timeout_seconds=settings.HATCH_COACH_TIMEOUT_QUESTION_REPAIR_SECONDS,
            )
        except TimeoutError:
            repair = _diagnostic(
                stage="question_generation_repair",
                prompt_id="question_generation_repair",
                outcome="unavailable",
                gate_codes=["coach_stage_timeout"],
                duration_ms=0,
                model_id=configured_model_id(self._client),
            )
            result = QuestionGenerationResult(
                [], initial, repair,
                _final_diagnostic(
                    outcome="unavailable", attempts=2, repair_count=1,
                    gates=["coach_stage_timeout"],
                ),
            )
            raise QuestionGenerationContractError(result) from None
        except Exception:
            repair = _diagnostic(
                stage="question_generation_repair",
                prompt_id="question_generation_repair",
                outcome="unavailable",
                gate_codes=["coach_stage_failed"],
                duration_ms=0,
                model_id=configured_model_id(self._client),
            )
            result = QuestionGenerationResult(
                [], initial, repair,
                _final_diagnostic(
                    outcome="unavailable", attempts=2, repair_count=1,
                    gates=["coach_stage_failed"],
                ),
            )
            raise QuestionGenerationContractError(result) from None

        repair_items = _extract_question_items(repair_raw)
        retained_payload = [
            {
                "text": question.text,
                "category": question.category,
                "difficulty": question.difficulty,
                "context": question.context,
                "requirement_id": question.requirement_id,
            }
            for question in retained
        ]
        assembled_raw = retained_payload + (repair_items or [])
        final_validation = _validate_questions(
            assembled_raw, config.question_count, requirement_ids
        )
        repair_gates = list(final_validation.gate_codes)
        repair = _diagnostic(
            stage="question_generation_repair",
            prompt_id="question_generation_repair",
            outcome=("completed" if not repair_gates else "invalid_output"),
            gate_codes=repair_gates,
            duration_ms=repair_duration,
            model_id=configured_model_id(self._client),
        )
        for gate in repair_gates:
            get_telemetry().record_validation_failure("coach_generation", gate)
        if final_validation.gate_codes:
            final_gates = [*final_validation.gate_codes, "coach_question_repair_exhausted"]
            result = QuestionGenerationResult(
                [], initial, repair,
                _final_diagnostic(
                    outcome="invalid_output", attempts=2, repair_count=1,
                    gates=final_gates,
                ),
            )
            raise QuestionGenerationContractError(result)

        return QuestionGenerationResult(
            final_validation.accepted,
            initial,
            repair,
            _final_diagnostic(
                outcome="completed", attempts=2, repair_count=1, gates=[]
            ),
        )


def _build_requirements(source: str) -> list[dict[str, str]]:
    """Build stable requirement IDs from source JD lines or sentences."""
    candidates = [
        value.strip(" \t-*•")
        for value in re.split(r"[\n.!?]+", source)
        if value.strip(" \t-*•")
    ][:12]
    if not candidates:
        candidates = ["Role requirements"]
    return [
        {
            "requirement_id": (
                "requirement-"
                + hashlib.sha256(text.casefold().encode("utf-8")).hexdigest()[:12]
            ),
            "text": text,
        }
        for text in candidates
    ]


def _parse_questions(
    raw_list: list[dict[str, Any]],
    expected_count: int,
    requirement_ids: tuple[str, ...],
) -> list[QuestionPresentation]:
    """Compatibility wrapper returning only a fully valid exact question set."""
    validation = _validate_questions(raw_list, expected_count, requirement_ids)
    return validation.accepted if not validation.gate_codes else []
