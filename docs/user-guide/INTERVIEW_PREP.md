# Interview Prep

Interview Prep supports role-specific preparation and reusable practice material.

## User Actions

- create or resume a prep session
- review likely questions
- save answers to the Question Bank
- practice or export calendar-linked prep

## Automatic Behavior

- gathers role and company context
- generates likely questions and guidance when AI capability is available
- links prep work back to the application lifecycle

## Legacy scores, conversational levels, and reports

- Legacy sessions continue to show their existing numeric report.
- Conversational sessions show named levels such as **Developing** or **Interview ready**; they do not show numeric conversational scores or confidence judgements.
- If evaluation is unavailable or invalid, Interview Prep keeps the recording and transcript, shows no numeric score, and lets you submit another attempt. Missing scores are never displayed as `0/10` or `5/10`.
- Ending a session waits until accepted answer evaluations have finished. Once complete, the report is a fixed snapshot; opening it again does not regenerate it.
- If the narrative model is unavailable, the report uses deterministic fallback feedback and labels it as such. A session with no completed evaluations shows “No score available”.
- Technical drills are optional. Invalid or unavailable generated drills are omitted without blocking the session.

## Conversational privacy

Conversational audio defaults to `delete_after_processing`. From the interview
screen you can delete an answer transcript or request hard deletion of the
interview. Hard deletion is irreversible; a short content-free receipt is kept
for reconciliation and expires after the configured 30-day default. JSON and
Markdown exports are snapshot-consistent and omit raw audio and filesystem
paths. The report page includes a browser **Print** action.

Conversational creation is controlled by
`HATCH_COACH_CONVERSATIONAL_ENABLED=false` by default. Existing sessions remain
readable and deletable if the flag is later disabled.

The existing `categories` and `interviewer_persona` configuration fields remain compatible but are not fully enforced or exposed by the launcher. Their broader product behaviour is deferred to a dedicated Coach configuration contract.
