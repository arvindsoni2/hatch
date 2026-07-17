---
name: interview-prep
description: Generate weighted interview questions and STAR-structured model answers tailored to the role and company
when_to_use: After an application is marked as interview-scheduled and the candidate needs to prepare
wraps: QuestionGeneratorService, ModelAnswerGen, StoryMatcher
---

# Interview Preparation

Generate a targeted question set and STAR-structured model answers so the candidate walks in prepared, not just informed.

## Process

1. **Weight the question categories** — Technical (30%), Behavioural (25%), Situational (15%), Domain (10%), Culture (10%), Commercial (10%).
2. **Pull company context** — use company-research output to tailor questions to likely themes and recent developments.
3. **Map proof points** — for each behavioural/situational question, match the strongest story from the candidate's history using the STAR framework.
4. **Generate model answers** — produce concise STAR answers (Situation → Task → Action → Result) that are specific, metric-grounded, and honest.

## STAR framework

See `resources/star_framework.md` for the full framework, examples, and common mistakes.

## Constraints

- Prioritise questions that target the role's must-have requirements.
- Map each question to a stable supplied job-requirement ID and remove
  semantically duplicate questions.
- Model answers must use real proof points — never invent outcomes or metrics.
- Preserve candidate numbers exactly and return an empty answer when approved
  evidence cannot support a truthful STAR story.
- Flag when a question category has no good story match; suggest the closest available.
- Keep each model answer under 200 words (spoken delivery target: ~90 seconds).
