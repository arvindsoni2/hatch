"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")


class Settings(BaseSettings):
    """All application settings, sourced from .env or environment."""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/jobpilot.db"

    # LLM provider keys — only the one matching profile.yaml llm.provider needs to be set
    ANTHROPIC_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-02-15-preview"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Region / locale
    LOCALE: str = "uk"
    ADZUNA_COUNTRY: str = "gb"

    # External API keys (optional — scrapers skip gracefully if missing)
    REED_API_KEY: str = ""
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""

    # Scraper behaviour
    SCRAPE_INTERVAL_HOURS: int = 4
    SCRAPE_DELAY_MIN_SECONDS: float = 2.0
    SCRAPE_DELAY_MAX_SECONDS: float = 8.0
    PLAYWRIGHT_HEADLESS: bool = True

    # Scraper v2 — broader search
    SCRAPE_LOOKBACK_DAYS: int = 90
    QUICK_SCRAPE_HOURS: int = 48
    FULL_SCRAPE_INTERVAL_HOURS: int = 8
    QUICK_SCRAPE_INTERVAL_HOURS: int = 3
    MAX_PAGES_PER_KEYWORD: int = 20

    # AI classifier
    CLASSIFIER_BATCH_SIZE: int = 30
    CLASSIFIER_RUN_INTERVAL_MINUTES: int = 30
    MATCH_SCORE_MIN_FOR_DIGEST: int = 70

    # Auto-apply permanently disabled — manual approval only per PRD non-goals
    AUTO_APPLY_ENABLED: bool = False

    # Daily digest email — SMTP_HOST empty disables email sending gracefully
    DIGEST_ENABLED: bool = True
    DIGEST_TIME: str = "07:00"
    # Leave empty to derive from locale (uk→Europe/London, in→Asia/Kolkata, etc.)
    DIGEST_TIMEZONE: str = ""
    DIGEST_FREQUENCY: str = "daily"
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    NOTIFICATION_EMAIL: str = ""

    # Optional integrations
    SERPAPI_KEY: str = ""

    # Agentic pipeline settings
    SCORE_THRESHOLD: float = 0.75
    MAX_TAILOR_BATCH: int = 5
    AUTO_APPROVE: bool = False
    AGENT_LOG_LEVEL: str = "INFO"
    LANGGRAPH_CHECKPOINT_DB: str = "sqlite:///data/langgraph_checkpoints.db"
    SUPERVISOR_POLL_INTERVAL_SECONDS: int = 60

    # CORS — comma-separated list of allowed origins (set ALLOWED_ORIGINS env var in production)
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Logging
    LOG_LEVEL: str = "INFO"

    # Optional bearer-token auth for non-localhost deploys.
    # When empty (default) auth is disabled — localhost use is frictionless.
    # Set HATCH_AUTH_TOKEN=<secret> in .env when exposing beyond localhost.
    HATCH_AUTH_TOKEN: str = ""
    HATCH_APP_LOCK_ENABLED: bool = True
    HATCH_APP_PASSWORD: str = ""
    HATCH_APP_SESSION_COOKIE: str = "hatch_app_session"
    HATCH_APP_SESSION_TTL_HOURS: int = 12
    HATCH_APP_LOCK_FAILED_ATTEMPT_LIMIT: int = 5
    HATCH_APP_LOCK_RETRY_DELAY_SECONDS: int = 30

    # Per-client rate limit on mutating endpoints (POST/PUT/PATCH/DELETE).
    # Only active when HATCH_AUTH_TOKEN is non-empty (disabled for localhost dev).
    # Default 600/min is generous for a single-user app; lower for exposed deploys.
    RATE_LIMIT_PER_MINUTE: int = 600

    # Job matching preferences — empty by default; source from profile/master_profile
    PRIORITY_KEYWORDS: str = ""
    PRIORITY_MIN_RATE: int = 0

    # Rotating User-Agent pool
    USER_AGENTS: list[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    ]

    @property
    def priority_keywords_list(self) -> list[str]:
        """Return priority keywords as a list of stripped lowercase strings."""
        return [kw.strip().lower() for kw in self.PRIORITY_KEYWORDS.split(",") if kw.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


# Singleton instance — import this everywhere
settings = Settings()
