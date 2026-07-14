"""App-lock setup, unlock and management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..services.app_lock_service import AppLockError, AppLockService
from ..services.onboarding_service import OnboardingService

router = APIRouter(prefix="/api/app-lock", tags=["app-lock"])


class PasswordRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def _token(request: Request) -> str | None:
    return request.cookies.get(settings.HATCH_APP_SESSION_COOKIE)


def _set_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        settings.HATCH_APP_SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        path="/",
    )


def _raise(exc: AppLockError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


def _onboarding_payload(state) -> dict[str, str | None]:
    return {
        "status": state.status,
        "last_completed_step": state.last_completed_step,
    }


@router.get("/status")
async def status(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    service = AppLockService(db)
    token = _token(request)
    bearer_ok = bool(
        settings.HATCH_AUTH_TOKEN
        and request.headers.get("authorization") == f"Bearer {settings.HATCH_AUTH_TOKEN}"
    )
    lock_status = await service.status(token, include_private=bearer_ok)
    onboarding = await OnboardingService(db).status()
    return {**lock_status, "onboarding": _onboarding_payload(onboarding)}


@router.post("/setup")
async def setup(body: PasswordRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        token = await AppLockService(db).setup(body.password)
    except AppLockError as exc:
        if exc.status_code == 409 and exc.detail == "App lock is already configured.":
            lock_status = await AppLockService(db).status(_token(request))
            onboarding = await OnboardingService(db).status()
            raise HTTPException(
                status_code=409,
                detail=jsonable_encoder({
                    "code": "app_lock_already_configured",
                    "message": exc.detail,
                    "app_lock": lock_status,
                    "onboarding": _onboarding_payload(onboarding),
                }),
            ) from exc
        _raise(exc)
    onboarding = await OnboardingService(db).mark_password_configured()
    _set_cookie(response, request, token)
    return {"unlocked": True, "onboarding": _onboarding_payload(onboarding)}


@router.post("/unlock")
async def unlock(body: PasswordRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        token = await AppLockService(db).unlock(body.password)
    except AppLockError as exc:
        _raise(exc)
    _set_cookie(response, request, token)
    return {"unlocked": True}


@router.post("/lock")
async def lock(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    await AppLockService(db).lock(_token(request))
    response.delete_cookie(settings.HATCH_APP_SESSION_COOKIE, path="/")
    return {"locked": True}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        token = await AppLockService(db).change_password(body.current_password, body.new_password)
    except AppLockError as exc:
        _raise(exc)
    _set_cookie(response, request, token)
    return {"changed": True}
