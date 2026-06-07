"""
Regression guard: Agent Skills layer inventory and structure.

Guards against:
- Skills being accidentally deleted
- A skill directory losing its SKILL.md specification
- SkillLoader or SkillRegistry being removed
- No autonomous submission via the service
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).parent.parent.parent / "app" / "skills"

EXPECTED_SKILLS = [
    "cv-tailoring",
    "cover-letter",
    "ats-optimization",
    "company-research",
    "interview-prep",
    "screening-answers",
    "form-mapping",
]


class TestSkillsInventory:
    def test_all_seven_skills_exist(self):
        """All 7 agent skills must have a directory under app/skills/."""
        existing = {
            d.name
            for d in SKILLS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
        }
        for skill in EXPECTED_SKILLS:
            assert skill in existing, (
                f"Skill '{skill}' directory is missing from app/skills/. "
                f"Found: {sorted(existing)}"
            )

    def test_each_skill_has_skill_md(self):
        """Every skill directory must contain a SKILL.md specification."""
        for skill in EXPECTED_SKILLS:
            skill_md = SKILLS_DIR / skill / "SKILL.md"
            assert skill_md.exists(), (
                f"app/skills/{skill}/SKILL.md is missing. "
                "Each skill must have a SKILL.md spec."
            )
            assert skill_md.stat().st_size > 0, (
                f"app/skills/{skill}/SKILL.md is empty."
            )

    def test_skill_loader_module_exists(self):
        """app/skills/skill_loader.py must exist and import cleanly."""
        loader = SKILLS_DIR / "skill_loader.py"
        assert loader.exists(), "app/skills/skill_loader.py is missing."

    def test_skill_wrappers_module_exists(self):
        """app/skills/wrappers.py must exist and import cleanly."""
        wrappers = SKILLS_DIR / "wrappers.py"
        assert wrappers.exists(), "app/skills/wrappers.py is missing."

    def test_skill_registry_importable(self):
        """SkillRegistry must be importable from app.skills.skill_loader."""
        mod = importlib.import_module("app.skills.skill_loader")
        assert hasattr(mod, "SkillRegistry"), (
            "SkillRegistry class not found in app.skills.skill_loader."
        )

    def test_skill_loader_class_importable(self):
        """SkillLoader must be importable from app.skills.skill_loader."""
        mod = importlib.import_module("app.skills.skill_loader")
        assert hasattr(mod, "SkillLoader"), (
            "SkillLoader class not found in app.skills.skill_loader."
        )

    def test_skill_count_in_registry(self):
        """SkillRegistry.list() must return all 7 expected skills."""
        from app.skills.skill_loader import SkillRegistry

        registry = SkillRegistry(skills_dir=SKILLS_DIR)
        listed = set(registry.list())

        for skill_id in EXPECTED_SKILLS:
            assert skill_id in listed, (
                f"SkillRegistry does not list '{skill_id}'. "
                f"Got: {sorted(listed)}"
            )


class TestNoAutonomousSubmission:
    """CRITICAL invariant: the apply service must never autonomously submit."""

    def test_no_submit_method_on_service(self):
        """AssistedApplyService must not expose a submit() method."""
        from app.services.assisted_apply import AssistedApplyService

        service = AssistedApplyService.__new__(AssistedApplyService)
        assert not hasattr(service, "submit"), (
            "AssistedApplyService must NOT have a submit() method — "
            "autonomous submission is forbidden by the v4 spec."
        )

    def test_assisted_apply_source_has_no_autonomous_post(self):
        """The assisted_apply module must not call httpx.post or requests.post."""
        import app.services.assisted_apply as m

        src = Path(m.__file__).read_text()
        assert "httpx.post" not in src, (
            "app/services/assisted_apply.py calls httpx.post — "
            "this could enable autonomous submission."
        )
        assert "requests.post" not in src, (
            "app/services/assisted_apply.py calls requests.post — "
            "this could enable autonomous submission."
        )
