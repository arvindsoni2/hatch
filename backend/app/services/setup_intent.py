"""Canonical, locked and atomic setup-intent persistence."""
from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from ..schemas.setup import IntentPatch, SetupIntent

_THREAD_LOCK = threading.RLock()


def _config_dir() -> Path:
    return Path(os.getenv("HATCH_CONFIG_DIR", "/hatch-home/config"))


def _intent_path() -> Path:
    return _config_dir() / "ai_setup_intent.json"


@contextmanager
def _intent_lock(*, create: bool) -> Iterator[None]:
    directory = _config_dir()
    if not directory.exists() and not create:
        with _THREAD_LOCK:
            yield
        return
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = directory / ".ai_setup_intent.lock"
    with _THREAD_LOCK, lock_path.open("a+", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        try:
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass


def _read_raw() -> dict[str, Any]:
    try:
        value = json.loads(_intent_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def _legacy_model_ids(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    values = raw.get("selected_model_ids")
    if not isinstance(values, list):
        return None, None
    ids = [str(value) for value in values if isinstance(value, str)]
    primary = next((value for value in ids if "primary" in value), None)
    triage = next((value for value in ids if "triage" in value), None)
    if len(ids) == 1 and primary is None and triage is None:
        primary = triage = ids[0]
    return primary, triage


def _normalize(raw: dict[str, Any]) -> SetupIntent:
    mode = raw.get("ai_mode", raw.get("aiMode", "not_configured"))
    if mode == "ai-later":
        mode = "none"
    elif mode == "advanced":
        mode = "none"
    if mode not in {"not_configured", "none", "local", "cloud", "custom"}:
        mode = "not_configured"

    profile = raw.get("backend_profile", raw.get("backendProfile", "core"))
    if profile not in {"core", "browser", "local-embeddings", "full"}:
        profile = "core"
    local_primary, local_triage = _legacy_model_ids(raw)
    metadata = raw.get("provider_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}

    values = {
        "schema_version": 2,
        "ai_mode": mode,
        "backend_profile": profile,
        "experience": raw.get("experience", "essential"),
        "local_primary_model": raw.get("local_primary_model", local_primary),
        "local_triage_model": raw.get("local_triage_model", local_triage),
        "cloud_provider": raw.get("cloud_provider", raw.get("provider")),
        "cloud_primary_model": raw.get(
            "cloud_primary_model", metadata.get("primary_model", metadata.get("model"))
        ),
        "cloud_triage_model": raw.get(
            "cloud_triage_model", metadata.get("triage_model", metadata.get("model"))
        ),
        "setup_deferred_at": raw.get("setup_deferred_at"),
        "restart_required": raw.get("restart_required", False),
        "hardware_probe_id": raw.get("hardware_probe_id"),
    }
    if mode == "none" and values["setup_deferred_at"] is None:
        values["setup_deferred_at"] = datetime.utcnow()
    return SetupIntent.model_validate(values)


def _write(intent: SetupIntent) -> None:
    path = _intent_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = intent.model_dump(mode="json")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_setup_intent() -> SetupIntent:
    with _intent_lock(create=False):
        return _normalize(_read_raw())


def patch_setup_intent(patch: IntentPatch) -> SetupIntent:
    with _intent_lock(create=True):
        current = _normalize(_read_raw())
        changes = patch.model_dump(exclude_unset=True)
        if changes.get("ai_mode") == "none" and "setup_deferred_at" not in changes:
            changes["setup_deferred_at"] = datetime.utcnow()
        elif changes.get("ai_mode") not in {None, "none"}:
            changes["setup_deferred_at"] = None
        updated = SetupIntent.model_validate({
            **current.model_dump(),
            **changes,
            "schema_version": 2,
        })
        _write(updated)
        return updated
