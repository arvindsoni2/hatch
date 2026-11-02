from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmarks.coach import phase2_checks
from benchmarks.coach.profiles import profile_for
from benchmarks.coach.runner import build_schedule
from benchmarks.coach.suite_loader import load_suite
from benchmarks.contracts import ModelSpec

PHASE2_ROOT = (
    Path(__file__).resolve().parents[3] / "benchmarks" / "coach" / "fixtures" / "phase2_v1"
)
_PERSONAL_EMAIL = re.compile(r"@[a-z0-9.-]+\.[a-z]{2,}", re.IGNORECASE)
_PHONE = re.compile(
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)"
)
_FORBIDDEN_MARKERS = ("arvind soni", "gmail", "outlook", "hotmail")


def _strings(value: object) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in _strings(child)]
    return [value] if isinstance(value, str) else []


def test_suite_manifest_loads_48_cases_with_split() -> None:
    suite = load_suite(PHASE2_ROOT)

    assert suite.suite_id == "coach_phase2_v1"
    assert suite.fixture_kind == "phase2"
    assert len(suite.scenarios) == 48
    assert Counter(item.stage for item in suite.scenarios.values()) == {
        "explain": 15,
        "brief_enhance": 15,
        "debrief_extract": 10,
        "competency_extract": 8,
    }
    assert Counter(suite.split.values()) == {"tuning": 16, "holdout": 32}
    assert set(suite.split) == set(suite.scenarios)


def test_every_case_validates_against_its_task_schema() -> None:
    suite = load_suite(PHASE2_ROOT)

    for scenario in suite.scenarios.values():
        assert scenario.stage in phase2_checks.PHASE2_STAGES
        assert scenario.stage in phase2_checks.TASK_TIERS
        phase2_checks.validate_case_input(scenario.stage, scenario.input)


def test_fixture_text_has_no_personal_or_local_data() -> None:
    for path in sorted(PHASE2_ROOT.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for value in _strings(payload):
            normalized = value.casefold()
            assert not _PERSONAL_EMAIL.search(value), f"{path.name}: email"
            assert not _PHONE.search(value), f"{path.name}: phone"
            assert not any(marker in normalized for marker in _FORBIDDEN_MARKERS)
            assert not value.startswith("/"), f"{path.name}: absolute path"
            assert "data/" not in value, f"{path.name}: data path"


def test_phase2_profile_schedules_every_case() -> None:
    suite = load_suite(PHASE2_ROOT)
    profile = profile_for("phase2")

    assert (
        profile.call_timeout_seconds
        <= profile.model_timeout_seconds
        <= profile.run_timeout_seconds
    )
    assert profile.call_timeout_seconds == phase2_checks.TIER_MAX_DEADLINE_SECONDS["L"]
    schedule = build_schedule(suite, profile, ["phase2-tier-s"])
    assert len(schedule) == 48
    assert {item.stage for item in schedule} == set(phase2_checks.PHASE2_STAGES)


def test_phase2_profile_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValidationError, match="loopback"):
        ModelSpec.model_validate(
            {
                "id": "remote",
                "runtime": "llamacpp",
                "model": "synthetic",
                "endpoint": "http://example.com:8080",
                "context_size": 32768,
            }
        )


def test_output_contracts_enforce_task_limits() -> None:
    phase2_checks.validate_output("explain", {"tips": ["Name the system first."]})

    with pytest.raises(ValidationError):
        phase2_checks.validate_output("explain", {"tips": ["word " * 61]})
    with pytest.raises(ValidationError):
        phase2_checks.validate_output(
            "competency_extract",
            {"competencies": ["one", "two", "three", "four", "five"]},
        )
