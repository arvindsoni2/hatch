"""Coarse command transition registry for conversational Coach sessions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol


class ConversationState(Protocol):
    conversation_state: str | None
    status: str


@dataclass(frozen=True)
class TransitionRule:
    """Exact coarse state/status projections that may invoke one command."""

    allowed_pairs: frozenset[tuple[str, str]]

    def permits(self, state: str | None, status: str | None) -> bool:
        return (
            state is not None
            and status is not None
            and (state, status) in self.allowed_pairs
        )


def _rule(*allowed_pairs: tuple[str, str]) -> TransitionRule:
    return TransitionRule(frozenset(allowed_pairs))


_TRANSITIONS: dict[str, TransitionRule] = {
    "start": _rule(("ready", "setup")),
    "begin_answer": _rule(("asking", "active")),
    "finish_answer": _rule(("listening", "active")),
    "keep_speaking": _rule(("listening", "active")),
    "pause": _rule(
        ("asking", "active"),
        ("listening", "active"),
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
        ("recoverable_error", "active"),
    ),
    "resume": _rule(("paused", "active")),
    "cancel_attempt": _rule(("listening", "active")),
    "record_capture_hard_stop": _rule(("listening", "active")),
    "retry_answer": _rule(
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
        ("recoverable_error", "active"),
    ),
    "retry_setup": _rule(("recoverable_error", "setup")),
    "rebuild_plan": _rule(("ready", "setup")),
    "retry_processing": _rule(("recoverable_error", "active")),
    "retry_report": _rule(
        ("recoverable_error", "active"),
        ("completed", "completed"),
    ),
    "request_hint": _rule(
        ("asking", "active"),
        ("listening", "active"),
    ),
    "request_coaching": _rule(("awaiting_next_action", "active")),
    "return_to_review": _rule(("coaching", "active")),
    "edit_transcript": _rule(
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
    ),
    "accept_attempt": _rule(
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
    ),
    "record_self_assessment": _rule(
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
        ("completed", "completed"),
    ),
    "update_retention": _rule(
        ("ready", "setup"),
        ("asking", "active"),
        ("listening", "active"),
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
        ("paused", "active"),
        ("recoverable_error", "setup"),
        ("recoverable_error", "active"),
    ),
    "skip_question": _rule(("asking", "active")),
    "end_session": _rule(
        ("asking", "active"),
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
        ("paused", "active"),
        ("recoverable_error", "active"),
    ),
    "delete_audio": _rule(
        ("asking", "active"),
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
        ("paused", "active"),
        ("recoverable_error", "active"),
        ("completed", "completed"),
    ),
    "delete_transcript": _rule(
        ("awaiting_next_action", "active"),
        ("coaching", "active"),
        ("recoverable_error", "active"),
        ("completed", "completed"),
    ),
}

TRANSITIONS: Final[Mapping[str, TransitionRule]] = MappingProxyType(_TRANSITIONS)


def _resolve_state(
    session: ConversationState | None,
    state: str | None,
    status: str | None,
) -> tuple[str | None, str | None]:
    if session is not None:
        state = session.conversation_state
        status = session.status
    return state, status


def allowed_commands(
    session: ConversationState | None = None,
    *,
    state: str | None = None,
    status: str | None = None,
) -> tuple[str, ...]:
    """Return registry-ordered commands permitted by coarse state and status."""
    state, status = _resolve_state(session, state, status)
    return tuple(
        command_type
        for command_type, rule in TRANSITIONS.items()
        if rule.permits(state, status)
    )


def require_transition(
    session: ConversationState | None = None,
    command_type: str = "",
    *,
    state: str | None = None,
    status: str | None = None,
) -> TransitionRule:
    """Return a permitted coarse rule or reject with the canonical error code."""
    state, status = _resolve_state(session, state, status)
    rule = TRANSITIONS.get(command_type)
    if rule is None or not rule.permits(state, status):
        raise ValueError("coach_conversation_invalid_state")
    return rule
