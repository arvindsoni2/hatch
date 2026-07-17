"""Tests for ATSOptimiser — algorithmic scoring, combined score, format warnings."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.tailor import ATSKeywords, ATSScoreResult, JDAnalysisResult, Requirements
from app.services.ats_optimiser import ATSOptimiser, _kw_in_text

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

JD_ANALYSIS = JDAnalysisResult(
    role_title="Solutions Architect",
    requirements=Requirements(
        must_have=["AWS", "Terraform"],
        nice_to_have=["GenAI"],
    ),
    ats_keywords=ATSKeywords(
        technical=["AWS", "Terraform", "Kubernetes", "Snowflake"],
        methodologies=["TOGAF", "ADR"],
        soft_skills=["Stakeholder management"],
        domain=["energy"],
        certifications=["AWS SAA"],
    ),
)

CV_TEXT_GOOD = """
Solutions Architect with 20+ years experience.
Expert in AWS (EC2, S3, Lambda, ECS, CloudFormation), Azure, and Terraform.
Kubernetes orchestration and Snowflake data platform design.
Applied TOGAF and Architecture Decision Records (ADR) for governance.
Strong stakeholder management skills at C-suite level.
AWS Solutions Architect Associate certified (in progress).
Energy sector experience spanning 5+ years.
"""

CV_TEXT_POOR = """
Software developer with experience in Python and JavaScript.
Built web applications using React and Node.js.
"""

MOCK_CLAUDE_SCORE = {
    "overall_score": 82,
    "format_warnings": [],
    "improvement_suggestions": ["Add specific AWS service names"],
}


def make_mock_client(response_dict: dict) -> MagicMock:
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=response_dict)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_score_returns_ats_result():
    client = make_mock_client(MOCK_CLAUDE_SCORE)
    optimiser = ATSOptimiser(client)
    result = await optimiser.score(CV_TEXT_GOOD, JD_ANALYSIS)

    assert isinstance(result, ATSScoreResult)
    assert 0 <= result.overall_score <= 100


@pytest.mark.asyncio
async def test_good_cv_scores_higher_than_poor():
    client_good = make_mock_client({"overall_score": 80, "format_warnings": [], "improvement_suggestions": []})
    client_poor = make_mock_client({"overall_score": 10, "format_warnings": ["Missing keywords"], "improvement_suggestions": ["Add AWS"]})

    good_score = await ATSOptimiser(client_good).score(CV_TEXT_GOOD, JD_ANALYSIS)
    poor_score = await ATSOptimiser(client_poor).score(CV_TEXT_POOR, JD_ANALYSIS)

    assert good_score.overall_score > poor_score.overall_score


@pytest.mark.asyncio
async def test_algorithmic_score_accuracy():
    """Good CV should have higher algorithmic score for matching keywords."""
    client = make_mock_client(MOCK_CLAUDE_SCORE)
    optimiser = ATSOptimiser(client)
    result = await optimiser.score(CV_TEXT_GOOD, JD_ANALYSIS)

    assert result.algorithmic_score is not None
    # CV_TEXT_GOOD contains AWS, Terraform, Kubernetes, Snowflake, TOGAF, ADR, energy
    # Should match most keywords
    assert result.algorithmic_score > 50.0


@pytest.mark.asyncio
async def test_missing_critical_detected():
    """Required keywords absent from CV should appear in missing_critical."""
    cv_without_aws = "Experienced architect. Expert in Azure. Strong Terraform skills."
    client = make_mock_client({"overall_score": 50, "format_warnings": [], "improvement_suggestions": []})
    optimiser = ATSOptimiser(client)
    result = await optimiser.score(cv_without_aws, JD_ANALYSIS)

    # AWS is in must_have but not in cv_without_aws
    assert "AWS" in result.missing_critical


@pytest.mark.asyncio
async def test_claude_failure_falls_back_to_algorithmic():
    """If Claude raises an exception, the optimiser uses algorithmic score only."""
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=Exception("API error"))
    optimiser = ATSOptimiser(client)

    result = await optimiser.score(CV_TEXT_GOOD, JD_ANALYSIS)

    assert isinstance(result, ATSScoreResult)
    assert 0 <= result.overall_score <= 100


@pytest.mark.asyncio
async def test_ats_prompt_uses_shared_contracts_and_filters_mutated_numbers():
    client = make_mock_client(
        {
            "overall_score": 80,
            "format_warnings": [],
            "improvement_suggestions": [
                "Keep the evidenced 20+ years wording.",
                "Claim 30+ years of experience.",
            ],
        }
    )
    result = await ATSOptimiser(client).score(CV_TEXT_GOOD, JD_ANALYSIS)

    assert result.improvement_suggestions == [
        "Keep the evidenced 20+ years wording."
    ]
    system_prompt, user_prompt = client.complete_json.await_args.args[:2]
    combined = system_prompt + user_prompt
    assert '"prompt_id": "ats_keywords"' in combined
    assert "APPROVED_EVIDENCE" in combined
    assert "IMMUTABLE_TOKEN" in combined


def test_keyword_match_case_insensitive():
    assert _kw_in_text("aws", "Strong AWS expertise in EC2 and S3") is True
    assert _kw_in_text("AWS", "strong aws expertise") is True
    assert _kw_in_text("Azure", "No cloud experience mentioned") is False


def test_suggest_improvements_critical_first():
    score_result = ATSScoreResult(
        overall_score=45,
        missing_critical=["AWS", "Terraform"],
        format_warnings=["No bullet points detected"],
        improvement_suggestions=["Add more keywords"],
        keyword_matches=[],
    )
    client = MagicMock()
    suggestions = ATSOptimiser(client).suggest_improvements(score_result)

    assert suggestions[0].startswith("CRITICAL")
    assert "AWS" in suggestions[0]
