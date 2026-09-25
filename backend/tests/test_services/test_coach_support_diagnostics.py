"""Content-free support diagnostics use the canonical Coach error registry."""

from app.services.coach_conversational_contracts import error_contract


def test_support_diagnostics_use_registry_safe_error_metadata() -> None:
    definition = error_contract("coach_progress_incompatible_session")

    assert definition.http_status == 409
    assert definition.retryable is False
    assert "session" in definition.message.lower()
