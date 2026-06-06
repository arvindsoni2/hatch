---
name: cv-tailoring
description: Tailor a master CV to a specific job description using keyword matching and narrative fit
when_to_use: When a shortlisted job needs a tailored CV generated before entering the Review gate
wraps: CVTailor, JDAnalyser, DocxCVBuilder
---

# CV Tailoring

Produce a CV that is both ATS-parseable and compelling to a human reader for this specific role.

## Process

1. **Analyse the JD** — extract must-have requirements, ATS keywords (technical, methodologies, domain, certifications), seniority signals, and role title.
2. **Select the best summary variant** — choose the master CV summary whose keyword overlap with the JD is highest.
3. **Reorder and reframe experience bullets** — surface the most relevant proof points first; use the JD's own language where truthful.
4. **ATS keyword check** — run `extract_jd_keywords.py` against the JD to get a target list, then verify each keyword appears at least once in the output.
5. **Fabrication guard** — never invent experience or skills. If a must-have keyword is absent from the master CV, flag it as a gap rather than inserting it.

## Constraints

- Output must not exceed 2 pages.
- Keyword density: aim for ≥ 80% of the ATS keyword list to appear naturally in the body text.
- Preserve the candidate's authentic voice; do not rewrite into generic corporate language.

## Scripts

- `scripts/extract_jd_keywords.py` — deterministic keyword extractor from JD text; use this before and after tailoring to measure coverage.

## Resources

- `resources/cv_patterns.yaml` — per-role patterns and bullet templates used to guide rewriting without fabrication.
