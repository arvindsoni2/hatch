"""Profile CRUD API — read, write, validate, and check profile.yaml."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from langchain.chat_models import init_chat_model
from pydantic import ValidationError

from ..agents.tools.profile_loader import invalidate_cache
from ..schemas.profile import Profile
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

    Builds the LLM client with the submitted api_key directly — never mutates
    os.environ, eliminating the global-state race condition in async context.
    Returns {ok: bool, error?: str}.
    """
    provider: str = data.get("provider", "anthropic")
    api_key: str = data.get("api_key", "")
    model_map = {
        "anthropic": "claude-haiku-4-5-20251001",
        "openai": "gpt-4o-mini",
        "google": "gemini-2.0-flash",
        "azure": "gpt-4o-mini",
        "ollama": "phi3:mini",
    }
    model_name = model_map.get(provider, "claude-haiku-4-5-20251001")

    try:
        kwargs: dict[str, Any] = {"temperature": 0.0, "max_retries": 1}
        if api_key and provider != "ollama":
            kwargs["api_key"] = api_key
        if provider == "ollama":
            from ..agents.tools.profile_loader import load_profile as _lp
            from ..config import settings as _settings
            try:
                kwargs["base_url"] = _lp().llm.base_url or _settings.OLLAMA_BASE_URL
            except Exception:
                kwargs["base_url"] = _settings.OLLAMA_BASE_URL
        llm = init_chat_model(model=model_name, model_provider=provider, **kwargs)
        await llm.ainvoke("Reply with the single word OK.")
        return {"ok": True}
    except Exception as exc:
        logger.debug("LLM connection test failed: %s", exc)
        return {"ok": False, "error": str(exc)}
