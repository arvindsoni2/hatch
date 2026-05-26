"""Local keyword-based job scorer — zero LLM cost.

Produces the same four-dimension score that the LLM scorer does, using
simple keyword matching.  Used in `hybrid` mode to pre-rank all jobs and
send only the top N% to the LLM for detailed scoring.

All matching is case-insensitive; word-boundary matching avoids false
positives (e.g. "PM" matching "programme manager").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LocalScoreResult:
    skill_match: float
    experience_match: float
    rate_match: float
    location_match: float
    overall_score: float
    keyword_matches: list[str] = field(default_factory=list)
    keyword_misses: list[str] = field(default_factory=list)
    reasoning: str = "local-keyword"


def _normalise(text: str) -> str:
    return text.lower()


def _keyword_present(text_lower: str, keyword: str) -> bool:
    """Return True if keyword appears as a whole word (or phrase) in text."""
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text_lower))


# ── Dimension scorers ─────────────────────────────────────────────────


def _skill_match(jd_lower: str, profile: Any) -> tuple[float, list[str], list[str]]:
    primary = profile.skills.primary
    secondary = profile.skills.secondary
    all_skills = list(primary) + list(secondary)

    matched: list[str] = []
    missed: list[str] = []
    for skill in all_skills:
        if _keyword_present(jd_lower, skill):
            matched.append(skill)
        else:
            missed.append(skill)

    # Weight primary skills more heavily
    total = len(primary) * 2 + len(secondary)
    if total == 0:
        return 0.5, matched, missed
    hits = sum(2 for s in primary if s in matched) + sum(1 for s in secondary if s in matched)
    return min(1.0, hits / total), matched, missed


def _experience_match(jd_lower: str, profile: Any) -> float:
    years = profile.candidate.years_experience
    title_lower = profile.candidate.title.lower()

    # Seniority keywords in JD that signal a good match
    senior_keywords = ["senior", "lead", "principal", "head of", "manager", "director", "programme"]
    junior_keywords = ["junior", "graduate", "entry level", "entry-level", "intern"]

    jd_has_senior = any(_keyword_present(jd_lower, kw) for kw in senior_keywords)
    jd_has_junior = any(_keyword_present(jd_lower, kw) for kw in junior_keywords)

    if jd_has_junior and years > 5:
        return 0.2  # overqualified
    if jd_has_senior and years >= 7:
        return 0.9
    if not jd_has_senior and not jd_has_junior:
        return 0.7  # mid-level, neutral

    # Try to match candidate title words to JD
    title_words = [w for w in title_lower.split() if len(w) > 3]
    title_matches = sum(1 for w in title_words if _keyword_present(jd_lower, w))
    title_score = title_matches / len(title_words) if title_words else 0.5

    return max(0.3, min(0.95, title_score))


def _rate_match(jd_lower: str, profile: Any) -> float:
    comp = profile.compensation
    if comp.min_rate == 0 and comp.max_rate == 0:
        return 0.7  # no target set — neutral

    # Look for numbers in JD that could be rates
    numbers = re.findall(r"\b(\d{3,6})\b", jd_lower)
    if not numbers:
        return 0.6  # rate not stated — mildly penalise

    for num_str in numbers:
        num = int(num_str)
        if comp.rate_type == "daily":
            if 200 <= num <= 2000:
                if comp.min_rate <= num <= comp.max_rate * 1.2:
                    return 0.9
                elif num > comp.max_rate * 1.5:
                    return 0.4  # over budget
                elif num >= comp.min_rate * 0.7:
                    return 0.7
        elif comp.rate_type == "annual":
            if 20000 <= num <= 300000:
                if comp.min_rate <= num <= comp.max_rate * 1.2:
                    return 0.9
                elif num < comp.min_rate * 0.7:
                    return 0.3

    return 0.5


def _location_match(jd_lower: str, profile: Any) -> float:
    locations = profile.search.locations
    if not locations:
        return 0.7

    # Remote keywords
    remote_keywords = ["remote", "work from home", "wfh", "fully remote", "anywhere"]
    hybrid_keywords = ["hybrid", "flexible location"]
    jd_has_remote = any(_keyword_present(jd_lower, kw) for kw in remote_keywords)
    jd_has_hybrid = any(_keyword_present(jd_lower, kw) for kw in hybrid_keywords)

    best = 0.0
    for loc in locations:
        pref = loc.remote_preference
        city_lower = loc.city.lower()
        country_lower = loc.country.lower()

        city_match = _keyword_present(jd_lower, city_lower) if city_lower else False
        country_match = _keyword_present(jd_lower, country_lower) if country_lower else False

        if pref == "remote" and jd_has_remote:
            best = max(best, 1.0)
        elif pref == "any":
            if city_match or country_match:
                best = max(best, 1.0)
            elif jd_has_remote or jd_has_hybrid:
                best = max(best, 0.9)
            else:
                best = max(best, 0.6)
        elif pref == "hybrid":
            if (city_match or country_match) and jd_has_hybrid:
                best = max(best, 1.0)
            elif city_match or country_match:
                best = max(best, 0.8)
            elif jd_has_hybrid:
                best = max(best, 0.7)
        elif pref == "onsite":
            if city_match:
                best = max(best, 0.95)
            elif country_match:
                best = max(best, 0.6)

    return best if best > 0 else 0.3


# ── Public API ────────────────────────────────────────────────────────


def score_locally(job: Any, profile: Any) -> LocalScoreResult:
    """Score a JobPosting against a Profile using keyword matching only.

    Returns a LocalScoreResult with the same shape as the LLM _ScoreResult
    so both can feed the same persistence path.
    """
    jd_lower = _normalise((job.description or "") + " " + (job.title or "") + " " + (job.location or ""))

    skill_score, matched, missed = _skill_match(jd_lower, profile)
    exp_score = _experience_match(jd_lower, profile)
    rate_score = _rate_match(jd_lower, profile)
    loc_score = _location_match(jd_lower, profile)

    weights = profile.scoring.weights
    overall = (
        skill_score * weights.skill_match
        + exp_score * weights.experience_match
        + rate_score * weights.rate_match
        + loc_score * weights.location_match
    )

    return LocalScoreResult(
        skill_match=round(skill_score, 3),
        experience_match=round(exp_score, 3),
        rate_match=round(rate_score, 3),
        location_match=round(loc_score, 3),
        overall_score=round(overall, 3),
        keyword_matches=matched[:15],
        keyword_misses=missed[:10],
        reasoning="local-keyword",
    )
