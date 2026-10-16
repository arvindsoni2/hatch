"""DAST-style reflected-input and bounded-resource checks for PR4 routes."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "session_id",
    ["%3Cscript%3Ealert(1)%3C/script%3E", "javascript:alert(1)", "\u202eprivate"],
)
async def test_hostile_session_identifiers_are_not_reflected(client, session_id: str) -> None:
    response = await client.get(f"/api/coach/sessions/{session_id}/diagnostics")

    assert response.status_code in {400, 404}
    assert "script" not in response.text.casefold()
    assert "javascript:" not in response.text.casefold()
    assert "private" not in response.text.casefold()


@pytest.mark.asyncio
async def test_export_rejects_unknown_fields_without_echoing_payload(client) -> None:
    canary = "CANARY-EXPORT-HOSTILE"
    response = await client.post(
        "/api/coach/sessions/unknown/exports",
        json={
            "format": "json",
            "expected_activity_version": 0,
            "expected_retention_version": 0,
            "contract_version": "coach_report_export_v1",
            "title": canary,
        },
    )

    assert response.status_code == 400
    assert canary not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("format_name", ["json", "markdown"])
async def test_export_hostile_reflection_cannot_inject_headers_or_raw_paths(client, db_session, format_name):
    from app.models.coach_session import InterviewSession
    from app.services.coach_conversational_report import build_conversational_report, ReportInputSnapshot

    canary = '<img src=x onerror=alert(1)> ```\n[open](javascript:alert(1))'
    report = build_conversational_report(ReportInputSnapshot(
        session_id="hostile-export", activity_version=3, retention_version=4,
        accepted_root_bundles=(), compatibility_key="hostile-key",
        counts={key: 0 for key in (
            "planned_questions_total", "planned_questions_answered", "planned_questions_skipped",
            "follow_ups_asked", "follow_ups_answered", "accepted_attempts", "retry_attempts",
            "unavailable_attempts", "hints_used",
        )}, candidate_reflection={"note": canary, "source_path": "PRIVATE-PATH-CANARY", "audio_uri": "PRIVATE-AUDIO-CANARY"},
    )).persisted_json()
    db_session.add(InterviewSession(id="hostile-export", company_name='"\r\nInjected: true', role_title=canary,
        experience_version="conversational_v1", status="completed", conversation_state="completed",
        activity_version=3, retention_version=4, report_state="completed", report_json=report))
    await db_session.commit()
    response = await client.post("/api/coach/sessions/hostile-export/exports", json={
        "format": format_name, "expected_activity_version": 3, "expected_retention_version": 4,
        "contract_version": "coach_report_export_v1",
    })
    assert response.status_code == 200, response.text
    assert "injected" not in response.headers
    assert "PRIVATE-PATH-CANARY" not in response.text and "PRIVATE-AUDIO-CANARY" not in response.text
    if format_name == "markdown":
        assert "<img" not in response.text
        assert "\\u003cimg" in response.text
        assert response.text.count("```json") == response.text.count("\n```\n")
    else:
        assert response.json()["candidate_reflection"]["note"] == canary
