"""Privacy-safe transcript and hard-deletion orchestration contracts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..schemas.coach_conversation import (
    DeletionCommandResult,
    HardDeletionCommandRequest,
)
from .coach_conversational_contracts import HARD_DELETE_CONTRACT


def session_deletion_key(session_id: str) -> str:
    """Return a domain-separated pseudonymous key for a deletion receipt."""

    return hashlib.sha256(
        f"coach-session-deletion-v1:{session_id}".encode("utf-8")
    ).hexdigest()


def deletion_request_hash(request: Mapping[str, object]) -> str:
    """Hash only the canonical command envelope, never its raw storage."""

    encoded = json.dumps(
        dict(request), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class TranscriptDeletionClaim:
    session_id: str
    attempt_id: str
    expected_attempt_version: int
    expected_processing_generation: int
    expected_state_version: int
    expected_activity_version: int


@dataclass(frozen=True)
class TranscriptDeletionResult:
    session_id: str
    attempt_id: str
    state_version: int
    activity_version: int
    report_job_id: str | None = None


@dataclass(frozen=True)
class HardDeletionClaim:
    session_id: str
    session_key_hash: str
    command_id: str
    request_hash: str
    job_id: str
    deletion_generation: int
    claim_token: str


class PrivacyRepository(Protocol):
    async def delete_attempt_transcript(
        self, claim: TranscriptDeletionClaim
    ) -> TranscriptDeletionResult: ...

    async def claim_hard_deletion(
        self,
        session_id: str,
        request: HardDeletionCommandRequest,
        request_hash: str,
        now: datetime,
    ) -> HardDeletionClaim | DeletionCommandResult: ...

    async def finalise_hard_deletion(
        self, claim: HardDeletionClaim, now: datetime
    ) -> DeletionCommandResult: ...

    async def fail_hard_deletion(
        self, claim: HardDeletionClaim, error_code: str, now: datetime
    ) -> DeletionCommandResult: ...

    async def expire_deletion_receipts(self, now: datetime, limit: int) -> int: ...


async def delete_attempt_transcript(
    claim: TranscriptDeletionClaim, repository: PrivacyRepository
) -> TranscriptDeletionResult:
    return await repository.delete_attempt_transcript(claim)


async def claim_hard_deletion(
    session_id: str,
    request: HardDeletionCommandRequest,
    repository: PrivacyRepository,
    *,
    now: datetime,
) -> HardDeletionClaim | DeletionCommandResult:
    if request.contract_version != HARD_DELETE_CONTRACT:
        raise ValueError("coach_contract_unsupported")
    request_hash = deletion_request_hash(request.model_dump(mode="json"))
    return await repository.claim_hard_deletion(
        session_id, request, request_hash, now
    )


async def run_hard_deletion(
    claim: HardDeletionClaim,
    repository: PrivacyRepository,
    *,
    now: datetime,
) -> DeletionCommandResult:
    # The worker owns rollback/commit. Failure publication must happen only
    # after rolling back the unsuccessful deletion transaction.
    return await repository.finalise_hard_deletion(claim, now)


async def expire_deletion_receipts(
    repository: PrivacyRepository, *, now: datetime, limit: int = 100
) -> int:
    if not 1 <= limit <= 1000:
        raise ValueError("receipt cleanup limit must be between 1 and 1000")
    return await repository.expire_deletion_receipts(now, limit)


class CoachPrivacyService:
    """Thin dependency-injected facade used by routes and workers."""

    def __init__(self, repository: PrivacyRepository) -> None:
        self.repository = repository

    async def delete_attempt_transcript(
        self, claim: TranscriptDeletionClaim
    ) -> TranscriptDeletionResult:
        return await delete_attempt_transcript(claim, self.repository)

    async def claim_hard_deletion(
        self,
        session_id: str,
        request: HardDeletionCommandRequest,
        *,
        now: datetime,
    ) -> HardDeletionClaim | DeletionCommandResult:
        return await claim_hard_deletion(
            session_id, request, self.repository, now=now
        )

    async def run_hard_deletion(
        self, claim: HardDeletionClaim, *, now: datetime
    ) -> DeletionCommandResult:
        return await run_hard_deletion(claim, self.repository, now=now)
