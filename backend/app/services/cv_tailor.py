"""CV Tailor — generates a tailored CV from master CV + JD analysis via Claude."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..prompts import render_prompt
from ..schemas.tailor import JDAnalysisResult, TailoredCVResult, TailoredExperience
from ..skills.skill_loader import SkillLoader, SkillRegistry
from .llm_client import LLMClient
from ..agents.tools.context_budgets import CV_GENERATE
from .jd_analyser import _split_jinja_output
from .master_cv_store import MasterCVMissingError, load_master_cv  # noqa: F401
from .master_cv_validator import MasterCVError, normalise_master_cv, validate_master_cv

logger = logging.getLogger(__name__)

_FABRICATION_THRESHOLD = 70  # rapidfuzz score below this → warning
_SKILLS_DIR = Path(__file__).parent.parent / "skills"


def _default_skill_loader() -> SkillLoader:
    return SkillLoader(SkillRegistry(_SKILLS_DIR))


class CVTailor:
    """Tailors the master CV to a specific job description."""

    def __init__(self, claude_client: LLMClient, skill_loader: SkillLoader | None = None) -> None:
        self._client = claude_client
        self._skill_loader = skill_loader or _default_skill_loader()

    def _load_master_cv(self) -> dict[str, Any]:
        """Return the master CV, loaded via the central store (mtime-cached)."""
        return load_master_cv()

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

    def _compact_jd(self, jd_analysis: JDAnalysisResult) -> dict[str, Any]:
        """Return a compact JD summary for the prompt (avoids over-stuffing the context window).

        Passes only must-have requirements, company name, sector, contract_type, and the
        top 15 ATS keywords — enough for accurate tailoring without the full analysis JSON.
        """
        cc = jd_analysis.company_context
        cd = jd_analysis.contract_details
        all_kws = (
            jd_analysis.ats_keywords.technical[:8]
            + jd_analysis.ats_keywords.methodologies[:4]
            + jd_analysis.ats_keywords.domain[:3]
        )
        return {
            "role_title": jd_analysis.role_title,
            "seniority_level": jd_analysis.seniority_level,
            "company_name": cc.company_name if cc else None,
            "sector": cc.sector if cc else None,
            "contract_type": cd.contract_type if cd else None,
            "must_have": jd_analysis.requirements.must_have[:10],
            "top_keywords": all_kws[:15],
            "culture_indicators": (cc.culture_indicators[:3] if cc else []),
        }

    def _select_relevant_cv_slices(
        self, jd_analysis: JDAnalysisResult, master_cv: dict[str, Any]
    ) -> dict[str, Any]:
        """Return a trimmed master CV containing only content relevant to this JD.

        Keeps prompt size manageable for all models (local and cloud alike):
          - The best summary variant (already selected by _select_best_summary_variant)
          - The top 3 experience entries by keyword overlap with the JD
          - All skill groups (compact — items only, no nested metadata)
          - Certifications list
        """
        all_jd_words = set(
            " ".join(
                jd_analysis.requirements.must_have
                + jd_analysis.ats_keywords.technical
                + jd_analysis.ats_keywords.domain
                + [jd_analysis.role_title or ""]
            ).lower().split()
        )

        # Score each experience entry by keyword overlap
        experiences = master_cv.get("experience", [])
        scored: list[tuple[int, dict]] = []
        for exp in experiences:
            if not isinstance(exp, dict):
                continue
            text = " ".join(
                [exp.get("role", ""), exp.get("company", "")]
                + [a.get("text", "") if isinstance(a, dict) else str(a) for a in exp.get("achievements", [])]
            ).lower()
            overlap = len(all_jd_words & set(text.split()))
            scored.append((overlap, exp))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_exp = [exp for _, exp in scored[:3]]

        # Compact skills: strip nested metadata, keep category + items
        raw_skills = master_cv.get("skills", {})
        compact_skills: list[dict[str, Any]] = []
        if isinstance(raw_skills, dict):
            for _key, group in raw_skills.items():
                if isinstance(group, dict):
                    compact_skills.append({
                        "category": group.get("category") or group.get("display_name") or _key,
                        "items": group.get("items", []),
                    })
        elif isinstance(raw_skills, list):
            compact_skills = raw_skills

        return {
            "personal": master_cv.get("personal", {}),
            "summary_variants": master_cv.get("summary_variants", {}),
            "experience": top_exp,
            "skills": compact_skills,
            "certifications": master_cv.get("certifications", []),
        }

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
        cv_slices = self._select_relevant_cv_slices(jd_analysis, master_cv)
        jd_compact = self._compact_jd(jd_analysis)

        system_prompt, user_prompt = _split_jinja_output(
            render_prompt(
                "cv_tailoring.j2",
                master_cv=cv_slices,
                jd_analysis=jd_compact,
                variant=variant,
                custom_instructions=custom_instructions or "",
                best_summary_variant=best_summary,
                skill_instructions=skill_instructions,
            )
        )
        raw: dict[str, Any] = await self._client.complete_json(system_prompt, user_prompt, max_tokens=CV_GENERATE.max_output)
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
        """Delegate to the entity-level grounding validator (G-5).

        Returns:
            (blocking, advisory) — two separate lists of human-readable strings.
        """
        from .grounding_validator import validate  # noqa: PLC0415
        return validate(tailored, master)


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
