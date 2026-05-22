"""Two-stage story retrieval: tag Jaccard similarity (fast) then embedding cosine (fallback)."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from ..models.story import Story

logger = logging.getLogger(__name__)

_TAG_SHORT_CIRCUIT = 0.6   # Jaccard threshold — skip Stage 2 if met
_TOP_N = 3


@dataclass
class MatchResult:
    story: Story
    confidence: float
    stage: str          # "tag" | "embedding"
    reason: str | None = None


def _jaccard(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    set_a, set_b = set(t.lower() for t in a), set(t.lower() for t in b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


class StoryMatcher:
    """Retrieves the best-matching stories for an interview question.

    Stage 1 — Tag Jaccard: fast, zero-cost, short-circuits if score >= 0.6.
    Stage 2 — Embedding cosine: runs only when Stage 1 has no strong winner.
    Stories without embeddings gracefully fall back to Stage 1 only.
    """

    def find_matches(
        self,
        question: str,
        question_tags: list[str] | None,
        stories: list[Story],
        question_embedding: list[float] | None = None,
        top_n: int = _TOP_N,
    ) -> list[MatchResult]:
        """Return up to top_n matching stories, ordered by confidence descending.

        Args:
            question: The interview question text.
            question_tags: Tags extracted for this question (may be empty).
            stories: All active Story ORM objects from the bank.
            question_embedding: Pre-computed embedding for the question (optional).
            top_n: Maximum number of results to return.

        Returns:
            List of MatchResult, best match first.
        """
        if not stories:
            return []

        # ── Stage 1: Tag Jaccard ──────────────────────────────────────────────
        tag_scored: list[tuple[float, Story]] = []
        if question_tags:
            for story in stories:
                score = _jaccard(question_tags, story.tags or [])
                if score > 0:
                    tag_scored.append((score, story))

        tag_scored.sort(key=lambda x: x[0], reverse=True)

        # Short-circuit if top tag match is strong enough
        if tag_scored and tag_scored[0][0] >= _TAG_SHORT_CIRCUIT:
            results = []
            for score, story in tag_scored[:top_n]:
                matched_tags = set(t.lower() for t in (question_tags or [])) & set(
                    t.lower() for t in (story.tags or [])
                )
                results.append(
                    MatchResult(
                        story=story,
                        confidence=round(score, 3),
                        stage="tag",
                        reason=f"Matched tags: {', '.join(sorted(matched_tags))}",
                    )
                )
            return results

        # ── Stage 2: Embedding cosine ─────────────────────────────────────────
        embedding_scored: list[tuple[float, Story]] = []
        if question_embedding:
            for story in stories:
                if story.embedding:
                    score = _cosine(question_embedding, story.embedding)
                    if score > 0:
                        embedding_scored.append((score, story))

        embedding_scored.sort(key=lambda x: x[0], reverse=True)

        if embedding_scored:
            results = []
            for score, story in embedding_scored[:top_n]:
                results.append(
                    MatchResult(
                        story=story,
                        confidence=round(score, 3),
                        stage="embedding",
                        reason="Semantic similarity match",
                    )
                )
            return results

        # ── Fallback: return whatever tag matches exist (even weak ones) ──────
        results = []
        for score, story in tag_scored[:top_n]:
            results.append(
                MatchResult(story=story, confidence=round(score, 3), stage="tag")
            )
        return results
