"""H3 file and path boundary contract.

The tests cover the shared path helper, both DOCX builders, Coach audio
publication, the shadow-mode DOCX append, and the digest env-file writer.
"""
from __future__ import annotations

import logging
import os
import shutil
import stat
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.models.async_job import AsyncJob
from app.models.coach_session import InterviewSession, SessionQuestion, SessionRecording
from app.routers import settings as settings_router
from app.runtime import RuntimeMode
from app.schemas.tailor import (
    ATSScoreResult,
    CoverLetterResult,
    JDAnalysisResult,
    TailoredCVResult,
)
from app.services import docx_cl_builder, docx_cv_builder
from app.services.docx_cl_builder import DocxCLBuilder
from app.services.docx_cv_builder import DocxCVBuilder
from app.services.safe_paths import UnsafePathError, require_uuid, resolve_within
from app.services.tailor_service import TailorService

_WAV = (
    b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00"
    b"\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00"
    b"data\x00\x00\x00\x00"
)


def _cv() -> TailoredCVResult:
    return TailoredCVResult(summary="Synthetic summary.")


def _jd() -> JDAnalysisResult:
    return JDAnalysisResult(role_title="Platform Engineer")


def _personal() -> dict[str, str]:
    return {"full_name": "Synthetic Candidate", "email": "candidate@example.test"}


def _cl() -> CoverLetterResult:
    return CoverLetterResult(
        subject_line="Application",
        greeting="Dear Hiring Team,",
        body_paragraphs=["Synthetic body."],
        sign_off="Regards",
        word_count=3,
    )


def _assert_node_available() -> None:
    if shutil.which("node") is None:
        pytest.skip("Node is not available for the real DOCX builder")
    if not (Path(docx_cv_builder._TEMPLATES_DIR) / "node_modules").is_dir():
        pytest.skip("backend/app/templates/node_modules is not installed")


# ---------------------------------------------------------------------------
# Shared helper
# ---------------------------------------------------------------------------


def test_resolve_within_returns_a_path_inside_the_base(tmp_path: Path) -> None:
    base = tmp_path / "generated"

    result = resolve_within(base, "child", "artifact.docx")

    assert result == (base / "child" / "artifact.docx").resolve()
    assert result.is_relative_to(base.resolve())


@pytest.mark.parametrize(
    "parts",
    [
        (),
        ("",),
        ("artifact.docx", ""),
        ("\x00",),
        ("../../outside.docx",),
        ("/etc/passwd",),
        ("C:\\Windows\\System32\\artifact.docx",),
        ("C:artifact.docx",),
        ("..\\..\\outside.docx",),
    ],
)
def test_resolve_within_rejects_unsafe_parts(tmp_path: Path, parts: tuple[str, ...]) -> None:
    base = tmp_path / "generated"

    with pytest.raises(UnsafePathError):
        resolve_within(base, *parts)


def test_resolve_within_rejects_sibling_with_the_same_prefix(tmp_path: Path) -> None:
    base = tmp_path / "generated"
    sibling = tmp_path / "generated-sibling"

    with pytest.raises(UnsafePathError):
        resolve_within(base, "..", sibling.name)

    assert not sibling.exists()


def test_resolve_within_rejects_a_symlink_that_leaves_the_base(tmp_path: Path) -> None:
    base = tmp_path / "generated"
    outside = tmp_path / "outside"
    base.mkdir()
    outside.mkdir()
    (base / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        resolve_within(base, "link", "artifact.docx")


def test_resolve_within_does_not_treat_percent_encoding_as_a_separator(
    tmp_path: Path,
) -> None:
    base = tmp_path / "generated"

    result = resolve_within(base, "%2e%2e%2foutside.docx")

    assert result.is_relative_to(base.resolve())


def test_resolve_within_has_no_file_system_effect(tmp_path: Path) -> None:
    base = tmp_path / "generated"

    with pytest.raises(UnsafePathError):
        resolve_within(base, "..", "outside")

    assert not base.exists()
    assert not (tmp_path / "outside").exists()


def test_require_uuid_returns_a_canonical_lowercase_uuid() -> None:
    value = uuid.uuid4()

    assert require_uuid(str(value).upper(), "application_id") == str(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-uuid",
        "../x",
        "/etc/passwd",
        "C:\\Windows",
        "%2e%2e",
        "a\x00b",
        "1234",
    ],
)
def test_require_uuid_rejects_non_uuid_values(value: str) -> None:
    with pytest.raises(ValueError, match="application_id"):
        require_uuid(value, "application_id")


# ---------------------------------------------------------------------------
# DOCX builders
# ---------------------------------------------------------------------------

_BUILDERS = [
    pytest.param(DocxCVBuilder, docx_cv_builder, _cv, "cv_v1_A.docx", id="cv"),
    pytest.param(DocxCLBuilder, docx_cl_builder, _cl, "cl_v1_A.docx", id="cl"),
]


def _build(builder_cls, payload, application_id, version=1, variant="A"):
    return builder_cls().build(
        payload(), _jd(), _personal(), application_id, version, variant
    )


@pytest.mark.parametrize("builder_cls,module,payload,artifact", _BUILDERS)
def test_builder_rejects_a_sibling_with_the_same_prefix_before_mkdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder_cls,
    module,
    payload,
    artifact: str,
) -> None:
    base = tmp_path / "generated"
    sibling = tmp_path / "generated-sibling"
    monkeypatch.setattr(module, "_OUTPUT_BASE", base)

    with pytest.raises(ValueError):
        _build(builder_cls, payload, "../generated-sibling")

    assert not sibling.exists()


@pytest.mark.parametrize("application_id", ["../x", "not-a-uuid"])
@pytest.mark.parametrize("builder_cls,module,payload,artifact", _BUILDERS)
def test_builder_rejects_relative_and_non_uuid_ids_before_mkdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder_cls,
    module,
    payload,
    artifact: str,
    application_id: str,
) -> None:
    base = tmp_path / "generated"
    monkeypatch.setattr(module, "_OUTPUT_BASE", base)
    expected = tmp_path / "x" if application_id == "../x" else base / application_id

    with pytest.raises(ValueError):
        _build(builder_cls, payload, application_id)

    assert not expected.exists()


@pytest.mark.parametrize("builder_cls,module,payload,artifact", _BUILDERS)
def test_builder_rejects_an_absolute_id_before_mkdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder_cls,
    module,
    payload,
    artifact: str,
) -> None:
    base = tmp_path / "generated"
    absolute = tmp_path / "absolute-output"
    monkeypatch.setattr(module, "_OUTPUT_BASE", base)

    with pytest.raises(ValueError):
        _build(builder_cls, payload, str(absolute))

    assert not absolute.exists()


@pytest.mark.parametrize("builder_cls,module,payload,artifact", _BUILDERS)
def test_builder_rejects_a_symlink_escape_before_mkdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder_cls,
    module,
    payload,
    artifact: str,
) -> None:
    base = tmp_path / "generated"
    outside = tmp_path / "generated-outside"
    base.mkdir()
    outside.mkdir()
    application_id = str(uuid.uuid4())
    (base / application_id).symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(module, "_OUTPUT_BASE", base)

    with pytest.raises(ValueError):
        _build(builder_cls, payload, application_id)

    assert not (outside / artifact).exists()


@pytest.mark.parametrize("builder_cls,module,payload,artifact", _BUILDERS)
def test_builder_rejects_unknown_variant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder_cls,
    module,
    payload,
    artifact: str,
) -> None:
    base = tmp_path / "generated"
    application_id = str(uuid.uuid4())
    monkeypatch.setattr(module, "_OUTPUT_BASE", base)

    with pytest.raises(ValueError):
        _build(builder_cls, payload, application_id, variant="C")

    assert not (base / application_id).exists()


@pytest.mark.parametrize("builder_cls,module,payload,artifact", _BUILDERS)
def test_builder_rejects_non_int_version(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    builder_cls,
    module,
    payload,
    artifact: str,
) -> None:
    base = tmp_path / "generated"
    application_id = str(uuid.uuid4())
    monkeypatch.setattr(module, "_OUTPUT_BASE", base)

    with pytest.raises(ValueError):
        _build(builder_cls, payload, application_id, version="1")

    assert not (base / application_id).exists()


def test_cv_builder_valid_uuid_builds_a_real_docx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _assert_node_available()
    base = tmp_path / "generated"
    application_id = str(uuid.uuid4())
    monkeypatch.setattr(docx_cv_builder, "_OUTPUT_BASE", base)

    path, size = DocxCVBuilder().build(
        _cv(), _jd(), _personal(), application_id, 1, "A"
    )

    assert Path(path).is_file()
    assert Path(path).read_bytes().startswith(b"PK")
    assert size > 0


def test_cl_builder_valid_uuid_builds_a_real_docx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _assert_node_available()
    base = tmp_path / "generated"
    application_id = str(uuid.uuid4())
    monkeypatch.setattr(docx_cl_builder, "_OUTPUT_BASE", base)

    path, size = DocxCLBuilder().build(
        _cl(), _jd(), _personal(), application_id, 1, "A"
    )

    assert Path(path).is_file()
    assert Path(path).read_bytes().startswith(b"PK")
    assert size > 0


# ---------------------------------------------------------------------------
# Coach submit-audio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_submit_audio_rejects_non_uuid_session_without_side_effects(
    client, db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    response = await client.post(
        "/api/coach/sessions/not-a-uuid/submit-audio",
        data={"question_id": str(uuid.uuid4())},
        files={"audio": ("answer.wav", _WAV, "audio/wav")},
    )

    assert response.status_code == 400
    assert "session_id" in response.json()["detail"].lower()
    assert not (tmp_path / "recordings").exists()
    assert await db_session.scalar(select(func.count(AsyncJob.id))) == 0
    assert await db_session.scalar(select(func.count(SessionRecording.id))) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question_id",
    ["../x", "a/b", "bad\x00id", "question-1"],
)
async def test_submit_audio_rejects_unsafe_questions_without_side_effects(
    client,
    db_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    question_id: str,
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    session_id = str(uuid.uuid4())

    response = await client.post(
        f"/api/coach/sessions/{session_id}/submit-audio",
        data={"question_id": question_id},
        files={"audio": ("answer.wav", _WAV, "audio/wav")},
    )

    assert response.status_code == 400
    assert "question_id" in response.json()["detail"].lower()
    assert not (tmp_path / "recordings").exists()
    assert await db_session.scalar(select(func.count(AsyncJob.id))) == 0
    assert await db_session.scalar(select(func.count(SessionRecording.id))) == 0


@pytest.mark.asyncio
async def test_submit_audio_accepts_uuid_session_and_question(
    client, db_session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    session_id = str(uuid.uuid4())
    question_id = str(uuid.uuid4())
    db_session.add(
        InterviewSession(
            id=session_id,
            company_name="Synthetic Co",
            role_title="Engineer",
            config={"question_count": 1},
            status="active",
            experience_version="legacy_v1",
        )
    )
    db_session.add(
        SessionQuestion(
            id=question_id,
            session_id=session_id,
            question_num=1,
            text="Synthetic question.",
            category="Behavioural",
            difficulty="medium",
            order_in_session=1,
        )
    )
    await db_session.commit()

    from unittest.mock import patch

    with patch("app.routers.coach.AsyncJobService.run") as run:
        response = await client.post(
            f"/api/coach/sessions/{session_id}/submit-audio",
            data={"question_id": question_id},
            files={"audio": ("answer.wav", _WAV, "audio/wav")},
        )

    assert response.status_code == 202
    assert response.json()["type"] == "submit_audio"
    saved = tmp_path / "recordings" / session_id / f"{question_id}-{response.json()['job_id']}.wav"
    assert saved.is_file()
    run.call_args.args[1].close()


# ---------------------------------------------------------------------------
# Shadow-mode append
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_shadow_append_rejects_a_file_outside_the_output_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session
) -> None:
    base = tmp_path / "generated"
    base.mkdir()
    outside = tmp_path / "outside.docx"
    with zipfile.ZipFile(outside, "w") as archive:
        archive.writestr("marker.txt", "keep")
    before = outside.read_bytes()
    monkeypatch.setattr(docx_cv_builder, "_OUTPUT_BASE", base)

    service = TailorService()
    service._jd_analyser.analyse = lambda _jd_text: _async_value(_jd())  # type: ignore[method-assign]
    service._tailor_and_score = lambda *_args, **_kwargs: _async_value(  # type: ignore[method-assign]
        (_cv(), ATSScoreResult(overall_score=80))
    )
    service._cv_builder.build = lambda *_args, **_kwargs: (  # type: ignore[method-assign]
        str(outside),
        outside.stat().st_size,
    )
    monkeypatch.setattr(
        "app.services.tailor_service._load_personal",
        lambda: _personal(),
    )
    monkeypatch.setattr(
        "app.services.docx_cv_builder._build_cv_spec",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "app.services.cv_tailor._parse_tailored_cv",
        lambda _spec: _cv(),
    )
    monkeypatch.setattr(
        "app.runtime_bindings.migration.cv_tailor.cv_content",
        lambda _rendered: {"synthetic": True},
    )

    class _Repository:
        def __init__(self, _db) -> None:
            pass

        async def get_latest_version(self, *_args) -> int:
            return 0

        async def create(self, **_kwargs) -> SimpleNamespace:
            return SimpleNamespace(id="synthetic-document")

    monkeypatch.setattr("app.services.tailor_service.DocumentRepository", _Repository)

    with pytest.raises(ValueError):
        await service._generate_cv_legacy(
            str(uuid.uuid4()),
            "A",
            "Synthetic job description.",
            db_session,
            template_id="ats_classic",
            runtime_mode=RuntimeMode.SHADOW,
        )

    assert outside.read_bytes() == before
    with zipfile.ZipFile(outside) as archive:
        assert "hatch/cv.json" not in archive.namelist()


async def _async_value(value):
    return value


# ---------------------------------------------------------------------------
# Digest and env-file writes
# ---------------------------------------------------------------------------


def _write_existing_keys(path: Path) -> None:
    path.write_text("OPENAI_API_KEY=existing\n", encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"time": "07:00\r\nDIGEST_ENABLED=false"},
        {"time": "7:00"},
        {"time": "24:00"},
        {"timezone": "Mars/Olympus"},
        {"frequency": "weekly"},
        {"enabled": "true"},
        {"enabled": 1},
    ],
)
async def test_digest_rejects_invalid_values_without_writing(
    client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    env_file = tmp_path / "api_keys.env"
    _write_existing_keys(env_file)
    before = env_file.read_bytes()

    response = await client.patch("/api/digest/settings", json=payload)

    assert response.status_code == 422
    assert env_file.read_bytes() == before


@pytest.mark.asyncio
async def test_digest_valid_update_writes_only_four_keys_with_mode_600(
    client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    env_file = tmp_path / "api_keys.env"

    response = await client.patch(
        "/api/digest/settings",
        json={
            "timezone": "Europe/London",
            "time": "07:30",
            "frequency": "daily",
            "enabled": True,
        },
    )

    assert response.status_code == 200
    lines = [line for line in env_file.read_text(encoding="utf-8").splitlines() if line]
    assert lines == [
        "DIGEST_TIMEZONE=Europe/London",
        "DIGEST_TIME=07:30",
        "DIGEST_FREQUENCY=daily",
        "DIGEST_ENABLED=true",
    ]
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".api_keys.env.*"))


def test_load_env_file_ignores_keys_outside_the_allow_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    for name in (
        "OPENAI_API_KEY",
        "DIGEST_TIME",
        "UNKNOWN_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / "api_keys.env").write_text(
        "OPENAI_API_KEY=allowed-value\n"
        "DIGEST_TIME=08:15\n"
        "UNKNOWN_KEY=ignored-value\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger=settings_router.logger.name):
        settings_router._load_env_file()

    assert os.environ["OPENAI_API_KEY"] == "allowed-value"
    assert os.environ["DIGEST_TIME"] == "08:15"
    assert "UNKNOWN_KEY" not in os.environ
    assert "UNKNOWN_KEY" in caplog.text
    assert "ignored-value" not in caplog.text


def test_env_writer_rejects_control_characters_and_unknown_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    env_file = tmp_path / "api_keys.env"
    _write_existing_keys(env_file)
    before = env_file.read_bytes()
    writer = getattr(settings_router, "write_env_values")

    with pytest.raises(ValueError):
        writer({"OPENAI_API_KEY": "value\nINJECTED=1"})
    with pytest.raises(ValueError):
        writer({"OPENAI_API_KEY": "value\x00tail"})
    with pytest.raises(ValueError):
        writer({"UNKNOWN_KEY": "value"})

    assert env_file.read_bytes() == before


def test_env_writer_atomic_failure_keeps_the_old_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    env_file = tmp_path / "api_keys.env"
    _write_existing_keys(env_file)
    before = env_file.read_bytes()
    writer = getattr(settings_router, "write_env_values")

    def fail_replace(*_args, **_kwargs):
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(settings_router.os, "replace", fail_replace)
    with pytest.raises(OSError):
        writer({"OPENAI_API_KEY": "new"})

    assert env_file.read_bytes() == before
    assert not list(tmp_path.glob(".api_keys.env.*"))


def test_env_writer_sets_mode_600_on_every_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    env_file = tmp_path / "api_keys.env"
    writer = getattr(settings_router, "write_env_values")

    writer({"OPENAI_API_KEY": "first"})
    env_file.chmod(0o644)
    writer({"OPENAI_API_KEY": "second"})

    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert "OPENAI_API_KEY=second" in env_file.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".api_keys.env.*"))
