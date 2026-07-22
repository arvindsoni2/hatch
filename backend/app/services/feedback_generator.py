"""Feedback Generator — produces comprehensive session feedback reports via Claude."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ..config import settings
from ..prompts import render_prompt
from ..observability import get_telemetry, trace_stage
from ..schemas.coach import (
    AnswerEvaluation,
    PracticePlanDay,
    QuestionEvaluationSummary,
    SessionFeedbackReport,
)
from .llm_client import LLMClient
from ..agents.tools.context_budgets import FEEDBACK
from .jd_analyser import _split_jinja_output
from .master_cv_store import load_master_cv
from .coach_contracts import (
    CoachDiagnostic,
    configured_attempt_count,
    configured_model_id,
    contains_candidate_history_claim,
    run_with_stage_deadline,
)
from .prompt_catalog import prompt_contract_block, prompt_metadata

logger = logging.getLogger(__name__)

def _load_candidate_name() -> str:
    try:
        cv = load_master_cv()
        return cv.get("personal", {}).get("full_name", "Candidate")
    except Exception:
        return "Candidate"


class FeedbackGeneratorService:
    """Generates comprehensive post-session feedback reports."""

    def __init__(self, claude_client: LLMClient) -> None:
        self._client = claude_client

    @trace_stage("coach_generation", "generate_initial")
    async def generate_report(
        self,
        session_id: str,
        role_title: str,
        company_name: str,
        question_evaluations: list[tuple[str, str, str, AnswerEvaluation]],
        speech_summaries: list[dict[str, Any]] | None = None,
        deterministic_report: SessionFeedbackReport | None = None,
    ) -> SessionFeedbackReport:
        """Generate a full session feedback report.

        Args:
            session_id: ID of the interview session.
            role_title: Role being interviewed for.
            company_name: Company name.
            question_evaluations: List of (question_id, question_text, category, AnswerEvaluation) tuples.
            speech_summaries: Optional list of speech metric dicts across answers.

        Returns:
            SessionFeedbackReport with scores, narrative, and practice plan.
        """
        if deterministic_report is None:
            deterministic_report = _legacy_deterministic_report(
                session_id, question_evaluations
            )
        base = deterministic_report.model_copy(deep=True)
        q_summaries = [item.model_dump(mode="json") for item in base.question_evaluations]

        # Speech summary stats
        speech_summary: dict[str, float] | None = None
        if speech_summaries:
            speech_summary = {
                "avg_fillers": sum(s.get("filler_count", 0) for s in speech_summaries) / len(speech_summaries),
                "avg_wpm": sum(s.get("wpm", 0) for s in speech_summaries) / len(speech_summaries),
                "avg_hedging": sum(s.get("hedging_count", 0) for s in speech_summaries) / len(speech_summaries),
            }

        # Claude narrative generation
        candidate_name = _load_candidate_name()
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "session_report.j2",
                candidate_name=candidate_name,
                role_title=role_title,
                company_name=company_name,
                session_date=datetime.utcnow().strftime("%d %B %Y"),
                answered_count=base.question_count_evaluated,
                total_questions=base.question_count_total,
                overall_score=base.overall_score,
                category_scores=base.category_scores,
                authoritative_improvement_areas=base.improvement_areas,
                question_summaries=q_summaries,
                speech_summary=speech_summary,
                prompt_contract=prompt_contract_block("session_report"),
            )
        )

        started = time.monotonic()
        try:
            raw = await run_with_stage_deadline(
                self._client.complete_json(
                    system_prompt,
                    user_prompt,
                    max_tokens=FEEDBACK.max_output,
                ),
                settings.HATCH_COACH_TIMEOUT_SESSION_REPORT_SECONDS,
            )
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
        except Exception as exc:
            get_telemetry().record_model_call(
                workflow="coach_generation",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
                outcome="failed",
            )
            get_telemetry().mark_current_error(
                "feedback_generation_failed",
                "model_error",
            )
            logger.warning("Session report generation failed: %s — using fallback", exc)
            gate = (
                "coach_stage_timeout"
                if isinstance(exc, TimeoutError)
                else "coach_report_provider_unavailable"
            )
            return _as_fallback(base, self._diagnostic("fallback_deterministic", [gate], started))

        if not isinstance(raw, dict):
            return _as_fallback(
                base,
                self._diagnostic(
                    "fallback_deterministic", ["coach_report_schema_invalid"], started
                ),
            )

        schema_valid = _valid_report_narrative_schema(raw)
        if not schema_valid:
            return _as_fallback(
                base,
                self._diagnostic(
                    "fallback_deterministic", ["coach_report_schema_invalid"], started
                ),
            )

        if _contains_candidate_history_claim(raw):
            return _as_fallback(
                base,
                self._diagnostic(
                    "fallback_deterministic", ["coach_report_unsupported_claim"], started
                ),
            )

        gates = _immutable_report_gates(raw, base)

        # Build practice plan
        practice_plan: list[PracticePlanDay] = []
        for day_raw in raw.get("practice_plan", []):
            try:
                practice_plan.append(PracticePlanDay(**day_raw))
            except Exception:
                pass

        base.executive_summary = str(raw.get("executive_summary") or base.executive_summary)
        for field in ("strengths", "coaching_points"):
            value = raw.get(field)
            if isinstance(value, list) and all(isinstance(item, str) for item in value):
                setattr(base, field, value)
        if raw.get("improvement_areas") == base.improvement_areas:
            base.improvement_areas = raw["improvement_areas"]
        base.practice_plan = practice_plan
        base.report_state = "fallback" if gates else "completed"
        base.diagnostic = self._diagnostic(
            "fallback_deterministic" if gates else "completed",
            gates,
            started,
        )
        return base

    def _diagnostic(
        self, outcome: str, gates: list[str], started: float
    ) -> CoachDiagnostic:
        metadata = prompt_metadata("session_report")
        return CoachDiagnostic(
            stage="session_report",
            outcome=outcome,
            execution_mode="llm",
            prompt_id=metadata.prompt_id,
            prompt_version=metadata.prompt_version,
            output_schema_version=metadata.schema_version,
            model_id=configured_model_id(self._client),
            attempt_count=configured_attempt_count(self._client),
            repair_count=0,
            gate_codes=gates,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _as_fallback(
    report: SessionFeedbackReport, diagnostic: CoachDiagnostic
) -> SessionFeedbackReport:
    fallback = report.model_copy(deep=True)
    fallback.report_state = "fallback"
    fallback.diagnostic = diagnostic
    return fallback


def _immutable_report_gates(
    raw: dict[str, Any], base: SessionFeedbackReport
) -> list[str]:
    gates: list[str] = []
    count_fields = (
        "question_count_total",
        "question_count_evaluated",
        "question_count_skipped",
        "question_count_unavailable",
        "question_count_unanswered",
    )
    if any(field in raw and raw[field] != getattr(base, field) for field in count_fields):
        gates.append("coach_report_count_mismatch")
    score_fields = ("overall_score", "category_scores", "question_evaluations")
    if any(field in raw and raw[field] != getattr(base, field) for field in score_fields):
        gates.append("coach_report_score_mutation")
    if (
        "improvement_areas" in raw
        and raw["improvement_areas"] != base.improvement_areas
    ):
        gates.append("coach_report_priority_mismatch")
    return gates


def _valid_report_narrative_schema(raw: dict[str, Any]) -> bool:
    if not isinstance(raw.get("executive_summary"), str):
        return False
    for field in ("strengths", "improvement_areas", "coaching_points"):
        value = raw.get(field)
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            return False
    practice_plan = raw.get("practice_plan")
    return isinstance(practice_plan, list) and all(
        isinstance(item, dict) for item in practice_plan
    )


def _contains_candidate_history_claim(raw: dict[str, Any]) -> bool:
    narrative = [raw["executive_summary"]]
    for field in ("strengths", "improvement_areas", "coaching_points"):
        narrative.extend(raw[field])
    for item in raw["practice_plan"]:
        narrative.extend(
            str(item[field])
            for field in ("focus", "activity", "resource")
            if item.get(field) is not None
        )
    return any(contains_candidate_history_claim(item) for item in narrative)


def _legacy_deterministic_report(
    session_id: str,
    question_evaluations: list[tuple[str, str, str, AnswerEvaluation]],
) -> SessionFeedbackReport:
    """Compatibility builder for callers not yet supplying persisted attempts."""
    valid = [item for item in question_evaluations if item[3].overall is not None]
    values = [Decimal(str(item[3].overall)) for item in valid]
    overall = (
        float(
            (sum(values) / Decimal(len(values))).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        )
        if values
        else None
    )
    categories: dict[str, list[Decimal]] = {}
    for _, _, category, evaluation in valid:
        categories.setdefault(category, []).append(Decimal(str(evaluation.overall)))
    category_scores = {
        category: float(
            (sum(scores) / Decimal(len(scores))).quantize(
                Decimal("0.1"), rounding=ROUND_HALF_UP
            )
        )
        for category, scores in categories.items()
    }
    summaries = [
        QuestionEvaluationSummary(
            question_id=question_id,
            question_text=question_text,
            category=category,
            overall_score=evaluation.overall,
            scores=evaluation.scores,
            strengths=evaluation.strengths,
            improvements=evaluation.improvements,
        )
        for question_id, question_text, category, evaluation in valid
    ]
    return SessionFeedbackReport(
        session_id=session_id,
        overall_score=overall,
        question_count_total=len(question_evaluations),
        question_count_evaluated=len(valid),
        question_count_unanswered=len(question_evaluations) - len(valid),
        category_scores=category_scores,
        executive_summary=(
            f"{len(valid)} questions received a completed evaluation."
            if valid
            else "No answers received a completed evaluation."
        ),
        question_evaluations=summaries,
    )
