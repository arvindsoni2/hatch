# P7 evidence — pre-interview brief (M5, S3)

## Carried from P6 review

All three carry-over findings were fixed first in commit `b9a76a4` (`fix(coach): guard tips polling and local-only explain routing`).

- **StrictMode polling:** `PatternCard` now sets `mounted.current = true` on effect mount and false on cleanup. A `<React.StrictMode>` Vitest requests tips (202 then cached 200), sees the operation succeed and renders the tip.
- **Local-only explain routing:** `_route_base_url` uses the profile's base URL only when `llm.provider == "llamacpp"`; otherwise it returns the local `ROUTE_URLS` default. Test: an `openrouter` profile with `base_url=https://openrouter.ai/api/v1` resolves to the local default.
- **Operations cap:** eviction skips `queued`/`running` entries. Test fills 200 terminal entries plus one running entry and asserts the running operation survives.

Carry-over gates (real output):

```text
$ python -m pytest -q --no-cov <P6 focused + explain tests + bench suite>
45 passed in 12.28s

$ npx vitest run src/components/coach/readiness src/app/coach/readiness
30 passed (30)

$ npm run type-check
exit 0

$ git diff --check
exit 0
```

## P7

Task / spec sections / ACs: P7, Wave 1. Spec §7.5, §8.4, §10, §13.1–§13.4, §14; AC12–AC15, AC28, AC32, AC33.

Baseline SHA → head SHA: `f58e14d` (P6 merge) → carry-over `b9a76a4` → head recorded in the P7 commit.

Model: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`, owner-confirmed 2026-11-05. No switch.

Files changed:

- `backend/app/services/coach_readiness/brief.py` — deterministic 7-section skeleton, enhancement fingerprint/state, enhancement via the same local route resolution and `finalise_generation` with story and round source refs.
- `backend/app/services/coach_readiness/scheduler.py` — 30-minute upcoming-round enhancement job.
- `backend/app/services/coach_readiness/next_actions.py` — brief actions for Today.
- `backend/app/models/coach_readiness.py`, `models/__init__.py` — `coach_interview_briefs`.
- `backend/alembic/versions/20261123_1115_6e209652647a_add_coach_interview_briefs.py` — additive migration.
- `backend/app/routers/coach_readiness.py` — GET brief and POST brief/tips.
- `backend/app/config.py` — `HATCH_COACH_BRIEF_ENABLED=False`.
- `backend/app/main.py` — scheduler job registration.
- `frontend/src/components/coach/readiness/InterviewBrief.tsx`, `BriefSection.tsx` — 7 sections, print action, no Refresh button, print stylesheet.
- `frontend/src/components/InterviewTimeline.tsx` — Brief/Debrief tabs per round.
- `frontend/src/lib/coachReadinessApi.ts` — typed brief client.
- Tests: `backend/tests/test_services/test_coach_brief.py`, `backend/tests/integration/test_coach_brief_lifecycle.py`, `frontend/src/components/coach/readiness/__tests__/InterviewBrief.test.tsx`.

GREEN:

```text
$ python -m pytest -q --no-cov tests/test_services/test_coach_brief.py \
    tests/integration/test_coach_brief_lifecycle.py \
    tests/runtime/test_coach_readiness_bindings.py tests/test_services/test_source_events.py
24 passed in 6.06s

$ python -m pytest -q --no-cov tests/runtime \
    tests/integration/test_coach_report_privacy_flow.py \
    tests/integration/test_coach_deletion_recovery.py \
    tests/integration/test_coach_audio_restart_recovery.py \
    tests/test_services/test_coach_privacy.py tests/test_routers/test_question_bank.py \
    tests/test_services/test_coach_brief.py tests/integration/test_coach_brief_lifecycle.py
554 passed, 1 skipped in 195.41s

$ npx vitest run src/components/coach/readiness/__tests__/InterviewBrief.test.tsx
2 passed

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app/ tests/
All checks passed!

$ alembic heads
6e209652647a (head)

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0
```

Migration round trip on a disposable DB: stamp `54f861f6f61d` → upgrade `6e209652647a` → downgrade `54f861f6f61d` → upgrade `6e209652647a`.

Sections/limits: likely questions ≤ 5, stories ≤ 3, watch-outs ≤ 2, gaps ≤ 2, ask-them ≤ 3; the skeleton is rebuilt on every read and archive follows `scheduled_at + duration`, `completed` and `cancelled`.

Model calls in tests: none live. Brief enhancement uses the same local-only route resolution as Explain and `finalise_generation`; no DB transaction is held during the HTTP call.

Not run / known limits:

- The Playwright A4 print test was not added/run in this environment; the print stylesheet is in `InterviewBrief.tsx`.
- The P3 bench/acceptance-smoke owner items remain open.

Ready for review: yes.
