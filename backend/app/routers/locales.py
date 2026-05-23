"""Locales API — list available locale packs and their configuration."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..services.locale_service import (
    LocaleNotFoundError,
    get_job_boards,
    get_legal_fields,
    get_locale,
    get_onboarding_defaults,
    list_locales,
)

router = APIRouter(prefix="/api/v2/locales", tags=["locales"])


@router.get("", response_model=list[dict[str, Any]])
async def list_available_locales() -> list[dict[str, Any]]:
    """Return a summary list of installed locale packs (id, name, flag)."""
    return list_locales()


@router.get("/{locale_id}", response_model=dict[str, Any])
async def get_locale_pack(locale_id: str) -> dict[str, Any]:
    """Return the full locale pack for *locale_id*."""
    try:
        return get_locale(locale_id)
    except LocaleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{locale_id}/boards", response_model=list[dict[str, Any]])
async def get_locale_boards(locale_id: str, enabled_only: bool = True) -> list[dict[str, Any]]:
    """Return job board configs for a locale."""
    try:
        get_locale(locale_id)  # raises 404 if unknown
    except LocaleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_job_boards(locale_id, enabled_only=enabled_only)


@router.get("/{locale_id}/legal-fields", response_model=list[dict[str, Any]])
async def get_locale_legal_fields(locale_id: str) -> list[dict[str, Any]]:
    """Return legal/compliance field definitions for the onboarding wizard."""
    try:
        get_locale(locale_id)
    except LocaleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_legal_fields(locale_id)


@router.get("/{locale_id}/onboarding-defaults", response_model=dict[str, Any])
async def get_locale_onboarding_defaults(locale_id: str) -> dict[str, Any]:
    """Return onboarding defaults for a locale."""
    try:
        get_locale(locale_id)
    except LocaleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_onboarding_defaults(locale_id)
