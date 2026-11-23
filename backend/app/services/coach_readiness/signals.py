"""Real-interview signals derived on read from saved debriefs (spec §7.1.5).

Nothing is stored: every signal is recomputed from the debrief rows, the
Question Bank items they reference and the application coverage lists.
Signals never feed `derive_patterns`; they are a separate read model.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, InterviewRound
from app.models.coach_readiness import CoachInterviewDebrief
from app.models.question_bank import QuestionBankItem

from .contracts import RealInterviewSignal
from .coverage import _competencies_for_application, match_key

_MIN_ROUNDS = 2


def question_keys(
    text: str,
    source_ref: dict[str, str] | None,
    qb_item: QuestionBankItem | None,
    coverage_keys: tuple[tuple[str, str], ...],
) -> frozenset[str]:
    """Deterministic tagging for one debrief question (spec §7.1.5).

    Keys are the union of the Question Bank item's skills and tags when the
    question was ticked from the likely-question list, plus every coverage
    competency whose match key is contained in the question's match key.
    """
    keys: set[str] = set()
    if source_ref and source_ref.get("kind") == "question_bank_item" and qb_item:
        keys.update(
            match_key(str(value))
            for value in [*(qb_item.skills or []), *(qb_item.tags or [])]
        )
    question_key = match_key(text)
    if question_key:
        keys.update(key for _original, key in coverage_keys if key and key in question_key)
    return frozenset(key for key in keys if key)


@dataclass(frozen=True)
class _DebriefView:
    """One saved debrief flattened for the pure derivation."""

    round_id: str
    application_id: str
    updated_at: datetime | None
    questions: tuple[dict, ...]


def derive_signals(
    debriefs: tuple[_DebriefView, ...],
    coverage_keys_by_application: dict[str, tuple[tuple[str, str], ...]],
    qb_items_by_id: dict[str, QuestionBankItem],
) -> tuple[RealInterviewSignal, ...]:
    """Aggregate per-key signals across saved debriefs; N ≥ 2 to appear."""
    asked_rounds: dict[str, set[str]] = {}
    low_ratings: dict[str, set[str]] = {}
    display: dict[str, str] = {}
    last_at: dict[str, datetime] = {}
    for debrief in debriefs:
        coverage_keys = coverage_keys_by_application.get(debrief.application_id, ())
        for question in debrief.questions:
            if not question.get("asked"):
                continue
            source_ref = (
                question.get("source_ref")
                if isinstance(question.get("source_ref"), dict)
                else None
            )
            keys = question_keys(
                str(question.get("text", "")),
                source_ref,
                qb_items_by_id.get(str(source_ref.get("id"))) if source_ref else None,
                coverage_keys,
            )
            for original, key in coverage_keys:
                if key in keys:
                    display.setdefault(key, original)
            for key in keys:
                asked_rounds.setdefault(key, set()).add(debrief.round_id)
                if isinstance(question.get("rating"), int) and question["rating"] <= 2:
                    low_ratings.setdefault(key, set()).add(debrief.round_id)
                if debrief.updated_at is not None:
                    current = last_at.get(key)
                    if current is None or debrief.updated_at > current:
                        last_at[key] = debrief.updated_at

    signals = []
    for key in sorted(asked_rounds):
        asked = len(asked_rounds.get(key, set()))
        low = len(low_ratings.get(key, set()))
        if max(asked, low) < _MIN_ROUNDS:
            continue
        signals.append(
            RealInterviewSignal(
                key=key,
                display=display.get(key, key),
                fingerprint=hashlib.sha256(f"signal:{key}".encode()).hexdigest(),
                asked_rounds=asked,
                low_rating_debriefs=low,
                last_at=last_at.get(key),
            )
        )
    return tuple(signals)


async def load_signals(
    db: AsyncSession, application_id: str | None = None
) -> tuple[RealInterviewSignal, ...]:
    """Derive the current signals; optionally scoped to one application."""
    filters = [
        CoachInterviewDebrief.status == "saved",
        Application.is_active.is_(True),
    ]
    if application_id is not None:
        filters.append(Application.id == application_id)
    rows = (
        await db.execute(
            select(CoachInterviewDebrief, Application)
            .join(
                InterviewRound,
                InterviewRound.id == CoachInterviewDebrief.interview_round_id,
            )
            .join(Application, Application.id == InterviewRound.application_id)
            .where(*filters)
        )
    ).all()
    if not rows:
        return ()

    debriefs: list[_DebriefView] = []
    qb_ids: set[str] = set()
    for debrief, application in rows:
        questions = tuple(
            value for value in (debrief.questions_json or []) if isinstance(value, dict)
        )
        debriefs.append(
            _DebriefView(
                round_id=debrief.interview_round_id,
                application_id=application.id,
                updated_at=debrief.updated_at,
                questions=questions,
            )
        )
        for question in questions:
            reference = question.get("source_ref")
            if (
                isinstance(reference, dict)
                and reference.get("kind") == "question_bank_item"
            ):
                qb_ids.add(str(reference.get("id")))

    qb_items: dict[str, QuestionBankItem] = {}
    if qb_ids:
        qb_items = {
            row.id: row
            for row in (
                await db.execute(
                    select(QuestionBankItem).where(QuestionBankItem.id.in_(qb_ids))
                )
            ).scalars()
        }

    coverage_keys: dict[str, tuple[tuple[str, str], ...]] = {}
    for debrief in debriefs:
        if debrief.application_id in coverage_keys:
            continue
        application = await db.get(Application, debrief.application_id)
        competencies = (
            await _competencies_for_application(db, application)
            if application is not None
            else ()
        )
        coverage_keys[debrief.application_id] = tuple(
            (item.text, item.match_key) for item in competencies
        )

    return derive_signals(tuple(debriefs), coverage_keys, qb_items)
