"""Tests for JDAnalyser — JD parsing, skill match, caching."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.jd_analyser import JDAnalyser, _parse_jd_analysis

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_JD_ANALYSIS_RESPONSE = {
    "role_title": "Solutions Architect",
    "seniority_level": "Senior",
    "contract_details": {
        "rate_range": "£650–£750 per day",
        "ir35_status": "Outside IR35",
        "duration": "6 months",
        "location": "London / Hybrid",
        "remote_policy": "Hybrid",
    },
    "company_context": {
        "company_name": None,
        "sector": "energy",
        "size": "FTSE 100",
        "culture_indicators": ["collaborative", "outcomes-focused"],
    },
    "requirements": {
        "must_have": ["AWS", "Terraform", "Microservices", "TOGAF", "Stakeholder management"],
        "nice_to_have": ["GenAI", "Snowflake", "SAFe"],
        "years_experience": "15+",
    },
    "responsibilities": [
        "Lead architecture design for hybrid cloud workloads",
        "Define ADRs and C4 model diagrams",
        "Champion GenAI/Agentic AI adoption",
    ],
    "ats_keywords": {
        "technical": ["AWS", "Azure", "Terraform", "CloudFormation", "Microservices", "API", "Snowflake", "Databricks"],
        "methodologies": ["TOGAF", "ADR", "C4", "DDD", "API-first"],
        "soft_skills": ["Stakeholder management", "C-suite engagement", "mentoring"],
        "domain": ["energy", "cloud", "data platform", "GenAI"],
        "certifications": ["AWS SAA", "TOGAF"],
    },
    "tone_analysis": {
        "formality": "professional",
        "emphasis": "technical",
        "red_flags": [],
    },
}

MASTER_CV_STUB = {
    "skills": {
        "cloud_architecture": {"items": ["AWS (EC2, S3, Lambda, ECS, RDS, CloudFormation)", "Azure", "Terraform", "Kubernetes"]},
        "ai_ml": {"items": ["Generative AI / LLMs", "RAG Architecture", "LangGraph"]},
        "data_engineering": {"items": ["Snowflake", "Databricks", "Apache Kafka"]},
    },
    "experience": [
        {
            "sector": "energy",
            "achievements": [
                {"text": "Led cloud migration", "tags": ["cloud", "aws", "architecture"]},
                {"text": "Snowflake data platform", "tags": ["data", "snowflake"]},
            ],
        }
    ],
}


def make_mock_client(response_dict: dict) -> MagicMock:
    client = MagicMock()
    client.complete_json = AsyncMock(return_value=response_dict)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyse_returns_jd_analysis_result():
    client = make_mock_client(MOCK_JD_ANALYSIS_RESPONSE)
    analyser = JDAnalyser(client)

    jd_text = (FIXTURES_DIR / "sample_jd_solutions_architect.txt").read_text()
    result = await analyser.analyse(jd_text)

    assert result.role_title == "Solutions Architect"
    assert result.seniority_level == "Senior"
    assert result.contract_details.ir35_status == "Outside IR35"
    assert "AWS" in result.ats_keywords.technical
    assert result.raw_text_length == len(jd_text)


@pytest.mark.asyncio
async def test_analyse_cloud_architect_jd():
    client = make_mock_client({
        **MOCK_JD_ANALYSIS_RESPONSE,
        "role_title": "Senior Cloud Architect",
        "requirements": {"must_have": ["AWS", "Terraform", "Kubernetes"], "nice_to_have": ["SageMaker"]},
        "ats_keywords": {
            "technical": ["AWS", "Terraform", "EKS", "Kafka", "Kubernetes"],
            "methodologies": ["Well-Architected", "CI/CD", "DevSecOps"],
            "soft_skills": [],
            "domain": ["financial-services", "cloud"],
            "certifications": ["AWS SAP-C02"],
        },
    })
    analyser = JDAnalyser(client)
    jd_text = (FIXTURES_DIR / "sample_jd_cloud_architect.txt").read_text()
    result = await analyser.analyse(jd_text)

    assert result.role_title == "Senior Cloud Architect"
    assert "AWS" in result.ats_keywords.technical
    assert "Terraform" in result.ats_keywords.technical


@pytest.mark.asyncio
async def test_analyse_delivery_manager_jd():
    client = make_mock_client({
        **MOCK_JD_ANALYSIS_RESPONSE,
        "role_title": "Technical Delivery Manager",
        "ats_keywords": {
            "technical": ["SAFe", "Jira", "CI/CD", "AWS"],
            "methodologies": ["SAFe", "Scrum", "Kanban", "DORA"],
            "soft_skills": ["Stakeholder management", "budget management"],
            "domain": ["aviation", "delivery"],
            "certifications": ["SAFe Agilist", "PMP"],
        },
    })
    analyser = JDAnalyser(client)
    jd_text = (FIXTURES_DIR / "sample_jd_delivery_manager.txt").read_text()
    result = await analyser.analyse(jd_text)

    assert result.role_title == "Technical Delivery Manager"
    assert "SAFe" in result.ats_keywords.methodologies


def test_skill_match_high_overlap():
    analyser = JDAnalyser(MagicMock())
    from app.schemas.tailor import ATSKeywords, JDAnalysisResult

    analysis = JDAnalysisResult(
        role_title="Solutions Architect",
        ats_keywords=ATSKeywords(
            technical=["AWS", "Terraform", "Snowflake", "Kubernetes"],
            methodologies=["TOGAF", "ADR"],
            soft_skills=[],
            domain=["energy"],
            certifications=[],
        ),
    )
    result = analyser.compute_skill_match(analysis, MASTER_CV_STUB)

    # AWS, Terraform, Snowflake should match
    assert result.match_pct > 0
    assert len(result.matched) > 0


def test_skill_match_domain_match():
    analyser = JDAnalyser(MagicMock())
    from app.schemas.tailor import ATSKeywords, CompanyContext, JDAnalysisResult

    analysis = JDAnalysisResult(
        role_title="Architect",
        company_context=CompanyContext(sector="energy"),
        ats_keywords=ATSKeywords(technical=["AWS"], methodologies=[], soft_skills=[], domain=[], certifications=[]),
    )
    result = analyser.compute_skill_match(analysis, MASTER_CV_STUB)
    assert result.domain_match is True


def test_skill_match_no_domain_match():
    analyser = JDAnalyser(MagicMock())
    from app.schemas.tailor import ATSKeywords, CompanyContext, JDAnalysisResult

    analysis = JDAnalysisResult(
        role_title="Architect",
        company_context=CompanyContext(sector="pharmaceutical"),
        ats_keywords=ATSKeywords(technical=["AWS"], methodologies=[], soft_skills=[], domain=[], certifications=[]),
    )
    result = analyser.compute_skill_match(analysis, MASTER_CV_STUB)
    assert result.domain_match is False


def test_parse_jd_analysis_handles_missing_fields():
    raw = {"role_title": "Engineer"}
    result = _parse_jd_analysis(raw, 100)
    assert result.role_title == "Engineer"
    assert result.ats_keywords.technical == []
    assert result.requirements.must_have == []


# ---------------------------------------------------------------------------
# SSRF validation tests
# ---------------------------------------------------------------------------

class TestFetchJdUrlValidation:

    async def test_private_ip_is_blocked(self):
        """_fetch_jd() raises ValueError for URLs resolving to private IPs."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="SSRF blocked"):
            await analyser._fetch_jd("http://192.168.1.1/secret")

    async def test_loopback_is_blocked(self):
        """_fetch_jd() raises ValueError for loopback URLs."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="SSRF blocked|private"):
            await analyser._fetch_jd("http://127.0.0.1:8080/admin")

    async def test_non_http_scheme_is_blocked(self):
        """_fetch_jd() raises ValueError for non-http/https schemes."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="Only http/https"):
            await analyser._fetch_jd("file:///etc/passwd")

    async def test_ftp_scheme_is_blocked(self):
        """_fetch_jd() raises ValueError for ftp:// scheme."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="Only http/https"):
            await analyser._fetch_jd("ftp://example.com/jobs.txt")
