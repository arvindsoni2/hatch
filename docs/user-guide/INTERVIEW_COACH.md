# Interview Coach

Interview Coach (`/coach`) is where you practise interviews, keep your stories, and, if you turn it on, prepare for a real scheduled interview.

## Practice Sessions

- Choose the role, interview type and difficulty, then answer each question.
- Answers are evaluated against the evidence in your master CV and stories.
- Hatch may ask a follow-up when an answer leaves something out.
- When the session ends you get a report; opening it again shows the same snapshot.

Typed answers work in every setup. Spoken answers use the conversational mode, which is off by default. Scores, levels, reports and privacy rules for sessions are described in [Interview Prep](INTERVIEW_PREP.md).

## Stories

**Coach → Stories** keeps reusable STAR stories. Sessions can draw on them, and Hatch records which stories you used.

## Interview Readiness Loop (opt-in)

These features help you get ready for a real interview round. Each one is off by default:

| Feature | What you get | Setting |
|---|---|---|
| Patterns, focus areas and plans | Weak spots that repeat across sessions, up to three focus areas, and a time-boxed practice plan | `HATCH_COACH_READINESS_ENABLED` |
| Interview brief | A one-page brief before a scheduled round, built from your own evidence | `HATCH_COACH_BRIEF_ENABLED` |
| Debrief | A short debrief after the round; its notes feed the next brief | `HATCH_COACH_DEBRIEF_ENABLED` |
| Story coverage | Which competencies your stories cover well, thinly or not at all | `HATCH_COACH_STORY_COVERAGE_ENABLED` |

To turn one on, set it to `true` in the backend environment and restart the backend. Turning it off again stops new processing; what was already created stays readable and deletable.

Anything a model suggests is a proposal: you accept or edit it. With AI mode set to None, every part still shows useful content built by rules.

## What Hatch Remembers

**Settings → Privacy → What Hatch remembers** lists what the readiness loop has derived from your sessions, stories and debriefs, and lets you delete it by kind or all at once. Deleting a source, such as a session or a story, also deletes what was derived from it. This page works even when the readiness features are off.
