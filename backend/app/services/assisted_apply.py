"""AssistedApplyService — prepares tailored CV and cover letter for a job application.

This service ONLY prepares documents for human review.
It does NOT submit anything, fill forms, or post to job boards.
The user always makes the final click.

Status flow: approved → preparing → ready_to_apply
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# profile_loader is imported lazily inside prepare_application to avoid
# circular imports at module load time; it is bound here for testability.
try:
    from ..agents.tools.profile_loader import load_profile
except Exception:  # pragma: no cover — only fails in isolated unit test contexts
    load_profile = None  # type: ignore[assignment]

# Skills directory (relative to this file's package root)
_SKILLS_DIR = Path(__file__).parent.parent / "skills"


@dataclass
class ApplicationPackage:
    """Bundle of prepared application materials ready for human review."""

    job_id: str
    job_url: str
    cv_path: str | None         # path to generated tailored CV (.docx), or None if unavailable
    cover_letter_path: str | None
    prefill_map: dict[str, str] = field(default_factory=dict)   # name, email, phone from profile
    screening_answers: dict[str, str] = field(default_factory=dict)  # knockout Q answers
    paste_map: dict[str, str] = field(default_factory=dict)          # ATS form field labels → values


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers — screening answers
# ─────────────────────────────────────────────────────────────────────────────

_LOCALE_MAP = {
    "en-GB": "uk",
    "en-gb": "uk",
    "en-IN": "in",
    "en-in": "in",
    "en-AE": "ae",
    "en-ae": "ae",
}


def _normalise_locale(raw: str) -> str:
    return _LOCALE_MAP.get(raw, raw.lower())


def _build_screening_answers(profile: object, skill_loader: object) -> dict[str, str]:
    """Generate knockout-question answers from profile + knockout_patterns.yaml.

    Returns empty dict on any failure so prepare_application stays graceful.
    """
    try:
        import yaml  # type: ignore[import-untyped]

        content = skill_loader.resource("screening-answers", "knockout_patterns.yaml")
        patterns: dict = yaml.safe_load(content)

        raw_locale = (
            getattr(getattr(profile, "preferences", None), "locale", None) or "uk"
        )
        locale = _normalise_locale(raw_locale)
        locale_patterns: dict = patterns.get(locale, patterns.get("uk", {}))

        compensation = getattr(profile, "compensation", None)
        min_rate = getattr(compensation, "min_rate", 0) or 0
        max_rate = getattr(compensation, "max_rate", 0) or 0
        currency = getattr(compensation, "currency", "GBP") or "GBP"

        try:
            locs_raw = getattr(getattr(profile, "search", None), "locations", [])
            locations = list(locs_raw) if isinstance(locs_raw, (list, tuple)) else []
        except Exception:
            locations = []
        city = str(getattr(locations[0], "city", "") or "") if locations else ""
        remote_pref = str(
            getattr(locations[0], "remote_preference", "hybrid") or "hybrid"
        ) if locations else "hybrid"

        # Gather legal_preferences for work_auth template selection + notice_period override
        legal_prefs: dict = {}
        try:
            lp = getattr(getattr(profile, "compensation", None), "legal_preferences", {})
            if isinstance(lp, dict):
                legal_prefs = lp
        except Exception:
            pass

        answers: dict[str, str] = {}
        for key, ptn in locale_patterns.items():
            # top-level default, or fallback to templates["default"] if present
            top_default: str = ptn.get("default", "")
            nested_templates: dict = ptn.get("templates", {})
            default: str = top_default or nested_templates.get("default", "")
            template: str = ptn.get("template", "")

            if key in ("expected_rate", "expected_salary", "expected_ctc"):
                if template and min_rate:
                    answer = template.replace("{min_rate}", str(int(min_rate)))
                    answer = answer.replace("{max_rate}", str(int(max_rate)))
                    answer = answer.replace("{currency}", currency)
                else:
                    answer = default
            elif key == "relocation":
                tmpl = nested_templates.get(remote_pref, nested_templates.get("hybrid", default))
                answer = tmpl.replace("{city}", city) if city else tmpl
            elif key == "work_authorisation":
                # Use legal_preferences.work_authorization to select the right template
                auth_status = legal_prefs.get("work_authorization", "")
                answer = nested_templates.get(auth_status, "") or default
            elif key == "notice_period":
                # Use legal_preferences.notice_period if present, else YAML default
                np_value = legal_prefs.get("notice_period", "")
                answer = np_value if np_value else default
            else:
                answer = default

            if answer:
                answers[key] = answer

        return answers
    except Exception as exc:
        logger.debug("screening_answers build failed (non-fatal): %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers — profile path resolver
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_profile_path(profile: object, path: str) -> str:
    """Walk a dotted+indexed path like 'candidate.email' or 'search.locations[0].city'.

    Returns '' on any failure so callers stay graceful.
    """
    try:
        current: object = profile
        for token in path.split("."):
            m = re.match(r'^(\w+)\[(\d+)\]$', token)
            if m:
                attr_name, idx = m.group(1), int(m.group(2))
                container = getattr(current, attr_name, None)
                if container is None:
                    return ""
                try:
                    current = container[idx]
                except (IndexError, TypeError):
                    return ""
            else:
                current = getattr(current, token, None)
                if current is None:
                    return ""
        return str(current) if current is not None else ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers — paste map
# ─────────────────────────────────────────────────────────────────────────────


def _detect_ats(job_url: str) -> str | None:
    """Return ATS name from job URL, or None if unrecognised."""
    url = job_url.lower()
    if "greenhouse.io" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "ashby" in url:
        return "ashby"
    if "myworkday" in url or "workday.com" in url:
        return "workday"
    return None


def _build_paste_map(
    job_url: str,
    prefill_map: dict[str, str],
    screening_answers: dict[str, str],
    skill_loader: object,
    profile: object = None,
) -> dict[str, str]:
    """Generate a form-field label → value map for the detected ATS.

    Returns empty dict on any failure.
    """
    ats = _detect_ats(job_url)
    if not ats:
        return {}

    try:
        import yaml  # type: ignore[import-untyped]

        content = skill_loader.resource("form-mapping", f"{ats}.yaml")
        schema: dict = yaml.safe_load(content)

        # Legacy resolvers: built from prefill_map, cover first_name/last_name/email/phone
        name_parts = prefill_map.get("name", "").split()
        first_name = name_parts[0] if name_parts else ""
        last_name = name_parts[-1] if len(name_parts) > 1 else ""
        legacy_resolvers: dict[str, str] = {
            "first_name": first_name,
            "last_name": last_name,
            "name": prefill_map.get("name", ""),
            "email": prefill_map.get("email", ""),
            "phone": prefill_map.get("phone", ""),
        }

        # Flatten Workday multi-step schema (steps[].fields[]) into a single field list
        if "steps" in schema and "fields" not in schema:
            all_fields: list = []
            for step in schema.get("steps", []):
                all_fields.extend(step.get("fields", []))
        else:
            all_fields = schema.get("fields", [])

        paste_map: dict[str, str] = {}
        for fld in all_fields:
            source = fld.get("source", "")
            label = fld.get("label", "")
            field_id = fld.get("field_id", "")
            path = fld.get("path", "")

            if source == "profile_field":
                # Try profile path resolution first; fall back to legacy dict
                value = ""
                if path and profile is not None:
                    value = _resolve_profile_path(profile, path)
                if not value:
                    value = legacy_resolvers.get(field_id, "")
                # Apply YAML transforms
                transform = fld.get("transform", "")
                if transform == "first_word" and value:
                    value = value.split()[0]
                elif transform == "last_word" and value:
                    parts = value.split()
                    value = parts[-1] if len(parts) > 1 else value
                if value:
                    paste_map[label] = value
            elif source == "screening_answer":
                screening_key = fld.get("screening_key", "")
                value = screening_answers.get(screening_key, "")
                if value:
                    paste_map[label] = value

        return paste_map
    except Exception as exc:
        logger.debug("paste_map build failed (non-fatal): %s", exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────


class AssistedApplyService:
    """Prepares application documents (CV + cover letter) for a specific job.

    IMPORTANT: This service has NO submit(), NO browser_fill(), and makes NO
    HTTP POST requests to any job board. It only returns document paths and
    prefill data so the user can review everything before applying themselves.
    """

    async def prepare_application(
        self,
        job_id: str,
        db: AsyncSession,
    ) -> ApplicationPackage:
        """Tailor CV + cover letter for this job; return paths and prefill map.

        Steps:
        1. Load job from DB
        2. Load user profile
        3. Build prefill_map (name, email if present, phone etc.)
        4. Attempt tailor service for CV + CL (graceful fallback on failure)
        5. Build screening_answers from screening-answers skill
        6. Build paste_map from form-mapping skill
        7. Update application status to "ready_to_apply"
        8. Return ApplicationPackage

        Args:
            job_id: UUID of the job posting to prepare for.
            db: Active async DB session.

        Returns:
            ApplicationPackage with cv_path, cover_letter_path, job_url,
            prefill_map, screening_answers, paste_map.
        """
        from sqlalchemy import select, update
        from datetime import datetime

        from ..models.job import JobPosting
        from ..models.application import Application

        # 1. Load job
        job_result = await db.execute(
            select(JobPosting).where(JobPosting.id == job_id)
        )
        job = job_result.scalar_one_or_none()
        job_url = job.url if job else ""

        # 2. Load profile (module-level reference for easy mocking in tests)
        try:
            _lp = load_profile
            profile = _lp() if callable(_lp) else None
            name = getattr(getattr(profile, "candidate", None), "name", None) or ""
            email_val = getattr(getattr(profile, "candidate", None), "email", None)
            phone_val = getattr(getattr(profile, "candidate", None), "phone", None)
        except Exception:
            profile = None
            name = ""
            email_val = None
            phone_val = None

        # 3. Build prefill_map
        prefill_map: dict[str, str] = {}
        if name:
            prefill_map["name"] = name
        if email_val:
            prefill_map["email"] = str(email_val)
        if phone_val:
            prefill_map["phone"] = str(phone_val)

        # 4. Mark status as "preparing"
        await db.execute(
            update(Application)
            .where(Application.job_id == job_id)
            .values(status="preparing", updated_at=datetime.utcnow())
        )

        # 5. Attempt to tailor CV + CL (wrap gracefully)
        cv_path: str | None = None
        cover_letter_path: str | None = None

        try:
            from ..services.tailor_service import TailorService

            tailor = TailorService()
            if job is not None:
                jd_text = job.description or f"{job.title} at {job.company}"
                result = await tailor.generate_all(
                    job_id=job_id,
                    jd_text=jd_text,
                )
                cv_path = getattr(result, "cv_path", None)
                cover_letter_path = getattr(result, "cover_letter_path", None)
        except Exception as exc:
            logger.warning(
                "Tailor service unavailable for job %s, continuing without docs: %s",
                job_id,
                exc,
            )

        # 6. Build screening_answers + paste_map using SkillLoader
        screening_answers: dict[str, str] = {}
        paste_map: dict[str, str] = {}

        try:
            from ..skills.skill_loader import SkillLoader, SkillRegistry

            skill_loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
            if profile is not None:
                screening_answers = _build_screening_answers(profile, skill_loader)
            paste_map = _build_paste_map(job_url, prefill_map, screening_answers, skill_loader, profile)
        except Exception as exc:
            logger.debug("Skill assembly failed (non-fatal): %s", exc)

        # 7. Update status to "ready_to_apply" + store doc paths
        update_values: dict = {
            "status": "ready_to_apply",
            "updated_at": datetime.utcnow(),
        }
        if cv_path:
            update_values["cv_version"] = cv_path
        if cover_letter_path:
            update_values["cover_letter_version"] = cover_letter_path

        await db.execute(
            update(Application)
            .where(Application.job_id == job_id)
            .values(**update_values)
        )
        await db.commit()

        return ApplicationPackage(
            job_id=job_id,
            job_url=job_url,
            cv_path=cv_path,
            cover_letter_path=cover_letter_path,
            prefill_map=prefill_map,
            screening_answers=screening_answers,
            paste_map=paste_map,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # NOTE: There is intentionally NO submit() method here.
    # NOTE: There is intentionally NO browser_fill() method here.
    # NOTE: There are NO HTTP requests to job board URLs.
    # The user is ALWAYS in control of the final submission click.
    # ─────────────────────────────────────────────────────────────────────────
