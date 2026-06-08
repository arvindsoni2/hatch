"""CV Tailor — generates a tailored CV from master CV + JD analysis via Claude."""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from ..prompts import render_prompt
from ..schemas.tailor import JDAnalysisResult, TailoredCVResult, TailoredExperience
from ..skills.skill_loader import SkillLoader, SkillRegistry
from .claude_client import ClaudeClient
from .jd_analyser import _split_jinja_output
from .master_cv_validator import MasterCVError, normalise_master_cv, validate_master_cv

logger = logging.getLogger(__name__)

_MASTER_CV_PATH = Path(__file__).parent.parent / "templates" / "master_cv.json"
_FABRICATION_THRESHOLD = 70  # rapidfuzz score below this → warning
_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _default_skill_loader() -> SkillLoader:
    return SkillLoader(SkillRegistry(_SKILLS_DIR))


@lru_cache(maxsize=1)
def _load_master_cv_cached() -> dict[str, Any]:
    """Load and cache master CV JSON. Cached for process lifetime."""
    with _MASTER_CV_PATH.open() as fh:
        return json.load(fh)


class CVTailor:
    """Tailors the master CV to a specific job description."""

    def __init__(self, claude_client: ClaudeClient, skill_loader: SkillLoader | None = None) -> None:
        self._client = claude_client
        self._skill_loader = skill_loader or _default_skill_loader()

    def _load_master_cv(self) -> dict[str, Any]:
        """Return the cached master CV dict."""
        return _load_master_cv_cached()

    def _select_best_summary_variant(self, jd_analysis: JDAnalysisResult) -> str:
        """Pick the most relevant summary variant based on keyword overlap.

        Args:
            jd_analysis: Parsed JD analysis.

        Returns:
            Summary text of the best-matching variant.
        """
        master = self._load_master_cv()
        variants: dict[str, str] = master.get("summary_variants", {})
        if not variants:
            return ""

        all_jd_words = set(
            " ".join(
                jd_analysis.ats_keywords.technical
                + jd_analysis.ats_keywords.methodologies
                + jd_analysis.ats_keywords.domain
                + [jd_analysis.role_title or ""]
            )
            .lower()
            .split()
        )

        best_key = next(iter(variants))
        best_score = -1
        for key, text in variants.items():
            cv_words = set(text.lower().split())
            overlap = len(all_jd_words & cv_words)
            if overlap > best_score:
                best_score = overlap
                best_key = key

        return variants[best_key]

    async def tailor(
        self,
        jd_analysis: JDAnalysisResult,
        variant: str = "A",
        custom_instructions: str | None = None,
    ) -> TailoredCVResult:
        """Produce a tailored CV for the given JD analysis.

        Args:
            jd_analysis: Parsed JD analysis from JDAnalyser.
            variant: "A" (conservative) or "B" (achievement-led).
            custom_instructions: Optional free-text guidance for Claude.

        Returns:
            TailoredCVResult with validated content.
        """
        master_cv = normalise_master_cv(self._load_master_cv())
        errors = validate_master_cv(master_cv)
        if errors:
            raise MasterCVError(
                f"Master CV contains {len(errors)} placeholder field(s) — "
                f"tailoring blocked. Fix before generating documents.\n"
                + "\n".join(f"  • {e}" for e in errors)
            )

        best_summary = self._select_best_summary_variant(jd_analysis)
        skill_instructions = self._skill_loader.instructions("cv-tailoring")

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "cv_tailoring.j2",
                master_cv=master_cv,
                jd_analysis=jd_analysis.model_dump(),
                variant=variant,
                custom_instructions=custom_instructions or "",
                best_summary_variant=best_summary,
                skill_instructions=skill_instructions,
            )
        )
        raw: dict[str, Any] = await self._client.complete_json(system_prompt, user_prompt, max_tokens=6000)
        result = _parse_tailored_cv(raw)

        # Post-generation validation
        blocking, advisory = self._validate_no_fabrication(result, master_cv)
        result.blocking_issues = blocking
        result.fabrication_warnings = advisory
        if blocking:
            logger.warning("Blocking issues in tailored CV (document withheld): %s", blocking)
        if advisory:
            logger.warning("Advisory fabrication warnings for tailored CV: %s", advisory)

        return result

    def _validate_no_fabrication(
        self, tailored: TailoredCVResult, master: dict[str, Any]
    ) -> tuple[list[str], list[str]]:
        """Check the tailored CV for placeholder tokens (blocking) and invented content (advisory).

        Blocking issues surface to the Review gate so the user knows why a document is withheld.
        Advisory warnings are logged but don't block the result.

        Returns:
            (blocking, advisory) — two separate lists of human-readable strings.
        """
        from .master_cv_validator import _PLACEHOLDER_PATTERNS

        blocking: list[str] = []
        advisory: list[str] = []

        def _has_ph(text: str) -> bool:
            return any(pat.search(text) for pat in _PLACEHOLDER_PATTERNS)

        # -- Blocking: placeholder tokens in generated output --
        if _has_ph(tailored.summary):
            blocking.append(f"summary: contains placeholder text — {tailored.summary[:80]!r}")

        for idx, skill_group in enumerate(tailored.skills):
            for item in skill_group.get("items", []):
                if isinstance(item, str) and _has_ph(item):
                    blocking.append(f"skills[{idx}].items: placeholder — {item!r}")

        for cert in tailored.certifications:
            if isinstance(cert, str) and _has_ph(cert):
                blocking.append(f"certifications: placeholder — {cert!r}")

        for exp in tailored.experience:
            if _has_ph(exp.role):
                blocking.append(f"experience.role: placeholder company — {exp.role!r}")
            if _has_ph(exp.company):
                blocking.append(f"experience.company: placeholder company — {exp.company!r}")

        # -- Advisory: fuzzy achievement + summary grounding check --
        master_texts: list[str] = []
        for exp in master.get("experience", []):
            for ach in exp.get("achievements", []):
                master_texts.append(ach.get("text", ""))

        if master_texts and len(tailored.summary) >= 30:
            best = max(
                (fuzz.partial_ratio(tailored.summary, mt) for mt in master_texts), default=0
            )
            if best < _FABRICATION_THRESHOLD:
                advisory.append(
                    f"Summary low similarity to master CV (score={best}) — "
                    f"verify no invented content: {tailored.summary[:80]!r}"
                )

        for exp in tailored.experience:
            for achievement in exp.achievements:
                if len(achievement) < 30:
                    continue
                best_score = max(
                    (fuzz.partial_ratio(achievement, mt) for mt in master_texts), default=0
                )
                if best_score < _FABRICATION_THRESHOLD:
                    advisory.append(
                        f"Possible fabrication (score={best_score}): {achievement[:80]!r}"
                    )

        return blocking, advisory


def _parse_tailored_cv(raw: dict[str, Any]) -> TailoredCVResult:
    """Convert raw Claude JSON into TailoredCVResult."""
    experience: list[TailoredExperience] = []
    for exp_raw in raw.get("experience", []):
        experience.append(
            TailoredExperience(
                role=exp_raw.get("role", ""),
                company=exp_raw.get("company", ""),
                period=exp_raw.get("period", ""),
                achievements=exp_raw.get("achievements", []),
            )
        )

    return TailoredCVResult(
        summary=raw.get("summary", ""),
        skills=raw.get("skills", []),
        experience=experience,
        certifications=raw.get("certifications", []),
        ats_keywords_embedded=raw.get("ats_keywords_embedded", []),
        tailoring_notes=raw.get("tailoring_notes", ""),
    )
