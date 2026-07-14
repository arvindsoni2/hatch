"""Authoritative onboarding state transition tests."""
from __future__ import annotations

import pytest

from app.services.onboarding_service import OnboardingService


@pytest.mark.asyncio
async def test_new_install_starts_not_started(db_session):
    status = await OnboardingService(db_session).status()

    assert status.status == "not_started"
    assert status.last_completed_step is None


@pytest.mark.asyncio
async def test_password_setup_moves_incomplete_onboarding_to_finalization_pending(db_session):
    service = OnboardingService(db_session)
    await service.mark_in_progress("review")

    state = await service.mark_password_configured()

    assert state.status == "finalization_pending"
    assert state.last_completed_step == "protect-workspace"


@pytest.mark.asyncio
async def test_complete_state_is_never_implicitly_downgraded(db_session):
    service = OnboardingService(db_session)
    await service.mark_complete("7af984dd-13c2-42e5-a17a-d62e548eadf1", "payload", "profile")

    await service.mark_in_progress("welcome")
    state = await service.mark_password_configured()

    assert state.status == "complete"
    assert state.last_completed_step == "protect-workspace"


@pytest.mark.asyncio
async def test_unknown_step_is_rejected_without_changing_state(db_session):
    service = OnboardingService(db_session)

    with pytest.raises(ValueError, match="Unknown onboarding step"):
        await service.mark_in_progress("password-first")

    assert (await service.status()).status == "not_started"


@pytest.mark.asyncio
async def test_reset_progress_returns_to_not_started(db_session):
    service = OnboardingService(db_session)
    await service.mark_in_progress("skills")

    state = await service.reset_progress()

    assert state.status == "not_started"
    assert state.last_completed_step is None

