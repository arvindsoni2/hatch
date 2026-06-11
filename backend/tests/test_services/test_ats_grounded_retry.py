"""G-6 tests — ATS retry loop only reinforces master-CV-grounded keywords."""
from __future__ import annotations

from app.services.tailor_service import _partition_ats_keywords


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
