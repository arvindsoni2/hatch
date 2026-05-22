"""Reed.co.uk platform handler for the auto-apply engine."""
from __future__ import annotations

import logging
from typing import Any

from .base import BasePlatformHandler

logger = logging.getLogger(__name__)

# Selectors used across Reed's application flow
_APPLY_BUTTON_SELECTORS = [
    "a[data-id='apply-button']",
    "a.btn-apply",
    "a[href*='/apply']",
    "button[data-ga-event*='apply']",
    "a:has-text('Apply')",
    "button:has-text('Apply')",
]

_SUCCESS_INDICATORS = [
    # URL patterns
    "/applied",
    "/application-sent",
    "/confirmation",
    # Text patterns checked via page content
]

_SUCCESS_TEXT_PATTERNS = [
    "application submitted",
    "application received",
    "successfully applied",
    "thank you for applying",
    "you have applied",
]


class ReedPlatformHandler(BasePlatformHandler):
    """Handles Reed.co.uk multi-step application forms.

    Reed's apply flow typically has these steps:
      1. Job listing page → click "Apply" → redirects to /jobs/{id}/apply
      2. Step 1: Personal details (pre-filled if logged in)
      3. Step 2: Upload CV / select existing CV
      4. Step 3: Cover letter + custom questions
      5. Step 4: Review & submit

    This handler navigates each step, clicking Next/Continue until the
    final Submit button is reached.
    """

    async def get_apply_url(self, page: Any) -> str:
        """Locate the Reed apply button and return the apply page URL.

        Tries a sequence of selectors until one matches. If Reed opens the
        apply flow in the same tab (common for direct applications), returns
        the URL after navigation.

        Args:
            page: Playwright Page on the Reed job-listing URL.

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
                        # Relative URL — prepend Reed's base
                        return f"https://www.reed.co.uk{href}"
                    # No href — it's a button; click and return new URL
                    await element.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    return page.url
            except Exception as exc:
                logger.debug("Reed apply selector '%s' failed: %s", selector, exc)

        raise RuntimeError("Could not find the Apply button on Reed job listing page.")

    async def fill_platform_specific(
        self, page: Any, profile: dict[str, Any], answers: dict[str, str]
    ) -> None:
        """Navigate Reed's multi-step form, clicking Next between steps.

        Handles:
        - Clicking through "Next" / "Continue" buttons between form steps.
        - Selecting an existing CV if already uploaded.
        - Pasting cover letter text into the free-text field.

        Args:
            page: Playwright Page on Reed's apply form.
            profile: Candidate profile dict.
            answers: Custom question answers.
        """
        personal = profile.get("personal", {})
        documents = profile.get("documents", {})

        # Step through the form up to 5 pages deep
        for step in range(1, 6):
            logger.debug("Reed: processing form step %d, URL: %s", step, page.url)

            # ---- Cover letter step ----------------------------------------
            cl_field = await page.query_selector(
                "textarea[name*='coverLetter'], textarea[id*='cover'], "
                "textarea[placeholder*='cover'], #cover-letter"
            )
            if cl_field:
                cl_text = documents.get("cover_letter_text", "")
                if cl_text:
                    await cl_field.fill(cl_text)
                    logger.debug("Reed: filled cover letter field")

            # ---- CV upload / selection ------------------------------------
            # If Reed shows "use existing CV" radio, prefer that
            existing_cv_radio = await page.query_selector(
                "input[type='radio'][value*='existing'], "
                "input[type='radio'][id*='existing-cv']"
            )
            if existing_cv_radio:
                await existing_cv_radio.click()
                logger.debug("Reed: selected existing CV option")
            else:
                # Try file upload
                cv_file_input = await page.query_selector("input[type='file'][name*='cv'], input[type='file'][id*='cv']")
                cv_path = documents.get("cv_path", "")
                if cv_file_input and cv_path:
                    await cv_file_input.set_input_files(cv_path)
                    logger.debug("Reed: uploaded CV from %s", cv_path)

            # ---- Custom questions -----------------------------------------
            # Already handled by the generic FormFiller; skip here.

            # ---- Next / Continue ------------------------------------------
            next_button = await page.query_selector(
                "button[type='submit']:not([value*='submit' i]):not([id*='apply' i]), "
                "button:has-text('Next'), button:has-text('Continue'), "
                "input[type='submit'][value='Next'], input[type='submit'][value='Continue']"
            )
            if not next_button:
                # No more Next buttons — we may be on the final submit step
                logger.debug("Reed: no Next button on step %d — stopping step loop", step)
                break

            # Check if it looks like a final Submit rather than Next
            btn_text = (await next_button.inner_text()).strip().lower()
            if btn_text in ("submit", "submit application", "apply"):
                logger.debug("Reed: reached submit button at step %d", step)
                break

            await next_button.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass  # Timeout is acceptable — page may already be ready

        logger.info("Reed: platform-specific fill complete")

    async def detect_success(self, page: Any) -> bool:
        """Check for Reed application confirmation.

        Examines the current URL path and page text for success signals.

        Args:
            page: Playwright Page after clicking the final submit button.

        Returns:
            True if a confirmation signal is found.
        """
        current_url = page.url.lower()
        for pattern in _SUCCESS_INDICATORS:
            if pattern in current_url:
                logger.info("Reed success detected via URL pattern: %s", pattern)
                return True

        try:
            body_text = (await page.inner_text("body")).lower()
            for pattern in _SUCCESS_TEXT_PATTERNS:
                if pattern in body_text:
                    logger.info("Reed success detected via text: %s", pattern)
                    return True
        except Exception as exc:
            logger.debug("Reed body text check failed: %s", exc)

        return False
