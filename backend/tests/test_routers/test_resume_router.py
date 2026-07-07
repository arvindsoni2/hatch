"""Integration tests for /api/resume router — status, json, upload endpoints."""
from __future__ import annotations

import io
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.routers.resume import _heuristic_cv, _is_complete_parse


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
async def test_resume_upload_rejects_extension_with_wrong_mime_type(client: AsyncClient) -> None:
    """POST /api/resume/upload requires the extension and content type to agree."""
    resp = await client.post(
        "/api/resume/upload",
        files={"file": ("resume.pdf", io.BytesIO(b"plain text"), "text/plain")},
    )
    assert resp.status_code == 422
    assert "PDF and DOCX" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_resume_upload_falls_back_when_structured_parse_times_out(
    client: AsyncClient,
    tmp_path,
) -> None:
    """A slow local LLM must not outlive the frontend proxy timeout."""
    extracted_text = (
        "Jane Doe\n\nProfessional Summary\nSenior engineer.\n\n"
        "Skills\nPython, FastAPI"
    )

    with (
        patch("app.routers.resume._extract_text_from_docx", return_value=extracted_text),
        patch("app.routers.resume._data_dir", return_value=tmp_path),
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


def test_grounded_fallback_preserves_complete_cv_structure() -> None:
    text = """Arvind Soni
arvind@example.com
Newcastle upon Tyne
07424 338059
Profile
Technical Project Manager delivering regulated programmes.
Professional Experience
05/2022 – Present Product Delivery Lead
Natoora Ltd
Established an Agile operating model.
• Reduced time-to-market from 5 weeks to 3 weeks.
07/2011 – 05/2022 Associate Consultant
Tata Consultancy Services
• Led a £400K infrastructure modernisation programme.
Education
2000 – 2004 Bachelor of Engineering - Computer Science
RGPV
Technical Skills and Tools
Agile Delivery Tools: Jira, Confluence
DevOps & Cloud: GitHub Actions, Docker
Awards & Certifications
• PMI PMP (Project Management Professional)
• PMI-ACP (Agile Certified Practitioner)
"""

    parsed = _heuristic_cv(text)

    assert _is_complete_parse(parsed)
    assert parsed["personal"]["full_name"] == "Arvind Soni"
    assert [item["role"] for item in parsed["experience"]] == [
        "Product Delivery Lead",
        "Associate Consultant",
    ]
    assert parsed["education"][0]["qualification"] == "Bachelor of Engineering - Computer Science"
    assert parsed["skills"][1]["category"] == "DevOps & Cloud"
    assert parsed["certifications"] == [
        "PMI PMP (Project Management Professional)",
        "PMI-ACP (Agile Certified Practitioner)",
    ]
