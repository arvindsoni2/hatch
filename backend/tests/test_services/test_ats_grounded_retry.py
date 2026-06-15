"""G-6 tests — ATS gaps remain grounded and do not trigger regeneration."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.tailor import ATSScoreResult, JDAnalysisResult, TailoredCVResult
from app.services.tailor_service import TailorService, _partition_ats_keywords


class TestPartitionATSKeywords:
    MASTER_TEXT = "agile delivery stakeholder management prince2 aws cloud architecture"

    def test_grounded_keyword_in_master_cv(self):
        """Keywords present in master CV go to grounded list."""
        grounded, gaps = _partition_ats_keywords(["agile", "aws"], self.MASTER_TEXT)
        assert "agile" in grounded
        assert "aws" in grounded
        assert gaps == []

    def test_absent_keyword_is_a_gap(self):
        """Keywords absent from master CV go to gaps list."""
        grounded, gaps = _partition_ats_keywords(["terraform", "kubernetes"], self.MASTER_TEXT)
        assert grounded == []
        assert "terraform" in gaps
        assert "kubernetes" in gaps

    def test_mix_of_grounded_and_gaps(self):
        """Mixed list is correctly partitioned."""
        grounded, gaps = _partition_ats_keywords(
            ["agile", "kubernetes", "prince2", "terraform"], self.MASTER_TEXT
        )
        assert "agile" in grounded
        assert "prince2" in grounded
        assert "kubernetes" in gaps
        assert "terraform" in gaps

    def test_gap_keyword_never_in_retry_instructions(self):
        """A JD keyword absent from master never appears in grounded list (anti-fabrication)."""
        _, gaps = _partition_ats_keywords(["devops", "splunk"], self.MASTER_TEXT)
        grounded, _ = _partition_ats_keywords(["devops", "splunk"], self.MASTER_TEXT)
        assert "devops" not in grounded
        assert "splunk" not in grounded

    def test_empty_missing_critical(self):
        """Empty input produces empty outputs."""
        grounded, gaps = _partition_ats_keywords([], self.MASTER_TEXT)
        assert grounded == []
        assert gaps == []


@pytest.mark.asyncio
async def test_low_ats_score_does_not_regenerate_cv():
    service = TailorService()
    tailored = TailoredCVResult(summary="Grounded summary")
    ats = ATSScoreResult(overall_score=60, missing_critical=["Unsupported Skill"])
    service._cv_tailor.tailor = AsyncMock(return_value=tailored)
    service._ats_optimiser.score = AsyncMock(return_value=ats)

    with patch("app.services.tailor_service._load_master_cv", return_value={}):
        result, score = await service._tailor_and_score(
            JDAnalysisResult(role_title="Solutions Architect"),
            "A",
        )

    assert result is tailored
    assert score is ats
    service._cv_tailor.tailor.assert_awaited_once()
    service._ats_optimiser.score.assert_awaited_once()
