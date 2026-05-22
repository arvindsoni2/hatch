"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All application settings, sourced from .env or environment."""

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/jobpilot.db"

    # AI
    ANTHROPIC_API_KEY: str = ""

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
    MATCH_SCORE_MIN_FOR_AUTO_APPLY: int = 60

    # Auto-apply
    AUTO_APPLY_ENABLED: bool = True
    AUTO_APPLY_MAX_PER_HOUR: int = 10
    AUTO_APPLY_COOLDOWN_SECONDS: int = 30
    AUTO_APPLY_ENABLED_BOARDS: str = "reed,cwjobs"
    REED_EMAIL: str = ""
    REED_PASSWORD: str = ""
    CWJOBS_EMAIL: str = ""
    CWJOBS_PASSWORD: str = ""

    # Daily digest email
    DIGEST_ENABLED: bool = True
    DIGEST_TIME: str = "07:00"
    DIGEST_TIMEZONE: str = "Europe/London"
    DIGEST_FREQUENCY: str = "daily"
    SMTP_HOST: str = "smtp.gmail.com"
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
    CHROMA_PERSIST_DIR: str = "./data/chroma"
    LANGGRAPH_CHECKPOINT_DB: str = "sqlite:///data/langgraph_checkpoints.db"
    SUPERVISOR_POLL_INTERVAL_SECONDS: int = 60

    # Logging
    LOG_LEVEL: str = "INFO"

    # Job matching preferences
    PRIORITY_KEYWORDS: str = "solutions architect,cloud architect"
    PRIORITY_MIN_RATE: int = 500

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
