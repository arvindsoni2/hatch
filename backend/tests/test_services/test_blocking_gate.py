"""G-3 tests — blocking grounding issues withhold document and surface reasons."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.tailor import CoverLetterResult, TailoredCVResult
from app.services.tailor_service import TailorService
from app.services.writing_contracts import (
    CV_TAILORING_PROMPT,
    EVIDENCE_SCHEMA_VERSION,
    GenerationProvenance,
    ValidationResult,
)

_PROFILE_LOADER_TARGET = "app.agents.tools.profile_loader.load_profile"


def _mock_tailored_cv(blocking: list[str], advisory: list[str] | None = None) -> TailoredCVResult:
    return TailoredCVResult(
        summary="A summary without placeholders.",
        skills=[{"category": "Cloud", "items": ["AWS"]}],
        experience=[],
        certifications=[],
        ats_keywords_embedded=[],
        tailoring_notes="notes",
        blocking_issues=blocking,
        fabrication_warnings=advisory or [],
    )


def _clean_tailored_cv() -> TailoredCVResult:
    result = _mock_tailored_cv(blocking=[], advisory=[])
    result.generation_provenance = GenerationProvenance(
        prompt_metadata=CV_TAILORING_PROMPT,
        evidence_schema_version=EVIDENCE_SCHEMA_VERSION,
        source_evidence_ids=("evidence-1",),
        validation=ValidationResult(passed=True, issues=(), metrics={}),
    )
    return result


def _review_required_cover_letter() -> CoverLetterResult:
    return CoverLetterResult(
        subject_line="Application for Engineer",
        greeting="Dear Hiring Manager,",
        body_paragraphs=["Private draft content must not be surfaced."],
        sign_off="Yours sincerely,",
        word_count=248,
        validation_status="review_required",
        validation_issues=[
            "Cover letter body has 248 words; expected 250-350."
        ],
        attempt_count=2,
        repair_count=1,
    )


def _service_with_mocked_master_cv(tmp_path):
    """Return a TailorService with all LLM/DB deps mocked, and a valid master CV file."""
    import json
    cv_file = tmp_path / "master_cv.json"
    cv_file.write_text(json.dumps({
        "personal": {"full_name": "Test User", "email": "test@example.com"},
        "experience": [],
        "skills": {},
        "certifications": [],
        "summary_variants": {"default": "A reliable professional."},
    }))

    mock_profile = MagicMock()
    mock_profile.master_cv_path = str(cv_file)
    return mock_profile


class TestBlockingGateGenerateCV:
    @pytest.mark.asyncio
    async def test_blocking_issues_raise_422(self, tmp_path):
        """generate_cv raises HTTPException 422 when blocking issues present."""
        from app.services.master_cv_store import invalidate_cache
        invalidate_cache()

        mock_profile = _service_with_mocked_master_cv(tmp_path)
        svc = TailorService.__new__(TailorService)
        svc._jd_analyser = AsyncMock()
        svc._cv_tailor = AsyncMock()
        svc._ats_optimiser = AsyncMock()
        svc._cl_generator = AsyncMock()
        svc._cv_builder = MagicMock()
        svc._cl_builder = MagicMock()

        svc._jd_analyser.analyse = AsyncMock(return_value=MagicMock())
        svc._cv_tailor.tailor = AsyncMock(
            return_value=_mock_tailored_cv(
                blocking=["experience.company: placeholder — 'PLACEHOLDER — Company A'"]
            )
        )

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_latest_version = AsyncMock(return_value=0)

        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            with patch("app.services.tailor_service.DocumentRepository", return_value=mock_doc_repo):
                with pytest.raises(HTTPException) as exc_info:
                    await svc.generate_cv("app-1", "A", "some jd text", mock_db)

        assert exc_info.value.status_code == 422
        assert "blocking" in str(exc_info.value.detail).lower() or "grounding" in str(exc_info.value.detail).lower()

    @pytest.mark.asyncio
    async def test_no_docx_written_when_blocking(self, tmp_path):
        """The docx builder is never called when blocking issues are present."""
        from app.services.master_cv_store import invalidate_cache
        invalidate_cache()

        mock_profile = _service_with_mocked_master_cv(tmp_path)
        svc = TailorService.__new__(TailorService)
        svc._jd_analyser = AsyncMock()
        svc._cv_tailor = AsyncMock()
        svc._ats_optimiser = AsyncMock()
        svc._cl_generator = AsyncMock()
        svc._cv_builder = MagicMock()
        svc._cl_builder = MagicMock()

        svc._jd_analyser.analyse = AsyncMock(return_value=MagicMock())
        svc._cv_tailor.tailor = AsyncMock(
            return_value=_mock_tailored_cv(blocking=["placeholder detected"])
        )

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_latest_version = AsyncMock(return_value=0)

        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            with patch("app.services.tailor_service.DocumentRepository", return_value=mock_doc_repo):
                with pytest.raises(HTTPException):
                    await svc.generate_cv("app-1", "A", "some jd text", mock_db)

        svc._cv_builder.build.assert_not_called()

    @pytest.mark.asyncio
    async def test_clean_result_proceeds_to_docx(self, tmp_path):
        """generate_cv does NOT raise when blocking_issues is empty."""
        from app.services.master_cv_store import invalidate_cache
        invalidate_cache()

        mock_profile = _service_with_mocked_master_cv(tmp_path)
        svc = TailorService.__new__(TailorService)
        svc._jd_analyser = AsyncMock()
        svc._cv_tailor = AsyncMock()
        svc._ats_optimiser = AsyncMock()
        svc._cl_generator = AsyncMock()
        svc._cv_builder = MagicMock()
        svc._cv_builder.build = MagicMock(return_value=("/tmp/cv.docx", 1024))
        svc._cl_builder = MagicMock()

        mock_analysis = MagicMock()
        mock_analysis.model_dump = MagicMock(return_value={"role_title": "Engineer"})
        svc._jd_analyser.analyse = AsyncMock(return_value=mock_analysis)
        svc._cv_tailor.tailor = AsyncMock(return_value=_clean_tailored_cv())

        ats_result = MagicMock()
        ats_result.overall_score = 80
        ats_result.model_dump = MagicMock(return_value={})
        svc._ats_optimiser.score = AsyncMock(return_value=ats_result)

        mock_db = AsyncMock()
        mock_doc_repo = AsyncMock()
        mock_doc_repo.get_latest_version = AsyncMock(return_value=0)
        mock_doc = MagicMock()
        mock_doc.id = "doc-1"
        mock_doc_repo.create = AsyncMock(return_value=mock_doc)

        with patch(_PROFILE_LOADER_TARGET, return_value=mock_profile):
            with patch("app.services.tailor_service.DocumentRepository", return_value=mock_doc_repo):
                await svc.generate_cv("app-1", "A", "some jd text", mock_db)

        svc._cv_builder.build.assert_called_once()
        create_kwargs = mock_doc_repo.create.call_args.kwargs
        persisted_params = __import__("json").loads(create_kwargs["tailoring_params"])
        assert (
            persisted_params["generation_provenance"]["prompt_metadata"][
                "prompt_version"
            ]
            == "2.0.0"
        )
        assert persisted_params["generation_provenance"]["source_evidence_ids"] == [
            "evidence-1"
        ]


class TestBlockingGateCoverLetter:
    @pytest.mark.asyncio
    async def test_review_required_letter_is_not_rendered_or_persisted(self):
        svc = TailorService.__new__(TailorService)
        analysis = MagicMock()
        analysis.model_dump.return_value = {"role_title": "Engineer"}
        svc._jd_analyser = MagicMock()
        svc._jd_analyser.analyse = AsyncMock(return_value=analysis)
        svc._tailor_and_score = AsyncMock(
            return_value=(_clean_tailored_cv(), MagicMock())
        )
        svc._cl_generator = MagicMock()
        svc._cl_generator.generate = AsyncMock(
            return_value=_review_required_cover_letter()
        )
        svc._cl_generator.render_document = MagicMock()
        svc._cl_builder = MagicMock()

        db = AsyncMock()
        doc_repo = AsyncMock()

        with (
            patch(
                "app.services.tailor_service.DocumentRepository",
                return_value=doc_repo,
            ),
            patch(
                "app.services.tailor_service._load_personal",
                return_value={"full_name": "Private Person"},
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await svc.generate_cover_letter(
                    "application-1", "A", "job description", db
                )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == {
            "error": "Cover letter failed validation — document withheld.",
            "final_state": "review_required",
            "attempt_count": 2,
            "issues": [
                "Cover letter body has 248 words; expected 250-350."
            ],
        }
        svc._cl_generator.render_document.assert_not_called()
        svc._cl_builder.build.assert_not_called()
        doc_repo.create.assert_not_awaited()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stream_error_has_metadata_but_no_private_content(self):
        svc = TailorService.__new__(TailorService)
        analysis = MagicMock()
        svc._jd_analyser = MagicMock()
        svc._jd_analyser.analyse = AsyncMock(return_value=analysis)
        svc._jd_analyser.compute_skill_match = MagicMock(return_value={})
        svc._tailor_and_score = AsyncMock(
            return_value=(_clean_tailored_cv(), MagicMock())
        )
        svc._cl_generator = MagicMock()
        svc._cl_generator.generate = AsyncMock(
            return_value=_review_required_cover_letter()
        )
        svc._cl_generator.render_document = MagicMock()
        svc._cv_builder = MagicMock()
        svc._cl_builder = MagicMock()
        db = AsyncMock()

        with (
            patch(
                "app.services.tailor_service._load_master_cv",
                return_value={},
            ),
            patch(
                "app.services.tailor_service._load_personal",
                return_value={"full_name": "Private Person"},
            ),
        ):
            events = [
                event
                async for event in svc.stream_progress(
                    "application-1", "A", "job description", db
                )
            ]

        error_event = json.loads(events[-1].removeprefix("data: "))
        detail = json.loads(error_event["message"])
        assert detail["final_state"] == "review_required"
        assert detail["attempt_count"] == 2
        serialized = json.dumps(detail)
        assert "Private draft content" not in serialized
        assert "Private Person" not in serialized
        svc._cl_generator.render_document.assert_not_called()
        svc._cl_builder.build.assert_not_called()
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_package_does_not_render_or_persist_failed_cover_letter(self):
        svc = TailorService.__new__(TailorService)
        analysis = MagicMock()
        analysis.model_dump.return_value = {"role_title": "Engineer"}
        svc._jd_analyser = MagicMock()
        svc._jd_analyser.analyse = AsyncMock(return_value=analysis)
        svc._jd_analyser.compute_skill_match = MagicMock(return_value={})
        ats_result = MagicMock(overall_score=80)
        ats_result.model_dump.return_value = {}
        svc._tailor_and_score = AsyncMock(
            return_value=(_clean_tailored_cv(), ats_result)
        )
        svc._cl_generator = MagicMock()
        svc._cl_generator.generate = AsyncMock(
            return_value=_review_required_cover_letter()
        )
        svc._cl_generator.render_document = MagicMock()
        svc._cv_builder = MagicMock()
        svc._cv_builder.build.return_value = ("/tmp/cv.docx", 1024)
        svc._cl_builder = MagicMock()

        db = AsyncMock()
        doc_repo = AsyncMock()
        doc_repo.get_latest_version = AsyncMock(return_value=0)
        cv_doc = MagicMock(id="cv-document-1")
        doc_repo.create = AsyncMock(return_value=cv_doc)

        with (
            patch(
                "app.services.tailor_service.DocumentRepository",
                return_value=doc_repo,
            ),
            patch(
                "app.services.tailor_service._load_master_cv",
                return_value={},
            ),
            patch(
                "app.services.tailor_service._load_personal",
                return_value={"full_name": "Private Person"},
            ),
        ):
            with pytest.raises(HTTPException):
                await svc.generate_all(
                    "application-1",
                    "A",
                    "job description",
                    db,
                    template_id="ats_classic",
                )

        svc._cl_generator.render_document.assert_not_called()
        svc._cl_builder.build.assert_not_called()
        create_types = [
            call.kwargs["document_type"]
            for call in doc_repo.create.await_args_list
        ]
        assert create_types == ["cv"]
        db.commit.assert_not_awaited()
