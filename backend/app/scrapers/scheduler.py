"""APScheduler configuration for periodic scraper execution."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from ..config import settings

if TYPE_CHECKING:
    from ..services.digest_service import DigestService
    from ..services.email_generator import EmailGenerator
    from ..services.job_classifier import JobClassifier
    from ..services.job_service import JobService
    from ..services.reminder_service import ReminderService

logger = logging.getLogger(__name__)

# Boards with good native date filters — used for the quick (frequent) scrape
QUICK_SCRAPE_BOARDS = {"reed", "adzuna"}

# Map of source names to scraper classes (lazy import to avoid circular deps)
SCRAPER_REGISTRY: dict[str, str] = {
    "contractoruk": "app.scrapers.contractoruk.ContractorUKScraper",
    "reed": "app.scrapers.reed.ReedScraper",
    "adzuna": "app.scrapers.adzuna.AdzunaScraper",
    "itjobswatch": "app.scrapers.itjobswatch.ITJobsWatchScraper",
    "cwjobs": "app.scrapers.cwjobs.CWJobsScraper",
    "jobserve": "app.scrapers.jobserve.JobServeScraper",
    "linkedin": "app.scrapers.linkedin.LinkedInScraper",
}


def _import_scraper(dotted_path: str) -> type:
    """Dynamically import a scraper class by dotted module path.

    Args:
        dotted_path: e.g. 'app.scrapers.reed.ReedScraper'

    Returns:
        The scraper class.
    """
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


async def run_classifier(classifier: "JobClassifier", db_factory: object) -> None:
    """Run the AI job classifier to score pending jobs.

    Args:
        classifier: JobClassifier instance.
        db_factory: Async session factory callable.
    """
    try:
        async with db_factory() as db:  # type: ignore[attr-defined]
            count = await classifier.run_pending(db)
            logger.info("Classifier: classified %d jobs", count)
    except Exception as exc:
        logger.error("Classifier job failed: %s", exc)


async def run_digest(digest_service: "DigestService", db_factory: object) -> None:
    """Send the daily digest email if enabled.

    Args:
        digest_service: DigestService instance.
        db_factory: Async session factory callable.
    """
    if not settings.DIGEST_ENABLED:
        return
    try:
        async with db_factory() as db:  # type: ignore[attr-defined]
            sent = await digest_service.send(db)
            logger.info("Digest: %s", "sent successfully" if sent else "skipped (nothing to report)")
    except Exception as exc:
        logger.error("Digest job failed: %s", exc)


async def run_reminder_emails(
    reminder_service: "ReminderService", db_factory: object
) -> None:
    """Check overdue follow-ups and auto-draft any missing emails.

    Args:
        reminder_service: ReminderService instance (must have email_generator set).
        db_factory: Async session factory callable.
    """
    try:
        async with db_factory() as db:  # type: ignore[attr-defined]
            count = await reminder_service.check_and_draft_emails(db)
            if count:
                logger.info("Reminder emails: drafted %d new email(s)", count)
    except Exception as exc:
        logger.error("Reminder email draft job failed: %s", exc)


async def run_thank_you_check(
    reminder_service: "ReminderService", db_factory: object
) -> None:
    """Check for recently completed interviews and draft thank-you emails.

    Args:
        reminder_service: ReminderService instance (must have email_generator set).
        db_factory: Async session factory callable.
    """
    try:
        async with db_factory() as db:  # type: ignore[attr-defined]
            count = await reminder_service.check_thank_you_emails(db)
            if count:
                logger.info("Thank-you check: drafted %d new email(s)", count)
    except Exception as exc:
        logger.error("Thank-you email check job failed: %s", exc)


async def run_ghost_analysis(db_factory: object) -> None:
    """Run ghost batch analysis for all unscored/stale jobs.

    Args:
        db_factory: Async session factory callable.
    """
    from ..services.ghost_detector import GhostDetector

    detector = GhostDetector()
    try:
        async with db_factory() as db:  # type: ignore[attr-defined]
            scores = await detector.analyse_batch(db)
            logger.info("Ghost analysis: scored %d jobs", len(scores))
    except Exception as exc:
        logger.error("Ghost analysis job failed: %s", exc)


async def run_scraper(scraper_class: type, job_service: "JobService") -> None:
    """Instantiate a scraper, run it, and save results via job_service.

    Args:
        scraper_class: The scraper class to instantiate and run.
        job_service: JobService instance for persisting the results.
    """
    instance = scraper_class()
    source_name: str = getattr(instance, "name", scraper_class.__name__)
    logger.info("Scheduler: starting scraper '%s'", source_name)
    try:
        result = await job_service.run_scraper(source_name)
        logger.info(
            "Scheduler: '%s' complete — found=%d, new=%d, errors=%d (%.1fs)",
            source_name,
            result.jobs_found,
            result.jobs_new,
            result.errors,
            result.duration_seconds,
        )
    except Exception as e:
        logger.error("Scheduler: scraper '%s' raised unexpected exception: %s", source_name, e)


def create_scheduler(
    job_service: "JobService",
    reminder_service: "ReminderService | None" = None,
    classifier: "JobClassifier | None" = None,
    digest_service: "DigestService | None" = None,
    db_factory: object = None,
    email_generator: "EmailGenerator | None" = None,
) -> AsyncIOScheduler:
    """Build and configure the APScheduler with all scraper jobs.

    Args:
        job_service: Shared JobService instance passed to each scheduled job.
        reminder_service: Optional ReminderService for hourly overdue follow-up checks.
        classifier: Optional JobClassifier for periodic AI classification.
        digest_service: Optional DigestService for daily email digest.
        db_factory: Async session factory (used by classifier and digest jobs).

    Returns:
        Configured (but not yet started) AsyncIOScheduler.
    """
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Scraping is now delegated entirely to ScoutAgent (via the agent orchestrator).
    # ScoutAgent reads job_boards from profile.yaml, uses the class-based registry,
    # and manages its own DB sessions — avoiding the write-lock contention that
    # running many individual scrapers in parallel caused. The old per-scraper jobs
    # are intentionally removed here; the orchestrator's APScheduler cron triggers
    # ScoutAgent on the profile's scrape_interval_hours.
    logger.info("Scraper scheduling delegated to ScoutAgent via agent orchestrator.")

    if reminder_service is not None:
        scheduler.add_job(
            reminder_service.check_overdue,
            IntervalTrigger(hours=1),
            id="reminder_check",
            name="Check overdue follow-ups",
            replace_existing=True,
        )
        logger.info("Scheduled reminder check (every 1 hour).")

        if db_factory is not None:
            scheduler.add_job(
                run_reminder_emails,
                IntervalTrigger(hours=1),
                args=[reminder_service, db_factory],
                id="reminder_email_draft",
                name="Auto-draft follow-up emails",
                replace_existing=True,
            )
            scheduler.add_job(
                run_thank_you_check,
                IntervalTrigger(hours=2),
                args=[reminder_service, db_factory],
                id="thank_you_email_check",
                name="Check for pending thank-you emails",
                replace_existing=True,
            )
            logger.info("Scheduled follow-up email drafting (every 1h) and thank-you checks (every 2h).")

    if classifier is not None and db_factory is not None:
        scheduler.add_job(
            run_classifier,
            IntervalTrigger(minutes=settings.CLASSIFIER_RUN_INTERVAL_MINUTES),
            args=[classifier, db_factory],
            id="job_classifier",
            name="AI classify pending jobs",
            replace_existing=True,
        )
        logger.info(
            "Scheduled job classifier (every %d minutes).",
            settings.CLASSIFIER_RUN_INTERVAL_MINUTES,
        )

    if db_factory is not None:
        scheduler.add_job(
            run_ghost_analysis,
            CronTrigger(hour=3, minute=0),
            args=[db_factory],
            id="ghost_detector_daily",
            name="Daily ghost job analysis",
            replace_existing=True,
        )
        logger.info("Scheduled daily ghost analysis at 03:00 UTC.")

    if digest_service is not None and db_factory is not None and settings.DIGEST_ENABLED:
        try:
            hour, minute = (int(p) for p in settings.DIGEST_TIME.split(":"))
        except ValueError:
            hour, minute = 7, 0
        scheduler.add_job(
            run_digest,
            CronTrigger(hour=hour, minute=minute, timezone=settings.DIGEST_TIMEZONE),
            args=[digest_service, db_factory],
            id="daily_digest",
            name="Send daily digest",
            replace_existing=True,
        )
        logger.info(
            "Scheduled daily digest at %02d:%02d %s.",
            hour,
            minute,
            settings.DIGEST_TIMEZONE,
        )

    return scheduler
