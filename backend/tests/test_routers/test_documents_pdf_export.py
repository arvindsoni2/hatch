from __future__ import annotations

from pathlib import Path
import uuid

import pytest
from httpx import AsyncClient

from app.models.application import Application
from app.models.document import GeneratedDocument
from app.models.job import JobPosting


async def _seed_cv_package(db_session, tmp_path: Path) -> tuple[Application, GeneratedDocument]:
    job_id = str(uuid.uuid4())
    application_id = str(uuid.uuid4())
    job = JobPosting(
        id=job_id,
        title="Platform Architect",
        company="Example",
        url="https://example.com/jobs/pdf",
        source="manual",
    )
    application = Application(id=application_id, status="approved", priority="normal", job_id=job.id)
    source_path = tmp_path / "cv.docx"
    source_path.write_bytes(b"docx bytes")
    document = GeneratedDocument(
        application_id=application_id,
        document_type="cv",
        version=1,
        file_path=str(source_path),
        file_size_bytes=source_path.stat().st_size,
        status="generated",
    )
    db_session.add_all([job, application, document])
    await db_session.commit()
    return application, document


@pytest.mark.asyncio
async def test_pdf_export_reports_unavailable_without_converter(
    client: AsyncClient,
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _document = await _seed_cv_package(db_session, tmp_path)
    monkeypatch.setattr("app.services.pdf_export.find_pdf_converter", lambda: None)

    response = await client.post(f"/api/documents/{application.id}/export/pdf")

    assert response.status_code == 503
    assert response.json()["detail"] == "PDF export is not installed in this setup."


@pytest.mark.asyncio
async def test_pdf_export_creates_downloadable_asset_with_mocked_converter(
    client: AsyncClient,
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, document = await _seed_cv_package(db_session, tmp_path)
    monkeypatch.setattr("app.services.pdf_export.find_pdf_converter", lambda: ("libreoffice",))

    async def fake_convert(source_path: Path, output_path: Path, _converter: tuple[str, ...]) -> Path:
        assert source_path == Path(document.file_path)
        output_path.write_bytes(b"%PDF-1.4\nmock cv\n")
        return output_path

    monkeypatch.setattr("app.services.pdf_export.convert_docx_to_pdf", fake_convert)

    response = await client.post(f"/api/documents/{application.id}/export/pdf")

    assert response.status_code == 201
    body = response.json()
    assert body["application_id"] == application.id
    assert body["package_id"] == application.id
    assert body["source_document_id"] == document.id
    assert body["kind"] == "cv"
    assert body["format"] == "pdf"
    assert body["generation_status"] == "completed"

    download = await client.get(f"/api/documents/assets/{body['id']}")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("application/pdf")
    assert download.content.startswith(b"%PDF-1.4")
