from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI

from app import main
from app.services.ai_setup import load_catalog
from app.services.coach_readiness import tiers


@pytest.mark.asyncio
async def test_startup_rejects_non_promoted_tier_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = next(
        model["id"] for model in load_catalog() if model["status"] == "candidate"
    )
    payload = json.loads(tiers.TIERS_PATH.read_text(encoding="utf-8"))
    payload["T"]["model_id"] = candidate
    bad_map = tmp_path / "model_tiers.json"
    bad_map.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(tiers, "TIERS_PATH", bad_map)

    with pytest.raises(RuntimeError, match="invalid model tier configuration"):
        async with main.lifespan(FastAPI()):
            pass
