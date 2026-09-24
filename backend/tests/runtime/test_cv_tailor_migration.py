"""Mode defaults; completed service/HTTP migration cases live in lifecycle tests."""

from app.config import Settings
from app.runtime import RuntimeMode


def test_default_mode_remains_legacy_for_rollback() -> None:
    assert Settings(_env_file=None).HATCH_RUNTIME_CV_TAILOR_MODE is RuntimeMode.LEGACY
