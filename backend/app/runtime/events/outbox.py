"""Transaction-bound outbox repository and fenced delivery publisher."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .models import (
    RuntimeOutboxAttemptRecord,
    RuntimeOutboxRecord,
    RuntimeOutboxStatus,
)
from .repository import MetadataOnlyViolation


SUPPORTED_OUTBOX_DESTINATIONS = frozenset(
    {"runtime.telemetry", "runtime.evaluation", "runtime.notification"}
)


@dataclass(frozen=True)
class OutboxClaim:
    entry_id: str
    event_id: str
    destination: str
    claim_id: str
    fencing_token: int
    lease_expires_at: datetime


def _eligible(now: datetime) -> Select[tuple[RuntimeOutboxRecord]]:
    return (
        select(RuntimeOutboxRecord)
        .where(
            RuntimeOutboxRecord.not_before <= now,
            or_(
                RuntimeOutboxRecord.status.in_(
                    [RuntimeOutboxStatus.PENDING, RuntimeOutboxStatus.RETRY_WAIT]
                ),
                (
                    (RuntimeOutboxRecord.status == RuntimeOutboxStatus.CLAIMED)
                    & (RuntimeOutboxRecord.lease_expires_at <= now)
                ),
            ),
        )
        .order_by(RuntimeOutboxRecord.not_before, RuntimeOutboxRecord.created_at)
        .limit(1)
    )


class SQLiteOutboxRepository:
    """Semantic outbox operations that never commit their bound transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(self, event_id: str, destination: str) -> RuntimeOutboxRecord:
        if destination not in SUPPORTED_OUTBOX_DESTINATIONS:
            raise ValueError(f"unsupported runtime outbox destination: {destination}")
        record = RuntimeOutboxRecord(event_id=event_id, destination=destination)
        self.session.add(record)
        await self.session.flush()
        return record

    async def claim_next(
        self, *, now: datetime, lease_duration: timedelta
    ) -> OutboxClaim | None:
        candidate = await self.session.scalar(_eligible(now))
        if candidate is None:
            return None
        claim_id = str(uuid.uuid4())
        fencing_token = candidate.fencing_token + 1
        lease_expires_at = now + lease_duration
        result = await self.session.execute(
            update(RuntimeOutboxRecord)
            .where(
                RuntimeOutboxRecord.id == candidate.id,
                RuntimeOutboxRecord.fencing_token == candidate.fencing_token,
                RuntimeOutboxRecord.status == candidate.status,
                RuntimeOutboxRecord.claim_id == candidate.claim_id,
            )
            .values(
                status=RuntimeOutboxStatus.CLAIMED,
                claim_id=claim_id,
                fencing_token=fencing_token,
                lease_expires_at=lease_expires_at,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            return None
        return OutboxClaim(
            entry_id=candidate.id,
            event_id=candidate.event_id,
            destination=candidate.destination,
            claim_id=claim_id,
            fencing_token=fencing_token,
            lease_expires_at=lease_expires_at,
        )

    async def finalize_delivery(
        self,
        claim: OutboxClaim,
        *,
        delivered: bool,
        lease_duration: timedelta,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_not_before: datetime | None = None,
        dead_letter: bool = False,
        now: datetime | None = None,
    ) -> bool:
        if error_detail is not None:
            raise MetadataOnlyViolation(
                "raw outbox error_detail is disabled by the metadata-only contract"
            )
        finished_at = now or datetime.utcnow()
        status = (
            RuntimeOutboxStatus.DELIVERED
            if delivered
            else (
                RuntimeOutboxStatus.DEAD_LETTER
                if dead_letter
                else RuntimeOutboxStatus.RETRY_WAIT
            )
        )
        result = await self.session.execute(
            update(RuntimeOutboxRecord)
            .where(
                RuntimeOutboxRecord.id == claim.entry_id,
                RuntimeOutboxRecord.status == RuntimeOutboxStatus.CLAIMED,
                RuntimeOutboxRecord.claim_id == claim.claim_id,
                RuntimeOutboxRecord.fencing_token == claim.fencing_token,
            )
            .values(
                status=status,
                claim_id=None,
                lease_expires_at=None,
                delivered_at=finished_at if delivered else None,
                not_before=retry_not_before or finished_at,
                updated_at=finished_at,
            )
        )
        if result.rowcount != 1:
            return False
        attempt_number = (
            await self.session.scalar(
                select(func.count())
                .select_from(RuntimeOutboxAttemptRecord)
                .where(RuntimeOutboxAttemptRecord.outbox_entry_id == claim.entry_id)
            )
            or 0
        ) + 1
        self.session.add(
            RuntimeOutboxAttemptRecord(
                outbox_entry_id=claim.entry_id,
                attempt_number=attempt_number,
                started_at=claim.lease_expires_at - lease_duration,
                finished_at=finished_at,
                result=status.value,
                error_code=error_code,
                error_detail=None,
            )
        )
        return True


class OutboxPublisher:
    """Own short claim/finalization transactions for at-least-once delivery."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        lease_duration: timedelta = timedelta(seconds=30),
        lock_retry_attempts: int = 3,
    ) -> None:
        if lock_retry_attempts < 1:
            raise ValueError("lock_retry_attempts must be at least 1")
        self.session_factory = session_factory
        self.lease_duration = lease_duration
        self.lock_retry_attempts = lock_retry_attempts

    async def _claim_once(self, claimed_at: datetime) -> OutboxClaim | None:
        async with self.session_factory.begin() as session:
            return await SQLiteOutboxRepository(session).claim_next(
                now=claimed_at, lease_duration=self.lease_duration
            )

    async def claim_next(self, *, now: datetime | None = None) -> OutboxClaim | None:
        claimed_at = now or datetime.utcnow()
        for attempt in range(self.lock_retry_attempts):
            try:
                return await self._claim_once(claimed_at)
            except OperationalError as error:
                if "locked" not in str(error).lower() or attempt + 1 == self.lock_retry_attempts:
                    raise
                await asyncio.sleep(0.005 * (2**attempt))
        return None

    async def finalize_delivery(
        self,
        claim: OutboxClaim,
        *,
        delivered: bool,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_not_before: datetime | None = None,
        dead_letter: bool = False,
        now: datetime | None = None,
    ) -> bool:
        async with self.session_factory.begin() as session:
            return await SQLiteOutboxRepository(session).finalize_delivery(
                claim,
                delivered=delivered,
                lease_duration=self.lease_duration,
                error_code=error_code,
                error_detail=error_detail,
                retry_not_before=retry_not_before,
                dead_letter=dead_letter,
                now=now,
            )
