"""SQLAlchemy ORM models for the Interview Story Bank: Story and StoryUsage."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Story(Base):
    """A canonical STAR+R narrative in the user's interview story bank."""

    __tablename__ = "stories"
    __table_args__ = (
        Index("idx_stories_is_active", "is_active"),
        Index("idx_stories_strength_score", "strength_score"),
        Index("idx_stories_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(220), nullable=False, unique=True)
    summary: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # STAR+R components
    situation: Mapped[str | None] = mapped_column(Text, nullable=True)
    task: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification metadata (JSON lists/dicts stored as text for SQLite portability)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)           # ["leadership", "delivery"]
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)         # ["stakeholder mgmt"]
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)        # {"savings_gbp": 500000}
    archetype_fit: Mapped[list | None] = mapped_column(JSON, nullable=True)  # ["solutions_architect"]

    # Strength scoring fields
    strength_score: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    times_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    times_edited: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    manual_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5

    # Auto-extraction provenance
    source_session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True
    )
    source_question_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("session_questions.id", ondelete="SET NULL"), nullable=True
    )

    # Semantic embedding (JSON float list; NULL until background job runs)
    embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow, nullable=False)

    usages: Mapped[list[StoryUsage]] = relationship(
        "StoryUsage", back_populates="story", cascade="all, delete-orphan"
    )


class StoryUsage(Base):
    """Records each time a story is retrieved as a match during a Coach session."""

    __tablename__ = "story_usages"
    __table_args__ = (
        Index("idx_story_usages_story_id", "story_id"),
        Index("idx_story_usages_session_id", "session_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    story_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stories.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True
    )
    question_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("session_questions.id", ondelete="SET NULL"), nullable=True
    )
    match_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_stage: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "tag" | "embedding"
    used_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)

    story: Mapped[Story] = relationship("Story", back_populates="usages")
