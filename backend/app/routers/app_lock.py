"""App-lock setup, unlock and management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..services.app_lock_service import AppLockError, AppLockService

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


@router.get("/status")
async def status(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    service = AppLockService(db)
    token = _token(request)
    bearer_ok = bool(
        settings.HATCH_AUTH_TOKEN
        and request.headers.get("authorization") == f"Bearer {settings.HATCH_AUTH_TOKEN}"
    )
    return await service.status(token, include_private=bearer_ok)


@router.post("/setup")
async def setup(body: PasswordRequest, request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        token = await AppLockService(db).setup(body.password)
    except AppLockError as exc:
        _raise(exc)
    _set_cookie(response, request, token)
    return {"unlocked": True}


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
