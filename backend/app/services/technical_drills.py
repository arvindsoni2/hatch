"""Prompt-catalogued, validated optional technical interview drills."""
from __future__ import annotations

import logging
import re
import time

from ..config import settings
from ..models.coach_session import SessionQuestion
from ..observability import get_telemetry, trace_stage
from ..prompts import render_prompt
from ..schemas.coach import TechnicalDrill
from .coach_contracts import CoachDiagnostic, configured_model_id, run_with_stage_deadline
from .jd_analyser import _split_jinja_output
from .llm_client import LLMClient
from .prompt_catalog import prompt_contract_block, prompt_metadata

logger = logging.getLogger(__name__)

_TECHNICAL_CATEGORIES = {"technical", "domain"}
_CANDIDATE_CLAIM = re.compile(
    r"\b(?:i|the candidate)\s+(?:built|created|delivered|designed|implemented|led|managed|reduced|saved|worked)\b",
    re.IGNORECASE,
)


class TechnicalDrillsResult(list[TechnicalDrill]):
    """List-compatible drill result with per-item and summary diagnostics."""

    def __init__(
        self,
        items: list[TechnicalDrill],
        items_diagnostics: list[dict[str, object]],
        summary_diagnostic: CoachDiagnostic,
    ) -> None:
        super().__init__(items)
        self.items_diagnostics = items_diagnostics
        self.summary_diagnostic = summary_diagnostic


class TechnicalDrillsService:
    """Build validated drills for technical/domain questions."""

    def __init__(self, claude: LLMClient) -> None:
        self._claude = claude

    async def build_drills(
        self, questions: list[SessionQuestion]
    ) -> TechnicalDrillsResult:
        technical = [
            question
            for question in questions
            if question.category.lower() in _TECHNICAL_CATEGORIES
        ]
        items: list[TechnicalDrill] = []
        diagnostics: list[dict[str, object]] = []
        for question in technical:
            drill, diagnostic = await self._build_single_drill(question)
            diagnostics.append({
                "question_id": question.id,
                "diagnostic": diagnostic.model_dump(mode="json"),
            })
            if drill is not None:
                items.append(drill)

        metadata = prompt_metadata("technical_drill")
        if not technical:
            summary = CoachDiagnostic(
                stage="technical_drill",
                outcome="completed",
                execution_mode="not_run",
                attempt_count=0,
                repair_count=0,
                gate_codes=[],
                duration_ms=0,
            )
        else:
            gates = list(dict.fromkeys(
                gate
                for item in diagnostics
                for gate in item["diagnostic"]["gate_codes"]
            ))
            summary = CoachDiagnostic(
                stage="technical_drill",
                outcome="completed" if len(items) == len(technical) else "unavailable",
                execution_mode="llm",
                prompt_id=metadata.prompt_id,
                prompt_version=metadata.prompt_version,
                output_schema_version=metadata.schema_version,
                model_id=configured_model_id(self._claude),
                attempt_count=len(technical),
                repair_count=0,
                gate_codes=gates,
                duration_ms=sum(
                    int(item["diagnostic"]["duration_ms"]) for item in diagnostics
                ),
            )
        return TechnicalDrillsResult(items, diagnostics, summary)

    @trace_stage("coach_generation", "generate_initial")
    async def _build_single_drill(
        self, question: SessionQuestion
    ) -> tuple[TechnicalDrill | None, CoachDiagnostic]:
        metadata = prompt_metadata("technical_drill")
        system, user = _split_jinja_output(render_prompt(
            "technical_drill.j2",
            question_id=question.id,
            question_text=question.text,
            category=question.category,
            prompt_contract=prompt_contract_block("technical_drill"),
        ))
        started = time.monotonic()
        try:
            raw = await run_with_stage_deadline(
                self._claude.complete_json(system, user),
                settings.HATCH_COACH_TIMEOUT_TECHNICAL_DRILL_SECONDS,
            )
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._claude).__name__,
                model_id=configured_model_id(self._claude),
                duration_ms=(time.monotonic() - started) * 1000,
            )
            gate = _validate_drill(raw, question)
            diagnostic = self._diagnostic(
                metadata,
                "completed" if gate is None else "invalid_output",
                [] if gate is None else [gate],
                started,
            )
            if gate is not None:
                get_telemetry().record_validation_failure("coach_generation", gate)
                return None, diagnostic
            return TechnicalDrill(
                question_id=question.id,
                question_text=question.text,
                walkthrough=raw["walkthrough"].strip(),
                drill_prompt=raw["drill_prompt"].strip(),
                category=question.category,
            ), diagnostic
        except Exception as exc:
            gate = (
                "coach_stage_timeout"
                if isinstance(exc, TimeoutError)
                else "coach_drill_provider_unavailable"
            )
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._claude).__name__,
                model_id=configured_model_id(self._claude),
                duration_ms=(time.monotonic() - started) * 1000,
                outcome="failed",
            )
            get_telemetry().mark_current_error(gate, "model_error")
            logger.warning("Technical drill omitted for question %s: %s", question.id, exc)
            return None, self._diagnostic(metadata, "unavailable", [gate], started)

    def _diagnostic(self, metadata, outcome, gates, started) -> CoachDiagnostic:
        return CoachDiagnostic(
            stage="technical_drill",
            outcome=outcome,
            execution_mode="llm",
            prompt_id=metadata.prompt_id,
            prompt_version=metadata.prompt_version,
            output_schema_version=metadata.schema_version,
            model_id=configured_model_id(self._claude),
            attempt_count=1,
            repair_count=0,
            gate_codes=gates,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _validate_drill(raw: object, question: SessionQuestion) -> str | None:
    if not isinstance(raw, dict):
        return "coach_drill_schema_invalid"
    if raw.get("question_id") != question.id:
        return "coach_drill_question_mismatch"
    if " ".join(str(raw.get("question_text", "")).split()).casefold() != " ".join(
        question.text.split()
    ).casefold():
        return "coach_drill_question_mismatch"
    walkthrough = raw.get("walkthrough")
    drill_prompt = raw.get("drill_prompt")
    if not isinstance(walkthrough, str) or not walkthrough.strip():
        return "coach_drill_schema_invalid"
    if not isinstance(drill_prompt, str) or not drill_prompt.strip():
        return "coach_drill_schema_invalid"
    if len(walkthrough.split()) > 200:
        return "coach_drill_length_exceeded"
    if _CANDIDATE_CLAIM.search(walkthrough) or _CANDIDATE_CLAIM.search(drill_prompt):
        return "coach_drill_candidate_claim"
    return None
