"""Filesystem boundary for streamed conversational Coach audio."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile


_STREAM_CHUNK_BYTES = 1024 * 1024
_AUDIO_MIME_ALIASES = {
    "audio/webm": "audio/webm",
    "audio/x-webm": "audio/webm",
}


class CoachMediaError(RuntimeError):
    """A content-free failure at the Coach media trust boundary."""


@dataclass(frozen=True)
class StagedAudio:
    temporary_path: Path
    content_sha256: str
    byte_size: int
    mime_type: str


def normalize_audio_mime(content_type: str | None) -> str:
    """Normalize the supported browser audio MIME without reflecting input."""
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    try:
        return _AUDIO_MIME_ALIASES[normalized]
    except KeyError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def _configured_root(storage_root: Path) -> Path:
    try:
        storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = storage_root.resolve(strict=True)
        if not root.is_dir():
            raise CoachMediaError("coach_attempt_upload_conflict")
        return root
    except CoachMediaError:
        raise
    except OSError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def _owned_directory(root: Path, candidate: Path) -> Path:
    try:
        if candidate.is_symlink():
            raise CoachMediaError("coach_attempt_upload_conflict")
        candidate.mkdir(parents=False, exist_ok=True, mode=0o700)
        if candidate.is_symlink():
            raise CoachMediaError("coach_attempt_upload_conflict")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir() or not resolved.is_relative_to(root):
            raise CoachMediaError("coach_attempt_upload_conflict")
        return resolved
    except CoachMediaError:
        raise
    except OSError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def coach_upload_temp_dir(storage_root: Path) -> Path:
    """Create and return the isolated upload staging directory."""
    root = _configured_root(storage_root)
    return _owned_directory(root, root / ".uploads")


async def stream_audio_upload(
    upload: UploadFile, *, max_bytes: int, temp_dir: Path
) -> StagedAudio:
    """Stream an allowlisted audio upload to a bounded private temporary file."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise CoachMediaError("coach_attempt_upload_conflict")
    mime_type = normalize_audio_mime(upload.content_type)
    digest = hashlib.sha256()
    size = 0
    path: Path | None = None
    try:
        fd, raw_path = tempfile.mkstemp(dir=temp_dir, prefix="coach-upload-")
        path = Path(raw_path)
        with os.fdopen(fd, "wb") as target:
            while chunk := await upload.read(_STREAM_CHUNK_BYTES):
                size += len(chunk)
                if size > max_bytes:
                    raise CoachMediaError("coach_attempt_upload_conflict")
                digest.update(chunk)
                target.write(chunk)
            if size == 0:
                raise CoachMediaError("coach_attempt_upload_conflict")
            target.flush()
            os.fsync(target.fileno())
        return StagedAudio(path, digest.hexdigest(), size, mime_type)
    except BaseException as error:
        if path is not None:
            path.unlink(missing_ok=True)
        if isinstance(error, OSError):
            raise CoachMediaError("coach_attempt_upload_conflict") from None
        raise


def resolve_owned_audio_path(
    storage_root: Path,
    session_id: str,
    attempt_id: str,
    upload_id: str,
    suffix: str,
) -> Path:
    """Resolve a server-generated destination beneath the configured root."""
    if (
        not suffix.startswith(".")
        or len(suffix) > 16
        or not suffix[1:].isalnum()
    ):
        raise CoachMediaError("coach_attempt_upload_conflict")
    root = _configured_root(storage_root)
    parent = _owned_directory(root, root / session_id)
    try:
        candidate = parent / f"{attempt_id}-{upload_id}{suffix}"
        if candidate.is_symlink():
            raise CoachMediaError("coach_attempt_upload_conflict")
        resolved = candidate.resolve(strict=False)
        if resolved.parent != parent or not resolved.is_relative_to(root):
            raise CoachMediaError("coach_attempt_upload_conflict")
        return resolved
    except CoachMediaError:
        raise
    except OSError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None
