"""SQLAlchemy ORM model for tracking agency/recruiter posting reliability."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class AgencyReputation(Base):
    """Tracks response rates and ghost score averages per agency.

    Updated by the ghost detector feedback loop:
    - application gets interview/offer → boost credibility
    - application stalls >30 days → increase suspicion
    """

    __tablename__ = "agency_reputations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    agency_name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    # Normalised lowercase name for consistent matching

    total_jobs_posted: Mapped[int] = mapped_column(Integer, default=0)
    total_applications: Mapped[int] = mapped_column(Integer, default=0)
    total_responses: Mapped[int] = mapped_column(Integer, default=0)
    response_rate: Mapped[float] = mapped_column(Float, default=0.0)  # 0.0-1.0
    avg_ghost_score: Mapped[float] = mapped_column(Float, default=0.0)
    reputation: Mapped[str] = mapped_column(String(16), default="unknown")
    # 'good' | 'average' | 'poor' | 'unknown'

    last_updated: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )
