"""Deterministic, synchronous, no-artifact conversational report exports."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..schemas.coach_conversation import ReportExportRequest

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_-]+")
_PRIVATE_KEYS = frozenset(
    {
        "audio_uri",
        "audio_url",
        "raw_audio_url",
        "video_uri",
        "video_url",
        "filename",
        "path",
        "retention_summary",
    }
)


@dataclass(frozen=True)
class ExportSnapshot:
    session_id: str
    report_state: Literal["completed", "fallback"]
    activity_version: int
    retention_version: int
    report_json: Mapping[str, object]
    retention_summary: Mapping[str, object] | None = None
    transcript: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    evidence_details: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    attempt_history: Sequence[Mapping[str, object]] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExportPayload:
    body: bytes
    media_type: str
    filename: str
    etag: str
    activity_version: int
    retention_version: int

    def headers(self) -> dict[str, str]:
        return {
            "Cache-Control": "no-store",
            "ETag": self.etag,
            "Content-Disposition": f'attachment; filename="{self.filename}"',
            "X-Coach-Activity-Version": str(self.activity_version),
            "X-Coach-Retention-Version": str(self.retention_version),
        }


class ExportRepository(Protocol):
    async def load_export_snapshot(
        self, session_id: str, request: ReportExportRequest
    ) -> ExportSnapshot | None: ...

    async def export_versions_match(
        self, session_id: str, activity_version: int, retention_version: int
    ) -> bool: ...


def make_etag(body: bytes) -> str:
    return f'"{hashlib.sha256(body).hexdigest()}"'


def _safe_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_value(nested)
            for key, nested in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key).lower() not in _PRIVATE_KEYS
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe_value(item) for item in value]
    return value


def _filename(session_id: str, extension: str) -> str:
    safe_id = _SAFE_FILENAME.sub("-", session_id).strip("-_") or "session"
    return f"coach-report-{safe_id}.{extension}"


def _json_document(snapshot: ExportSnapshot, request: ReportExportRequest) -> dict[str, object]:
    document = dict(_safe_value(snapshot.report_json))
    document.pop("retention_summary", None)
    document["activity_version"] = snapshot.activity_version
    document["retention_version"] = snapshot.retention_version
    document["report_state"] = snapshot.report_state
    document["contract_version"] = "coach_report_export_v1"
    if request.include_candidate_reflection:
        reflection = snapshot.report_json.get("candidate_reflection")
        if reflection is not None:
            document["candidate_reflection"] = _safe_value(reflection)
    else:
        document.pop("candidate_reflection", None)
    if request.include_transcript:
        document["transcript"] = _safe_value(snapshot.transcript)
    if request.include_evidence_details:
        document["evidence_details"] = _safe_value(snapshot.evidence_details)
    if request.include_attempt_history:
        document["attempt_history"] = _safe_value(snapshot.attempt_history)
    return document


def _markdown_document(document: Mapping[str, object]) -> str:
    sections = [
        ("Session level", document.get("session_level", "not_assessed")),
        ("Dimensions", document.get("dimensions", {})),
        ("Strengths", document.get("strengths", [])),
        ("Improvement priorities", document.get("improvement_priorities", [])),
        ("Evidence review", document.get("evidence_review_items", [])),
        ("Question summaries", document.get("question_summaries", [])),
        ("Practice suggestions", document.get("practice_suggestions", [])),
        ("Candidate reflection", document.get("candidate_reflection", {})),
    ]
    lines = ["# Conversational interview report", ""]
    for title, value in sections:
        lines.extend((f"## {title}", "", json.dumps(value, ensure_ascii=False, sort_keys=True), ""))
    lines.extend(
        (
            "## Source disclaimer",
            "",
            "This report is grounded in the accepted conversational interview evidence available at export time.",
            "",
        )
    )
    return "\n".join(lines)


def render_report_export(
    snapshot: ExportSnapshot, request: ReportExportRequest
) -> ExportPayload:
    if snapshot.report_state not in {"completed", "fallback"}:
        raise ValueError("coach_report_unavailable")
    if (
        snapshot.activity_version != request.expected_activity_version
        or snapshot.retention_version != request.expected_retention_version
    ):
        raise ValueError("coach_export_source_changed")
    document = _json_document(snapshot, request)
    if request.format == "json":
        body = (
            json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        media_type = "application/json"
        extension = "json"
    else:
        body = _markdown_document(document).encode("utf-8")
        media_type = "text/markdown; charset=utf-8"
        extension = "md"
    return ExportPayload(
        body=body,
        media_type=media_type,
        filename=_filename(snapshot.session_id, extension),
        etag=make_etag(body),
        activity_version=snapshot.activity_version,
        retention_version=snapshot.retention_version,
    )


async def export_report(
    session_id: str,
    request: ReportExportRequest,
    repository: ExportRepository,
) -> ExportPayload:
    snapshot = await repository.load_export_snapshot(session_id, request)
    if snapshot is None:
        raise ValueError("coach_report_unavailable")
    payload = render_report_export(snapshot, request)
    if not await repository.export_versions_match(
        session_id, snapshot.activity_version, snapshot.retention_version
    ):
        raise ValueError("coach_export_source_changed")
    return payload
