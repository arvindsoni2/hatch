---
name: cover-letter
description: Generate a tailored cover letter that connects the candidate's proof points to the role's key requirements
when_to_use: After CV tailoring is complete and a shortlisted job needs a cover letter for the application package
wraps: CoverLetterGenerator, DocxCLBuilder
---

# Cover Letter Generation

Produce a concise, targeted cover letter (250–350 words) that:

- Opens with the strongest proof-point match for this role.
- Addresses the employer's two or three most pressing stated requirements directly.
- Closes with a clear, confident call to action.

## Process

1. Pull the top three requirement matches from the JD analysis.
2. Map each to a concrete proof point from the candidate's history.
3. Tone variant is **auto-selected** by `select_tone_variant(jd_analysis)`:
   - **A (formal)**: construction, finance, government, energy, defence, banking, legal, infrastructure
   - **B (conversational)**: technology, tech, startup, creative, media, gaming, SaaS
   - Defaults to **A** when sector is absent or unrecognised.
4. Trim to ≤ 350 words; never pad below 250.

## Company Name Handling

- Use the company name **verbatim** from `jd_analysis.company_context.company_name` in paragraph 1.
- If the company name is empty or null, open with role + sector — **never** use `[Company Name]`, `the Company`, or any placeholder.
- Never fabricate a company name. If genuinely unknown, omit the name and reference the role and sector instead.

## Constraints

- Never repeat the CV verbatim — the letter should add context, not summarise.
- Do not include salary expectations or availability unless the JD explicitly asks.
- UK spelling and grammar conventions unless locale is overridden.
- **NEVER emit bracketed placeholders** — `[Company Name]`, `[Role]`, `[Year]`, or any `[...]` token.
- **NEVER use LaTeX markup** — write £ for GBP, never `\textsterling` or `$...$` notation.

## Resources

- `resources/tone_examples.md` — reference examples for variant A (formal) and variant B (conversational) openings and closings.
