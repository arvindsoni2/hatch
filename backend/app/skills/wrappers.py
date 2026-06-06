"""Thin skill wrappers — each wraps an existing service behind the SkillLoader interface.

Each wrapper:
  - Declares a ``skill_name`` matching its folder in ``app/skills/``
  - Exposes ``metadata()`` and ``instructions()`` via the injected SkillLoader
  - Delegates its ``invoke()`` call directly to the underlying service
"""
from __future__ import annotations

from typing import Any

from .skill_loader import SkillLoader


class _BaseSkill:
    skill_name: str = ""

    def __init__(self, service: Any, loader: SkillLoader) -> None:
        self._service = service
        self._loader = loader

    def metadata(self) -> dict[str, str]:
        return self._loader.metadata(self.skill_name)

    def instructions(self) -> str:
        return self._loader.instructions(self.skill_name)


class CvTailoringSkill(_BaseSkill):
    """Wraps CVTailor — tailors a master CV to a specific JD."""

    skill_name = "cv-tailoring"

    async def invoke(self, jd_analysis: Any, **kwargs: Any) -> Any:
        return await self._service.tailor(jd_analysis, **kwargs)


class CoverLetterSkill(_BaseSkill):
    """Wraps CoverLetterGenerator — generates a tailored cover letter."""

    skill_name = "cover-letter"

    async def invoke(
        self,
        jd_analysis: Any,
        tailored_cv: Any,
        personal: dict[str, Any],
        **kwargs: Any,
    ) -> Any:
        return await self._service.generate(jd_analysis, tailored_cv, personal, **kwargs)


class AtsOptimizationSkill(_BaseSkill):
    """Wraps ATSOptimiser — scores a CV against JD keywords."""

    skill_name = "ats-optimization"

    async def invoke(self, cv_text: str, jd_analysis: Any) -> Any:
        return await self._service.score(cv_text, jd_analysis)

    def lint_script(self):
        """Return the deterministic ats_lint callable."""
        return self._loader.script(self.skill_name, "ats_lint.py")


class CompanyResearchSkill(_BaseSkill):
    """Wraps CompanyResearchService — researches a company for interview prep."""

    skill_name = "company-research"

    async def invoke(self, company_name: str, **kwargs: Any) -> Any:
        return await self._service.research(company_name, **kwargs)


class InterviewPrepSkill(_BaseSkill):
    """Wraps QuestionGeneratorService — generates weighted interview questions."""

    skill_name = "interview-prep"

    def star_framework(self) -> str:
        """Return the STAR framework markdown resource."""
        return self._loader.resource(self.skill_name, "star_framework.md")

    async def invoke(
        self,
        config: Any,
        company_name: str,
        role_title: str,
        **kwargs: Any,
    ) -> Any:
        return await self._service.generate(config, company_name, role_title, **kwargs)
