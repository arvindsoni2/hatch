"""CWJobs.co.uk platform handler for the auto-apply engine."""
from __future__ import annotations

import logging
from typing import Any

from .base import BasePlatformHandler

logger = logging.getLogger(__name__)

_APPLY_BUTTON_SELECTORS = [
    "a[data-at='job-apply-button']",
    "a.apply-button",
    "a[href*='/apply']",
    "button[data-at='apply-button']",
    "a:has-text('Apply now')",
    "a:has-text('Apply')",
    "button:has-text('Apply now')",
    "button:has-text('Apply')",
]

_SUCCESS_URL_PATTERNS = [
    "/applied",
    "/application-complete",
    "/application-success",
    "/confirmation",
    "success=true",
]

_SUCCESS_TEXT_PATTERNS = [
    "application submitted",
    "application complete",
    "successfully applied",
    "thank you for your application",
    "application has been sent",
    "we've received your application",
]


class CWJobsPlatformHandler(BasePlatformHandler):
    """Handles CWJobs.co.uk multi-step application forms.

    CWJobs application flow:
      1. Job listing → "Apply now" button → /apply page
      2. Register/login gate (if not logged in — handled by profile credentials)
      3. Personal details step
      4. CV upload / existing CV selection
      5. Cover letter + screening questions step
      6. Review & submit

    Note: CWJobs uses StepStone's underlying ATS, so some selectors are
    shared with other StepStone-powered boards.
    """

    async def get_apply_url(self, page: Any) -> str:
        """Locate CWJobs apply button and return the apply page URL.

        Args:
            page: Playwright Page on a CWJobs job-listing URL.

        Returns:
            Absolute URL of the application form page.

        Raises:
            RuntimeError: If no apply button is found.
        """
        for selector in _APPLY_BUTTON_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    href = await element.get_attribute("href")
                    if href:
                        if href.startswith("http"):
                            return href
                        return f"https://www.cwjobs.co.uk{href}"
                    # Button with no href — click and capture URL
                    await element.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    return page.url
            except Exception as exc:
                logger.debug("CWJobs apply selector '%s' failed: %s", selector, exc)

        raise RuntimeError("Could not find the Apply button on CWJobs job listing page.")

    async def fill_platform_specific(
        self, page: Any, profile: dict[str, Any], answers: dict[str, str]
    ) -> None:
        """Navigate CWJobs multi-step form and fill platform-specific fields.

        Handles:
        - Login gate if credentials are configured in settings.
        - CV upload or selection of existing CV.
        - Cover letter free-text field.
        - Stepping through multi-page form via Next/Continue buttons.

        Args:
            page: Playwright Page on CWJobs apply form.
            profile: Candidate profile dict.
            answers: Custom question answers.
        """
        from ....config import settings

        personal = profile.get("personal", {})
        documents = profile.get("documents", {})

        # ---- Login gate (CWJobs requires authentication) ------------------
        await self._handle_login_gate(page, settings)

        # Step through up to 6 form pages
        for step in range(1, 7):
            logger.debug("CWJobs: step %d, URL: %s", step, page.url)

            # ---- CV section -----------------------------------------------
            existing_cv = await page.query_selector(
                "input[type='radio'][value*='existing'], "
                "label:has-text('Use my existing CV') input[type='radio'], "
                "[data-at='existing-cv-option']"
            )
            if existing_cv:
                await existing_cv.click()
                logger.debug("CWJobs: selected existing CV")
            else:
                cv_upload = await page.query_selector(
                    "input[type='file'][name*='cv'], "
                    "input[type='file'][id*='cv'], "
                    "input[type='file'][accept*='.pdf']"
                )
                cv_path = documents.get("cv_path", "")
                if cv_upload and cv_path:
                    await cv_upload.set_input_files(cv_path)
                    logger.debug("CWJobs: uploaded CV from %s", cv_path)

            # ---- Cover letter field ----------------------------------------
            cl_field = await page.query_selector(
                "textarea[name*='coverLetter'], textarea[name*='cover_letter'], "
                "textarea[id*='cover'], [data-at='cover-letter-field']"
            )
            if cl_field:
                cl_text = documents.get("cover_letter_text", "")
                if cl_text:
                    await cl_field.fill(cl_text)
                    logger.debug("CWJobs: filled cover letter")

            # ---- Next / Continue ------------------------------------------
            next_button = await page.query_selector(
                "button[data-at='next-button'], "
                "button:has-text('Next'), button:has-text('Continue'), "
                "input[type='submit'][value='Next'], input[type='submit'][value='Continue']"
            )
            if not next_button:
                logger.debug("CWJobs: no Next button on step %d", step)
                break

            btn_text = (await next_button.inner_text()).strip().lower()
            if btn_text in ("submit", "submit application", "send application"):
                logger.debug("CWJobs: reached submit button at step %d", step)
                break

            await next_button.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass

        logger.info("CWJobs: platform-specific fill complete")

    async def detect_success(self, page: Any) -> bool:
        """Check for CWJobs application confirmation.

        Args:
            page: Playwright Page after submission.

        Returns:
            True if application confirmation is detected.
        """
        current_url = page.url.lower()
        for pattern in _SUCCESS_URL_PATTERNS:
            if pattern in current_url:
                logger.info("CWJobs success detected via URL: %s", pattern)
                return True

        try:
            body_text = (await page.inner_text("body")).lower()
            for pattern in _SUCCESS_TEXT_PATTERNS:
                if pattern in body_text:
                    logger.info("CWJobs success detected via text: %s", pattern)
                    return True
        except Exception as exc:
            logger.debug("CWJobs body text check failed: %s", exc)

        return False

    # ---------------------------------------------------------------------- #
    # Private helpers
    # ---------------------------------------------------------------------- #

    async def _handle_login_gate(self, page: Any, settings: Any) -> None:
        """Attempt to log in to CWJobs if a login form is visible.

        Uses CWJOBS_EMAIL and CWJOBS_PASSWORD from settings if available.
        Silently skips if credentials are not configured or no login gate
        is visible.

        Args:
            page: Playwright Page.
            settings: Application settings object.
        """
        if not settings.CWJOBS_EMAIL or not settings.CWJOBS_PASSWORD:
            logger.debug("CWJobs: no credentials configured, skipping login")
            return

        try:
            email_field = await page.query_selector(
                "input[type='email'][name*='email'], input[id*='email'][type='email']"
            )
            password_field = await page.query_selector(
                "input[type='password'][name*='password'], input[id*='password']"
            )

            if email_field and password_field:
                await email_field.fill(settings.CWJOBS_EMAIL)
                await password_field.fill(settings.CWJOBS_PASSWORD)

                login_button = await page.query_selector(
                    "button[type='submit']:has-text('Sign in'), "
                    "button[type='submit']:has-text('Log in'), "
                    "input[type='submit'][value='Sign in']"
                )
                if login_button:
                    await login_button.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)
                    logger.info("CWJobs: login submitted")
            else:
                logger.debug("CWJobs: no login gate detected on this page")

        except Exception as exc:
            logger.warning("CWJobs login attempt failed: %s", exc)
