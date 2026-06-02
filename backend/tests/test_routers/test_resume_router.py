"""Integration tests for /api/resume router — status, json, upload endpoints."""
from __future__ import annotations

import io

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
