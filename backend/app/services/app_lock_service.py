"""Secure single-workspace app-lock operations."""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

import bcrypt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.app_lock import AppLockConfig, AppLockSession
from .password_policy import APP_LOCK_PASSWORD_POLICY, validate_new_password


class AppLockError(Exception):
    def __init__(self, detail: str, status_code: int) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.utcnow()


def _session_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


class AppLockService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _config(self, create: bool = False) -> AppLockConfig | None:
        row = await self._db.get(AppLockConfig, 1)
        if row is None and create:
            row = AppLockConfig(id=1)
            self._db.add(row)
            await self._db.flush()
        return row

    async def configured_source(self) -> str:
        if settings.HATCH_APP_PASSWORD:
            return "env"
        row = await self._config()
        return "database" if row and row.password_hash else "none"

    async def cleanup_expired_sessions(self) -> None:
        await self._db.execute(delete(AppLockSession).where(AppLockSession.expires_at <= _utcnow()))

    async def session(self, token: str | None, *, touch: bool = False) -> AppLockSession | None:
        if not settings.HATCH_APP_LOCK_ENABLED or not token:
            return None
        result = await self._db.execute(
            select(AppLockSession).where(
                AppLockSession.session_hash == _session_hash(token),
                AppLockSession.expires_at > _utcnow(),
            )
        )
        row = result.scalar_one_or_none()
        if row and touch:
            row.last_seen_at = _utcnow()
        return row

    async def status(self, token: str | None, *, include_private: bool = False) -> dict:
        source = await self.configured_source()
        session = await self.session(token, touch=False)
        base = {
            "enabled": settings.HATCH_APP_LOCK_ENABLED,
            "configured_source": source,
            "is_configured": source != "none",
            "is_unlocked": not settings.HATCH_APP_LOCK_ENABLED or session is not None,
            "password_policy": APP_LOCK_PASSWORD_POLICY.public(),
        }
        if not include_private and session is None:
            return base
        row = await self._config()
        return {
            **base,
            "last_unlocked_at": row.last_unlocked_at if row else None,
            "last_password_changed_at": row.last_password_changed_at if row else None,
            "failed_attempt_count": row.failed_attempt_count if row else 0,
            "retry_after_seconds": self._retry_after(row),
        }

    async def setup(self, password: str) -> str:
        if not settings.HATCH_APP_LOCK_ENABLED:
            raise AppLockError("App lock is disabled by environment configuration.", 409)
        if settings.HATCH_APP_PASSWORD:
            raise AppLockError("App lock password is controlled by environment configuration.", 409)
        row = await self._config(create=True)
        assert row is not None
        if row.password_hash:
            raise AppLockError("App lock is already configured.", 409)
        try:
            validate_new_password(password)
        except ValueError as exc:
            raise AppLockError(str(exc), 422) from exc
        row.password_hash = _hash_password(password)
        row.last_password_changed_at = _utcnow()
        return await self._create_session(row)

    def _retry_after(self, row: AppLockConfig | None) -> int:
        if (
            not row
            or row.failed_attempt_count < settings.HATCH_APP_LOCK_FAILED_ATTEMPT_LIMIT
            or not row.last_failed_attempt_at
        ):
            return 0
        elapsed = (_utcnow() - row.last_failed_attempt_at).total_seconds()
        return max(0, int(settings.HATCH_APP_LOCK_RETRY_DELAY_SECONDS - elapsed + 0.999))

    async def _password_matches(self, password: str, row: AppLockConfig | None) -> bool:
        if settings.HATCH_APP_PASSWORD:
            return secrets.compare_digest(password, settings.HATCH_APP_PASSWORD)
        return bool(
            row
            and row.password_hash
            and bcrypt.checkpw(password.encode(), row.password_hash.encode())
        )

    async def unlock(self, password: str) -> str:
        if not settings.HATCH_APP_LOCK_ENABLED:
            raise AppLockError("App lock is disabled by environment configuration.", 409)
        row = await self._config(create=True)
        assert row is not None
        retry_after = self._retry_after(row)
        if retry_after:
            raise AppLockError(f"Too many failed attempts. Try again in {retry_after} seconds.", 429)
        if not await self._password_matches(password, row):
            row.failed_attempt_count += 1
            row.last_failed_attempt_at = _utcnow()
            raise AppLockError("Password is incorrect. Please try again.", 401)
        row.failed_attempt_count = 0
        row.last_failed_attempt_at = None
        return await self._create_session(row)

    async def _create_session(self, row: AppLockConfig) -> str:
        # Session creation already requires a write transaction, so this is the
        # safe place to prune expired rows. Status checks remain read-only and
        # cannot fail merely because another worker currently holds SQLite's
        # write lock.
        await self.cleanup_expired_sessions()
        token = secrets.token_urlsafe(32)
        now = _utcnow()
        self._db.add(AppLockSession(
            session_hash=_session_hash(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(hours=settings.HATCH_APP_SESSION_TTL_HOURS),
        ))
        row.last_unlocked_at = now
        await self._db.flush()
        return token

    async def lock(self, token: str | None) -> None:
        if token:
            await self._db.execute(
                delete(AppLockSession).where(AppLockSession.session_hash == _session_hash(token))
            )

    async def change_password(self, current: str, new: str) -> str:
        if settings.HATCH_APP_PASSWORD:
            raise AppLockError("App lock password is controlled by environment configuration.", 409)
        try:
            validate_new_password(new)
        except ValueError as exc:
            raise AppLockError(str(exc), 422) from exc
        row = await self._config(create=True)
        assert row is not None
        if not await self._password_matches(current, row):
            raise AppLockError("Password is incorrect. Please try again.", 401)
        if secrets.compare_digest(current, new):
            raise AppLockError("New password must be different from the current password.", 422)
        row.password_hash = _hash_password(new)
        row.last_password_changed_at = _utcnow()
        await self._db.execute(delete(AppLockSession))
        return await self._create_session(row)

    async def reset(self) -> None:
        row = await self._config()
        if row:
            row.password_hash = None
            row.failed_attempt_count = 0
            row.last_failed_attempt_at = None
            row.last_password_changed_at = None
            row.last_unlocked_at = None
        await self._db.execute(delete(AppLockSession))
