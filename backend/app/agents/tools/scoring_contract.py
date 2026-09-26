"""Shared scoring schemas, deterministic normalization and prompt construction."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel
from ...models.job import JobPosting
from ...services.prompt_catalog import prompt_contract_block, source_contains

_FREE_TIER_PROVIDERS = {"google_genai", "ollama"}


class _TriageResult(BaseModel):
    relevant: bool
    reason: str = ""


class _ScoreResult(BaseModel):
    skill_match: float
    experience_match: float
    rate_match: float
    location_match: float
    overall_score: float
    reasoning: str
    keyword_matches: list[str] = []
    keyword_misses: list[str] = []
    fit_reasoning: str | None = None
    strengths: list[str] = []
    score_gaps: list[str] = []


def _normalise_score_result(
    result: _ScoreResult,
    weights: Any,
    *,
    candidate_text: str,
    job_text: str,
) -> _ScoreResult:
    """Clamp model components and derive the total deterministically."""
    values = {
        field: max(0.0, min(1.0, float(getattr(result, field))))
        for field in (
            "skill_match",
            "experience_match",
            "rate_match",
            "location_match",
        )
    }
    overall = sum(values[field] * float(getattr(weights, field)) for field in values)
    keyword_matches = [
        keyword
        for keyword in list(getattr(result, "keyword_matches", []))
        if source_contains(str(keyword), candidate_text)
        and source_contains(str(keyword), job_text)
    ]
    return _ScoreResult(
        **values,
        overall_score=round(overall, 4),
        reasoning=str(getattr(result, "reasoning", "")),
        keyword_matches=keyword_matches,
        keyword_misses=list(getattr(result, "keyword_misses", [])),
        fit_reasoning=getattr(result, "fit_reasoning", None),
        strengths=list(getattr(result, "strengths", [])),
        score_gaps=list(getattr(result, "score_gaps", [])),
    )


class ScoringPrompts:
    # ── Strategy resolver ─────────────────────────────────────────────

    @staticmethod
    def _resolve_method(profile: Any) -> str:
        """Resolve 'auto' to a concrete method based on provider tier."""
        method = getattr(profile.scoring, "method", "auto")
        if method == "auto":
            return "hybrid" if profile.llm.provider in _FREE_TIER_PROVIDERS else "llm"
        return method

    # ── Prompt builders — all data sourced from profile.yaml ─────────

    def _build_triage_prompt(self, job: JobPosting, profile: Any) -> str:
        roles = ", ".join(profile.search.target_roles)
        locations = ", ".join(
            f"{loc.city}, {loc.country}" for loc in profile.search.locations
        )
        return (
            f"{prompt_contract_block('job_scoring_triage')}\n\n"
            f"You are a job relevance filter for a {profile.candidate.title} "
            f"with {profile.candidate.years_experience} years experience.\n\n"
            f"Target roles: {roles}\n"
            f"Target locations: {locations}\n\n"
            f"Job title: {job.title}\n"
            f"Company: {job.company or 'unknown'}\n"
            f"Location: {job.location or 'unknown'}\n"
            f"Description (first 500 chars): {(job.description or '')[:500]}\n\n"
            "Is this job relevant? Reject: junior roles, unrelated domains, locations "
            "clearly outside target. Pass: anything plausibly matching the profile. "
            "Map the reason only to supplied profile or job fields; use unknown rather "
            "than assuming eligibility, sponsorship, clearance, or working pattern."
        )

    def _build_scoring_prompt(self, job: JobPosting, profile: Any) -> str:
        weights = profile.scoring.weights
        comp = profile.compensation
        primary_skills = ", ".join(profile.skills.primary)
        secondary_skills = ", ".join(profile.skills.secondary)
        preferred_domains = ", ".join(profile.domains.preferred)
        proof_summaries = "; ".join(p.summary for p in profile.proof_points)
        locations = "; ".join(
            f"{loc.city} ({loc.remote_preference})" for loc in profile.search.locations
        )

        locale_context = self._get_locale_scoring_context(profile)

        return (
            f"{prompt_contract_block('job_scoring_detailed')}\n\n"
            f"Score this job for a candidate with the following profile:\n\n"
            f"Title: {profile.candidate.title}, {profile.candidate.years_experience} years experience\n"
            f"Primary skills: {primary_skills}\n"
            f"Secondary skills: {secondary_skills}\n"
            f"Preferred domains: {preferred_domains}\n"
            f"Key achievements: {proof_summaries}\n"
            f"Target locations: {locations}\n"
            f"Rate range: {comp.currency} {comp.min_rate}–{comp.max_rate} ({comp.rate_type})\n\n"
            f"Job:\nTitle: {job.title}\nCompany: {job.company or 'N/A'}\n"
            f"Location: {job.location or 'N/A'}\nRate: {job.rate_text or 'N/A'}\n"
            f"Legal/contract fields: {getattr(job, 'legal_fields', None) or {'ir35_status': job.ir35_status} if job.ir35_status else {}}\n"
            f"Description:\n{(job.description or '')[:3000]}\n\n"
            f"Score on four dimensions (0.0–1.0):\n"
            f"- skill_match (weight {weights.skill_match}): how well skills match?\n"
            f"- experience_match (weight {weights.experience_match}): seniority/domain alignment?\n"
            f"- rate_match (weight {weights.rate_match}): rate within candidate range?\n"
            f"- location_match (weight {weights.location_match}): location/remote policy match?\n"
            f"{locale_context}\n"
            f"overall_score = weighted sum using the weights above.\n\n"
            f"Also return two keyword lists:\n"
            f"- keyword_matches: skills/tools mentioned in the job that the candidate clearly has (max 15)\n"
            f"- keyword_misses: skills/tools required by the job that the candidate lacks (max 10)\n"
            f"Every rationale claim must map to a supplied profile or job field. "
            f"Do not invent candidate metrics or justification. Component scores are "
            f"validated and the weighted total is recomputed by the application."
        )

    def _build_llm_judge_prompt(
        self, job: JobPosting, profile: Any, resume_text: str
    ) -> str:
        """Build the holistic LLM-judge prompt with full resume and JD.

        Uses resume_store.get_resume_text() for the candidate's full CV text,
        and the job's full description.  Instructs the LLM to assess semantic
        fit beyond keyword matching.
        """
        jd_text = (job.description or "")[:3000]
        weights = profile.scoring.weights
        comp = profile.compensation

        return (
            f"{prompt_contract_block('job_scoring_judge')}\n\n"
            f"You are an experienced recruiter assessing candidate-job fit.\n\n"
            f"Here is a candidate's full resume:\n{resume_text}\n\n"
            f"Here is a job description:\nTitle: {job.title}\n"
            f"Company: {job.company or 'N/A'}\nLocation: {job.location or 'N/A'}\n"
            f"Rate: {job.rate_text or 'N/A'}\n\n{jd_text}\n\n"
            f"Assess fit holistically. A candidate whose title or experience maps to "
            f"the role counts as a strong match even if exact keywords differ "
            f"(e.g. 'AI Project Manager' fits 'IT Project Manager'). "
            f"Consider transferable experience, seniority, domain.\n\n"
            f"Score on four dimensions (0.0–1.0):\n"
            f"- skill_match (weight {weights.skill_match}): skills and toolset alignment\n"
            f"- experience_match (weight {weights.experience_match}): seniority/domain fit\n"
            f"- rate_match (weight {weights.rate_match}): rate within "
            f"{comp.currency} {comp.min_rate}–{comp.max_rate} ({comp.rate_type})\n"
            f"- location_match (weight {weights.location_match}): location/remote policy\n"
            f"overall_score = weighted sum.\n\n"
            f"Also return:\n"
            f"- fit_reasoning: one holistic paragraph explaining the overall fit\n"
            f"- strengths: 2-3 specific, concrete strengths this candidate brings\n"
            f"- score_gaps: genuine gaps or risks (empty list if none)\n"
            f"- keyword_matches: skills/tools the candidate clearly has (max 15)\n"
            f"- keyword_misses: required skills the candidate lacks (max 10)\n"
            f"Every rationale claim must map to resume or job evidence. Do not add "
            f"candidate metrics or fabricate justification after selecting a score. "
            f"Component scores are validated and the weighted total is recomputed "
            f"by the application."
        )

    @staticmethod
    def _job_evidence_text(job: JobPosting) -> str:
        return " ".join(
            str(value or "")
            for value in (
                job.title,
                job.company,
                job.location,
                job.rate_text,
                job.description,
            )
        )

    @staticmethod
    def _profile_evidence_text(profile: Any) -> str:
        return " ".join(
            (
                str(profile.candidate.title),
                str(profile.candidate.years_experience),
                *map(str, profile.skills.primary),
                *map(str, profile.skills.secondary),
                *(str(proof.summary) for proof in profile.proof_points),
            )
        )

    def _get_locale_scoring_context(self, profile: Any) -> str:
        try:
            from ...services.locale_service import get_scoring_context

            legal_prefs: dict[str, str] = getattr(
                profile.compensation, "legal_preferences", {}
            )
            ctx = get_scoring_context(profile.locale, legal_prefs)
            if ctx:
                return f"Additional location_match guidance ({profile.locale} locale):\n{ctx}"
        except Exception:
            pass
        return ""
