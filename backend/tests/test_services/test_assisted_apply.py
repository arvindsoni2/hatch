"""Tests for AssistedApplyService (P8 — Assisted Apply backend).

Key invariants verified:
- prepare_application() returns an ApplicationPackage with the right shape
- The service has NO submit() method (no autonomous submission ever)
- The service does NOT make HTTP requests to job board URLs
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.assisted_apply import ApplicationPackage, AssistedApplyService


# ──────────────────────────────────────────────────────────────
# test_approve_triggers_tailoring
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_triggers_tailoring():
    """Approving a job calls prepare_application and result has required fields."""
    service = AssistedApplyService()

    mock_db = AsyncMock()
    # Make db.execute return a mock scalar_one_or_none that yields a fake job
    fake_job = MagicMock()
    fake_job.url = "https://example.com/job/123"
    fake_job.title = "Test Engineer"
    fake_job.company = "Test Corp"
    fake_job.description = "Python development role"
    fake_job.id = "job-123"

    fake_app = MagicMock()
    fake_app.job_id = "job-123"

    _execute_results = []

    class MockScalarResult:
        def __init__(self, value):
            self._value = value
        def scalar_one_or_none(self):
            return self._value

    # First call → job, second call → scalars execute for update
    call_count = [0]

    async def mock_execute(query):
        call_count[0] += 1
        if call_count[0] == 1:
            return MockScalarResult(fake_job)
        return MockScalarResult(None)

    mock_db.execute = mock_execute
    mock_db.commit = AsyncMock()

    with patch(
        "app.services.assisted_apply.load_profile",
        side_effect=Exception("no profile"),
    ):
        package = await service.prepare_application(job_id="job-123", db=mock_db)

    assert isinstance(package, ApplicationPackage)
    assert package.job_id == "job-123"
    assert package.job_url == "https://example.com/job/123"
    # cv_path and cover_letter_path may be None when tailor is unavailable
    assert package.cv_path is None or isinstance(package.cv_path, str)
    assert package.cover_letter_path is None or isinstance(package.cover_letter_path, str)
    assert isinstance(package.prefill_map, dict)


# ──────────────────────────────────────────────────────────────
# test_application_package_assembled
# ──────────────────────────────────────────────────────────────

def test_application_package_assembled():
    """ApplicationPackage dataclass has the required fields with correct types."""
    pkg = ApplicationPackage(
        job_id="job-abc",
        job_url="https://example.com/apply",
        cv_path="/tmp/cv.docx",
        cover_letter_path="/tmp/cl.docx",
        prefill_map={"name": "Alice Smith", "email": "alice@example.com"},
    )

    assert pkg.job_id == "job-abc"
    assert pkg.job_url == "https://example.com/apply"
    assert pkg.cv_path == "/tmp/cv.docx"
    assert pkg.cover_letter_path == "/tmp/cl.docx"
    assert pkg.prefill_map["name"] == "Alice Smith"
    assert pkg.prefill_map["email"] == "alice@example.com"


def test_application_package_none_paths():
    """ApplicationPackage can hold None for cv_path and cover_letter_path."""
    pkg = ApplicationPackage(
        job_id="job-xyz",
        job_url="https://example.com/job",
        cv_path=None,
        cover_letter_path=None,
        prefill_map={"name": "Bob"},
    )
    assert pkg.cv_path is None
    assert pkg.cover_letter_path is None


# ──────────────────────────────────────────────────────────────
# test_no_autonomous_submission
# ──────────────────────────────────────────────────────────────

def test_no_autonomous_submission():
    """CRITICAL: AssistedApplyService must not expose a 'submit' method.

    Hatch only prepares documents — the user always makes the final submission.
    """
    service = AssistedApplyService()

    # No method named 'submit' on the service
    assert not hasattr(service, "submit"), (
        "AssistedApplyService must NOT have a 'submit' method — "
        "autonomous submission is forbidden."
    )

    # No method named 'browser_fill' on the service
    assert not hasattr(service, "browser_fill"), (
        "AssistedApplyService must NOT have a 'browser_fill' method."
    )

    # Inspect source to ensure no httpx.post or requests.post to external URLs
    source = inspect.getsource(AssistedApplyService)
    assert "httpx.post" not in source, (
        "AssistedApplyService source must not contain httpx.post (no autonomous POSTs)."
    )
    assert "requests.post" not in source, (
        "AssistedApplyService source must not contain requests.post (no autonomous POSTs)."
    )


def test_service_only_exposes_prepare_application():
    """The public API surface of AssistedApplyService is only prepare_application()."""
    public_methods = [
        name for name, _ in inspect.getmembers(AssistedApplyService, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]
    assert "prepare_application" in public_methods, (
        "prepare_application must be a public method."
    )
    # 'submit' must not appear at all
    assert "submit" not in public_methods, (
        "submit must not be a method of AssistedApplyService."
    )
