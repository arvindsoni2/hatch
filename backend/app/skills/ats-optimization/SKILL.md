---
name: ats-optimization
description: Score a CV against JD keywords and provide concrete improvement suggestions to pass ATS filters
when_to_use: After CV tailoring, before committing the document to the application package, to verify keyword coverage
wraps: ATSOptimiser
---

# ATS Optimisation

Ensure the tailored CV will pass algorithmic screening before a human sees it.

## Process

1. **Deterministic keyword scan** — run `scripts/ats_lint.py` against the CV text with the JD keyword list; compute raw coverage score.
2. **Semantic analysis** — use Claude to assess whether keywords appear in meaningful context (not just keyword-stuffed).
3. **Format warnings** — flag structural issues that confuse parsers: tables, text boxes, headers in unusual fonts, missing section labels.
4. **Improvement suggestions** — produce an ordered list of specific changes (add keyword X to bullet Y in role Z).

## Score interpretation

| Score | Action |
|---|---|
| ≥ 0.80 | Proceed to application package |
| 0.60–0.79 | Apply top 3 suggestions, re-score |
| < 0.60 | Return to CV tailoring |

## Keyword Grounding Rules

- `missing_critical` must only list keywords that appear in the JD's **must-have requirements** AND are genuinely absent from the CV. Do not flag "nice-to-have" keywords as critical.
- `improvement_suggestions` must reference **real master-CV content** — every suggestion of the form "add X to section Y" must be grounded in evidence already in the candidate's background. Never suggest inventing experience.
- When a must-have keyword is absent from the master CV, flag it in `missing_critical` and note it as a genuine skill gap — do not suggest adding it.

## Scripts

- `scripts/ats_lint.py` — deterministic keyword coverage scorer; `ats_lint(cv_text, keywords) -> float`; no LLM, instant, always available.

## Constraints

- Never recommend adding keywords that are absent from the candidate's real experience.
- Treat the supplied evidence IDs as the only source of candidate facts and
  preserve every numeric token exactly.
- When evidence is missing, report a gap; do not manufacture a suggested claim.
- Format warnings take priority over keyword suggestions when a parser failure would hide all content.
- Improvement suggestions are ordered by impact: format issues > must-have gaps > coverage boosts.
