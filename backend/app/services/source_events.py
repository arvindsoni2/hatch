"""Neutral source-change seam between existing domains and Phase 2 (spec §5.3)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

SourceKind = Literal[
    "coach_session", "story", "question_bank_item", "job", "interview_round"
]
ChangeKind = Literal["deleted", "edited", "deactivated"]


@dataclass(frozen=True)
class SourceChange:
    kind: SourceKind
    source_id: str
    change: ChangeKind


class SourceChangeListener(Protocol):
    async def on_source_change(
        self, session: AsyncSession, change: SourceChange
    ) -> None: ...


_LISTENERS: list[SourceChangeListener] = []


def register_listener(listener: SourceChangeListener) -> None:
    if listener not in _LISTENERS:
        _LISTENERS.append(listener)


def unregister_listener(listener: SourceChangeListener) -> None:
    if listener in _LISTENERS:
        _LISTENERS.remove(listener)


async def notify(session: AsyncSession, change: SourceChange) -> None:
    """Await every listener with the caller's session, inside its transaction."""
    for listener in list(_LISTENERS):
        await listener.on_source_change(session, change)
