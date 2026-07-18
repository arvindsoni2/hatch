# Run representative local-model selection

Use this procedure to compare Hatch's five local writing models against the controlled eight-case suite. The staged run records a model decision without writing fixture content, generated documents, or raw responses to Git.

## Keep the benchmark boundary stable

Run the benchmark from a clean, committed branch. A resumed run rejects a changed source commit, suite hash, profile hash, or database hash.
The database protection hash covers both the main SQLite database and its
write-ahead log when present. A run refuses to start when either the profile or
database state cannot be recorded.

Before inference, confirm these conditions:

- All benchmark changes are committed
- The working tree is clean
- The five suite models are installed
- The `llm-primary` service and Ollama server are available
- No application workflow writes to the profile or database during the run

Do not edit model defaults or model documentation before the final decision.

## Validate the suite and services

Validate the synthetic fixture contract from the `backend` directory:

```bash
cd backend
python -m benchmarks validate-suite \
  --suite benchmarks/fixtures/representative_suite.json
```

The command must report eight cases and five models.

Check the two local runtime endpoints:

```bash
curl --fail http://127.0.0.1:8080/health
curl --fail http://127.0.0.1:11434/api/tags
ollama ps
```

`ollama ps` lists loaded models. Ollama's current command for unloading one model is `ollama stop model_name`.

## Run Stage A and Stage B

Start the staged run from the `backend` directory:

```bash
python -m benchmarks staged-run \
  --suite benchmarks/fixtures/representative_suite.json \
  --output-root ../data/benchmarks/results
```

The command prints a pair-count and duration projection before each stage. Copy the run ID from the final status line.

Stage A runs 15 pairs. Stage B runs no more than 36 pairs and includes the baseline comparator. If no challenger qualifies, the run records `retain_baseline` and does not start Stage C.

Detailed artifacts remain under `data/benchmarks/results/run_id_here/`. The aggregate `report.md` and `selection.json` files in that directory contain the reviewable evidence.

## Restart services before each Stage C run

A qualifying challenger places the run in `awaiting_restart_evidence`. Restart both relevant runtimes before each official run.

From the repository root, restart the baseline `llama.cpp` service:

```bash
docker compose restart llm-primary
curl --fail http://127.0.0.1:8080/health
```

If the challenger uses Ollama, unload its exact catalogue model and check the server:

```bash
ollama ps
ollama stop model_name_here
curl --fail http://127.0.0.1:11434/api/tags
```

Read `challenger_model_id` from the ignored progress file. Map that identifier to its `model` value in `representative_suite.json`.

Create a new evidence file after the restart. Use the two Stage C model IDs in the endpoint records:

```json
{
  "timestamp": "2026-07-17T12:34:56+00:00",
  "source_commit": "source_commit_sha_here",
  "endpoints": [
    {"model_id": "qwen35-4b", "healthy": true},
    {"model_id": "challenger_model_id_here", "healthy": true}
  ]
}
```

Use `git rev-parse HEAD` for `source_commit`. Use a timezone-qualified timestamp created after the restart. Store the file under the ignored staged run directory.

Resume official run 1 from the `backend` directory:

```bash
python -m benchmarks staged-run \
  --suite benchmarks/fixtures/representative_suite.json \
  --output-root ../data/benchmarks/results \
  --resume run_id_here \
  --restart-evidence ../data/benchmarks/results/run_id_here/restart-1.json
```

After official run 1 completes, repeat the service restart. Create `restart-2.json` with a later timestamp, then run the same resume command with the second evidence file. The coordinator rejects reused or stale restart evidence.

Each official run schedules 80 pairs: two models, eight cases, and five shared seeds.

## Resume an interrupted stage

Resume with the same run ID:

```bash
python -m benchmarks staged-run \
  --suite benchmarks/fixtures/representative_suite.json \
  --output-root ../data/benchmarks/results \
  --resume run_id_here
```

The coordinator skips completed case units. It retries interrupted or timed-out repetitions within the current unit and preserves existing pair artifacts.

Do not change commits between the initial command and a resume command. Start a new staged run when the benchmark code or suite changes.

## Record a deliberate deferral

If you stop after Stage B, record the decision explicitly:

```bash
python -m benchmarks staged-run \
  --suite benchmarks/fixtures/representative_suite.json \
  --output-root ../data/benchmarks/results \
  --resume run_id_here \
  --defer-stage-c
```

This records `benchmark_deferred`. A deferred or incomplete run cannot authorize a default-model change.

## Review the decision

Review these ignored artifacts:

- `staged_manifest.json`: suite, source commit, and fixed stage plan
- `staged_progress.json`: completed units, projections, protected-state evidence, and restart records
- `selection.json`: final locked-threshold decision
- `report.md`: aggregate reliability, safety, quality, operations, and qualification results

The coordinator returns a nonzero status for interrupted execution or protected-state changes. An evidence-backed `retain_baseline` returns zero.

## Apply the model-change boundary

Apply the recorded decision exactly:

- `retain_baseline`: do not change model defaults, the README, the model catalogue, migration notes, or rollback instructions
- `benchmark_deferred`: do not change those files
- `change_default`: confirm both official runs pass every locked threshold before changing those files

For `change_default`, update the default and its documentation in a separate commit. Include the README, canonical model catalogue, migration notes, and rollback procedure, then rerun their contract tests.

## Publish privacy-safe evidence

Create the checked-in decision record from aggregate values only. Include case identifiers, counts, rates, scores, threshold outcomes, run ID, and source commit.

Exclude these values:

- Fixture prose and personal fields
- Generated CV or cover-letter text
- Raw model responses
- Secrets and environment values
- Database or profile contents
- Machine-specific absolute paths
