"""Tripwire tests for context_budgets.py (R2a).

1. CV_GENERATE fits inside the primary server's --ctx-size.
2. No raw max_tokens/num_ctx integer literals in app code (excluding context_budgets.py
   itself and test files).
"""
from __future__ import annotations

import re
from pathlib import Path


_APP_ROOT = Path(__file__).parent.parent.parent / "app"


def test_cv_generate_fits_primary_ctx() -> None:
    from app.agents.tools.context_budgets import CV_GENERATE, PRIMARY_CTX

    total = CV_GENERATE.prompt + CV_GENERATE.max_output
    assert total <= PRIMARY_CTX, (
        f"CV_GENERATE ({CV_GENERATE.prompt}+{CV_GENERATE.max_output}={total}) "
        f"exceeds PRIMARY_CTX ({PRIMARY_CTX})"
    )


def test_no_literal_token_budgets_in_app_code() -> None:
    """Regex tripwire: no (max_tokens|num_ctx)=<digits> outside context_budgets.py."""
    pattern = re.compile(r"(max_tokens|num_ctx)\s*=\s*\d")
    violations: list[str] = []

    for py_file in _APP_ROOT.rglob("*.py"):
        if py_file.name == "context_budgets.py":
            continue
        text = py_file.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                violations.append(f"{py_file.relative_to(_APP_ROOT.parent.parent)}:{lineno}: {line.strip()}")

    assert not violations, (
        "Raw token-budget literals found — use constants from context_budgets.py:\n"
        + "\n".join(violations)
    )
