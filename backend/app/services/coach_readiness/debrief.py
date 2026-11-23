"""Commands, reads, extraction and proposals for real-interview debriefs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.coach_readiness import CoachInterviewDebrief
from app.models.question_bank import QuestionBankItem
from app.models.story import Story
from app.repositories.interview_repository import InterviewRepository
from app.schemas.interview import InterviewRoundUpdate
from app.schemas.question_bank import QuestionBankCreate
from app.services.ai_setup import load_runtime
from app.services.question_bank import create_question_bank_item
from app.services.story_service import StoryService

from .contracts import (
    DebriefProposal,
    DebriefQuestion,
    DebriefRead,
    ReadinessError,
    SaveDebriefCommand,
)
from .grounding import grounding_violations
from .questions import likely_questions
from .tiers import load_tier_map

EXTRACT_TASK = "coach.readiness.debrief_extract"
EXTRACT_PROMPT = "debrief-extract-v1"
_MAX_EXTRACT_QUESTIONS = 12

_DEFAULT_DURATION_MINUTES = 60
_MAX_QUESTIONS = 20
_MAX_QUESTION_CHARS = 200
_MAX_NOTE_CHARS = 200
_MAX_FREE_TEXT = 1_000
_MAX_NOTES_TEXT = 2_500
_EXPECTATIONS = {"yes", "unsure", "no"}


def _naive_utc(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment
    return moment.astimezone(UTC).replace(tzinfo=None)


def _due(round_row: object, now: datetime) -> bool:
    status = getattr(round_row, "status", "")
    if status == "completed":
        return True
    if status not in {"scheduled", "rescheduled"}:
        return False
    scheduled_at = getattr(round_row, "scheduled_at", None)
    if scheduled_at is None:
        return False
    duration = getattr(round_row, "duration_minutes", None)
    minutes = duration if duration is not None else _DEFAULT_DURATION_MINUTES
    return scheduled_at + timedelta(minutes=minutes) <= _naive_utc(now)


def _serialize_question(question: DebriefQuestion) -> dict:
    return {
        "id": question.id,
        "text": question.text.strip(),
        "source_ref": question.source_ref,
        "asked": bool(question.asked),
        "rating": question.rating,
        "story_id": question.story_id,
        "note": question.note,
    }


def _deserialize_question(value: object) -> DebriefQuestion | None:
    if not isinstance(value, dict):
        return None
    return DebriefQuestion(
        id=str(value.get("id", "")),
        text=str(value.get("text", "")),
        source_ref=(
            value.get("source_ref")
            if isinstance(value.get("source_ref"), dict)
            else None
        ),
        asked=bool(value.get("asked", False)),
        rating=value.get("rating") if isinstance(value.get("rating"), int) else None,
        story_id=value.get("story_id") if isinstance(value.get("story_id"), str) else None,
        note=value.get("note") if isinstance(value.get("note"), str) else None,
    )


def _normalised(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _deserialize_proposal(value: object) -> DebriefProposal | None:
    if not isinstance(value, dict) or value.get("kind") not in {"question_bank", "story_use"}:
        return None
    return DebriefProposal(
        id=str(value.get("id", "")),
        kind=value["kind"],
        questions=tuple(
            item for item in value.get("questions", []) if isinstance(item, str)
        ),
        story_id=value.get("story_id") if isinstance(value.get("story_id"), str) else None,
        story_title=value.get("story_title") if isinstance(value.get("story_title"), str) else None,
        accepted=bool(value.get("accepted", False)),
    )


class DebriefService:
    """Read, save and skip a debrief for one real interview round."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = InterviewRepository(session)

    async def _round(self, round_id: str):
        return await self._repo.get(round_id)

    async def _active_application(self, application_id: str) -> bool:
        application = await self._session.get(Application, application_id)
        return application is not None and bool(application.is_active)

    async def _row(self, round_id: str) -> CoachInterviewDebrief | None:
        return (
            await self._session.execute(
                select(CoachInterviewDebrief).where(
                    CoachInterviewDebrief.interview_round_id == round_id
                )
            )
        ).scalar_one_or_none()

    def _read(self, round_row, row: CoachInterviewDebrief) -> DebriefRead:
        questions = tuple(
            question
            for value in (row.questions_json or [])
            if (question := _deserialize_question(value)) is not None
        )
        return replace(
            DebriefRead(
                status=row.status,
                version=row.version,
                overall=row.overall,
                expectation=row.expectation,
                questions=questions,
                went_well=row.went_well,
                do_differently=row.do_differently,
                notes_text=row.notes_text,
                round_id=round_row.id,
                application_id=round_row.application_id,
                round_status=round_row.status,
                scheduled_at=round_row.scheduled_at,
                duration_minutes=round_row.duration_minutes,
            ),
            proposals=tuple(
                proposal
                for value in (row.proposals_json or [])
                if (proposal := _deserialize_proposal(value)) is not None
            ),
        )

    async def get_or_due(self, round_id: str, now: datetime) -> DebriefRead | None:
        round_row = await self._round(round_id)
        if round_row is None:
            return None
        if not await self._active_application(round_row.application_id):
            return None
        row = await self._row(round_id)
        if row is not None:
            return self._read(round_row, row)
        if not _due(round_row, now):
            return None
        return DebriefRead(
            status="due",
            version=0,
            questions=tuple(
                await likely_questions(self._session, round_row.application_id)
            ),
            round_id=round_row.id,
            application_id=round_row.application_id,
            round_status=round_row.status,
            scheduled_at=round_row.scheduled_at,
            duration_minutes=round_row.duration_minutes,
        )

    def _validate(self, command: SaveDebriefCommand) -> None:
        if command.overall is not None and not 1 <= int(command.overall) <= 5:
            raise ReadinessError("invalid_input")
        if command.overall is None and not (command.notes_text or "").strip():
            # A notes-only draft is the only save without the overall rating.
            raise ReadinessError("invalid_input")
        if command.expectation is not None and command.expectation not in _EXPECTATIONS:
            raise ReadinessError("invalid_input")
        if len(command.questions) > _MAX_QUESTIONS:
            raise ReadinessError("invalid_input")
        for question in command.questions:
            if not question.text.strip() or len(question.text) > _MAX_QUESTION_CHARS:
                raise ReadinessError("invalid_input")
            if question.rating is not None and not 1 <= question.rating <= 5:
                raise ReadinessError("invalid_input")
            if question.note is not None and len(question.note) > _MAX_NOTE_CHARS:
                raise ReadinessError("invalid_input")
        for value in (command.went_well, command.do_differently):
            if value is not None and len(value) > _MAX_FREE_TEXT:
                raise ReadinessError("invalid_input")
        if command.notes_text is not None and len(command.notes_text) > _MAX_NOTES_TEXT:
            raise ReadinessError("invalid_input")

    async def save(
        self,
        round_id: str,
        command: SaveDebriefCommand,
        now: datetime,
    ) -> DebriefRead:
        round_row = await self._round(round_id)
        if round_row is None or not await self._active_application(
            round_row.application_id
        ):
            raise ReadinessError("not_found")
        row = await self._row(round_id)
        if row is None:
            if not _due(round_row, now):
                raise ReadinessError("invalid_state")
            if command.expected_version != 0:
                raise ReadinessError("version_conflict")
        elif row.status not in {"draft", "saved", "skipped"}:
            raise ReadinessError("invalid_state")
        self._validate(command)

        moment = _naive_utc(now)
        values = {
            "status": "draft" if command.overall is None else "saved",
            "overall": command.overall,
            "expectation": command.expectation,
            "questions_json": [
                _serialize_question(question) for question in command.questions
            ],
            "went_well": command.went_well,
            "do_differently": command.do_differently,
            "notes_text": command.notes_text,
            "proposals_json": [
                asdict(proposal) for proposal in await self._proposals(
                    round_row.application_id, command.questions
                )
            ],
            "updated_at": moment,
        }
        if row is None:
            row = CoachInterviewDebrief(
                interview_round_id=round_id,
                version=1,
                created_at=moment,
                **values,
            )
            try:
                self._session.add(row)
                await self._session.flush()
            except IntegrityError as exc:
                raise ReadinessError("version_conflict") from exc
        else:
            result = await self._session.execute(
                update(CoachInterviewDebrief)
                .where(
                    CoachInterviewDebrief.id == row.id,
                    CoachInterviewDebrief.version == command.expected_version,
                )
                .values(version=command.expected_version + 1, **values)
            )
            if (result.rowcount or 0) == 0:
                raise ReadinessError("version_conflict")
            await self._session.flush()
            row = await self._row(round_id)
            if row is None:
                raise ReadinessError("version_conflict")

        asked = [
            question.text.strip()
            for question in command.questions
            if question.asked
        ]
        existing = list(round_row.questions_asked or [])
        seen = {" ".join(str(value).casefold().split()) for value in existing}
        new_asked = []
        for text in asked:
            key = " ".join(text.casefold().split())
            if key in seen:
                continue
            seen.add(key)
            new_asked.append(text)
        completes = round_row.status in {"scheduled", "rescheduled"}
        if new_asked or completes:
            patch = InterviewRoundUpdate()
            if new_asked:
                patch.questions_asked = [*existing, *new_asked]
            if completes:
                patch.status = "completed"
            await self._repo.update(round_id, patch)
        return replace(self._read(round_row, row), questions_added=len(new_asked))

    async def skip(
        self,
        round_id: str,
        expected_version: int,
        now: datetime,
    ) -> DebriefRead:
        round_row = await self._round(round_id)
        if round_row is None or not await self._active_application(
            round_row.application_id
        ):
            raise ReadinessError("not_found")
        row = await self._row(round_id)
        if row is not None or not _due(round_row, now):
            raise ReadinessError("invalid_state")
        if expected_version != 0:
            raise ReadinessError("version_conflict")

        moment = _naive_utc(now)
        row = CoachInterviewDebrief(
            interview_round_id=round_id,
            version=1,
            status="skipped",
            questions_json=[],
            proposals_json=[],
            created_at=moment,
            updated_at=moment,
        )
        try:
            self._session.add(row)
            await self._session.flush()
        except IntegrityError as exc:
            raise ReadinessError("version_conflict") from exc
        return self._read(round_row, row)

    async def _proposals(
        self, application_id: str, questions: tuple[DebriefQuestion, ...]
    ) -> tuple[DebriefProposal, ...]:
        """S2 batch proposals from one save (spec §7.6); stored, never auto-run."""
        asked = [question for question in questions if question.asked]
        proposals: list[DebriefProposal] = []

        unsourced: list[str] = []
        existing = {
            _normalised(str(item.question))
            for item in (
                await self._session.execute(select(QuestionBankItem))
            ).scalars()
            if str(item.question or "").strip()
        }
        for question in asked:
            if question.source_ref or not question.text.strip():
                # Ticked likely questions already come from the Question Bank.
                continue
            key = _normalised(question.text)
            if key in existing or key in {_normalised(text) for text in unsourced}:
                continue
            unsourced.append(question.text.strip())
        if unsourced:
            fingerprint = hashlib.sha256(
                "\x1f".join(unsourced).encode("utf-8")
            ).hexdigest()[:16]
            proposals.append(
                DebriefProposal(
                    id=f"question_bank:{fingerprint}",
                    kind="question_bank",
                    questions=tuple(unsourced),
                )
            )

        story_ids = {
            question.story_id
            for question in asked
            if question.story_id
        }
        if story_ids:
            stories = {
                row.id: row
                for row in (
                    await self._session.execute(
                        select(Story).where(Story.id.in_(story_ids))
                    )
                ).scalars()
            }
            for story_id in sorted(stories):
                story = stories.get(story_id)
                if story is None:
                    continue
                proposals.append(
                    DebriefProposal(
                        id=f"story_use:{story_id}",
                        kind="story_use",
                        story_id=story_id,
                        story_title=story.title,
                    )
                )
        return tuple(proposals)

    async def accept_proposal(
        self, round_id: str, proposal_id: str, now: datetime
    ) -> DebriefRead:
        round_row = await self._round(round_id)
        if round_row is None or not await self._active_application(
            round_row.application_id
        ):
            raise ReadinessError("not_found")
        row = await self._row(round_id)
        if row is None:
            raise ReadinessError("not_found")
        proposals = [
            proposal
            for proposal in (
                _deserialize_proposal(value) for value in (row.proposals_json or [])
            )
            if proposal is not None
        ]
        proposal = next((item for item in proposals if item.id == proposal_id), None)
        if proposal is None:
            raise ReadinessError("not_found")
        if proposal.accepted:
            return self._read(round_row, row)

        # Claim the accept before any domain write: concurrent accepts collide
        # on the version guard and exactly one performs the writes (AC27).
        claimed = [asdict(item) for item in proposals]
        for item in claimed:
            if item["id"] == proposal_id:
                item["accepted"] = True
        result = await self._session.execute(
            update(CoachInterviewDebrief)
            .where(
                CoachInterviewDebrief.id == row.id,
                CoachInterviewDebrief.version == row.version,
            )
            .values(
                proposals_json=claimed,
                version=row.version + 1,
                updated_at=_naive_utc(now),
            )
        )
        if (result.rowcount or 0) == 0:
            # Lost the race: return the state the winner wrote.
            row = await self._row(round_id)
            if row is None:
                raise ReadinessError("version_conflict")
            return self._read(round_row, row)

        if proposal.kind == "question_bank":
            # Accept is idempotent: only texts not already stored are created.
            existing = {
                _normalised(str(item.question))
                for item in (
                    await self._session.execute(select(QuestionBankItem))
                ).scalars()
                if str(item.question or "").strip()
            }
            for text in proposal.questions:
                if _normalised(text) in existing:
                    continue
                await create_question_bank_item(
                    self._session,
                    QuestionBankCreate(
                        title=text[:256],
                        question=text,
                        answer_draft="Draft",
                        linked_applications=[round_row.application_id],
                        source="interview_prep",
                    ),
                )
                existing.add(_normalised(text))
        elif proposal.story_id:
            if not await StoryService().record_use(proposal.story_id, self._session):
                raise ReadinessError("not_found")

        return replace(
            self._read(round_row, row),
            version=row.version + 1,
            proposals=tuple(
                proposal
                for proposal in (
                    _deserialize_proposal(value) for value in claimed
                )
                if proposal is not None
            ),
        )

    async def extract_notes(self, round_id: str, now: datetime) -> tuple[str, ...]:
        """Tier T proposal of the asked questions; nothing is saved (spec §10)."""
        round_row = await self._round(round_id)
        if round_row is None or not await self._active_application(
            round_row.application_id
        ):
            raise ReadinessError("not_found")
        row = await self._row(round_id)
        if row is None or not (row.notes_text or "").strip():
            raise ReadinessError("invalid_input")
        if load_runtime().get("ai_mode") not in {"local", "custom"}:
            raise ReadinessError("temporarily_unavailable")

        notes = row.notes_text[:_MAX_NOTES_TEXT]
        case = {"debrief_id": row.id, "notes": notes}
        try:
            output = await _extract_call(notes)
        except Exception:
            raise ReadinessError("temporarily_unavailable") from None
        if grounding_violations("debrief_extract", output, case):
            raise ReadinessError("temporarily_unavailable")
        return tuple(output["questions"][:_MAX_EXTRACT_QUESTIONS])


async def _extract_call(notes: str) -> dict:
    from .explain import _route_base_url

    tier = load_tier_map()["T"]
    payload = {
        "model": tier.model_id,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON with a questions array of the interview "
                    "questions found in the notes, each at most 120 characters."
                ),
            },
            {"role": "user", "content": notes},
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
        raise ValueError("debrief extraction is not JSON")
    return json.loads(content[start : end + 1])
