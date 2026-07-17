from __future__ import annotations

from pathlib import Path

from app.services.prompt_catalog import PROMPT_CONTRACTS, prompt_contract


ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = ROOT / "backend" / "app" / "prompts"
SKILLS_DIR = ROOT / "backend" / "app" / "skills"
AUDIT_PATH = (
    ROOT
    / "docs"
    / "implementation-notes"
    / "PRODUCTION_PROMPT_AND_SKILL_AUDIT.md"
)

INLINE_PROMPT_IDS = {
    "cover_letter_paragraph_regeneration",
    "job_scoring_triage",
    "job_scoring_detailed",
    "job_scoring_judge",
    "rubric_synthesis",
    "email_post_application",
    "email_post_interview_thankyou",
    "email_warm_reengagement",
}


def test_catalog_covers_every_production_jinja_prompt() -> None:
    template_paths = {
        f"backend/app/prompts/{path.name}"
        for path in PROMPTS_DIR.glob("*.j2")
    }
    catalog_paths = {
        contract.path
        for contract in PROMPT_CONTRACTS.values()
        if contract.path.endswith(".j2")
    }

    assert catalog_paths == template_paths


def test_catalog_covers_all_known_inline_prompts() -> None:
    assert INLINE_PROMPT_IDS <= PROMPT_CONTRACTS.keys()


def test_every_prompt_has_stable_version_schema_and_family() -> None:
    for prompt_id, contract in PROMPT_CONTRACTS.items():
        assert contract.metadata.prompt_id == prompt_id
        assert contract.metadata.prompt_version
        assert contract.metadata.schema_version
        assert contract.metadata.task_name
        assert contract.family
        assert contract.output_schema


def test_prompt_contract_rejects_unknown_id() -> None:
    try:
        prompt_contract("not-a-production-prompt")
    except KeyError as exc:
        assert "not-a-production-prompt" in str(exc)
    else:
        raise AssertionError("unknown prompt ID must raise KeyError")


def test_checked_in_audit_covers_every_prompt_and_skill() -> None:
    audit = AUDIT_PATH.read_text(encoding="utf-8")
    for contract in PROMPT_CONTRACTS.values():
        assert contract.path in audit
    for skill_path in SKILLS_DIR.glob("*/SKILL.md"):
        relative = skill_path.relative_to(ROOT).as_posix()
        assert relative in audit
