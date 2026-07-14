"""State transitions for first-run onboarding."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.onboarding import OnboardingState

OnboardingStatus = Literal[
    "not_started", "in_progress", "finalization_pending", "complete"
]

VALID_STEPS = {
    "welcome",
    "profile",
    "preferences",
    "skills",
    "experience",
    "ai-capabilities",
    "review",
    "protect-workspace",
}


class OnboardingService:
    """Own the singleton onboarding row and its legal transitions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def state(self) -> OnboardingState:
        row = await self._db.get(OnboardingState, 1, with_for_update=True)
        if row is None:
            row = OnboardingState(id=1)
            self._db.add(row)
            await self._db.flush()
        return row

    async def status(self) -> OnboardingState:
        return await self.state()

    async def mark_in_progress(self, step_id: str) -> OnboardingState:
        if step_id not in VALID_STEPS:
            raise ValueError(f"Unknown onboarding step: {step_id}")
        row = await self.state()
        if row.status != "complete":
            row.status = "in_progress"
            row.last_completed_step = step_id
            await self._db.flush()
        return row

    async def mark_password_configured(self) -> OnboardingState:
        row = await self.state()
        if row.status != "complete":
            row.status = "finalization_pending"
            row.last_completed_step = "protect-workspace"
            await self._db.flush()
        return row

    async def mark_complete(
        self,
        finalization_id: str,
        payload_hash: str,
        profile_hash: str,
    ) -> OnboardingState:
        row = await self.state()
        row.status = "complete"
        row.last_completed_step = "protect-workspace"
        row.finalization_id = finalization_id
        row.finalization_payload_hash = payload_hash
        row.finalized_profile_hash = profile_hash
        await self._db.flush()
        return row

    async def reset_progress(self) -> OnboardingState:
        row = await self.state()
        row.status = "not_started"
        row.last_completed_step = None
        row.finalization_id = None
        row.finalization_payload_hash = None
        row.finalized_profile_hash = None
        await self._db.flush()
        return row

