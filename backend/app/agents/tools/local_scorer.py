"""Local keyword-based job scorer — zero LLM cost.

Produces the same four-dimension score that the LLM scorer does, using
keyword matching with normalization and synonym expansion.  Used in
`hybrid` mode to pre-rank all jobs and send only the top N% to the LLM
for detailed scoring.

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
    scoring_method: str = "local"


# ── Skill synonym map ─────────────────────────────────────────────────
# Maps canonical form → list of aliases (all lowercase).
# When the profile lists the canonical form and the JD uses an alias
# (or vice-versa), the match is recorded under the canonical name.

_SKILL_SYNONYMS: dict[str, list[str]] = {
    "kubernetes": ["k8s"],
    "javascript": ["js"],
    "typescript": ["ts"],
    "react": ["reactjs", "react.js"],
    "vue": ["vuejs", "vue.js"],
    "angular": ["angularjs"],
    "python": ["py"],
    "machine learning": ["ml"],
    "artificial intelligence": ["ai"],
    "devops": ["dev ops", "dev-ops"],
    "continuous integration": ["ci/cd", "ci", "cicd"],
    "amazon web services": ["aws"],
    "google cloud": ["gcp", "google cloud platform"],
    "microsoft azure": ["azure"],
    "postgresql": ["postgres"],
    "mongodb": ["mongo"],
    "elasticsearch": ["elastic"],
    "node.js": ["nodejs", "node"],
    "next.js": ["nextjs"],
    "tailwind css": ["tailwind"],
    "docker": ["containerisation", "containerization"],
}

# Build reverse lookup: alias → canonical
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in _SKILL_SYNONYMS.items():
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias] = _canonical


def _normalise_skill(skill: str) -> str:
    """Lowercase, strip common suffixes, collapse whitespace."""
    s = skill.lower().strip()
    s = re.sub(r"\.js$", "", s)        # vue.js → vue
    s = re.sub(r"js$", "", s)          # reactjs → react  (only at end)
    s = re.sub(r"[\s\-_]+", " ", s)   # normalise separators
    return s.strip()


def _canonical(skill: str) -> str:
    """Return the canonical form of a skill name."""
    norm = _normalise_skill(skill)
    return _ALIAS_TO_CANONICAL.get(norm, norm)


def _all_forms(skill: str) -> list[str]:
    """Return all forms (canonical + aliases) that should match a skill."""
    canon = _canonical(skill)
    forms = [canon, _normalise_skill(skill)]
    forms += _SKILL_SYNONYMS.get(canon, [])
    # Also add any aliases that map TO the normalised skill
    for alias, mapped in _ALIAS_TO_CANONICAL.items():
        if mapped == canon:
            forms.append(alias)
    return list(dict.fromkeys(forms))  # deduplicate, preserve order


def _normalise(text: str) -> str:
    return text.lower()


def _keyword_present(text_lower: str, keyword: str) -> bool:
    """Return True if keyword appears as a whole word (or phrase) in text."""
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return bool(re.search(pattern, text_lower))


def _skill_in_text(text_lower: str, skill: str) -> bool:
    """Return True if the skill (or any of its synonyms/aliases) is in text."""
    for form in _all_forms(skill):
        if form and _keyword_present(text_lower, form):
            return True
    return False


# ── Dimension scorers ─────────────────────────────────────────────────


def _skill_match(jd_lower: str, profile: Any) -> tuple[float, list[str], list[str]]:
    primary = profile.skills.primary
    secondary = profile.skills.secondary
    all_skills = list(primary) + list(secondary)

    matched: list[str] = []
    missed: list[str] = []
    for skill in all_skills:
        if _skill_in_text(jd_lower, skill):
            matched.append(skill)
        else:
            missed.append(skill)

    # Weight primary skills more heavily
    total = len(primary) * 2 + len(secondary)
    if total == 0:
        return 0.5, matched, missed
    hits = sum(2 for s in primary if s in matched) + sum(1 for s in secondary if s in matched)
    return min(1.0, hits / total), matched, missed


def _experience_match(jd_lower: str, profile: Any, job_title: str = "") -> float:
    """Match experience based on job TITLE seniority only, plus explicit year requirements."""
    years = profile.candidate.years_experience

    # Seniority keywords — checked against the JOB TITLE only, not full description.
    # This avoids "mentor junior engineers" false positives.
    senior_keywords = ["senior", "lead", "principal", "head of", "manager", "director", "programme"]
    junior_keywords = ["junior", "graduate", "entry level", "entry-level", "intern", "apprentice"]

    title_lower = (job_title or "").lower()
    title_has_senior = any(_keyword_present(title_lower, kw) for kw in senior_keywords)
    title_has_junior = any(_keyword_present(title_lower, kw) for kw in junior_keywords)

    # Extract explicit year requirements from JD ("5+ years", "minimum 7 years", "at least 3 years")
    required_years: int | None = None
    year_patterns = [
        r"(\d+)\+\s*years?",
        r"minimum\s+(\d+)\s+years?",
        r"at least\s+(\d+)\s+years?",
        r"(\d+)\s+years?\s+(?:of\s+)?(?:experience|exp)",
    ]
    for pat in year_patterns:
        m = re.search(pat, jd_lower)
        if m:
            required_years = int(m.group(1))
            break

    # Score based on explicit year requirements if available
    if required_years is not None:
        gap = years - required_years
        if gap >= 0:
            return min(1.0, 0.8 + gap * 0.02)   # matches or exceeds
        else:
            return max(0.2, 0.8 + gap * 0.10)   # underqualified, penalise

    # Fall back to title-based seniority
    if title_has_junior and years > 5:
        return 0.2  # clearly overqualified
    if title_has_senior and years >= 7:
        return 0.9
    if not title_has_senior and not title_has_junior:
        return 0.7  # mid-level or unspecified, neutral

    # Title word overlap as a fallback
    candidate_title_words = [w for w in profile.candidate.title.lower().split() if len(w) > 3]
    title_matches = sum(1 for w in candidate_title_words if _keyword_present(title_lower, w))
    title_score = title_matches / len(candidate_title_words) if candidate_title_words else 0.5
    return max(0.3, min(0.95, title_score))


# Currency / rate context patterns — only extract numbers near these signals
_CURRENCY_CONTEXT_PATTERN = re.compile(
    r"""
    (?:                                   # currency symbol before or after
        (?:[£$€₹¥])\s*(\d[\d,\.]*(?:k|K)?)|  # £500, £75,000, £75k
        (\d[\d,\.]*(?:k|K)?)\s*(?:per\s+day|/day|pd\b|p\.d\b|per\s+annum|p\.a\b|pa\b|lpa\b|/yr\b)|
        (\d[\d,\.]*(?:k|K)?)\s*(?:GBP|USD|EUR|INR|gbp|usd|eur|inr)
    )
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Contextual range: "£550 - £650 per day", "550-650/day"
_RATE_RANGE_PATTERN = re.compile(
    r"[£$€₹]?\s*(\d[\d,\.]*(?:k|K)?)\s*[-–to]+\s*[£$€₹]?\s*(\d[\d,\.]*(?:k|K)?)"
    r"(?:\s*(?:per\s+day|/day|per\s+annum|p\.a|pa|per year|k\s*p\.?a\.?))?",
    re.IGNORECASE,
)


def _parse_amount(raw: str) -> float:
    """Parse '75k' → 75000, '75,000' → 75000, '650' → 650."""
    raw = raw.replace(",", "").strip()
    if raw.lower().endswith("k"):
        return float(raw[:-1]) * 1000
    return float(raw)


def _extract_rates(jd_lower: str) -> list[float]:
    """Extract salary/rate numbers that are clearly contextualised as pay rates."""
    found: list[float] = []

    # Range pattern first (e.g. £550 - £650/day)
    for m in _RATE_RANGE_PATTERN.finditer(jd_lower):
        for g in (1, 2):
            try:
                found.append(_parse_amount(m.group(g)))
            except (ValueError, TypeError, AttributeError):
                pass

    # Single currency-contextualised amounts
    for m in _CURRENCY_CONTEXT_PATTERN.finditer(jd_lower):
        for g in range(1, 4):
            if m.group(g):
                try:
                    found.append(_parse_amount(m.group(g)))
                except (ValueError, TypeError):
                    pass

    return found


def _rate_match(jd_lower: str, profile: Any) -> float:
    comp = profile.compensation
    if comp.min_rate == 0 and comp.max_rate == 0:
        return 0.7  # no target set — neutral

    rates = _extract_rates(jd_lower)
    if not rates:
        return 0.6  # rate not stated — neutral, don't penalise

    # Find the best-matching rate
    for rate in rates:
        if comp.rate_type == "daily":
            if 100 <= rate <= 3000:
                if comp.min_rate <= rate <= comp.max_rate * 1.2:
                    return 0.9
                elif rate > comp.max_rate * 1.5:
                    return 0.4  # over profile budget (rare but possible)
                elif rate >= comp.min_rate * 0.7:
                    return 0.7
        elif comp.rate_type == "annual":
            if 10000 <= rate <= 500000:
                if comp.min_rate <= rate <= comp.max_rate * 1.2:
                    return 0.9
                elif rate < comp.min_rate * 0.7:
                    return 0.3
                elif rate >= comp.min_rate * 0.85:
                    return 0.7

    return 0.5  # rates found but none matched profile type/range


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
    jd_lower = _normalise(
        (job.description or "") + " " + (job.location or "")
    )
    job_title = job.title or ""

    skill_score, matched, missed = _skill_match(jd_lower, profile)
    exp_score = _experience_match(jd_lower, profile, job_title=job_title)
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
        scoring_method="local",
    )
