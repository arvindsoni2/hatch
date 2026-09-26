"""Conversational Coach telemetry must remain bounded and content-free."""

from app.observability import attributes as telemetry_attributes
from app.observability.runtime import TelemetryRuntime


def test_state_version_is_trace_only_and_content_is_dropped_from_metrics():
    attrs = {
        telemetry_attributes.COACH_STATE_VERSION: 9,
        telemetry_attributes.COACH_COMMAND_TYPE: "delete_transcript",
        telemetry_attributes.COACH_SESSION_ID: "session-private-1",
        "transcript": "CANARY-TRANSCRIPT-7f2",
    }

    trace_safe = telemetry_attributes.sanitize_attributes(attrs)
    metric_safe = telemetry_attributes.sanitize_metric_attributes(attrs)

    assert trace_safe[telemetry_attributes.COACH_STATE_VERSION] == 9
    assert telemetry_attributes.COACH_STATE_VERSION not in metric_safe
    assert telemetry_attributes.COACH_SESSION_ID not in metric_safe
    assert "transcript" not in metric_safe


def test_conversation_metric_facade_is_fail_open():
    telemetry = TelemetryRuntime(status="disabled")

    telemetry.record_conversation_metric(
        "report",
        1,
        {telemetry_attributes.COACH_STATE_VERSION: 2},
    )
