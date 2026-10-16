"""Privacy deletion contracts for conversational Coach."""

import hashlib

from app.services.coach_privacy import (
    deletion_request_hash,
    session_deletion_key,
)


def test_session_deletion_key_is_domain_separated_and_one_way():
    session_id = "session-123"

    key = session_deletion_key(session_id)

    assert key == hashlib.sha256(
        b"coach-session-deletion-v1:session-123"
    ).hexdigest()
    assert session_id not in key


def test_deletion_request_hash_is_deterministic_and_content_free():
    request = {
        "command_id": "delete-1",
        "confirmation": "DELETE",
        "contract_version": "coach_session_hard_delete_v1",
    }

    first = deletion_request_hash(request)
    second = deletion_request_hash(dict(request))

    assert first == second
    assert len(first) == 64
    assert "DELETE" not in first
