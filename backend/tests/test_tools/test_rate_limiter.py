"""Tests for TokenBucketLimiter sliding-window rate limiting."""
from __future__ import annotations

import time

from app.agents.tools.rate_limiter import TokenBucketLimiter


class TestRateLimiter:

    async def test_acquire_within_limit_completes_without_blocking(self):
        """3 calls within rpm_limit=15 all acquire a slot immediately."""
        limiter = TokenBucketLimiter(rpm_limit=15, rpd_limit=1500)

        t0 = time.monotonic()
        for _ in range(3):
            await limiter.acquire()
        elapsed = time.monotonic() - t0

        # Should complete in well under 1 second — not blocked
        assert elapsed < 1.0
        assert limiter.status().rpm_used == 3

    async def test_status_reflects_correct_counts_after_calls(self):
        """status() returns correct rpm_used and rpd_used counts."""
        limiter = TokenBucketLimiter(rpm_limit=15, rpd_limit=100)

        for _ in range(5):
            await limiter.acquire()

        status = limiter.status()
        assert status.rpm_used == 5
        assert status.rpd_used == 5
        assert status.rpm_remaining == 10
        assert status.rpd_remaining == 95
        assert status.throttled is False

    async def test_acquire_exceeding_daily_limit_blocks_status(self):
        """After rpd_limit calls, status shows rpd_remaining == 0."""
        limiter = TokenBucketLimiter(rpm_limit=1000, rpd_limit=5)

        for _ in range(5):
            await limiter.acquire()

        status = limiter.status()
        assert status.rpd_remaining == 0
        assert status.rpd_used == 5

    def test_record_429_sets_last_429_at(self):
        """record_429() stores the monotonic timestamp for backoff calculation."""
        limiter = TokenBucketLimiter(rpm_limit=15, rpd_limit=1500)
        assert limiter.status().last_429_at is None

        limiter.record_429()

        status = limiter.status()
        assert status.last_429_at is not None
        # Backoff should be positive (within 60s window)
        assert status.wait_seconds > 0
        assert status.throttled is True

    def test_minute_window_evicts_old_timestamps(self):
        """Timestamps older than 60s are evicted from the minute window."""
        limiter = TokenBucketLimiter(rpm_limit=15, rpd_limit=1500)

        # Manually add timestamps that are 61 seconds in the past
        old_time = time.monotonic() - 61.0
        limiter._minute_window.append(old_time)
        limiter._minute_window.append(old_time)

        # Eviction happens on next status() call
        status = limiter.status()
        assert status.rpm_used == 0
