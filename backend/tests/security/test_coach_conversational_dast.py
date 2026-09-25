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
