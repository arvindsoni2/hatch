---
title: Hatch v5 (rev 3 — FINAL) — llama.cpp Runtime, Dead-Weight Removal & Codebase Cleanup
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

# Hatch v5 (rev 3 — FINAL) — llama.cpp Runtime, Dead-Weight Removal & Codebase Cleanup

**Date:** 2026-06-11
**Supersedes:** rev 2 (`2026-06-11-v5-rev2-llamacpp-deadweight-refactor.md`) and its addenda A1–A14.
This is the clean consolidated handoff: every Q&A resolution is folded into the body. No addendum
cross-referencing required. Where rev 2's body and addenda conflicted, this document is authoritative.
**Repo:** https://github.com/arvindsoni2/hatch — audit baseline `4d208ab`; frontend dispositions
re-verified at HEAD (working tree has diverged from the baseline; see C1 rule).
**Status:** Ready for implementation.

**Scope (maintainer-confirmed):**
- ✅ Ollama → llama.cpp (llama-server) as the default local runtime (Ollama retained as a provider)
- ✅ Dead-weight removal (evidence table below)
- ✅ Codebase cleanup/refactor (rename, budgets, pragmas, CI gates)
- ❌ NOT in scope: embedding stack changes (MiniLM + sentence-transformers stays), FAISS/any vector
  index, LangChain/LangGraph changes, Next.js 15 / transformers 5.x / langgraph 1.x migrations,
  anything touching the assisted-apply boundary or `test_no_autonomous_submission`.

---

## Dead-code audit — evidence

Method: AST import-graph over `backend/app`, vulture ≥80%, requirements-vs-imports diff, frontend
reference counts; cross-verified by the implementer at HEAD. False positives kept (with reasons):
aiosqlite (DB URL string), `langchain-*` providers (dynamic via `init_chat_model`), lxml (bs4
parser string), alembic (CLI). **Not duplicates, do not merge:** `agent_orchestrator` (lifecycle)
vs `supervisor` (LangGraph routing). All 15 scrapers registered and profile-selectable — no pruning.

| # | Item | Evidence | Verdict |
|---|---|---|---|
| D1 | `chromadb` dep + `CHROMA_PERSIST_DIR` (config.py:72) + compose env + string entry in `skills/cv-tailoring/scripts/extract_jd_keywords.py:50` (list entry, not an import) | instantiated nowhere | remove |
| D2 | Autonomous-apply residue: `models/auto_apply.py`, `repositories/auto_apply_repository.py` (never imported → nothing ever writes the table), `models/__init__.py:7`, `database.py:77`, `digest_service.py:15,44,164–185`, `templates/emails/daily_digest.html:136–142`, `templates/candidate_profile.json:82` `auto_apply_config` block | digest section permanently empty | remove all (incl. the JSON block, for consistency) |
| D3 | `services/recruiter_finder.py` | zero consumers | remove |
| D4 | `skills/wrappers.py` + `test_skill_wrappers.py` | unreachable by skill loader (loads only `<skill>/scripts/<file>` via `spec_from_file_location`, loader line 126); the test imports dead code only | remove both |
| D5 | `schemas/job_score.py` (`JobScoreRead`) | never imported; uniquely exposes `id`, `job_id`, `scored_at` | **wire, don't delete** (R4) |
| D6 | 10 orphaned frontend components (zero refs, re-confirmed at HEAD): `JobTable.tsx`, `components/EmptyState.tsx`, `CVPreview.tsx`, `CLPreview.tsx`, `StatsBar.tsx`, `ActivityTimeline.tsx`, `GhostBadge.tsx`, `AdvancedFilterPanel.tsx`, `coach/RecordingControls.tsx`, `coach/StoryMatchBadge.tsx` | v4 shell-rework orphans | remove, except `GhostBadge` (rewire, C1) and note `ui/EmptyState.tsx` is the live canonical empty-state (C1) |
| D7 | vulture: unused callback vars `llm_factory.py:124,127`; `claude_client.py` `max_concurrent`; `tts_service.py:10` `struct` import | 90–100% confidence | fix — **`max_tokens` is NOT removed in DW-3** (9 callers pass it; R2 owns it) |
| D8 | Dev deps in runtime requirements: pytest, pytest-asyncio, pytest-cov, pytest-httpx, ruff, factory-boy | shipped in prod image | split to `requirements-dev.txt` |

**Key runtime fact discovered during audit (shapes R2):** `complete()`/`complete_json()` accept
`max_tokens` but never use it — `llm.ainvoke(messages)` runs unbounded. Every `max_tokens` literal
in the codebase is decorative; current behaviour is model-default/`num_ctx`-bounded generation.

---

# Part 1 — llama.cpp runtime

Two resident llama-server containers (triage + primary): the scorer interleaves triage→score calls
per batch, the worst case for swap/router-mode serving (full unload→reload per switch). Embedder
stays in-process (out of scope).

### RT-1 — Compose services + model fetch

- [ ] Pin the image: `docker pull ghcr.io/ggml-org/llama.cpp:server` (rolling) → read build from
      `--version` → smoke-test it loads `Qwen3.5-0.8B Q8_0` and answers one prompt
      (`scripts/verify_runtime.sh`) → pin `server-bNNNN` in compose, recording build+date in a
      comment (replacing the stale "2024 builds predate Qwen3" comment — GHCR publishes per-build
      tags continuously; any build ≥ March 2026 supports Qwen3.5).
- [ ] `llm-primary` — `:8080`, **Qwen3.5-4B-Instruct GGUF Q4_K_M**,
      `--ctx-size 16384 --parallel 1`. (16384 is sized for today's monolithic CV-generation call,
      `CV_GENERATE=(10240,6000)`; drops to 8192 in the same PR that lands the grounding spec's
      G-4 per-section tailoring and deletes `CV_GENERATE`.)
- [ ] `llm-triage` — `:8081`, **Qwen3.5-0.8B GGUF Q8_0**, `--ctx-size 4096 --parallel 2`
      (llama-server divides context across slots → 2048/slot ≥ TRIAGE 1536+256).
- [ ] `--threads` **omitted** (llama.cpp self-detects; the flag requires an integer — `auto`
      crashes). Tuning ships as a commented `docker-compose.override.yml.example` with an explicit
      `--threads N`; document that CPU-limited containers (`cpus:`/cpuset) should set it to match
      the limit since auto-detection sees host cores.
- [ ] Shared `./data/models:/models:ro`; healthchecks on `/health`; backend
      `depends_on: condition: service_healthy`.
- [ ] `scripts/fetch_models.sh`: idempotent download of the two GGUFs, pinned HF repo + revision +
      sha256 (prefer official `Qwen/Qwen3.5-*-GGUF`; community quants only if an official one is
      missing). Never deletes user files — the existing `./models/Qwen3-14B-Q4_K_M.gguf` stays on
      disk; release notes mark it superseded (Qwen3.5-9B ≥ quality at ~40% less RAM, ~2× speed)
      and reclaiming the 9GB is the user's call. Offline path: drop GGUFs into `data/models/`.
- [ ] Docs: model tiers — default 4B Q4_K_M; **Qwen3.5-9B** (not 8B — no 8B exists in this
      family) documented for 16GB+ with honest ~3–5 tok/s CPU expectation.
- [ ] Tests: compose config validates; fetch idempotent; smoke script gates the pin.

**Commit:** `feat(runtime): compose-managed llama-server services for triage and primary`

### RT-2 — Profile schema, factory wiring, onboarding

- [ ] `schemas/profile.py` llm: add `triage_base_url: str = ""`; default provider flips to
      `"llamacpp"` with `base_url="http://llm-primary:8080/v1"`,
      `triage_base_url="http://llm-triage:8081/v1"`. Existing `provider: ollama` profiles work
      unchanged (regression suite).
- [ ] **Triage routing (Option A — no `_build_model` signature change):**
      ```python
      def get_triage_model() -> BaseChatModel:
          profile = load_profile()
          effective = profile.llm.model_copy(
              update={"base_url": profile.llm.triage_base_url or profile.llm.base_url}
          )
          return _build_model(profile.llm.triage_model, effective)
      ```
      (Without this, `_build_model` reads `llm_cfg.base_url` at line 329 and triage would route
      to the primary port.)
- [ ] Fold-onto-primary fallback: `triage_base_url == base_url` (or empty) runs both roles on one
      server — the documented 8GB-constrained option.
- [ ] **Startup context assertion:** on backend startup, read `/props` from each configured
      llama-server; compare slot context (`ctx / parallel`) against the largest
      `prompt_budget + max_output` routed to that server. Mismatch → `logger.warning` with the
      numbers + `degraded: context_budget_exceeds_slot` detail on `/api/health`. **Soft warning,
      never a hard failure** (a self-hosted app must not refuse to boot over a tuning mismatch;
      the risk is truncation, not corruption). Skip silently for non-llamacpp providers and
      unreachable servers.
- [ ] Onboarding `StepAIProvider`: "Built-in local (recommended)" **pre-selected**, including
      flipping the wizard's initial state in `onboarding/page.tsx` from `google_genai` to
      `llamacpp`. Rationale: the wizard is only reachable when compose is up, and
      `depends_on: healthy` brings the LLM services with it — the zero-key default works out of
      the box; `google_genai` pre-selected would demand an API key as the first interaction.
      Guard the dev edge with a live reachability indicator (existing `/test-connection`
      pattern) and an inline "Start the bundled AI services: `docker compose up -d`" hint on
      failure. Ollama option relabelled "Ollama on this machine (advanced)".
- [ ] Frontend wiring (all three gaps):
      (a) `LLMData` interface gains `triage_base_url: string` so `saveProfile()` round-trips it;
      (b) `needsKey` becomes `llm.provider !== "ollama" && llm.provider !== "llamacpp"` (also
      apply the same exclusion at `onboarding/page.tsx:194`);
      (c) `handleProviderChange("llamacpp")` performs **no detection** and writes:
      `primary_model="qwen3.5-4b-instruct-q4_k_m"`, `triage_model="qwen3.5-0.8b-q8_0"`
      (lowercase, exactly the GGUF filenames pinned in `fetch_models.sh`; export both strings
      from one shared constants location — llama-server in single-model mode ignores the request
      `model` field, so these serve cost rows/traces/display only), plus the two service URLs
      above. The reachability indicator is the verification, not model-list discovery.
- [ ] Tests: triage model builds against `triage_base_url` (new — existing llamacpp tests cover
      build_model/get_primary_model/get_json_model only); ollama regression green; fallback path
      builds; `/props` mismatch produces warning + health detail (mocked `/props`); wizard
      pre-fill values round-trip.

**Commit:** `feat(llm): per-role llamacpp endpoints; llamacpp becomes the default local provider`

### RT-3 — Grammar-guaranteed JSON (two paths, no caller parsing changes)

- [ ] **Structured path** (scorer already uses `.with_structured_output` at
      `scorer_agent.py:108–109`): add a factory helper owning the per-provider method choice —
      `with_schema(llm, schema)` → `with_structured_output(schema, method="json_schema")` on
      llamacpp, LangChain default elsewhere. Scorer changes two lines.
- [ ] **`complete_json` path:** `get_json_model(schema: type[BaseModel] | None = None)`. With a
      schema on llamacpp, upgrade the existing `response_format: json_object`
      (llm_factory.py:428) to
      `{"type":"json_schema","json_schema":{"name":..., "schema": schema.model_json_schema(), "strict": true}}`.
      Return type unchanged (chat model emitting JSON text) → `complete_json`'s parse-and-retry
      loop untouched. `LLMClient.complete_json` gains an optional `schema=None` pass-through.
- [ ] Call-site threading is incremental: pass schemas where Pydantic models exist (JD analysis,
      tailor sections, rubric synthesiser); no caller is forced to change.
- [ ] Tests: json_schema attached when schema given, json_object when not; scorer structured path
      uses `method="json_schema"` on llamacpp; recorded-response round-trip parses first time.

**Commit:** `feat(llm): json_schema grammar enforcement on the llamacpp path`

### RT-4 — Provider-aware reasoning, timeouts, context handling

- [ ] Thinking-mode on llamacpp: Qwen3.5 GGUF via ChatOpenAI `extra_body` /
      `chat_template_kwargs: {enable_thinking: false}` (verify against the pinned build, lock
      with a test). **Must NOT touch `_maybe_add_think_token`** (llm_factory.py:261) — that
      function is the gemma4/Ollama `<|think|>` mechanism and correctly early-returns for
      non-ollama providers. Triage/scoring always non-thinking; `llm.reasoning=true` opts Coach
      rubric calls in.
- [ ] **Timeouts:** the llamacpp ChatOpenAI constructions (both `_build_model` ~line 326 and
      `get_json_model` ~line 414) currently have **no timeout**, while the Ollama path sets
      `request_timeout=300`. Add `timeout=300` to both llamacpp constructions — Qwen3.5-4B on a
      U-series CPU can take 4–8 min/call; a silent hang is worse than a clean timeout into the
      existing retry.
- [ ] Ollama-specific `num_ctx` tuning blocks become provider-aware (no-ops for llamacpp; the
      server flag governs).
- [ ] Docs: README/install rewritten around the self-contained compose; "stay on Ollama"
      migration note in release notes.
- [ ] Tests: thinking off by default on llamacpp; gemma4/ollama unchanged; timeout present on
      both llamacpp constructors.

**Commit:** `refactor(llm): provider-aware reasoning, timeouts and context handling for llamacpp`

---

# Part 2 — Dead-weight removal

### DW-1 — Remove ChromaDB (D1)
Requirement, `CHROMA_PERSIST_DIR` (config.py:72 + compose env), and the string list entry in
`extract_jd_keywords.py:50`. Grep-tripwire test: no `chromadb` import anywhere.
**Commit:** `chore(deps): remove unused ChromaDB`

### DW-2 — Remove autonomous-apply residue (D2)
All targets in the D2 row, **including** the `auto_apply_config` block in
`templates/candidate_profile.json:82` and the digest HTML section. Alembic migration drops
`application_attempts` (guard: only if empty; else log + skip with a manual note — expected empty
since nothing writes it; the two existing migrations use `op.*` style and remain runnable after
the model deletion). Confirm `test_no_autonomous_submission` untouched and green — this removal
strengthens the boundary.
**Commit:** `chore: remove dead autonomous-apply model/repository/digest residue`

### DW-3 — Dead modules + vulture (D3, D4, D7)
Delete `recruiter_finder.py`, `skills/wrappers.py` **and `test_skill_wrappers.py`** (tests dead
code only). Vulture fixes per D7 — `max_concurrent` only in `claude_client.py`; **`max_tokens`
stays** (9 callers across 9 files pass it as a keyword; removing it here breaks the backend until
R2). Verify the llm_factory callback args are not signature-bound by LangChain before deleting
(else rename to `_serialized`). Import-graph script reports zero never-imported modules after
this task (allowlist: entrypoints, alembic, `skills/*/scripts/`).
**Commit:** `chore: delete dead modules and vulture findings`

### DW-4 — Requirements split (D8)
`requirements-dev.txt` for pytest*, ruff, factory-boy; Dockerfile installs runtime only; CI
installs both; `pip check` clean.
**Commit:** `chore(deps): split dev requirements out of the runtime image`

---

# Part 3 — Frontend cleanup

### C1 — Empty states, GhostBadge, orphan removal (one coherent pass)

**HEAD rule:** all D6 reference counts are re-verified against the implementer's HEAD before any
deletion (the audit baseline is `4d208ab`; UX-5 partially landed since — `ui/EmptyState.tsx` with
`EmptyStateCause` variants now exists and is canonical).

Sequencing (gate-clean at every step; the backend item may be a separate PR landing first):

0. **Backend:** extend `ScoringInsights` with two all-time counts (single `COUNT(*)` each):
   - `total_jobs_in_db` — **`COUNT(*)` over ALL rows, no `is_active` filter.** It answers "have
     you ever scraped anything"; a user who archived all 200 jobs must NOT see "no-scrape".
   - `total_scored` — all-time `JobScore` count (same no-filter logic; avoids the 7-day-window
     bug recurring one level up).
   Frontend treats both as optional — `undefined` → generic empty state, never a guessed cause —
   so deploy order cannot break the page.
1. **Wire `ui/EmptyState` in `app/jobs/page.tsx`** (page level; the hatch shell stays
   layout-only). Exact cause table: no confirmed profile → `"no-profile"` (CTA → onboarding);
   `total_jobs_in_db === 0` → `"no-scrape"` (CTA → trigger scout); `total_scored === 0` →
   `"scraped-unscored"` (CTA → scoring status); filtered `total === 0` → `"no-results"`. **Also
   convert the `showAll` (line ~285) and `showArchived` (line ~283) inline-JSX empty blocks to
   `ui/EmptyState` with a generic cause** — cheap consistency while the file is open; do not
   invent new cause variants for them. This closes audit UX-5; mark it "done via v5 C1".
2. **Rewire `GhostBadge` into `JobCard.tsx`:** render when `job.ghost_verdict` is non-null
   (fields confirmed in `schemas/job.py:84–87` and the frontend `Job` type), verdict + score,
   tooltip from `ghost_signals`.
3. **Delete** `JobTable.tsx` (re-verified orphan at HEAD; jobs page renders `JobCard`),
   `components/EmptyState.tsx` (pre-UX-5 orphan), and the remaining D6 components.
4. Run knip locally: zero unused exports under `src/components`. `tsc --noEmit` + Vitest green.

Tests: each cause renders the right copy + CTA; counts-undefined → generic; ghost badge
present/absent per fixture; non-empty list renders cards as today.
**Commit:** `feat(ui): cause-exact empty states + ghost badge; remove v4-orphaned components`

### C2 — Orphan tripwire
`knip` (or ts-prune) in CI, baseline zero unused exports under `src/components`; failures block
merge.
**Commit:** `ci(ui): unused-export gate to prevent component orphaning`

---

# Part 4 — Refactors (behaviour-preserving)

### R1 — Rename `ClaudeClient` → `LLMClient`
Atomic rename, **no deprecation alias** (all consumers internal; an alias would be dead code in a
release dedicated to removing it). Measured scope: 39 occurrences across 13 files at HEAD
(12 after DW-3 deletes `recruiter_finder`) — grep-and-replace + tests in one commit.
**Commit:** `refactor: rename ClaudeClient to LLMClient`

### R2 — Token budgets, split into a no-op and an enforcement step

`max_tokens` is decorative today (bodies never use it), so the behaviour-preserving baseline is
**unbounded generation**, and enforcement is new behaviour. Hence:

**R2a (this release — pure no-op):** `agents/tools/context_budgets.py` with
`(prompt_budget, max_output)` per call type; replace every literal with its constant (still
passed, still ignored); land the tripwire. Constants = current literals (author intent);
`prompt_budget` mechanically `16384 − max_output` unless specified tighter:

| Constant | (prompt, output) | Call site / note |
|---|---|---|
| TRIAGE | (1536, 256) | scorer triage |
| SCORING | (3328, 768) | scorer detailed |
| CV_GENERATE | (10240, 6000) | cv_tailor.py:194 — transitional; **never** TAILORING; deleted with grounding-G-4 |
| TAILORING | (6656, 1536) | reserved for G-4 per-section calls only |
| CL_BODY | (6656, 2048) | cl_generator.py:85,102 |
| CL_SNIPPET | (2048, 512) | cl_generator.py:139 — own constant; GENERIC must not absorb a 512 call |
| JD_ANALYSIS | (3328, 1024) | jd_analyser |
| ATS | (4096, 2048) | ats_optimiser.py:68 — current literal |
| COMPANY_RESEARCH | (3072, 2048) | company_researcher.py:47 — current literal |
| CV_PARSE | (12288, 4096) | cv_parser.py:66 |
| ANSWER_EVAL | (2048, 2048) | answer_evaluator.py:73 |
| MODEL_ANSWER | (2048, 2048) | model_answer_gen.py:54 |
| QUESTION_GEN | (4096, 4096) | question_generator.py:90 |
| FEEDBACK | (4096, 4096) | feedback_generator.py:111 |
| COACH_RUBRIC | (6144, 2048) | coach rubric |
| GENERIC | (3072, 4096) | signature default — matches the existing 4096, so jd_analyser/email_generator no-arg calls see zero change at R2b |

`llm_factory.py`'s `num_ctx=16384` becomes a derived constant in the same module. A static test
asserts `CV_GENERATE` fits the shipped primary `--ctx-size` (16240 ≤ 16384). Tripwire: regex
`(max_tokens|num_ctx)\s*=\s*\d` over `backend/app/**/*.py`, allowlist exactly
`agents/tools/context_budgets.py`, tests excluded by path.

**R2b (separate commit, bench-gated):** forward `max_output` to the model
(`llm.bind(max_tokens=...)` / provider kwarg) and add `prompt_budget` truncation warnings. Gate:
bench comparing JSON-failure + truncation rates before/after; any budget observed too small is
raised **before** enforcement.

**Commits:** `refactor(llm): centralise token budgets (no-op)` · `feat(llm): enforce per-call output budgets (bench-gated)`

### R3 — SQLite pragmas + one index
`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON` (safe with
the jobs router's soft-delete; no hard DELETEs to cascade). **One net-new index:**
`Index("idx_job_postings_active_scraped", "is_active", "scraped_at")` — the hot list query
(`job_repository.py:115,161–163`) filters `is_active` and orders by `scraped_at`/`match_score`;
there is no `status` column and `sync_status` never appears in list predicates. The
`match_score` ordering path uses `nullslast()` (SQLite won't serve it from a simple composite) —
no index for it. `agent_events` and `job_scores` already indexed — untouched. **The
`EXPLAIN QUERY PLAN` test on the real `list_with_filters` query is the final authority; if the
plan disagrees with this spec, fix the index to match the plan.**
**Commit:** `perf(db): WAL, pragmas, hot-path index`

### R4 — `JobScoreRead`: additive endpoint
SC-3 per-dimension transparency is already live (`JobPostingRead` embeds all four dimensions +
reasoning/strengths/gaps; `JobCard` renders via `ScoreBadge`) — mark SC-3's UI portion done. R4 is
additive only: `GET /api/v2/scoring/{job_id}` returning raw `JobScoreRead` (404 if unscored), plus
one consumer — a "Scored <relative time>" line in the job detail (stale scores become visible).
No existing response shapes change.
**Commit:** `feat(scoring): expose score record via JobScoreRead endpoint`

### R5 — Backend dead-code gate in CI
Commit the audit's AST import-graph script as `scripts/dead_code_check.py` (allowlist:
entrypoints, alembic, `skills/*/scripts/`); run it + `vulture --min-confidence 90` in CI.
**Commit:** `ci: dead-code gates (import graph + vulture)`

---

## Execution order

1. **DW-1, DW-3, DW-4** — pure deletions first (shrink the surface)
2. **RT-1 → RT-4** — llama.cpp switch, in order; capture a before/after timing note
   (tokens/sec, score-one-job) even if the full rev-1 bench harness isn't built
3. **DW-2** — includes a migration; after the runtime settles
4. **R1, R2a, R3** — rename, budget centralisation (no-op), pragmas+index
5. **C1, R4** — frontend pass + score endpoint
6. **C2, R5** — CI gates once the baseline is clean
7. **R2b** — enforcement, bench-gated, last

## Risks

| Risk | Mitigation |
|---|---|
| llama.cpp flag/API churn on upgrade | pinned build tag; `verify_runtime.sh` smoke gate; RT-4 thinking test locks behaviour |
| A "dead" module loaded dynamically somewhere unexpected | import-graph allowlist + full suite + string-import grep before each deletion |
| `application_attempts` has rows in some deployment | migration guards on non-empty, logs + skips |
| Component removal vs unmerged branches | git-recoverable; C1 step 3 is one reviewable commit |
| 8GB machines: 16K primary ctx KV + two servers | fold-onto-primary fallback; KV shrinks when G-4 lets primary drop to 8192; `/props` warning surfaces any mismatch |
| R2b enforcement truncates an under-budgeted call | bench gate; budgets raised before enforcement, never after a production truncation |

## Deferred / follow-ups (explicitly not now)

- Today-page empty-state treatment (same pattern as C1 step 1 — follow-up).
- Primary `--ctx-size` 16384 → 8192 + delete `CV_GENERATE`: lands with grounding-spec G-4.
- Speculative decoding / draft-model experiments: bench-then-decide after RT-1.
- `sqlite-vec` only if a real k-NN feature (e.g. "similar jobs") appears.
