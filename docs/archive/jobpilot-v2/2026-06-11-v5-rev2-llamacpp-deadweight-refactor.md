---
title: Hatch v5 (rev 2) — llama.cpp Runtime, Dead-Weight Removal & Codebase Cleanup
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

# Hatch v5 (rev 2) — llama.cpp Runtime, Dead-Weight Removal & Codebase Cleanup

**Date:** 2026-06-11 (rev 2 — supersedes the scope of `2026-06-11-v5-optimisation-llamacpp-embeddings.md`)
**Repo:** https://github.com/arvindsoni2/hatch (commit `4d208ab`)
**Status:** Ready for Claude Code implementation
**Scope decisions (maintainer-confirmed):**
- ✅ **IN:** Ollama → llama.cpp (llama-server) as the default local runtime
- ✅ **IN:** Dead-weight removal (ChromaDB and everything found by the audit below)
- ✅ **IN:** Codebase cleanup/refactor — unused modules, functions, components; module hygiene
- ❌ **OUT (rev 1 items dropped):** bge-small embedding swap, embeddings-as-a-service container,
  torch removal. `sentence-transformers` + `all-MiniLM-L6-v2` in-process stays as-is.
  FAISS remains rejected (no k-NN access pattern exists). Consequence accepted: backend image
  keeps the ~400MB torch payload.

---

## Dead-code audit — evidence (commit `4d208ab`)

Method: AST import-graph over `backend/app` (modules never imported), vulture ≥80% confidence,
requirements-vs-imports diff, and per-component reference counts over `frontend/src`. Verified
manually to exclude false positives (aiosqlite via DB URL string, `langchain-*` providers loaded
dynamically by `init_chat_model`, `lxml` as a bs4 parser string, alembic via CLI — all **kept**).

| # | Item | Evidence | Verdict |
|---|---|---|---|
| D1 | `chromadb` dependency + `CHROMA_PERSIST_DIR` (config.py:72) + compose env | instantiated **nowhere** in app code | remove |
| D2 | Autonomous-apply residue: `models/auto_apply.py` (`ApplicationAttempt`), `repositories/auto_apply_repository.py`, digest "auto_apply_results" section (`digest_service.py:15,44,169,185`), `models/__init__.py:7`, `database.py:77`, DB table | repository never imported → **nothing ever writes** the table; digest section permanently empty | remove (aligns with the no-autonomous-submission principle) |
| D3 | `services/recruiter_finder.py` (6KB) | zero consumers | remove |
| D4 | `skills/wrappers.py` | zero consumers | remove |
| D5 | `schemas/job_score.py` (`JobScoreRead`) | never imported — but it is exactly the per-dimension schema the scorer-transparency work (SC-3, 2026-06-11 grounding spec) needs | **wire, don't delete** (see R4) |
| D6 | 10 orphaned frontend components (0 references each): `JobTable.tsx`, `EmptyState.tsx`, `CVPreview.tsx`, `CLPreview.tsx`, `StatsBar.tsx`, `ActivityTimeline.tsx`, `GhostBadge.tsx`, `AdvancedFilterPanel.tsx`, `coach/RecordingControls.tsx`, `coach/StoryMatchBadge.tsx` | v4 `HatchNavShell` rework orphans (matches the known v4 orphaned-UX history) | per-component decide: remove or rewire (see C2) |
| D7 | vulture: unused vars `llm_factory.py:124,127` (`serialized`, `prompts`), `claude_client.py:44,52,71` (`max_concurrent`, `max_tokens`), unused import `tts_service.py:10` (`struct`) | 90–100% confidence | fix |
| D8 | Dev-only deps in runtime requirements: `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-httpx`, `ruff`, `factory-boy` | shipped in the production image | split to `requirements-dev.txt` |

**Verified NOT duplicates (do not merge):** `services/agent_orchestrator.py` (lifecycle: startup,
APScheduler, pause/resume) vs `agents/supervisor.py` (LangGraph event routing + HITL checkpoint) —
distinct responsibilities, both used by `main.py`. All 15 scrapers on disk are registered in
`SCRAPER_REGISTRY` and selectable via `profile.job_boards` — no scraper pruning.

---

# Part 1 — llama.cpp runtime (carried from rev 1, trimmed)

Two resident llama-server containers — triage and primary — because the scorer interleaves
triage→score calls per batch, and llama-server router mode does a full unload/reload per switch
(the pathological case). No embeddings container in this rev (embedder stays in-process).

### RT-1 — Compose services + model fetch

- [ ] `llm-primary` (`:8080`, Qwen3.5-4B-Instruct GGUF Q4_K_M, `--ctx-size 16384 --parallel 1` —
      sized for today's monolithic CV-generation call; drops to 8192 once the grounding spec's
      G-4 per-section tailoring lands, see A12) and
      `llm-triage` (`:8081`, Qwen3.5-0.8B GGUF Q8_0, `--ctx-size 4096 --parallel 2` — context is
      divided across slots, giving 2048/slot; see A7) from a **pinned**
      `ghcr.io/ggml-org/llama.cpp:server-<tag>` image; shared `./data/models:/models:ro`;
      `--threads` **omitted by default** (llama.cpp self-detects; the flag requires an integer —
      see A10); healthchecks on `/health`; backend `depends_on: healthy`.
- [ ] `scripts/fetch_models.sh` (or init service): idempotent GGUF download from pinned HF
      repo+revision with sha256 verification; offline path documented (drop files in
      `data/models/`).
- [ ] Test: compose config validates; fetch idempotent; healthcheck gates startup.

**Commit:** `feat(runtime): compose-managed llama-server services for triage and primary`

### RT-2 — Profile schema + factory wiring

- [ ] `schemas/profile.py` llm: add `triage_base_url: str = ""` (falls back to `base_url`);
      default provider flips to `"llamacpp"` with the two service URLs. `get_triage_model()`
      honours `triage_base_url`. Existing `provider: ollama` profiles continue working unchanged
      (regression suite).
- [ ] Onboarding StepAIProvider: "Built-in local (recommended)" option, **pre-selected** —
      including flipping the wizard's initial state in `onboarding/page.tsx` from `google_genai`
      to `llamacpp`. Rationale: in the shipped deployment the wizard is only reachable when
      compose is up, and `depends_on: healthy` means the LLM services are up with it — so the
      zero-key, privacy-first default works out of the box, which is the product's headline
      promise; `google_genai` pre-selected would demand an API key first. Guard the edge (backend
      run outside compose / services disabled): reuse the existing `/test-connection` pattern to
      show a live reachability indicator on the step, with inline hint "Start the bundled AI
      services: `docker compose up -d`" on failure — the user can switch providers right there.
      Existing Ollama option relabelled "Ollama on this machine (advanced)".
- [ ] Fold-onto-primary fallback built in: setting `triage_base_url == base_url` runs both roles
      on one server (for 8GB-constrained machines; document).
- [ ] **Startup context assertion (from A7, owned here):** on backend startup, read `/props` from
      each configured llama-server and compare slot context (`ctx / parallel`) against the largest
      `prompt_budget + max_output` routed to that server. Mismatch → `logger.warning` with the
      numbers + a `degraded: context_budget_exceeds_slot` detail on `/api/health` so the UI can
      surface it. **Soft warning, never a hard failure** — a self-hosted app must not refuse to
      boot over a tuning mismatch; the consequence is truncation risk, not corruption. Skip
      silently for non-llamacpp providers and unreachable servers (healthcheck owns reachability).
- [ ] Tests: distinct base_urls per role; ollama regression green; fallback path builds; /props
      mismatch produces the warning + health detail (mocked /props).

**Commit:** `feat(llm): per-role llamacpp endpoints; llamacpp becomes the default local provider`

### RT-3 — Grammar-guaranteed JSON

- [ ] `get_json_model()` on the llamacpp path passes
      `response_format={"type":"json_schema","json_schema":{...}}` derived from the target
      Pydantic model (scorer `_ScoreResult`/`_TriageResult`, JD analysis, tailor per-section
      schemas). Structurally valid JSON every call on the local path; tolerant parser retained
      for other providers.
- [ ] Tests: schema attached for llamacpp; recorded-response round-trip parses first time.

**Commit:** `feat(llm): json_schema grammar enforcement on the llamacpp path`

### RT-4 — Provider-aware reasoning/context handling + docs

- [ ] Thinking-mode: llamacpp branch for Qwen3.5 GGUF (`chat_template_kwargs:
      {enable_thinking: false}` or `/no_think` — verify against the pinned tag, lock with a
      test). Triage/scoring always non-thinking; `llm.reasoning=true` opts Coach rubric calls in.
- [ ] `num_ctx`/Ollama-specific tuning blocks become provider-aware (no-ops for llamacpp where the
      server flag governs).
- [ ] README/install rewritten around the self-contained compose; "stay on Ollama" path in
      release notes.
- [ ] Tests: thinking off by default on llamacpp; gemma4/ollama behaviour unchanged.

**Commit:** `refactor(llm): provider-aware context and reasoning handling for llamacpp default`

---

# Part 2 — Dead-weight removal (backend)

### DW-1 — Remove ChromaDB (D1)
- [ ] Delete requirement, `CHROMA_PERSIST_DIR` (config + compose), and the stray keyword in
      `skills/cv-tailoring/scripts/extract_jd_keywords.py`.
- [ ] Grep-tripwire test: no `chromadb` import anywhere.

**Commit:** `chore(deps): remove unused ChromaDB`

### DW-2 — Remove the autonomous-apply residue (D2)
- [ ] Delete `repositories/auto_apply_repository.py`, `models/auto_apply.py`; strip the import
      from `models/__init__.py:7` and `database.py:77`; remove the `auto_apply_results` block and
      `ApplicationAttempt` import from `digest_service.py` (and its template section in
      `templates/emails/`).
- [ ] Alembic migration dropping `application_attempts` (guard: only if empty — if any deployment
      has rows, log + skip and surface a manual note; expected empty since nothing writes it).
- [ ] Confirm `test_no_autonomous_submission` untouched and green — this removal *strengthens*
      the boundary by deleting the last machinery that could have served auto-apply.
- [ ] Tests: digest renders without the section; app boots; models import clean.

**Commit:** `chore: remove dead autonomous-apply model/repository/digest residue`

### DW-3 — Remove dead services/modules (D3, D4, D7)
- [ ] Delete `services/recruiter_finder.py` and `skills/wrappers.py` (+ their tests if any are
      testing dead code only).
- [ ] Fix vulture items: dead callback args in `llm_factory.py` (rename to `_serialized` etc. if
      signature-bound by LangChain callbacks — verify before deleting), the unused `struct` import
      in `tts_service.py`, and in `claude_client.py` remove **only `max_concurrent`** (zero
      callers pass it). **Do NOT remove `max_tokens` here** — 9 call sites across 9 files pass it
      as an explicit keyword (it is accepted-and-ignored today); removing it in DW-3 breaks the
      backend until R2. R2 owns that parameter's fate (see A14).
- [ ] Test: import-graph script (see R5) reports zero never-imported modules after this task
      (excluding `main`, `seed`, `config`, alembic, skill scripts executed by the skill loader).

**Commit:** `chore: delete dead modules and vulture findings`

### DW-4 — Requirements hygiene (D8)
- [ ] Split `requirements-dev.txt` (pytest*, ruff, factory-boy); Dockerfile installs runtime only;
      CI installs both. Pin review while there: `next` line per SEC-9 note stays.
- [ ] Test: production image build succeeds without dev deps; `pip check` clean.

**Commit:** `chore(deps): split dev requirements out of the runtime image`

---

# Part 3 — Frontend cleanup (D6)

### C1 — Decide-and-remove pass for the 10 orphans
Disposition per component (proposed; confirm during implementation):
- **Remove** (superseded by `hatch/` shell equivalents or feature rework): `JobTable.tsx`
  (jobs page renders its own table), `CVPreview.tsx`, `CLPreview.tsx`, `StatsBar.tsx`,
  `ActivityTimeline.tsx`, `AdvancedFilterPanel.tsx`, `coach/RecordingControls.tsx`,
  `coach/StoryMatchBadge.tsx`.
- **Rewire** (cheap, fills a known gap): `EmptyState.tsx` — the 2026-06-10 audit's UX-5
  (cause-specific empty states) assumed this component was live; wire it there rather than
  rebuilding. `GhostBadge.tsx` — ghost-job detection exists in the backend; if the jobs list
  lacks a ghost indicator, rewiring this is a one-liner of product value; otherwise remove.
- [ ] For removals: delete component + its orphaned tests/stories; `npx tsc --noEmit` and Vitest
      green; no dynamic-import references (grep `lazy(`/string paths) — verified zero, re-verify.
- [ ] Note: `JobTable.tsx` removal closes part of audit HC-1's hardcoded-`£` surface — update that
      spec's finding list on completion.

**Commit:** `chore(ui): remove v4-orphaned components; rewire EmptyState and GhostBadge`

### C2 — Orphan tripwire for the frontend
- [ ] Add `knip` (or `ts-prune`) to CI with a baseline of zero unused exported components under
      `src/components`; failures block merge. Prevents the v4-style silent orphaning from
      recurring.

**Commit:** `ci(ui): unused-export gate (knip) to prevent component orphaning`

---

# Part 4 — Refactors (behaviour-preserving)

### R1 — Rename `ClaudeClient` → `LLMClient`
It wraps `llm_factory` and serves every provider; the name misleads (`services/claude_client.py:1`
docstring already says "Provider-agnostic"). Atomic rename — 39 occurrences across 11 files
(post-DW-3, which deletes `recruiter_finder` first) +
tests in one commit — **no deprecation alias** (per A8: consumers are all internal, and an alias
would be dead code in a release dedicated to removing dead code).

**Commit:** `refactor: rename ClaudeClient to LLMClient (provider-agnostic reality)`

### R2 — Centralised per-call token budgets (full scope; split R2a/R2b per A14)

**Reality check that reshapes this task:** `complete()`/`complete_json()` accept `max_tokens` but
their bodies never use it — `llm.ainvoke(messages)` runs with no output bound. **Every
`max_tokens` literal in the codebase is decorative today**; actual behaviour is
model-default/`num_ctx`-bounded generation. Therefore the behaviour-preserving baseline is
"unbounded", and *enforcing* any budget is new behaviour. The task splits:

**R2a (this release, pure no-op refactor):** create `context_budgets.py` with
`(prompt_budget, max_output)` per call type; replace every literal with its constant (still
passed, still ignored); land the tripwire. Constants capture the original author intent
(= current literals) so R2b has a vetted table to enforce. Full table — `prompt_budget`
mechanically `16384 − max_output` unless A7 specified tighter:

`TRIAGE=(1536, 256)` · `SCORING=(3328, 768)` ·
`CV_GENERATE=(10240, 6000)` *(transitional; cv_tailor.py:194 — never `TAILORING`, per A12)* ·
`TAILORING=(6656, 1536)` *(reserved for G-4 per-section calls)* ·
`CL_BODY=(6656, 2048)` *(cl_generator.py:85,102 — current literals)* ·
`CL_SNIPPET=(2048, 512)` *(cl_generator.py:139 — own constant; GENERIC must not absorb a 512
call)* · `JD_ANALYSIS=(3328, 1024)` · `ATS=(4096, 2048)` *(current literal, not A7's 1024)* ·
`COMPANY_RESEARCH=(3072, 2048)` *(current literal)* · `CV_PARSE=(12288, 4096)` ·
`ANSWER_EVAL=(2048, 2048)` · `MODEL_ANSWER=(2048, 2048)` · `QUESTION_GEN=(4096, 4096)` ·
`FEEDBACK=(4096, 4096)` · `COACH_RUBRIC=(6144, 2048)` ·
`GENERIC=(3072, 4096)` *(max_output matches the existing signature default of 4096 — so
jd_analyser's and email_generator's no-arg calls see zero change at R2b time)*.

Tripwire (R2a): regex `(max_tokens|num_ctx)\s*=\s*\d` over `backend/app/**/*.py`, allowlist
exactly `agents/tools/context_budgets.py`; tests excluded by path. `llm_factory.py`'s
`num_ctx=16384` becomes a derived constant in the same module.

**R2b (separate commit, bench-gated):** actually forward `max_output` to the model
(`llm.bind(max_tokens=...)` / provider-appropriate kwarg) and enforce `prompt_budget` truncation
warnings. Gate: bench harness run comparing JSON-failure and truncation rates before/after;
any call type whose output is observed exceeding its budget gets the budget raised before
enforcement, not after a production truncation.

**Commits:** `refactor(llm): centralise token budgets (no-op)` · `feat(llm): enforce per-call output budgets (bench-gated)`

### R3 — SQLite pragmas (cheap, addresses the documented db-lock history)
`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON` on engine
connect. Index work (third and final correction — see A14): the hot list query
(`job_repository.py:115,161–163`) filters `is_active.is_(True)` and orders by
`match_score.desc().nullslast(), scraped_at.desc()` or `scraped_at.desc()` — **not** `status`
(doesn't exist) and **not** `sync_status` (a scrape-sync state, never in the list predicates).
Net-new index: `Index("idx_job_postings_active_scraped", "is_active", "scraped_at")`. The
`match_score` ordering path uses `nullslast()`, which SQLite won't serve from a simple composite —
don't add an index for it; rely on the `(is_active, scraped_at)` filter narrowing.
`agent_events` and `job_scores` stay untouched (already indexed). **The test is the authority:**
`EXPLAIN QUERY PLAN` on the actual `list_with_filters` query must show the new index; if it
doesn't, fix the index to match the plan, not the spec.

**Commit:** `perf(db): WAL, pragmas, hot-path indices`

### R4 — Wire `JobScoreRead` (D5): additive endpoint, not a response reshape
Implementer verification confirms SC-3's per-dimension transparency is **already live**:
`JobPostingRead` embeds all four dimensions + reasoning/strengths/gaps and `JobCard` renders them
via `ScoreBadge`. Mark SC-3's UI portion done. What `JobScoreRead` uniquely offers is the score
*record*: `id`, `job_id`, `scored_at` — none currently exposed. R4 is therefore **additive only**:
- `GET /api/v2/scoring/{job_id}` on the scoring router returning the raw `JobScoreRead`
  (404 if unscored). No change to any existing response shape.
- One small consumer so the endpoint isn't write-only: surface `scored_at` as a "Scored <relative
  time>" line in the job detail view (stale scores become visible — useful once re-scoring
  exists). Test: endpoint round-trip; 404 path; relative-time render.

**Commit:** `feat(scoring): expose per-dimension scores via the existing JobScoreRead schema`

### R5 — Backend dead-code gate in CI
- [ ] Commit the AST import-graph script used for this audit as `scripts/dead_code_check.py`
      (allowlist: entrypoints, alembic, dynamically-loaded skill scripts under
      `skills/*/scripts/`). Run it + `vulture --min-confidence 90` in CI.

**Commit:** `ci: dead-code gates (import graph + vulture)`

---

## Explicitly NOT in this release

- Embedding stack changes of any kind (maintainer decision — MiniLM + sentence-transformers stays).
- FAISS or any vector index (no k-NN access pattern exists in the codebase).
- `agent_orchestrator`/`supervisor` consolidation (verified: distinct responsibilities).
- Scraper pruning (all 15 registered and profile-selectable).
- LangChain/LangGraph removal; Next.js 15 / transformers 5.x / langgraph 1.x migrations (SEC-9).
- Anything touching the assisted-apply boundary or `test_no_autonomous_submission`
  (DW-2 deletes dead residue *behind* that boundary; the guard test itself is untouched).

## Suggested execution order

1. **DW-1, DW-3, DW-4** (pure deletions — shrink the surface before changing the runtime)
2. **RT-1 → RT-4** (llama.cpp switch, in order; bench before/after with the rev-1 Phase-0 harness
   if already landed, else a minimal tokens/sec + score-one-job timing note)
3. **DW-2** (auto-apply residue — includes a migration, so after the runtime settles)
4. **R1, R2, R3** (rename, budgets, pragmas)
5. **C1, R4** (frontend cleanup + score transparency)
6. **C2, R5** (CI gates last, once the baseline is clean)

## Risks

| Risk | Mitigation |
|---|---|
| llama.cpp flag churn on upgrade | pinned image tag; RT-4 test locks thinking behaviour; upgrades are deliberate |
| A "dead" module is loaded dynamically somewhere unexpected | import-graph allowlist + full test suite + grep for string-based imports before each deletion |
| `application_attempts` has rows in some deployment | migration guards on non-empty and skips with a logged manual note |
| Component removal breaks an unmerged branch | deletions are git-recoverable; do C1 in one reviewable commit |
| 8GB machines with both servers + backend + frontend | fold-onto-primary fallback (RT-2); resident weights ≈3.5GB at defaults |

## Open questions

1. **GhostBadge** — RESOLVED, see Addendum A5: rewire into `JobCard.tsx`; schema fields already exist.
2. **Triage container vs fold-onto-primary as the *default*** — once deterministic pre-triage
   (SC-1) lands, LLM triage volume drops; decide by measured batch timings whether the second
   container earns its RAM on 8GB machines.
3. **GGUF source** — pin one repo+revision+sha256 in `fetch_models.sh` (Addendum A2 names the
   defaults).
4. **Deprecation alias horizon** — RESOLVED, see Addendum A8: no alias, atomic rename.

---

# Addendum (2026-06-11) — Implementation Q&A resolutions

Answers to the implementer's blocking questions, verified against the repo and current ecosystem.

### A1 — llama.cpp image (RT-1 unblocked)

The compose comment ("GHCR images are 2024 builds that predate Qwen3 support") is **stale** — GHCR
publishes per-build tags continuously from `ghcr.io/ggml-org/llama.cpp`. Qwen3.5 (released Feb
2026) is supported by current mainline llama.cpp; QwenLM's own docs direct GGUF users to
llama.cpp, and notably **Ollama could not initially run Qwen3.5 GGUFs** (separate mmproj files) —
one more reason this switch is right.

Pinning procedure (first task in RT-1, replaces guessing a tag in the spec):
1. `docker pull ghcr.io/ggml-org/llama.cpp:server` (rolling) → `docker run --rm <image> --version`
   → note the build number `bNNNN`.
2. Gate: the image must load `Qwen3.5-0.8B-GGUF:Q8_0` and answer one prompt (smoke script in
   `scripts/verify_runtime.sh`). Any build ≥ March 2026 passes.
3. Pin `ghcr.io/ggml-org/llama.cpp:server-bNNNN` in compose; record build + date in the compose
   comment, replacing the stale one.

### A2 — Model names and the on-disk 14B (RT-1)

"Qwen3.5" is the correct family name, **not** a typo: released Feb 2026 with Small variants
**0.8B / 2B / 4B / 9B** (plus MoE Medium). So:
- Primary default: **Qwen3.5-4B** Q4_K_M. Triage: **Qwen3.5-0.8B** Q8_0.
- The documented upgrade tier becomes **Qwen3.5-9B** (there is no 8B in this family — corrects the
  rev-1 doc; ~12GB RAM near-full-precision per Unsloth, Q4 comfortably in 8GB; expect ~3–5 tok/s
  on U-series CPUs).
- The existing `./models/Qwen3-14B-Q4_K_M.gguf` (previous family): **do not delete in code** — the
  fetch script never removes user files. Release notes mark it superseded (Qwen3.5-9B ≥ quality at
  ~40% less RAM and ~2× speed); user reclaims the 9GB manually if they wish. It remains selectable
  as a custom model path.
- Pin GGUF sources in `fetch_models.sh`: prefer official `Qwen/Qwen3.5-*-GGUF` repos; fall back to
  unsloth/bartowski only if an official quant is missing — record repo+revision+sha256 either way.

### A3 — JobTable.tsx (C1) — premise incorrect, deletion stands

Verified at `4d208ab`: `frontend/src/app/jobs/page.tsx` imports and renders **`JobCard`** (line
14, render at 319) plus `FilterPanel` — it does **not** import `JobTable`. The only file
containing the string `JobTable` is `JobTable.tsx` itself. There is no gap; delete with no
replacement plan needed.

### A4 — EmptyState (C1/D6) — CORRECTED 2026-06-11 (working tree diverged from `4d208ab`)

The original A4 was verified against commit `4d208ab` and is stale for HEAD: the working tree now
contains `components/ui/EmptyState.tsx` — a live, typed component with `EmptyStateCause` variants
(`"no-profile"`, `"no-scrape"`, `"scraped-unscored"`) — i.e. **UX-5 has partially landed since the
audit commit**, and `JobTable.tsx` now imports it.

Resolution:
- **Canonical: `components/ui/EmptyState.tsx`.** It already implements UX-5's cause-specific
  design; all UX-5 wiring goes through it.
- **Delete `components/EmptyState.tsx`** (the pre-UX-5 orphan, superseded).
- **Re-run the D6 reference counts against HEAD before any deletion** — the audit numbers are
  commit-pinned to `4d208ab`. Specifically for `JobTable.tsx`: if a page now renders it, keep it
  (and audit HC-1's hardcoded-`£` fix applies to it); if it is still page-orphaned, delete it and
  confirm `ui/EmptyState.tsx` retains its UX-5 consumers afterwards.
- General rule appended to C1: every D6 disposition is re-verified against the implementer's HEAD
  (the C2 knip gate, run locally, is the verification tool) — deletions execute against current
  reality, not the audit snapshot.

### A9 — RT-3 scope: `get_json_model()` signature and the two JSON paths (RESOLVED)

There are two structured-output paths in the codebase and RT-3 must cover both, with **no change
to any caller's parsing flow**:

1. **Scorer path** — already typed: `scorer_agent.py:108–109` calls
   `get_*_model().with_structured_output(_TriageResult/_ScoreResult)`. On the llamacpp provider,
   LangChain's default `with_structured_output` method (function-calling) is the wrong choice for
   llama-server; the grammar-backed route is `method="json_schema"`. Add a factory helper that
   owns the per-provider decision:
   ```python
   def with_schema(llm: BaseChatModel, schema: type[BaseModel]) -> Runnable:
       """with_structured_output with the provider-correct method
       (llamacpp → method='json_schema'; others → LangChain default)."""
   ```
   Scorer changes two lines to `with_schema(get_triage_model(), _TriageResult)` etc.
2. **`complete_json` path** — `get_json_model()` gains an **optional** parameter:
   `get_json_model(schema: type[BaseModel] | None = None)`. With a schema on llamacpp, the
   response_format upgrades from `json_object` (already in place at `llm_factory.py:428`) to
   `{"type":"json_schema","json_schema":{"name": ..., "schema": schema.model_json_schema(),
   "strict": true}}`. **Return type unchanged** (a chat model emitting JSON text), so
   `complete_json`'s existing parse-and-retry loop is untouched. `ClaudeClient.complete_json`
   (→ `LLMClient` after R1) gains the same optional `schema=None` pass-through.
3. **Call-site threading is incremental, not blocking:** pass schemas where Pydantic models
   already exist (JD analysis, tailor per-section schemas from the grounding spec,
   `rubric_synthesiser`); everything else keeps `json_object` behaviour with zero edits. No
   caller is forced to change in RT-3.

Scope of RT-3 is therefore: `llm_factory` (helper + optional param), two scorer lines,
`complete_json` signature pass-through, and tests (llamacpp model carries the json_schema
response_format when a schema is given; json_object when not; scorer structured path uses
`method="json_schema"` on llamacpp).

### A10 — `--threads auto` is invalid (RT-1 corrected)

Correct: llama.cpp's `--threads` takes an integer; `auto` would crash the server. **Preference:
omit the flag entirely** — llama.cpp self-detects threads sensibly, and that is the zero-config
default this product wants. Tuning is for the minority and belongs in the standard Compose
override pattern: ship a commented `docker-compose.override.yml.example` showing a `command:`
override with an explicit `--threads N`. No shell-conditional interpolation
(`${LLAMA_THREADS:+...}`) in the main compose file — nested-variable expansion inside `:+` is
compose-version-sensitive and not worth the fragility for an advanced knob. If an inline knob is
ever demanded, the acceptance test is `docker compose config` rendering correctly with the var
both set and unset. One caveat for the override docs: in CPU-pinned containers
(`cpuset`/`cpus:` limits) auto-detection sees host cores, so users applying CPU limits should set
`--threads` to match the limit.

### A5 — GhostBadge rewire location (C1)

Backend already serves the data: `schemas/job.py:84–87` exposes `ghost_score`, `ghost_verdict`,
`ghost_signals`, `ghost_analysed_at` on the job payload. `JobCard.tsx` currently renders no ghost
indicator (and the jobs page only offers the `hide_ghosts` filter). Rewire = render `GhostBadge`
inside **`JobCard.tsx`** when `job.ghost_verdict` is non-null, showing verdict + score, tooltip
listing `ghost_signals`. One conditional render; Vitest case: badge present for a ghost-flagged
job fixture, absent otherwise.

### A6 — wrappers.py is unreachable by the skill loader (DW-3 safe)

`skill_loader.py` loads scripts exclusively via
`self._registry.skill_dir(name) / "scripts" / filename` (line 126) with
`importlib.util.spec_from_file_location`. `skills/wrappers.py` sits at the `skills/` package root,
not under any skill's `scripts/` directory, and no skill script, SKILL.md, or app module
references it (repo-wide grep). Purely dead; delete.

### A7 — Context budget semantics (R2/RT-1 corrected)

`--ctx-size` is the **total** window (prompt + generation), and with `--parallel N` llama-server
**divides the context across slots** (each slot gets ctx/N). The spec's original numbers would
have given triage zero headroom. Corrected definitions:

- `context_budgets.py` defines per-call `(prompt_budget, max_output)`:
  TRIAGE=(1536, 256) · SCORING=(3328, 768) · TAILORING=(6656, 1536) · COACH=(6144, 2048).
  App code truncates/validates prompts against `prompt_budget` and passes `max_tokens=max_output`.
- Server flags derive from the budgets: triage server `--ctx-size 4096 --parallel 2`
  (= 2048/slot ≥ 1536+256); primary server `--ctx-size 8192 --parallel 1` (≥ all primary-call
  sums). A startup assertion in the backend reads `/props` from each server and warns if
  slot-context < the largest budget routed to it.

### A8 — ClaudeClient alias (R1 closed)

No deprecation alias. All consumers are internal services; do the rename atomically in one commit
(`git grep -l ClaudeClient` → rename + imports + tests). An alias would itself be dead code in a
release dedicated to removing dead code.

### A11 — `ui/EmptyState.tsx` wire target after JobTable deletion (C1 completed)

Correct observation: deleting `JobTable.tsx` (its sole consumer at HEAD) would orphan
`ui/EmptyState.tsx` and trip the C2 knip gate. **Wire target: `app/jobs/page.tsx`** — page level,
not the hatch shell (empty-list state is a per-page concern; the shell stays layout-only).

Sequencing within C1 (gate-clean at every step; backend item may be a separate PR landing first):
0. Backend (in C1 scope per A13): extend `ScoringInsights` with `total_jobs_in_db` and
   `total_scored` (A12). Frontend treats the fields as optional — `undefined` → generic empty
   state, never a guessed cause — so deploy order cannot break the page.
1. In `jobs/page.tsx`, when the fetched job list is empty, render `ui/EmptyState` with the cause
   derived from data already available to the page: no confirmed profile → `"no-profile"`
   (CTA → onboarding); profile exists but zero jobs in DB → `"no-scrape"` (CTA → trigger scout);
   jobs exist but none scored / all filtered → `"scraped-unscored"` (CTA → scoring status). This
   *is* audit UX-5 — implementing it here closes that task; update the 2026-06-10 spec's UX-5 to
   "done via v5 C1" on completion.
2. Then delete `JobTable.tsx` (re-verified against HEAD per A4) and `components/EmptyState.tsx`.
3. Run knip locally: zero unused exports under `src/components`.
- Vitest: each cause renders the right copy + CTA; empty-list page shows the component;
  non-empty list renders cards as today.

If the Today page later wants the same treatment, that's a follow-up — not part of C1.

### A12 — Empty-state cause signals + tailoring budget split (final two gaps)

**A11 cause derivation: add the fields, don't accept the proxy.** The 7-day window makes
`scored_last_7d=0` wrong for any user returning after a quiet week — a guaranteed-misleading
empty state for exactly the user who most needs an accurate one. Add **two** all-time counts to
the `ScoringInsights` response (both are single `COUNT(*)` queries):
- `total_jobs_in_db: int` — distinguishes `"no-scrape"` (=0) from everything else;
- `total_scored: int` — distinguishes `"scraped-unscored"` (jobs>0, scored=0) from
  `"no-results"` (scored>0, filtered total=0) without the same window bug recurring one level up.

Exact decision table: no confirmed profile → `"no-profile"`; else `total_jobs_in_db==0` →
`"no-scrape"`; else `total_scored==0` → `"scraped-unscored"`; else filtered `total==0` →
`"no-results"`. Test each branch with fixture counts.

**R2 tailoring budget: separate constant (option B), plus a correction to A7's server sizing.**
Adopting `TAILORING.max_output=1536` for today's monolithic call would truncate CV generation —
the behaviour-preserving rule forbids it. But the deeper issue: A7's `(6656, 1536)` numbers were
designed for the grounding spec's G-4 *per-section* calls, and the primary server's
`--ctx-size 8192` assumed the same. If v5 lands before G-4 (it will), the monolithic call needs
prompt + 6000 output ≈ 12–16K — which `8192` cannot fit. Resolution:
- `CV_GENERATE=(10240, 6000)` — transitional constant for the monolithic call, preserving the
  current `max_tokens=6000` literal exactly;
- `TAILORING=(6656, 1536)` — reserved, applied only when G-4's per-section calls exist;
- primary server ships at `--ctx-size 16384` (matching the current Ollama `num_ctx=16384`
  behaviour) and drops to `8192` in the same PR that lands G-4 and deletes `CV_GENERATE`;
- the RT-2 `/props` startup assertion is the enforcement: it would have flagged the
  `10240+6000 > 8192` mismatch on first boot — which is precisely why it exists. Add a test
  asserting `CV_GENERATE` fits the shipped primary `--ctx-size`.

### A13 — Final verification-pass resolutions

- **R3 corrected in body:** the spec's original index list named a non-existent `events` table and
  two already-indexed paths. Net-new index is `job_postings(status, created_at)` only.
- **R4 interpretation confirmed:** SC-3 transparency is already live; R4 = additive
  `GET /api/v2/scoring/{job_id}` returning `JobScoreRead`, plus a `scored_at` line in the job
  detail as its first consumer. No existing response shapes change.
- **RT-2 onboarding:** llamacpp **pre-selected** with a live reachability indicator and a
  `docker compose up -d` hint on failure (full rationale in the RT-2 checklist).
- **C1 ↔ A12 coupling made explicit:** the `ScoringInsights` backend extension
  (`total_jobs_in_db`, `total_scored`) is **in C1's scope**. Sequencing: backend field addition is
  additive and lands first (or same PR); the frontend cause-derivation treats the fields as
  optional (`undefined` → render the generic empty state, never a wrong cause) so the PRs cannot
  deploy in a broken order.
- Line-number nit fixed (`CHROMA_PERSIST_DIR` → config.py:72); R1 scope corrected to 39
  occurrences / 11 files post-DW-3.

### A14 — Ground-up verification resolutions (final)

**1. R3 index — neither `status` nor `sync_status`.** Verified against
`job_repository.py:115,161–163`: the hot list query filters `is_active` and orders by
`scraped_at`/`match_score` — `sync_status` never appears in list predicates and `created_at`
appears only in the ghost backlog query. Correct index:
`Index("idx_job_postings_active_scraped", "is_active", "scraped_at")`. R3 body rewritten; the
`EXPLAIN QUERY PLAN` test remains the final authority over any spec text (three iterations on
this index is the proof of why).

**2. DW-3/R2 sequencing — agreed.** DW-3 removes only `max_concurrent`; `max_tokens` stays in
both signatures until R2. Spec body updated.

**3+4. The missing/mismatched constants — resolved by a deeper fact:** `complete()`/
`complete_json()` never use `max_tokens` in their bodies (`llm.ainvoke(messages)` — vulture was
right at 100% confidence). Every literal is decorative; current behaviour is unbounded
generation. So R2 splits: **R2a** centralises all literals (including the 5 unmapped files —
`CV_PARSE`, `ANSWER_EVAL`, `MODEL_ANSWER`, `QUESTION_GEN`, `FEEDBACK` at current values, and
dedicated `CL_SNIPPET=(2048,512)` so GENERIC never absorbs a 512 call) as a pure no-op with the
tripwire; **R2b** separately enforces forwarding, bench-gated. `ATS` and `COMPANY_RESEARCH`
adopt their current literals (2048). `GENERIC.max_output=4096` matches the existing signature
default, so jd_analyser's and email_generator's no-arg calls see no change when R2b lands.

**5. RT-2 llamacpp pre-fill values** (also closes frontend gaps a–c, added to RT-2 checklist):
- `base_url = "http://llm-primary:8080/v1"` · `triage_base_url = "http://llm-triage:8081/v1"`
  (compose service names; the backend resolves them — these are backend-side URLs stored in the
  profile, never fetched by the browser).
- `primary_model = "qwen3.5-4b-instruct-q4_k_m"` · `triage_model = "qwen3.5-0.8b-q8_0"` —
  lowercase, exactly matching the GGUF filenames pinned in `fetch_models.sh` (single source of
  truth: export both strings from one shared constants location). Note: llama-server in
  single-model mode ignores the request's `model` field, so these strings serve cost-tracking
  rows, traces, and display — consistency matters, validity to the server does not.
- Gap (a): `LLMData` interface gains `triage_base_url: string` so `saveProfile()` round-trips it.
- Gap (b): `needsKey` becomes `llm.provider !== "ollama" && llm.provider !== "llamacpp"`.
- Gap (c): `handleProviderChange("llamacpp")` performs **no detection** and writes the four
  values above directly; the step's reachability indicator (`/test-connection`) is the
  verification, not model-list discovery.

**Non-blocking acks:** R1 count is 13 files (grep-and-replace regardless). DW-1 is a string list
entry, not an import. RT-4 clarified: the llamacpp thinking path goes through ChatOpenAI
`extra_body`/`chat_template_kwargs` and must NOT touch `_maybe_add_think_token` (which correctly
early-returns for non-ollama providers).
