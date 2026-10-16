"""Isolated negative-path coverage for PR4 conversational HTTP boundaries."""

from __future__ import annotations

import pytest


EXPORT_PAYLOAD = {
    "format": "json",
    "expected_activity_version": 0,
    "expected_retention_version": 0,
    "include_transcript": True,
    "include_evidence_details": True,
    "include_attempt_history": True,
    "include_candidate_reflection": True,
    "contract_version": "coach_report_export_v1",
}

DELETE_PAYLOAD = {
    "command_id": "01JEXAMPLE0000000000000001",
    "confirmation": "DELETE",
    "contract_version": "coach_session_hard_delete_v1",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "http_request",
    [
        ("GET", "/api/coach/sessions/private-canary/report", None),
        ("POST", "/api/coach/sessions/private-canary/exports", EXPORT_PAYLOAD),
        (
            "POST",
            "/api/coach/sessions/private-canary/deletion-commands",
            DELETE_PAYLOAD,
        ),
        ("GET", "/api/coach/sessions/private-canary/diagnostics", None),
    ],
)
async def test_unknown_session_does_not_disclose_existence_or_details(
    client, http_request
) -> None:
    method, path, payload = http_request
    response = await client.request(method, path, json=payload)

    assert response.status_code in {404, 409, 503}
    assert "private-canary" not in response.text
    if response.headers.get("content-type", "").startswith("application/json"):
        body = response.json()
        if "error" in body:
            assert body["error"].get("details") == {}


@pytest.mark.asyncio
async def test_progress_selector_conflict_is_canonical_and_non_mutating(client) -> None:
    response = await client.get(
        "/api/coach/conversational-progress",
        params={"session_id": "session-a", "application_id": "application-a"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_progress_selector_conflict"
    assert response.json()["error"]["details"] == {}
    assert "session-a" not in response.text
    assert "application-a" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/coach/sessions/%2F/report",
        "/api/coach/sessions/private-canary%2Freport/report",
        "/api/coach/sessions/private-canary%5Creport/diagnostics",
    ],
)
async def test_new_pr4_routes_reject_path_traversal_without_reflection(client, path):
    response = await client.get(path)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "coach_contract_unsupported"
    assert response.json()["error"]["details"] == {}
    assert "private-canary" not in response.text


@pytest.mark.asyncio
async def test_progress_group_limit_is_bounded(client) -> None:
    response = await client.get(
        "/api/coach/conversational-progress", params={"group_limit": 101}
    )

    assert response.status_code == 400
