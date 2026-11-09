"""Bench-gated local model tier map (spec §9).

The map names one promoted model per tier. Startup validation refuses a model
whose catalogue status is not ``promoted`` so an unbenchmarked candidate can
never become a route default by editing this file alone.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TIERS_PATH = Path(__file__).parents[2] / "config" / "model_tiers.json"
MAX_DEADLINE_S = {"T": 60, "S": 180, "L": 300}
MAX_OUTPUT_TOKENS = {"T": 512, "S": 600, "L": 600}
MIN_TIER_L_RAM_GB = 24.0


@dataclass(frozen=True)
class TierConfig:
    tier: str
    route: str
    model_id: str | None
    thinking: bool
    max_input_tokens: int
    max_output_tokens: int
    deadline_s: int


def _catalog() -> list[dict[str, Any]]:
    from app.services.ai_setup import load_catalog

    return load_catalog()


def load_tier_map(
    *,
    path: Path | None = None,
    catalog: list[dict[str, Any]] | None = None,
) -> dict[str, TierConfig]:
    payload = json.loads((path or TIERS_PATH).read_text(encoding="utf-8"))
    entries = payload if isinstance(payload, dict) else None
    if not isinstance(entries, dict) or not entries:
        raise ValueError("model tier map must define at least one tier")
    by_id = {model["id"]: model for model in (catalog if catalog is not None else _catalog())}
    mapping: dict[str, TierConfig] = {}
    for tier, raw in entries.items():
        if tier not in MAX_DEADLINE_S or not isinstance(raw, dict):
            raise ValueError(f"unknown model tier: {tier}")
        model_id = raw.get("model_id")
        optional = bool(raw.get("optional"))
        if model_id is None:
            if not optional:
                raise ValueError(f"tier {tier} has no model id")
        else:
            model = by_id.get(str(model_id))
            if model is None or model.get("status") != "promoted":
                raise ValueError(f"tier {tier} model is not promoted: {model_id}")
        route = str(raw.get("route") or "")
        if not route:
            raise ValueError(f"tier {tier} has no route")
        deadline = raw.get("deadline_s")
        if not isinstance(deadline, int) or not 0 < deadline <= MAX_DEADLINE_S[tier]:
            raise ValueError(f"tier {tier} deadline exceeds its maximum")
        output = raw.get("max_output_tokens")
        if not isinstance(output, int) or not 0 < output <= MAX_OUTPUT_TOKENS[tier]:
            raise ValueError(f"tier {tier} output cap exceeds its maximum")
        input_tokens = raw.get("max_input_tokens")
        if not isinstance(input_tokens, int) or input_tokens <= 0:
            raise ValueError(f"tier {tier} has no input budget")
        mapping[tier] = TierConfig(
            tier=tier,
            route=route,
            model_id=str(model_id) if model_id is not None else None,
            thinking=bool(raw.get("thinking")),
            max_input_tokens=input_tokens,
            max_output_tokens=output,
            deadline_s=deadline,
        )
    return mapping


def validate_tier_map(**kwargs: Any) -> None:
    load_tier_map(**kwargs)


def tier_l_available(total_ram_gb: float) -> bool:
    return total_ram_gb >= MIN_TIER_L_RAM_GB


def estimate_tokens(text: str) -> int:
    """Production and bench estimate: characters ÷ 4, rounded up (spec AC34)."""
    return math.ceil(len(text) / 4)


def fit_input(text: str, tier: str, *, path: Path | None = None) -> str:
    config = load_tier_map(path=path)[tier]
    return text[: config.max_input_tokens * 4]
