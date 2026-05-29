"""Resume store — persist and retrieve the candidate's master resume text.

Provides a simple file-backed store for the full resume text used during
semantic scoring.  Falls back to synthesising text from profile.yaml if no
CV file has been uploaded yet.

The module-level embedding cache avoids repeated embed() calls within a
single process lifecycle.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Storage paths ──────────────────────────────────────────────────────────────

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
RESUME_TEXT_FILE = DATA_DIR / "master_resume.txt"

# Module-level embedding cache: key = resume text (or sentinel), value = embedding
_embedding_cache: dict[str, list[float]] = {}
_CACHE_KEY = "__resume__"


# ── Lazy import of embedder (avoids hard import-time crash if ST not installed) ──

def _get_embed_fn():  # type: ignore[return]
    """Import embed from embedder module, raising RuntimeError if unavailable."""
    try:
        from ..agents.tools.embedder import embed  # type: ignore[import]
        return embed
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers is required for embedding. "
            "Install with: pip install sentence-transformers>=3.0"
        ) from exc


# Allow tests to patch the name `embed` in this module's namespace
def embed(text: str) -> list[float]:
    """Delegate to embedder.embed — importable name for mocking in tests."""
    fn = _get_embed_fn()
    return fn(text)


# ── Public API ─────────────────────────────────────────────────────────────────


def save_resume_text(text: str) -> None:
    """Persist resume text to disk and invalidate the embedding cache.

    Args:
        text: Full plain-text content of the candidate's CV.
    """
    path = _resolve_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    # Invalidate cached embedding so next get_resume_embedding() recomputes
    _embedding_cache.clear()
    logger.debug("Resume text saved (%d chars) to %s", len(text), path)


def get_resume_text() -> str:
    """Return the stored resume text, or synthesise from profile if absent.

    Returns:
        Resume text as a plain string.
    """
    path = _resolve_path()
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read resume file %s: %s", path, exc)

    # Fallback: synthesise from profile
    logger.info("No resume file found at %s — synthesising from profile.", path)
    return synthesise_from_profile()


def synthesise_from_profile() -> str:
    """Build a representative resume text from the loaded profile.

    Concatenates: title, summary, proof_points, skills, certifications,
    and target_roles.  This gives the semantic scorer something meaningful
    to embed when no CV has been uploaded.

    Returns:
        Multi-line plain-text representation of the profile.
    """
    from ..agents.tools.profile_loader import load_profile

    try:
        profile = load_profile()
    except Exception as exc:
        logger.warning("Could not load profile for synthesis: %s", exc)
        return ""

    parts: list[str] = []

    # Candidate headline
    if profile.candidate.title:
        parts.append(profile.candidate.title)
    if profile.candidate.summary:
        parts.append(profile.candidate.summary)

    # Proof points
    for pp in profile.proof_points:
        if hasattr(pp, "summary") and pp.summary:
            parts.append(pp.summary)

    # Skills
    primary = list(profile.skills.primary)
    secondary = list(profile.skills.secondary)
    if primary or secondary:
        all_skills = primary + secondary
        parts.append("Skills: " + ", ".join(all_skills))

    # Certifications
    certs = list(profile.skills.certifications)
    if certs:
        parts.append("Certifications: " + ", ".join(certs))

    # Target roles
    roles = list(profile.search.target_roles)
    if roles:
        parts.append("Target roles: " + ", ".join(roles))

    return "\n".join(parts)


def get_resume_embedding() -> list[float]:
    """Return the embedding vector for the current resume text.

    The result is cached in-process so repeated calls do not re-embed.
    Cache is invalidated when save_resume_text() is called.

    Returns:
        List of floats (384-dim for all-MiniLM-L6-v2).

    Raises:
        RuntimeError: If sentence-transformers is not installed.
    """
    if _CACHE_KEY in _embedding_cache:
        return _embedding_cache[_CACHE_KEY]

    text = get_resume_text()
    embedding = embed(text)
    _embedding_cache[_CACHE_KEY] = embedding
    return embedding


def _resolve_path() -> Path:
    """Resolve the resume text file path, respecting DATA_DIR env var."""
    base = Path(os.getenv("DATA_DIR", "")) or DATA_DIR
    if not base:
        base = DATA_DIR
    # Re-evaluate each call so tests can change DATA_DIR via os.environ
    data_dir_env = os.getenv("DATA_DIR")
    if data_dir_env:
        return Path(data_dir_env) / "master_resume.txt"
    return RESUME_TEXT_FILE
