from __future__ import annotations

from pathlib import Path

import pytest

from app.routers.coach_readiness import get_model_tiers
from app.schemas.setup import IntentPatch
from app.services.setup_intent import patch_setup_intent


@pytest.mark.asyncio
async def test_model_tiers_list_promoted_routes_and_gate_tier_l(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("HATCH_PROBE_DIR", str(tmp_path / "probe"))
    (tmp_path / "probe").mkdir()
    (tmp_path / "probe" / "hardware_probe_latest.json").write_text(
        '{"sanitised":true,"memory":{"total_gb":16},"storage":{"models_dir_free_gb":24}}'
    )
    patch_setup_intent(IntentPatch(tier_l_enabled=True))

    payload = await get_model_tiers()

    assert [row["tier"] for row in payload["tiers"]] == ["T", "S"]
    assert payload["tiers"][0]["route"] == "llm-triage"
    assert payload["tiers"][1]["route"] == "llm-primary"
    assert payload["tier_l"]["available"] is False
    # The stored opt-in is ignored below the 24 GB gate (L3).
    assert payload["tier_l"]["enabled"] is False

    (tmp_path / "probe" / "hardware_probe_latest.json").write_text(
        '{"sanitised":true,"memory":{"total_gb":32},"storage":{"models_dir_free_gb":80}}'
    )
    payload = await get_model_tiers()

    assert payload["tier_l"]["available"] is True
    assert payload["tier_l"]["enabled"] is True
