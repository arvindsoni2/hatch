# P0 evidence — handoff check, gate report, Phase 2 bench suite

Task / spec sections / ACs: P0 rework after two reviews. Spec §7.6, §9.1, §9.4, §10. No ACs are implemented by P0. The first review's findings 1–10 and the re-review's findings 1–6 are addressed below.

Baseline SHA → head SHA: `b7274a6` (plan baseline) → `412008b` (handoff pack) → `870696c` (main merged into the branch as `1a6f02e`) → head recorded in the commit that adds this report.

OpenCode version · model ID · effort · switches (with reasons): opencode `2.2.5`; model ID `opencode-go/deepseek-v4.1-flash`; effort not exposed to the agent; no model switch in this run. The original P0 run used `deepseek-v4.1-flash-free`, which plan §1.2 excludes; it does not count toward P1 qualification. `/models` and the Go privacy table are still owner checks.

Claude Code RED commit (HA only) and untouched-tests check output: not applicable to P0 (non-HA). The implementer wrote the new tests first; no test from `PN-red.md` exists for P0.

Files changed (one line each: responsibility):

- `backend/benchmarks/coach/phase2_checks.py` — spec §7.6/§10 limits, Tier T budgets, real citation/number/name grounding checks, input-size helper.
- `backend/benchmarks/coach/phase2_adapter.py` — new bench-only execution path: versioned prompt per task, streaming loopback llama-server call, per-case tier deadline and output cap, metrics.
- `backend/benchmarks/coach/contracts.py` — `ScenarioResult.metrics` carries latency, TTFT, tokens/s, peak RSS and token counts.
- `backend/benchmarks/coach/runner.py` — selects the Phase 2 adapter for the `phase2` profile and copies its metrics into the result.
- `backend/benchmarks/coach/fixtures/phase2_v1/models.json` — Tier T context 2,048 (llama-triage 4,096 × 2 slots) and Tier S 16,384.
- `backend/benchmarks/coach/fixtures/phase2_v1/*.json` — 48 cases stay 15/15/10/8 and 16 tuning / 32 holdout; at least a third per task is sized within 20 % of its input maximum.
- `backend/tests/benchmarks/coach/test_phase2_suite.py` — resized-suite, token-budget, grounding, loopback and fake-server bench tests.
- `docs/implementation-reports/coach-phase2/P0-entry.md` — this report.

File deviations from the plan's P0 list (finding 9):

- `backend/benchmarks/coach/suite_loader.py` (previous P0 commit) — needed to load a `phase2` fixture kind, its input-key allowlist and tuning/holdout split.
- `backend/benchmarks/coach/cli.py` (previous P0 commit) — needed to offer `--profile phase2`.
- `backend/benchmarks/coach/phase2_adapter.py` — the plan lets the implementer choose the bench-only path file. `production_adapter.py` was **not** edited.

RED: test names and failure output (short):

The new tests were written before the implementation. First run:

```text
$ python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py
ERROR collecting tests/benchmarks/coach/test_phase2_suite.py
E   ModuleNotFoundError: No module named 'benchmarks.coach.phase2_adapter'
1 error in 0.26s
```

After the module and checks existed, the new suite reached GREEN. The old stub `grounding_violations` returned `()` and could not satisfy the new unknown-id, absent-number, absent-name and over-limit assertions; the fixtures also failed the new 20 % size and §7.6/§10 limit assertions until resized.

Re-review round (new tests written first):

```text
$ python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py
FAILED test_grounding_allowlists_star_and_rubric_words
FAILED test_explain_excerpts_are_capped_at_two
FAILED test_phase2_bench_path_marks_bad_json_invalid
FAILED test_phase2_bench_path_marks_ungrounded_output_invalid
FAILED test_phase2_bench_path_times_out_instead_of_hanging
FAILED test_phase2_bench_path_runs_all_four_stages_against_fake_server
6 failed, 13 passed in 3.26s
```

The failure modes were: `STAR`/`Situation` were flagged as names; three excerpts were accepted; the fake server rejected requests without `stream_options.include_usage`; and the negative-path cases had no server mode yet.

GREEN: commands, exit codes, counts:

```text
cd backend
python -m pytest -q --no-cov tests/benchmarks/coach/test_phase2_suite.py   # exit 0, 19 passed
python -m pytest -q --no-cov tests/benchmarks/coach                       # exit 0, 154 passed
/tmp/p0-py312/bin/python -m pytest -q --no-cov tests/benchmarks/coach     # exit 0, 154 passed (Python 3.12.16)
ruff check benchmarks/coach/phase2_checks.py benchmarks/coach/phase2_adapter.py \
  benchmarks/coach/contracts.py benchmarks/coach/runner.py \
  tests/benchmarks/coach/test_phase2_suite.py                              # exit 0, All checks passed
python -m benchmarks.coach validate --suite benchmarks/coach/fixtures/phase2_v1
  # exit 0, "Valid Coach suite coach_phase2_v1: 48 scenarios, 2 models"
git diff --check                                                           # exit 0
```

Docs checks (working tree vs clean export). The owner's untracked
`docs/implementation-specs/active/hatch-coach-phase2-handoff/` makes the
working-tree `python scripts/check_docs.py` fail with front-matter errors for
that folder only. It was left exactly where it was. The tracked files were
checked on a clean export:

```text
$ D=$(mktemp -d) && git ls-files -z | tar --null -T - -c | tar -x -C "$D" \
    && (cd "$D" && python scripts/check_docs.py && python scripts/check_readme_contract.py); rm -rf "$D"
Documentation validation passed.
README contract passed.
```

Working-tree `python scripts/check_docs.py` output begins with
`docs/implementation-specs/active/hatch-coach-phase2-handoff/HANDOFF.md: missing
required YAML front matter`; no other path is reported.

Python 3.12 environment: `uv venv --python 3.12 /tmp/p0-py312`, then `uv pip install -r requirements.txt -r requirements-test.txt`; `python --version` is 3.12.16. System Python is 3.14.8. Node is v22.23.2.

Regressions run: the full `tests/benchmarks/coach` suite on Python 3.14 (154 passed) and Python 3.12 (154 passed), including profiles, suite loader, CLI, runner, adapters, scoring and the new fake-server bench run and failure cases.

Model calls in tests: fake / live (live only in P3 bench): fake only. The bench path was exercised against an in-process loopback SSE server on `127.0.0.1`; no live model call was made.

Metrics capture (finding 1): `phase2_adapter.py` records per attempt:

- `latency_ms` — wall clock from before the HTTP request to the last streamed chunk; includes queue time on `llm-primary`.
- `ttft_ms` — time to the first streamed content delta.
- `tokens_per_second` — llama.cpp `timings.predicted_per_second` when present, else completion tokens divided by the time from first token to last.
- `peak_rss_bytes` — `/proc/<HATCH_BENCH_SERVER_PID>/status` `VmHWM`, the kernel's peak resident set for the llama-server process. The fake-server test sets the variable to the test process. When unset or unreadable the value is `null`.
- `prompt_tokens`, `completion_tokens`, `output_chars`, `deadline_seconds`.
- `schema_valid` and `grounding_violations` — the P3 gate inputs; a failed schema or any grounding violation also raises the blocking `coach_stage_failed` gate on the attempt.

Per-tier enforcement (finding 6): the adapter applies `TIER_MAX_DEADLINE_SECONDS` (T 60 s, S 180 s, L 300 s) per case and `TASK_OUTPUT_CAPS` (T 512, S 600, L 600) to the request. The now-unused 300 s profile bound remains only as an outer runner guard.

P3 notes — peak memory and token usage:

- P3 sets `HATCH_BENCH_SERVER_PID` to the **host PID** of the Docker llama-server: `docker inspect -f '{{.State.Pid}}' <container>`.
- `VmHWM` is cumulative since that process started. P3 must start a fresh llama-server per candidate, run the suite, and read the maximum; do not reuse a server across candidates.
- `phase2_adapter.py` sends `"stream_options": {"include_usage": true}` so llama-server fills `prompt_tokens` and `completion_tokens`. The word-count fallback is used only when usage is absent.
- The fake server rejects requests without `stream_options.include_usage`, so the full-run and failure tests enforce it.

Review finding mapping:

1. Bench-only path — `phase2_adapter.py`, selected by `runner.py` for `phase2`; all four stages run in `test_phase2_bench_path_runs_all_four_stages_against_fake_server`.
2. Real grounding — `grounding_violations` checks unknown story ids/fingerprints, numbers absent from the supplied source, capitalised names absent from the source, and schema/word/character limits; positive and negative tests cover each.
3. Fixture size — 5/15 explain, 5/15 brief, 4/10 debrief and 3/8 competency cases are at least 80 % of `INPUT_MAX_CHARS`; enforced by `test_a_third_of_each_task_is_near_its_input_maximum`.
4. Schema limits — debrief notes 2,500 chars; debrief output ≤ 12 × 120 chars; explain ≤ 40 words per tip and ≤ 120 total; competency input ≤ 4,500 chars (Tier T 1,200-token input budget, 4 chars/token); enforced by the schema tests and `test_tier_t_cases_fit_the_context_budget`.
5. Context sizes — Tier T 2,048, Tier S 16,384 in `models.json`.
6. Per-tier deadlines — adapter timeout per task tier (see above) and constants test.
7. Model — this rework ran on `opencode-go/deepseek-v4.1-flash`; the free-tier original run does not count toward P1 qualification.
8. Loopback test — now checks both `phase2_v1/models.json` entries and that the loader rejects a copied suite whose endpoint is remote.
9. Deviations — listed above.
10. Python versions — 3.12.16 and 3.14.8, both 154 passed.

Re-review findings (cbbeed4):

1. Process — the owner's untracked `docs/implementation-specs/active/hatch-coach-phase2-handoff/` was **not** moved, renamed or deleted. Docs checks were run on a clean export of tracked files (command and output above).
2. Grounding names — `_ALLOWED_NAME_WORDS` covers the seven dimensions and STAR words (Situation, Task, Action, Result, STAR), and `grounding_violations(..., instruction_text=...)` also allows every word in the task's own bench instruction and the supplied rubric text (the rubric is already part of the explain source). `test_grounding_allowlists_star_and_rubric_words` uses the review's exact example; the existing `Northwind` negative test still fails.
3. Bench failure paths — three fake-server tests run through `run_benchmark` with the `phase2` profile: bad JSON (`schema_valid` false + blocking `coach_stage_failed`), ungrounded output (`schema_valid` true, `grounding_violations` > 0 + blocking gate), and a stalled server with patched `TIER_MAX_DEADLINE_SECONDS` (case ends as `timeout`, no hang).
4. Token usage — `stream_options.include_usage` is sent; the fake server rejects requests without it.
5. Peak memory — documented under "P3 notes" above, including `docker inspect` for the host PID and the fresh-server/VmHWM maximum rule.
6. Explain excerpts — capped at 2 in `ExplainInput`; `INPUT_MAX_CHARS["explain"]` is 2,000, the five long cases are ~1,800 characters, and `test_explain_excerpts_are_capped_at_two` covers the cap.

Privacy / deletion / fencing evidence: all 48 cases are synthetic. The fixture test walks every JSON string for personal email, phone shapes, private markers, absolute paths and `data/` references; the loader's privacy scan also runs. No `data/`, `.env`, CV, transcript or recording was read. No privacy, deletion or fencing code changed. The bench stores model output as the validated task payload only; invalid output is not stored raw.

Migration: heads before/after, downgrade/upgrade result: before `a4b5c6d7e8f9 (head)`; after `a4b5c6d7e8f9 (head)`. No migration in P0; no downgrade/upgrade run.

Gate report:

| Gate | Result |
|---|---|
| Merged HEAD | `1a6f02e` (`main` `870696c` merged; no rebase) |
| Migration head | `a4b5c6d7e8f9` |
| Python / Node | 3.12.16 and 3.14.8 / v22.23.2 |
| R7 / R8 / R9 | No branches, merged commits or evidence reports; paused per D6 |
| Handoff pack installed | Yes, including the revised 2 Nov spec, plan and agent files |
| `check_docs.py` / `check_readme_contract.py` | exit 0 / exit 0 on a clean export of tracked files; working-tree `check_docs` fails only on the owner's untracked staging folder, which was left in place |
| Wave 0 verdict | **GO** |
| Wave 1 verdict | Pending the §3.2 readiness check, recorded at P4 |

Not run / known limits:

- No live model call and no P3 bench run. The fake server proves wiring, metrics and validation only.
- `peak_rss_bytes` is `null` unless `HATCH_BENCH_SERVER_PID` names the llama-server process; P3 must set it and report the PID source.
- The Phase 2 profile uses a single model id per run; tier caps come from the task, not from the model spec.
- `/models` and the Go privacy table were not verifiable from this session.
- Only `tests/benchmarks/coach` was run; the full backend and frontend suites belong to the P4/P6/P9 gates.
- The owner's untracked `docs/implementation-specs/active/hatch-coach-phase2-handoff/` remains in the working tree, untouched; it is why the working-tree docs check fails and why the clean-export check is recorded instead.

Ready for review: yes — all re-review findings are addressed, the fake-server success and failure paths pass on both Python versions, and no protected or untracked file was moved or changed.
