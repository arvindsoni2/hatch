"""ATS Optimiser — scores CV text against JD keywords and provides improvement suggestions."""
from __future__ import annotations

import logging
import time
from typing import Any

from pathlib import Path

from ..prompts import render_prompt
from ..observability import get_telemetry, trace_stage
from ..schemas.tailor import ATSScoreResult, JDAnalysisResult, KeywordMatch
from ..skills.skill_loader import SkillLoader, SkillRegistry
from .llm_client import LLMClient
from ..agents.tools.context_budgets import ATS
from .jd_analyser import _split_jinja_output
from .prompt_catalog import (
    candidate_claim_contract,
    prompt_contract_block,
    validate_candidate_output,
)
from .writing_contracts import build_evidence_ledger, evidence_records

logger = logging.getLogger(__name__)

# Weight split: algorithmic keyword match vs Claude semantic analysis
_ALGO_WEIGHT = 0.40
_SEMANTIC_WEIGHT = 0.60
_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _default_skill_loader() -> SkillLoader:
    return SkillLoader(SkillRegistry(_SKILLS_DIR))


class ATSOptimiser:
    """Scores and optimises CVs for Applicant Tracking Systems."""

    def __init__(self, claude_client: LLMClient, skill_loader: SkillLoader | None = None) -> None:
        self._client = claude_client
        self._skill_loader = skill_loader or _default_skill_loader()

    @trace_stage("cv_tailoring", "validate_output")
    async def score(
        self,
        cv_text: str,
        jd_analysis: JDAnalysisResult,
        evidence_bank: str | None = None,
        target_score: int = 80,
    ) -> ATSScoreResult:
        """Compute a blended ATS score: 40% algorithmic + 60% Claude semantic.

        Args:
            cv_text: Plain text content of the tailored CV.
            jd_analysis: Parsed JD analysis with target keywords.

        Returns:
            ATSScoreResult with overall score and detailed breakdown.
        """
        all_keywords = (
            jd_analysis.ats_keywords.technical
            + jd_analysis.ats_keywords.methodologies
            + jd_analysis.ats_keywords.domain
            + jd_analysis.ats_keywords.certifications
        )
        must_have = jd_analysis.requirements.must_have

        # Algorithmic component
        keyword_matches, algo_score = self._keyword_match(cv_text, all_keywords)
        missing_critical = [kw for kw in must_have if not _kw_in_text(kw, cv_text)]

        # Semantic component via Claude
        skill_instructions = self._skill_loader.instructions("ats-optimization")
        ledger = build_evidence_ledger(
            {
                "summary": cv_text,
                "summary_variants": {"evidence_bank": evidence_bank or ""},
            }
        )
        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "ats_keywords.j2",
                cv_content=cv_text[:6000],  # Stay within token budget
                evidence_bank=(evidence_bank or "")[:3000],
                target_keywords=all_keywords,
                must_have=must_have,
                skill_instructions=skill_instructions,
                approved_evidence=evidence_records(ledger),
                prompt_contract=prompt_contract_block("ats_keywords"),
                candidate_contract=candidate_claim_contract("ats_keywords"),
            )
        )
        started = time.monotonic()
        model_call_completed = False
        try:
            raw: dict[str, Any] = await self._client.complete_json(
                system_prompt,
                user_prompt,
                max_tokens=ATS.max_output,
            )
            get_telemetry().record_model_call(
                workflow="cv_tailoring",
                provider=type(self._client).__name__,
                model_id=str(getattr(self._client, "model", "configured")),
                duration_ms=(time.monotonic() - started) * 1000,
            )
            model_call_completed = True
            semantic_score = float(raw.get("overall_score", 0)) / 100.0
            format_warnings: list[str] = raw.get("format_warnings", [])
            improvement_suggestions = [
                suggestion
                for suggestion in raw.get("improvement_suggestions", [])
                if isinstance(suggestion, str)
                and validate_candidate_output([suggestion], ledger).passed
            ]
        except Exception as exc:
            if not model_call_completed:
                get_telemetry().record_model_call(
                    workflow="cv_tailoring",
                    provider=type(self._client).__name__,
                    model_id=str(getattr(self._client, "model", "configured")),
                    duration_ms=(time.monotonic() - started) * 1000,
                    outcome="failed",
                )
            get_telemetry().mark_current_error(
                (
                    "ats_response_invalid"
                    if model_call_completed
                    else "ats_scoring_failed"
                ),
                (
                    "validation_failure"
                    if model_call_completed
                    else "model_error"
                ),
            )
            logger.warning("Claude ATS scoring failed, using algorithmic only: %s", exc)
            semantic_score = algo_score
            format_warnings = []
            improvement_suggestions = []

        overall = int((_ALGO_WEIGHT * algo_score + _SEMANTIC_WEIGHT * semantic_score) * 100)
        overall = max(0, min(100, overall))

        return ATSScoreResult(
            overall_score=overall,
            target_score=target_score,
            passed_target=overall >= target_score,
            algorithmic_score=round(algo_score * 100, 1),
            semantic_score=round(semantic_score * 100, 1),
            keyword_matches=keyword_matches,
            format_warnings=format_warnings,
            missing_critical=missing_critical,
            improvement_suggestions=improvement_suggestions,
        )

    def _keyword_match(self, cv_text: str, keywords: list[str]) -> tuple[list[KeywordMatch], float]:
        """Scan CV text for each keyword and return match list + score.

        Args:
            cv_text: Plain text of the CV.
            keywords: List of keywords to check.

        Returns:
            Tuple of (keyword_matches list, score 0.0–1.0).
        """
        matches: list[KeywordMatch] = []
        found_count = 0

        for kw in keywords:
            found = _kw_in_text(kw, cv_text)
            if found:
                found_count += 1
                # Find context snippet
                idx = cv_text.lower().find(kw.lower())
                context = cv_text[max(0, idx - 30):idx + len(kw) + 30].strip() if idx >= 0 else None
            else:
                context = None
            matches.append(KeywordMatch(keyword=kw, found=found, context=context))

        score = found_count / len(keywords) if keywords else 0.0
        return matches, score

    def suggest_improvements(self, score_result: ATSScoreResult) -> list[str]:
        """Return prioritised improvement suggestions.

        Must-have missing keywords are surfaced first.

        Args:
            score_result: ATSScoreResult from score().

        Returns:
            Ordered list of improvement suggestions.
        """
        suggestions: list[str] = []

        if score_result.missing_critical:
            suggestions.append(
                f"CRITICAL: Add these must-have keywords: {', '.join(score_result.missing_critical[:5])}"
            )

        # Add format warnings
        for w in score_result.format_warnings[:3]:
            suggestions.append(f"Format: {w}")

        # Add Claude's suggestions
        for s in score_result.improvement_suggestions[:5]:
            suggestions.append(s)

        return suggestions


def _kw_in_text(keyword: str, text: str) -> bool:
    """Case-insensitive substring check."""
    return keyword.lower() in text.lower()
