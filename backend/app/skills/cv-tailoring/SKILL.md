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
4. **ATS keyword check** — run `scripts/extract_jd_keywords.py` against the JD to get a target list, then verify each keyword appears at least once in the output.
5. **Fabrication guard** — never invent experience or skills. If a must-have keyword is absent from the master CV, flag it as a gap rather than inserting it.

## Constraints

- Output must not exceed 2 pages.
- Keyword density: aim for ≥ 80% of the ATS keyword list to appear naturally in the body text.
- Preserve the candidate's authentic voice; do not rewrite into generic corporate language.
- **NEVER emit bracketed placeholders** — `[Company Name]`, `[Role]`, `[Year]`, or any `[...]` token. If a value is unknown, omit the clause entirely.
- **NEVER use LaTeX markup** — write £ for GBP, never `\textsterling` or `$...$` notation.

## Skill Category Labels

Use these exact display names for skill groups in the output. Do not invent new categories; only add a category the candidate genuinely has skills for:

| Display name | Typical content |
|---|---|
| `Cloud & Infrastructure` | AWS, Azure, GCP, Kubernetes, Terraform, networking |
| `Data & AI` | Python, SQL, Spark, dbt, ML frameworks, LLMs |
| `Architecture & Design` | Enterprise architecture, system design, API design |
| `Delivery & Leadership` | Agile, SAFe, PMO, stakeholder management, team leadership |
| `Security & Compliance` | ISO 27001, GDPR, pen-testing, SIEM, SOC |

The `category` field in the JSON output maps directly to these display names. An empty or missing label produces a bare `:` in the generated document — always populate it.

## Sector-Transfer Guidance

When the candidate's background is in a different sector than the target role (e.g. energy/aviation vs construction/finance):

- **Do NOT claim sector-specific experience they do not have.**
- **Do surface transferable proof points**: regulated-industry delivery, large-programme governance, data-platform consolidation, stakeholder management at scale.
- **Frame in the target sector's language**: use the sector's vocabulary (e.g. "project controls" for construction, "front-office" for finance) where it accurately describes what the candidate did.
- Lead the summary with the strongest cross-sector credential (e.g. "Delivered £500K savings across 2,000-engineer field mobility programme" works in any capital-projects sector).

## Scripts

- `scripts/extract_jd_keywords.py` — deterministic keyword extractor from JD text; use this before and after tailoring to measure coverage.

## Resources

- `resources/cv_patterns.yaml` — per-role patterns and bullet templates used to guide rewriting without fabrication.
