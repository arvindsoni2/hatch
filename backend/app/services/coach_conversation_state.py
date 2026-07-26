"""Coarse command transition registry for conversational Coach sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ConversationState(Protocol):
    conversation_state: str | None
    status: str


@dataclass(frozen=True)
class TransitionRule:
    states: frozenset[str]
    statuses: frozenset[str]


TRANSITIONS: dict[str, TransitionRule] = {
    "start": TransitionRule(frozenset({"ready"}), frozenset({"setup"})),
    "begin_answer": TransitionRule(frozenset({"asking"}), frozenset({"active"})),
    "finish_answer": TransitionRule(frozenset({"listening"}), frozenset({"active"})),
    "keep_speaking": TransitionRule(frozenset({"listening"}), frozenset({"active"})),
    "pause": TransitionRule(
        frozenset(
            {
                "asking",
                "listening",
                "awaiting_next_action",
                "coaching",
                "recoverable_error",
            }
        ),
        frozenset({"active"}),
    ),
    "resume": TransitionRule(frozenset({"paused"}), frozenset({"active"})),
    "cancel_attempt": TransitionRule(frozenset({"listening"}), frozenset({"active"})),
    "retry_answer": TransitionRule(
        frozenset({"awaiting_next_action", "coaching", "recoverable_error"}),
        frozenset({"active"}),
    ),
    "retry_setup": TransitionRule(
        frozenset({"recoverable_error"}), frozenset({"setup"})
    ),
    "rebuild_plan": TransitionRule(frozenset({"ready"}), frozenset({"setup"})),
    "retry_processing": TransitionRule(
        frozenset({"recoverable_error"}), frozenset({"active"})
    ),
    "retry_report": TransitionRule(
        frozenset({"recoverable_error", "completed"}),
        frozenset({"active", "completed"}),
    ),
    "request_hint": TransitionRule(
        frozenset({"asking", "listening"}), frozenset({"active"})
    ),
    "request_coaching": TransitionRule(
        frozenset({"awaiting_next_action"}), frozenset({"active"})
    ),
    "return_to_review": TransitionRule(frozenset({"coaching"}), frozenset({"active"})),
    "edit_transcript": TransitionRule(
        frozenset({"awaiting_next_action", "coaching"}), frozenset({"active"})
    ),
    "accept_attempt": TransitionRule(
        frozenset({"awaiting_next_action", "coaching"}), frozenset({"active"})
    ),
    "record_self_assessment": TransitionRule(
        frozenset({"awaiting_next_action", "coaching", "completed"}),
        frozenset({"active", "completed"}),
    ),
    "update_retention": TransitionRule(
        frozenset(
            {
                "ready",
                "asking",
                "listening",
                "awaiting_next_action",
                "coaching",
                "paused",
                "recoverable_error",
            }
        ),
        frozenset({"setup", "active"}),
    ),
    "skip_question": TransitionRule(frozenset({"asking"}), frozenset({"active"})),
    "end_session": TransitionRule(
        frozenset(
            {
                "asking",
                "awaiting_next_action",
                "coaching",
                "paused",
                "recoverable_error",
            }
        ),
        frozenset({"active"}),
    ),
    "delete_audio": TransitionRule(
        frozenset(
            {
                "awaiting_next_action",
                "coaching",
                "paused",
                "recoverable_error",
                "completed",
            }
        ),
        frozenset({"active", "completed"}),
    ),
    "delete_transcript": TransitionRule(
        frozenset(
            {"awaiting_next_action", "coaching", "recoverable_error", "completed"}
        ),
        frozenset({"active", "completed"}),
    ),
}


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
        if state in rule.states and status in rule.statuses
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
    if rule is None or state not in rule.states or status not in rule.statuses:
        raise ValueError("coach_conversation_invalid_state")
    return rule
