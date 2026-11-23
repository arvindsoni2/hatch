from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.application import Application, InterviewRound


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", True)


def _past() -> datetime:
    return (datetime.now(UTC) - timedelta(hours=2)).replace(tzinfo=None)


async def _seed_round(
    db_session: AsyncSession,
    *,
    app_id: str = "app-1",
    round_id: str = "round-1",
    status: str = "scheduled",
    scheduled_at: datetime | None = None,
) -> None:
    if await db_session.get(Application, app_id) is None:
        db_session.add(
            Application(id=app_id, status="interview", priority="normal")
        )
    db_session.add(
        InterviewRound(
            id=round_id,
            application_id=app_id,
            round_number=1,
            type="behavioural",
            scheduled_at=scheduled_at or _past(),
            duration_minutes=60,
            status=status,
        )
    )
    await db_session.flush()


async def test_next_actions_includes_debrief_prompt(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_round(db_session)

    response = await client.get("/api/coach/readiness/next-actions")

    assert response.status_code == 200
    assert response.json() == [
        {
            "application_id": "app-1",
            "round_id": "round-1",
            "action": "How did it go?",
            "reason": "Debrief due",
            "urgency": "high",
            "kind": "debrief",
        }
    ]


async def test_round_times_returned_as_utc_z(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_round(db_session, status="completed")

    response = await client.get("/api/coach/readiness/rounds/round-1/debrief")

    assert response.status_code == 200
    assert response.json()["scheduled_at"].endswith("Z")


async def test_flag_off_blocks_writes_but_allows_reads(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _seed_round(db_session, round_id="round-due")
    await _seed_round(db_session, round_id="round-saved")
    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", True)
    saved = await client.put(
        "/api/coach/readiness/rounds/round-saved/debrief",
        json={"expected_version": 0, "overall": 4, "expectation": "unsure"},
    )
    assert saved.status_code == 200

    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", False)
    unstored = await client.get("/api/coach/readiness/rounds/round-due/debrief")
    stored = await client.get("/api/coach/readiness/rounds/round-saved/debrief")
    actions = await client.get("/api/coach/readiness/next-actions")
    blocked = await client.put(
        "/api/coach/readiness/rounds/round-due/debrief",
        json={"expected_version": 0, "overall": 4},
    )
    skipped = await client.post(
        "/api/coach/readiness/rounds/round-due/debrief/skip",
        json={"expected_version": 0},
    )

    assert unstored.status_code == 404
    assert unstored.json()["detail"] == "not_found"
    assert stored.status_code == 200
    assert stored.json()["status"] == "saved"
    assert actions.json() == []
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "disabled"
    assert skipped.status_code == 403


async def test_display_timezone_route(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "HATCH_DISPLAY_TIMEZONE", "Asia/Kolkata")
    configured = await client.get("/api/coach/readiness/display-timezone")
    monkeypatch.setattr(settings, "HATCH_DISPLAY_TIMEZONE", None)
    unset = await client.get("/api/coach/readiness/display-timezone")

    assert configured.status_code == 200
    assert configured.json() == {"display_timezone": "Asia/Kolkata"}
    assert unset.json() == {"display_timezone": None}


async def test_notes_only_draft_save_and_extract_routes(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.coach_readiness.debrief import DebriefService

    await _seed_round(db_session, round_id="round-notes")

    draft = await client.put(
        "/api/coach/readiness/rounds/round-notes/debrief",
        json={
            "expected_version": 0,
            "overall": None,
            "notes_text": "Asked about budgets and sign-off.",
        },
    )
    assert draft.status_code == 200
    assert draft.json()["status"] == "draft"
    assert draft.json()["proposals"] == []

    async def fake_extract(self, round_id, now):
        return ("How did you manage the budget?",)

    monkeypatch.setattr(DebriefService, "extract_notes", fake_extract)
    extracted = await client.post(
        "/api/coach/readiness/rounds/round-notes/debrief/extract"
    )
    assert extracted.status_code == 200
    assert extracted.json() == {"questions": ["How did you manage the budget?"]}

    async def fake_accept(self, round_id, proposal_id, now):
        return await DebriefService.get_or_due(self, round_id, now)

    monkeypatch.setattr(DebriefService, "accept_proposal", fake_accept)
    accepted = await client.post(
        "/api/coach/readiness/rounds/round-notes/debrief/proposals/xyz/accept"
    )
    assert accepted.status_code == 200

    monkeypatch.setattr(settings, "HATCH_COACH_DEBRIEF_ENABLED", False)
    blocked_extract = await client.post(
        "/api/coach/readiness/rounds/round-notes/debrief/extract"
    )
    blocked_accept = await client.post(
        "/api/coach/readiness/rounds/round-notes/debrief/proposals/xyz/accept"
    )
    assert blocked_extract.status_code == 403
    assert blocked_extract.json()["detail"] == "disabled"
    assert blocked_accept.status_code == 403


async def test_coverage_overview_includes_signals(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _seed_round(db_session, app_id="app-signal", round_id="round-signal")

    response = await client.get("/api/coach/readiness/coverage/overview")

    assert response.status_code == 200
    assert response.json()["signals"] == []
