from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_docs", ROOT / "scripts" / "check_docs.py")
assert SPEC and SPEC.loader
check_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_docs)


def test_validate_front_matter_requires_expected_keys(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "architecture" / "OVERVIEW.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# Missing metadata\n", encoding="utf-8")

    errors = check_docs.validate_front_matter(
        [doc],
        root=tmp_path,
    )

    assert errors == [
        "docs/architecture/OVERVIEW.md: missing required YAML front matter"
    ]


def test_validate_stale_paths_flags_moved_references_in_current_docs(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "implementation-specs" / "active" / "example.md"
    doc.parent.mkdir(parents=True)
    doc.write_text(
        """---
document_type: implementation-spec
status: active
implementation_status: partial
applies_to: main
last_verified: 2026-07-11
---

Use docs/hatch_ux_gap_review_codex_spec.md when resuming this work.
""",
        encoding="utf-8",
    )

    errors = check_docs.validate_stale_paths([doc], root=tmp_path)

    assert errors == [
        "docs/implementation-specs/active/example.md: stale moved-path reference 'docs/hatch_ux_gap_review_codex_spec.md' -> 'docs/implementation-specs/active/hatch_ux_gap_review_codex_spec.md'"
    ]


def test_validate_mermaid_fences_detects_unclosed_block(tmp_path: Path) -> None:
    doc = tmp_path / "README.md"
    doc.write_text(
        """# Example

```mermaid
graph TD
A --> B
""",
        encoding="utf-8",
    )

    errors = check_docs.validate_mermaid_fences([doc], root=tmp_path)

    assert errors == ["README.md: unclosed mermaid fence"]


def test_collect_markdown_targets_excludes_archive_and_includes_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Root\n", encoding="utf-8")
    docs = tmp_path / "docs"
    (docs / "archive").mkdir(parents=True)
    (docs / "user-guide").mkdir(parents=True)
    (docs / "archive" / "old.md").write_text("# Historical\n", encoding="utf-8")
    (docs / "user-guide" / "TODAY.md").write_text("# Current\n", encoding="utf-8")

    targets = check_docs.collect_markdown_targets(tmp_path)

    assert tmp_path / "README.md" in targets
    assert docs / "user-guide" / "TODAY.md" in targets
    assert docs / "archive" / "old.md" not in targets


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("architecture", True),
        ("historical", True),
        ("wrong", False),
    ],
)
def test_validate_enum_value(value: str, expected: bool) -> None:
    errors = check_docs.validate_front_matter_mapping(
        {
            "document_type": value,
            "status": "current",
            "implementation_status": "not-applicable",
            "applies_to": "main",
            "last_verified": "2026-07-11",
        },
        "docs/example.md",
    )

    assert (not errors) is expected
