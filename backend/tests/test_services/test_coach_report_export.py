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
    assert first.filename == "hatch-coach-session-opaque-1.json"
    assert first.media_type == "application/json; charset=utf-8"


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


@pytest.mark.parametrize("format_name", ["json", "markdown"])
@pytest.mark.parametrize("flags", range(16))
def test_export_include_flags_apply_independently_in_both_formats(format_name, flags):
    import json

    source = ExportSnapshot(
        session_id='opaque/"\r\nInjected: true', report_state="completed",
        activity_version=3, retention_version=4,
        report_json={"session_level": "strong", "candidate_reflection": {"note": "REFLECTION-CANARY"}},
        transcript=({"transcript": "TRANSCRIPT-CANARY", "audio_uri": "PRIVATE-AUDIO"},),
        evidence_details=({"snapshot_text": "EVIDENCE-CANARY", "source_path": "PRIVATE-PATH"},),
        attempt_history=({"attempt_id": "HISTORY-CANARY", "path": "PRIVATE-PATH"},),
    )
    options = request(format_name).model_copy(update={
        "include_transcript": bool(flags & 1), "include_evidence_details": bool(flags & 2),
        "include_attempt_history": bool(flags & 4), "include_candidate_reflection": bool(flags & 8),
    })
    payload = render_report_export(source, options)
    assert payload == render_report_export(source, options)
    body = payload.body.decode()
    for bit, canary in enumerate(("TRANSCRIPT-CANARY", "EVIDENCE-CANARY", "HISTORY-CANARY", "REFLECTION-CANARY")):
        assert (canary in body) == bool(flags & (1 << bit))
    assert "PRIVATE-AUDIO" not in body and "PRIVATE-PATH" not in body
    assert "source_path" not in body
    assert payload.filename.startswith("hatch-coach-")
    assert not any(character in payload.filename for character in '\r\n/"')
    assert payload.headers()["Cache-Control"] == "no-store"
    if format_name == "json":
        assert "not independent verification" in json.loads(body)["source_disclaimer"]
    else:
        assert "not independent verification" in body


def test_markdown_treats_hostile_source_as_literal_data(snapshot):
    from dataclasses import replace

    hostile = '<img src=x onerror=alert(1)> [open](javascript:alert(1)) ```\n# forged'
    source = replace(snapshot, evidence_details=({"snapshot_text": hostile},))
    payload = render_report_export(source, request("markdown").model_copy(update={"include_evidence_details": True}))
    text = payload.body.decode()
    assert "## Evidence details" in text
    assert "<img" not in text
    assert text.count("```json") == text.count("\n```\n")
    assert "\\u003cimg" in text
