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
        """Return the complete CV, with roles ordered by relevance to the JD.

        Tailoring must preserve the master CV's breadth and approximate length, so
        every role and achievement is supplied to the model. Relevance changes
        emphasis and ordering; it must not silently delete career history.
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
        ordered_exp = [exp for _, exp in scored]

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
            "experience": ordered_exp,
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
        result = _preserve_master_structure(result, master_cv)

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


def _achievement_texts(exp: dict[str, Any]) -> list[str]:
    return [
        item.get("text", "") if isinstance(item, dict) else str(item)
        for item in exp.get("achievements", [])
        if item
    ]


def _similar_length(candidate: str, source: str) -> bool:
    source_words = max(1, len(source.split()))
    ratio = len(candidate.split()) / source_words
    return 0.7 <= ratio <= 1.3


def _preserve_master_structure(
    tailored: TailoredCVResult, master: dict[str, Any]
) -> TailoredCVResult:
    """Keep all source roles, bullet counts, identities, and certifications.

    The LLM may rephrase achievements, but it cannot shorten the CV by omitting
    roles or reinterpret an award/employer as a certification. If a role has an
    incomplete bullet set, the original grounded bullets are used for that role.
    """
    generated = {
        (exp.role.strip().casefold(), exp.company.strip().casefold()): exp
        for exp in tailored.experience
    }
    preserved: list[TailoredExperience] = []
    for source in master.get("experience", []):
        if not isinstance(source, dict):
            continue
        role = str(source.get("role", ""))
        company = str(source.get("company", ""))
        period = str(source.get("period") or source.get("dates") or "")
        source_bullets = _achievement_texts(source)
        candidate = generated.get((role.strip().casefold(), company.strip().casefold()))
        achievements = source_bullets
        if candidate and len(candidate.achievements) == len(source_bullets):
            achievements = [
                generated if _similar_length(generated, original) else original
                for generated, original in zip(candidate.achievements, source_bullets)
            ]
        preserved.append(TailoredExperience(
            role=role,
            company=company,
            period=period,
            achievements=achievements,
        ))

    tailored.experience = preserved
    generated_skills = {
        str(group.get("category") or group.get("display_name") or "").casefold(): group
        for group in tailored.skills
        if isinstance(group, dict)
    }
    preserved_skills: list[dict[str, Any]] = []
    raw_skills = master.get("skills", {})
    skill_groups = raw_skills.items() if isinstance(raw_skills, dict) else enumerate(raw_skills)
    for key, source_group in skill_groups:
        if not isinstance(source_group, dict):
            continue
        category = str(
            source_group.get("category") or source_group.get("display_name") or key
        )
        source_items = [str(item) for item in source_group.get("items", []) if item]
        candidate_group = generated_skills.get(category.casefold(), {})
        candidate_items = [
            str(item) for item in candidate_group.get("items", [])
            if str(item) in source_items
        ]
        ordered_items = candidate_items + [
            item for item in source_items if item not in candidate_items
        ]
        preserved_skills.append({"category": category, "items": ordered_items})
    tailored.skills = preserved_skills
    tailored.certifications = [
        str(cert) for cert in master.get("certifications", []) if cert
    ]
    return tailored
