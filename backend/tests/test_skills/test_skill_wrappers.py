"""Tests for the 5 thin skill wrappers — parity with the wrapped service."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock


_SKILLS_DIR = Path(__file__).parent.parent.parent / "app" / "skills"


def _make_loader():
    from app.skills.skill_loader import SkillLoader, SkillRegistry
    return SkillLoader(SkillRegistry(_SKILLS_DIR))


# ──────────────────────────────────────────────────────────────────────────────
# CvTailoringSkill
# ──────────────────────────────────────────────────────────────────────────────


class TestCvTailoringSkill:

    def test_skill_name_matches_registry(self):
        """CvTailoringSkill.skill_name == 'cv-tailoring'."""
        from app.skills.wrappers import CvTailoringSkill
        assert CvTailoringSkill.skill_name == "cv-tailoring"

    def test_metadata_returns_frontmatter(self):
        """metadata() returns the cv-tailoring SKILL.md frontmatter."""
        from app.skills.wrappers import CvTailoringSkill
        skill = CvTailoringSkill(service=MagicMock(), loader=_make_loader())
        meta = skill.metadata()
        assert meta["name"] == "cv-tailoring"
        assert meta["description"]

    def test_instructions_returns_non_empty_body(self):
        """instructions() returns non-empty markdown body."""
        from app.skills.wrappers import CvTailoringSkill
        skill = CvTailoringSkill(service=MagicMock(), loader=_make_loader())
        assert skill.instructions()

    async def test_invoke_calls_service_tailor_with_jd_analysis(self):
        """invoke() delegates to CVTailor.tailor(jd_analysis)."""
        from app.skills.wrappers import CvTailoringSkill
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_service.tailor = AsyncMock(return_value=mock_result)
        jd_analysis = MagicMock()

        skill = CvTailoringSkill(service=mock_service, loader=MagicMock())
        result = await skill.invoke(jd_analysis)

        mock_service.tailor.assert_called_once_with(jd_analysis)
        assert result is mock_result

    async def test_invoke_passes_kwargs_to_service(self):
        """invoke() forwards variant and custom_instructions kwargs to the service."""
        from app.skills.wrappers import CvTailoringSkill
        mock_service = MagicMock()
        mock_service.tailor = AsyncMock(return_value=MagicMock())
        jd_analysis = MagicMock()

        skill = CvTailoringSkill(service=mock_service, loader=MagicMock())
        await skill.invoke(jd_analysis, variant="B", custom_instructions="Focus on cloud")

        mock_service.tailor.assert_called_once_with(
            jd_analysis, variant="B", custom_instructions="Focus on cloud"
        )


# ──────────────────────────────────────────────────────────────────────────────
# CoverLetterSkill
# ──────────────────────────────────────────────────────────────────────────────


class TestCoverLetterSkill:

    def test_skill_name_matches_registry(self):
        """CoverLetterSkill.skill_name == 'cover-letter'."""
        from app.skills.wrappers import CoverLetterSkill
        assert CoverLetterSkill.skill_name == "cover-letter"

    def test_metadata_returns_frontmatter(self):
        from app.skills.wrappers import CoverLetterSkill
        skill = CoverLetterSkill(service=MagicMock(), loader=_make_loader())
        meta = skill.metadata()
        assert meta["name"] == "cover-letter"
        assert meta["description"]

    async def test_invoke_calls_service_generate(self):
        """invoke() delegates to CoverLetterGenerator.generate()."""
        from app.skills.wrappers import CoverLetterSkill
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_service.generate = AsyncMock(return_value=mock_result)
        jd_analysis = MagicMock()
        tailored_cv = MagicMock()
        personal = {"name": "Arvind"}

        skill = CoverLetterSkill(service=mock_service, loader=MagicMock())
        result = await skill.invoke(jd_analysis, tailored_cv, personal)

        mock_service.generate.assert_called_once_with(jd_analysis, tailored_cv, personal)
        assert result is mock_result

    async def test_invoke_passes_variant_kwarg(self):
        """invoke() forwards variant kwarg to service.generate()."""
        from app.skills.wrappers import CoverLetterSkill
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(return_value=MagicMock())
        jd_analysis = MagicMock()
        tailored_cv = MagicMock()
        personal = {}

        skill = CoverLetterSkill(service=mock_service, loader=MagicMock())
        await skill.invoke(jd_analysis, tailored_cv, personal, variant="B")

        mock_service.generate.assert_called_once_with(
            jd_analysis, tailored_cv, personal, variant="B"
        )


# ──────────────────────────────────────────────────────────────────────────────
# AtsOptimizationSkill
# ──────────────────────────────────────────────────────────────────────────────


class TestAtsOptimizationSkill:

    def test_skill_name_matches_registry(self):
        """AtsOptimizationSkill.skill_name == 'ats-optimization'."""
        from app.skills.wrappers import AtsOptimizationSkill
        assert AtsOptimizationSkill.skill_name == "ats-optimization"

    def test_metadata_returns_frontmatter(self):
        from app.skills.wrappers import AtsOptimizationSkill
        skill = AtsOptimizationSkill(service=MagicMock(), loader=_make_loader())
        meta = skill.metadata()
        assert meta["name"] == "ats-optimization"
        assert meta["description"]

    async def test_invoke_calls_service_score(self):
        """invoke() delegates to ATSOptimiser.score(cv_text, jd_analysis)."""
        from app.skills.wrappers import AtsOptimizationSkill
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_service.score = AsyncMock(return_value=mock_result)
        cv_text = "Python developer with AWS experience."
        jd_analysis = MagicMock()

        skill = AtsOptimizationSkill(service=mock_service, loader=MagicMock())
        result = await skill.invoke(cv_text, jd_analysis)

        mock_service.score.assert_called_once_with(cv_text, jd_analysis)
        assert result is mock_result

    def test_lint_script_accessible_via_loader(self):
        """ats_lint script is accessible through the skill's loader."""
        from app.skills.wrappers import AtsOptimizationSkill
        skill = AtsOptimizationSkill(service=MagicMock(), loader=_make_loader())
        fn = skill.lint_script()
        assert callable(fn)
        score = fn("Python developer", ["Python"])
        assert score == 1.0


# ──────────────────────────────────────────────────────────────────────────────
# CompanyResearchSkill
# ──────────────────────────────────────────────────────────────────────────────


class TestCompanyResearchSkill:

    def test_skill_name_matches_registry(self):
        """CompanyResearchSkill.skill_name == 'company-research'."""
        from app.skills.wrappers import CompanyResearchSkill
        assert CompanyResearchSkill.skill_name == "company-research"

    def test_metadata_returns_frontmatter(self):
        from app.skills.wrappers import CompanyResearchSkill
        skill = CompanyResearchSkill(service=MagicMock(), loader=_make_loader())
        meta = skill.metadata()
        assert meta["name"] == "company-research"
        assert meta["description"]

    async def test_invoke_calls_service_research(self):
        """invoke() delegates to CompanyResearchService.research(company_name)."""
        from app.skills.wrappers import CompanyResearchSkill
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_service.research = AsyncMock(return_value=mock_result)

        skill = CompanyResearchSkill(service=mock_service, loader=MagicMock())
        result = await skill.invoke("Acme Corp")

        mock_service.research.assert_called_once_with("Acme Corp")
        assert result is mock_result

    async def test_invoke_passes_sector_kwarg(self):
        """invoke() forwards sector kwarg to service.research()."""
        from app.skills.wrappers import CompanyResearchSkill
        mock_service = MagicMock()
        mock_service.research = AsyncMock(return_value=MagicMock())

        skill = CompanyResearchSkill(service=mock_service, loader=MagicMock())
        await skill.invoke("Acme Corp", sector="FinTech")

        mock_service.research.assert_called_once_with("Acme Corp", sector="FinTech")


# ──────────────────────────────────────────────────────────────────────────────
# InterviewPrepSkill
# ──────────────────────────────────────────────────────────────────────────────


class TestInterviewPrepSkill:

    def test_skill_name_matches_registry(self):
        """InterviewPrepSkill.skill_name == 'interview-prep'."""
        from app.skills.wrappers import InterviewPrepSkill
        assert InterviewPrepSkill.skill_name == "interview-prep"

    def test_metadata_returns_frontmatter(self):
        from app.skills.wrappers import InterviewPrepSkill
        skill = InterviewPrepSkill(service=MagicMock(), loader=_make_loader())
        meta = skill.metadata()
        assert meta["name"] == "interview-prep"
        assert meta["description"]

    def test_star_framework_accessible_as_resource(self):
        """star_framework() loads the star_framework.md resource."""
        from app.skills.wrappers import InterviewPrepSkill
        skill = InterviewPrepSkill(service=MagicMock(), loader=_make_loader())
        content = skill.star_framework()
        assert "STAR" in content
        assert "#" in content  # has markdown headings

    async def test_invoke_calls_service_generate(self):
        """invoke() delegates to QuestionGeneratorService.generate()."""
        from app.skills.wrappers import InterviewPrepSkill
        mock_service = MagicMock()
        mock_result = [MagicMock()]
        mock_service.generate = AsyncMock(return_value=mock_result)
        config = MagicMock()
        company_name = "Acme Corp"
        role_title = "Solutions Architect"

        skill = InterviewPrepSkill(service=mock_service, loader=MagicMock())
        result = await skill.invoke(config, company_name, role_title)

        mock_service.generate.assert_called_once_with(config, company_name, role_title)
        assert result is mock_result

    async def test_invoke_passes_optional_kwargs(self):
        """invoke() forwards company_research and jd_text kwargs to service."""
        from app.skills.wrappers import InterviewPrepSkill
        mock_service = MagicMock()
        mock_service.generate = AsyncMock(return_value=[])
        config = MagicMock()
        company_research = MagicMock()
        jd_text = "Python engineer..."

        skill = InterviewPrepSkill(service=mock_service, loader=MagicMock())
        await skill.invoke(
            config, "Acme", "Engineer",
            company_research=company_research, jd_text=jd_text,
        )

        mock_service.generate.assert_called_once_with(
            config, "Acme", "Engineer",
            company_research=company_research, jd_text=jd_text,
        )
