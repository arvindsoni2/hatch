"""Filesystem-boundary tests for Coach audio read leases."""

from __future__ import annotations

import asyncio
import ctypes
import errno
import hashlib
import os
import threading
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services import coach_media_storage as media_storage
from app.services.coach_media_storage import (
    CoachMediaError,
    StagedAudio,
    cleanup_staged_audio,
    open_verified_audio_deletion_lease,
    open_verified_audio_read_lease,
    publish_staged_audio,
    resolve_owned_audio_path,
    stream_audio_upload,
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


def test_verified_deletion_lease_unlinks_only_its_hashed_inode(tmp_path: Path) -> None:
    root = tmp_path / "coach-media"
    source = root / "session-1" / "answer.webm"
    source.parent.mkdir(parents=True)
    body = b"owned-audio"
    source.write_bytes(body)

    with open_verified_audio_deletion_lease(root, source, _sha256(body)) as lease:
        assert lease.delete_owned() is True

    assert not source.exists()


def test_verified_deletion_lease_does_not_unlink_path_replacement(
    tmp_path: Path,
) -> None:
    root = tmp_path / "coach-media"
    source = root / "session-1" / "answer.webm"
    source.parent.mkdir(parents=True)
    original = b"owned-audio"
    replacement = b"replacement-audio"
    source.write_bytes(original)

    with open_verified_audio_deletion_lease(
        root, source, _sha256(original)
    ) as lease:
        source.unlink()
        source.write_bytes(replacement)
        assert lease.delete_owned() is False

    assert source.read_bytes() == replacement


def test_verified_deletion_lease_does_not_hide_two_boundary_replacements(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A basename swap at match-to-rename must preserve every competing inode."""
    root = tmp_path / "coach-media"
    source = root / "session-1" / "answer.webm"
    source.parent.mkdir(parents=True)
    original = b"owned-audio"
    first_replacement = b"first-replacement"
    second_replacement = b"second-replacement"
    source.write_bytes(original)
    preserved_original = source.with_name("preserved-original.webm")
    real_rename = os.rename
    real_exchange = media_storage._rename_exchange
    injected = False

    def replace_at_exchange(directory_fd: int, src: str, dst: str) -> None:
        nonlocal injected
        if not injected:
            injected = True
            real_rename(source, preserved_original)
            source.write_bytes(first_replacement)
            real_exchange(directory_fd, src, dst)
            source.unlink()
            source.write_bytes(second_replacement)
            return
        real_exchange(directory_fd, src, dst)

    with open_verified_audio_deletion_lease(
        root, source, _sha256(original)
    ) as lease:
        monkeypatch.setattr(media_storage, "_rename_exchange", replace_at_exchange)
        with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
            lease.delete_owned()

    entries = list(source.parent.iterdir())
    assert injected is True
    assert source.read_bytes() == second_replacement
    assert preserved_original.read_bytes() == original
    assert {entry.read_bytes() for entry in entries} >= {
        original,
        first_replacement,
        second_replacement,
    }
    conflicts = [entry for entry in entries if entry.name.startswith("coach-conflict-")]
    assert len(conflicts) == 1
    assert conflicts[0].read_bytes() == first_replacement
    assert not any(entry.name.startswith(".coach-delete-") for entry in entries)


def test_verified_deletion_lease_preserves_modified_exchange_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Matching placeholder inode metadata cannot authorize deleting new bytes."""
    root = tmp_path / "coach-media"
    source = root / "session-1" / "answer.webm"
    source.parent.mkdir(parents=True)
    original = b"owned-audio"
    replacement = b"same-inode-placeholder-write"
    source.write_bytes(original)
    real_exchange = media_storage._rename_exchange
    injected = False

    def mutate_placeholder(directory_fd: int, src: str, dst: str) -> None:
        nonlocal injected
        real_exchange(directory_fd, src, dst)
        if not injected:
            injected = True
            source.write_bytes(replacement)

    with open_verified_audio_deletion_lease(
        root, source, _sha256(original)
    ) as lease:
        monkeypatch.setattr(media_storage, "_rename_exchange", mutate_placeholder)
        with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
            lease.delete_owned()

    entries = list(source.parent.iterdir())
    assert source.read_bytes() == original
    conflicts = [entry for entry in entries if entry.name.startswith("coach-conflict-")]
    assert len(conflicts) == 1
    assert conflicts[0].read_bytes() == replacement
    assert not any(entry.name.startswith(".coach-delete-") for entry in entries)


def test_verified_deletion_lease_serializes_cooperative_publication(
    tmp_path: Path,
) -> None:
    """An app publisher cannot enter a verified deletion critical section."""
    root = tmp_path / "coach-media"
    parent = root / "session-1"
    parent.mkdir(parents=True)
    source = parent / "answer.webm"
    source_body = b"owned-audio"
    source.write_bytes(source_body)
    staged_path = root / ".uploads" / "staged.webm"
    staged_path.parent.mkdir()
    staged_body = b"new-audio"
    staged_path.write_bytes(staged_body)
    staged = StagedAudio(
        staged_path,
        _sha256(staged_body),
        len(staged_body),
        "audio/webm",
    )
    destination = parent / "published.webm"
    started = threading.Event()
    completed = threading.Event()
    failures: list[BaseException] = []

    def publish() -> None:
        started.set()
        try:
            publication = publish_staged_audio(staged, destination)
            publication.release()
        except BaseException as error:
            failures.append(error)
        finally:
            completed.set()

    with open_verified_audio_deletion_lease(
        root, source, _sha256(source_body)
    ):
        thread = threading.Thread(target=publish)
        thread.start()
        assert started.wait(timeout=1)
        entered_while_lease_held = completed.wait(timeout=0.1)

    thread.join(timeout=1)
    assert entered_while_lease_held is False
    assert completed.is_set()
    assert failures == []
    assert destination.read_bytes() == staged_body


def test_verified_deletion_lease_serializes_staging_create_and_cleanup(
    tmp_path: Path,
) -> None:
    """Staging creation and compensation share the owned-directory mutex."""
    root = tmp_path / "coach-media"
    uploads = root / ".uploads"
    uploads.mkdir(parents=True)
    barrier = uploads / "barrier.webm"
    barrier_body = b"barrier"
    barrier.write_bytes(barrier_body)
    cleanup_path = uploads / "cleanup.webm"
    cleanup_body = b"cleanup"
    cleanup_path.write_bytes(cleanup_body)
    cleanup_entry = StagedAudio(
        cleanup_path,
        _sha256(cleanup_body),
        len(cleanup_body),
        "audio/webm",
    )
    upload = UploadFile(
        BytesIO(b"new-upload"),
        filename="answer.webm",
        headers=Headers({"content-type": "audio/webm"}),
    )
    started = [threading.Event(), threading.Event()]
    completed = [threading.Event(), threading.Event()]
    failures: list[BaseException] = []
    created: list[StagedAudio] = []

    def cleanup() -> None:
        started[0].set()
        try:
            cleanup_staged_audio(cleanup_entry)
        except BaseException as error:
            failures.append(error)
        finally:
            completed[0].set()

    def create() -> None:
        started[1].set()
        try:
            created.append(
                asyncio.run(
                    stream_audio_upload(upload, max_bytes=64, temp_dir=uploads)
                )
            )
        except BaseException as error:
            failures.append(error)
        finally:
            completed[1].set()

    with open_verified_audio_deletion_lease(
        root, barrier, _sha256(barrier_body)
    ):
        threads = [threading.Thread(target=cleanup), threading.Thread(target=create)]
        for thread in threads:
            thread.start()
        assert all(event.wait(timeout=1) for event in started)
        entered_while_lease_held = [event.wait(timeout=0.1) for event in completed]

    for thread in threads:
        thread.join(timeout=1)
    assert entered_while_lease_held == [False, False]
    assert all(event.is_set() for event in completed)
    assert failures == []
    assert not cleanup_path.exists()
    assert len(created) == 1
    cleanup_staged_audio(created[0])


def test_verified_deletion_lease_serializes_owned_child_creation(
    tmp_path: Path,
) -> None:
    """Session-directory publication cannot mutate a locked media root."""
    root = tmp_path / "coach-media"
    root.mkdir()
    barrier = root / "barrier.webm"
    barrier_body = b"barrier"
    barrier.write_bytes(barrier_body)
    started = threading.Event()
    completed = threading.Event()
    failures: list[BaseException] = []

    def resolve() -> None:
        started.set()
        try:
            resolve_owned_audio_path(
                root, "session-2", "attempt-1", "upload-1", ".webm"
            )
        except BaseException as error:
            failures.append(error)
        finally:
            completed.set()

    with open_verified_audio_deletion_lease(
        root, barrier, _sha256(barrier_body)
    ):
        thread = threading.Thread(target=resolve)
        thread.start()
        assert started.wait(timeout=1)
        entered_while_lease_held = completed.wait(timeout=0.1)

    thread.join(timeout=1)
    assert entered_while_lease_held is False
    assert completed.is_set()
    assert failures == []
    assert (root / "session-2").is_dir()


def test_verified_deletion_lease_fails_safe_without_rename_exchange(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unsupported atomic exchange cannot mutate the authoritative basename."""
    root = tmp_path / "coach-media"
    source = root / "session-1" / "answer.webm"
    source.parent.mkdir(parents=True)
    body = b"owned-audio"
    source.write_bytes(body)

    def unsupported(*_args: object) -> int:
        ctypes.set_errno(errno.ENOSYS)
        return -1

    with open_verified_audio_deletion_lease(root, source, _sha256(body)) as lease:
        monkeypatch.setattr(media_storage, "_LIBC_RENAMEAT2", unsupported)
        with pytest.raises(CoachMediaError, match="coach_attempt_upload_conflict"):
            lease.delete_owned()

    assert source.read_bytes() == body
    assert not any(
        entry.name.startswith(".coach-delete-") for entry in source.parent.iterdir()
    )
