# P0 evidence — handoff check, gate report, Phase 2 bench suite

Task / spec sections / ACs: P0. Spec §3 (gates and repository facts), §9.4 (bench protocol, suite counts and split). No ACs are implemented by P0.

Baseline SHA → head SHA: `b7274a6` (plan baseline) → `412008b` branch base (handoff pack) → head recorded in the commit that adds this report.

OpenCode version · model ID · effort · switches (with reasons): opencode `2.2.5`; provider `opencode`; model `deepseek-v4.1-flash-free`; effort not exposed to the agent; no model switch. The plan expects `opencode-go/deepseek-v4.1-flash`; this session is not on the Go plan and the agent cannot run `/models` or read the Go privacy table. The owner approved proceeding on the current model and recording the mismatch here. `/models` and the Go privacy table must be confirmed by the owner before the P1 qualification record.

Claude Code RED commit (HA only) and untouched-tests check output: not applicable to P0 (non-HA). RED was produced by the implementer against the pre-change harness; see below.

Files changed (one line each: responsibility):

- `backend/benchmarks/coach/contracts.py` — add the four Phase 2 stage names and the `phase2` profile name.
- `backend/benchmarks/coach/profiles.py` — add the bounded `phase2` profile (one repetition, 300 s call/model, 18,000 s run, no ranking).
- `backend/benchmarks/coach/runner.py` — accept `phase2` in `RunRequest`.
- `backend/benchmarks/coach/cli.py` — expose `phase2` on `run`.
- `backend/benchmarks/coach/suite_loader.py` — accept `fixture_kind: phase2`, require a tuning/holdout split, allow the four Phase 2 input shapes, expose fixture kind and split on the loaded suite.
- `backend/benchmarks/coach/phase2_checks.py` — typed input/output contracts for the four tasks, tier maxima, and the grounding stub that P6 replaces with `grounding.py`.
- `backend/benchmarks/coach/fixtures/phase2_v1/` — manifest, two loopback model specs and 48 synthetic cases (15 explain, 15 brief-enhance, 10 debrief-extract, 8 competency-extract; 16 tuning / 32 holdout).
- `backend/tests/benchmarks/coach/test_phase2_suite.py` — the named P0 tests plus output-limit checks.
- `docs/implementation-reports/coach-phase2/P0-entry.md` — this report.

RED: test names and failure output (short):

`python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py` with the harness changes stashed:

```text
FAILED test_suite_manifest_loads_48_cases_with_split
FAILED test_every_case_validates_against_its_task_schema
FAILED test_phase2_profile_schedules_every_case
SuiteValidationError: invalid Coach suite manifest: ... fixture_kind Input should be 'legacy' or 'conversational' ... split Extra inputs are not permitted
3 failed, 3 passed
```

The other three tests passed before the change because they cover existing behaviour (loopback rejection, local-only fixture scan, output limits).

GREEN: commands, exit codes, counts:

```text
cd backend
python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py   # exit 0, 6 passed
python -m pytest -q --no-cov tests/benchmarks/coach                       # exit 0, 141 passed
ruff check benchmarks/coach/... tests/benchmarks/coach/test_phase2_suite.py  # exit 0, All checks passed
python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/phase2_v1  # exit 0, 48 scenarios, 2 models
```

Regressions run: full `tests/benchmarks/coach` (141 passed), which includes profiles, suite loader, CLI, runner, adapters and scoring.

Model calls in tests: fake / live (live only in P3 bench): none. P0 makes no model calls.

Privacy / deletion / fencing evidence: all 48 cases are synthetic. The named fixture test walks every JSON string and rejects personal email, phone shapes, private markers, absolute paths and `data/` references; the loader's existing privacy scan also runs on the suite. No `data/`, `.env`, CV, transcript or recording was read. No privacy, deletion or fencing code changed.

Migration: heads before/after, downgrade/upgrade result: before `a4b5c6d7e8f9 (head)`; after `a4b5c6d7e8f9 (head)`. No migration in P0; no downgrade/upgrade run.

Gate report:

| Gate | Result |
|---|---|
| HEAD recorded | branch base `412008b` (handoff pack on `main`); implementation head in the commit |
| Migration head | `a4b5c6d7e8f9` |
| Python / Node | 3.14.8 / v22.23.2 (system Python, not the spec's 3.12; bench tests pass) |
| R7 / R8 / R9 | No branches, merged commits or evidence reports exist; paused per D6 |
| Handoff pack installed | Yes: `AGENTS.md`, `CLAUDE.md`, `opencode.json`, `.claude/commands/`, spec, plan, screen designs, diagrams |
| `python scripts/check_docs.py` | exit 0 (after removing superseded draft copies and installing the pack) |
| `python scripts/check_readme_contract.py` | exit 0 |
| Wave 0 verdict | **GO** |
| Wave 1 verdict | Pending the §3.2 readiness check, recorded at P4 |

Not run / known limits:

- The Phase 2 profile validates and schedules all 48 cases, but the production adapter has no `_execute_explain`, `_execute_brief_enhance`, `_execute_debrief_extract` or `_execute_competency_extract` handlers. P3's live bench cannot run until the P6 TaskSpecs/adapter exist (or P3 adds a bench-only adapter). This is a plan-order/interface mismatch: P3 precedes P6 but the bench needs an execution path. Reported for the reviewer/owner; not redesigned in P0.
- Latency, TTFT, tokens/s and peak-RSS capture are not wired into the runner for Phase 2. The existing adapters report tokens/s; `phase2_checks.py` exposes schema and grounding checks only. Wiring follows the execution path above.
- The profile uses the Tier L maximum (300 s) as its call bound. Per-tier maxima live in `phase2_checks.TIER_MAX_DEADLINE_SECONDS` and are not enforced per case yet.
- No holdout bench was run; P3 is owner-run on the reference laptop with the pinned llama.cpp build.
- `/models` and the Go privacy table were not verifiable from this session.
- Five unrelated untracked documents remain in the working tree (the 26 Sep readiness review and four completed-specification files: three Markdown, one PDF). They were not part of the pack and were left untouched; they do not affect the doc gate.

Ready for review: yes — suite, profile and checks are green; execution-path wiring is the known P3/P6 dependency above.
