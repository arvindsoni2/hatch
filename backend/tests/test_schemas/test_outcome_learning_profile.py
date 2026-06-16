import pytest
from pydantic import ValidationError

from app.schemas.profile import OutcomeLearningConfig


def test_signal_names_are_deduplicated_in_order() -> None:
    config = OutcomeLearningConfig(enabled_signals=["source", "freshness", "source"])
    assert config.enabled_signals == ["source", "freshness"]


def test_segment_size_cannot_exceed_total() -> None:
    with pytest.raises(ValidationError):
        OutcomeLearningConfig(minimum_total_applications=5, minimum_segment_size=6)


def test_signal_cap_cannot_exceed_total_cap() -> None:
    with pytest.raises(ValidationError):
        OutcomeLearningConfig(maximum_score_adjustment=0.03, maximum_signal_adjustment=0.04)
