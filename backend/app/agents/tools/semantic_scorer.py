"""Semantic job scorer using sentence-transformer embeddings.

Replaces the keyword-matching approach with dense vector similarity,
solving the core problem where semantically-equivalent role titles
(e.g. 'AI Project Manager' == 'IT Project Manager') scored 0%.

Pipeline:
1. If job has no usable description (needs_enrichment=True or empty): return deferred.
2. Embed the candidate's resume text and the job description.
3. Compute cosine similarity as the semantic_fit score.
4. Use local_scorer for rate_match and location_match (deterministic, free).
5. Blend dimensions using profile weights.
6. If embedder is unavailable: fall back to score_locally.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_MIN_JD_LENGTH = 50  # minimum chars to consider a JD usable for semantic scoring


@dataclass
class SemanticScoreResult:
    """Result from semantic scoring.

    When deferred=True, overall_score is None (job needs full JD before scoring).
    """
    skill_match: float | None
    experience_match: float | None
    rate_match: float | None
    location_match: float | None
    overall_score: float | None
    semantic_fit: float
    scoring_method: str = "semantic"
    reasoning: str = ""
    keyword_matches: list[str] = field(default_factory=list)
    keyword_misses: list[str] = field(default_factory=list)
    deferred: bool = False


# Allow tests to patch `embed` in this module's namespace
def embed(text: str) -> list[float]:
    """Delegate to embedder.embed — importable name for patching in tests."""
    from .embedder import embed as _embed
    return _embed(text)


def score_semantic(job: Any, profile: Any, resume_text: str) -> SemanticScoreResult:
    """Score a job posting against the candidate's resume using semantic similarity.

    Args:
        job: JobPosting or mock with .title, .description, .needs_enrichment,
             .location, .rate_text.
        profile: Loaded Profile (or mock) with scoring weights, skills,
                 compensation, and search preferences.
        resume_text: Plain-text content of the candidate's resume.

    Returns:
        SemanticScoreResult with scores and deferred flag.
    """
    from .local_scorer import score_locally, _rate_match, _location_match, _experience_match, _normalise, _skill_match

    description = getattr(job, "description", None) or ""
    needs_enrichment = getattr(job, "needs_enrichment", False)

    # ── Guard: no usable description ──────────────────────────────────────────
    if needs_enrichment or len(description.strip()) < _MIN_JD_LENGTH:
        return SemanticScoreResult(
            skill_match=None,
            experience_match=None,
            rate_match=None,
            location_match=None,
            overall_score=None,
            semantic_fit=0.0,
            scoring_method="semantic",
            reasoning="deferred: job description too short or needs enrichment",
            deferred=True,
        )

    # ── Compute semantic fit ───────────────────────────────────────────────────
    try:
        from .embedder import cosine

        resume_emb = embed(resume_text)
        jd_text = f"{job.title or ''} {description}"
        jd_emb = embed(jd_text)
        semantic_fit = max(0.0, min(1.0, cosine(resume_emb, jd_emb)))

    except RuntimeError as exc:
        logger.warning("Embedder unavailable, falling back to local scorer: %s", exc)
        local = score_locally(job, profile)
        return SemanticScoreResult(
            skill_match=local.skill_match,
            experience_match=local.experience_match,
            rate_match=local.rate_match,
            location_match=local.location_match,
            overall_score=local.overall_score,
            semantic_fit=local.skill_match,  # best proxy
            scoring_method="local",
            reasoning=local.reasoning,
            keyword_matches=local.keyword_matches,
            keyword_misses=local.keyword_misses,
            deferred=False,
        )

    # ── Deterministic dimensions from local scorer ────────────────────────────
    jd_lower = _normalise(description + " " + (job.location or ""))
    job_title = job.title or ""

    rate_score = _rate_match(jd_lower, profile)
    loc_score = _location_match(jd_lower, profile)
    exp_score = _experience_match(jd_lower, profile, job_title=job_title)
    _, kw_matches, kw_misses = _skill_match(jd_lower, profile)

    # ── Blend dimensions using profile weights ────────────────────────────────
    weights = profile.scoring.weights
    # semantic_fit replaces both skill_match and experience_match dimensions
    overall = (
        semantic_fit * weights.skill_match
        + semantic_fit * weights.experience_match
        + rate_score * weights.rate_match
        + loc_score * weights.location_match
    )
    overall = max(0.0, min(1.0, overall))

    return SemanticScoreResult(
        skill_match=round(semantic_fit, 3),
        experience_match=round(exp_score, 3),
        rate_match=round(rate_score, 3),
        location_match=round(loc_score, 3),
        overall_score=round(overall, 3),
        semantic_fit=round(semantic_fit, 4),
        scoring_method="semantic",
        reasoning=f"semantic cosine={semantic_fit:.3f}",
        keyword_matches=kw_matches[:15],
        keyword_misses=kw_misses[:10],
        deferred=False,
    )
