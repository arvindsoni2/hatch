"""Owner-scoped, content-free support diagnostics for conversational Coach."""

from __future__ import annotations

from ..schemas.coach_conversation import SupportDiagnosticsRead
from .coach_conversational_contracts import error_contract


def build_support_diagnostics(
    session, *, error_code: str | None = None
) -> SupportDiagnosticsRead:
    definition = error_contract(error_code) if error_code else None
    return SupportDiagnosticsRead(
        session_id=session.id,
        status=session.status,
        conversation_state=session.conversation_state,
        report_state=session.report_state,
        error_code=error_code,
        retryable=definition.retryable if definition else None,
        contract_version="coach_support_diagnostics_v1",
    )
