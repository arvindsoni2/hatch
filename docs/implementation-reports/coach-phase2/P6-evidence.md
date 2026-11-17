# P6 evidence — source events, fencing, cascade, Explain (HA)

Task / spec sections / ACs: P6, Wave 1, high-assurance. Spec §5.1–§5.3, §7.7, §7.8, §8.6, §9.1, §9.3, §10, §10.1, §11, §12, §15; AC19, AC21, AC23, AC29, AC30, AC36 and the content canary.

Baseline SHA → head SHA: `64f4313` (P5 merged) / RED `491a6df` → head recorded in the commit that adds this report.

OpenCode version · model ID · effort · switches (with reasons): opencode (harness-reported model ID `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`, owner-confirmed 2026-11-05). Effort is not exposed to the agent. No model switch.

Claude Code RED commit: `491a6df7065c7bac1327ffbff7b88b9fbdd429c2` (`test(coach): RED contract for P6`), approval docs `1f562ee` / `7e056ff`. Untouched-tests check:

```text
$ git diff --name-only 491a6df..HEAD -- \
    backend/tests/test_services/test_source_events.py \
    backend/tests/integration/test_coach_readiness_cascade.py \
    backend/tests/integration/test_coach_readiness_fencing.py \
    backend/tests/integration/coach_readiness_support.py \
    backend/tests/security/test_coach_readiness_canary.py \
    backend/tests/architecture/test_coach_readiness_imports.py
(no output)
```

Files changed (one line each: responsibility):

- `backend/app/services/source_events.py` — neutral registry, `notify`, `register_listener`, `unregister_listener`, `SourceChange`.
- `backend/app/repositories/conversational_session_repository.py` — exactly three `notify` calls: transcript delete (`edited`), new hard-deletion claim (`deactivated`), finalise (`deleted`), before media removal and before the method's own data change.
- `backend/app/repositories/story_repository.py` — `notify` in `update` and `soft_delete`.
- `backend/app/services/question_bank.py` — `notify` in update and archive.
- `backend/app/repositories/coach_readiness_repository.py` — approved repository with `delete_derived_for_source`.
- `backend/app/services/coach_readiness/privacy.py` — `ReadinessPrivacy` listener.
- `backend/app/main.py` — register/unregister the readiness listener in the lifespan.
- `backend/app/models/coach_readiness.py`, `backend/app/models/__init__.py` — `coach_derived_text` and `coach_derived_sources`.
- `backend/alembic/versions/20261117_1323_54f861f6f61d_add_coach_derived_text_cache.py` — additive migration on `f4f4b2b410de`.
- `backend/app/services/coach_readiness/contracts.py` — `SourceRef`, `GenerationRequest`, `ValidatedOutput`, `GenerationOutcome`, `input_fingerprint`, `finalise_generation`.
- `backend/app/services/coach_readiness/grounding.py` — production grounding checks; `benchmarks/coach/phase2_checks.py` is now a re-export.
- `backend/app/services/coach_readiness/explain.py` — Explain cache, dedupe, one-repair generation, absolute deadline, fencing, AI-off handling, reasoning stripping.
- `backend/app/routers/coach_readiness.py` — tips and operations routes, including 202/200 cache/dedupe behaviour.
- `backend/app/runtime_bindings/tasks/coach_readiness.py`, `.../context/coach_readiness.py`, `.../capabilities/registry.py`, `.../context/__init__.py`, `.../tasks/__init__.py` — five TaskSpecs, reference-only context provider and local-capable capability registration.
- `frontend/src/lib/coachReadinessApi.ts`, `frontend/src/components/coach/readiness/PatternTips.tsx`, `PatternCard.tsx` — tips request, instant skeleton, `aria-live="polite"` arriving text, retry/unavailable state.
- Tests: `backend/tests/runtime/test_coach_readiness_bindings.py`, `backend/tests/test_services/test_coach_grounding.py`, `frontend/src/components/coach/readiness/__tests__/PatternTips.test.tsx`.
- `docs/implementation-reports/coach-phase2/P6-evidence.md` — this report.

RED: the fourteen protected tests failed on the RED commit exactly as recorded in `P6-red.md`: missing `app.services.source_events`, missing `app.repositories.coach_readiness_repository`, and the missing seam assertion. No test failed from a syntax or fixture error.

GREEN:

```text
$ python -m pytest -q --no-cov \
    tests/test_services/test_source_events.py \
    tests/integration/test_coach_readiness_cascade.py \
    tests/integration/test_coach_readiness_fencing.py \
    tests/security/test_coach_readiness_canary.py \
    tests/architecture/test_coach_readiness_imports.py
14 passed

$ python -m pytest -q --no-cov \
    tests/runtime/test_coach_readiness_bindings.py \
    tests/test_services/test_coach_grounding.py
7 passed

$ python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py
19 passed

$ npx vitest run
702 passed (115 files)

$ npm run type-check
exit 0

$ npm run build
exit 0

$ ruff check app/ tests/
All checks passed!

$ alembic heads
54f861f6f61d (head)

$ python scripts/check_docs.py
Documentation validation passed.

$ git diff --check
exit 0
```

Full backend suite and regression counts:

```text
$ python -m pytest -q --no-cov tests
4100 passed, 2 skipped, 9 failed in 1092.42s
# One failure was real: test_conversational_contract_versions_have_single_production_authority
# rejected hard-coded report contract strings in the new readiness files. Fixed by using
# REPORT_CONTRACT; the test now passes. The remaining 8 are the known CUDA/sm_61 environment
# failures in tests/test_tools/test_embedder.py and test_semantic_scorer.py.
```

Migration (disposable DB):

```text
$ DATABASE_URL=sqlite+aiosqlite:////tmp/opencode/p6-migration.db
$ alembic stamp f4f4b2b410de  -> stamp_revision -> f4f4b2b410de
$ alembic upgrade head         -> upgrade f4f4b2b410de -> 54f861f6f61d
$ alembic downgrade -1        -> downgrade 54f861f6f61d -> f4f4b2b410de
$ alembic upgrade head         -> upgrade f4f4b2b410de -> 54f861f6f61d
```

Model calls in tests: fake / live: only the local model server is faked at its HTTP `/chat/completions` boundary; no live model call.

Privacy / deletion / fencing evidence: the cascade tests drive the real domain methods and reload durable rows; the listener deletes cached text for every change kind and never commits. Fencing checks session `deletion_state`/`activity_version`, story `is_active`, Question Bank archive state, round cancellation and the recomputed fingerprint; failures write nothing. The canary test confirms prompt text reaches the model request and appears in no other table, log at DEBUG, telemetry item or `llm_factory` trace. AI mode None is enforced in the tips route.

Not run / known limits:

- Live local-model generation is P3's bench/owner step; P6 tests use the HTTP fake.
- The runtime TaskSpecs/context provider/capability registration are added for §10 wiring; the tips route's transport is the direct httpx path explicitly allowed by the approved P6 interfaces.
- P3 bench/acceptance-smoke owner items remain open.

Ready for review: yes.
