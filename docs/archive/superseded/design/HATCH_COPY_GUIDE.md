---
title: Hatch Copy Guide
document_type: historical
status: historical
implementation_status: not-applicable
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!WARNING]
> This document is retained for historical context. It does not describe the current Hatch implementation on `main`.

# Hatch Copy Guide

## Voice

Hatch is clear, direct, supportive, and calm. It explains evidence and the next action without hype.

- Use plain language.
- Lead with the user's outcome.
- Be specific about state and time.
- Use active voice.
- Keep sentences short.
- Never imply an application was submitted when Hatch only prepared documents.
- Never claim an agent is running without confirmed runtime state.

## Preferred Terms

| Avoid | Prefer |
|---|---|
| Agent output | Agent progress |
| Needs you | Ready for you |
| Packages | CV packs |
| Packages ready | CV packs ready |
| Review & approve | Review CV packs |
| Stream | Pipeline |
| Tracker | Applications |
| Prep | Interview Prep |
| Generate All | Generate CV pack |
| Open generated documents | Review CV pack |
| Extraction failed | We could not read this job page reliably |

Visible labels may change while existing routes remain unchanged.

## Headings and Summaries

Use sentence case and make the page's purpose explicit.

Good:

- “Today’s command centre”
- “3 CV packs are ready to review”
- “2 follow-ups are overdue”
- “Scout last checked 6 boards at 07:05”

Avoid:

- “Agent Dashboard”
- “Needs you”
- “Pipeline Execution Results”
- “Your application workspace at a glance”

## Buttons

Button copy describes the immediate outcome.

Good:

- “Review CV packs”
- “Open application”
- “Mark as applied”
- “Prepare for interview”
- “Retry import”
- “Paste job description”
- “Save to applications”

Avoid:

- “Continue” when the next step is not obvious.
- “Submit” when the action can be named.
- “Yes” or “OK” for consequential actions.
- “Review & approve” when review and approval are separate decisions.

Use one primary action per view or decision region.

## Agent Status

Describe confirmed state, evidence, and time where useful.

| State | Pattern | Example |
|---|---|---|
| Running | Agent + current action | “Scout is checking job boards” |
| Complete | Agent + result + time | “Scorer ranked 12 roles at 06:18” |
| Idle | Last known result | “Tailor last prepared a CV pack yesterday” |
| Delayed | State + expectation | “Scoring is taking longer than usual” |
| Failed | Problem + recovery | “Scout could not reach one board. Retry the search.” |

Avoid “Agents active” or “Agents running” as a default capability label.

## Empty States

An empty state answers:

1. What is empty?
2. Is that expected?
3. What can the user do next?

Examples:

- “No CV packs need review. New packs will appear here after Tailor finishes.”
- “No roles match these filters. Clear a filter or widen your search.”
- “Scout has not run yet. Run Scout to find roles from your saved preferences.”
- “You have no upcoming interviews. Add an interview from Applications when one is confirmed.”

Do not use celebratory copy when the absence may be ambiguous.

## Loading and Delays

Name the work and set expectations only when known.

Good:

- “Preparing your CV and cover letter…”
- “Importing job details…”
- “This is taking longer than usual. You can leave this page and return later.”

Avoid:

- “Please wait.”
- “Working…”
- Exact time promises that the system cannot guarantee.

## Errors and Recovery

Use:

`What happened. What the user can do next.`

Good:

- “We could not read this job page reliably. Paste the job description and continue.”
- “Your CV pack was not generated. Check the job description, then try again.”
- “Hatch could not connect to the local AI service. Start the service and retry the connection.”
- “This job is already in Applications. Open the existing job or update its details.”

Avoid:

- “Extraction failed.”
- “Unknown error.”
- “Something went wrong” without a recovery action.
- Raw status codes, stack traces, provider names, or internal service terms.

## Success and Confirmation

State exactly what changed.

Good:

- “Job saved to Applications.”
- “Marked as applied.”
- “CV pack ready to review.”
- “Follow-up scheduled for 12 July.”

Avoid:

- “Success!”
- “All done!” when follow-up work remains.
- “On its way” unless an external submission or message was actually sent.

## Review and Tailoring

Keep preparation separate from submission.

Preferred:

- “CV pack”
- “Review changes”
- “Regenerate CV”
- “Regenerate cover letter”
- “Use this version”
- “Ready to apply”

Do not say “application sent” until the application has been explicitly marked or confirmed as submitted.

## Applications

Use status labels that describe the user's real-world progress:

- Saved
- CV pack ready
- Ready to apply
- Applied
- Interview
- Offer
- Rejected
- Withdrawn

Use “overdue” only when a due date exists. Use exact dates for future actions when practical.

## Scores

- “Match” describes role fit.
- “CV ATS” describes the generated CV's ATS assessment.
- Never merge or substitute these values.
- Include the unit or percent sign.
- Do not describe a score as a guarantee.

Examples:

- “Match 86%”
- “CV ATS 88%”
- “Strong skills match; location preference differs.”

## Tone Boundaries

Avoid:

- Hype: “Amazing match!”
- Blame: “You forgot to follow up.”
- False certainty: “You will get an interview.”
- Surveillance language: “Hatch is watching your applications.”
- Internal architecture: “The Tailor agent emitted an artifact.”
- Excess punctuation, emoji, or exclamation marks.

Prefer:

- “This role matches 8 of your 10 required skills.”
- “A follow-up was due yesterday.”
- “Tailor prepared a CV pack for your review.”

## Content QA

- Can the user tell what happened?
- Can the user tell what to do next?
- Is the state confirmed by available data?
- Does the copy distinguish preparation from submission?
- Are Match and CV ATS labelled separately?
- Is the same concept named consistently across navigation, cards, and dialogs?
- Does the message avoid internal implementation detail?
- Does an error include recovery?
- Does the text remain clear without colour or icon context?
