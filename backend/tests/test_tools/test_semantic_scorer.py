"""Tests for the semantic scorer tool."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── Shared fixtures ────────────────────────────────────────────────────────────

IT_PM_JD = """
We are seeking an experienced Information Technology Project Manager to lead
complex digital transformation programmes within the public sector.

The successful candidate will have:
- 15+ years of project management experience
- Strong stakeholder management and governance skills
- Proven delivery of large-scale IT programmes (£5M+ budget)
- PMP or PRINCE2 certification preferred
- Experience with Agile and Waterfall methodologies
- Cloud migration programme experience advantageous

This is an outside IR35 contract, based in London hybrid.
Rate: £600-£750 per day.
""".strip()

DELIVERY_LEAD_JD = """
Senior Delivery Lead required for a 6-month contract engagement.
Leading delivery of digital services across multiple workstreams.
Strong Agile delivery background essential. Stakeholder management at C-suite level.
London hybrid, £650-£750 per day outside IR35.
""".strip()

GRADUATE_SCHEME_JD = """
Graduate Project Coordinator – Entry Level
This is an entry-level position for recent graduates.
No prior experience required. On-the-job training provided.
Salary: £25,000 per annum.
""".strip()

PASTRY_CHEF_JD = """
Head Pastry Chef – Luxury Hotel
We are seeking an experienced Head Pastry Chef to join our award-winning kitchen.
Skills required: patisserie, chocolate work, sugar craft, team management.
Fine dining background essential.
""".strip()


def _make_profile(
    title: str = "AI Project Manager / Technical Delivery Lead",
    years: int = 20,
    primary_skills: list[str] | None = None,
    secondary_skills: list[str] | None = None,
    certifications: list[str] | None = None,
    min_rate: float = 550.0,
    max_rate: float = 750.0,
    rate_type: str = "daily",
    currency: str = "GBP",
    remote_preference: str = "hybrid",
    city: str = "London",
    country: str = "UK",
) -> MagicMock:
    p = MagicMock()
    p.candidate.title = title
    p.candidate.years_experience = years
    p.skills.primary = primary_skills or [
        "agile delivery", "project management", "stakeholder management",
        "programme delivery", "digital transformation",
    ]
    p.skills.secondary = secondary_skills or ["python", "cloud", "devops"]
    p.skills.certifications = certifications or ["PMP", "PSM-1"]
    p.compensation.min_rate = min_rate
    p.compensation.max_rate = max_rate
    p.compensation.rate_type = rate_type
    p.compensation.currency = currency
    p.scoring.weights.skill_match = 0.35
    p.scoring.weights.experience_match = 0.30
    p.scoring.weights.rate_match = 0.20
    p.scoring.weights.location_match = 0.15
    loc = MagicMock()
    loc.city = city
    loc.country = country
    loc.remote_preference = remote_preference
    p.search.locations = [loc]
    p.domains.preferred = ["Public Sector", "Financial Services"]
    return p


def _make_job(
    title: str,
    description: str,
    location: str = "London, UK",
    needs_enrichment: bool = False,
    url: str = "https://example.com/job/1",
) -> MagicMock:
    j = MagicMock()
    j.title = title
    j.description = description
    j.location = location
    j.needs_enrichment = needs_enrichment
    j.url = url
    j.rate_text = None
    j.ir35_status = None
    return j


RESUME_TEXT = (
    "AI Project Manager / Technical Delivery Lead\n"
    "20 years delivering complex IT transformation programmes for enterprise clients.\n"
    "PMP certified. Expert in Agile, Waterfall, and hybrid delivery methodologies.\n"
    "Skills: project management, programme delivery, stakeholder management, "
    "agile delivery, digital transformation, cloud migration, governance.\n"
    "Target roles: IT Project Manager, Programme Manager, Technical Delivery Lead"
)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestSemanticScorer:

    def test_it_pm_role_scores_high_for_pm_profile(self):
        """AI PM profile vs IT PM job with realistic JD should score overall >= 0.55.

        This is the core regression test: keyword scoring gave 0% because the
        scraper only had the title, not the description.  With real JD + semantic
        embedding, the score must be recognised as a strong match.
        """
        from app.agents.tools.semantic_scorer import score_semantic

        profile = _make_profile()
        job = _make_job(
            title="Information Technology Project Manager",
            description=IT_PM_JD,
        )
        result = score_semantic(job, profile, RESUME_TEXT)

        assert result.deferred is False, "Full JD present — should not be deferred"
        assert result.overall_score is not None
        assert result.overall_score >= 0.55, (
            f"IT PM job vs AI PM profile should score >= 0.55, got {result.overall_score:.4f}. "
            f"semantic_fit={result.semantic_fit:.4f}"
        )

    def test_full_jd_required(self):
        """Job with needs_enrichment=True should return deferred result (score=None)."""
        from app.agents.tools.semantic_scorer import score_semantic

        profile = _make_profile()
        job = _make_job(
            title="IT Project Manager",
            description="",
            needs_enrichment=True,
        )
        result = score_semantic(job, profile, RESUME_TEXT)

        assert result.deferred is True, "needs_enrichment=True should return deferred=True"
        assert result.overall_score is None, (
            "Deferred result should have overall_score=None, not 0%"
        )

    def test_semantic_score_combines_with_dimensions(self):
        """Final score blends semantic_fit with rate/location from local_scorer."""
        from app.agents.tools.semantic_scorer import score_semantic

        profile = _make_profile()
        job = _make_job(
            title="Senior Delivery Lead",
            description=DELIVERY_LEAD_JD,
        )
        result = score_semantic(job, profile, RESUME_TEXT)

        assert result.deferred is False
        # semantic_fit should be a valid similarity score
        assert 0.0 <= result.semantic_fit <= 1.0
        # rate_match and location_match should come from local scorer
        assert result.rate_match is not None
        assert result.location_match is not None
        # overall_score should be a weighted blend
        assert result.overall_score is not None
        assert 0.0 <= result.overall_score <= 1.0

    def test_deferred_job_with_no_description_returns_none_score(self):
        """Job with no description and needs_enrichment=False but empty desc -> deferred."""
        from app.agents.tools.semantic_scorer import score_semantic

        profile = _make_profile()
        job = _make_job(
            title="Programme Director",
            description=None,
            needs_enrichment=False,
        )
        # Force None description
        job.description = None

        result = score_semantic(job, profile, RESUME_TEXT)
        # No description -> deferred
        assert result.deferred is True

    def test_scoring_method_is_semantic(self):
        """Scoring method for semantic scorer should be 'semantic'."""
        from app.agents.tools.semantic_scorer import score_semantic

        profile = _make_profile()
        job = _make_job(
            title="IT Project Manager",
            description=IT_PM_JD,
        )
        result = score_semantic(job, profile, RESUME_TEXT)
        assert result.scoring_method == "semantic"

    def test_fallback_to_local_on_embedder_failure(self):
        """If embedder raises RuntimeError, falls back to score_locally."""
        from app.agents.tools.semantic_scorer import score_semantic

        profile = _make_profile()
        job = _make_job(
            title="IT Project Manager",
            description=IT_PM_JD,
        )

        with patch("app.agents.tools.semantic_scorer.embed") as mock_embed:
            mock_embed.side_effect = RuntimeError("No sentence-transformers")
            result = score_semantic(job, profile, RESUME_TEXT)

        # Should not raise — should fall back to local scorer
        assert result.overall_score is not None
        assert result.scoring_method in ("local", "semantic")
