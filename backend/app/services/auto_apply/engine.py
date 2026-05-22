"""Auto-apply engine orchestrator."""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from ...config import settings
from ...models.auto_apply import ApplicationAttempt
from ...repositories.auto_apply_repository import AutoApplyRepository
from .captcha_handler import CaptchaHandler
from .form_detector import FormDetector, FormField
from .form_filler import FormFiller
from .question_answerer import CustomQuestionAnswerer

logger = logging.getLogger(__name__)

# Path to the candidate profile JSON relative to this file's package root
_PROFILE_PATH = Path(__file__).parent.parent.parent / "templates" / "candidate_profile.json"

# Platform detection URL patterns — checked in order, first match wins
_PLATFORM_PATTERNS: list[tuple[str, str]] = [
    ("reed.co.uk", "reed"),
    ("cwjobs.co.uk", "cwjobs"),
    ("workday.com", "workday"),
    ("myworkdayjobs.com", "workday"),
    ("greenhouse.io", "greenhouse"),
    ("boards.greenhouse.io", "greenhouse"),
    ("lever.co", "lever"),
    ("jobs.lever.co", "lever"),
    ("mailto:", "email"),
]

# Submit button selectors tried in order during submission
_SUBMIT_SELECTORS = [
    "button[type='submit'][id*='submit']",
    "input[type='submit'][value*='Submit']",
    "input[type='submit'][value*='Apply']",
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "button:has-text('Send application')",
    "button:has-text('Apply')",
    "button[type='submit']",
]


class AutoApplyEngine:
    """Orchestrates the full auto-apply lifecycle for a job application.

    Lifecycle:
      1. prepare_application() — navigate, detect fields, generate answers,
         save form_data → status='ready_for_review'
      2. get_preview() / update_preview() — user reviews & edits form_data
      3. approve_attempt() — user confirms → status='approved'
      4. submit_application() — re-fill form, upload docs, click submit,
         detect confirmation → status='submitted' or 'failed'
    """

    def __init__(self, claude_client: Any, db_factory: Any) -> None:
        """Initialise engine with dependencies.

        Args:
            claude_client: ClaudeClient instance for AI question answering.
            db_factory: Async SQLAlchemy session factory (used for background tasks).
        """
        self._claude = claude_client
        self._db_factory = db_factory
        self._form_detector = FormDetector()
        self._form_filler = FormFiller()
        self._question_answerer = CustomQuestionAnswerer(claude_client)
        self._captcha_handler = CaptchaHandler()

    # ------------------------------------------------------------------ #
    # Stage 1 — Prepare
    # ------------------------------------------------------------------ #

    async def prepare_application(
        self, application_id: str, db: Any
    ) -> ApplicationAttempt:
        """Stage 1: navigate to job URL, detect form fields, generate answers.

        Performs the following steps:
        - Creates an ApplicationAttempt record (status='preparing').
        - Loads the candidate profile.
        - Opens the job URL with Playwright and finds the apply page.
        - Detects all form fields with FormDetector.
        - Maps profile fields and identifies unanswered custom questions.
        - Calls QuestionAnswerer for unmapped questions.
        - Takes a screenshot of the pre-filled form.
        - Persists form_data and custom_questions JSON.
        - Sets status='ready_for_review'.

        Args:
            application_id: UUID of the parent Application record.
            db: SQLAlchemy AsyncSession.

        Returns:
            The created and updated ApplicationAttempt ORM object.

        Raises:
            ValueError: If the job URL cannot be resolved.
            RuntimeError: If Playwright navigation fails fatally.
        """
        repo = AutoApplyRepository(db)

        # ---------------------------------------------------------------- #
        # Resolve job_url from the application record (caller supplies it
        # via application_id; the engine creates the attempt here)
        # ---------------------------------------------------------------- #
        # For the engine interface we accept the job_url directly via
        # kwargs or look it up.  To keep this class decoupled from the
        # Application model we accept job_url as a separate parameter
        # when called from the router.  Here we use application_id as a
        # sentinel — the router always calls with job_url kwarg injected.
        #
        # Retrieve it from a previously created "pending" attempt if one
        # exists, otherwise the caller must have created the attempt first.

        attempt = await self._get_or_create_attempt(application_id, repo)
        job_url = attempt.job_url

        await repo.update_attempt(attempt.id, status="preparing")

        profile = await self._load_candidate_profile()

        screenshots_dir = Path("data/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
            context = await browser.new_context(
                user_agent=random.choice(settings.USER_AGENTS),
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            try:
                # Navigate to the job listing
                await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)

                # Detect platform
                platform = await self._detect_platform(job_url)
                handler = self._get_platform_handler(platform)

                # Get the apply page URL
                try:
                    apply_url = await handler.get_apply_url(page)
                except RuntimeError as exc:
                    logger.warning("Could not find apply URL: %s", exc)
                    apply_url = job_url

                # Navigate to apply page
                if apply_url != page.url:
                    await page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)

                # CAPTCHA check before we do anything
                captcha_type = await self._captcha_handler.detect(page)
                if captcha_type:
                    await self._captcha_handler.handle(page, attempt, db, repo)
                    await browser.close()
                    return await repo.get_attempt(attempt.id)  # type: ignore[return-value]

                # Detect all form fields
                fields = await self._form_detector.detect_fields(page)

                # Identify custom questions (unmapped fields)
                custom_question_texts = self._extract_custom_questions(fields, profile)

                # Get job description text for question context
                jd_text = await self._extract_page_text(page)

                # Generate answers for custom questions
                custom_answers: dict[str, str] = {}
                if custom_question_texts:
                    custom_answers = await self._question_answerer.answer_questions(
                        custom_question_texts, jd_text, profile
                    )

                # Fill form to build form_data (returns filled values)
                fill_results = await self._form_filler.fill_form(
                    page, fields, profile, custom_answers
                )

                # Build form_data dict
                form_data: dict[str, str] = {}
                for result in fill_results:
                    if result.get("value") is not None:
                        form_data[result["label"]] = str(result["value"])

                # Take screenshot of the filled (but not yet submitted) form
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
                screenshot_path = str(screenshots_dir / f"before_{attempt.id}_{ts}.png")
                await page.screenshot(path=screenshot_path, full_page=True)

                # Persist
                await repo.update_attempt(
                    attempt.id,
                    platform=platform,
                    apply_url=apply_url,
                    status="ready_for_review",
                    form_data=json.dumps(form_data),
                    custom_questions=json.dumps(custom_answers),
                    screenshot_before=screenshot_path,
                )

            except Exception as exc:
                logger.exception("prepare_application failed for attempt %s", attempt.id)
                await repo.update_attempt(
                    attempt.id,
                    status="failed",
                    error_message=str(exc),
                )
            finally:
                await browser.close()

        refreshed = await repo.get_attempt(attempt.id)
        return refreshed  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Stage 2 — Preview / Edit
    # ------------------------------------------------------------------ #

    async def get_preview(self, attempt_id: str, db: Any) -> dict[str, Any]:
        """Return the attempt with its form_data and custom_questions for review.

        Args:
            attempt_id: UUID of the ApplicationAttempt.
            db: SQLAlchemy AsyncSession.

        Returns:
            Dict with attempt fields including parsed form_data and
            custom_questions dicts.

        Raises:
            ValueError: If no attempt with the given ID exists.
        """
        repo = AutoApplyRepository(db)
        attempt = await repo.get_attempt(attempt_id)
        if attempt is None:
            raise ValueError(f"No attempt found with id={attempt_id}")

        form_data = json.loads(attempt.form_data) if attempt.form_data else {}
        custom_questions = (
            json.loads(attempt.custom_questions) if attempt.custom_questions else {}
        )

        return {
            "id": attempt.id,
            "application_id": attempt.application_id,
            "job_url": attempt.job_url,
            "apply_url": attempt.apply_url,
            "platform": attempt.platform,
            "status": attempt.status,
            "form_data": form_data,
            "custom_questions": custom_questions,
            "cv_path": attempt.cv_path,
            "cl_path": attempt.cl_path,
            "screenshot_before": attempt.screenshot_before,
            "created_at": attempt.created_at.isoformat() if attempt.created_at else None,
        }

    async def update_preview(
        self, attempt_id: str, updates: dict[str, Any], db: Any
    ) -> ApplicationAttempt:
        """Apply user edits to form_data before the attempt is approved.

        Merges updates into the existing form_data JSON. If updates contains
        a 'form_data' key its value is deep-merged; any other top-level keys
        are applied directly as column updates (e.g. cv_path, cl_path).

        Args:
            attempt_id: UUID of the ApplicationAttempt.
            updates: Dict of changes. 'form_data' key → merged into form_data JSON.
                     Other keys mapped to ORM columns directly.
            db: SQLAlchemy AsyncSession.

        Returns:
            Updated ApplicationAttempt.

        Raises:
            ValueError: If attempt not found.
        """
        repo = AutoApplyRepository(db)
        attempt = await repo.get_attempt(attempt_id)
        if attempt is None:
            raise ValueError(f"No attempt found with id={attempt_id}")

        column_updates: dict[str, Any] = {}

        if "form_data" in updates:
            existing = json.loads(attempt.form_data) if attempt.form_data else {}
            existing.update(updates["form_data"])
            column_updates["form_data"] = json.dumps(existing)

        # Pass through allowed column overrides
        for key in ("cv_path", "cl_path"):
            if key in updates:
                column_updates[key] = updates[key]

        if column_updates:
            await repo.update_attempt(attempt_id, **column_updates)

        return await repo.get_attempt(attempt_id)  # type: ignore[return-value]

    async def approve_attempt(self, attempt_id: str, db: Any) -> ApplicationAttempt:
        """Mark the attempt as approved, ready for submission.

        Args:
            attempt_id: UUID of the ApplicationAttempt.
            db: SQLAlchemy AsyncSession.

        Returns:
            Updated ApplicationAttempt with status='approved'.

        Raises:
            ValueError: If attempt not found.
        """
        repo = AutoApplyRepository(db)
        attempt = await repo.get_attempt(attempt_id)
        if attempt is None:
            raise ValueError(f"No attempt found with id={attempt_id}")

        await repo.update_attempt(attempt_id, status="approved")
        return await repo.get_attempt(attempt_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Stage 3 — Submit
    # ------------------------------------------------------------------ #

    async def submit_application(
        self, attempt_id: str, db: Any
    ) -> ApplicationAttempt:
        """Stage 3: re-open the apply page, fill and submit the form.

        Pre-conditions:
          - Attempt status must be 'approved'.
          - Rate limit must not be exceeded (AUTO_APPLY_MAX_PER_HOUR).

        Process:
          1. Rate-limit check.
          2. Re-open apply_url in Playwright.
          3. Re-fill all fields from stored form_data.
          4. Upload CV/CL files if paths are set.
          5. Run platform-specific handler.
          6. CAPTCHA check.
          7. Click submit button.
          8. Wait for confirmation.
          9. Take screenshot_after.
          10. Update status to 'submitted' or 'failed'.

        Args:
            attempt_id: UUID of the ApplicationAttempt.
            db: SQLAlchemy AsyncSession.

        Returns:
            Updated ApplicationAttempt.

        Raises:
            ValueError: If status is not 'approved' or rate limit exceeded.
        """
        repo = AutoApplyRepository(db)
        attempt = await repo.get_attempt(attempt_id)
        if attempt is None:
            raise ValueError(f"No attempt found with id={attempt_id}")

        if attempt.status != "approved":
            raise ValueError(
                f"Attempt {attempt_id} has status='{attempt.status}'; must be 'approved' to submit."
            )

        # Rate limit check
        submitted_count = await repo.count_submitted_last_hour()
        if submitted_count >= settings.AUTO_APPLY_MAX_PER_HOUR:
            raise ValueError(
                f"Rate limit reached: {submitted_count} applications submitted in the last hour "
                f"(max {settings.AUTO_APPLY_MAX_PER_HOUR}). Try again later."
            )

        apply_url = attempt.apply_url or attempt.job_url
        form_data: dict[str, str] = json.loads(attempt.form_data) if attempt.form_data else {}
        custom_answers: dict[str, str] = (
            json.loads(attempt.custom_questions) if attempt.custom_questions else {}
        )
        platform = attempt.platform or "generic"

        await repo.update_attempt(attempt_id, status="submitting")

        screenshots_dir = Path("data/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        profile = await self._load_candidate_profile()

        # Overlay form_data values back into profile documents section so
        # the filler can re-use them
        if attempt.cv_path:
            profile.setdefault("documents", {})["cv_path"] = attempt.cv_path
        if attempt.cl_path:
            profile.setdefault("documents", {})["cl_path"] = attempt.cl_path

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)
            context = await browser.new_context(
                user_agent=random.choice(settings.USER_AGENTS),
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            success = False
            error_msg: str | None = None

            try:
                await page.goto(apply_url, wait_until="domcontentloaded", timeout=30000)

                # CAPTCHA check early
                captcha_type = await self._captcha_handler.detect(page)
                if captcha_type:
                    await self._captcha_handler.handle(page, attempt, db, repo)
                    await browser.close()
                    return await repo.get_attempt(attempt_id)  # type: ignore[return-value]

                # Re-detect form fields
                fields = await self._form_detector.detect_fields(page)

                # Re-fill all fields
                await self._form_filler.fill_form(page, fields, profile, custom_answers)

                # Platform-specific fill (multi-step navigation, login, etc.)
                handler = self._get_platform_handler(platform)
                await handler.fill_platform_specific(page, profile, custom_answers)

                # CV upload if not already handled by platform handler
                await self._upload_documents(page, attempt)

                # Final CAPTCHA check before submitting
                captcha_type = await self._captcha_handler.detect(page)
                if captcha_type:
                    await self._captcha_handler.handle(page, attempt, db, repo)
                    await browser.close()
                    return await repo.get_attempt(attempt_id)  # type: ignore[return-value]

                # Click submit
                submitted = await self._click_submit(page)
                if not submitted:
                    error_msg = "No submit button found on the application form."
                    await repo.update_attempt(
                        attempt_id,
                        status="manual_required",
                        error_message=error_msg,
                    )
                    await browser.close()
                    return await repo.get_attempt(attempt_id)  # type: ignore[return-value]

                # Wait for page to settle
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

                # Detect success
                success = await handler.detect_success(page)

            except Exception as exc:
                logger.exception("submit_application failed for attempt %s", attempt_id)
                error_msg = str(exc)

            finally:
                # Take post-submission screenshot
                ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
                screenshot_after = str(screenshots_dir / f"after_{attempt_id}_{ts}.png")
                try:
                    await page.screenshot(path=screenshot_after, full_page=False)
                except Exception as ss_exc:
                    logger.warning("Post-submit screenshot failed: %s", ss_exc)
                    screenshot_after = None  # type: ignore[assignment]

                await browser.close()

        # Persist final status
        if success:
            await repo.update_attempt(
                attempt_id,
                status="submitted",
                submitted_at=datetime.utcnow(),
                screenshot_after=screenshot_after,
            )
            logger.info("Attempt %s submitted successfully", attempt_id)
        else:
            await repo.update_attempt(
                attempt_id,
                status="failed",
                error_message=error_msg or "Application submission failed — no confirmation detected.",
                screenshot_after=screenshot_after,
            )
            logger.warning("Attempt %s failed to submit", attempt_id)

        return await repo.get_attempt(attempt_id)  # type: ignore[return-value]

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    async def _detect_platform(self, url: str) -> str:
        """Determine the job board platform from a URL.

        Checks the URL against known domain patterns. Returns 'generic'
        for unrecognised domains.

        Args:
            url: Job posting or apply page URL.

        Returns:
            Platform identifier string:
            'reed'|'cwjobs'|'workday'|'greenhouse'|'lever'|'email'|'generic'
        """
        url_lower = url.lower()
        for domain, platform in _PLATFORM_PATTERNS:
            if domain in url_lower:
                return platform
        return "generic"

    async def _load_candidate_profile(self) -> dict[str, Any]:
        """Load the candidate profile from the JSON template file.

        Returns:
            Parsed profile dict. Returns an empty dict if the file is
            missing so the engine degrades gracefully.
        """
        if not _PROFILE_PATH.exists():
            logger.warning("Candidate profile not found at %s — using empty profile", _PROFILE_PATH)
            return {}
        try:
            with _PROFILE_PATH.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception as exc:
            logger.error("Failed to load candidate profile: %s", exc)
            return {}

    def _get_platform_handler(self, platform: str) -> Any:
        """Return the appropriate platform handler for the given platform string.

        Args:
            platform: Platform identifier from _detect_platform().

        Returns:
            A BasePlatformHandler subclass instance.
        """
        from .platform_handlers.cwjobs import CWJobsPlatformHandler
        from .platform_handlers.generic import GenericPlatformHandler
        from .platform_handlers.reed import ReedPlatformHandler

        handlers = {
            "reed": ReedPlatformHandler,
            "cwjobs": CWJobsPlatformHandler,
        }
        handler_cls = handlers.get(platform, GenericPlatformHandler)
        return handler_cls()

    def _extract_custom_questions(
        self, fields: list[FormField], profile: dict[str, Any]
    ) -> list[str]:
        """Identify form fields that cannot be answered from the candidate profile.

        Uses FormFiller's FIELD_MAPPING to determine which fields already
        have profile-based answers. Any remaining textarea or visible text
        fields with labels not in the mapping are treated as custom questions.

        Args:
            fields: List of detected FormField objects.
            profile: Candidate profile dict.

        Returns:
            List of question label strings.
        """
        filler = FormFiller()
        custom: list[str] = []

        for form_field in fields:
            if form_field.field_type in ("submit", "hidden", "file"):
                continue
            label_lower = form_field.label.lower()
            name_lower = form_field.name.lower()
            # Check if the filler can auto-map this field
            has_mapping = any(
                kw in label_lower or kw in name_lower
                for kw in filler.FIELD_MAPPING.keys()
            )
            if not has_mapping and form_field.label:
                custom.append(form_field.label)

        return custom

    async def _extract_page_text(self, page: Any) -> str:
        """Extract visible text from the current page for JD context.

        Args:
            page: Playwright Page.

        Returns:
            Page body text (truncated to 4000 chars).
        """
        try:
            text = await page.inner_text("body")
            return text[:4000]
        except Exception as exc:
            logger.debug("Page text extraction failed: %s", exc)
            return ""

    async def _upload_documents(self, page: Any, attempt: ApplicationAttempt) -> None:
        """Upload CV and cover letter files if set and a file input is present.

        Args:
            page: Playwright Page.
            attempt: ApplicationAttempt with cv_path and cl_path fields.
        """
        if attempt.cv_path:
            for selector in (
                "input[type='file'][name*='cv']",
                "input[type='file'][id*='cv']",
                "input[type='file'][accept*='.pdf']",
                "input[type='file']",
            ):
                try:
                    el = await page.query_selector(selector)
                    if el:
                        await el.set_input_files(attempt.cv_path)
                        logger.debug("Uploaded CV via '%s'", selector)
                        break
                except Exception as exc:
                    logger.debug("CV upload via '%s' failed: %s", selector, exc)

        if attempt.cl_path:
            for selector in (
                "input[type='file'][name*='cover']",
                "input[type='file'][name*='cl']",
                "input[type='file'][id*='cover']",
            ):
                try:
                    el = await page.query_selector(selector)
                    if el:
                        await el.set_input_files(attempt.cl_path)
                        logger.debug("Uploaded cover letter via '%s'", selector)
                        break
                except Exception as exc:
                    logger.debug("CL upload via '%s' failed: %s", selector, exc)

    async def _click_submit(self, page: Any) -> bool:
        """Find and click the final submit button on the form.

        Args:
            page: Playwright Page with the filled form.

        Returns:
            True if a submit button was found and clicked.
        """
        for selector in _SUBMIT_SELECTORS:
            try:
                button = await page.query_selector(selector)
                if button:
                    visible = await button.is_visible()
                    enabled = await button.is_enabled()
                    if visible and enabled:
                        await button.click()
                        logger.info("Clicked submit via selector: %s", selector)
                        return True
            except Exception as exc:
                logger.debug("Submit click via '%s' failed: %s", selector, exc)
        return False

    async def _get_or_create_attempt(
        self, application_id: str, repo: AutoApplyRepository
    ) -> ApplicationAttempt:
        """Retrieve a pending attempt for the application or raise.

        In practice the router/service creates the attempt before calling
        prepare_application. This helper fetches the most recent pending
        attempt for the given application_id.

        Args:
            application_id: Parent application UUID.
            repo: AutoApplyRepository.

        Returns:
            The ApplicationAttempt to prepare.

        Raises:
            ValueError: If no pending attempt exists.
        """
        attempts = await repo.list_attempts(application_id=application_id, status="pending", limit=1)
        if not attempts:
            raise ValueError(
                f"No pending ApplicationAttempt found for application_id={application_id}. "
                "Create one via the repository before calling prepare_application()."
            )
        return attempts[0]
