from __future__ import annotations

import pytest

from benchmarks.coach.profiles import profile_for, with_timeout_overrides


def test_standard_profile_is_locked() -> None:
    profile = profile_for("standard")
    assert profile.repetitions == 2
    assert (
        profile.call_timeout_seconds,
        profile.model_timeout_seconds,
        profile.run_timeout_seconds,
    ) == (900, 10800, 54000)
    assert profile.allow_ranking is True
    assert profile.scenario_ids is None


def test_acceptance_profile_has_exact_core_scenarios() -> None:
    profile = profile_for("acceptance-smoke")
    assert profile.scenario_ids == (
        "qg_01_requirement_coverage",
        "ma_01_supported_star",
        "ma_02_insufficient_evidence",
        "ae_01_strong_answer",
        "ae_02_weak_answer",
        "sr_01_mixed_session_report",
    )
    assert profile.repetitions == 1
    assert profile.allow_ranking is False


def test_profile_defaults_match_v5() -> None:
    acceptance = profile_for("acceptance-smoke")
    standard = profile_for("standard")
    extended = profile_for("extended")
    assert (
        acceptance.call_timeout_seconds,
        acceptance.model_timeout_seconds,
        acceptance.run_timeout_seconds,
    ) == (600, 3600, 18000)
    assert (
        standard.call_timeout_seconds,
        standard.model_timeout_seconds,
        standard.run_timeout_seconds,
    ) == (900, 10800, 54000)
    assert (
        extended.call_timeout_seconds,
        extended.model_timeout_seconds,
        extended.run_timeout_seconds,
    ) == (1200, 21600, 108000)


def test_contract_smoke_never_allows_ranking() -> None:
    profile = profile_for("contract-smoke")
    assert profile.repetitions == 1
    assert profile.allow_ranking is False


def test_timeout_overrides_must_be_positive_and_within_profile_bounds() -> None:
    profile = profile_for("acceptance-smoke")
    overridden = with_timeout_overrides(
        profile,
        call_timeout_seconds=30,
        model_timeout_seconds=300,
        run_timeout_seconds=900,
    )
    assert overridden.call_timeout_seconds == 30
    assert overridden.model_timeout_seconds == 300
    assert overridden.run_timeout_seconds == 900

    with pytest.raises(ValueError, match="call timeout"):
        with_timeout_overrides(profile, call_timeout_seconds=601)
    with pytest.raises(ValueError, match="positive"):
        with_timeout_overrides(profile, run_timeout_seconds=0)


def test_unknown_profile_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown Coach benchmark profile"):
        profile_for("quick")
