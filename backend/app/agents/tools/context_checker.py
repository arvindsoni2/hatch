"""Startup assertion: verify llama-server slot context fits the configured budgets.

Reads /props from each llamacpp endpoint, computes the largest (prompt + output) budget
routed to that server, and warns if the slot context is too small. Soft warning only —
never blocks startup; the risk is truncation, not corruption.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Lazily populated at startup — read by /api/health.
_degraded_details: list[dict[str, Any]] = []


def get_degraded_details() -> list[dict[str, Any]]:
    return _degraded_details


async def assert_context_budgets(llm_cfg: Any) -> None:
    """Check slot context against context budgets for llamacpp providers.

    Skips silently for non-llamacpp providers or unreachable servers.
    """
    global _degraded_details
    _degraded_details = []

    if getattr(llm_cfg, "provider", "") != "llamacpp":
        return

    from .context_budgets import (  # noqa: PLC0415
        CV_GENERATE, TRIAGE, SCORING, CL_BODY, CL_SNIPPET,
        JD_ANALYSIS, ATS, COMPANY_RESEARCH, CV_PARSE,
        ANSWER_EVAL, MODEL_ANSWER, QUESTION_GEN, FEEDBACK,
        COACH_RUBRIC, GENERIC,
    )

    # Largest budget routed to each server (prompt + output)
    primary_max = max(
        p + o for p, o in [
            CV_GENERATE, SCORING, CL_BODY, CL_SNIPPET, JD_ANALYSIS,
            ATS, COMPANY_RESEARCH, CV_PARSE, ANSWER_EVAL, MODEL_ANSWER,
            QUESTION_GEN, FEEDBACK, COACH_RUBRIC, GENERIC,
        ]
    )
    triage_max = sum(TRIAGE)  # prompt + output

    triage_url = (getattr(llm_cfg, "triage_base_url", "") or llm_cfg.base_url or "").rstrip("/v1").rstrip("/")
    primary_url = (llm_cfg.base_url or "").rstrip("/v1").rstrip("/")

    for label, base_url, required in [
        ("primary", primary_url, primary_max),
        ("triage", triage_url, triage_max),
    ]:
        if not base_url:
            continue
        props_url = f"{base_url}/props"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(props_url)
                resp.raise_for_status()
                props = resp.json()
        except Exception:
            logger.debug("llamacpp %s /props unreachable — skipping context check.", label)
            continue

        # /props returns {"n_ctx": total, "n_parallel": slots, ...}
        total_ctx = props.get("n_ctx", 0)
        parallel = props.get("n_parallel", 1) or 1
        slot_ctx = total_ctx // parallel

        if slot_ctx < required:
            msg = (
                f"llamacpp {label} server: slot context {slot_ctx} "
                f"(ctx={total_ctx}/parallel={parallel}) is smaller than the largest budget "
                f"routed to it ({required} tokens). Truncation risk on long calls."
            )
            logger.warning(msg)
            _degraded_details.append({
                "server": label,
                "slot_ctx": slot_ctx,
                "required": required,
                "reason": "context_budget_exceeds_slot",
            })
        else:
            logger.info(
                "llamacpp %s: slot context %d >= required %d — OK.",
                label, slot_ctx, required,
            )
