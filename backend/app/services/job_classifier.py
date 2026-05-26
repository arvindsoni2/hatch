"""AI batch classifier that enriches job postings with match scores and metadata."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models.job import JobPosting
from ..prompts import render_prompt
from .llm_factory import get_triage_model

logger = logging.getLogger(__name__)

_PROFILE_PATH = Path(__file__).parent.parent / "templates" / "candidate_profile.json"


class JobClassifier:
    """Enriches job postings with AI-classified metadata in batches.

    Uses the triage model from llm_factory so it works with any configured
    provider (Anthropic, OpenAI, Google, Ollama, etc.).
    """

    def __init__(self) -> None:
        pass

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
            }
            for job in jobs
        ]

        prompt = render_prompt("job_classification.j2", jobs_json=json.dumps(jobs_payload, indent=2))

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
            response = await model.ainvoke(messages)
            text = response.content if isinstance(response.content, str) else str(response.content)

            cleaned = text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            result = json.loads(cleaned)
            return result.get("jobs", [])
        except Exception as exc:
            logger.error("Batch classify failed (%d jobs): %s", len(jobs), exc)
            return []

    async def run_pending(self, db: AsyncSession) -> int:
        """Fetch unclassified jobs, classify in batches, update the database.

        Args:
            db: Async SQLAlchemy session.

        Returns:
            Number of jobs successfully classified.
        """
        stmt = (
            select(JobPosting)
            .where(JobPosting.match_score.is_(None))
            .where(JobPosting.is_active.is_(True))
            .limit(settings.CLASSIFIER_BATCH_SIZE * 3)  # fetch up to 3 batches
        )
        result = await db.execute(stmt)
        all_jobs = list(result.scalars().all())

        if not all_jobs:
            logger.info("No unclassified jobs to process.")
            return 0

        logger.info("Classifying %d jobs in batches of %d", len(all_jobs), settings.CLASSIFIER_BATCH_SIZE)
        classified = 0

        for batch_start in range(0, len(all_jobs), settings.CLASSIFIER_BATCH_SIZE):
            batch = all_jobs[batch_start : batch_start + settings.CLASSIFIER_BATCH_SIZE]
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
                            employment_type=classification.get("employment_type", "unknown"),
                            ir35_status=classification.get("ir35_status", "unknown"),
                            working_pattern=classification.get("working_pattern", "unknown"),
                            seniority=classification.get("seniority"),
                            match_score=float(classification.get("match_score", 0)),
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
