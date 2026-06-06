"""Tests for SkillRegistry and SkillLoader — progressive disclosure, fallbacks."""
from __future__ import annotations

from pathlib import Path

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

ALL_SKILL_NAMES = {
    "cv-tailoring",
    "cover-letter",
    "ats-optimization",
    "company-research",
    "interview-prep",
    "screening-answers",
    "form-mapping",
}

# Path under backend/app/skills/ (real location used by production code)
_SKILLS_DIR = Path(__file__).parent.parent.parent / "app" / "skills"


# ──────────────────────────────────────────────────────────────────────────────
# SkillRegistry
# ──────────────────────────────────────────────────────────────────────────────


class TestSkillRegistry:

    def test_registry_discovers_all_seven_skills(self):
        """SkillRegistry.list() returns all 7 skill folder names."""
        from app.skills.skill_loader import SkillRegistry

        registry = SkillRegistry(_SKILLS_DIR)
        names = set(registry.list())
        assert names == ALL_SKILL_NAMES

    def test_registry_list_is_sorted(self):
        """SkillRegistry.list() returns names in consistent alphabetical order."""
        from app.skills.skill_loader import SkillRegistry

        registry = SkillRegistry(_SKILLS_DIR)
        names = registry.list()
        assert names == sorted(names)

    def test_registry_has_returns_true_for_known_skill(self):
        """SkillRegistry.has(name) returns True for a registered skill."""
        from app.skills.skill_loader import SkillRegistry

        registry = SkillRegistry(_SKILLS_DIR)
        assert registry.has("cv-tailoring") is True

    def test_registry_has_returns_false_for_unknown_skill(self):
        """SkillRegistry.has(name) returns False for an unregistered skill."""
        from app.skills.skill_loader import SkillRegistry

        registry = SkillRegistry(_SKILLS_DIR)
        assert registry.has("nonexistent-skill") is False


# ──────────────────────────────────────────────────────────────────────────────
# SkillLoader — metadata (cheap: frontmatter only)
# ──────────────────────────────────────────────────────────────────────────────


class TestSkillLoaderMetadata:

    def test_metadata_returns_name_description_and_when_to_use(self):
        """metadata() returns a dict with name, description, when_to_use keys."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        meta = loader.metadata("cv-tailoring")
        assert meta["name"] == "cv-tailoring"
        assert isinstance(meta["description"], str) and meta["description"]
        assert isinstance(meta["when_to_use"], str) and meta["when_to_use"]

    def test_metadata_does_not_include_instructions_body(self):
        """metadata() returns only the frontmatter — the instructions body is absent."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        meta = loader.metadata("cv-tailoring")
        # The full instructions live in the SKILL.md body; metadata must not include them
        assert "instructions" not in meta

    def test_metadata_for_missing_skill_returns_fallback(self):
        """metadata() for an unknown skill returns a fallback dict rather than raising."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        meta = loader.metadata("does-not-exist")
        assert meta["name"] == "does-not-exist"
        assert meta["description"] == ""
        assert meta["when_to_use"] == ""

    def test_metadata_all_skills_have_non_empty_description(self):
        """Every registered skill SKILL.md has a non-empty description."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        registry = SkillRegistry(_SKILLS_DIR)
        loader = SkillLoader(registry)
        for name in registry.list():
            meta = loader.metadata(name)
            assert meta["description"], f"Skill '{name}' has empty description"


# ──────────────────────────────────────────────────────────────────────────────
# SkillLoader — instructions (expensive: full SKILL.md body)
# ──────────────────────────────────────────────────────────────────────────────


class TestSkillLoaderInstructions:

    def test_instructions_returns_markdown_body_without_frontmatter(self):
        """instructions() returns the SKILL.md body (no YAML frontmatter markers)."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        body = loader.instructions("cv-tailoring")
        assert isinstance(body, str) and body.strip()
        # Frontmatter delimiters must not appear in the returned string
        assert "---" not in body

    def test_instructions_for_missing_skill_returns_empty_string(self):
        """instructions() for an unknown skill returns '' (not an exception)."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        body = loader.instructions("does-not-exist")
        assert body == ""

    def test_instructions_different_from_metadata(self):
        """instructions() returns more content than metadata() for the same skill."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        meta = loader.metadata("cv-tailoring")
        body = loader.instructions("cv-tailoring")
        # Instructions body should be substantially longer than the description string
        assert len(body) > len(meta["description"])


# ──────────────────────────────────────────────────────────────────────────────
# SkillLoader — resources (on-demand file content)
# ──────────────────────────────────────────────────────────────────────────────


class TestSkillLoaderResources:

    def test_resource_returns_file_content_as_string(self):
        """resource() returns the raw string content of a resources/ file."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        content = loader.resource("cv-tailoring", "cv_patterns.yaml")
        assert isinstance(content, str) and content.strip()

    def test_resource_missing_file_raises_file_not_found(self):
        """resource() raises FileNotFoundError for a non-existent resource file."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        with pytest.raises(FileNotFoundError):
            loader.resource("cv-tailoring", "does_not_exist.yaml")

    def test_resource_missing_skill_raises_key_error(self):
        """resource() raises KeyError when the skill itself does not exist."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        with pytest.raises(KeyError):
            loader.resource("nonexistent-skill", "anything.yaml")

    def test_resource_star_framework_is_markdown(self):
        """interview-prep star_framework.md resource is a non-empty markdown string."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        content = loader.resource("interview-prep", "star_framework.md")
        assert "#" in content  # at least one markdown heading


# ──────────────────────────────────────────────────────────────────────────────
# SkillLoader — scripts (callable tools)
# ──────────────────────────────────────────────────────────────────────────────


class TestSkillLoaderScripts:

    def test_script_returns_callable(self):
        """script() returns a callable Python object for a scripts/ file."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        fn = loader.script("ats-optimization", "ats_lint.py")
        assert callable(fn)

    def test_script_ats_lint_accepts_cv_and_keywords(self):
        """ats_lint script takes cv_text and keywords and returns a score between 0-1."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        fn = loader.script("ats-optimization", "ats_lint.py")
        score = fn("Python developer with AWS experience.", ["Python", "AWS", "Docker"])
        assert 0.0 <= score <= 1.0

    def test_script_ats_lint_full_match_returns_high_score(self):
        """ats_lint returns score >= 0.8 when all keywords appear in the CV text."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        fn = loader.script("ats-optimization", "ats_lint.py")
        cv = "Python developer. Uses AWS daily. Runs Docker containers."
        score = fn(cv, ["Python", "AWS", "Docker"])
        assert score >= 0.8

    def test_script_ats_lint_no_match_returns_zero(self):
        """ats_lint returns 0.0 when no keywords appear in the CV text."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        fn = loader.script("ats-optimization", "ats_lint.py")
        score = fn("Senior pastry chef with baking expertise.", ["Python", "AWS", "Docker"])
        assert score == 0.0

    def test_script_missing_file_raises_file_not_found(self):
        """script() raises FileNotFoundError for a non-existent script."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        with pytest.raises(FileNotFoundError):
            loader.script("ats-optimization", "nonexistent.py")

    def test_script_cv_tailoring_extract_keywords_returns_list(self):
        """extract_jd_keywords script returns a list of keyword strings."""
        from app.skills.skill_loader import SkillLoader, SkillRegistry

        loader = SkillLoader(SkillRegistry(_SKILLS_DIR))
        fn = loader.script("cv-tailoring", "extract_jd_keywords.py")
        jd = "We need a Python engineer with AWS, Docker, and Kubernetes experience."
        keywords = fn(jd)
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert all(isinstance(k, str) for k in keywords)
