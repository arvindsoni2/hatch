"""Setup control-plane reset operations for local Hatch workspaces."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import Base
from .. import models as _models  # noqa: F401 - register all ORM tables

ResetMode = Literal["onboarding", "demo", "factory"]

PRESERVED_TABLES = {"app_lock_config", "app_lock_sessions", "onboarding_state"}
RESET_FILE_NAMES = (
    "langgraph_checkpoints.db",
    "langgraph_checkpoints.db-shm",
    "langgraph_checkpoints.db-wal",
)
PROFILE_FILE_NAMES = (
    "master_cv.json",
    "master_cv.meta.json",
    "master_resume.txt",
    "master_resume.pdf",
    "master_resume.docx",
)
RESET_DIR_NAMES = ("generated", "recordings", "uploads")


def data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "./data"))


def resettable_tables() -> list[str]:
    return [
        table.name
        for table in Base.metadata.sorted_tables
        if table.name not in PRESERVED_TABLES
    ]


async def reset_preview(db: AsyncSession, mode: ResetMode, *, preserve_profile: bool = False) -> dict[str, Any]:
    if mode == "factory":
        return {
            "mode": mode,
            "can_apply": False,
            "requires_confirmation": True,
            "deletes": ["application database", "documents", "runtime cache"],
            "preserves": ["api_keys.env unless --delete-secrets is used"],
            "counts": {"database": {}, "files": {}},
            "fallback_command": "bash scripts/reset-user-data.sh --yes --delete-secrets",
            "warning": "Factory reset requires an explicit host-side destructive command.",
        }

    database_counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        if table.name in PRESERVED_TABLES:
            continue
        database_counts[table.name] = int(await db.scalar(select(func.count()).select_from(table)) or 0)

    root = data_dir()
    files = {name: int((root / name).exists()) for name in RESET_FILE_NAMES}
    if not preserve_profile:
        files.update({name: int((root / name).exists()) for name in PROFILE_FILE_NAMES})
    files.update({
        f"{name}/": len(list((root / name).iterdir())) if (root / name).is_dir() else 0
        for name in RESET_DIR_NAMES
    })
    if not preserve_profile:
        files["profile.yaml"] = int((root / "profile.yaml").exists())

    deletes = resettable_tables() + [name for name, count in files.items() if count > 0]
    preserves = [
        "app_lock_config",
        "app_lock_sessions",
        "onboarding_state",
        "api_keys.env",
        "hardware probe cache",
        "installed runtime and model files",
    ]
    if preserve_profile:
        preserves.append("profile.yaml and Master CV/profile files")

    return {
        "mode": mode,
        "can_apply": True,
        "requires_confirmation": True,
        "deletes": deletes,
        "preserves": preserves,
        "counts": {"database": database_counts, "files": files},
        "fallback_command": None,
        "warning": "This clears local Hatch workspace data but preserves host-owned secrets.",
    }


async def apply_reset(
    db: AsyncSession,
    mode: ResetMode,
    *,
    confirmation: str,
    preserve_profile: bool = False,
) -> dict[str, Any]:
    if confirmation != "RESET":
        raise ValueError("Type RESET to confirm this workspace reset.")
    if mode == "factory":
        raise ValueError("Factory reset must be run from the host CLI with explicit destructive intent.")

    preview = await reset_preview(db, mode, preserve_profile=preserve_profile)

    for table in reversed(Base.metadata.sorted_tables):
        if table.name in PRESERVED_TABLES:
            continue
        await db.execute(delete(table))

    if mode == "onboarding":
        from .onboarding_service import OnboardingService

        await OnboardingService(db).reset_progress()

    _clear_files(preserve_profile=preserve_profile)
    return {"applied": True, "mode": mode, "preview": preview}


def _clear_files(*, preserve_profile: bool) -> None:
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)

    for dirname in RESET_DIR_NAMES:
        directory = root / dirname
        if directory.is_dir():
            for child in directory.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)

    for name in RESET_FILE_NAMES:
        (root / name).unlink(missing_ok=True)

    if preserve_profile:
        return

    for name in PROFILE_FILE_NAMES:
        (root / name).unlink(missing_ok=True)

    example = root / "profile.yaml.example"
    profile = root / "profile.yaml"
    if example.exists():
        shutil.copyfile(example, profile)
    else:
        profile.unlink(missing_ok=True)
