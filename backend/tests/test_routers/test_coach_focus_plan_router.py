"""Focus and plan routes: flag, validation and status codes (spec §12)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from app.config import settings
from app.models.application import Application, InterviewRound


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", True)


def _focus_body(**overrides):
    body = {
        "title": "Make answers specific",
        "dimension": "specificity",
        "group": {
            "role_family": "Delivery Lead",
            "interview_type": "behavioural",
        },
        "criteria": [{"kind": "practice", "count": 1}],
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_focus_and_plan_lifecycle(client: AsyncClient) -> None:
    created = await client.post(
        "/api/coach/readiness/focus-areas", json=_focus_body()
    )
    assert created.status_code == 201, created.text
    area = created.json()
    assert area["status"] == "active"
    assert area["active_slot"] == 1

    patched = await client.patch(
        f"/api/coach/readiness/focus-areas/{area['id']}",
        json={"expected_version": area["version"], "title": "Sharper answers"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "Sharper answers"

    stale = await client.patch(
        f"/api/coach/readiness/focus-areas/{area['id']}",
        json={"expected_version": area["version"], "title": "Stale"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "version_conflict"

    draft = await client.post(
        "/api/coach/readiness/plans", json={"minutes": 30}
    )
    assert draft.status_code == 201, draft.text
    plan = draft.json()
    assert plan["status"] == "draft"
    assert plan["items"][0]["type"] == "practice_session"

    started = await client.post(f"/api/coach/readiness/plans/{plan['id']}/start")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "active"

    item_id = started.json()["items"][0]["id"]
    done = await client.patch(
        f"/api/coach/readiness/plans/{plan['id']}/items/{item_id}",
        json={"action": "done"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["items"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_flag_off_blocks_creation_but_not_reads_or_edits(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await client.post(
        "/api/coach/readiness/focus-areas", json=_focus_body()
    )
    area = created.json()
    draft = await client.post("/api/coach/readiness/plans", json={})
    monkeypatch.setattr(settings, "HATCH_COACH_READINESS_ENABLED", False)

    blocked = await client.post(
        "/api/coach/readiness/focus-areas", json=_focus_body(title="Blocked")
    )
    blocked_plan = await client.post("/api/coach/readiness/plans", json={})
    blocked_start = await client.post(
        f"/api/coach/readiness/plans/{draft.json()['id']}/start"
    )
    listing = await client.get("/api/coach/readiness/focus-areas")
    edited = await client.patch(
        f"/api/coach/readiness/focus-areas/{area['id']}",
        json={"expected_version": area["version"], "title": "Still editable"},
    )

    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "disabled"
    assert blocked_plan.status_code == 403
    assert blocked_start.status_code == 403
    assert listing.status_code == 200
    assert listing.json()["active_count"] == 1
    assert edited.status_code == 200


@pytest.mark.asyncio
async def test_unknown_fields_and_invalid_transitions_are_safe(
    client: AsyncClient,
) -> None:
    unknown = await client.post(
        "/api/coach/readiness/focus-areas",
        json={**_focus_body(), "unexpected": True},
    )
    assert unknown.status_code == 422

    created = await client.post(
        "/api/coach/readiness/focus-areas", json=_focus_body()
    )
    area = created.json()
    paused = await client.patch(
        f"/api/coach/readiness/focus-areas/{area['id']}",
        json={"expected_version": area["version"], "status": "paused"},
    )
    archived = await client.patch(
        f"/api/coach/readiness/focus-areas/{area['id']}",
        json={
            "expected_version": paused.json()["version"],
            "status": "archived",
        },
    )
    illegal = await client.patch(
        f"/api/coach/readiness/focus-areas/{area['id']}",
        json={
            "expected_version": archived.json()["version"],
            "status": "active",
        },
    )

    assert paused.status_code == 200
    assert archived.status_code == 200
    assert illegal.status_code == 409
    assert illegal.json()["detail"] == "invalid_state"


@pytest.mark.asyncio
async def test_round_under_two_hours_is_invalid_input(
    client: AsyncClient, db_session
) -> None:
    db_session.add(Application(id="p5-app", status="interview", priority="normal"))
    await db_session.flush()
    db_session.add(
        InterviewRound(
            id="p5-round",
            application_id="p5-app",
            round_number=1,
            type="behavioural",
            scheduled_at=datetime.utcnow() + timedelta(minutes=90),
            duration_minutes=60,
            status="scheduled",
        )
    )
    await db_session.commit()

    response = await client.post(
        "/api/coach/readiness/plans",
        json={"minutes": 30, "target_round_id": "p5-round"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid_input"
