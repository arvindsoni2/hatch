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
3. Choose tone variant: **A (formal)** for regulated industries (finance, legal, public sector); **B (conversational)** for tech/startup/creative roles.
4. Trim to ≤ 350 words; never pad below 250.

## Constraints

- Never repeat the CV verbatim — the letter should add context, not summarise.
- Do not include salary expectations or availability unless the JD explicitly asks.
- UK spelling and grammar conventions unless locale is overridden.

## Resources

- `resources/tone_examples.md` — reference examples for variant A (formal) and variant B (conversational) openings and closings.
