"""Scout Agent — wraps existing scrapers, deduplicates, emits job_discovered events."""
from __future__ import annotations

import importlib
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.job_repository import JobRepository
from ..scrapers.scheduler import SCRAPER_REGISTRY
from ..services.dedup import DedupService
from .base_agent import BaseAgent

logger = logging.getLogger("jobpilot.agent.scout")


class ScoutAgent(BaseAgent):
    """Iterates all configured scrapers, deduplicates results, emits events.

    LLM usage: None — Scout is purely deterministic.
    """

    name = "scout"

    def __init__(self, sources: list[str] | None = None) -> None:
        super().__init__()
        # Default: run all registered boards; caller may restrict to a subset
        self._sources = sources or list(SCRAPER_REGISTRY.keys())
        self._dedup = DedupService()

    # ── Main entry point ──────────────────────────────────────────────

    async def run(self, db: AsyncSession, **kwargs: Any) -> dict[str, Any]:
        """Run all scrapers and emit job_discovered for each new posting.

        Returns:
            Summary dict: sources_run, jobs_found, jobs_new, errors.
        """
        await self.update_state(db, "running", {"sources": self._sources})

        repo = JobRepository(db)

        total_found = 0
        total_new = 0
        errors: list[dict[str, str]] = []

        for source in self._sources:
            found, new, errs = await self._scrape_source(source, repo, db)
            total_found += found
            total_new += new
            errors.extend(errs)

        await self.update_state(db, "idle")
        self._log.info(
            "Scout run complete: %d sources, %d found, %d new, %d errors.",
            len(self._sources), total_found, total_new, len(errors),
        )
        return {
            "sources_run": len(self._sources),
            "jobs_found": total_found,
            "jobs_new": total_new,
            "errors": errors,
        }

    # ── Per-source scraping ───────────────────────────────────────────

    async def _scrape_source(
        self,
        source: str,
        repo: JobRepository,
        db: AsyncSession,
    ) -> tuple[int, int, list[dict[str, str]]]:
        """Run one scraper, dedup, save new jobs, emit events.

        Returns (found_count, new_count, errors_list).
        """
        errors: list[dict[str, str]] = []
        self._log.info("Scraping source: %s", source)

        dotted_path = SCRAPER_REGISTRY.get(source)
        if not dotted_path:
            self._log.warning("Unknown source '%s' — skipping.", source)
            return 0, 0, [{"source": source, "error": "unknown source"}]

        try:
            module_path, class_name = dotted_path.rsplit(".", 1)
            mod = importlib.import_module(module_path)
            scraper_cls = getattr(mod, class_name)
            scraper = scraper_cls()
            raw_jobs = await scraper.scrape()
        except Exception as exc:
            msg = str(exc)
            self._log.exception("Scraper error for %s: %s", source, msg)
            errors.append({"source": source, "error": msg})
            await self.emit_event(
                "scout_error",
                {"source": source, "error": msg, "retry_count": 0},
                db,
            )
            return 0, 0, errors

        found = len(raw_jobs)
        new_count = 0

        for job_schema in raw_jobs:
            try:
                is_dup = await self._dedup.is_duplicate(
                    job_schema.title, job_schema.company, repo
                )
                if is_dup:
                    continue

                # Use a savepoint so a duplicate-URL IntegrityError only rolls
                # back this one insert and not the entire session transaction.
                try:
                    async with db.begin_nested():
                        saved = await repo.create(job_schema)
                except IntegrityError:
                    self._log.debug(
                        "Duplicate URL skipped for '%s' from %s.",
                        getattr(job_schema, "title", "?"),
                        source,
                    )
                    continue

                new_count += 1

                # Emit discovery event
                event_id = await self.emit_event(
                    "job_discovered",
                    {
                        "job_id": saved.id,
                        "title": saved.title,
                        "company": saved.company,
                        "rate_text": saved.rate_text,
                        "source": source,
                    },
                    db,
                )
                self._log.info(
                    "Emitted job_discovered: %s at %s (job_id=%s, event_id=%s)",
                    saved.title, saved.company, saved.id, event_id,
                )
            except Exception as exc:
                self._log.exception(
                    "Error processing job '%s' from %s: %s",
                    getattr(job_schema, "title", "?"),
                    source,
                    exc,
                )
                errors.append({
                    "source": source,
                    "error": f"job processing error: {exc}",
                })

        await self.emit_event(
            "scrape_complete",
            {
                "source": source,
                "jobs_found": found,
                "jobs_new": new_count,
                "duplicates_filtered": found - new_count,
                "errors": len(errors),
            },
            db,
        )
        self._log.info(
            "%s: %d found, %d new.", source, found, new_count
        )
        return found, new_count, errors
