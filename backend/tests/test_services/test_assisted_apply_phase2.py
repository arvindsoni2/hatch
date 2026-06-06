"""Phase 2 tests for AssistedApplyService — screening_answers + paste_map.

Iron Law (TDD): every test here was written RED before any production code
changed.  The guardrail test is repeated so CI catches a regression even when
this file runs in isolation.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_mock_db(job_url: str = "https://greenhouse.io/jobs/42") -> MagicMock:
    """Return a minimal AsyncSession mock that yields one fake job."""
    mock_db = MagicMock()

    fake_job = MagicMock()
    fake_job.url = job_url
    fake_job.title = "Senior Engineer"
    fake_job.company = "Acme Corp"
    fake_job.description = "Python, AWS, Kubernetes role"
    fake_job.id = "job-123"

    class _ScalarResult:
        def __init__(self, v):
            self._v = v

        def scalar_one_or_none(self):
            return self._v

    _call = [0]

    async def _execute(q):
        _call[0] += 1
        return _ScalarResult(fake_job if _call[0] == 1 else None)

    mock_db.execute = _execute
    mock_db.commit = AsyncMock()
    return mock_db


# ─────────────────────────────────────────────────────────────────────────────
# ApplicationPackage — new fields
# ─────────────────────────────────────────────────────────────────────────────


class TestApplicationPackageExtended:
    """ApplicationPackage dataclass must expose screening_answers and paste_map."""

    def test_package_has_screening_answers_field(self):
        """ApplicationPackage accepts a screening_answers dict."""
        from app.services.assisted_apply import ApplicationPackage

        pkg = ApplicationPackage(
            job_id="j1",
            job_url="https://example.com",
            cv_path=None,
            cover_letter_path=None,
            prefill_map={},
            screening_answers={"work_authorisation": "British Citizen"},
        )
        assert pkg.screening_answers == {"work_authorisation": "British Citizen"}

    def test_package_has_paste_map_field(self):
        """ApplicationPackage accepts a paste_map dict."""
        from app.services.assisted_apply import ApplicationPackage

        pkg = ApplicationPackage(
            job_id="j1",
            job_url="https://example.com",
            cv_path=None,
            cover_letter_path=None,
            prefill_map={},
            paste_map={"First Name": "Arvind"},
        )
        assert pkg.paste_map == {"First Name": "Arvind"}

    def test_screening_answers_defaults_to_empty_dict(self):
        """Omitting screening_answers defaults to {}."""
        from app.services.assisted_apply import ApplicationPackage

        pkg = ApplicationPackage(
            job_id="j2",
            job_url="https://example.com",
            cv_path=None,
            cover_letter_path=None,
            prefill_map={},
        )
        assert pkg.screening_answers == {}

    def test_paste_map_defaults_to_empty_dict(self):
        """Omitting paste_map defaults to {}."""
        from app.services.assisted_apply import ApplicationPackage

        pkg = ApplicationPackage(
            job_id="j2",
            job_url="https://example.com",
            cv_path=None,
            cover_letter_path=None,
            prefill_map={},
        )
        assert pkg.paste_map == {}


# ─────────────────────────────────────────────────────────────────────────────
# prepare_application — screening answers assembly
# ─────────────────────────────────────────────────────────────────────────────


class TestPrepareApplicationScreeningAnswers:
    """prepare_application must return screening_answers populated from the
    screening-answers skill resources."""

    @pytest.mark.asyncio
    async def test_prepare_application_returns_screening_answers_dict(self):
        """package.screening_answers is always a dict (may be empty)."""
        from app.services.assisted_apply import AssistedApplyService

        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", side_effect=Exception("no profile")):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        assert isinstance(package.screening_answers, dict)

    @pytest.mark.asyncio
    async def test_prepare_application_includes_uk_knockout_keys(self):
        """When profile locale is 'uk', screening_answers has at least
        work_authorisation and notice_period keys (populated from knockout_patterns.yaml)."""
        from app.services.assisted_apply import AssistedApplyService

        mock_profile = MagicMock()
        mock_profile.preferences = MagicMock()
        mock_profile.preferences.locale = "en-GB"
        mock_profile.candidate = MagicMock()
        mock_profile.candidate.name = "Arvind Soni"
        mock_profile.candidate.email = "arvind@example.com"
        mock_profile.candidate.phone = "+44 7700 900000"
        mock_profile.compensation = MagicMock()
        mock_profile.compensation.min_rate = 550
        mock_profile.compensation.max_rate = 700
        mock_profile.compensation.currency = "GBP"

        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=mock_profile):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        assert "work_authorisation" in package.screening_answers
        assert "notice_period" in package.screening_answers

    @pytest.mark.asyncio
    async def test_prepare_application_screening_answers_are_strings(self):
        """Every value in screening_answers is a non-empty string."""
        from app.services.assisted_apply import AssistedApplyService

        mock_profile = MagicMock()
        mock_profile.preferences = MagicMock()
        mock_profile.preferences.locale = "en-GB"
        mock_profile.candidate = MagicMock()
        mock_profile.candidate.name = "Arvind"
        mock_profile.candidate.email = None
        mock_profile.candidate.phone = None
        mock_profile.compensation = MagicMock()
        mock_profile.compensation.min_rate = 500
        mock_profile.compensation.max_rate = 600
        mock_profile.compensation.currency = "GBP"

        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=mock_profile):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        for key, val in package.screening_answers.items():
            assert isinstance(val, str), f"screening_answers[{key!r}] must be str, got {type(val)}"
            assert val, f"screening_answers[{key!r}] must not be empty"


# ─────────────────────────────────────────────────────────────────────────────
# prepare_application — paste map assembly
# ─────────────────────────────────────────────────────────────────────────────


class TestPrepareApplicationPasteMap:
    """prepare_application must return paste_map for known ATS job URLs."""

    @pytest.mark.asyncio
    async def test_prepare_application_returns_paste_map_dict(self):
        """package.paste_map is always a dict."""
        from app.services.assisted_apply import AssistedApplyService

        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", side_effect=Exception("no profile")):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        assert isinstance(package.paste_map, dict)

    @pytest.mark.asyncio
    async def test_paste_map_populated_for_greenhouse_url(self):
        """When job URL contains 'greenhouse.io', paste_map has form-field labels."""
        from app.services.assisted_apply import AssistedApplyService

        mock_profile = MagicMock()
        mock_profile.preferences = MagicMock()
        mock_profile.preferences.locale = "en-GB"
        mock_profile.candidate = MagicMock()
        mock_profile.candidate.name = "Arvind Soni"
        mock_profile.candidate.email = "arvind@example.com"
        mock_profile.candidate.phone = "+44 7700 900000"
        mock_profile.compensation = MagicMock()
        mock_profile.compensation.min_rate = 550
        mock_profile.compensation.max_rate = 700
        mock_profile.compensation.currency = "GBP"

        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=mock_profile):
            package = await service.prepare_application(
                job_id="job-123",
                db=_make_mock_db(job_url="https://boards.greenhouse.io/acme/jobs/42"),
            )
        assert len(package.paste_map) > 0, "paste_map should be non-empty for Greenhouse URLs"

    @pytest.mark.asyncio
    async def test_paste_map_empty_for_unknown_ats(self):
        """When job URL does not match any known ATS, paste_map is {}."""
        from app.services.assisted_apply import AssistedApplyService

        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", side_effect=Exception("no profile")):
            package = await service.prepare_application(
                job_id="job-123",
                db=_make_mock_db(job_url="https://careers.acme.com/apply/123"),
            )
        assert package.paste_map == {}


# ─────────────────────────────────────────────────────────────────────────────
# Permanent guardrail — must never regress
# ─────────────────────────────────────────────────────────────────────────────


def test_no_autonomous_submission_guardrail():
    """PERMANENT: AssistedApplyService must not have submit() or browser_fill().
    Re-tested here so this file alone can catch a regression."""
    from app.services.assisted_apply import AssistedApplyService

    service = AssistedApplyService()
    assert not hasattr(service, "submit"), (
        "AssistedApplyService must NOT have a 'submit' method."
    )
    assert not hasattr(service, "browser_fill"), (
        "AssistedApplyService must NOT have a 'browser_fill' method."
    )
    source = inspect.getsource(AssistedApplyService)
    assert "httpx.post" not in source
    assert "requests.post" not in source
