"""Profile CRUD API — read, write, validate, and check profile.yaml."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
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

router = APIRouter(prefix="/api/v2/profile", tags=["profile"])


@router.get("", response_model=dict[str, Any])
async def get_profile() -> dict[str, Any]:
    """Return the current profile.yaml as a raw dict."""
    if not profile_exists():
        return {}
    return load_profile_raw()


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
