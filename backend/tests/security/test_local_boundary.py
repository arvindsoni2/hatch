"""Security contracts for the browser-to-localhost boundary (H2)."""
from __future__ import annotations

import asyncio
import hmac
import time
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.database import Base
from app.main import (
    AuthMiddleware,
    RateLimitMiddleware,
    TrustedHostMiddleware,
    app,
)
from app.models.app_lock import AppLockConfig
from app.routers.app_lock import _set_cookie
from app.services import profile_service
from app.services.app_lock_service import AppLockError, AppLockService


def _auth_app(token: str) -> FastAPI:
    inner = FastAPI()

    @inner.get("/api/protected")
    async def protected():
        return {"ok": True}

    inner.add_middleware(AuthMiddleware, token=token)
    return inner


def _request(scheme: str, forwarded_proto: str | None = None) -> Request:
    headers = []
    if forwarded_proto is not None:
        headers.append((b"x-forwarded-proto", forwarded_proto.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "headers": headers,
            "scheme": scheme,
            "server": ("localhost", 80),
            "client": ("127.0.0.1", 123),
        }
    )


async def _call_next(request: Request) -> Response:
    return Response("ok")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_url",
    [
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1:8000",
        "http://[::1]:3000",
        "http://backend:8000",
        "http://frontend:3000",
    ],
)
async def test_trusted_hosts_are_accepted(base_url: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=base_url
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("host", ["evil.example", "evil.example:3000"])
async def test_untrusted_host_is_rejected(host: str) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url=f"http://{host}"
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 400
    assert response.json()["code"] == "untrusted_host"


@pytest.mark.asyncio
async def test_host_header_with_multiple_values_is_rejected() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.get(
            "/api/health", headers={"host": "localhost,evil.example"}
        )

    assert response.status_code == 400
    assert response.json()["code"] == "untrusted_host"


@pytest.mark.asyncio
async def test_configured_extra_host_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "HATCH_TRUSTED_HOSTS",
        f"{settings.HATCH_TRUSTED_HOSTS},proxy.example",
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://proxy.example:8443"
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_untrusted_host_is_rejected_before_auth() -> None:
    inner = FastAPI()

    @inner.get("/api/protected")
    async def protected():
        return {"ok": True}

    inner.add_middleware(AuthMiddleware, token="boundary-token")
    inner.add_middleware(TrustedHostMiddleware)

    async with AsyncClient(
        transport=ASGITransport(app=inner), base_url="http://evil.example:3000"
    ) as client:
        rejected = await client.get("/api/protected")

    async with AsyncClient(
        transport=ASGITransport(app=inner), base_url="http://localhost"
    ) as client:
        unauthorized = await client.get("/api/protected")

    assert rejected.status_code == 400
    assert rejected.json()["code"] == "untrusted_host"
    assert unauthorized.status_code == 401


@pytest.mark.asyncio
async def test_cross_site_origin_is_rejected_for_mutations(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/setup/onboarding/progress",
        json={"step_id": "skills"},
        headers={"Origin": "http://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


@pytest.mark.asyncio
async def test_allowed_origin_passes_for_mutations(client: AsyncClient) -> None:
    response = await client.post(
        "/api/setup/onboarding/progress",
        json={"step_id": "skills"},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_cross_site_fetch_metadata_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/setup/onboarding/progress",
        json={"step_id": "skills"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "origin_not_allowed"


@pytest.mark.asyncio
@pytest.mark.parametrize("fetch_site", ["same-origin", "none"])
async def test_same_origin_or_none_fetch_metadata_passes(
    client: AsyncClient, fetch_site: str
) -> None:
    response = await client.post(
        "/api/setup/onboarding/progress",
        json={"step_id": "skills"},
        headers={"Sec-Fetch-Site": fetch_site},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_requests_without_origin_headers_pass(client: AsyncClient) -> None:
    response = await client.post(
        "/api/setup/onboarding/progress",
        json={"step_id": "skills"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_is_not_subject_to_origin_check(client: AsyncClient) -> None:
    response = await client.get(
        "/api/health",
        headers={"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"},
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_equal_length_wrong_bearer_is_rejected_through_compare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[bytes, bytes]] = []
    real_compare = hmac.compare_digest

    def recording_compare(left, right):
        calls.append((bytes(left), bytes(right)))
        return real_compare(left, right)

    monkeypatch.setattr("app.main.hmac.compare_digest", recording_compare)
    app_with_auth = _auth_app("supersecret")

    async with AsyncClient(
        transport=ASGITransport(app=app_with_auth), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/protected",
            headers={"Authorization": "Bearer wrongsecret"},
        )

    assert response.status_code == 401
    assert calls


def test_cookie_ignores_forwarded_proto_from_untrusted_client() -> None:
    response = Response()
    _set_cookie(response, _request("http", "https"), "session-token")

    assert "secure" not in response.headers["set-cookie"].lower()


def test_cookie_is_secure_when_request_scheme_is_https() -> None:
    response = Response()
    _set_cookie(response, _request("https"), "session-token")

    assert "secure" in response.headers["set-cookie"].lower()


@pytest.mark.asyncio
@pytest.mark.app_lock
@pytest.mark.parametrize(
    "method,path,body",
    [
        ("POST", "/api/setup/hardware", None),
        ("POST", "/api/setup/ai-mode", {"ai_mode": "not_configured"}),
        ("POST", "/api/setup/experience", {"experience": "essential"}),
        ("POST", "/api/setup/local-model-selection", {"selected_model_ids": []}),
        ("POST", "/api/setup/cloud-provider", {"provider": "anthropic"}),
        ("POST", "/api/setup/provider/test", {"provider": "anthropic"}),
        ("POST", "/api/setup/skip-ai", None),
        ("POST", "/api/setup/onboarding/progress", {"step_id": "skills"}),
        ("PATCH", "/api/setup/intent", {"ai_mode": "not_configured"}),
    ],
)
async def test_mutating_bootstrap_setup_routes_require_session_after_setup(
    client: AsyncClient,
    db_session: AsyncSession,
    method: str,
    path: str,
    body: dict | None,
) -> None:
    setup = await client.post(
        "/api/app-lock/setup", json={"password": "safe-password-1"}
    )
    assert setup.status_code == 200
    await db_session.commit()
    client.cookies.clear()

    response = await client.request(method, path, json=body)

    assert response.status_code == 423


@pytest.mark.asyncio
@pytest.mark.app_lock
@pytest.mark.parametrize(
    "path",
    [
        "/api/setup/status",
        "/api/setup/providers",
        "/api/setup/models/discovery",
    ],
)
async def test_onboarding_get_routes_remain_public_after_setup(
    client: AsyncClient, db_session: AsyncSession, path: str
) -> None:
    setup = await client.post(
        "/api/app-lock/setup", json={"password": "safe-password-1"}
    )
    assert setup.status_code == 200
    await db_session.commit()
    client.cookies.clear()

    response = await client.get(path)

    assert response.status_code != 423


@pytest.mark.asyncio
@pytest.mark.app_lock
@pytest.mark.parametrize(
    "path",
    [
        "/api/setup/hardware",
        "/api/setup/models/catalog",
        "/api/setup/models/recommendations",
        "/api/setup/capabilities",
        "/api/setup/doctor",
    ],
)
async def test_non_onboarding_get_routes_require_session_after_setup(
    client: AsyncClient, db_session: AsyncSession, path: str
) -> None:
    setup = await client.post(
        "/api/app-lock/setup", json={"password": "safe-password-1"}
    )
    assert setup.status_code == 200
    await db_session.commit()
    client.cookies.clear()

    response = await client.get(path)

    assert response.status_code == 423


@pytest.mark.asyncio
@pytest.mark.app_lock
async def test_mutating_bootstrap_setup_routes_work_with_session(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path / "config"))
    setup = await client.post(
        "/api/app-lock/setup", json={"password": "safe-password-1"}
    )
    assert setup.status_code == 200

    progress = await client.post(
        "/api/setup/onboarding/progress", json={"step_id": "skills"}
    )
    intent = await client.patch(
        "/api/setup/intent", json={"ai_mode": "not_configured"}
    )

    assert progress.status_code == 200
    assert intent.status_code == 200


@pytest.mark.asyncio
@pytest.mark.app_lock
async def test_onboarding_password_then_setup_steps_end_to_end(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("HATCH_CONFIG_DIR", str(tmp_path / "config"))
    profile_path = tmp_path / "profile.yaml"
    monkeypatch.setattr(profile_service, "_DEFAULT_PROFILE_PATH", profile_path)

    setup = await client.post(
        "/api/app-lock/setup", json={"password": "safe-password-1"}
    )
    assert setup.status_code == 200

    intent = await client.patch(
        "/api/setup/intent", json={"ai_mode": "not_configured"}
    )
    finalize = await client.post(
        "/api/setup/onboarding/finalize",
        json={
            "finalization_id": str(uuid.uuid4()),
            "profile": {
                "locale": "uk",
                "candidate": {"name": "Ada Lovelace", "title": "Platform Engineer"},
                "search": {
                    "target_roles": ["Platform Engineer"],
                    "locations": [{"city": "London", "country": "GB"}],
                },
            },
        },
    )

    assert intent.status_code == 200
    assert finalize.status_code == 200
    assert profile_path.exists()


@pytest.mark.asyncio
@pytest.mark.app_lock
async def test_bootstrap_mutation_is_public_before_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/setup/onboarding/progress", json={"step_id": "skills"}
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_parallel_wrong_unlocks_cannot_exceed_the_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "HATCH_APP_LOCK_ENABLED", True)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'lock.db'}",
        connect_args={"timeout": 30},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        async with session_factory() as session:
            await AppLockService(session).setup("safe-password-1")
            await session.commit()

        async def wrong_unlock() -> int:
            async with session_factory() as session:
                try:
                    await AppLockService(session).unlock("wrong-password")
                except AppLockError as error:
                    return error.status_code
            return 200

        results = await asyncio.gather(*(wrong_unlock() for _ in range(10)))

        async with session_factory() as session:
            count = await session.scalar(
                select(AppLockConfig.failed_attempt_count)
            )
            try:
                await AppLockService(session).unlock("safe-password-1")
            except AppLockError as error:
                persisted_status = error.status_code
            else:
                persisted_status = 200

        assert count == settings.HATCH_APP_LOCK_FAILED_ATTEMPT_LIMIT
        assert results.count(401) == settings.HATCH_APP_LOCK_FAILED_ATTEMPT_LIMIT
        assert results.count(429) == 10 - settings.HATCH_APP_LOCK_FAILED_ATTEMPT_LIMIT
        assert persisted_status == 429
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rate_limiter_map_is_bounded_and_drops_empty_buckets() -> None:
    async def dummy_app(scope, receive, send):
        return None

    middleware = RateLimitMiddleware(
        dummy_app,
        limit_per_minute=100,
        enabled=True,
        max_clients=3,
    )

    async def dispatch(client_host: str) -> Response:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/mutate",
                "query_string": b"",
                "headers": [],
                "client": (client_host, 123),
                "scheme": "http",
                "server": ("localhost", 80),
            }
        )
        return await middleware.dispatch(request, _call_next)

    middleware._buckets["stale"] = []  # type: ignore[attr-defined]
    for index in range(10):
        response = await dispatch(f"10.0.0.{index}")
        assert response.status_code == 200

    assert len(middleware._buckets) <= 3  # type: ignore[attr-defined]
    assert "stale" not in middleware._buckets  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_rate_limiter_evicts_the_oldest_client() -> None:
    async def dummy_app(scope, receive, send):
        return None

    middleware = RateLimitMiddleware(
        dummy_app,
        limit_per_minute=100,
        enabled=True,
        max_clients=3,
    )
    now = time.monotonic()
    middleware._buckets.update(  # type: ignore[attr-defined]
        {
            "oldest": [now - 30],
            "middle": [now - 20],
            "newest": [now - 10],
        }
    )

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/mutate",
            "query_string": b"",
            "headers": [],
            "client": ("10.0.0.4", 123),
            "scheme": "http",
            "server": ("localhost", 80),
        }
    )
    response = await middleware.dispatch(request, _call_next)

    assert response.status_code == 200
    assert "oldest" not in middleware._buckets  # type: ignore[attr-defined]
    assert "10.0.0.4" in middleware._buckets  # type: ignore[attr-defined]
