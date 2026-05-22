"""Generic fallback platform handler for unknown job boards."""
from __future__ import annotations

import logging
from typing import Any

from .base import BasePlatformHandler

logger = logging.getLogger(__name__)

# Ordered list of selectors to try when looking for an Apply button
_APPLY_BUTTON_SELECTORS = [
    "a[href*='/apply']",
    "a[href*='apply']",
    "button[id*='apply']",
    "a[id*='apply']",
    "button[class*='apply']",
    "a[class*='apply']",
    "a:has-text('Apply now')",
    "a:has-text('Apply for this job')",
    "button:has-text('Apply now')",
    "button:has-text('Apply for this job')",
    "a:has-text('Apply')",
    "button:has-text('Apply')",
    "input[type='submit'][value*='Apply']",
]

# Selectors for the final submit button
_SUBMIT_BUTTON_SELECTORS = [
    "button[type='submit'][id*='submit']",
    "input[type='submit'][value*='Submit']",
    "input[type='submit'][value*='Apply']",
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "button:has-text('Send application')",
    "button[type='submit']",
]

_SUCCESS_TEXT_PATTERNS = [
    "application submitted",
    "application received",
    "application complete",
    "successfully applied",
    "thank you for applying",
    "thank you for your application",
    "we have received your application",
    "we've received your application",
    "application has been sent",
    "application confirmed",
]

_SUCCESS_URL_PATTERNS = [
    "/applied",
    "/application-sent",
    "/application-complete",
    "/application-success",
    "/confirmation",
    "success=true",
    "applied=true",
]


class GenericPlatformHandler(BasePlatformHandler):
    """Fallback handler for job boards not covered by a dedicated handler.

    Attempts to find an Apply button using a broad set of selector heuristics,
    then fills the form generically and clicks the first plausible submit button.
    Will not handle multi-step wizards reliably — if the form requires more than
    one page the engine may mark the attempt as 'manual_required'.
    """

    async def get_apply_url(self, page: Any) -> str:
        """Locate any apply CTA on the page and return the target URL.

        Tries a broad list of selector heuristics. If a button has no href,
        clicks it and returns the resulting page URL.

        Args:
            page: Playwright Page on the job listing.

        Returns:
            Absolute URL string for the application form.

        Raises:
            RuntimeError: If no apply button is found after all selectors.
        """
        for selector in _APPLY_BUTTON_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    href = await element.get_attribute("href")
                    if href:
                        if href.startswith("http"):
                            return href
                        # Build absolute URL from current page origin
                        origin = await page.evaluate("() => window.location.origin")
                        return f"{origin}{href}" if href.startswith("/") else href
                    # No href — click and follow
                    await element.click()
                    await page.wait_for_load_state("networkidle", timeout=15000)
                    return page.url
            except Exception as exc:
                logger.debug("Generic apply selector '%s' failed: %s", selector, exc)

        logger.warning("Generic handler: no Apply button found on %s", page.url)
        raise RuntimeError(f"No apply button found on page: {page.url}")

    async def fill_platform_specific(
        self, page: Any, profile: dict[str, Any], answers: dict[str, str]
    ) -> None:
        """No platform-specific filling for the generic handler.

        The engine's FormFiller already handles the generic field mapping.
        This method is a no-op — it exists to satisfy the abstract interface.

        Args:
            page: Playwright Page.
            profile: Candidate profile dict.
            answers: Custom question answers.
        """
        logger.debug("Generic handler: no platform-specific fill needed")

    async def detect_success(self, page: Any) -> bool:
        """Check URL and page text for generic success signals.

        Args:
            page: Playwright Page after clicking submit.

        Returns:
            True if a success indicator is found.
        """
        current_url = page.url.lower()
        for pattern in _SUCCESS_URL_PATTERNS:
            if pattern in current_url:
                logger.info("Generic success detected via URL pattern: %s", pattern)
                return True

        try:
            body_text = (await page.inner_text("body")).lower()
            for pattern in _SUCCESS_TEXT_PATTERNS:
                if pattern in body_text:
                    logger.info("Generic success detected via text: %s", pattern)
                    return True
        except Exception as exc:
            logger.debug("Generic body text check failed: %s", exc)

        return False

    async def click_submit(self, page: Any) -> bool:
        """Attempt to click the form's submit button.

        Tries a ranked list of submit button selectors. Returns True if a
        button was found and clicked.

        Args:
            page: Playwright Page with the filled form.

        Returns:
            True if a submit button was found and clicked.
        """
        for selector in _SUBMIT_BUTTON_SELECTORS:
            try:
                button = await page.query_selector(selector)
                if button:
                    is_visible = await button.is_visible()
                    is_enabled = await button.is_enabled()
                    if is_visible and is_enabled:
                        await button.click()
                        logger.info("Generic handler: clicked submit via '%s'", selector)
                        return True
            except Exception as exc:
                logger.debug("Submit selector '%s' failed: %s", selector, exc)

        logger.warning("Generic handler: no submit button found on %s", page.url)
        return False
