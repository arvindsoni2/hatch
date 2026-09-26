"""Claim value validation shared by the durable workflow repository."""

from __future__ import annotations


def require_worker_id(worker_id: str) -> str:
    """Return a stable worker identifier or reject an invalid claimant."""
    normalized = worker_id.strip() if isinstance(worker_id, str) else ""
    if not normalized:
        raise ValueError("worker_id must be a non-empty string")
    if len(normalized) > 128:
        raise ValueError("worker_id must be at most 128 characters")
    return normalized
