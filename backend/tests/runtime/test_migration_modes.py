"""Contract tests for slice-level runtime migration modes."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.runtime.migration import RuntimeMode, UnknownRuntimeSliceError, resolve_runtime_mode


_SETTING_BY_SLICE = {
    "job_score": "HATCH_RUNTIME_JOB_SCORE_MODE",
    "cv_tailor": "HATCH_RUNTIME_CV_TAILOR_MODE",
    "cover_letter": "HATCH_RUNTIME_COVER_LETTER_MODE",
    "coach": "HATCH_RUNTIME_COACH_MODE",
}


@pytest.mark.parametrize("setting", _SETTING_BY_SLICE.values())
def test_existing_installations_default_to_legacy(setting: str) -> None:
    assert getattr(Settings(_env_file=None), setting) is RuntimeMode.LEGACY


def test_runtime_mode_has_exact_persisted_values() -> None:
    assert {member.value for member in RuntimeMode} == {"legacy", "shadow", "new"}


@pytest.mark.parametrize(("slice_name", "setting"), _SETTING_BY_SLICE.items())
def test_slice_mode_resolves_once_from_its_explicit_setting(
    monkeypatch: pytest.MonkeyPatch, slice_name: str, setting: str
) -> None:
    configured = Settings(_env_file=None)
    monkeypatch.setattr(configured, setting, RuntimeMode.SHADOW)

    assert resolve_runtime_mode(slice_name, configured) is RuntimeMode.SHADOW


def test_environment_values_parse_to_runtime_mode_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_RUNTIME_JOB_SCORE_MODE", "new")
    monkeypatch.setenv("HATCH_RUNTIME_COACH_MODE", "SHADOW")

    configured = Settings(_env_file=None)

    assert configured.HATCH_RUNTIME_JOB_SCORE_MODE is RuntimeMode.NEW
    assert configured.HATCH_RUNTIME_COACH_MODE is RuntimeMode.SHADOW


def test_unknown_slice_fails_closed() -> None:
    with pytest.raises(UnknownRuntimeSliceError, match="unknown runtime slice"):
        resolve_runtime_mode("unknown", Settings(_env_file=None))
