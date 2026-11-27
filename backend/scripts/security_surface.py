"""Generate the route rows for docs/architecture/SECURITY_SURFACE.md.

The committed inventory is the source of truth for the contract test; this
script only prints the generated columns so the table can be refreshed.
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from fastapi.routing import APIRoute  # noqa: E402
from starlette.routing import Mount, WebSocketRoute  # noqa: E402

from app.main import app  # noqa: E402

DEFAULTS = {
    "app.routers.analytics": "DB read",
    "app.routers.app_lock": "DB read",
    "app.routers.applications": "DB write",
    "app.routers.async_jobs": "DB read",
    "app.routers.agents": "DB read",
    "app.routers.coach": "DB read",
    "app.routers.coach_conversation": "DB read",
    "app.routers.coach_readiness": "DB read",
    "app.routers.company_watchlist": "DB read",
    "app.routers.debug": "Memory read",
    "app.routers.digest": "DB read",
    "app.routers.documents": "DB read",
    "app.routers.emails": "DB read",
    "app.routers.events": "DB read",
    "app.routers.gap_analysis": "DB read",
    "app.routers.ghost": "DB read",
    "app.routers.interviews": "DB read",
    "app.routers.interviews_ical": "DB read; template",
    "app.routers.jobs": "DB read",
    "app.routers.locales": "File read",
    "app.routers.outcome_learning": "DB read",
    "app.routers.profile": "File read",
    "app.routers.question_bank": "DB read",
    "app.routers.resume": "File read",
    "app.routers.scoring": "DB read",
    "app.routers.settings": "File read",
    "app.routers.setup": "File read",
    "app.routers.stories": "DB read",
    "app.routers.system": "File read",
    "app.routers.tailor": "DB read",
    "fastapi.applications": "Read",
}

OVERRIDES = {
    ("app.routers.agents", "trigger_agent"): "Background model/outbound; DB write",
    ("app.routers.agents", "pause_agent"): "Memory write",
    ("app.routers.agents", "resume_agent"): "Memory write",
    ("app.routers.agents", "approve_application"): "DB write",
    ("app.routers.agents", "reject_application"): "DB write",
    ("app.routers.agents", "update_application_notes"): "DB write",
    ("app.routers.agents", "rate_limit_status"): "Memory read",
    ("app.routers.app_lock", "setup"): "DB write",
    ("app.routers.app_lock", "unlock"): "DB write",
    ("app.routers.app_lock", "lock"): "DB write",
    ("app.routers.app_lock", "change_password"): "DB write",
    ("app.routers.applications", "list_applications"): "DB read",
    ("app.routers.applications", "get_kanban"): "DB read",
    ("app.routers.applications", "get_all_next_actions"): "DB read",
    ("app.routers.applications", "export_applications"): "DB read",
    ("app.routers.applications", "get_follow_up_reminders"): "DB read; file read",
    ("app.routers.applications", "get_application"): "DB read",
    ("app.routers.applications", "get_application_package"): "DB read; file read",
    ("app.routers.applications", "track_from_job"): "DB write",
    ("app.routers.applications", "create_application"): "DB write",
    ("app.routers.applications", "create_manual_application"): "DB write",
    ("app.routers.applications", "update_application"): "DB write",
    ("app.routers.applications", "update_application_status"): "DB write",
    ("app.routers.applications", "add_note"): "DB write",
    ("app.routers.applications", "prepare_application"): "DB write; model call; file write; subprocess",
    ("app.routers.applications", "mark_applied"): "DB write",
    ("app.routers.applications", "reject_application"): "DB write",
    ("app.routers.applications", "revert_application"): "DB write",
    ("app.routers.applications", "delete_application"): "DB write",
    ("app.routers.coach", "research_company"): "Outbound; model call; DB write",
    ("app.routers.coach", "create_session"): "DB write; async model call",
    ("app.routers.coach", "retry_session"): "DB write; async model call",
    ("app.routers.coach", "submit_answer"): "DB write; async model call",
    ("app.routers.coach", "submit_audio"): "File write; DB write; async model call",
    ("app.routers.coach", "end_session"): "DB write; async model call",
    ("app.routers.coach", "abandon_session"): "DB write",
    ("app.routers.coach", "skip_question"): "DB write",
    ("app.routers.coach", "plan_followup_session"): "DB read/write",
    ("app.routers.coach", "get_capabilities"): "File read",
    ("app.routers.coach", "synthesise_question"): "DB read; subprocess",
    ("app.routers.coach_conversation", "execute_command"): "DB read/write; queues model work",
    ("app.routers.coach_conversation", "export_conversational_report"): "DB read; template",
    ("app.routers.coach_conversation", "request_hard_deletion"): "DB write; queued file delete",
    ("app.routers.coach_conversation", "upload_attempt_audio"): "File write; DB write",
    ("app.routers.coach_readiness", "put_coverage_overrides"): "DB read/write; background model call",
    ("app.routers.coach_readiness", "get_coverage_overview"): "DB read; background model call",
    ("app.routers.coach_readiness", "get_coverage"): "DB read; background model call",
    ("app.routers.coach_readiness", "extract_debrief_notes"): "DB read; model call",
    ("app.routers.coach_readiness", "put_debrief"): "DB write",
    ("app.routers.coach_readiness", "skip_debrief"): "DB write",
    ("app.routers.coach_readiness", "accept_debrief_proposal"): "DB write",
    ("app.routers.coach_readiness", "dismiss_readiness_pattern"): "DB write",
    ("app.routers.coach_readiness", "undo_readiness_pattern_dismissal"): "DB write",
    ("app.routers.coach_readiness", "create_focus_area"): "DB write",
    ("app.routers.coach_readiness", "patch_focus_area"): "DB write",
    ("app.routers.coach_readiness", "create_plan"): "DB write",
    ("app.routers.coach_readiness", "start_plan"): "DB write",
    ("app.routers.coach_readiness", "patch_plan_item"): "DB write",
    ("app.routers.coach_readiness", "delete_memory_kind"): "DB write",
    ("app.routers.coach_readiness", "delete_all_memory"): "DB write",
    ("app.routers.coach_readiness", "request_pattern_tips"): "DB read/write; outbound model call",
    ("app.routers.coach_readiness", "get_interview_brief"): "DB read/write; outbound model call",
    ("app.routers.coach_readiness", "retry_interview_brief_tips"): "DB read/write; outbound model call",
    ("app.routers.coach_readiness", "get_model_tiers"): "File read",
    ("app.routers.company_watchlist", "create_company"): "DB write",
    ("app.routers.company_watchlist", "update_company"): "DB write",
    ("app.routers.company_watchlist", "delete_company"): "DB write",
    ("app.routers.company_watchlist", "scan_company"): "DB write; outbound",
    ("app.routers.debug", "list_llm_traces"): "Memory read",
    ("app.routers.debug", "clear_llm_traces"): "Memory write",
    ("app.routers.debug", "runtime_status"): "Outbound",
    ("app.routers.digest", "preview_digest"): "DB read; template",
    ("app.routers.digest", "send_digest"): "DB read; template; outbound (SMTP)",
    ("app.routers.digest", "digest_status"): "Config read",
    ("app.routers.digest", "update_digest_settings"): "File read/write",
    ("app.routers.documents", "export_pdf"): "DB write; file read/write; subprocess",
    ("app.routers.documents", "download_asset"): "DB read; file read",
    ("app.routers.emails", "update_email"): "DB write; template",
    ("app.routers.emails", "generate_email"): "DB write; async model call",
    ("app.routers.emails", "send_email"): "DB write; outbound (SMTP) or mailto",
    ("app.routers.emails", "skip_email"): "DB write",
    ("app.routers.emails", "regenerate_email"): "DB write; model call",
    ("app.routers.events", "retry_event"): "DB write",
    ("app.routers.ghost", "get_job_ghost_score"): "DB read/write",
    ("app.routers.ghost", "analyse_job"): "DB write; background DB write",
    ("app.routers.ghost", "analyse_all"): "DB read; background DB write",
    ("app.routers.ghost", "override_verdict"): "DB write",
    ("app.routers.interviews", "create_interview"): "DB write",
    ("app.routers.interviews", "update_interview"): "DB write",
    ("app.routers.interviews", "complete_interview"): "DB write",
    ("app.routers.interviews", "delete_interview"): "DB write",
    ("app.routers.interviews", "create_follow_up"): "DB write",
    ("app.routers.interviews", "complete_follow_up"): "DB write",
    ("app.routers.jobs", "health_check"): "File read",
    ("app.routers.jobs", "preview_job_url"): "Outbound; DB read",
    ("app.routers.jobs", "save_imported_job"): "DB write",
    ("app.routers.jobs", "trigger_all_scrapers"): "Outbound; DB write",
    ("app.routers.jobs", "trigger_single_scraper"): "Outbound; DB write",
    ("app.routers.jobs", "update_job"): "DB write",
    ("app.routers.jobs", "delete_job"): "DB write",
    ("app.routers.jobs", "rescore_unscored"): "DB read/write",
    ("app.routers.jobs", "run_archive"): "DB read/write",
    ("app.routers.jobs", "unarchive"): "DB write",
    ("app.routers.jobs", "approve_job"): "DB write; async model call; file write; subprocess",
    ("app.routers.outcome_learning", "recompute"): "DB write",
    ("app.routers.outcome_learning", "backfill"): "DB write",
    ("app.routers.outcome_learning", "reset"): "DB write; file write",
    ("app.routers.profile", "update_profile"): "File write; DB write",
    ("app.routers.profile", "validate_profile"): "None",
    ("app.routers.profile", "test_llm_connection"): "Outbound",
    ("app.routers.question_bank", "create_item"): "DB write",
    ("app.routers.question_bank", "from_interview_answer"): "DB write",
    ("app.routers.question_bank", "update_item"): "DB write",
    ("app.routers.question_bank", "delete_item"): "DB write",
    ("app.routers.resume", "upload_resume"): "File write; parser; model call",
    ("app.routers.resume", "confirm_cv"): "File write",
    ("app.routers.settings", "save_api_key"): "None (410)",
    ("app.routers.settings", "list_ollama_models"): "Outbound",
    ("app.routers.settings", "set_ollama_model"): "File write",
    ("app.routers.setup", "patch_intent"): "File write",
    ("app.routers.setup", "onboarding_progress"): "DB write",
    ("app.routers.setup", "finalize_onboarding"): "DB write; file write",
    ("app.routers.setup", "setup_status"): "DB read",
    ("app.routers.setup", "model_discovery"): "File read/write; outbound",
    ("app.routers.setup", "set_ai_mode"): "File write",
    ("app.routers.setup", "set_experience"): "File write",
    ("app.routers.setup", "select_local_models"): "File write",
    ("app.routers.setup", "select_cloud_provider"): "File write",
    ("app.routers.setup", "test_provider_connection"): "Outbound; file write",
    ("app.routers.setup", "skip_ai"): "File write",
    ("app.routers.setup", "preview_reset"): "DB read; file read",
    ("app.routers.setup", "apply_setup_reset"): "DB write; file delete/write",
    ("app.routers.stories", "create_story"): "DB write",
    ("app.routers.stories", "update_story"): "DB write",
    ("app.routers.stories", "delete_story"): "DB write",
    ("app.routers.stories", "rate_story"): "DB write",
    ("app.routers.stories", "record_story_use"): "DB write",
    ("app.routers.tailor", "list_templates"): "File read",
    ("app.routers.tailor", "recommend_resume_templates"): "File read",
    ("app.routers.tailor", "quality_precheck"): "File read",
    ("app.routers.tailor", "set_default_template"): "File write",
    ("app.routers.tailor", "analyse_job"): "DB write; async model call",
    ("app.routers.tailor", "analyse_jd_text"): "DB write; async model call; outbound",
    ("app.routers.tailor", "generate_cv"): "DB write; async model call; file write; subprocess",
    ("app.routers.tailor", "generate_cover_letter"): "DB write; async model call; file write; subprocess",
    ("app.routers.tailor", "generate_all"): "DB write; async model call; file write; subprocess",
    ("app.routers.tailor", "stream_generation"): "Model call; file write; subprocess",
    ("app.routers.tailor", "download_document"): "DB read; file read",
    ("app.routers.tailor", "ats_optimise"): "DB read; model call",
    ("fastapi.applications", "openapi"): "Read",
    ("fastapi.applications", "swagger_ui_html"): "Template",
    ("fastapi.applications", "swagger_ui_redirect"): "Template",
}

ALWAYS_PUBLIC = {
    ("GET", "/api/health"),
    ("GET", "/api/app-lock/status"),
    ("POST", "/api/app-lock/setup"),
    ("POST", "/api/app-lock/unlock"),
}
BOOTSTRAP_GET = {
    "/api/setup/status",
    "/api/setup/hardware",
    "/api/setup/models/catalog",
    "/api/setup/models/recommendations",
    "/api/setup/models/discovery",
    "/api/setup/capabilities",
    "/api/setup/doctor",
    "/api/setup/providers",
}
BOOTSTRAP_POST = {
    "/api/setup/hardware",
    "/api/setup/ai-mode",
    "/api/setup/experience",
    "/api/setup/local-model-selection",
    "/api/setup/cloud-provider",
    "/api/setup/provider/test",
    "/api/setup/skip-ai",
    "/api/setup/onboarding/progress",
}
BOOTSTRAP_PATCH = {"/api/setup/intent"}


def _auth(method: str, path: str) -> str:
    if (method, path) in {("GET", "/api/health"), ("GET", "/api/app-lock/status")}:
        return "None (exempt)"
    if path.startswith("/api/"):
        return "Bearer (optional)"
    return "None (non-API)"


def _app_lock(method: str, path: str, *, before_setup: bool) -> str:
    if (method, path) in ALWAYS_PUBLIC:
        return "Public"
    if method == "GET" and (
        path == "/api/v2/locales" or path.startswith("/api/v2/locales/")
    ):
        return "Public"
    if method == "GET" and path in BOOTSTRAP_GET:
        return "Public"
    if method == "POST" and path in BOOTSTRAP_POST:
        return "Public"
    if method == "PATCH" and path in BOOTSTRAP_PATCH:
        return "Public"
    if (method, path) == ("POST", "/api/resume/upload"):
        return "Public*" if before_setup else "Session"
    return "Locked" if before_setup else "Session"


def _limit(path: str) -> str:
    if path == "/api/resume/upload":
        return "10 MB"
    if path.endswith("/submit-audio"):
        return "50 MB"
    if "/attempts/" in path and path.endswith("/audio"):
        return "50 MB (configurable)"
    return "None"


def _effect(module: str, endpoint: str) -> str:
    return OVERRIDES.get((module, endpoint), DEFAULTS[module])


def _routes():
    rows = []
    seen: set[tuple[str, str]] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if isinstance(route, APIRoute) or methods:
            pairs = [(method, route.path) for method in sorted(methods or ())]
        elif isinstance(route, WebSocketRoute):
            pairs = [("WS", route.path)]
        elif isinstance(route, Mount):
            pairs = [("MOUNT", route.path)]
        else:
            continue
        for method, path in pairs:
            if (method, path) in seen:
                continue
            seen.add((method, path))
            rows.append((method, path, route))
    return rows


def main() -> None:
    print(
        "| Method | Path | Router module | Auth dependency | App lock before setup | "
        "App lock after setup | Body/upload limit | Effect |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for method, path, route in _routes():
        endpoint = getattr(route, "endpoint", None)
        module = getattr(endpoint, "__module__", "fastapi.applications")
        name = getattr(endpoint, "__name__", type(route).__name__)
        print(
            f"| {method} | `{path}` | `{module}` | {_auth(method, path)} | "
            f"{_app_lock(method, path, before_setup=True)} | "
            f"{_app_lock(method, path, before_setup=False)} | "
            f"{_limit(path)} | {_effect(module, name)} |"
        )


if __name__ == "__main__":
    main()
