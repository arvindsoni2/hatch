"""Filesystem boundary for streamed conversational Coach audio."""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import UploadFile


_STREAM_CHUNK_BYTES = 1024 * 1024
_AUDIO_MIME_ALIASES = {
    "audio/webm": "audio/webm",
    "audio/x-webm": "audio/webm",
}
_DIRECTORY_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)


class CoachMediaError(RuntimeError):
    """A content-free failure at the Coach media trust boundary."""


@dataclass
class _OwnedEntry:
    directory_fd: int
    name: str
    device: int
    inode: int
    closed: bool = False

    def matches(self) -> bool:
        try:
            current = os.stat(
                self.name, dir_fd=self.directory_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            return False
        return (
            stat.S_ISREG(current.st_mode)
            and current.st_dev == self.device
            and current.st_ino == self.inode
        )

    def unlink_owned(self) -> None:
        error = False
        try:
            current = os.stat(
                self.name, dir_fd=self.directory_fd, follow_symlinks=False
            )
        except FileNotFoundError:
            return
        except OSError:
            error = True
        else:
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_dev != self.device
                or current.st_ino != self.inode
            ):
                error = True
            else:
                try:
                    os.unlink(self.name, dir_fd=self.directory_fd)
                except OSError:
                    error = True
        if error:
            raise CoachMediaError("coach_attempt_upload_conflict")

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            os.close(self.directory_fd)
        except OSError:
            raise CoachMediaError("coach_attempt_upload_conflict") from None

    def cleanup(self) -> None:
        unlink_error: BaseException | None = None
        try:
            self.unlink_owned()
        except BaseException as error:
            unlink_error = error
        if unlink_error is not None:
            # Keep the directory descriptor and inode identity available for a
            # later compensation attempt. Closing here would make a transient
            # unlink failure indistinguishable from an already-cleaned entry.
            if not isinstance(unlink_error, Exception):
                raise unlink_error
            raise CoachMediaError("coach_attempt_upload_conflict") from None
        try:
            self.close()
        except BaseException:
            raise CoachMediaError("coach_attempt_upload_conflict") from None


@dataclass
class OwnedAudioPublication:
    """An inode-bound destination lease used for rollback compensation."""

    _entry: _OwnedEntry

    def compensate(self) -> None:
        self._entry.cleanup()

    def release(self) -> None:
        self._entry.close()


@dataclass(frozen=True)
class StagedAudio:
    temporary_path: Path
    content_sha256: str
    byte_size: int
    mime_type: str
    _entry: _OwnedEntry | None = field(default=None, repr=False, compare=False)


def normalize_audio_mime(content_type: str | None) -> str:
    """Normalize the supported browser audio MIME without reflecting input."""
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    try:
        return _AUDIO_MIME_ALIASES[normalized]
    except KeyError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def _descriptor_path(directory_fd: int) -> Path | None:
    descriptor = Path(f"/proc/self/fd/{directory_fd}")
    try:
        return Path(os.readlink(descriptor))
    except OSError:
        return None


def _open_exact_directory(path: Path) -> int:
    expected = path.absolute()
    directory_fd = -1
    try:
        directory_fd = os.open(expected, _DIRECTORY_FLAGS)
        opened = os.fstat(directory_fd)
        current = os.stat(expected, follow_symlinks=False)
        descriptor_path = _descriptor_path(directory_fd)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or opened.st_dev != current.st_dev
            or opened.st_ino != current.st_ino
            or (descriptor_path is not None and descriptor_path != expected)
        ):
            raise CoachMediaError("coach_attempt_upload_conflict")
        return directory_fd
    except CoachMediaError:
        if directory_fd >= 0:
            os.close(directory_fd)
        raise
    except OSError:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def _configured_root(storage_root: Path) -> Path:
    try:
        if storage_root.is_symlink():
            raise CoachMediaError("coach_attempt_upload_conflict")
        storage_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root = storage_root.resolve(strict=True)
        directory_fd = _open_exact_directory(root)
        os.close(directory_fd)
        return root
    except CoachMediaError:
        raise
    except OSError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def _owned_child_directory(root: Path, name: str) -> Path:
    root_fd = _open_exact_directory(root)
    child_fd = -1
    try:
        try:
            os.mkdir(name, mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=root_fd)
        child = root / name
        opened = os.fstat(child_fd)
        descriptor_path = _descriptor_path(child_fd)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or (descriptor_path is not None and descriptor_path != child)
        ):
            raise CoachMediaError("coach_attempt_upload_conflict")
        return child
    except CoachMediaError:
        raise
    except OSError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None
    finally:
        if child_fd >= 0:
            try:
                os.close(child_fd)
            except OSError:
                pass
        try:
            os.close(root_fd)
        except OSError:
            pass


def coach_upload_temp_dir(storage_root: Path) -> Path:
    """Create and return the isolated upload staging directory."""
    root = _configured_root(storage_root)
    return _owned_child_directory(root, ".uploads")


def _new_staged_entry(temp_dir: Path) -> tuple[_OwnedEntry, int, Path]:
    directory_fd = _open_exact_directory(temp_dir)
    file_fd = -1
    try:
        for _ in range(64):
            name = f"coach-upload-{secrets.token_hex(16)}"
            try:
                file_fd = os.open(
                    name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                continue
            opened = os.fstat(file_fd)
            return (
                _OwnedEntry(directory_fd, name, opened.st_dev, opened.st_ino),
                file_fd,
                temp_dir / name,
            )
        raise CoachMediaError("coach_attempt_upload_conflict")
    except BaseException as error:
        if file_fd >= 0:
            try:
                os.close(file_fd)
            except OSError:
                pass
        try:
            os.close(directory_fd)
        except OSError:
            pass
        if isinstance(error, CoachMediaError) or not isinstance(error, Exception):
            raise
        raise CoachMediaError("coach_attempt_upload_conflict") from None


async def stream_audio_upload(
    upload: UploadFile, *, max_bytes: int, temp_dir: Path
) -> StagedAudio:
    """Stream an allowlisted audio upload to a bounded private temporary file."""
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise CoachMediaError("coach_attempt_upload_conflict")
    mime_type = normalize_audio_mime(upload.content_type)
    digest = hashlib.sha256()
    size = 0
    entry: _OwnedEntry | None = None
    file_fd = -1
    try:
        entry, file_fd, path = _new_staged_entry(temp_dir)
        with os.fdopen(file_fd, "wb") as target:
            file_fd = -1
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
        return StagedAudio(path, digest.hexdigest(), size, mime_type, entry)
    except BaseException as error:
        if file_fd >= 0:
            try:
                os.close(file_fd)
            except OSError:
                pass
        cleanup_error: BaseException | None = None
        if entry is not None:
            try:
                entry.cleanup()
            except BaseException as failure:
                cleanup_error = failure
        if not isinstance(error, Exception):
            raise
        if cleanup_error is not None and not isinstance(cleanup_error, Exception):
            raise cleanup_error
        if isinstance(error, CoachMediaError) and cleanup_error is None:
            raise
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def _entry_for_staged(staged: StagedAudio) -> _OwnedEntry:
    existing_entry = getattr(staged, "_entry", None)
    if existing_entry is not None and not existing_entry.closed:
        if not existing_entry.matches():
            raise CoachMediaError("coach_attempt_upload_conflict")
        return existing_entry
    path = staged.temporary_path.absolute()
    directory_fd = _open_exact_directory(path.parent)
    try:
        opened = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode):
            raise CoachMediaError("coach_attempt_upload_conflict")
        return _OwnedEntry(directory_fd, path.name, opened.st_dev, opened.st_ino)
    except BaseException:
        try:
            os.close(directory_fd)
        except OSError:
            pass
        raise


def cleanup_staged_audio(staged: StagedAudio) -> None:
    """Remove only the exact staged inode owned by this request."""
    existing_entry = getattr(staged, "_entry", None)
    if existing_entry is not None and existing_entry.closed:
        return
    if existing_entry is None:
        try:
            staged.temporary_path.lstat()
        except FileNotFoundError:
            return
        except OSError:
            raise CoachMediaError("coach_attempt_upload_conflict") from None
    try:
        _entry_for_staged(staged).cleanup()
    except CoachMediaError:
        raise
    except BaseException as error:
        if not isinstance(error, Exception):
            raise
        raise CoachMediaError("coach_attempt_upload_conflict") from None


def publish_staged_audio(
    staged: StagedAudio, destination: Path
) -> OwnedAudioPublication:
    """Publish without following parents or replacing an existing entry."""
    source = _entry_for_staged(staged)
    destination_fd = _open_exact_directory(destination.parent)
    publication: _OwnedEntry | None = None
    try:
        if destination.name in {"", ".", ".."}:
            raise CoachMediaError("coach_attempt_upload_conflict")
        try:
            os.stat(destination.name, dir_fd=destination_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise CoachMediaError("coach_attempt_upload_conflict")
        os.link(
            source.name,
            destination.name,
            src_dir_fd=source.directory_fd,
            dst_dir_fd=destination_fd,
            follow_symlinks=False,
        )
        published = os.stat(
            destination.name, dir_fd=destination_fd, follow_symlinks=False
        )
        if published.st_dev != source.device or published.st_ino != source.inode:
            raise CoachMediaError("coach_attempt_upload_conflict")
        publication = _OwnedEntry(
            destination_fd,
            destination.name,
            published.st_dev,
            published.st_ino,
        )
        destination_fd = -1
        os.unlink(source.name, dir_fd=source.directory_fd)
        source.close()
        return OwnedAudioPublication(publication)
    except BaseException as error:
        cleanup_error: BaseException | None = None
        if publication is not None:
            try:
                publication.cleanup()
            except BaseException as failure:
                cleanup_error = failure
        try:
            source.cleanup()
        except BaseException as failure:
            if cleanup_error is None:
                cleanup_error = failure
        if not isinstance(error, Exception):
            raise
        if cleanup_error is not None and not isinstance(cleanup_error, Exception):
            raise cleanup_error
        raise CoachMediaError("coach_attempt_upload_conflict") from None
    finally:
        if destination_fd >= 0:
            try:
                os.close(destination_fd)
            except OSError:
                pass


def owned_audio_path_is_file(destination: Path) -> bool:
    """Check an existing destination through an exact no-follow parent handle."""
    directory_fd = -1
    try:
        directory_fd = _open_exact_directory(destination.parent)
        opened = os.stat(
            destination.name, dir_fd=directory_fd, follow_symlinks=False
        )
        return stat.S_ISREG(opened.st_mode)
    except (CoachMediaError, OSError):
        return False
    finally:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass


def resolve_owned_audio_path(
    storage_root: Path,
    session_id: str,
    attempt_id: str,
    upload_id: str,
    suffix: str,
) -> Path:
    """Resolve a server-generated destination beneath the configured root."""
    if not suffix.startswith(".") or len(suffix) > 16 or not suffix[1:].isalnum():
        raise CoachMediaError("coach_attempt_upload_conflict")
    root = _configured_root(storage_root)
    parent = _owned_child_directory(root, session_id)
    candidate = parent / f"{attempt_id}-{upload_id}{suffix}"
    if candidate.parent != parent:
        raise CoachMediaError("coach_attempt_upload_conflict")
    return candidate
