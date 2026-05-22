"""Database access layer for cached company research results."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.coach_session import CompanyResearch

logger = logging.getLogger(__name__)

_CACHE_DAYS = 30


class ResearchRepository:
    """All database operations for CompanyResearch cache records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_cached(self, company_name: str) -> CompanyResearch | None:
        """Return a non-expired cache entry for the given company name.

        Args:
            company_name: Company to look up (case-insensitive match).

        Returns:
            CompanyResearch ORM object if a valid (non-expired) record exists,
            otherwise None.
        """
        now = datetime.utcnow()
        result = await self._session.execute(
            select(CompanyResearch)
            .where(
                CompanyResearch.company_name.ilike(company_name),
                CompanyResearch.expires_at > now,
            )
            .order_by(CompanyResearch.cached_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def save(
        self,
        company_name: str,
        data: dict,
        expires_days: int = _CACHE_DAYS,
    ) -> CompanyResearch:
        """Persist new company research data with a TTL.

        Args:
            company_name: Canonical company name.
            data: Research payload — keys: sector, website, description,
                recent_news, key_products, tech_stack_signals.
            expires_days: Cache TTL in days (default 30).

        Returns:
            Persisted CompanyResearch ORM object.
        """
        now = datetime.utcnow()
        research = CompanyResearch(
            company_name=company_name,
            sector=data.get("sector"),
            website=data.get("website"),
            description=data.get("description"),
            recent_news=data.get("recent_news") or [],
            key_products=data.get("key_products") or [],
            tech_stack_signals=data.get("tech_stack_signals") or [],
            cached_at=now,
            expires_at=now + timedelta(days=expires_days),
        )
        self._session.add(research)
        await self._session.flush()
        await self._session.refresh(research)
        return research

    async def invalidate(self, company_name: str) -> int:
        """Expire all cached records for a company by setting expires_at to now.

        Args:
            company_name: Company whose cache entries should be invalidated.

        Returns:
            Number of records invalidated.
        """
        from sqlalchemy import update

        result = await self._session.execute(
            update(CompanyResearch)
            .where(CompanyResearch.company_name.ilike(company_name))
            .values(expires_at=datetime.utcnow())
        )
        return result.rowcount
