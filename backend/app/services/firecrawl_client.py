"""Optional one-page Firecrawl fallback for public job content only."""
from __future__ import annotations
import os
import httpx


async def scrape_public_job(url: str) -> str | None:
    if os.getenv("FIRECRAWL_ENABLED", "false").lower() != "true":
        return None
    key = os.getenv("FIRECRAWL_API_KEY", "")
    if not key:
        return None
    timeout = float(os.getenv("FIRECRAWL_TIMEOUT_SECONDS", "20"))
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers={"Authorization": f"Bearer {key}"},
            json={"url": url, "formats": ["html"], "onlyMainContent": True},
        )
        response.raise_for_status()
        data = response.json().get("data", {})
        return data.get("html") or data.get("markdown")
