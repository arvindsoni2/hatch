"""Profile CRUD API — read, write, validate, and check profile.yaml."""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import ValidationError

from ..agents.tools.profile_loader import invalidate_cache
from ..agents.tools.llm_factory import get_triage_model
from ..schemas.profile import Profile
from ..services.locale_service import list_locales
from ..services.profile_service import (
    load_profile,
    load_profile_raw,
    profile_exists,
    save_profile_raw,
    validate_profile_data,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v2/profile", tags=["profile"])


@router.get("", response_model=dict[str, Any])
async def get_profile() -> dict[str, Any]:
    """Return the current profile.yaml as a raw dict, with job_boards derived from locale."""
    if not profile_exists():
        return {}
    data = load_profile_raw()
    locale_id = data.get("locale", "uk")
    try:
        from ..services.locale_service import get_job_boards as _get_boards
        locale_boards = _get_boards(locale_id, enabled_only=False)
        data["job_boards"] = [
            {
                "name": b["name"],
                "enabled": b.get("enabled", True),
                "scraper": b.get("scraper", ""),
                "search_params": b.get("search_params", {}),
            }
            for b in locale_boards
        ]
    except Exception:
        pass
    return data


@router.get("/validated", response_model=Profile)
async def get_validated_profile() -> Profile:
    """Return the profile parsed and validated against the Pydantic schema."""
    if not profile_exists():
        raise HTTPException(status_code=404, detail="profile.yaml not found — run onboarding first")
    return load_profile()


@router.put("", response_model=dict[str, Any])
async def update_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Replace profile.yaml with the submitted data. Validates before writing."""
    errors = validate_profile_data(data)
    if errors:
        raise HTTPException(status_code=422, detail={"validation_errors": errors})
    profile = save_profile_raw(data)
    invalidate_cache()
    return profile.model_dump()


@router.post("/validate", response_model=dict[str, Any])
async def validate_profile(data: dict[str, Any]) -> dict[str, Any]:
    """Dry-run validate profile data without saving."""
    errors = validate_profile_data(data)
    return {"valid": len(errors) == 0, "errors": errors}


@router.get("/status")
async def profile_status() -> dict[str, Any]:
    """Return whether profile exists and if it has enough data to run agents."""
    if not profile_exists():
        return {"exists": False, "complete": False, "onboarding_required": True}
    try:
        profile = load_profile()
        complete = profile.is_complete()
    except ValidationError as exc:
        return {
            "exists": True,
            "complete": False,
            "onboarding_required": True,
            "errors": [e["msg"] for e in exc.errors()],
        }
    return {
        "exists": True,
        "complete": complete,
        "onboarding_required": not complete,
        "candidate_name": profile.candidate.name,
        "llm_provider": profile.llm.provider,
        "target_roles": profile.search.target_roles,
    }


@router.post("/test-connection")
async def test_llm_connection(data: dict[str, Any]) -> dict[str, Any]:
    """Test that the LLM API key / provider in the submitted profile config is valid.

    Temporarily sets the relevant env var, makes a minimal LLM call, then
    restores the env. Returns {ok: bool, error?: str}.
    """
    provider: str = data.get("provider", "anthropic")
    api_key: str = data.get("api_key", "")
    env_var_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "google": "GOOGLE_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
    }
    env_var = env_var_map.get(provider)
    original: str | None = None

    try:
        if env_var and api_key:
            original = os.environ.get(env_var)
            os.environ[env_var] = api_key

        llm = get_triage_model()
        await llm.ainvoke("Reply with the single word OK.")
        return {"ok": True}
    except Exception as exc:
        logger.debug("LLM connection test failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    finally:
        if env_var and original is not None:
            os.environ[env_var] = original
        elif env_var and api_key:
            os.environ.pop(env_var, None)
