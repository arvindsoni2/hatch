#!/usr/bin/env python3
"""Validate README release promises against local repository files."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def fail(message: str) -> None:
    print(f"README contract failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"{path.relative_to(ROOT)} is missing")


def local_markdown_links(markdown: str) -> list[str]:
    links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", markdown)
    return [
        link
        for link in links
        if not link.startswith(("http", "#", "mailto:"))
    ]


def local_image_links(markdown: str) -> list[str]:
    return re.findall(r'<img\s+[^>]*src="([^"]+)"', markdown)


def check_local_assets(markdown: str) -> None:
    for image in local_image_links(markdown):
      path = ROOT / image
      require(path.exists(), f"README image {image} is missing")
      require(path.stat().st_size > 0, f"README image {image} is empty")

    for link in local_markdown_links(markdown):
      target = link.split("#", 1)[0]
      require((ROOT / target).exists(), f"README link {link} does not resolve")


def check_install_branch(markdown: str) -> None:
    require(
        "raw.githubusercontent.com/arvindsoni2/hatch/main/install.sh" in markdown,
        "Linux/macOS install command must reference main/install.sh",
    )
    require(
        "raw.githubusercontent.com/arvindsoni2/hatch/main/install.ps1" in markdown,
        "Windows install command must reference main/install.ps1",
    )
    invalid = re.search(r"raw\.githubusercontent\.com/arvindsoni2/hatch/(?!main/)", markdown)
    require(invalid is None, "README install command references a non-main branch")


def check_cli_commands(markdown: str) -> None:
    cli = read(ROOT / "scripts" / "hatch_cli.py")
    command_block = re.search(r"Common host commands:\n\n```bash\n(?P<body>.*?)```", markdown, re.S)
    require(command_block is not None, "Common host commands block is missing")
    commands = re.findall(r"^hatch\s+([a-z0-9-]+)", command_block.group("body"), re.M)
    require(commands, "No hatch commands found in README command block")
    for command in commands:
        require(
            re.search(rf"['\"]{re.escape(command)}['\"]", cli) is not None,
            f"hatch {command} is named in README but not implemented in hatch_cli.py",
        )


def check_boundaries(markdown: str) -> None:
    expectations = {
        "auto-apply boundary": r"never submits applications automatically",
        "app lock boundary": r"App lock protects",
        "AI-later mode": r"AI configuration deferred",
        "DOCX source of truth": r"DOCX remains the source of truth",
    }
    for label, pattern in expectations.items():
        require(re.search(pattern, markdown, re.I) is not None, f"Missing README statement: {label}")


def check_governance_files() -> None:
    for relative in [
        "LICENSE",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "docs/OPERATIONS.md",
        "docs/RELEASE_CHECKLIST.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        ".github/pull_request_template.md",
    ]:
        require((ROOT / relative).exists(), f"{relative} is missing")


def main() -> int:
    markdown = read(README)
    check_local_assets(markdown)
    check_install_branch(markdown)
    check_cli_commands(markdown)
    check_boundaries(markdown)
    check_governance_files()
    print("README contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
