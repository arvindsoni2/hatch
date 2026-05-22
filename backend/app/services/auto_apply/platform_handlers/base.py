"""Abstract base class for platform-specific apply-form handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BasePlatformHandler(ABC):
    """Abstract base for site-specific application form handlers.

    Each concrete implementation encapsulates the quirks of a particular
    job board's multi-step application flow, including how to locate the
    Apply button, handle platform-specific fields, and confirm success.
    """

    @abstractmethod
    async def get_apply_url(self, page: Any) -> str:
        """Return the direct URL of the application form.

        Navigates the job-listing page to find the primary apply CTA
        (e.g. "Apply now", "Apply on Reed") and returns the href target.
        May follow a redirect or open a new tab, depending on the board.

        Args:
            page: Playwright async Page currently on the job-listing URL.

        Returns:
            Absolute URL string for the application form page.

        Raises:
            RuntimeError: If no apply button or link is found on the page.
        """

    @abstractmethod
    async def fill_platform_specific(
        self, page: Any, profile: dict[str, Any], answers: dict[str, str]
    ) -> None:
        """Fill platform-specific fields that generic detection misses.

        Override to handle multi-step wizards, hidden fields, dynamic
        dropdowns, or any board-specific interaction that the generic
        FormFiller cannot handle.

        Args:
            page: Playwright async Page on the application form.
            profile: Candidate profile dict.
            answers: Custom question answers from QuestionAnswerer.
        """

    @abstractmethod
    async def detect_success(self, page: Any) -> bool:
        """Determine whether the application was submitted successfully.

        Called immediately after clicking the final Submit button.
        Checks for confirmation messages, URL patterns, or redirects
        that indicate the application was received.

        Args:
            page: Playwright async Page after submission.

        Returns:
            True if a success indicator is detected, False otherwise.
        """
