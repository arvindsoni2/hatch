---
name: form-mapping
description: Produce a paste-map showing which profile fields to copy into which form fields for the target ATS (Greenhouse, Lever, Ashby, Workday)
when_to_use: When assembling the application package, to help the candidate fill the external application form quickly and accurately
wraps: null
---

# Form Mapping

Produce a "what to paste where" map for the external application form so the candidate can fill it in seconds rather than minutes.

## Process

1. Detect the ATS from the job URL or the `job.ats_hint` field (if present).
2. Load the matching ATS YAML from `resources/` (greenhouse, lever, ashby, workday).
3. Resolve each form field from the candidate's profile and documents:
   - Personal details (name, email, phone, LinkedIn, location) from `profile.yaml`.
   - CV upload → path from the application package.
   - Cover letter upload → path from the application package.
   - Screening question answers → from the `screening-answers` skill output.
4. Return a list of `{form_field, value, source}` triples for display on the Application-ready card.

## Constraints

- This skill produces a paste-map for the **human** to use — it does not automate form submission.
- If the ATS cannot be detected, return an empty map with an `ats_unknown` flag rather than guessing.
- If a source profile/document value is missing, leave `value` empty and attach
  a `missing_field` flag; never infer personal, eligibility, or compensation data.
- Field labels are ATS-specific; use only the labels defined in the resource YAML.

## Resources

- `resources/greenhouse.yaml` — Greenhouse field schema and paste-map template.
- `resources/lever.yaml` — Lever field schema and paste-map template.
- `resources/ashby.yaml` — Ashby field schema and paste-map template.
- `resources/workday.yaml` — Workday field schema and paste-map template.
