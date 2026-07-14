"""Onboarding-aware reset service tests."""
from __future__ import annotations

import pytest

from app.services.onboarding_service import OnboardingService
from app.services.setup_reset import apply_reset, reset_preview


@pytest.mark.asyncio
async def test_onboarding_reset_preserves_row_and_explicitly_resets_progress(
    db_session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    service = OnboardingService(db_session)
    await service.mark_complete("finalization-id", "payload", "profile")

    preview = await reset_preview(db_session, "onboarding")
    result = await apply_reset(
        db_session, "onboarding", confirmation="RESET", preserve_profile=True
    )

    assert "onboarding_state" not in preview["deletes"]
    assert "onboarding_state" in preview["preserves"]
    assert result["applied"] is True
    state = await OnboardingService(db_session).status()
    assert state.status == "not_started"
    assert state.finalization_id is None


@pytest.mark.asyncio
async def test_demo_reset_does_not_downgrade_completed_onboarding(
    db_session,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    service = OnboardingService(db_session)
    await service.mark_complete("finalization-id", "payload", "profile")

    await apply_reset(db_session, "demo", confirmation="RESET", preserve_profile=True)

    assert (await OnboardingService(db_session).status()).status == "complete"

