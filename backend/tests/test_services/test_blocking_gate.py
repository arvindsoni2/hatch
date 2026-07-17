"""G-3 tests — blocking grounding issues withhold document and surface reasons."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.schemas.tailor import TailoredCVResult
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
                result = await svc.generate_cv("app-1", "A", "some jd text", mock_db)

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
