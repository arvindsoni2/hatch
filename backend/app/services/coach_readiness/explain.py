"""Deterministic Explain orchestration: cache, dedupe, one repair, fencing."""
from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import database
from app.config import settings
from app.models.coach_readiness import CoachDerivedText, CoachPatternDismissal
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.services.ai_setup import load_runtime
from app.services.coach_readiness import grounding
from app.services.coach_readiness.contracts import (
    GenerationRequest,
    PatternPolicy,
    SourceRef,
    ValidatedOutput,
    finalise_generation,
    input_fingerprint,
)
from app.services.coach_readiness.patterns import derive_patterns, explain_pattern
from app.services.coach_readiness.tiers import load_tier_map

TASK_ID = "coach.readiness.explain"
PROMPT_VERSION = "explain-v1"
RUBRICS = {
    "relevance": "Answers the question asked and keeps the role requirements in view.",
    "structure": "Signals situation, task, action and result in a clear order.",
    "specificity": "Names the system, the people and the numbers that make the story checkable.",
    "impact": "States the measurable result and who benefited from it.",
    "role_depth": "Shows the judgement expected at the target role level.",
    "clarity": "Uses short sentences and plain words without filler.",
    "conciseness": "Stays inside the time box and drops repeated setup.",
}
ROUTE_URLS = {
    "llm-primary": "http://llm-primary:8080/v1",
    "llm-triage": "http://llm-triage:8081/v1",
    "llm-deep": "http://llm-deep:8082/v1",
}
_OPERATIONS: dict[str, dict[str, Any]] = {}
_INFLIGHT: dict[str, str] = {}
_OPERATION_LOCK = asyncio.Lock()
_TASKS: set[asyncio.Task] = set()
_THINKING = re.compile(r"<think(?:ing)?>.*?</think(?:ing)?>", re.DOTALL | re.IGNORECASE)


@dataclass
class ExplainContext:
    fingerprint: str
    dimension: str
    excerpts: tuple[dict[str, str], ...]
    sources: tuple[SourceRef, ...]
    cache_key: str
    model_id: str
    prompt: str
    deadline_s: int
    params: dict[str, str]


@dataclass
class _Draft:
    tips: list[str] = field(default_factory=list)


def _strip_reasoning(content: str) -> str:
    return _THINKING.sub("", content).strip()


def _parse_tips(content: str) -> list[str]:
    cleaned = _strip_reasoning(content)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("model output is not JSON")
    payload = json.loads(cleaned[start : end + 1])
    tips = payload.get("tips")
    if not isinstance(tips, list) or not all(isinstance(item, str) for item in tips):
        raise ValueError("model output has no tips")
    return tips


def _route_base_url(route: str) -> str:
    try:
        from app.agents.tools.profile_loader import load_profile

        llm = load_profile().llm
        if route == "llm-triage":
            return (llm.triage_base_url or llm.base_url or ROUTE_URLS[route]).rstrip("/")
        if route == "llm-primary":
            return (llm.base_url or ROUTE_URLS[route]).rstrip("/")
    except Exception:
        pass
    return ROUTE_URLS.get(route, ROUTE_URLS["llm-primary"])


async def _call_model(context: ExplainContext) -> list[str]:
    tier = load_tier_map()["S"]
    base_url = _route_base_url(tier.route)
    payload = {
        "model": context.model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON {\"tips\": [...]} with at most three short tips. "
                    "Use only the supplied excerpts and rubric. No new facts."
                ),
            },
            {"role": "user", "content": context.prompt},
        ],
        "temperature": 0,
        "max_tokens": tier.max_output_tokens,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(context.deadline_s)) as client:
        response = await client.post(f"{base_url}/chat/completions", json=payload)
        response.raise_for_status()
        body = response.json()
    content = body["choices"][0]["message"]["content"]
    return _parse_tips(content)


def _valid_tips(tips: list[str], context: ExplainContext) -> list[str] | None:
    case = {
        "dimension": context.dimension,
        "rubric_description": RUBRICS.get(context.dimension, ""),
        "excerpts": [
            {
                "excerpt_id": item["excerpt_id"],
                "text": item["text"],
                "session_date": item["session_date"],
                "difficulty": item["difficulty"],
            }
            for item in context.excerpts
        ],
    }
    output = {"tips": tips}
    if grounding.grounding_violations("explain", output, case):
        return None
    return tips


async def _run(operation_id: str, context: ExplainContext, deadline_at: float) -> None:
    _OPERATIONS[operation_id]["status"] = "running"
    try:
        valid: list[str] | None = None
        for _attempt in range(2):
            remaining = deadline_at - time.monotonic()
            if remaining <= 0:
                _OPERATIONS[operation_id]["status"] = "degraded"
                return
            tips = await asyncio.wait_for(
                _call_model(context), timeout=remaining
            )
            valid = _valid_tips(tips, context)
            if valid is not None:
                break
        if valid is None:
            _OPERATIONS[operation_id]["status"] = "degraded"
            return
        request = GenerationRequest(
            task_id=TASK_ID,
            kind="explain",
            cache_key=context.cache_key,
            input_fingerprint=input_fingerprint(TASK_ID, context.sources, context.params),
            sources=context.sources,
            params=context.params,
        )
        async with database.AsyncSessionLocal() as db:
            outcome = await finalise_generation(
                db,
                request,
                ValidatedOutput(
                    text_json={"tips": valid},
                    model_identity=context.model_id,
                    prompt_version=PROMPT_VERSION,
                ),
                datetime.now(UTC),
            )
            await db.commit()
        _OPERATIONS[operation_id]["status"] = outcome.status
        _OPERATIONS[operation_id]["derived_text_id"] = outcome.derived_text_id
    except Exception:
        _OPERATIONS[operation_id]["status"] = "degraded"
    finally:
        _INFLIGHT.pop(input_fingerprint(TASK_ID, context.sources, context.params), None)


async def _context(db: AsyncSession, fingerprint: str) -> ExplainContext | None:
    snapshots = await ConversationalSessionRepository(db).load_learning_snapshots()
    dismissed = frozenset(
        (await db.execute(select(CoachPatternDismissal.fingerprint))).scalars().all()
    )
    patterns = derive_patterns(
        snapshots,
        dismissed,
        PatternPolicy(window_days=settings.HATCH_COACH_PATTERN_WINDOW_DAYS),
        datetime.now(UTC),
    )
    pattern = next((item for item in patterns if item.fingerprint == fingerprint), None)
    if pattern is None:
        return None
    why = explain_pattern(pattern, snapshots)
    if why is None:
        return None
    by_id = {item.session_id: item for item in snapshots}
    sources = tuple(
        SourceRef("coach_session", item.session_id, str(by_id[item.session_id].activity_version))
        for item in pattern.supporting
        if item.session_id in by_id
    )
    if not sources:
        return None
    tier = load_tier_map()["S"]
    excerpts = tuple(
        {
            "excerpt_id": f"excerpt-{index}",
            "text": item.text,
            "session_date": item.completed_at.date().isoformat(),
            "difficulty": str(by_id[item.session_id].difficulty or "realistic"),
        }
        for index, item in enumerate(why.excerpts, start=1)
    )
    prompt = (
        f"Dimension: {pattern.dimension}\n"
        f"Rubric: {RUBRICS.get(pattern.dimension, '')}\n"
        "Excerpts:\n"
        + "\n".join(f"- {item['text']}" for item in excerpts)
    )
    model_id = tier.model_id or "qwen3.5-4b-q4km-primary"
    params = {"pattern": fingerprint, "prompt": PROMPT_VERSION, "model": model_id}
    return ExplainContext(
        fingerprint=fingerprint,
        dimension=pattern.dimension,
        excerpts=excerpts,
        sources=sources,
        cache_key=f"explain:{fingerprint}:{PROMPT_VERSION}:{model_id}",
        model_id=model_id,
        prompt=prompt,
        deadline_s=tier.deadline_s,
        params=params,
    )


async def request_tips(db: AsyncSession, fingerprint: str) -> tuple[int, dict[str, Any]]:
    if not settings.HATCH_COACH_READINESS_ENABLED:
        return 403, {"detail": "disabled"}
    runtime = load_runtime()
    if runtime.get("ai_mode") not in {"local", "custom"}:
        return 200, {"tips": [], "status": "unavailable", "reason": "ai_off"}

    context = await _context(db, fingerprint)
    if context is None:
        return 404, {"detail": "not_found"}

    cached = await db.scalar(
        select(CoachDerivedText).where(CoachDerivedText.cache_key == context.cache_key)
    )
    if cached is not None:
        return 200, {
            "tips": cached.text_json.get("tips", []),
            "status": "succeeded",
            "operation_id": None,
        }

    key = input_fingerprint(TASK_ID, context.sources, context.params)
    deadline_at = time.monotonic() + context.deadline_s
    async with _OPERATION_LOCK:
        if (existing := _INFLIGHT.get(key)) is not None:
            return 202, {"operation_id": existing, "status": _OPERATIONS[existing]["status"]}
        operation_id = str(uuid.uuid4())
        _OPERATIONS[operation_id] = {
            "operation_id": operation_id,
            "status": "queued",
            "derived_text_id": None,
        }
        if len(_OPERATIONS) > 200:
            _OPERATIONS.pop(next(iter(_OPERATIONS)))
        _INFLIGHT[key] = operation_id
    task = asyncio.create_task(_run(operation_id, context, deadline_at))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    return 202, {"operation_id": operation_id, "status": "queued"}


def operation(operation_id: str) -> dict[str, Any] | None:
    current = _OPERATIONS.get(operation_id)
    if current is None:
        return None
    return {
        "operation_id": operation_id,
        "status": current["status"],
    }
