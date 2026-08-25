"""Transaction-bound runtime event repository and metadata privacy guard."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from .models import RuntimeEventRecord


class MetadataOnlyViolation(ValueError):
    """Raised when raw or sensitive content is offered to a metadata record."""


_SENSITIVE_FIELDS = {
    "content",
    "cv",
    "file_path",
    "job_description",
    "prompt",
    "raw",
    "resume",
    "transcript",
}

_EVENT_METADATA_FIELDS = {
    "attempt_number",
    "comparison_status",
    "destination",
    "domain_type",
    "fencing_token",
    "reason_code",
    "reason_codes",
    "result_class",
    "runtime_mode",
    "sensitivity",
    "status",
}
_EVENT_METADATA_SUFFIXES = (
    "_at",
    "_code",
    "_count",
    "_hash",
    "_id",
    "_ms",
    "_ref",
    "_status",
    "_usd",
    "_version",
)


def _is_sensitive_field(field: str) -> bool:
    return (
        field in _SENSITIVE_FIELDS
        or field.startswith("raw_")
        or field.endswith(("_content", "_path", "_text"))
        or "transcript" in field
        or "prompt" in field
    )


def enforce_metadata_only(value: Any, *, path: str = "payload") -> None:
    """Reject structurally sensitive fields and local paths in durable metadata."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if _is_sensitive_field(normalized):
                raise MetadataOnlyViolation(
                    f"sensitive field is not allowed in metadata-only records: {path}.{key}"
                )
            enforce_metadata_only(item, path=f"{path}.{key}")
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            enforce_metadata_only(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and (
        value.startswith(("/", "file://")) or "\\Users\\" in value
    ):
        raise MetadataOnlyViolation(
            f"local file paths are not allowed in metadata-only records: {path}"
        )


def enforce_event_metadata(value: Any, *, path: str = "payload") -> None:
    """Apply the event plane's strict metadata field allowlist recursively."""
    enforce_metadata_only(value, path=path)
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized not in _EVENT_METADATA_FIELDS and not normalized.endswith(
                _EVENT_METADATA_SUFFIXES
            ):
                raise MetadataOnlyViolation(
                    f"field is not in the runtime event metadata contract: {path}.{key}"
                )
            if isinstance(item, (Mapping, Sequence)) and not isinstance(
                item, (str, bytes, bytearray)
            ):
                enforce_event_metadata(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            enforce_event_metadata(item, path=f"{path}[{index}]")


class SQLiteEventRepository:
    """Append runtime events without owning or committing the transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def append(self, **values: Any) -> RuntimeEventRecord:
        if values.get("sensitivity") != "metadata":
            raise MetadataOnlyViolation(
                "runtime events accept only the metadata sensitivity contract"
            )
        enforce_event_metadata(values.get("payload_json", {}))
        enforce_event_metadata(values.get("metadata_json") or {}, path="metadata")
        record = RuntimeEventRecord(**values)
        self.session.add(record)
        await self.session.flush()
        return record
