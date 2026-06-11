"""G-2 tests — cv_parser grounding checks drop hallucinated content."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.cv_parser import CVParseResult, _normalise, _substring_present, parse_cv_text


class TestNormalise:
    def test_lowercases_and_strips(self):
        assert _normalise("  Jane Smith  ") == "jane smith"

    def test_collapses_whitespace(self):
        assert _normalise("a  b\t\nc") == "a b c"


class TestSubstringPresent:
    def test_finds_exact_match(self):
        assert _substring_present("Utility Corp", _normalise("Worked at Utility Corp from 2018"))

    def test_case_insensitive(self):
        assert _substring_present("UTILITY CORP", _normalise("worked at utility corp"))

    def test_returns_true_for_empty_value(self):
        assert _substring_present("", "anything")

    def test_returns_false_for_absent_value(self):
        assert not _substring_present("Company X", _normalise("worked at Utility Corp"))


class TestParseCVText:
    @pytest.mark.asyncio
    async def test_drops_company_not_in_source(self):
        """Grounding check clears company name not present in source text."""
        source_text = "Jane Smith. Worked at Utility Corp as Programme Manager 2018–2024."

        mock_client = AsyncMock()
        mock_client.complete_json = AsyncMock(return_value={
            "personal": {"full_name": "Jane Smith", "email": "", "phone": "", "location": "", "linkedin": "", "title": ""},
            "summary_variants": {"default": ""},
            "experience": [
                {
                    "role": "Programme Manager",
                    "company": "INVENTED COMPANY LTD",  # not in source
                    "period": "2018–2024",
                    "achievements": [],
                }
            ],
            "skills": [],
            "certifications": [],
            "education": [],
        })

        result = await parse_cv_text(source_text, mock_client)
        exp = result.parsed["experience"][0]
        assert exp["company"] == "", f"Expected cleared company, got: {exp['company']!r}"
        assert any("company" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_keeps_company_present_in_source(self):
        """Company name that IS in source text is not cleared."""
        source_text = "Jane Smith. Worked at Utility Corp as Programme Manager 2018–2024."

        mock_client = AsyncMock()
        mock_client.complete_json = AsyncMock(return_value={
            "personal": {"full_name": "Jane Smith", "email": "", "phone": "", "location": "", "linkedin": "", "title": ""},
            "summary_variants": {"default": ""},
            "experience": [
                {
                    "role": "Programme Manager",
                    "company": "Utility Corp",
                    "period": "2018–2024",
                    "achievements": [],
                }
            ],
            "skills": [],
            "certifications": [],
            "education": [],
        })

        result = await parse_cv_text(source_text, mock_client)
        exp = result.parsed["experience"][0]
        assert exp["company"] == "Utility Corp"

    @pytest.mark.asyncio
    async def test_drops_certification_not_in_source(self):
        """Certification not present in source text is dropped."""
        source_text = "Jane Smith. PMP certified. AWS Solutions Architect."

        mock_client = AsyncMock()
        mock_client.complete_json = AsyncMock(return_value={
            "personal": {"full_name": "", "email": "", "phone": "", "location": "", "linkedin": "", "title": ""},
            "summary_variants": {"default": ""},
            "experience": [],
            "skills": [],
            "certifications": ["PMP", "CISSP"],  # CISSP not in source
            "education": [],
        })

        result = await parse_cv_text(source_text, mock_client)
        assert "PMP" in result.parsed["certifications"]
        assert "CISSP" not in result.parsed["certifications"]
        assert any("CISSP" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty_structure(self):
        """LLM parse failure returns an empty CV structure with a warning."""
        mock_client = AsyncMock()
        mock_client.complete_json = AsyncMock(side_effect=Exception("model timeout"))

        result = await parse_cv_text("any text", mock_client)
        assert isinstance(result, CVParseResult)
        assert isinstance(result.parsed, dict)
        assert any("failed" in w.lower() for w in result.warnings)
