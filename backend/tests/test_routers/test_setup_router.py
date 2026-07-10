from __future__ import annotations

from pathlib import Path
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.app_lock import AppLockConfig
from app.models.application import Application
from app.models.company_watchlist import CompanyWatchlistItem
from app.models.document import GeneratedDocument
from app.models.document_asset import GeneratedDocumentAsset
from app.models.job import JobPosting
from app.models.question_bank import QuestionBankItem
from app.routers import setup


@pytest.mark.asyncio
async def test_setup_status_composes_experience_capabilities_and_hardware(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    (tmp_path / "backend_capabilities.json").write_text(
        '{"schema_version":1,"profile":"core","enabled":[],"updated_by":"test"}'
    )
    (tmp_path / "hardware_probe_latest.json").write_text(
        '{"sanitised":true,"captured_at":"2026-07-10T10:00:00Z","memory":{"total_gb":16},"storage":{"models_dir_free_gb":24},"platform":{"os_family":"windows","arch":"x86_64"}}'
    )

    await setup.set_experience({
        "experience": "custom",
        "ai_mode": "cloud",
        "backend_profile": "browser",
        "provider": "openrouter",
        "provider_metadata": {"model": "openai/gpt-4o-mini"},
    })
    status = await setup.setup_status()

    assert status["schema_version"] == 1
    assert status["experience"] == "custom"
    assert status["ai"]["mode"] == "cloud"
    assert status["ai"]["provider"] == "openrouter"
    assert status["ai"]["configured"] is False
    assert status["capabilities"]["profile"] == "core"
    assert status["capabilities"]["available_profiles"] == ["core", "browser", "local-embeddings", "full"]
    assert status["hardware"]["status"] == "supported_with_limitations"
    assert status["hardware"]["recommendation"]["recommended_ai_modes"] == ["cloud", "ai-later"]
    assert status["operation"]["host_action_required"] is True
    assert status["operation"]["command"] == "hatch capabilities enable browser"


@pytest.mark.asyncio
async def test_experience_endpoint_rejects_unsupported_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    with pytest.raises(setup.HTTPException) as error:
        await setup.set_experience({"experience": "full_ai", "backend_profile": "perception"})

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_cloud_endpoint_rejects_secret_fields() -> None:
    with pytest.raises(setup.HTTPException) as error:
        await setup.select_cloud_provider({"provider": "openai", "api_key": "secret"})

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_cloud_endpoint_canonicalizes_google_alias(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    response = await setup.select_cloud_provider({"provider": "google_gemini"})

    assert response["intent"]["provider"] == "google_genai"
    assert response["next_command"] == "hatch secrets set google_genai"


@pytest.mark.asyncio
async def test_cloud_endpoint_accepts_openrouter_model_without_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    response = await setup.select_cloud_provider({
        "provider": "openrouter",
        "provider_metadata": {"model": "openai/gpt-4o-mini"},
    })

    assert response["intent"]["provider"] == "openrouter"
    assert response["intent"]["provider_metadata"] == {"model": "openai/gpt-4o-mini"}
    assert response["next_command"] == "hatch secrets set openrouter"


@pytest.mark.asyncio
async def test_cloud_endpoint_rejects_unknown_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    with pytest.raises(setup.HTTPException) as error:
        await setup.select_cloud_provider({"provider": "made_up"})

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_hardware_endpoint_gives_host_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    response = await setup.setup_hardware()

    assert response == {
        "detected": False,
        "message": "Hardware not detected yet.",
        "next_command": "hatch probe",
    }


@pytest.mark.asyncio
async def test_hardware_post_gives_safe_cli_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))

    response = await setup.refresh_hardware_probe()

    assert response == {
        "started": False,
        "detected": False,
        "message": "Run hatch probe from the host, then refresh this page.",
        "next_command": "hatch probe",
    }


@pytest.mark.asyncio
async def test_capabilities_endpoint_reports_openrouter_missing_secret(
    client: AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    await setup.select_cloud_provider({"provider": "openrouter"})

    response = await client.get("/api/setup/capabilities")

    assert response.status_code == 200
    capabilities = {item["id"]: item for item in response.json()["capabilities"]}
    assert capabilities["openrouter_provider"]["status"] == "needs_setup"
    assert capabilities["openrouter_provider"]["requiresSecret"] is True
    assert capabilities["openrouter_provider"]["docsCommand"] == "hatch secrets set openrouter"


@pytest.mark.asyncio
async def test_capabilities_endpoint_reports_pdf_export_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(setup, "pdf_export_capability", lambda: {
        "available": False,
        "status": "unavailable",
        "message": "PDF export is not installed in this setup.",
    })

    response = await client.get("/api/setup/capabilities")

    assert response.status_code == 200
    capabilities = {item["id"]: item for item in response.json()["capabilities"]}
    assert capabilities["document_generation_pdf"]["status"] == "unavailable"
    assert capabilities["document_generation_pdf"]["message"] == "PDF export is not installed in this setup."


@pytest.mark.asyncio
async def test_provider_test_reports_missing_openrouter_secret(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    response = await setup.test_provider_connection({
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
    })

    assert response == {
        "ok": False,
        "status": "missing_secret",
        "error": "OPENROUTER_API_KEY is not configured.",
        "next_command": "hatch secrets set openrouter",
    }


@pytest.mark.asyncio
async def test_reset_preview_reports_preserved_secrets_and_clearable_data(
    client: AsyncClient,
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "api_keys.env").write_text("OPENAI_API_KEY=kept\n")
    (tmp_path / "profile.yaml.example").write_text("candidate:\n  name: ''\n")
    (tmp_path / "profile.yaml").write_text("candidate:\n  name: Existing User\n")
    (tmp_path / "master_cv.json").write_text('{"name":"Existing User"}\n')
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "cv.docx").write_text("docx")

    db_session.add(
        JobPosting(
            title="Cloud Architect",
            company="Example",
            url="https://example.com/job",
            source="manual",
        )
    )
    db_session.add(
        CompanyWatchlistItem(
            company_name="Example",
            careers_url="https://example.com/careers",
            source_type="generic_careers_page",
        )
    )
    db_session.add(
        QuestionBankItem(
            type="interview_question",
            title="Tell me about delivery risk",
            answer_draft="I surface risk early and align owners.",
            source="manual",
            confidence="draft",
        )
    )
    await db_session.commit()

    response = await client.get("/api/setup/reset/preview?mode=onboarding")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "onboarding"
    assert body["can_apply"] is True
    assert "api_keys.env" in body["preserves"]
    assert "job_postings" in body["deletes"]
    assert "company_watchlist_items" in body["deletes"]
    assert "question_bank_items" in body["deletes"]
    assert body["counts"]["database"]["job_postings"] == 1
    assert body["counts"]["database"]["company_watchlist_items"] == 1
    assert body["counts"]["database"]["question_bank_items"] == 1
    assert body["counts"]["files"]["master_cv.json"] == 1
    assert body["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_reset_apply_clears_workspace_data_but_preserves_app_lock_and_secrets(
    client: AsyncClient,
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "api_keys.env").write_text("OPENAI_API_KEY=kept\n")
    (tmp_path / "profile.yaml.example").write_text("candidate:\n  name: ''\n")
    (tmp_path / "profile.yaml").write_text("candidate:\n  name: Existing User\n")
    (tmp_path / "master_cv.json").write_text('{"name":"Existing User"}\n')
    (tmp_path / "master_cv.meta.json").write_text("{}\n")
    (tmp_path / "master_resume.txt").write_text("resume")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "cv.docx").write_text("docx")
    (tmp_path / "generated" / "cv.pdf").write_text("pdf")

    app_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    job = JobPosting(
        title="Cloud Architect",
        company="Example",
        url="https://example.com/job",
        source="manual",
    )
    app = Application(id=app_id, status="discovered", priority="normal")
    document = GeneratedDocument(
        id=document_id,
        application_id=app_id,
        document_type="cv",
        version=1,
        file_path=str(tmp_path / "generated" / "cv.docx"),
        status="generated",
    )
    document_asset = GeneratedDocumentAsset(
        application_id=app_id,
        package_id=app_id,
        source_document_id=document_id,
        kind="cv",
        format="pdf",
        path_or_blob_ref=str(tmp_path / "generated" / "cv.pdf"),
        generation_status="completed",
    )
    watchlist_item = CompanyWatchlistItem(
        company_name="Example",
        careers_url="https://example.com/careers",
        source_type="generic_careers_page",
    )
    question_bank_item = QuestionBankItem(
        type="interview_question",
        title="Tell me about delivery risk",
        answer_draft="I surface risk early and align owners.",
        source="manual",
        confidence="draft",
    )
    lock = AppLockConfig(id=1, password_hash="hash")
    db_session.add_all([job, app, document, document_asset, watchlist_item, question_bank_item, lock])
    await db_session.commit()

    response = await client.post(
        "/api/setup/reset/apply",
        json={"mode": "onboarding", "confirmation": "RESET"},
    )

    assert response.status_code == 200
    assert response.json()["applied"] is True
    assert await db_session.scalar(select(func.count()).select_from(JobPosting)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Application)) == 0
    assert await db_session.scalar(select(func.count()).select_from(GeneratedDocumentAsset)) == 0
    assert await db_session.scalar(select(func.count()).select_from(CompanyWatchlistItem)) == 0
    assert await db_session.scalar(select(func.count()).select_from(QuestionBankItem)) == 0
    assert (await db_session.get(AppLockConfig, 1)).password_hash == "hash"
    assert (tmp_path / "api_keys.env").read_text() == "OPENAI_API_KEY=kept\n"
    assert (tmp_path / "profile.yaml").read_text() == "candidate:\n  name: ''\n"
    assert not (tmp_path / "master_cv.json").exists()
    assert not (tmp_path / "master_cv.meta.json").exists()
    assert not (tmp_path / "master_resume.txt").exists()
    assert not (tmp_path / "generated" / "cv.docx").exists()
    assert not (tmp_path / "generated" / "cv.pdf").exists()


@pytest.mark.asyncio
async def test_reset_apply_can_preserve_profile_and_master_cv_files(
    client: AsyncClient,
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    (tmp_path / "profile.yaml").write_text("candidate:\n  name: Existing User\n")
    (tmp_path / "master_cv.json").write_text('{"name":"Existing User"}\n')
    (tmp_path / "master_resume.pdf").write_text("pdf")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "cv.docx").write_text("docx")
    db_session.add(Application(status="discovered", priority="normal"))
    await db_session.commit()

    response = await client.post(
        "/api/setup/reset/apply",
        json={
            "mode": "onboarding",
            "confirmation": "RESET",
            "preserve_profile": True,
        },
    )

    assert response.status_code == 200
    assert await db_session.scalar(select(func.count()).select_from(Application)) == 0
    assert (tmp_path / "profile.yaml").read_text() == "candidate:\n  name: Existing User\n"
    assert (tmp_path / "master_cv.json").exists()
    assert (tmp_path / "master_resume.pdf").exists()
    assert not (tmp_path / "generated" / "cv.docx").exists()
