"""JobPilot FastAPI application entry point."""

from __future__ import annotations

import json
import logging
import logging.config
import time
from collections import defaultdict
from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from fastapi.responses import JSONResponse

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
from .routers.coach_conversation import router as coach_conversation_router
from .routers.settings import router as settings_router
from .routers.system import router as system_router
from .routers.tailor import router as tailor_router
from .routers.gap_analysis import router as gap_analysis_router
from .routers.scoring import router as scoring_router
from .routers.async_jobs import router as async_jobs_router
from .routers.debug import router as debug_router
from .routers.outcome_learning import router as outcome_learning_router
from .routers.app_lock import router as app_lock_router
from .routers.setup import router as setup_router
from .routers.company_watchlist import router as company_watchlist_router
from .routers.documents import router as documents_router
from .routers.question_bank import router as question_bank_router
from .scrapers.scheduler import create_scheduler
from .services.agent_orchestrator import AgentOrchestrator
from .services.llm_client import LLMClient
from .services.job_classifier import JobClassifier
from .services.job_service import JobService
from .services.email_generator import EmailGenerator
from .services.reminder_service import ReminderService
from .services.ai_setup import feature_enabled, load_runtime
from .observability import (
    initialize_telemetry,
    instrument_fastapi_app,
    shutdown_telemetry,
)

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

    # Recover Coach-owned claims only after the global restart fence makes every
    # abandoned running job terminal and visible to the shared reconciler.
    try:
        from .services.coach_reconciliation import (  # noqa: PLC0415
            reconcile_stale_coach_state,
        )

        # One bounded entry point covers legacy and conversational Coach claims.
        recovered = await reconcile_stale_coach_state(batch_size=100)
        if recovered:
            logger.warning("Recovered %d stale Coach async states.", recovered)
    except Exception:
        logger.exception(
            "Coach startup reconciliation failed; lazy recovery remains enabled."
        )

    # Build a long-lived DB session for the scheduler's JobService
    scheduler_session = AsyncSessionLocal()
    scheduler_repo = JobRepository(scheduler_session)
    scheduler_service = JobService(scheduler_repo)

    reminder_repo = ApplicationRepository(scheduler_session)

    ai_configured = load_runtime().get("ai_mode") != "not_configured"

    # AI classifier — provider-agnostic via llm_factory. Keep it disabled when
    # easy install has no AI configuration so background jobs do not fail.
    job_classifier = JobClassifier() if ai_configured else None

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
    orchestrator = (
        AgentOrchestrator(db_factory=AsyncSessionLocal) if ai_configured else None
    )
    if orchestrator is not None:
        orchestrator.start()
    app.state.orchestrator = orchestrator
    logger.info(
        "Agent orchestrator %s.",
        "started" if orchestrator else "disabled until AI setup",
    )

    # ── Startup context assertion (llamacpp only) ─────────────────
    try:
        from .agents.tools.context_checker import assert_context_budgets  # noqa: PLC0415
        from .agents.tools.profile_loader import load_profile  # noqa: PLC0415

        _profile = load_profile()
        await assert_context_budgets(_profile.llm)
    except Exception:
        logger.debug(
            "Context budget check skipped (profile not loaded or non-llamacpp)."
        )

    try:
        yield  # Application running
    finally:
        # Shutdown
        logger.info("JobPilot shutting down...")
        if orchestrator is not None:
            orchestrator.stop()
        scheduler.shutdown(wait=False)
        await scheduler_session.close()
        shutdown_telemetry(deadline_seconds=5.0)
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


class ConversationalRawPathBoundaryMiddleware(BaseHTTPMiddleware):
    """Reject only encoded-separator command/live paths before route matching."""

    _PREFIX = b"/api/coach/sessions/"
    _SUFFIXES = {"POST": b"/commands", "GET": b"/live"}

    async def dispatch(self, request: StarletteRequest, call_next):
        suffix = self._SUFFIXES.get(request.method)
        raw_path = request.scope.get("raw_path", b"")
        if isinstance(raw_path, bytes) and suffix is not None:
            candidate = raw_path.split(b"?", 1)[0]
            normalized, has_encoded_separator = _normalize_encoded_separators(candidate)
            if (
                has_encoded_separator
                and normalized.startswith(self._PREFIX)
                and normalized.endswith(suffix)
            ):
                from .routers.coach_conversation import (  # noqa: PLC0415
                    conversation_error_response,
                )

                return conversation_error_response("coach_contract_unsupported")
        return await call_next(request)


def _normalize_encoded_separators(raw_path: bytes) -> tuple[bytes, bool]:
    """Collapse any nested percent-encoded slash or backslash in one pass."""
    normalized = bytearray()
    found = False
    cursor = 0
    while cursor < len(raw_path):
        if raw_path[cursor] != ord("%"):
            normalized.append(raw_path[cursor])
            cursor += 1
            continue
        terminal_start = cursor + 1
        while raw_path[terminal_start : terminal_start + 2] == b"25":
            terminal_start += 2
        terminal = raw_path[terminal_start : terminal_start + 2].lower()
        if terminal in (b"2f", b"5c"):
            normalized.append(ord("/"))
            found = True
            cursor = terminal_start + 2
            continue
        normalized.extend(raw_path[cursor:terminal_start])
        cursor = terminal_start
    if not found:
        return raw_path, False
    return bytes(normalized), True


def _request_media_type(request: StarletteRequest) -> str:
    return request.headers.get("content-type", "").split(";", 1)[0].strip().lower()


def _validation_body_bytes(body: object) -> bytes | None:
    if isinstance(body, bytes):
        return body
    if isinstance(body, str):
        try:
            return body.encode("utf-8")
        except UnicodeEncodeError:
            return None
    return None


def _hex_value(character: int) -> int | None:
    if ord("0") <= character <= ord("9"):
        return character - ord("0")
    lowered = character | 0x20
    if ord("a") <= lowered <= ord("f"):
        return lowered - ord("a") + 10
    return None


def _form_component_equals(
    raw_body: bytes, start: int, end: int, expected: bytes
) -> bool:
    """Compare one form component after strict, allocation-free decoding."""
    raw_cursor = start
    expected_cursor = 0
    while raw_cursor < end:
        character = raw_body[raw_cursor]
        if character == ord("%"):
            if raw_cursor + 2 >= end:
                return False
            high = _hex_value(raw_body[raw_cursor + 1])
            low = _hex_value(raw_body[raw_cursor + 2])
            if high is None or low is None:
                return False
            character = high * 16 + low
            raw_cursor += 3
        else:
            if character == ord("+"):
                character = ord(" ")
            raw_cursor += 1
        if expected_cursor >= len(expected) or character != expected[expected_cursor]:
            return False
        expected_cursor += 1
    return expected_cursor == len(expected)


def _single_conversational_form_discriminator(raw_body: bytes) -> bool:
    """Find exactly one v1 form discriminator without parsing unrelated values."""
    discriminator_count = 0
    discriminator_matches = False
    field_start = 0
    while field_start <= len(raw_body):
        field_end = raw_body.find(b"&", field_start)
        if field_end == -1:
            field_end = len(raw_body)
        equals_at = raw_body.find(b"=", field_start, field_end)
        if equals_at == -1:
            key_end = field_end
            value_start = field_end
        else:
            key_end = equals_at
            value_start = equals_at + 1
        if _form_component_equals(
            raw_body, field_start, key_end, b"experience_version"
        ):
            discriminator_count += 1
            if discriminator_count > 1:
                return False
            discriminator_matches = _form_component_equals(
                raw_body,
                value_start,
                field_end,
                b"conversational_v1",
            )
        if field_end == len(raw_body):
            break
        field_start = field_end + 1
    return discriminator_count == 1 and discriminator_matches


def _conversational_create_discriminator(
    request: StarletteRequest, body: object
) -> bool:
    """Recognize one bounded, unambiguous v1 discriminator without retaining content."""
    media_type = _request_media_type(request)
    parsed_body: object = body
    if media_type == "application/json" or media_type.endswith("+json"):
        if not isinstance(parsed_body, Mapping):
            raw_body = _validation_body_bytes(parsed_body)
            if raw_body is None:
                return False
            try:
                parsed_body = json.loads(raw_body)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return False
        return (
            isinstance(parsed_body, Mapping)
            and parsed_body.get("experience_version") == "conversational_v1"
        )

    raw_body = _validation_body_bytes(parsed_body)
    if raw_body is None:
        return False
    if media_type != "application/x-www-form-urlencoded":
        try:
            possible_json = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        else:
            if isinstance(possible_json, Mapping):
                return possible_json.get("experience_version") == "conversational_v1"
    return _single_conversational_form_discriminator(raw_body)


def _is_malformed_conversational_create(
    request: StarletteRequest, error: RequestValidationError
) -> bool:
    """Classify only the v1 conversational create discriminator without echoing input."""
    return (
        request.method == "POST"
        and request.url.path == "/api/coach/sessions"
        and _conversational_create_discriminator(request, error.body)
    )


def _known_conversational_create_validation_code(
    request: StarletteRequest,
    error: RequestValidationError,
) -> str | None:
    """Allowlist a known model-level error without rendering validation input."""
    if not _is_malformed_conversational_create(request, error):
        return None
    expected_location = ("body", "conversational_config", "evidence_selection")
    for detail in error.errors():
        if not isinstance(detail, Mapping) or detail.get("type") != "value_error":
            continue
        location = detail.get("loc")
        if not isinstance(location, (list, tuple)) or tuple(location) != (
            expected_location
        ):
            continue
        context = detail.get("ctx")
        if not isinstance(context, Mapping):
            continue
        validation_error = context.get("error")
        if type(validation_error) is ValueError and validation_error.args == (
            "coach_draft_evidence_consent_required",
        ):
            return "coach_draft_evidence_consent_required"
    return None


_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AISetupGateMiddleware(BaseHTTPMiddleware):
    """Return an actionable response when a disabled feature needs an LLM."""

    _PREFIX_FEATURES = {
        "/api/tailor": "cv_tailoring",
        "/api/coach": "coach_interview_prep",
        "/api/scoring": "cv_tailoring",
    }

    async def dispatch(self, request: StarletteRequest, call_next):
        if request.method in _MUTATING_METHODS:
            for prefix, feature in self._PREFIX_FEATURES.items():
                if request.url.path.startswith(prefix) and not feature_enabled(feature):
                    return JSONResponse(
                        {
                            "detail": "AI is not configured for this feature.",
                            "code": "ai_setup_required",
                            "next_step": "Open Settings > AI Setup or run hatch apply-ai-config.",
                        },
                        status_code=409,
                    )
        return await call_next(request)


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
        if request.method == "GET" and request.url.path == "/api/app-lock/status":
            return await call_next(request)
        if request.url.path.startswith("/api/"):
            auth = request.headers.get("Authorization", "")
            if auth != f"Bearer {self._token}":
                from fastapi.responses import JSONResponse  # noqa: PLC0415

                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)


class AppLockMiddleware(BaseHTTPMiddleware):
    """Require a valid server-side app-lock session for product routes and APIs."""

    _PUBLIC_PATHS = {
        "/api/health",
        "/api/healthz",
        "/api/app-lock/status",
        "/api/app-lock/setup",
        "/api/app-lock/unlock",
    }

    @staticmethod
    def _is_public_locale_metadata(request: StarletteRequest) -> bool:
        path = request.url.path
        return request.method == "GET" and (
            path == "/api/v2/locales" or path.startswith("/api/v2/locales/")
        )

    @staticmethod
    def _is_onboarding_resume_upload(request: StarletteRequest) -> bool:
        return request.method == "POST" and request.url.path == "/api/resume/upload"

    @staticmethod
    def _is_bootstrap_setup_request(request: StarletteRequest) -> bool:
        """Allow only non-secret setup intent and diagnostic operations."""
        path = request.url.path
        if request.method == "GET":
            return path in {
                "/api/setup/status",
                "/api/setup/hardware",
                "/api/setup/models/catalog",
                "/api/setup/models/recommendations",
                "/api/setup/models/discovery",
                "/api/setup/capabilities",
                "/api/setup/doctor",
                "/api/setup/providers",
            }
        if request.method == "POST":
            return path in {
                "/api/setup/hardware",
                "/api/setup/ai-mode",
                "/api/setup/experience",
                "/api/setup/local-model-selection",
                "/api/setup/cloud-provider",
                "/api/setup/provider/test",
                "/api/setup/skip-ai",
                "/api/setup/onboarding/progress",
            }
        if request.method == "PATCH":
            return path == "/api/setup/intent"
        return False

    async def dispatch(self, request: StarletteRequest, call_next):
        if not settings.HATCH_APP_LOCK_ENABLED or request.method == "OPTIONS":
            return await call_next(request)
        path = request.url.path
        if (
            path in self._PUBLIC_PATHS
            or self._is_public_locale_metadata(request)
            or self._is_bootstrap_setup_request(request)
            or path.startswith("/static/")
        ):
            return await call_next(request)
        should_protect = path.startswith("/api/") or path in {
            "/docs",
            "/redoc",
            "/openapi.json",
        }
        if not should_protect:
            return await call_next(request)
        from fastapi.responses import JSONResponse  # noqa: PLC0415
        from .services.app_lock_service import AppLockService  # noqa: PLC0415
        from .services.onboarding_service import OnboardingService  # noqa: PLC0415

        token = request.cookies.get(settings.HATCH_APP_SESSION_COOKIE)
        session_factory = getattr(
            request.app.state, "app_lock_session_factory", AsyncSessionLocal
        )
        async with session_factory() as db:
            lock_service = AppLockService(db)
            session = await lock_service.session(token)
            allow_onboarding_upload = False
            bootstrap_state_failed = False
            if session is None and self._is_onboarding_resume_upload(request):
                try:
                    configured_source = await lock_service.configured_source()
                    onboarding = await OnboardingService(db).status()
                    allow_onboarding_upload = (
                        configured_source == "none" and onboarding.status != "complete"
                    )
                except Exception:
                    logger.exception("Unable to verify onboarding resume-upload state")
                    await db.rollback()
                    bootstrap_state_failed = True
            if not bootstrap_state_failed:
                await db.commit()
        if allow_onboarding_upload:
            return await call_next(request)
        if session is None:
            return JSONResponse({"detail": "Hatch is locked."}, status_code=423)
        return await call_next(request)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance.
    """
    telemetry = initialize_telemetry(settings)
    _debug = settings.LOG_LEVEL.upper() == "DEBUG"
    app = FastAPI(
        title="Hatch API",
        description="Autonomous multi-agent job search — profile-driven, human-in-the-loop.",
        version="2.0.0",
        docs_url="/docs",
        redoc_url="/redoc" if _debug else None,
        lifespan=lifespan,
    )
    instrument_fastapi_app(app, telemetry)
    app.state.app_lock_session_factory = AsyncSessionLocal

    @app.exception_handler(RequestValidationError)
    async def redact_conversational_command_validation(
        request: StarletteRequest, error: RequestValidationError
    ) -> JSONResponse:
        """Keep strict conversational command validation free of client echoes."""
        known_create_code = _known_conversational_create_validation_code(request, error)
        if (
            (
                request.url.path.startswith("/api/coach/sessions/")
                and request.url.path.endswith("/commands")
            )
            or known_create_code is not None
            or _is_malformed_conversational_create(request, error)
        ):
            from .routers.coach_conversation import (  # noqa: PLC0415
                conversation_error_response,
            )

            return conversation_error_response(
                known_create_code or "coach_contract_unsupported"
            )
        return await request_validation_exception_handler(request, error)

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
    app.add_middleware(ConversationalRawPathBoundaryMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,  # bearer token in Authorization header; no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "Authorization"],
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(AISetupGateMiddleware)
    app.add_middleware(AppLockMiddleware)
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
    app.include_router(coach_conversation_router)
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
    app.include_router(system_router)
    app.include_router(scoring_router)
    app.include_router(async_jobs_router)
    app.include_router(debug_router)
    app.include_router(outcome_learning_router)
    app.include_router(app_lock_router)
    app.include_router(setup_router)
    app.include_router(company_watchlist_router)
    app.include_router(documents_router)
    app.include_router(question_bank_router)

    return app


app = create_app()
