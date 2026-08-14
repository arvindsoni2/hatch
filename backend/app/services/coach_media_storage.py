"""Filesystem boundary for streamed conversational Coach audio."""

from __future__ import annotations

import hashlib
import ctypes
import errno
import fcntl
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
_READ_FLAGS = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_LOCK_NAME = ".coach-media.lock"
_RENAME_EXCHANGE = 2


try:
    _LIBC_RENAMEAT2 = ctypes.CDLL(None, use_errno=True).renameat2
    _LIBC_RENAMEAT2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    _LIBC_RENAMEAT2.restype = ctypes.c_int
except AttributeError:  # pragma: no cover - exercised through the wrapper seam
    _LIBC_RENAMEAT2 = None


class CoachMediaError(RuntimeError):
    """A content-free failure at the Coach media trust boundary."""


def _rename_exchange(directory_fd: int, first: str, second: str) -> None:
    """Atomically exchange two names in one owned Linux directory."""
    if _LIBC_RENAMEAT2 is None:
        raise CoachMediaError("coach_attempt_upload_conflict")
    ctypes.set_errno(0)
    result = _LIBC_RENAMEAT2(
        directory_fd,
        os.fsencode(first),
        directory_fd,
        os.fsencode(second),
        _RENAME_EXCHANGE,
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
        raise CoachMediaError("coach_attempt_upload_conflict")
    raise OSError(error, os.strerror(error))


def _preserve_conflict_link(
    directory_fd: int, name: str, entry: os.stat_result
) -> str:
    """Give a displaced non-cooperating inode a stable, visible identity."""
    conflict = f"coach-conflict-{entry.st_dev:x}-{entry.st_ino:x}"
    try:
        os.link(
            name,
            conflict,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
    except FileExistsError:
        existing = os.stat(conflict, dir_fd=directory_fd, follow_symlinks=False)
        if existing.st_dev != entry.st_dev or existing.st_ino != entry.st_ino:
            raise CoachMediaError("coach_attempt_upload_conflict") from None
    preserved = os.stat(conflict, dir_fd=directory_fd, follow_symlinks=False)
    if preserved.st_dev != entry.st_dev or preserved.st_ino != entry.st_ino:
        raise CoachMediaError("coach_attempt_upload_conflict")
    return conflict


@dataclass
class _DirectoryMutationLock:
    file_descriptor: int
    closed: bool = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            fcntl.flock(self.file_descriptor, fcntl.LOCK_UN)
            os.close(self.file_descriptor)
        except OSError:
            raise CoachMediaError("coach_attempt_upload_conflict") from None


@dataclass
class _DirectoryMutationLocks:
    locks: list[_DirectoryMutationLock]

    def close(self) -> None:
        failed = False
        for lock in reversed(self.locks):
            try:
                lock.close()
            except CoachMediaError:
                failed = True
        if failed:
            raise CoachMediaError("coach_attempt_upload_conflict")

    def __enter__(self) -> _DirectoryMutationLocks:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


def _acquire_directory_mutation_locks(
    *directory_fds: int,
) -> _DirectoryMutationLocks:
    """Serialize every cooperating mutation in stable directory-inode order."""
    keyed_fds: dict[tuple[int, int], int] = {}
    for directory_fd in directory_fds:
        opened = os.fstat(directory_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise CoachMediaError("coach_attempt_upload_conflict")
        keyed_fds.setdefault((opened.st_dev, opened.st_ino), directory_fd)
    locks: list[_DirectoryMutationLock] = []
    try:
        for _, directory_fd in sorted(keyed_fds.items()):
            lock_fd = os.open(
                _LOCK_NAME,
                os.O_RDWR
                | os.O_CREAT
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=directory_fd,
            )
            lock = _DirectoryMutationLock(lock_fd)
            locks.append(lock)
            opened = os.fstat(lock_fd)
            current = os.stat(
                _LOCK_NAME, dir_fd=directory_fd, follow_symlinks=False
            )
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_mode & 0o022
                or opened.st_dev != current.st_dev
                or opened.st_ino != current.st_ino
            ):
                raise CoachMediaError("coach_attempt_upload_conflict")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            current = os.stat(
                _LOCK_NAME, dir_fd=directory_fd, follow_symlinks=False
            )
            if opened.st_dev != current.st_dev or opened.st_ino != current.st_ino:
                raise CoachMediaError("coach_attempt_upload_conflict")
        return _DirectoryMutationLocks(locks)
    except BaseException as error:
        for lock in reversed(locks):
            try:
                lock.close()
            except CoachMediaError:
                pass
        if isinstance(error, CoachMediaError) or not isinstance(error, Exception):
            raise
        raise CoachMediaError("coach_attempt_upload_conflict") from None


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

    def unlink_owned(self, *, lock_held: bool = False) -> None:
        locks = None
        if not lock_held:
            locks = _acquire_directory_mutation_locks(self.directory_fd)
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
        finally:
            if locks is not None:
                locks.close()
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

    def cleanup(self, *, lock_held: bool = False) -> None:
        unlink_error: BaseException | None = None
        try:
            self.unlink_owned(lock_held=lock_held)
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
    _file_descriptor: int

    def _close_file_descriptor(self) -> None:
        if self._file_descriptor < 0:
            return
        file_descriptor = self._file_descriptor
        self._file_descriptor = -1
        try:
            os.close(file_descriptor)
        except OSError:
            raise CoachMediaError("coach_attempt_upload_conflict") from None

    def compensate(self) -> None:
        self._entry.cleanup()
        self._close_file_descriptor()

    def release(self) -> None:
        failed = False
        try:
            self._close_file_descriptor()
        except CoachMediaError:
            failed = True
        try:
            self._entry.close()
        except CoachMediaError:
            failed = True
        if failed:
            raise CoachMediaError("coach_attempt_upload_conflict")


@dataclass
class OwnedAudioReadLease:
    """A verified, inode-pinned read descriptor for worker media access."""

    _file_descriptor: int
    _closed: bool = False

    @property
    def file_descriptor(self) -> int:
        return self._file_descriptor

    @property
    def path(self) -> Path:
        return Path(f"/proc/self/fd/{self._file_descriptor}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            os.close(self._file_descriptor)
        except OSError:
            raise CoachMediaError("coach_attempt_upload_conflict") from None

    def __enter__(self) -> OwnedAudioReadLease:
        if self._closed:
            raise CoachMediaError("coach_attempt_upload_conflict")
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


@dataclass
class OwnedAudioDeletionLease:
    """Authority to remove only the exact verified directory-entry inode."""

    _entry: _OwnedEntry
    _file_descriptor: int
    _directory_lock: _DirectoryMutationLocks
    _closed: bool = False
    _deleted: bool = False

    def delete_owned(self) -> bool:
        """Atomically isolate and delete the verified inode, never a replacement."""
        if self._closed:
            raise CoachMediaError("coach_attempt_upload_conflict")
        if self._deleted:
            return True
        tombstone = f".coach-delete-{secrets.token_hex(16)}"
        placeholder_fd = -1
        placeholder_device = -1
        placeholder_inode = -1
        placeholder_mode = -1
        placeholder_uid = -1
        placeholder_gid = -1
        try:
            if not self._entry.matches():
                return False
            placeholder_fd = os.open(
                tombstone,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=self._entry.directory_fd,
            )
            placeholder = os.fstat(placeholder_fd)
            placeholder_device = placeholder.st_dev
            placeholder_inode = placeholder.st_ino
            placeholder_mode = placeholder.st_mode
            placeholder_uid = placeholder.st_uid
            placeholder_gid = placeholder.st_gid
            _rename_exchange(self._entry.directory_fd, self._entry.name, tombstone)
            moved = os.stat(
                tombstone,
                dir_fd=self._entry.directory_fd,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(moved.st_mode)
                or moved.st_dev != self._entry.device
                or moved.st_ino != self._entry.inode
            ):
                try:
                    current = os.stat(
                        self._entry.name,
                        dir_fd=self._entry.directory_fd,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    current = None
                if (
                    current is not None
                    and current.st_dev == placeholder_device
                    and current.st_ino == placeholder_inode
                ):
                    _rename_exchange(
                        self._entry.directory_fd, self._entry.name, tombstone
                    )
                    restored_placeholder = os.stat(
                        tombstone,
                        dir_fd=self._entry.directory_fd,
                        follow_symlinks=False,
                    )
                    if (
                        restored_placeholder.st_dev != placeholder_device
                        or restored_placeholder.st_ino != placeholder_inode
                    ):
                        raise CoachMediaError("coach_attempt_upload_conflict")
                    os.unlink(tombstone, dir_fd=self._entry.directory_fd)
                    return False
                _preserve_conflict_link(
                    self._entry.directory_fd, tombstone, moved
                )
                os.unlink(tombstone, dir_fd=self._entry.directory_fd)
                raise CoachMediaError("coach_attempt_upload_conflict")
            try:
                current = os.stat(
                    self._entry.name,
                    dir_fd=self._entry.directory_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                current = None
            if (
                current is not None
                and current.st_dev == placeholder_device
                and current.st_ino == placeholder_inode
            ):
                placeholder_read_fd = -1
                try:
                    placeholder_read_fd = os.open(
                        self._entry.name,
                        _READ_FLAGS,
                        dir_fd=self._entry.directory_fd,
                    )
                    verified_placeholder = os.fstat(placeholder_read_fd)
                    placeholder_unchanged = bool(
                        verified_placeholder.st_dev == placeholder_device
                        and verified_placeholder.st_ino == placeholder_inode
                        and verified_placeholder.st_mode == placeholder_mode
                        and verified_placeholder.st_uid == placeholder_uid
                        and verified_placeholder.st_gid == placeholder_gid
                        and verified_placeholder.st_size == 0
                        and os.read(placeholder_read_fd, 1) == b""
                    )
                finally:
                    if placeholder_read_fd >= 0:
                        os.close(placeholder_read_fd)
                if not placeholder_unchanged:
                    _preserve_conflict_link(
                        self._entry.directory_fd,
                        self._entry.name,
                        current,
                    )
                    _rename_exchange(
                        self._entry.directory_fd, self._entry.name, tombstone
                    )
                    restored = os.stat(
                        self._entry.name,
                        dir_fd=self._entry.directory_fd,
                        follow_symlinks=False,
                    )
                    displaced = os.stat(
                        tombstone,
                        dir_fd=self._entry.directory_fd,
                        follow_symlinks=False,
                    )
                    if (
                        restored.st_dev != self._entry.device
                        or restored.st_ino != self._entry.inode
                        or displaced.st_dev != placeholder_device
                        or displaced.st_ino != placeholder_inode
                    ):
                        raise CoachMediaError("coach_attempt_upload_conflict")
                    os.unlink(tombstone, dir_fd=self._entry.directory_fd)
                    raise CoachMediaError("coach_attempt_upload_conflict")
                os.unlink(self._entry.name, dir_fd=self._entry.directory_fd)
            elif current is not None:
                raise CoachMediaError("coach_attempt_upload_conflict")
            os.unlink(tombstone, dir_fd=self._entry.directory_fd)
            self._deleted = True
            return True
        except FileNotFoundError:
            return False
        except OSError:
            raise CoachMediaError("coach_attempt_upload_conflict") from None
        finally:
            if placeholder_fd >= 0:
                try:
                    os.close(placeholder_fd)
                except OSError:
                    pass
            if placeholder_inode >= 0:
                try:
                    remaining = os.stat(
                        tombstone,
                        dir_fd=self._entry.directory_fd,
                        follow_symlinks=False,
                    )
                except OSError:
                    pass
                else:
                    if (
                        remaining.st_dev == placeholder_device
                        and remaining.st_ino == placeholder_inode
                    ):
                        try:
                            os.unlink(tombstone, dir_fd=self._entry.directory_fd)
                        except OSError:
                            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        file_error = False
        try:
            os.close(self._file_descriptor)
        except OSError:
            file_error = True
        try:
            self._entry.close()
        except CoachMediaError:
            file_error = True
        try:
            self._directory_lock.close()
        except CoachMediaError:
            file_error = True
        if file_error:
            raise CoachMediaError("coach_attempt_upload_conflict")

    def __enter__(self) -> OwnedAudioDeletionLease:
        if self._closed:
            raise CoachMediaError("coach_attempt_upload_conflict")
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


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
        with _acquire_directory_mutation_locks(root_fd):
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
        with _acquire_directory_mutation_locks(directory_fd):
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
    publication_fd = -1
    locks: _DirectoryMutationLocks | None = None
    try:
        locks = _acquire_directory_mutation_locks(
            source.directory_fd, destination_fd
        )
        if not source.matches():
            raise CoachMediaError("coach_attempt_upload_conflict")
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
        publication_fd = os.open(
            destination.name,
            _READ_FLAGS,
            dir_fd=destination_fd,
        )
        pinned = os.fstat(publication_fd)
        if pinned.st_dev != published.st_dev or pinned.st_ino != published.st_ino:
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
        result = OwnedAudioPublication(publication, publication_fd)
        publication_fd = -1
        return result
    except BaseException as error:
        cleanup_error: BaseException | None = None
        if publication is not None:
            try:
                publication.cleanup(lock_held=locks is not None)
            except BaseException as failure:
                cleanup_error = failure
        try:
            source.cleanup(lock_held=locks is not None)
        except BaseException as failure:
            if cleanup_error is None:
                cleanup_error = failure
        if not isinstance(error, Exception):
            raise
        if cleanup_error is not None and not isinstance(cleanup_error, Exception):
            raise cleanup_error
        raise CoachMediaError("coach_attempt_upload_conflict") from None
    finally:
        if publication_fd >= 0:
            try:
                os.close(publication_fd)
            except OSError:
                pass
        if locks is not None:
            try:
                locks.close()
            except CoachMediaError:
                pass
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


def owned_audio_path_is_missing(storage_root: Path, source_path: Path) -> bool:
    """Return true only for an absent leaf beneath valid no-follow parents."""
    try:
        root = _configured_root(storage_root)
        relative = source_path.absolute().relative_to(root)
    except (CoachMediaError, OSError, ValueError):
        return False
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        return False
    directory_fd = -1
    try:
        directory_fd = _open_exact_directory(root)
        for part in relative.parts[:-1]:
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            opened = os.fstat(next_fd)
            if not stat.S_ISDIR(opened.st_mode):
                os.close(next_fd)
                return False
            os.close(directory_fd)
            directory_fd = next_fd
        try:
            os.stat(
                relative.parts[-1],
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return True
        return False
    except (CoachMediaError, OSError):
        return False
    finally:
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass


def open_verified_audio_read_lease(
    storage_root: Path,
    source_path: Path,
    expected_sha256: str,
) -> OwnedAudioReadLease:
    """Open and hash an exact regular inode beneath the configured media root."""
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise CoachMediaError("coach_attempt_upload_conflict")
    root = _configured_root(storage_root)
    try:
        relative = source_path.absolute().relative_to(root)
    except (OSError, ValueError):
        raise CoachMediaError("coach_attempt_upload_conflict") from None
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise CoachMediaError("coach_attempt_upload_conflict")

    directory_fd = _open_exact_directory(root)
    file_fd = -1
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            opened_directory = os.fstat(next_fd)
            if not stat.S_ISDIR(opened_directory.st_mode):
                os.close(next_fd)
                raise CoachMediaError("coach_attempt_upload_conflict")
            os.close(directory_fd)
            directory_fd = next_fd

        name = relative.parts[-1]
        file_fd = os.open(name, _READ_FLAGS, dir_fd=directory_fd)
        opened = os.fstat(file_fd)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or opened.st_dev != current.st_dev
            or opened.st_ino != current.st_ino
        ):
            raise CoachMediaError("coach_attempt_upload_conflict")

        digest = hashlib.sha256()
        while chunk := os.read(file_fd, _STREAM_CHUNK_BYTES):
            digest.update(chunk)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            current.st_dev != opened.st_dev
            or current.st_ino != opened.st_ino
            or not secrets.compare_digest(digest.hexdigest(), expected_sha256)
        ):
            raise CoachMediaError("coach_attempt_upload_conflict")
        os.lseek(file_fd, 0, os.SEEK_SET)
        lease = OwnedAudioReadLease(file_fd)
        file_fd = -1
        return lease
    except CoachMediaError:
        raise
    except OSError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None
    finally:
        if file_fd >= 0:
            try:
                os.close(file_fd)
            except OSError:
                pass
        try:
            os.close(directory_fd)
        except OSError:
            pass


def open_verified_audio_deletion_lease(
    storage_root: Path,
    source_path: Path,
    expected_sha256: str,
) -> OwnedAudioDeletionLease:
    """Verify and retain inode-bound, root-confined deletion authority."""
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise CoachMediaError("coach_attempt_upload_conflict")
    root = _configured_root(storage_root)
    try:
        relative = source_path.absolute().relative_to(root)
    except (OSError, ValueError):
        raise CoachMediaError("coach_attempt_upload_conflict") from None
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise CoachMediaError("coach_attempt_upload_conflict")

    directory_fd = _open_exact_directory(root)
    file_fd = -1
    directory_lock: _DirectoryMutationLocks | None = None
    try:
        for part in relative.parts[:-1]:
            next_fd = os.open(part, _DIRECTORY_FLAGS, dir_fd=directory_fd)
            opened_directory = os.fstat(next_fd)
            if not stat.S_ISDIR(opened_directory.st_mode):
                os.close(next_fd)
                raise CoachMediaError("coach_attempt_upload_conflict")
            os.close(directory_fd)
            directory_fd = next_fd

        name = relative.parts[-1]
        directory_lock = _acquire_directory_mutation_locks(directory_fd)
        file_fd = os.open(name, _READ_FLAGS, dir_fd=directory_fd)
        opened = os.fstat(file_fd)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(current.st_mode)
            or opened.st_dev != current.st_dev
            or opened.st_ino != current.st_ino
        ):
            raise CoachMediaError("coach_attempt_upload_conflict")
        digest = hashlib.sha256()
        while chunk := os.read(file_fd, _STREAM_CHUNK_BYTES):
            digest.update(chunk)
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            current.st_dev != opened.st_dev
            or current.st_ino != opened.st_ino
            or not secrets.compare_digest(digest.hexdigest(), expected_sha256)
        ):
            raise CoachMediaError("coach_attempt_upload_conflict")
        os.lseek(file_fd, 0, os.SEEK_SET)
        lease = OwnedAudioDeletionLease(
            _OwnedEntry(directory_fd, name, opened.st_dev, opened.st_ino),
            file_fd,
            directory_lock,
        )
        directory_fd = -1
        file_fd = -1
        directory_lock = None
        return lease
    except CoachMediaError:
        raise
    except OSError:
        raise CoachMediaError("coach_attempt_upload_conflict") from None
    finally:
        if file_fd >= 0:
            try:
                os.close(file_fd)
            except OSError:
                pass
        if directory_fd >= 0:
            try:
                os.close(directory_fd)
            except OSError:
                pass
        if directory_lock is not None:
            try:
                directory_lock.close()
            except CoachMediaError:
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
