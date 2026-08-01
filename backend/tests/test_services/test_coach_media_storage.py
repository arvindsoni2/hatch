"""Filesystem-boundary tests for Coach audio read leases."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.services.coach_media_storage import (
    CoachMediaError,
    open_verified_audio_read_lease,
)


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def test_verified_read_lease_retains_the_hashed_inode_after_path_replacement(
    tmp_path: Path,
) -> None:
    """Reopening the pathname after verification can transcribe replacement bytes."""
    root = tmp_path / "coach-media"
    source = root / "session-1" / "attempt-1-upload-1.webm"
    source.parent.mkdir(parents=True)
    original = b"original-audio"
    source.write_bytes(original)

    with open_verified_audio_read_lease(root, source, _sha256(original)) as lease:
        descriptor_path = lease.path
        source.unlink()
        source.write_bytes(b"replacement-audio")

        assert descriptor_path == Path(f"/proc/self/fd/{lease.file_descriptor}")
        assert descriptor_path.read_bytes() == original

    lease.close()
    assert not descriptor_path.exists()


@pytest.mark.parametrize("symlink_part", ("root", "parent", "file"))
def test_verified_read_lease_rejects_symlinked_storage_components(
    tmp_path: Path, symlink_part: str
) -> None:
    """Following any symlink in the trusted path can escape Coach media storage."""
    real_root = tmp_path / "real-coach-media"
    real_parent = real_root / "session-1"
    real_parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    body = b"outside-audio"
    outside_file = outside / "answer.webm"
    outside_file.write_bytes(body)

    if symlink_part == "root":
        root = tmp_path / "coach-media"
        root.symlink_to(real_root, target_is_directory=True)
        source = root / "session-1" / "answer.webm"
        (real_parent / "answer.webm").write_bytes(body)
    elif symlink_part == "parent":
        root = real_root
        source = root / "linked-session" / "answer.webm"
        (root / "linked-session").symlink_to(outside, target_is_directory=True)
    else:
        root = real_root
        source = real_parent / "answer.webm"
        source.symlink_to(outside_file)

    with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
        open_verified_audio_read_lease(root, source, _sha256(body))


def test_verified_read_lease_rejects_root_escape_and_hash_mismatch(
    tmp_path: Path,
) -> None:
    """Trusting either caller path containment or its declared hash reads wrong bytes."""
    root = tmp_path / "coach-media"
    root.mkdir()
    outside = tmp_path / "outside.webm"
    outside.write_bytes(b"outside-audio")
    inside = root / "inside.webm"
    inside.write_bytes(b"inside-audio")

    with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
        open_verified_audio_read_lease(root, outside, _sha256(b"outside-audio"))
    with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
        open_verified_audio_read_lease(root, inside, _sha256(b"different-audio"))


def test_verified_read_lease_rejects_replacement_during_descriptor_hashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hashing a pinned inode without checking its directory entry accepts a swap race."""
    root = tmp_path / "coach-media"
    source = root / "session-1" / "answer.webm"
    source.parent.mkdir(parents=True)
    original = b"original-audio"
    source.write_bytes(original)
    real_read = os.read
    replaced = False

    def replace_after_first_read(file_descriptor: int, size: int) -> bytes:
        nonlocal replaced
        chunk = real_read(file_descriptor, size)
        if chunk and not replaced:
            replaced = True
            source.unlink()
            source.write_bytes(b"replacement-audio")
        return chunk

    monkeypatch.setattr(os, "read", replace_after_first_read)

    with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
        open_verified_audio_read_lease(root, source, _sha256(original))

    assert replaced is True

