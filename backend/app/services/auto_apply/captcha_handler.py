"""CAPTCHA detection and graceful blocking for auto-apply attempts."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# CSS selectors / script patterns that indicate the presence of a CAPTCHA widget.
_RECAPTCHA_SELECTORS = [
    ".g-recaptcha",
    "iframe[src*='recaptcha']",
    "iframe[title*='reCAPTCHA']",
    "div[data-sitekey]",
    "#recaptcha",
]

_HCAPTCHA_SELECTORS = [
    ".h-captcha",
    "iframe[src*='hcaptcha']",
    "iframe[title*='hCaptcha']",
    "div[data-hcaptcha-widget-id]",
]


class CaptchaHandler:
    """Detects CAPTCHA widgets and blocks the attempt gracefully.

    Does NOT attempt to solve CAPTCHAs or use any third-party solving
    service. When a CAPTCHA is detected, the attempt is flagged as
    'captcha_blocked' so the user can apply manually.
    """

    async def detect(self, page: Any) -> str | None:
        """Detect whether the current page has a known CAPTCHA widget.

        Checks for reCAPTCHA and hCaptcha selector patterns. Does NOT
        evaluate JavaScript — only inspects static DOM selectors.

        Args:
            page: Playwright async Page object.

        Returns:
            'recaptcha' | 'hcaptcha' | None if no CAPTCHA detected.
        """
        for selector in _RECAPTCHA_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    logger.info("reCAPTCHA detected via selector: %s", selector)
                    return "recaptcha"
            except Exception as exc:
                logger.debug("Selector query failed (%s): %s", selector, exc)

        for selector in _HCAPTCHA_SELECTORS:
            try:
                element = await page.query_selector(selector)
                if element:
                    logger.info("hCaptcha detected via selector: %s", selector)
                    return "hcaptcha"
            except Exception as exc:
                logger.debug("Selector query failed (%s): %s", selector, exc)

        # Secondary check: look for common captcha-related script tags
        try:
            scripts = await page.evaluate(
                "() => Array.from(document.querySelectorAll('script[src]')).map(s => s.src)"
            )
            for src in scripts:
                if "recaptcha" in src:
                    logger.info("reCAPTCHA detected via script src: %s", src)
                    return "recaptcha"
                if "hcaptcha" in src:
                    logger.info("hCaptcha detected via script src: %s", src)
                    return "hcaptcha"
        except Exception as exc:
            logger.debug("Script-src CAPTCHA check failed: %s", exc)

        return None

    async def handle(
        self,
        page: Any,
        attempt: Any,
        db: Any,
        repo: Any,
    ) -> None:
        """Mark the attempt as captcha_blocked, capture a screenshot, and log.

        Does NOT attempt to solve the CAPTCHA or call any external service.
        The attempt status is set to 'captcha_blocked' so the user can
        complete the application manually.

        Args:
            page: Playwright async Page object.
            attempt: ApplicationAttempt ORM object.
            db: SQLAlchemy AsyncSession (unused here, passed for interface consistency).
            repo: AutoApplyRepository instance used to persist the status update.
        """
        screenshot_path: str | None = None
        try:
            import os
            from pathlib import Path

            screenshots_dir = Path("data/screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
            screenshot_path = str(screenshots_dir / f"captcha_{attempt.id}_{ts}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            logger.info("CAPTCHA screenshot saved: %s", screenshot_path)
        except Exception as exc:
            logger.warning("Failed to take CAPTCHA screenshot: %s", exc)

        try:
            update_kwargs: dict[str, Any] = {
                "status": "captcha_blocked",
                "error_message": "CAPTCHA detected — manual application required.",
            }
            if screenshot_path:
                update_kwargs["screenshot_before"] = screenshot_path

            await repo.update_attempt(attempt.id, **update_kwargs)
            logger.warning(
                "Attempt %s blocked by CAPTCHA and marked as captcha_blocked.",
                attempt.id,
            )
        except Exception as exc:
            logger.error("Failed to update attempt status for captcha_blocked: %s", exc)
