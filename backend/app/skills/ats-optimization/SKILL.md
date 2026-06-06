---
name: ats-optimization
description: Score a CV against JD keywords and provide concrete improvement suggestions to pass ATS filters
when_to_use: After CV tailoring, before committing the document to the application package, to verify keyword coverage
wraps: ATSOptimiser
---

# ATS Optimisation

Ensure the tailored CV will pass algorithmic screening before a human sees it.

## Process

1. **Deterministic keyword scan** — run `ats_lint.py` against the CV text with the JD keyword list; compute raw coverage score.
2. **Semantic analysis** — use Claude to assess whether keywords appear in meaningful context (not just keyword-stuffed).
3. **Format warnings** — flag structural issues that confuse parsers: tables, text boxes, headers in unusual fonts, missing section labels.
4. **Improvement suggestions** — produce an ordered list of specific changes (add keyword X to bullet Y in role Z).

## Score interpretation

| Score | Action |
|---|---|
| ≥ 0.80 | Proceed to application package |
| 0.60–0.79 | Apply top 3 suggestions, re-score |
| < 0.60 | Return to CV tailoring |

## Scripts

- `scripts/ats_lint.py` — deterministic keyword coverage scorer; `ats_lint(cv_text, keywords) -> float`; no LLM, instant, always available.

## Constraints

- Never recommend adding keywords that are absent from the candidate's real experience.
- Format warnings take priority over keyword suggestions when a parser failure would hide all content.
