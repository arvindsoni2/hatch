#!/usr/bin/env python3
"""Validate release-facing documentation structure and metadata."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROOT_MARKDOWN = ("README.md", "CONTRIBUTING.md", "CHANGELOG.md")
MARKDOWN_EXTENSIONS = {".md", ".markdown"}
MOVED_PATHS = {
    "docs/OPERATIONS.md": "docs/operations/OPERATIONS.md",
    "docs/RELEASE_CHECKLIST.md": "docs/operations/RELEASE_CHECKLIST.md",
    "docs/ROUTE_TAXONOMY.md": "docs/development/ROUTE_TAXONOMY.md",
    "docs/WINDOWS_INSTALL.md": "docs/getting-started/WINDOWS_INSTALL.md",
    "docs/Hatch_Backend_Container_Optimisation_Spec.md": (
        "docs/implementation-specs/active/Hatch_Backend_Container_Optimisation_Spec.md"
    ),
    "docs/Hatch_Easy_Install_Hardware_Model_Selection_Spec_v8.md": (
        "docs/implementation-specs/completed/Hatch_Easy_Install_Hardware_Model_Selection_Spec_v8.md"
    ),
    "docs/hatch_ux_gap_review_codex_spec.md": (
        "docs/implementation-specs/active/hatch_ux_gap_review_codex_spec.md"
    ),
    "docs/images/": "docs/visual-evidence/readme/",
    "docs/design/": "docs/archive/superseded/design/",
    "docs/features/": "docs/archive/superseded/features/",
}
ALLOWED_FRONT_MATTER = {
    "document_type": {"architecture", "implementation-spec", "historical"},
    "status": {"current", "active", "implemented", "historical"},
    "implementation_status": {"not-applicable", "partial", "complete"},
    "applies_to": {"main", "main/latest"},
}
REQUIRED_FRONT_MATTER_KEYS = tuple(ALLOWED_FRONT_MATTER) + ("last_verified",)


def fail(errors: list[str]) -> int:
    print("Documentation validation failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def collect_markdown_targets(root: Path) -> list[Path]:
    targets: list[Path] = []
    for name in ROOT_MARKDOWN:
        path = root / name
        if path.exists():
            targets.append(path)

    docs_root = root / "docs"
    if docs_root.exists():
        for path in sorted(docs_root.rglob("*")):
            if (
                path.is_file()
                and path.suffix.lower() in MARKDOWN_EXTENSIONS
                and "archive" not in path.relative_to(docs_root).parts
            ):
                targets.append(path)

    return targets


def collect_front_matter_targets(root: Path) -> list[Path]:
    targets: list[Path] = []
    patterns = [
        "docs/architecture/**/*.md",
        "docs/implementation-specs/**/*.md",
        "docs/archive/**/*.md",
    ]
    for pattern in patterns:
        targets.extend(sorted(root.glob(pattern)))
    return [path for path in targets if path.is_file()]


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def strip_fenced_code_blocks(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            lines.append("")
            continue
        lines.append("" if in_fence else line)
    return "\n".join(lines)


def parse_front_matter(text: str) -> dict[str, str] | None:
    if not text.startswith("---\n"):
        return None

    closing = text.find("\n---\n", 4)
    if closing == -1:
        return None

    body = text[4:closing]
    mapping: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        mapping[key.strip()] = value.strip().strip("'\"")
    return mapping


def validate_front_matter_mapping(mapping: dict[str, str], rel_path: str) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_FRONT_MATTER_KEYS:
        if not mapping.get(key):
            errors.append(f"{rel_path}: front matter missing '{key}'")

    for key, allowed in ALLOWED_FRONT_MATTER.items():
        value = mapping.get(key)
        if value and value not in allowed:
            errors.append(
                f"{rel_path}: front matter '{key}' has invalid value '{value}'"
            )

    last_verified = mapping.get("last_verified")
    if last_verified and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", last_verified):
        errors.append(
            f"{rel_path}: front matter 'last_verified' must use YYYY-MM-DD"
        )

    return errors


def validate_front_matter(paths: list[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        rel_path = relative(path, root)
        mapping = parse_front_matter(load_text(path))
        if mapping is None:
            errors.append(f"{rel_path}: missing required YAML front matter")
            continue
        errors.extend(validate_front_matter_mapping(mapping, rel_path))
    return errors


def markdown_links(text: str) -> list[str]:
    return [
        link
        for link in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", text)
        if not link.startswith(("http://", "https://", "mailto:", "#"))
    ]


def image_links(text: str) -> list[str]:
    markdown_images = re.findall(r"!\[[^\]]*]\(([^)]+)\)", text)
    html_images = re.findall(r'<img\s+[^>]*src="([^"]+)"', text)
    return [
        link
        for link in [*markdown_images, *html_images]
        if not link.startswith(("http://", "https://", "data:"))
    ]


def normalize_target(raw_target: str) -> str:
    target = raw_target.strip().strip("<>")
    target = target.split("#", 1)[0]
    target = target.split("?", 1)[0]
    return target


def resolve_local_target(base: Path, target: str) -> Path:
    return (base / target).resolve()


def validate_relative_links(paths: list[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        rel_path = relative(path, root)
        text = strip_fenced_code_blocks(load_text(path))

        for raw in markdown_links(text):
            target = normalize_target(raw)
            if not target:
                continue
            resolved = resolve_local_target(path.parent, target)
            if not resolved.exists():
                errors.append(f"{rel_path}: broken markdown link '{raw}'")

        for raw in image_links(text):
            target = normalize_target(raw)
            if not target:
                continue
            resolved = resolve_local_target(path.parent, target)
            if not resolved.exists():
                errors.append(f"{rel_path}: missing image '{raw}'")
            elif resolved.stat().st_size == 0:
                errors.append(f"{rel_path}: empty image '{raw}'")

    return errors


def validate_stale_paths(paths: list[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        rel_path = relative(path, root)
        text = load_text(path)
        for old, new in MOVED_PATHS.items():
            if old in text:
                errors.append(
                    f"{rel_path}: stale moved-path reference '{old}' -> '{new}'"
                )
    return errors


def validate_mermaid_fences(paths: list[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for path in paths:
        rel_path = relative(path, root)
        in_mermaid = False
        for line in load_text(path).splitlines():
            stripped = line.strip()
            if stripped == "```mermaid":
                in_mermaid = True
                continue
            if in_mermaid and stripped == "```":
                in_mermaid = False
        if in_mermaid:
            errors.append(f"{rel_path}: unclosed mermaid fence")
    return errors


def main() -> int:
    current_markdown = collect_markdown_targets(ROOT)
    front_matter_markdown = collect_front_matter_targets(ROOT)

    errors = [
        *validate_relative_links(current_markdown, root=ROOT),
        *validate_front_matter(front_matter_markdown, root=ROOT),
        *validate_stale_paths(current_markdown, root=ROOT),
        *validate_mermaid_fences(current_markdown, root=ROOT),
    ]

    if errors:
        return fail(sorted(set(errors)))

    print("Documentation validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
