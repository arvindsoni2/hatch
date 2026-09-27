"""Deterministic synchronous conversational report export contracts."""

import pytest

from app.schemas.coach_conversation import ReportExportRequest
from app.services.coach_report_export import (
    ExportSnapshot,
    export_report,
    render_report_export,
)


def request(format_name: str = "json") -> ReportExportRequest:
    return ReportExportRequest(
        format=format_name,
        expected_activity_version=3,
        expected_retention_version=4,
        include_candidate_reflection=True,
        contract_version="coach_report_export_v1",
    )


@pytest.fixture
def snapshot() -> ExportSnapshot:
    return ExportSnapshot(
        session_id="session-opaque-1",
        report_state="completed",
        activity_version=3,
        retention_version=4,
        report_json={
            "session_level": "developing",
            "dimensions": {"structure": "developing", "clarity": "strong"},
            "retention_summary": {"audio": "retained"},
            "raw_audio_url": "/private/audio.wav",
        },
        retention_summary={
            "attempts": [
                {
                    "attempt_id": "attempt-opaque",
                    "audio_policy": "retain_until_deleted",
                    "audio_state": "deleted",
                    "transcript_state": "retained",
                    "audio_cleanup_retryable": False,
                }
            ]
        },
    )


def test_json_export_is_sorted_stable_and_uses_live_not_persisted_retention(snapshot):
    first = render_report_export(snapshot, request("json"))
    second = render_report_export(snapshot, request("json"))

    assert first.body == second.body
    assert first.etag == second.etag
    assert first.body.endswith(b"\n")
    assert b"raw_audio_url" not in first.body
    import json

    assert json.loads(first.body)["retention_summary"] == snapshot.retention_summary
    assert first.headers()["X-Hatch-Session-Activity-Version"] == "3"
    assert first.headers()["X-Hatch-Retention-Version"] == "4"
    assert first.filename == "coach-report-session-opaque-1.json"


def test_markdown_export_has_fixed_sections_and_no_raw_link(snapshot):
    payload = render_report_export(snapshot, request("markdown"))

    text = payload.body.decode("utf-8")
    assert text.index("## Session level") < text.index("## Dimensions")
    assert "/private/audio.wav" not in text
    assert "## Retention summary" in text
    assert '"audio_state": "deleted"' in text
    assert payload.media_type == "text/markdown; charset=utf-8"


@pytest.mark.asyncio
async def test_export_rechecks_both_source_versions(snapshot):
    class Repository:
        async def load_export_snapshot(self, session_id, request):
            return snapshot

        async def export_versions_match(
            self, session_id, activity_version, retention_version
        ):
            return False

    with pytest.raises(ValueError, match="source_changed"):
        await export_report("session-opaque-1", request(), Repository())
