"""Locked Coach benchmark profiles and bounded timeout overrides."""
from __future__ import annotations

from .contracts import CoachProfile

_ACCEPTANCE_SCENARIOS = (
    "qg_01_requirement_coverage",
    "ma_01_supported_star",
    "ma_02_insufficient_evidence",
    "ae_01_strong_answer",
    "ae_02_weak_answer",
    "sr_01_mixed_session_report",
)

_PROFILES = {
    "contract-smoke": CoachProfile(
        name="contract-smoke",
        repetitions=1,
        scenario_ids=None,
        call_timeout_seconds=90,
        model_timeout_seconds=90,
        run_timeout_seconds=90,
        allow_ranking=False,
    ),
    "acceptance-smoke": CoachProfile(
        name="acceptance-smoke",
        repetitions=1,
        scenario_ids=_ACCEPTANCE_SCENARIOS,
        call_timeout_seconds=600,
        model_timeout_seconds=3600,
        run_timeout_seconds=18000,
        allow_ranking=False,
    ),
    "standard": CoachProfile(
        name="standard",
        repetitions=2,
        scenario_ids=None,
        call_timeout_seconds=900,
        model_timeout_seconds=10800,
        run_timeout_seconds=54000,
        allow_ranking=True,
    ),
    "extended": CoachProfile(
        name="extended",
        repetitions=3,
        scenario_ids=None,
        call_timeout_seconds=1200,
        model_timeout_seconds=21600,
        run_timeout_seconds=108000,
        allow_ranking=True,
    ),
}


def profile_for(name: str) -> CoachProfile:
    """Return an isolated copy of a named, locked profile."""
    try:
        return _PROFILES[name].model_copy(deep=True)
    except KeyError as exc:
        raise ValueError(f"unknown Coach benchmark profile: {name}") from exc


def with_timeout_overrides(
    profile: CoachProfile,
    *,
    call_timeout_seconds: int | None = None,
    model_timeout_seconds: int | None = None,
    run_timeout_seconds: int | None = None,
) -> CoachProfile:
    """Return a profile copy with positive overrides inside its locked bounds."""
    requested = {
        "call_timeout_seconds": call_timeout_seconds,
        "model_timeout_seconds": model_timeout_seconds,
        "run_timeout_seconds": run_timeout_seconds,
    }
    labels = {
        "call_timeout_seconds": "call timeout",
        "model_timeout_seconds": "model timeout",
        "run_timeout_seconds": "run timeout",
    }
    changes: dict[str, int] = {}
    for field, value in requested.items():
        if value is None:
            continue
        if value <= 0:
            raise ValueError(f"{labels[field]} must be positive")
        maximum = int(getattr(profile, field))
        if value > maximum:
            raise ValueError(f"{labels[field]} cannot exceed {maximum} seconds")
        changes[field] = value
    result = profile.model_copy(update=changes, deep=True)
    if not (
        result.call_timeout_seconds
        <= result.model_timeout_seconds
        <= result.run_timeout_seconds
    ):
        raise ValueError("timeouts must be ordered call <= model <= run")
    return result
