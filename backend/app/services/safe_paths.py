"""Shared validation for identifiers that become filesystem path segments."""
from __future__ import annotations

import re
import uuid
from pathlib import Path


class UnsafePathError(ValueError):
    """A path or path component is outside the allowed filesystem boundary."""


_DRIVE_LETTER_RE = re.compile(r"^[A-Za-z]:")


def _validate_part(part: str) -> None:
    if not isinstance(part, str) or not part:
        raise UnsafePathError("path components must be non-empty strings")
    if "\x00" in part:
        raise UnsafePathError("path components must not contain NUL")
    # Backslashes are Windows separators; reject them even on POSIX so a
    # component cannot become traversal when the same data is used elsewhere.
    if "\\" in part:
        raise UnsafePathError("path components must not contain backslashes")
    if Path(part).is_absolute() or _DRIVE_LETTER_RE.match(part):
        raise UnsafePathError("absolute path components are not allowed")


def resolve_within(base: Path, *parts: str) -> Path:
    """Resolve ``parts`` beneath ``base`` without touching the filesystem.

    Raises ``UnsafePathError`` for empty or NUL components, absolute paths,
    Windows drive paths, and any candidate that resolves outside ``base``
    (including through symlinks).
    """
    if not parts:
        raise UnsafePathError("at least one path component is required")
    for part in parts:
        _validate_part(part)

    resolved_base = Path(base).resolve()
    candidate = resolved_base.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_base):
        raise UnsafePathError("path resolves outside the allowed base")
    return candidate


def require_uuid(value: str, field: str) -> str:
    """Return a canonical lowercase UUID or raise ``ValueError``.

    Only the canonical hyphenated form is accepted; UUID's alternate input
    forms (URN, braces, no hyphens, underscores) are rejected.
    """
    if not isinstance(value, str):
        raise ValueError(f"Invalid {field}: must be a UUID")
    try:
        parsed = uuid.UUID(value)
    except (AttributeError, ValueError):
        raise ValueError(f"Invalid {field}: must be a UUID") from None
    canonical = str(parsed)
    if canonical != value.lower():
        raise ValueError(f"Invalid {field}: must be a canonical UUID")
    return canonical
