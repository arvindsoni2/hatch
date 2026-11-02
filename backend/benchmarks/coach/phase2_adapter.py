"""Bench-only execution path for the Coach Phase 2 tasks.

This adapter talks to a loopback llama-server directly so P3 can bench the four
Phase 2 tasks before the P6 TaskSpecs exist. It is selected by the runner only
for the ``phase2`` profile and never touches the production adapter.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from app.services.coach_contracts import CoachDiagnostic

from .contracts import CoachScenario
from .phase2_checks import (
    TASK_OUTPUT_CAPS,
    TASK_TIERS,
    TIER_MAX_DEADLINE_SECONDS,
    grounding_violations,
    validate_output,
)
from .production_adapter import ScenarioContext, StageExecution

PHASE2_PROMPT_VERSION = "p0-v1"
_PEAK_RSS_ENV = "HATCH_BENCH_SERVER_PID"

_TASK_INSTRUCTIONS = {
    "explain": (
        "Return {\"tips\": [string]} with at most three tips. Each tip is at most "
        "40 words and all tips total at most 120 words. Use only the supplied "
        "rubric and excerpts; add no names or numbers."
    ),
    "brief_enhance": (
        "Return {\"talking_points\": [{\"story_id\": string, \"text\": string}], "
        "\"watch_outs\": [{\"fingerprint\": string, \"text\": string}]}. Use only "
        "supplied story ids and watch-out fingerprints. Each text is at most 30 "
        "words. Add no names or numbers that the source text does not contain."
    ),
    "debrief_extract": (
        "Return {\"questions\": [string]} with at most twelve questions. Each "
        "question is at most 120 characters. Use only the supplied notes; add no "
        "names or numbers."
    ),
    "competency_extract": (
        "Return {\"competencies\": [string]} with at most four short competency "
        "names, each at most 40 characters, taken from the requirement text."
    ),
}

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def build_prompt(stage: str, case_input: dict[str, Any]) -> tuple[str, str]:
    """Build the versioned bench prompt for one task and case."""
    try:
        instruction = _TASK_INSTRUCTIONS[stage]
    except KeyError as exc:
        raise ValueError(f"unknown Phase 2 bench stage: {stage}") from exc
    system = (
        "You are running inside the Hatch Coach Phase 2 benchmark. "
        "Return one JSON object only, with no prose.\n"
        f"BENCH_TASK={stage}\n"
        f"PROMPT_VERSION={PHASE2_PROMPT_VERSION}\n"
        f"{instruction}"
    )
    user = json.dumps(case_input, sort_keys=True, separators=(",", ":"))
    return system, user


def _parse_output(text: str) -> dict[str, Any]:
    value = _THINK.sub("", text).strip()
    if value.startswith("```"):
        lines = value.splitlines()
        value = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("bench output must be a JSON object")
    return parsed


def _peak_rss_bytes() -> int | None:
    raw_pid = os.environ.get(_PEAK_RSS_ENV)
    if not raw_pid:
        return None
    try:
        status = Path(f"/proc/{int(raw_pid)}/status").read_text(encoding="utf-8")
    except (OSError, ValueError):
        return None
    match = re.search(r"^VmHWM:\s+(\d+)\s+kB$", status, re.MULTILINE)
    return int(match.group(1)) * 1024 if match else None


@dataclass(frozen=True)
class Phase2StageExecution(StageExecution):
    """A Phase 2 stage result plus the metrics the bench records per attempt."""

    metrics: dict[str, Any] = field(default_factory=dict)


class Phase2BenchAdapter:
    """Execute one Phase 2 case against a loopback llama-server."""

    async def execute(
        self,
        scenario: CoachScenario,
        client: object,
        context: ScenarioContext,
    ) -> Phase2StageExecution:
        del context
        spec = getattr(client, "spec", None)
        if spec is None:
            raise ValueError("Phase 2 bench requires a BenchmarkLLMClient")
        tier = TASK_TIERS[scenario.stage]
        max_tokens = TASK_OUTPUT_CAPS[tier]
        deadline = TIER_MAX_DEADLINE_SECONDS[tier]
        system, user = build_prompt(scenario.stage, scenario.input)
        started = time.monotonic()
        async with asyncio.timeout(deadline):
            text, usage, first_token_at = await self._stream(
                spec=spec,
                system=system,
                user=user,
                max_tokens=max_tokens,
                seed=int(getattr(client, "seed", 11)),
                timeout_seconds=deadline + 10,
            )
        ended = time.monotonic()
        latency_ms = int((ended - started) * 1000)
        ttft_ms = (
            int((first_token_at - started) * 1000)
            if first_token_at is not None
            else latency_ms
        )
        completion_tokens = usage.get("completion_tokens") or len(text.split())
        generated_seconds = max(ended - (first_token_at or started), 1e-9)
        tokens_per_second = usage.get("tokens_per_second") or round(
            completion_tokens / generated_seconds, 3
        )
        metrics = {
            "latency_ms": latency_ms,
            "ttft_ms": ttft_ms,
            "tokens_per_second": float(tokens_per_second),
            "peak_rss_bytes": _peak_rss_bytes(),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": completion_tokens,
            "output_chars": len(text),
            "deadline_seconds": deadline,
        }

        gate_codes: list[str] = []
        output: dict[str, Any] = {}
        schema_valid = False
        violations: tuple[str, ...] = ()
        try:
            parsed = _parse_output(text)
            output = validate_output(scenario.stage, parsed).model_dump()
        except (json.JSONDecodeError, ValidationError, ValueError):
            violations = ("schema_invalid",)
        else:
            schema_valid = True
            violations = grounding_violations(scenario.stage, output, scenario.input)
        if not schema_valid or violations:
            gate_codes.append("coach_stage_failed")
        metrics["schema_valid"] = schema_valid
        metrics["grounding_violations"] = len(violations)

        diagnostic = CoachDiagnostic(
            stage="answer_evaluation",
            outcome="completed" if not gate_codes else "invalid_output",
            execution_mode="llm",
            prompt_id=f"coach.readiness.{scenario.stage}",
            prompt_version=PHASE2_PROMPT_VERSION,
            output_schema_version="1",
            model_id=str(spec.id),
            attempt_count=1,
            repair_count=0,
            gate_codes=gate_codes,
            duration_ms=latency_ms,
        )
        return Phase2StageExecution(
            output=output,
            diagnostic=diagnostic,
            provider_attempt_count=1,
            repair_count=0,
            metrics=metrics,
        )

    async def _stream(
        self,
        *,
        spec: Any,
        system: str,
        user: str,
        max_tokens: int,
        seed: int,
        timeout_seconds: float,
    ) -> tuple[str, dict[str, Any], float | None]:
        payload = {
            "model": spec.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": True,
            "temperature": spec.temperature,
            "seed": seed,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "chat_template_kwargs": {"enable_thinking": False},
            "reasoning_format": "none",
        }
        chunks: list[str] = []
        usage: dict[str, Any] = {}
        first_token_at: float | None = None
        async with httpx.AsyncClient(
            base_url=str(spec.endpoint).rstrip("/"),
            timeout=timeout_seconds,
        ) as http:
            async with http.stream(
                "POST", "/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        continue
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    if event.get("usage"):
                        usage.update(event["usage"])
                    timings = event.get("timings") or {}
                    if timings.get("predicted_per_second"):
                        usage["tokens_per_second"] = timings["predicted_per_second"]
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    content = choices[0].get("delta", {}).get("content")
                    if content:
                        if first_token_at is None:
                            first_token_at = time.monotonic()
                        chunks.append(str(content))
        return "".join(chunks), usage, first_token_at
