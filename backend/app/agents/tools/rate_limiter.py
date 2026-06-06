"""Token-bucket rate limiter for LLM API calls.

Tracks per-minute and per-day request windows using a sliding deque.
A single shared instance is used across all agents to honour provider limits.

Default limits match Google Gemini free-tier:
  - 15 requests per minute (RPM)
  - 1 500 requests per day (RPD)
Adjust via environment variables or override at construction time.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from dataclasses import dataclass
from datetime import date

logger = logging.getLogger("jobpilot.rate_limiter")

_MINUTE = 60.0
_DAY = 86_400.0


@dataclass
class RateLimitStatus:
    rpm_used: int
    rpm_limit: int
    rpd_used: int
    rpd_limit: int
    wait_seconds: float  # seconds until next slot is available (0 = available now)
    throttled: bool       # True if currently in a wait state
    last_429_at: float | None  # monotonic timestamp of last 429 error

    @property
    def rpm_remaining(self) -> int:
        return max(0, self.rpm_limit - self.rpm_used)

    @property
    def rpd_remaining(self) -> int:
        return max(0, self.rpd_limit - self.rpd_used)

    def as_dict(self) -> dict:
        return {
            "rpm_used": self.rpm_used,
            "rpm_limit": self.rpm_limit,
            "rpm_remaining": self.rpm_remaining,
            "rpd_used": self.rpd_used,
            "rpd_limit": self.rpd_limit,
            "rpd_remaining": self.rpd_remaining,
            "wait_seconds": round(self.wait_seconds, 2),
            "throttled": self.throttled,
            "last_429_at": self.last_429_at,
        }


class TokenBucketLimiter:
    """Sliding-window rate limiter with per-minute and per-day caps.

    Thread-safe via asyncio.Lock. All timestamps use monotonic clock to
    avoid timezone / DST issues; day window resets on UTC calendar date change.
    """

    def __init__(
        self,
        rpm_limit: int | None = None,
        rpd_limit: int | None = None,
    ) -> None:
        self._rpm_limit = rpm_limit or int(os.getenv("LLM_RPM_LIMIT", "15"))
        self._rpd_limit = rpd_limit or int(os.getenv("LLM_RPD_LIMIT", "1500"))
        self._minute_window: deque[float] = deque()  # monotonic timestamps
        self._day_window: deque[float] = deque()
        self._lock = asyncio.Lock()
        self._throttled = False
        self._last_429_at: float | None = None
        self._day_date: date = date.today()

    # ── Public API ────────────────────────────────────────────────────

    async def acquire(self) -> None:
        """Block until a request slot is available within both windows."""
        while True:
            wait = await self._compute_wait()
            if wait <= 0:
                return
            self._throttled = True
            logger.info("Rate limiter: waiting %.1fs before next LLM call.", wait)
            await asyncio.sleep(wait)

    def record_429(self) -> None:
        """Call this when the provider returns HTTP 429 to back off aggressively."""
        self._last_429_at = time.monotonic()
        logger.warning("Rate limiter: 429 recorded — backing off 60 s.")

    def status(self) -> RateLimitStatus:
        """Return current status snapshot (non-blocking)."""
        now = time.monotonic()
        self._evict(now)
        wait = 0.0
        rpm_used = len(self._minute_window)
        rpd_used = len(self._day_window)
        if rpm_used >= self._rpm_limit and self._minute_window:
            wait = max(wait, _MINUTE - (now - self._minute_window[0]))
        if rpd_used >= self._rpd_limit and self._day_window:
            wait = max(wait, _DAY - (now - self._day_window[0]))
        if self._last_429_at is not None:
            remaining_backoff = 60.0 - (now - self._last_429_at)
            if remaining_backoff > 0:
                wait = max(wait, remaining_backoff)
        return RateLimitStatus(
            rpm_used=rpm_used,
            rpm_limit=self._rpm_limit,
            rpd_used=rpd_used,
            rpd_limit=self._rpd_limit,
            wait_seconds=max(0.0, wait),
            throttled=wait > 0,
            last_429_at=self._last_429_at,
        )

    # ── Internal helpers ──────────────────────────────────────────────

    async def _compute_wait(self) -> float:
        """Evict stale timestamps, attempt to claim a slot, return wait time."""
        async with self._lock:
            now = time.monotonic()
            self._evict(now)

            # 429 back-off takes priority
            if self._last_429_at is not None:
                remaining = 60.0 - (now - self._last_429_at)
                if remaining > 0:
                    return remaining
                self._last_429_at = None  # back-off expired

            wait = 0.0
            if len(self._minute_window) >= self._rpm_limit:
                wait = max(wait, _MINUTE - (now - self._minute_window[0]))
            if len(self._day_window) >= self._rpd_limit:
                wait = max(wait, _DAY - (now - self._day_window[0]))

            if wait <= 0:
                # Claim the slot
                self._minute_window.append(now)
                self._day_window.append(now)
                self._throttled = False
                return 0.0
            return wait

    def _evict(self, now: float) -> None:
        """Remove timestamps outside the sliding windows."""
        # Reset day window on UTC calendar date change
        today = date.today()
        if today != self._day_date:
            self._day_window.clear()
            self._day_date = today

        cutoff_minute = now - _MINUTE
        while self._minute_window and self._minute_window[0] <= cutoff_minute:
            self._minute_window.popleft()

        cutoff_day = now - _DAY
        while self._day_window and self._day_window[0] <= cutoff_day:
            self._day_window.popleft()


# Single shared instance — imported by scorer_agent and any future LLM-calling agents
_limiter: TokenBucketLimiter | None = None


def get_limiter() -> TokenBucketLimiter:
    """Return (and lazily create) the process-global rate limiter."""
    global _limiter
    if _limiter is None:
        _limiter = TokenBucketLimiter()
    return _limiter
