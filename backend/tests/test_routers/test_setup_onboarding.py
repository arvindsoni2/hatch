"""Crash-safe onboarding finalization API tests."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from httpx import AsyncClient

from app.services import profile_service

pytestmark = pytest.mark.app_lock

FINALIZATION_ID = "2d08a912-b0b1-4a77-b07f-64fc6c82f452"
OTHER_ID = "c971d30c-ad71-40b2-bfcb-051820673acc"


@pytest.fixture
def profile_payload() -> dict:
    return {
        "locale": "uk",
        "candidate": {"name": "Ada Lovelace", "title": "Platform Engineer"},
        "search": {
            "target_roles": ["Platform Engineer"],
            "locations": [{"city": "London", "country": "GB"}],
        },
    }


@pytest.fixture
def profile_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "profile.yaml"
    monkeypatch.setattr(profile_service, "_DEFAULT_PROFILE_PATH", path)
    return path


async def _protect_workspace(client: AsyncClient) -> None:
    response = await client.post(
        "/api/app-lock/setup", json={"password": "safe-password-1"}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_finalize_same_id_and_payload_is_idempotent(
    client: AsyncClient,
    profile_payload: dict,
    profile_path: Path,
) -> None:
    await _protect_workspace(client)
    body = {"finalization_id": FINALIZATION_ID, "profile": profile_payload}

    first = await client.post("/api/setup/onboarding/finalize", json=body)
    second = await client.post("/api/setup/onboarding/finalize", json=body)

    assert first.status_code == second.status_code == 200
    assert second.json()["onboarding"]["status"] == "complete"
    assert yaml.safe_load(profile_path.read_text(encoding="utf-8"))["candidate"]["name"] == "Ada Lovelace"


@pytest.mark.asyncio
async def test_different_id_after_completion_conflicts(
    client: AsyncClient,
    profile_payload: dict,
    profile_path: Path,
) -> None:
    await _protect_workspace(client)
    await client.post(
        "/api/setup/onboarding/finalize",
        json={"finalization_id": FINALIZATION_ID, "profile": profile_payload},
    )

    response = await client.post(
        "/api/setup/onboarding/finalize",
        json={"finalization_id": OTHER_ID, "profile": profile_payload},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "onboarding_already_complete"


@pytest.mark.asyncio
async def test_finalize_requires_password_gate(
    client: AsyncClient,
    profile_payload: dict,
    profile_path: Path,
) -> None:
    response = await client.post(
        "/api/setup/onboarding/finalize",
        json={"finalization_id": FINALIZATION_ID, "profile": profile_payload},
    )

    assert response.status_code == 423
    assert not profile_path.exists()


@pytest.mark.asyncio
async def test_finalize_rejects_incomplete_profile(
    client: AsyncClient,
    profile_path: Path,
) -> None:
    await _protect_workspace(client)

    response = await client.post(
        "/api/setup/onboarding/finalize",
        json={"finalization_id": FINALIZATION_ID, "profile": {"candidate": {"name": "Ada"}}},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "profile_incomplete"
    assert not profile_path.exists()


@pytest.mark.asyncio
async def test_finalize_returns_structured_validation_error(
    client: AsyncClient,
    profile_payload: dict,
    profile_path: Path,
) -> None:
    await _protect_workspace(client)
    profile_payload["search"]["locations"][0]["remote_preference"] = "teleport"

    response = await client.post(
        "/api/setup/onboarding/finalize",
        json={"finalization_id": FINALIZATION_ID, "profile": profile_payload},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "profile_invalid"
    assert not profile_path.exists()


@pytest.mark.asyncio
async def test_progress_is_available_before_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/setup/onboarding/progress", json={"step_id": "skills"}
    )

    assert response.status_code == 200
    assert response.json()["onboarding"] == {
        "status": "in_progress",
        "last_completed_step": "skills",
    }
