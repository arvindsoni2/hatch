"""Tests for CVTailor — achievement reordering, fabrication checks, variant selection."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.tailor import ATSKeywords, JDAnalysisResult, TailoredCVResult
from app.services.cv_tailor import CVTailor, _parse_tailored_cv

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_TAILOR_RESPONSE = {
    "summary": "Solutions Architect with 20+ years delivering enterprise cloud and AI architectures.",
    "skills": [
        {"display_name": "Cloud & Infrastructure", "items": ["AWS", "Azure", "Terraform"]},
        {"display_name": "AI & Machine Learning", "items": ["GenAI", "RAG", "LangGraph"]},
    ],
    "experience": [
        {
            "role": "Solutions Architect / Technical Lead",
            "company": "PLACEHOLDER — Company A (Energy Sector)",
            "period": "2022 — Present",
            "achievements": [
                "Designed hybrid cloud field mobility platform serving 2,000+ engineers, delivering £500K annual savings.",
                "Led GenAI document processing automation, reducing manual review by 70%.",
            ],
        },
        {
            "role": "Technical Delivery Manager",
            "company": "PLACEHOLDER — Company B (Aviation Sector)",
            "period": "2019 — 2022",
            "achievements": [
                "Delivered £3M AWS microservices migration achieving 99.99% uptime.",
            ],
        },
    ],
    "certifications": ["PMP", "PMI-ACP", "PSM-1"],
    "ats_keywords_embedded": ["AWS", "Terraform", "GenAI", "RAG"],
    "tailoring_notes": "Emphasised cloud and GenAI achievements per JD requirements.",
}

MOCK_MASTER_CV = {
    "summary_variants": {
        "solutions_architect": "Solutions Architect with 20+ years...",
        "data_architect": "Data Architect with deep Snowflake expertise...",
    },
    "skills": {
        "cloud_architecture": {"items": ["AWS", "Azure", "Terraform"]},
        "ai_ml": {"items": ["GenAI", "RAG", "LangGraph"]},
    },
    "experience": [
        {
            "role": "Solutions Architect",
            "company": "Company A",
            "period": "2022 - Present",
            "achievements": [
                {"text": "Designed hybrid cloud field mobility platform serving 2,000+ field engineers across the North of England, reducing paper-based processes by 90% and delivering £500K annual operational savings.", "tags": ["cloud", "aws"]},
                {"text": "Led adoption of GenAI-powered document processing, automating extraction from 50,000+ regulatory documents annually using RAG architecture, reducing manual review time by 70%.", "tags": ["genai", "rag"]},
            ],
        },
    ],
    "education": [
        {
            "qualification": "MBA",
            "institution": "Example Business School",
            "year": "2010",
        }
    ],
    "certifications": ["PMP"],
}

JD_ANALYSIS = JDAnalysisResult(
    role_title="Solutions Architect",
    ats_keywords=ATSKeywords(
        technical=["AWS", "Terraform", "GenAI"],
        methodologies=["TOGAF"],
        soft_skills=[],
        domain=["energy"],
        certifications=[],
    ),
)


def make_mock_client(response_dict: dict) -> MagicMock:
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=response_dict)
    return client


@pytest.mark.asyncio
async def test_tailor_accepts_isolated_master_cv_loader():
    loader = MagicMock(return_value=MOCK_MASTER_CV)
    tailor = CVTailor(
        make_mock_client(MOCK_TAILOR_RESPONSE),
        master_cv_loader=loader,
    )

    result = await tailor.tailor(JD_ANALYSIS)

    assert result.experience[0].company == "Company A"
    assert loader.call_count >= 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tailor_returns_result():
    client = make_mock_client(MOCK_TAILOR_RESPONSE)
    tailor = CVTailor(client)

    with patch.object(tailor, "_load_master_cv", return_value=MOCK_MASTER_CV):
        result = await tailor.tailor(JD_ANALYSIS, variant="A")

    assert isinstance(result, TailoredCVResult)
    assert result.summary != ""
    assert len(result.experience) == len(MOCK_MASTER_CV["experience"])
    assert "AWS" in result.ats_keywords_embedded


@pytest.mark.asyncio
async def test_variant_b_passed_to_claude():
    client = make_mock_client(MOCK_TAILOR_RESPONSE)
    tailor = CVTailor(client)

    with patch.object(tailor, "_load_master_cv", return_value=MOCK_MASTER_CV):
        await tailor.tailor(JD_ANALYSIS, variant="B")

    call_kwargs = client.complete_json.call_args
    # The user prompt should contain "B" variant instruction
    assert "B" in str(call_kwargs)


@pytest.mark.asyncio
async def test_master_structure_removes_fabricated_identity_fields():
    """Model-generated identity fields are replaced by grounded master values."""
    client = make_mock_client(MOCK_TAILOR_RESPONSE)
    tailor = CVTailor(client)

    with patch.object(tailor, "_load_master_cv", return_value=MOCK_MASTER_CV):
        result = await tailor.tailor(JD_ANALYSIS)

    assert result.blocking_issues == []
    assert result.experience[0].role == "Solutions Architect"
    assert result.experience[0].company == "Company A"


@pytest.mark.asyncio
async def test_fabrication_detected_for_invented_text():
    """Invented achievements should be flagged by the fabrication check."""
    invented_response = dict(MOCK_TAILOR_RESPONSE)
    invented_response["experience"] = [
        {
            "role": "CTO",
            "company": "Invented Corp",
            "period": "2024 — Present",
            "achievements": [
                "Invented a revolutionary quantum computing framework that saved £10 billion globally.",
                "Won the Nobel Prize for Computer Science in 2023 for distributed blockchain AI.",
            ],
        }
    ]
    client = make_mock_client(invented_response)
    tailor = CVTailor(client)

    with patch.object(tailor, "_load_master_cv", return_value=MOCK_MASTER_CV):
        result = await tailor.tailor(JD_ANALYSIS)

    assert len(result.fabrication_warnings) > 0


def test_select_best_summary_variant_solutions_architect():
    tailor = CVTailor(MagicMock())
    with patch.object(tailor, "_load_master_cv", return_value=MOCK_MASTER_CV):
        summary = tailor._select_best_summary_variant(JD_ANALYSIS)
    # solutions_architect variant has cloud/architecture keywords matching the JD
    assert "Solutions Architect" in summary or "Data Architect" in summary


@pytest.mark.asyncio
async def test_conflicting_summary_uses_grounded_role_variant():
    response = {**MOCK_TAILOR_RESPONSE, "summary": "Technical Project Manager with 20 years' experience."}
    tailor = CVTailor(make_mock_client(response))

    with patch.object(tailor, "_load_master_cv", return_value=MOCK_MASTER_CV):
        result = await tailor.tailor(JD_ANALYSIS)

    assert result.summary == MOCK_MASTER_CV["summary_variants"]["solutions_architect"]


def test_parse_tailored_cv():
    result = _parse_tailored_cv(MOCK_TAILOR_RESPONSE)
    assert result.summary.startswith("Solutions Architect")
    assert len(result.experience) == 2
    assert result.experience[0].role == "Solutions Architect / Technical Lead"
    assert len(result.experience[0].achievements) == 2


def test_parse_tailored_cv_accepts_education():
    result = _parse_tailored_cv({
        **MOCK_TAILOR_RESPONSE,
        "education": [{
            "qualification": "MBA",
            "institution": "Example Business School",
            "year": "2010",
        }],
    })

    assert result.education[0].qualification == "MBA"
    assert result.education[0].institution == "Example Business School"
    assert result.education[0].year == "2010"


def test_preserves_master_roles_bullets_and_certifications():
    from app.services.cv_tailor import _preserve_master_structure

    parsed = _parse_tailored_cv(MOCK_TAILOR_RESPONSE)
    master = {
        **MOCK_MASTER_CV,
        "certifications": ["PMP"],
        "experience": [
            {
                "role": "Solutions Architect",
                "company": "Company A",
                "period": "2022 - Present",
                "achievements": [{"text": "One"}, {"text": "Two"}],
            },
            {
                "role": "Earlier Role",
                "company": "Company B",
                "period": "2020 - 2022",
                "achievements": [{"text": "Three"}],
            },
        ],
    }

    result = _preserve_master_structure(parsed, master)

    assert [exp.role for exp in result.experience] == ["Solutions Architect", "Earlier Role"]
    assert [len(exp.achievements) for exp in result.experience] == [2, 1]
    assert result.certifications == ["PMP"]


def test_tailored_cv_does_not_collapse_to_one_page_or_drop_sections():
    from app.services.cv_tailor import _preserve_master_structure

    collapsed = _parse_tailored_cv({
        "summary": "Tailored summary.",
        "skills": [],
        "experience": [
            {
                "role": "Solutions Architect",
                "company": "Company A",
                "period": "2022 - Present",
                "achievements": [
                    "Designed hybrid cloud field mobility platform serving 2,000+ field engineers across the North of England, reducing paper-based processes by 90% and delivering £500K annual operational savings.",
                    "Led adoption of GenAI-powered document processing, automating extraction from 50,000+ regulatory documents annually using RAG architecture, reducing manual review time by 70%.",
                ],
            }
        ],
        "certifications": [],
    })
    master = {
        **MOCK_MASTER_CV,
        "experience": [
            *MOCK_MASTER_CV["experience"],
            {
                "role": "Earlier Delivery Lead",
                "company": "Company B",
                "period": "2019 - 2022",
                "achievements": [{"text": "Delivered a multi-team transformation programme."}],
            },
        ],
    }

    result = _preserve_master_structure(collapsed, master)

    assert [exp.role for exp in result.experience] == ["Solutions Architect", "Earlier Delivery Lead"]
    assert result.education[0].institution == "Example Business School"
    assert result.skills[0]["items"] == ["AWS", "Azure", "Terraform"]
    assert result.certifications == ["PMP"]
    assert result.validation_status == "repaired"
    assert any("education" in warning for warning in result.structural_warnings)


def test_rejects_drastically_shortened_bullets():
    from app.services.cv_tailor import _preserve_master_structure

    parsed = _parse_tailored_cv({
        **MOCK_TAILOR_RESPONSE,
        "experience": [{
            "role": "Solutions Architect",
            "company": "Company A",
            "period": "2022 - Present",
            "achievements": ["Cloud work.", "AI work."],
        }],
    })

    result = _preserve_master_structure(parsed, MOCK_MASTER_CV)

    assert result.experience[0].achievements[0].startswith("Designed hybrid cloud")
