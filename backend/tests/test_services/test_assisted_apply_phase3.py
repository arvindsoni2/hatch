"""Phase 3 tests for AssistedApplyService — profile-driven skill resources.

Phase 3 wires actual profile.yaml fields into answer generation:
- CandidateConfig gains email, phone, linkedin_url, current_employer fields
- _resolve_profile_path walks dotted+indexed paths (e.g. 'search.locations[0].city')
- _build_paste_map uses path resolution → linkedin_url, city, current_employer populated
- Workday multi-step steps[].fields[] schema is flattened into one paste_map
- work_authorisation template selected by legal_preferences.work_authorization
- notice_period sourced from legal_preferences.notice_period when present

Iron Law (TDD): every test here written RED before any production code changed.
"""
from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_mock_db(job_url: str = "https://boards.greenhouse.io/acme/jobs/42") -> MagicMock:
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


def _make_uk_profile(
    *,
    linkedin_url: str = "",
    current_employer: str = "",
    city: str = "Newcastle upon tyne",
    remote_pref: str = "hybrid",
    work_authorization: str = "",
    notice_period: str = "",
    name: str = "Arvind Soni",
    email: str = "arvind@example.com",
    phone: str = "+44 7700 900000",
) -> MagicMock:
    """Build a MagicMock profile with all fields Phase 3 tests need."""
    profile = MagicMock()
    profile.preferences = MagicMock()
    profile.preferences.locale = "en-GB"

    profile.candidate = MagicMock()
    profile.candidate.name = name
    profile.candidate.email = email
    profile.candidate.phone = phone
    profile.candidate.linkedin_url = linkedin_url
    profile.candidate.current_employer = current_employer

    mock_loc = MagicMock()
    mock_loc.city = city
    mock_loc.remote_preference = remote_pref
    profile.search = MagicMock()
    profile.search.locations = [mock_loc]

    profile.compensation = MagicMock()
    profile.compensation.min_rate = 550
    profile.compensation.max_rate = 700
    profile.compensation.currency = "GBP"

    legal_prefs: dict = {}
    if work_authorization:
        legal_prefs["work_authorization"] = work_authorization
    if notice_period:
        legal_prefs["notice_period"] = notice_period
    profile.compensation.legal_preferences = legal_prefs

    return profile


# ─────────────────────────────────────────────────────────────────────────────
# CandidateConfig schema extension
# ─────────────────────────────────────────────────────────────────────────────


class TestCandidateConfigExtended:
    """CandidateConfig must gain email, phone, linkedin_url, current_employer fields."""

    def test_candidate_config_accepts_email_field(self):
        """CandidateConfig has an email field that defaults to empty string."""
        from app.schemas.profile import CandidateConfig

        cfg = CandidateConfig(email="arvind@example.com")
        assert cfg.email == "arvind@example.com"

    def test_candidate_config_email_defaults_to_empty_string(self):
        """CandidateConfig.email defaults to '' when not provided."""
        from app.schemas.profile import CandidateConfig

        cfg = CandidateConfig()
        assert cfg.email == ""

    def test_candidate_config_accepts_phone_field(self):
        """CandidateConfig has a phone field."""
        from app.schemas.profile import CandidateConfig

        cfg = CandidateConfig(phone="+44 7700 900000")
        assert cfg.phone == "+44 7700 900000"

    def test_candidate_config_accepts_linkedin_url_field(self):
        """CandidateConfig has a linkedin_url field."""
        from app.schemas.profile import CandidateConfig

        cfg = CandidateConfig(linkedin_url="https://linkedin.com/in/arvindsoni")
        assert cfg.linkedin_url == "https://linkedin.com/in/arvindsoni"

    def test_candidate_config_accepts_current_employer_field(self):
        """CandidateConfig has a current_employer field."""
        from app.schemas.profile import CandidateConfig

        cfg = CandidateConfig(current_employer="TechCorp Ltd")
        assert cfg.current_employer == "TechCorp Ltd"


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_profile_path
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveProfilePath:
    """_resolve_profile_path walks dotted+indexed paths on a profile-like object."""

    def _ns(self) -> object:
        """Build a simple namespace that mimics the relevant profile shape."""
        loc = types.SimpleNamespace(city="Newcastle upon tyne", remote_preference="hybrid")
        search = types.SimpleNamespace(locations=[loc])
        candidate = types.SimpleNamespace(
            name="Arvind Soni",
            email="arvind@example.com",
            linkedin_url="https://linkedin.com/in/arvindsoni",
            current_employer="TechCorp",
        )
        return types.SimpleNamespace(candidate=candidate, search=search)

    def test_resolves_simple_dotted_path(self):
        """'candidate.email' resolves to the email string."""
        from app.services.assisted_apply import _resolve_profile_path

        profile = self._ns()
        assert _resolve_profile_path(profile, "candidate.email") == "arvind@example.com"

    def test_resolves_indexed_list_path(self):
        """'search.locations[0].city' resolves to the city string."""
        from app.services.assisted_apply import _resolve_profile_path

        profile = self._ns()
        assert _resolve_profile_path(profile, "search.locations[0].city") == "Newcastle upon tyne"

    def test_resolves_linkedin_url_path(self):
        """'candidate.linkedin_url' resolves to the URL string."""
        from app.services.assisted_apply import _resolve_profile_path

        profile = self._ns()
        assert _resolve_profile_path(profile, "candidate.linkedin_url").startswith("https://")

    def test_returns_empty_string_for_missing_attribute(self):
        """Non-existent attribute returns '' rather than raising."""
        from app.services.assisted_apply import _resolve_profile_path

        profile = self._ns()
        assert _resolve_profile_path(profile, "candidate.nationality") == ""

    def test_returns_empty_string_for_out_of_bounds_index(self):
        """Index beyond list length returns '' rather than raising."""
        from app.services.assisted_apply import _resolve_profile_path

        profile = self._ns()
        assert _resolve_profile_path(profile, "search.locations[5].city") == ""


# ─────────────────────────────────────────────────────────────────────────────
# paste_map — extended field resolution via profile paths
# ─────────────────────────────────────────────────────────────────────────────


class TestPasteMapProfilePathResolution:
    """paste_map must include fields that require path resolution not available in Phase 2."""

    @pytest.mark.asyncio
    async def test_paste_map_includes_linkedin_url_for_greenhouse(self):
        """When profile.candidate.linkedin_url is set, paste_map has 'LinkedIn Profile'."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile(linkedin_url="https://linkedin.com/in/arvindsoni")
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123",
                db=_make_mock_db("https://boards.greenhouse.io/acme/jobs/42"),
            )
        assert "LinkedIn Profile" in package.paste_map, (
            "paste_map should include LinkedIn Profile when profile.candidate.linkedin_url is set"
        )
        assert package.paste_map["LinkedIn Profile"] == "https://linkedin.com/in/arvindsoni"

    @pytest.mark.asyncio
    async def test_paste_map_includes_location_city_from_profile(self):
        """When profile.search.locations[0].city is set, paste_map has 'Current Location'."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile(city="Newcastle upon tyne")
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123",
                db=_make_mock_db("https://boards.greenhouse.io/acme/jobs/42"),
            )
        assert "Current Location" in package.paste_map, (
            "paste_map should include Current Location resolved from search.locations[0].city"
        )

    @pytest.mark.asyncio
    async def test_paste_map_includes_current_company_for_lever(self):
        """When profile.candidate.current_employer is set, Lever paste_map has 'Current Company'."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile(current_employer="Acme Ltd")
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123",
                db=_make_mock_db("https://jobs.lever.co/acme/123"),
            )
        assert "Current Company" in package.paste_map, (
            "paste_map should include Current Company resolved from candidate.current_employer"
        )
        assert package.paste_map["Current Company"] == "Acme Ltd"

    @pytest.mark.asyncio
    async def test_paste_map_workday_multi_step_is_non_empty(self):
        """Workday multi-step schema (steps[].fields[]) is flattened; paste_map is non-empty."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile()
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123",
                db=_make_mock_db("https://acme.myworkday.com/acme/d/apply/job/123"),
            )
        assert len(package.paste_map) > 0, (
            "Workday paste_map should be non-empty after multi-step schema is flattened"
        )


# ─────────────────────────────────────────────────────────────────────────────
# screening_answers — profile-driven work_auth + notice_period
# ─────────────────────────────────────────────────────────────────────────────


class TestScreeningAnswersProfileDriven:
    """screening_answers must use profile.compensation.legal_preferences for
    work_authorisation template selection and notice_period override."""

    @pytest.mark.asyncio
    async def test_work_auth_uses_british_citizen_template(self):
        """work_authorization: 'british_citizen' → answer contains 'British Citizen'."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile(work_authorization="british_citizen")
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        answer = package.screening_answers.get("work_authorisation", "")
        assert "British Citizen" in answer, (
            f"Expected 'British Citizen' in work_authorisation answer, got: {answer!r}"
        )

    @pytest.mark.asyncio
    async def test_work_auth_uses_eu_settled_template(self):
        """work_authorization: 'eu_settled' → answer contains 'EU Settled Status'."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile(work_authorization="eu_settled")
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        answer = package.screening_answers.get("work_authorisation", "")
        assert "EU Settled" in answer, (
            f"Expected 'EU Settled Status' in work_authorisation answer, got: {answer!r}"
        )

    @pytest.mark.asyncio
    async def test_notice_period_sourced_from_legal_preferences(self):
        """When legal_preferences.notice_period is set, notice_period answer uses that value."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile(notice_period="1 month")
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        answer = package.screening_answers.get("notice_period", "")
        assert "1 month" in answer, (
            f"Expected '1 month' in notice_period answer, got: {answer!r}"
        )

    @pytest.mark.asyncio
    async def test_notice_period_falls_back_to_default_when_not_set(self):
        """When legal_preferences has no notice_period, answer is the YAML default."""
        from app.services.assisted_apply import AssistedApplyService

        profile = _make_uk_profile(notice_period="")
        service = AssistedApplyService()
        with patch("app.services.assisted_apply.load_profile", return_value=profile):
            package = await service.prepare_application(
                job_id="job-123", db=_make_mock_db()
            )
        answer = package.screening_answers.get("notice_period", "")
        assert answer, "notice_period answer should not be empty even when legal_preferences is empty"
        assert "Immediately" in answer or "available" in answer.lower(), (
            f"Expected fallback default answer, got: {answer!r}"
        )
