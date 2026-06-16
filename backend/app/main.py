"""JobPilot FastAPI application entry point."""
from __future__ import annotations

import logging
import logging.config
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest

from .config import settings
from .database import AsyncSessionLocal, init_db
from .repositories.application_repository import ApplicationRepository
from .repositories.job_repository import JobRepository
from .routers.agents import router as agents_router
from .routers.locales import router as locales_router
from .routers.profile import router as profile_router
from .routers.analytics import router as analytics_router
from .routers.applications import router as applications_router
from .routers.digest import router as digest_router
from .routers.emails import router as emails_router
from .routers.events import router as events_router
from .routers.resume import router as resume_router
from .routers.ghost import router as ghost_router
from .routers.stories import router as stories_router
from .routers.interviews import router as interviews_router
from .routers.interviews_ical import router as interviews_ical_router
from .routers.jobs import health_router, router as jobs_router
from .routers.coach import router as coach_router
from .routers.settings import router as settings_router
from .routers.tailor import router as tailor_router
from .routers.gap_analysis import router as gap_analysis_router
from .routers.scoring import router as scoring_router
from .routers.async_jobs import router as async_jobs_router
from .routers.debug import router as debug_router
from .routers.outcome_learning import router as outcome_learning_router
from .scrapers.scheduler import create_scheduler
from .services.agent_orchestrator import AgentOrchestrator
from .services.llm_client import LLMClient
from .services.job_classifier import JobClassifier
from .services.job_service import JobService
from .services.email_generator import EmailGenerator
from .services.reminder_service import ReminderService

# ──────────────────────── Logging Setup ────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("jobpilot")


# ──────────────────────── Lifespan ────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: initialise database and start scheduler on startup,
    gracefully shut down scheduler on teardown.
    """
    logger.info("JobPilot starting up...")

    # Initialise database tables
    await init_db()
    logger.info("Database ready.")

    # Reset any jobs left in "running" state from a previous crash
    from sqlalchemy import update as _sa_update  # noqa: PLC0415
    from .models.async_job import AsyncJob as _AsyncJob  # noqa: PLC0415
    from .models.application import Application as _Application  # noqa: PLC0415
    async with AsyncSessionLocal() as _db:
        _r = await _db.execute(
            _sa_update(_AsyncJob)
            .where(_AsyncJob.status == "running")
            .values(status="failed", error="Server restarted while job was in progress")
        )
        if _r.rowcount:
            logger.warning("Reset %d orphaned async jobs to failed.", _r.rowcount)
        _apps = await _db.execute(
            _sa_update(_Application)
            .where(_Application.status == "preparing")
            .values(status="approved")
        )
        if _apps.rowcount:
            logger.warning(
                "Reset %d interrupted application packages to retryable.",
                _apps.rowcount,
            )
        await _db.commit()

    # Build a long-lived DB session for the scheduler's JobService
    scheduler_session = AsyncSessionLocal()
    scheduler_repo = JobRepository(scheduler_session)
    scheduler_service = JobService(scheduler_repo)

    reminder_repo = ApplicationRepository(scheduler_session)

    # AI classifier — provider-agnostic via llm_factory
    job_classifier = JobClassifier()

    # Email generation still uses LLMClient directly (Anthropic-only for now)
    claude_client = LLMClient()
    email_gen = EmailGenerator(claude_client)
    reminder_svc = ReminderService(reminder_repo, email_generator=email_gen)

    # Digest service
    digest_svc = None
    if settings.DIGEST_ENABLED:
        from .services.digest_service import DigestService  # noqa: PLC0415
        digest_svc = DigestService(claude_client)

    scheduler = create_scheduler(
        scheduler_service,
        reminder_service=reminder_svc,
        classifier=job_classifier,
        digest_service=digest_svc,
        db_factory=AsyncSessionLocal,
        email_generator=email_gen,
    )
    scheduler.start()
    logger.info(
        "Scheduler started (full: %dh, quick: %dh, classifier: %dmin).",
        settings.FULL_SCRAPE_INTERVAL_HOURS,
        settings.QUICK_SCRAPE_INTERVAL_HOURS,
        settings.CLASSIFIER_RUN_INTERVAL_MINUTES,
    )

    # ── Agentic orchestrator ──────────────────────────────────────────
    orchestrator = AgentOrchestrator(db_factory=AsyncSessionLocal)
    orchestrator.start()
    app.state.orchestrator = orchestrator
    logger.info("Agent orchestrator started.")

    # ── Startup context assertion (llamacpp only) ─────────────────
    try:
        from .agents.tools.context_checker import assert_context_budgets  # noqa: PLC0415
        from .agents.tools.profile_loader import load_profile  # noqa: PLC0415
        _profile = load_profile()
        await assert_context_budgets(_profile.llm)
    except Exception:
        logger.debug("Context budget check skipped (profile not loaded or non-llamacpp).")

    yield  # Application running

    # Shutdown
    logger.info("JobPilot shutting down...")
    orchestrator.stop()
    scheduler.shutdown(wait=False)
    await scheduler_session.close()
    logger.info("Scheduler stopped. Goodbye.")


# ──────────────────────── App Factory ────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Content-Security-Policy: report-only mode so we catch violations without
        # breaking the app. Switch to Content-Security-Policy once violations are clean.
        # MediaPipe CDN and inline theme bootstrap script must be in the allowlist first.
        csp = (
            "default-src 'self'; "
            "connect-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "media-src 'self' blob:; "
            "frame-ancestors 'none'"
        )
        response.headers["Content-Security-Policy-Report-Only"] = csp
        return response


_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-client token-bucket rate limiter for mutating endpoints.

    Only active when HATCH_AUTH_TOKEN is non-empty (disabled for localhost dev ergonomics).
    Clients are identified by their remote host IP.
    """

    def __init__(self, app, limit_per_minute: int, enabled: bool) -> None:
        super().__init__(app)
        self._limit = limit_per_minute
        self._enabled = enabled
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: StarletteRequest, call_next):
        if not self._enabled or request.method not in _MUTATING_METHODS:
            return await call_next(request)

        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window_start = now - 60.0
        bucket = self._buckets[client]
        # Evict timestamps outside the 1-minute window
        self._buckets[client] = [t for t in bucket if t > window_start]
        if len(self._buckets[client]) >= self._limit:
            from fastapi.responses import JSONResponse  # noqa: PLC0415
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        self._buckets[client].append(now)
        return await call_next(request)


class AuthMiddleware(BaseHTTPMiddleware):
    """Optional bearer-token gate — active only when HATCH_AUTH_TOKEN is non-empty.

    Exemptions: OPTIONS (CORS preflight) and /api/health always pass through.
    All other /api/* paths require Authorization: Bearer <token>.
    """

    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: StarletteRequest, call_next):
        if not self._token:
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if request.url.path in ("/api/health", "/api/healthz"):
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self._token}":
                from fastapi.responses import JSONResponse  # noqa: PLC0415
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance.
    """
    _debug = settings.LOG_LEVEL.upper() == "DEBUG"
    app = FastAPI(
        title="Hatch API",
        description="Autonomous multi-agent job search — profile-driven, human-in-the-loop.",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc" if _debug else None,
        lifespan=lifespan,
    )

    # CORS — origins from ALLOWED_ORIGINS env var (comma-separated), defaults to localhost
    _origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
    if "*" in _origins:
        logger.warning(
            "SECURITY: ALLOWED_ORIGINS contains '*' — restrict to explicit origins in production."
        )
    _loopback_prefixes = ("http://localhost", "http://127.0.0.1", "http://[::1]")
    if not settings.HATCH_AUTH_TOKEN and any(
        not any(o.startswith(p) for p in _loopback_prefixes) for o in _origins
    ):
        logger.warning(
            "SECURITY: ALLOWED_ORIGINS includes non-loopback origins but HATCH_AUTH_TOKEN is "
            "empty. Set HATCH_AUTH_TOKEN to protect your API from unauthenticated access."
        )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,  # bearer token in Authorization header; no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Authorization"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AuthMiddleware, token=settings.HATCH_AUTH_TOKEN)
    app.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.RATE_LIMIT_PER_MINUTE,
        enabled=bool(settings.HATCH_AUTH_TOKEN),  # disabled for localhost dev
    )

    # Routers
    app.include_router(health_router)
    app.include_router(jobs_router)
    app.include_router(gap_analysis_router)
    app.include_router(applications_router)
    app.include_router(interviews_router)
    app.include_router(interviews_ical_router)
    app.include_router(analytics_router)
    app.include_router(tailor_router)
    app.include_router(coach_router)
    app.include_router(digest_router)
    app.include_router(emails_router)
    app.include_router(ghost_router)
    app.include_router(stories_router)
    # Agentic pipeline routers
    app.include_router(agents_router)
    app.include_router(events_router)
    # v2: profile-driven configuration
    app.include_router(profile_router)
    app.include_router(locales_router)
    app.include_router(resume_router)
    app.include_router(settings_router)
    app.include_router(scoring_router)
    app.include_router(async_jobs_router)
    app.include_router(debug_router)
    app.include_router(outcome_learning_router)

    return app


app = create_app()
