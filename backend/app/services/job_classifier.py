"""AI batch classifier that enriches job postings with match scores and metadata."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.job import JobPosting
from ..observability import get_telemetry, trace_workflow
from ..prompts import render_prompt
from ..agents.tools.llm_factory import get_triage_model
from ..agents.tools.profile_loader import load_profile
from .prompt_catalog import prompt_contract_block, source_contains

logger = logging.getLogger(__name__)

# The bundled triage server runs two parallel slots in a 4096-token context,
# leaving 2048 tokens per request. Three 500-character job excerpts plus the
# classifier instructions fit below that limit with room for the JSON response.
_MAX_CONTEXT_SAFE_BATCH_SIZE = 3


class JobClassifier:
    """Enriches job postings with AI-classified metadata in batches.

    Uses the triage model from llm_factory so it works with any configured
    provider (Anthropic, OpenAI, Google, Ollama, etc.).
    """

    def __init__(self) -> None:
        pass

    @trace_workflow("job_discovery_import")
    async def classify_batch(self, jobs: list[JobPosting]) -> list[dict]:
        """Classify a batch of jobs in a single LLM call.

        Args:
            jobs: List of JobPosting ORM objects to classify.

        Returns:
            List of classification dicts keyed by job id.
        """
        if not jobs:
            return []

        jobs_payload = [
            {
                "id": job.id,
                "title": job.title,
                "description": (job.description or "")[:500],
                "rate_text": job.rate_text or "",
                "location": job.location or "",
                "employment_type": _known_text_value(job, "employment_type"),
                "ir35_status": _known_text_value(job, "ir35_status"),
                "working_pattern": _known_text_value(job, "working_pattern"),
            }
            for job in jobs
        ]
        profile = load_profile()
        candidate_profile = _runtime_candidate_profile(profile)

        prompt = render_prompt(
            "job_classification.j2",
            jobs_json=json.dumps(jobs_payload, indent=2),
            candidate_profile=candidate_profile,
            prompt_contract=prompt_contract_block("job_classification"),
        )

        # Split on SYSTEM: / USER: markers as used in other prompts
        if "USER:" in prompt:
            parts = prompt.split("USER:", 1)
            system = parts[0].replace("SYSTEM:", "").strip()
            user = parts[1].strip()
        else:
            system = "You are a technical recruiter. Return only valid JSON."
            user = prompt

        json_instruction = "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no code blocks, no explanation."

        try:
            model = get_triage_model()
            messages = [
                SystemMessage(content=system + json_instruction),
                HumanMessage(content=user),
            ]
            started = time.monotonic()
            try:
                response = await model.ainvoke(messages)
            except Exception:
                get_telemetry().record_model_call(
                    workflow="job_discovery_import",
                    provider=type(model).__name__,
                    model_id=str(getattr(model, "model", "configured")),
                    duration_ms=(time.monotonic() - started) * 1000,
                    outcome="failed",
                )
                raise
            else:
                get_telemetry().record_model_call(
                    workflow="job_discovery_import",
                    provider=type(model).__name__,
                    model_id=str(getattr(model, "model", "configured")),
                    duration_ms=(time.monotonic() - started) * 1000,
                )
            text = response.content if isinstance(response.content, str) else str(response.content)

            cleaned = text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            result = json.loads(cleaned)
            # LLM may return {"jobs": [...]} or directly [...]
            items = result if isinstance(result, list) else result.get("jobs", [])
            return _validate_classifications(items, jobs_payload)
        except Exception as exc:
            get_telemetry().mark_current_error(
                "classification_failed",
                "workflow_error",
            )
            logger.error("Batch classify failed (%d jobs): %s", len(jobs), exc)
            return []

    async def run_pending(self, db: AsyncSession) -> int:
        """Fetch unclassified jobs, classify in batches, update the database.

        Args:
            db: Async SQLAlchemy session.

        Returns:
            Number of jobs successfully classified.
        """
        batch_size = min(
            max(settings.CLASSIFIER_BATCH_SIZE, 1),
            _MAX_CONTEXT_SAFE_BATCH_SIZE,
        )
        stmt = (
            select(JobPosting)
            .where(JobPosting.match_score.is_(None))
            .where(JobPosting.is_active.is_(True))
            .limit(batch_size * 3)  # fetch up to 3 context-safe batches
        )
        result = await db.execute(stmt)
        all_jobs = list(result.scalars().all())

        if not all_jobs:
            logger.info("No unclassified jobs to process.")
            return 0

        logger.info("Classifying %d jobs in batches of %d", len(all_jobs), batch_size)
        classified = 0

        for batch_start in range(0, len(all_jobs), batch_size):
            batch = all_jobs[batch_start : batch_start + batch_size]
            classifications = await self.classify_batch(batch)

            if not classifications:
                continue

            # Build lookup by id
            by_id: dict[str, dict] = {c["id"]: c for c in classifications if "id" in c}

            # Wrap each batch's DB writes in a try/rollback so a failed execute
            # never leaves the session in a broken state for the next batch.
            try:
                for job in batch:
                    classification = by_id.get(job.id)
                    if not classification:
                        continue
                    await db.execute(
                        update(JobPosting)
                        .where(JobPosting.id == job.id)
                        .values(
                            employment_type=classification.get("employment_type") or "unknown",
                            ir35_status=classification.get("ir35_status") or "unknown",
                            working_pattern=classification.get("working_pattern") or "unknown",
                            seniority=classification.get("seniority"),
                            match_score=float(classification.get("match_score", 0)) / 100.0,
                            match_reasons=classification.get("match_reasons", []),
                            red_flags=classification.get("red_flags", []),
                        )
                    )
                    classified += 1
                await db.commit()
            except Exception as exc:
                logger.warning(
                    "Failed to persist batch %d-%d, rolling back: %s",
                    batch_start + 1,
                    batch_start + len(batch),
                    exc,
                )
                await db.rollback()
                continue

            logger.info(
                "Classified batch %d-%d (%d/%d done)",
                batch_start + 1,
                batch_start + len(batch),
                classified,
                len(all_jobs),
            )

        return classified


def _runtime_candidate_profile(profile: Any) -> dict[str, Any]:
    """Serialize only the profile fields required for job classification."""
    return {
        "title": profile.candidate.title,
        "years_experience": profile.candidate.years_experience,
        "target_roles": list(profile.search.target_roles),
        "primary_skills": list(profile.skills.primary),
        "secondary_skills": list(profile.skills.secondary),
        "compensation": {
            "currency": profile.compensation.currency,
            "minimum": profile.compensation.min_rate,
            "maximum": profile.compensation.max_rate,
            "rate_type": profile.compensation.rate_type,
        },
        "locations": [
            {
                "city": location.city,
                "country": location.country,
                "remote_preference": location.remote_preference,
            }
            for location in profile.search.locations
        ],
    }


def _known_text_value(job: Any, field: str) -> str:
    """Return a persisted string value without serializing mock/ORM sentinels."""
    value = getattr(job, field, "")
    return value if isinstance(value, str) else ""


def _validate_classifications(
    raw_items: Any,
    jobs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize model classifications against the supplied job batch."""
    if not isinstance(raw_items, list):
        return []
    jobs_by_id = {job["id"]: job for job in jobs}
    enums = {
        "employment_type": {
            "contract",
            "permanent",
            "fixed_term",
            "part_time",
            "freelance",
            "unknown",
        },
        "ir35_status": {"outside", "inside", "not_applicable", "unknown"},
        "working_pattern": {"remote", "hybrid", "onsite", "unknown"},
        "seniority": {
            "junior",
            "mid",
            "senior",
            "lead",
            "principal",
            "head",
            "director",
            None,
        },
    }
    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict) or item.get("id") not in jobs_by_id:
            continue
        job = jobs_by_id[item["id"]]
        job_text = " ".join(
            str(job.get(field) or "")
            for field in (
                "title",
                "description",
                "rate_text",
                "location",
                "employment_type",
                "ir35_status",
                "working_pattern",
            )
        )
        clean = dict(item)
        for field, allowed in enums.items():
            if clean.get(field) not in allowed:
                clean[field] = None if field == "seniority" else "unknown"
        explicit_phrases = {
            "ir35_status": {
                "outside": "outside ir35",
                "inside": "inside ir35",
            },
            "working_pattern": {
                "remote": "remote",
                "hybrid": "hybrid",
                "onsite": "onsite",
            },
        }
        for field, phrases in explicit_phrases.items():
            value = clean.get(field)
            phrase = phrases.get(value)
            persisted_value = job.get(field)
            if (
                phrase
                and persisted_value != value
                and not source_contains(phrase, job_text)
            ):
                clean[field] = "unknown"
        try:
            score = int(clean.get("match_score", 0))
        except (TypeError, ValueError):
            score = 0
        clean["match_score"] = max(0, min(100, score))
        clean["match_reasons"] = [
            str(value)
            for value in clean.get("match_reasons", [])[:3]
            if isinstance(value, str)
        ]
        clean["red_flags"] = [
            str(value)
            for value in clean.get("red_flags", [])
            if isinstance(value, str)
        ]
        normalized.append(clean)
    return normalized
