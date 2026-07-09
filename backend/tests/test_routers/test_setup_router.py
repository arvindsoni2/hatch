from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.app_lock import AppLockConfig
from app.models.application import Application
from app.models.job import JobPosting
from app.routers import setup


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
    await db_session.commit()

    response = await client.get("/api/setup/reset/preview?mode=onboarding")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "onboarding"
    assert body["can_apply"] is True
    assert "api_keys.env" in body["preserves"]
    assert "job_postings" in body["deletes"]
    assert body["counts"]["database"]["job_postings"] == 1
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

    job = JobPosting(
        title="Cloud Architect",
        company="Example",
        url="https://example.com/job",
        source="manual",
    )
    app = Application(status="discovered", priority="normal")
    lock = AppLockConfig(id=1, password_hash="hash")
    db_session.add_all([job, app, lock])
    await db_session.commit()

    response = await client.post(
        "/api/setup/reset/apply",
        json={"mode": "onboarding", "confirmation": "RESET"},
    )

    assert response.status_code == 200
    assert response.json()["applied"] is True
    assert await db_session.scalar(select(func.count()).select_from(JobPosting)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Application)) == 0
    assert (await db_session.get(AppLockConfig, 1)).password_hash == "hash"
    assert (tmp_path / "api_keys.env").read_text() == "OPENAI_API_KEY=kept\n"
    assert (tmp_path / "profile.yaml").read_text() == "candidate:\n  name: ''\n"
    assert not (tmp_path / "master_cv.json").exists()
    assert not (tmp_path / "master_cv.meta.json").exists()
    assert not (tmp_path / "master_resume.txt").exists()
    assert not (tmp_path / "generated" / "cv.docx").exists()


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
