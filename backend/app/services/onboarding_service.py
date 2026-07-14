"""State transitions for first-run onboarding."""
from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.onboarding import OnboardingState
from .profile_service import (
    atomic_save_profile_raw,
    current_profile_hash,
    profile_payload_hash,
)

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


class OnboardingFinalizationError(Exception):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


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

    async def finalize(
        self,
        finalization_id: str,
        profile_data: dict,
    ) -> OnboardingState:
        payload_hash = profile_payload_hash(profile_data)
        from ..schemas.profile import Profile

        profile = Profile.model_validate(profile_data)
        if not profile.is_complete():
            raise OnboardingFinalizationError(
                "profile_incomplete",
                "Name, at least one target role, and at least one location are required.",
                422,
            )

        row = await self.state()
        if row.status == "complete":
            if (
                row.finalization_id != finalization_id
                or row.finalization_payload_hash != payload_hash
            ):
                raise OnboardingFinalizationError(
                    "onboarding_already_complete",
                    "Onboarding was already completed by another finalization request.",
                    409,
                )
            if current_profile_hash() != row.finalized_profile_hash:
                raise OnboardingFinalizationError(
                    "finalized_profile_changed",
                    "The finalized profile changed after onboarding completed.",
                    409,
                )
            return row

        if row.status != "finalization_pending":
            raise OnboardingFinalizationError(
                "password_not_configured",
                "Protect the workspace with a password before finalizing onboarding.",
                409,
            )
        if row.finalization_id and row.finalization_id != finalization_id:
            raise OnboardingFinalizationError(
                "finalization_conflict",
                "A different onboarding finalization is already in progress.",
                409,
            )

        _, finalized_hash = atomic_save_profile_raw(profile_data)
        if finalized_hash != payload_hash:
            raise OnboardingFinalizationError(
                "profile_write_mismatch",
                "The saved profile did not match the validated onboarding payload.",
                500,
            )
        return await self.mark_complete(
            finalization_id,
            payload_hash,
            finalized_hash,
        )

    async def reset_progress(self) -> OnboardingState:
        row = await self.state()
        row.status = "not_started"
        row.last_completed_step = None
        row.finalization_id = None
        row.finalization_payload_hash = None
        row.finalized_profile_hash = None
        await self._db.flush()
        return row
