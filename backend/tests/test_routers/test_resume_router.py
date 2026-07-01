"""Integration tests for /api/resume router — status, json, upload endpoints."""
from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_resume_status_returns_200(client: AsyncClient) -> None:
    """GET /api/resume/status returns 200."""
    resp = await client.get("/api/resume/status")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_resume_json_returns_200_or_404(client: AsyncClient) -> None:
    """GET /api/resume/json returns 200 if resume exists, 404 if not."""
    resp = await client.get("/api/resume/json")
    assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_resume_upload_invalid_file_type_returns_422(client: AsyncClient) -> None:
    """POST /api/resume/upload with .txt file returns 422."""
    resp = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.txt", io.BytesIO(b"plain text"), "text/plain")},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_resume_upload_falls_back_when_structured_parse_times_out(
    client: AsyncClient,
) -> None:
    """A slow local LLM must not outlive the frontend proxy timeout."""
    extracted_text = (
        "Jane Doe\n\nProfessional Summary\nSenior engineer.\n\n"
        "Skills\nPython, FastAPI"
    )

    with (
        patch("app.routers.resume._extract_text_from_docx", return_value=extracted_text),
        patch("app.services.resume_store.save_resume_text"),
        patch("app.routers.resume._STRUCTURED_PARSE_TIMEOUT_SECONDS", 0),
    ):
        resp = await client.post(
            "/api/resume/upload",
            files={
                "file": (
                    "resume.docx",
                    io.BytesIO(b"synthetic docx"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "resume.docx"
    assert body["parsed_cv"]["skills"][0]["items"] == ["Python", "FastAPI"]
    assert "timed out" in body["warnings"][0]
