"""Model tier map: promotion gate, budgets, and Tier L visibility (spec §9)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.ai_setup import load_catalog
from app.services.coach_readiness import tiers


def _write_tier_map(path: Path, mutate) -> Path:
    payload = json.loads(tiers.TIERS_PATH.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_catalog_entries_have_revision_sha_tiers_and_status() -> None:
    catalog = load_catalog()

    assert all(model["tiers"] for model in catalog)
    assert all(set(model["tiers"]) <= {"T", "S", "L"} for model in catalog)
    assert {model["status"] for model in catalog} <= {
        "candidate",
        "qualified",
        "promoted",
        "rejected",
        "retired",
    }
    assert any(model["status"] == "promoted" for model in catalog)
    assert all(len(model["source_revision"]) == 40 for model in catalog)
    assert all(len(model["sha256"]) == 64 for model in catalog)
    expected_d18 = {
        "gemma-4-e2b-q4km-triage": ["T"],
        "bonsai-1.7b-q1-triage": ["T"],
        "lfm2.5-1.2b-instruct-q4km-triage": ["T"],
        "gemma-4-e4b-q4km-primary": ["S"],
        "bonsai-4b-q1-primary": ["S"],
        "bonsai-8b-q1-primary": ["S"],
        "lfm2.5-8b-a1b-q4km-primary": ["S"],
        "gemma-4-26b-a4b-ud-q4km-deep": ["L"],
        "gemma-4-12b-q4km-deep": ["L"],
        "ternary-bonsai-2-27b-q2-deep": ["L"],
        "lfm2-24b-a2b-q4km-deep": ["L"],
        "qwen3.8-27b-ud-q4km-deep": ["L"],
    }
    by_id = {model["id"]: model for model in catalog}
    assert {model_id: by_id[model_id]["tiers"] for model_id in expected_d18} == expected_d18
    assert all(by_id[model_id]["status"] == "candidate" for model_id in expected_d18)
    assert all(
        by_id[model_id]["license"] in {"apache-2.0", "mit", "qwen-research", "lfm1.0"}
        for model_id in expected_d18
    )


def test_tier_map_defaults_to_promoted_incumbents() -> None:
    mapping = tiers.load_tier_map()
    catalog = {model["id"]: model for model in load_catalog()}

    assert set(mapping) == {"T", "S"}
    assert mapping["T"].route == "llm-triage"
    assert mapping["S"].route == "llm-primary"
    assert mapping["T"].max_output_tokens == 512
    assert (
        300 + mapping["T"].max_input_tokens + mapping["T"].max_output_tokens
        <= 2048
    )
    assert mapping["S"].max_output_tokens == 600
    assert mapping["T"].deadline_s <= tiers.MAX_DEADLINE_S["T"]
    assert mapping["S"].deadline_s <= tiers.MAX_DEADLINE_S["S"]
    assert mapping["T"].thinking is False
    assert mapping["S"].thinking is False
    assert catalog[mapping["T"].model_id]["status"] == "promoted"
    assert catalog[mapping["S"].model_id]["status"] == "promoted"


def test_tier_map_rejects_non_promoted_model(tmp_path: Path) -> None:
    candidate = next(model for model in load_catalog() if model["status"] == "candidate")
    path = _write_tier_map(
        tmp_path / "model_tiers.json",
        lambda payload: payload["S"].update({"model_id": candidate["id"]}),
    )

    with pytest.raises(ValueError, match="promoted"):
        tiers.load_tier_map(path=path)


def test_tier_map_rejects_unknown_model_and_over_max_deadline(tmp_path: Path) -> None:
    unknown = _write_tier_map(
        tmp_path / "unknown.json",
        lambda payload: payload["T"].update({"model_id": "not-in-catalogue"}),
    )
    with pytest.raises(ValueError, match="promoted"):
        tiers.load_tier_map(path=unknown)

    slow = _write_tier_map(
        tmp_path / "slow.json",
        lambda payload: payload["T"].update({"deadline_s": tiers.MAX_DEADLINE_S["T"] + 1}),
    )
    with pytest.raises(ValueError, match="deadline"):
        tiers.load_tier_map(path=slow)


def test_tier_t_budget_enforced() -> None:
    mapping = tiers.load_tier_map()

    assert mapping["T"].max_input_tokens == 1200
    assert tiers.estimate_tokens("x" * 4000) == 1000
    fitted = tiers.fit_input("x" * 6000, "T")
    assert tiers.estimate_tokens(fitted) <= 1200
    assert len(fitted) == 4800
    assert mapping["T"].max_output_tokens == 512
    assert (
        300 + mapping["T"].max_input_tokens + mapping["T"].max_output_tokens
        <= 2048
    )


def test_tier_l_hidden_below_24gb() -> None:
    assert tiers.tier_l_available(23.9) is False
    assert tiers.tier_l_available(24) is True
    assert tiers.MIN_TIER_L_RAM_GB == 24


def test_phase1_routes_unchanged() -> None:
    mapping = tiers.load_tier_map()
    catalog = {model["id"]: model for model in load_catalog()}

    assert mapping["T"].model_id == "qwen3.5-0.8b-q8-triage"
    assert mapping["S"].model_id == "qwen3.5-4b-q4km-primary"
    assert catalog[mapping["T"].model_id]["role"] == "triage"
    assert catalog[mapping["S"].model_id]["role"] == "combined_capable_primary"
    assert "L" not in mapping
