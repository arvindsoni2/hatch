---
name: screening-answers
description: Generate clipboard-ready answers to application knockout questions (work auth, notice period, rate, relocation) from profile.yaml
when_to_use: When assembling the application package for the Application-ready card, to provide copy-paste answers to standard screening questions
wraps: null
---

# Screening Answers

Produce pre-filled, copy-paste-ready answers to the standard knockout questions that appear on most application forms.

## Process

1. Load `profile.yaml` fields: `locale`, `candidate.availability`, `compensation`, `apply` block.
2. Load `resources/knockout_patterns.yaml` for the locale-specific legal field labels and expected answer formats.
3. For each pattern, resolve the answer from the profile:
   - **Work authorisation** — derive from `locale` (e.g. "British Citizen — no sponsorship required" for `locale: uk`).
   - **Notice period** — from `candidate.availability.notice_period` (default: "immediately available").
   - **Expected rate/salary** — from `compensation.min_rate`–`compensation.max_rate` in `compensation.currency`.
   - **Relocation** — from `search.locations[0].remote_preference`.
4. Return a list of `{label, answer}` pairs for display on the Application-ready card.

## Constraints

- Answers must derive entirely from explicit `profile.yaml` fields — never
  infer work authorisation, sponsorship, availability, relocation, notice
  period, or compensation from locale or another field.
- If a required field is missing from the profile, return `{label, answer: ""}` with a `missing_field` flag.
- Rate answers should respect the locale's convention (daily for UK contract, annual for permanent/AE/IN).

## Resources

- `resources/knockout_patterns.yaml` — per-locale knockout question labels and answer templates.
