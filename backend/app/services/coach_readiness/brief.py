"""Deterministic pre-interview brief skeleton and enhancement state (spec §7.5)."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import database
from app.config import settings
from app.models.application import Application, InterviewRound
from app.models.coach_readiness import (
    CoachDerivedText,
    CoachInterviewBrief,
    CoachPatternDismissal,
)
from app.models.coach_session import CompanyResearch
from app.models.job import JobPosting
from app.models.question_bank import QuestionBankItem
from app.models.story import Story
from app.repositories.conversational_session_repository import (
    ConversationalSessionRepository,
)
from app.services.ai_setup import load_runtime
from app.services.coach_readiness import coverage
from app.services.coach_readiness.contracts import (
    GenerationRequest,
    PatternPolicy,
    SourceRef,
    ValidatedOutput,
    finalise_generation,
    input_fingerprint,
)
from app.services.coach_readiness.grounding import grounding_violations
from app.services.coach_readiness.tiers import load_tier_map
from app.services.coach_readiness.patterns import derive_patterns
from app.services.coach_readiness.questions import likely_questions
from app.services.coach_readiness.signals import RealInterviewSignal, load_signals

PRACTICE_TYPES = {
    "behavioural": ("behavioural", "mixed"),
    "culture_fit": ("behavioural", "mixed"),
    "technical": ("role_specific_verbal", "mixed"),
    "assessment": ("role_specific_verbal", "mixed"),
    "presentation": ("role_specific_verbal", "mixed"),
    "phone_screen": ("behavioural", "role_specific_verbal", "mixed"),
    "panel": ("behavioural", "role_specific_verbal", "mixed"),
    "final": ("behavioural", "role_specific_verbal", "mixed"),
}
BRIEF_ROUND_TYPE = {
    "behavioural": "behavioural",
    "culture_fit": "behavioural",
    "technical": "role_specific_verbal",
    "assessment": "role_specific_verbal",
    "presentation": "role_specific_verbal",
    "phone_screen": "mixed",
    "panel": "mixed",
    "final": "mixed",
}
ASK_TEMPLATES = {
    "behavioural": ["What does success look like in the first 90 days?", "How does the team handle competing priorities?"],
    "technical": ["How does the team review technical decisions?", "What does the on-call and support model look like?"],
    "panel": ["How do the panel members work together day to day?", "What decision would you want this role to own?"],
}
ENHANCE_TASK = "coach.readiness.brief_enhance"
ENHANCE_PROMPT = "brief-enhance-v1"
# Dedupe: one enhancement per (round, fingerprint) while queued or running.
_INFLIGHT: set[str] = set()
_TASKS: set[asyncio.Task] = set()


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    return _utc(value).isoformat().replace("+00:00", "Z") if value else None


def _round_archived(round_row: InterviewRound, now: datetime) -> bool:
    if round_row.status == "cancelled" or round_row.status == "completed":
        return True
    if round_row.scheduled_at is None:
        return False
    duration = round_row.duration_minutes or 60
    return _utc(round_row.scheduled_at) + timedelta(minutes=duration) < _utc(now)


def _role_family(snapshots, application_id: str) -> str | None:
    linked = [item for item in snapshots if item.application_id == application_id]
    if not linked:
        return None
    latest = max(linked, key=lambda item: (item.completed_at, item.session_id))
    return latest.role_family


async def _story_rows(db, coverage_map):
    ids: list[str] = []
    for item in coverage_map.competencies:
        if item.status == "covered":
            ids.extend(story.story_id for story in item.stories)
    if not ids:
        return []
    rows = (await db.execute(select(Story).where(Story.id.in_(set(ids))))).scalars().all()
    by_id = {row.id: row for row in rows if row.is_active}
    scores: dict[str, float] = {}
    competences: dict[str, list[str]] = {}
    for item in coverage_map.competencies:
        for story in item.stories:
            if story.story_id in by_id:
                scores[story.story_id] = max(scores.get(story.story_id, 0), story.score)
                competences.setdefault(story.story_id, []).append(item.competency)
    ordered = sorted(
        by_id.values(),
        key=lambda row: (-scores.get(row.id, 0), -(row.strength_score or 0), row.id),
    )
    return [
        {
            "story_id": row.id,
            "title": row.title,
            "version": row.version,
            "competencies": sorted(set(competences.get(row.id, []))),
            "score": scores.get(row.id, 0),
            "has_metric": bool(row.metrics),
            "text": " ".join(filter(None, [row.situation, row.task, row.action, row.result])),
        }
        for row in ordered[:3]
    ]


async def build_brief(db, round_id: str, now: datetime) -> dict[str, Any] | None:
    built = await _build_brief(db, round_id, now)
    return built[0] if built else None


async def _build_brief(
    db, round_id: str, now: datetime
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    round_row = await db.get(InterviewRound, round_id)
    if round_row is None:
        return None
    application = await db.get(Application, round_row.application_id)
    job = await db.get(JobPosting, application.job_id) if application and application.job_id else None
    snapshots = await ConversationalSessionRepository(db).load_learning_snapshots()
    dismissed = frozenset(
        (await db.execute(select(CoachPatternDismissal.fingerprint))).scalars().all()
    )
    role_family = _role_family(snapshots, round_row.application_id)
    practice_types = PRACTICE_TYPES.get(round_row.type, ("behavioural", "mixed"))
    patterns = derive_patterns(
        snapshots, dismissed,
        PatternPolicy(window_days=settings.HATCH_COACH_PATTERN_WINDOW_DAYS), now,
    )
    watch_outs: list[Any] = [
        pattern for pattern in patterns
        if pattern.kind == "focus" and not pattern.stale
        and pattern.group.role_family == (role_family or "unspecified")
        and pattern.group.interview_type in practice_types
    ][:2]
    # Real-interview signals fill the remaining watch-out slots (spec §7.5 §4,
    # §7.1.5: signals aggregate across all saved debriefs, not one application).
    for signal in await load_signals(db):
        if len(watch_outs) == 2:
            break
        if signal.fingerprint not in {item.fingerprint for item in watch_outs}:
            watch_outs.append(signal)
    coverage_map = (
        await coverage.coverage_for_application(db, round_row.application_id)
        if application is not None else None
    )
    stories = (await _story_rows(db, coverage_map)) if coverage_map else []
    gaps = (
        [
            item.competency for item in coverage_map.competencies
            if item.status == "gap"
        ][:2] if coverage_map else []
    )
    questions = (
        (await likely_questions(db, round_row.application_id))[:5]
        if application is not None else []
    )
    ask_them: list[str] = []
    if job and job.company:
        research = (await db.execute(
            select(CompanyResearch).where(CompanyResearch.company_name == job.company)
        )).scalars().first()
        if research:
            for value in (research.recent_news or []) + (research.key_products or []):
                if isinstance(value, str):
                    ask_them.append(value)
                if len(ask_them) == 3:
                    break
    ask_them = ask_them[:3] or ASK_TEMPLATES.get(
        round_row.type, ["What does success look like in this role?"]
    )[:3]
    question_refs: list[SourceRef] = []
    for question in questions:
        reference = question.source_ref or {}
        if reference.get("kind") != "question_bank_item":
            continue
        item = await db.get(QuestionBankItem, reference["id"])
        if item is not None:
            question_refs.append(
                SourceRef("question_bank_item", item.id, item.updated_at.isoformat())
            )
    brief_row = (await db.execute(
        select(CoachInterviewBrief).where(
            CoachInterviewBrief.interview_round_id == round_row.id
        )
    )).scalar_one_or_none()
    enhanced = (
        await db.get(CoachDerivedText, brief_row.enhanced_text_id)
        if brief_row and brief_row.enhanced_text_id else None
    )
    job_description = (job.description or "") if job else ""
    fingerprint = hashlib.sha256(json.dumps({
        "stories": [[item["story_id"], item["version"]] for item in stories],
        "watch_outs": [item.fingerprint for item in watch_outs],
        "job": hashlib.sha256(job_description.encode("utf-8")).hexdigest(),
        "round_type": round_row.type,
    }, sort_keys=True).encode("utf-8")).hexdigest()
    if brief_row and enhanced and brief_row.enhancement_fingerprint == fingerprint:
        state = "current"
    elif brief_row and enhanced:
        state = "outdated"
    elif brief_row and brief_row.enhancement_state == "enhancing":
        state = "enhancing"
    elif brief_row and brief_row.enhancement_state == "unavailable":
        state = "unavailable"
    else:
        state = "none"
    tips = enhanced.text_json if state == "current" and isinstance(enhanced.text_json, dict) else {}
    talking_points = {
        item.get("story_id"): item.get("text")
        for item in tips.get("talking_points", ())
        if isinstance(item, dict)
    }
    watch_out_tips = {
        item.get("fingerprint"): item.get("text")
        for item in tips.get("watch_outs", ())
        if isinstance(item, dict)
    }
    archived = _round_archived(round_row, now)
    data: dict[str, Any] = {
        "round_id": round_row.id,
        "state": "archived" if archived else "active",
        "header": {
            "company": job.company if job else "",
            "role": job.title if job else "",
            "round_type": round_row.type,
            "starts_at": _iso(round_row.scheduled_at),
            "display_timezone": settings.HATCH_DISPLAY_TIMEZONE,
            "duration_minutes": round_row.duration_minutes,
            "interviewer": round_row.interviewer_name,
            "location": round_row.location,
        },
        "likely_questions": [
            {
                "id": item.id, "text": item.text,
                "source": "question_bank"
                if (item.source_ref or {}).get("kind") == "question_bank_item"
                else "session_plan",
            }
            for item in questions
        ],
        "stories": [
            {
                "story_id": item["story_id"], "title": item["title"],
                "competencies": item["competencies"], "score": item["score"],
                "has_metric": item["has_metric"],
                "talking_point": talking_points.get(item["story_id"]),
            }
            for item in stories
        ],
        "watch_outs": [
            {
                "fingerprint": item.fingerprint,
                "dimension": getattr(item, "dimension", None) or item.display,
                "source": "real_interview" if isinstance(item, RealInterviewSignal) else "practice",
                "sentence": watch_out_tips.get(item.fingerprint),
            }
            for item in watch_outs
        ],
        "gaps": [{"competency": item, "action": "draft_story"} for item in gaps],
        "ask_them": ask_them,
        "enhancement": {
            "state": state,
            "fingerprint": f"sha256:{fingerprint}",
            "operation_id": None,
            "model_identity": enhanced.model_identity if enhanced else None,
        },
    }
    context = {
        "header": data["header"],
        "stories": stories, "watch_outs": watch_outs,
        "job_description": job_description, "fingerprint": fingerprint,
        "question_refs": question_refs,
        "round_id": round_row.id,
        "round_version": round_row.updated_at.isoformat() if round_row.updated_at else "",
    }
    return data, context


def _sources(context: dict) -> tuple[SourceRef, ...]:
    refs = [
        SourceRef("story", item["story_id"], str(item["version"]))
        for item in context["stories"]
    ]
    refs.append(
        SourceRef("interview_round", context["round_id"], context["round_version"])
    )
    refs.extend(context.get("question_refs", ()))
    return tuple(refs)


async def _enhance_call(prompt: str) -> dict:
    from app.services.coach_readiness.explain import _route_base_url

    tier = load_tier_map()["S"]
    payload = {
        "model": tier.model_id,
        "messages": [
            {"role": "system", "content": "Return only JSON with talking_points and watch_outs."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": tier.max_output_tokens,
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(tier.deadline_s)) as client:
        response = await client.post(
            f"{_route_base_url(tier.route)}/chat/completions", json=payload
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("brief enhancement is not JSON")
    return json.loads(content[start : end + 1])


async def _run_enhancement(round_id: str, context: dict, key: str) -> None:
    request = GenerationRequest(
        task_id=ENHANCE_TASK,
        kind="brief",
        cache_key=f"brief:{round_id}:{ENHANCE_PROMPT}:{context['fingerprint']}",
        input_fingerprint=input_fingerprint(
            ENHANCE_TASK, _sources(context), {"round": round_id}
        ),
        sources=_sources(context),
        params={"round": round_id},
    )
    prompt = (
        "Stories:\n"
        + "\n".join(f"- {item['story_id']}: {item['text']}" for item in context["stories"])
        + "\nWatch-outs:\n"
        + "\n".join(
            getattr(item, "dimension", None) or item.display
            for item in context["watch_outs"]
        )
    )
    try:
        output = await _enhance_call(prompt)
        case = {
            "brief_id": round_id,
            "input_fingerprint": "sha256:" + context["fingerprint"],
            "header": {
                "company": context["header"]["company"],
                "role": context["header"]["role"],
                "round_type": BRIEF_ROUND_TYPE.get(
                    context["header"]["round_type"], "behavioural"
                ),
            },
            "stories": [
                {"story_id": item["story_id"], "title": item["title"],
                 "text": item["text"], "competencies": item["competencies"], "score": item["score"]}
                for item in context["stories"]
            ],
            "watch_outs": [
                {"fingerprint": item.fingerprint,
                 "dimension": getattr(item, "dimension", None) or item.display,
                 "evidence": getattr(item, "dimension", None) or item.display}
                for item in context["watch_outs"]
            ],
        }
        if grounding_violations("brief_enhance", output, case):
            raise ValueError("brief enhancement failed grounding")
        async with database.AsyncSessionLocal() as db:
            outcome = await finalise_generation(
                db, request,
                ValidatedOutput(
                    text_json=output, model_identity=load_tier_map()["S"].model_id or "",
                    prompt_version=ENHANCE_PROMPT,
                ),
                datetime.now(UTC),
            )
            row = (await db.execute(
                select(CoachInterviewBrief).where(
                    CoachInterviewBrief.interview_round_id == round_id
                )
            )).scalar_one_or_none()
            if row is not None:
                if outcome.status == "fenced":
                    row.enhancement_state = "unavailable"
                else:
                    # Only a successful finalise publishes the fingerprint.
                    row.enhancement_state = "current"
                    row.enhanced_text_id = outcome.derived_text_id
                    row.enhancement_fingerprint = context["fingerprint"]
            await db.commit()
    except Exception:
        async with database.AsyncSessionLocal() as db:
            row = (await db.execute(
                select(CoachInterviewBrief).where(
                    CoachInterviewBrief.interview_round_id == round_id
                )
            )).scalar_one_or_none()
            if row is not None:
                row.enhancement_state = "unavailable"
                await db.commit()
    finally:
        _INFLIGHT.discard(key)


def _inflight_for(round_id: str) -> bool:
    """True while any generation for this round is queued or running."""
    prefix = f"{round_id}:"
    return any(key.startswith(prefix) for key in _INFLIGHT)


async def request_enhancement(db, round_id: str, now: datetime) -> dict[str, Any] | None:
    if not settings.HATCH_COACH_BRIEF_ENABLED:
        return None
    runtime = load_runtime()
    if runtime.get("ai_mode") not in {"local", "custom"}:
        return None
    built = await _build_brief(db, round_id, now)
    if built is None:
        return None
    data, context = built
    if data["state"] == "archived":
        return data
    if data["enhancement"]["state"] == "current":
        return data
    if data["enhancement"]["state"] == "enhancing" and _inflight_for(round_id):
        return data
    key = f"{round_id}:{context['fingerprint']}"
    if key in _INFLIGHT:
        data["enhancement"]["state"] = "enhancing"
        return data
    # Claim the round before the first await so concurrent reads dedupe here.
    _INFLIGHT.add(key)
    try:
        row = (await db.execute(
            select(CoachInterviewBrief).where(
                CoachInterviewBrief.interview_round_id == round_id
            )
        )).scalar_one_or_none()
        if row is None:
            db.add(CoachInterviewBrief(interview_round_id=round_id, enhancement_state="enhancing"))
        else:
            # Old tips never read as current while the fresh ones are on their
            # way. A stale enhancing row (no in-flight task, e.g. after a
            # restart) re-queues here too.
            row.enhancement_state = "enhancing"
            row.enhanced_text_id = None
        await db.commit()
    except IntegrityError:
        # A concurrent request inserted the row first; our write is idempotent.
        await db.rollback()
        row = (await db.execute(
            select(CoachInterviewBrief).where(
                CoachInterviewBrief.interview_round_id == round_id
            )
        )).scalar_one_or_none()
        if row is None:
            _INFLIGHT.discard(key)
            raise
        row.enhancement_state = "enhancing"
        row.enhanced_text_id = None
        await db.commit()
    except Exception:
        _INFLIGHT.discard(key)
        raise
    task = asyncio.create_task(_run_enhancement(round_id, context, key))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    data["enhancement"]["state"] = "enhancing"
    return data
