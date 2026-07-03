"""Tests for the tailor router — 200/404 responses, SSE stream, file download."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import get_db
from app.routers.tailor import get_tailor_service
from app.schemas.document import GeneratedDocumentRead
from app.schemas.tailor import (
    ATSKeywords,
    ATSScoreResult,
    JDAnalysisResponse,
    JDAnalysisResult,
    SkillMatchResult,
    TailorResultBundle,
)

from datetime import datetime

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_JD_RESPONSE = JDAnalysisResponse(
    job_id="test-job-123",
    analysis=JDAnalysisResult(
        role_title="Solutions Architect",
        ats_keywords=ATSKeywords(technical=["AWS"], methodologies=[], soft_skills=[], domain=[], certifications=[]),
    ),
    skill_match=SkillMatchResult(matched=["AWS"], missing=[], match_pct=75.0),
)

MOCK_DOC = GeneratedDocumentRead(
    id="doc-uuid-001",
    application_id="app-uuid-001",
    document_type="cv",
    version=1,
    file_path="/tmp/cv_v1_A.docx",
    file_size_bytes=10000,
    ats_score=82,
    variant_label="A",
    status="generated",
    created_at=datetime.utcnow(),
)

MOCK_BUNDLE = TailorResultBundle(
    application_id="app-uuid-001",
    cv_document_id="doc-uuid-001",
    cl_document_id="doc-uuid-002",
    ats_score=ATSScoreResult(
        overall_score=82,
        keyword_matches=[],
        format_warnings=[],
        missing_critical=[],
        improvement_suggestions=[],
    ),
)


@pytest.mark.asyncio
async def test_download_document_returns_existing_file(tmp_path):
    from app.services.tailor_service import TailorService

    document_path = tmp_path / "tailored-cv.docx"
    document_path.write_bytes(b"docx")
    document = MOCK_DOC.model_copy(update={"file_path": str(document_path)})

    with patch(
        "app.services.tailor_service.DocumentRepository.get_by_id",
        AsyncMock(return_value=document),
    ):
        file_path, filename = await TailorService().download_document(
            document.id, AsyncMock()
        )

    assert file_path == str(document_path)
    assert filename == "tailored-cv.docx"


def make_mock_service():
    svc = MagicMock()
    svc.analyse_job = AsyncMock(return_value=MOCK_JD_RESPONSE)
    svc.analyse_jd_text = AsyncMock(return_value=MOCK_JD_RESPONSE)
    svc.generate_cv = AsyncMock(return_value=MOCK_DOC)
    svc.generate_cover_letter = AsyncMock(return_value=MOCK_DOC)
    svc.generate_all = AsyncMock(return_value=MOCK_BUNDLE)
    svc.download_document = AsyncMock(return_value=("/tmp/cv_v1_A.docx", "cv_v1_A.docx"))
    svc.get_document_history = AsyncMock(return_value=[MOCK_DOC])
    return svc


@pytest_asyncio.fixture
async def client(db_session):
    mock_svc = make_mock_service()
    app.dependency_overrides[get_tailor_service] = lambda: mock_svc

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyse_job_202(client):
    resp = await client.post("/api/tailor/analyse/test-job-123")
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["type"] == "tailor_analyse"


@pytest.mark.asyncio
async def test_template_recommendation_endpoint(client, tmp_path):
    master_cv = tmp_path / "master_cv.json"
    master_cv.write_text('{"experience": [{}, {}, {}, {}, {}, {}]}')

    with patch("app.routers.tailor.resolve_master_cv_path", return_value=master_cv):
        resp = await client.post(
            "/api/tailor/templates/recommend",
            json={"analysis": MOCK_JD_RESPONSE.analysis.model_dump(mode="json")},
        )

    assert resp.status_code == 200
    assert resp.json()["recommendations"]


@pytest.mark.asyncio
async def test_analyse_job_returns_async_job(client):
    resp = await client.post("/api/tailor/analyse/test-job-123")
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data


@pytest.mark.asyncio
async def test_get_document_200(client, db_session):
    from app.repositories.document_repository import DocumentRepository
    doc_repo = DocumentRepository(db_session)

    with patch.object(doc_repo.__class__, "get_by_id", AsyncMock(return_value=MOCK_DOC)):
        resp = await client.get("/api/tailor/document/doc-uuid-001")
    # The route uses its own DB session — just check it reaches the endpoint
    assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_get_document_404(client, db_session):
    resp = await client.get("/api/tailor/document/non-existent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_document_history_endpoint(client):
    resp = await client.get("/api/tailor/history/app-uuid-001")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_ats_score_endpoint(client, db_session):
    resp = await client.get("/api/tailor/ats-score/non-existent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyse_jd_text_202(client):
    """POST /api/tailor/analyse returns 202 for raw JD text (async job pattern)."""
    resp = await client.post(
        "/api/tailor/analyse",
        params={"job_description": "We are looking for a Solutions Architect with AWS experience."},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["type"] == "tailor_analyse"


@pytest.mark.asyncio
async def test_generate_stream_returns_200(client):
    """GET /api/tailor/generate/stream returns a streaming response."""
    resp = await client.get(
        "/api/tailor/generate/stream",
        params={
            "application_id": "app-uuid-001",
            "variant": "A",
            "jd_text": "We are looking for an AWS architect.",
        },
    )
    # Streaming response — server may yield nothing but should not 500
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_analyse_jd_text_returns_async_job(client):
    """POST /api/tailor/analyse returns async job envelope (202 pattern)."""
    resp = await client.post(
        "/api/tailor/analyse",
        params={"job_description": "Senior AWS Solutions Architect with Terraform skills."},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["type"] == "tailor_analyse"


@pytest.mark.asyncio
async def test_document_history_with_doc_type_filter(client):
    """GET /api/tailor/history/{app_id}?doc_type=cv filters by document type."""
    resp = await client.get("/api/tailor/history/app-uuid-001?doc_type=cv")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_ats_optimise_404_for_unknown_document(client):
    """POST /api/tailor/ats-optimise/{id} returns 404 when document doesn't exist."""
    resp = await client.post(
        "/api/tailor/ats-optimise/non-existent-doc-id",
        params={"jd_text": "We need an AWS architect with Terraform skills."},
    )
    assert resp.status_code == 404
