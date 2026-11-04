"""Commands and reads for real-interview debriefs (P2)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.coach_readiness import CoachInterviewDebrief
from app.repositories.interview_repository import InterviewRepository
from app.schemas.interview import InterviewRoundUpdate

from .contracts import (
    DebriefQuestion,
    DebriefRead,
    ReadinessError,
    SaveDebriefCommand,
)
from .questions import likely_questions

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
        return DebriefRead(
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
        if not 1 <= int(command.overall) <= 5:
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
            "status": "saved",
            "overall": command.overall,
            "expectation": command.expectation,
            "questions_json": [
                _serialize_question(question) for question in command.questions
            ],
            "went_well": command.went_well,
            "do_differently": command.do_differently,
            "notes_text": command.notes_text,
            "updated_at": moment,
        }
        if row is None:
            row = CoachInterviewDebrief(
                interview_round_id=round_id,
                version=1,
                proposals_json=[],
                created_at=moment,
                **values,
            )
            try:
                async with self._session.begin_nested():
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
        return self._read(round_row, row)

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
            async with self._session.begin_nested():
                self._session.add(row)
                await self._session.flush()
        except IntegrityError as exc:
            raise ReadinessError("version_conflict") from exc
        return self._read(round_row, row)
