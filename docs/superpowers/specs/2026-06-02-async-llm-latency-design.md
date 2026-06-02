# Async LLM Latency Architecture — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate user-facing timeouts on all LLM-heavy endpoints by converting them to an async job + polling pattern, and replace the slow local Ollama/gemma model with a llama.cpp server running Qwen3 14B Q4_K_M.

**Architecture:** All user-blocking LLM endpoints return `202 Accepted` with a `job_id` immediately. A background asyncio coroutine runs the actual LLM work and writes the result to a new `async_jobs` table. The frontend polls `GET /api/async-jobs/{job_id}` every 3 seconds and shows in-app toast + notification bell when the job completes.

**Tech Stack:** FastAPI background tasks (asyncio), SQLAlchemy async + SQLite, Alembic migration, React `useAsyncJob` hook, llama.cpp server container (OpenAI-compatible API), Qwen3 14B Q4_K_M GGUF, LangChain `ChatOpenAI`.

---

## 1. Root Cause

`POST /api/tailor/analyse` and `POST /api/coach/sessions` (and 8 other endpoints) call the LLM synchronously. With `gemma:latest` on CPU, each LLM call takes 5–10 minutes. The Next.js rewrite proxy times out at ~30 seconds, returning 500 before the backend finishes. Switching models alone is insufficient — the proxy timeout problem exists regardless of model speed. Both fixes are required.

---

## 2. Async Job Layer

### 2.1 Database Model

New table `async_jobs` (Alembic migration required):

```python
# backend/app/models/async_job.py
class AsyncJob(Base):
    __tablename__ = "async_jobs"

    id: str          # UUID PK
    type: str        # "tailor_analyse" | "tailor_generate_cv" | "tailor_generate_cl"
                     # | "tailor_generate" | "coach_session" | "submit_answer"
                     # | "end_session" | "email_generate" | "ghost_analyse"
    status: str      # "pending" | "running" | "done" | "failed"
    result_json: str | None   # serialised Pydantic model; null until done
    error: str | None         # error message if failed
    created_at: datetime
    updated_at: datetime
```

No `payload_json` column — the job coroutine already has all inputs captured via closure. Retries are not in scope for v1.

### 2.2 AsyncJobService

```python
# backend/app/services/async_job_service.py
class AsyncJobService:
    @staticmethod
    async def create(db: AsyncSession, job_type: str) -> AsyncJob:
        """Persist a new pending job and return it."""

    @staticmethod
    def run(job_id: str, coro: Coroutine[Any, Any, str]) -> None:
        """Fire-and-forget: create asyncio.Task that runs coro.
        coro must write result_json and set status=done|failed via _finish()."""

    @staticmethod
    async def _finish(
        job_id: str, result_json: str | None, error: str | None
    ) -> None:
        """Open a new DB session (separate from the request session) and
        persist the final status. Called from within the background coroutine."""

    @staticmethod
    async def get(db: AsyncSession, job_id: str) -> AsyncJob | None:
        """Return the job record by ID."""

    @staticmethod
    async def list_completed_since(
        db: AsyncSession, since: datetime, limit: int = 20
    ) -> list[AsyncJob]:
        """Return done jobs created after `since`. Used by notification bell."""
```

**Critical detail:** The background coroutine must open its own DB session via `async_sessionmaker` — it cannot reuse the request-scoped session, which is closed when the 202 response is sent.

### 2.3 New Router

```python
# backend/app/routers/async_jobs.py
GET /api/async-jobs/{job_id}
→ 200 { id, type, status, result, error, created_at }
→ 404 if not found

GET /api/async-jobs?status=done&since=ISO8601&limit=20
→ 200 [ { id, type, status, result, error, created_at }, … ]
```

`result` is the raw JSON object (not a string) when `status == "done"`.

---

## 3. Endpoint Migration

Every endpoint below changes from synchronous (blocks until LLM returns) to async (returns 202 immediately).

**Before:**
```
POST /api/tailor/analyse
→ 200 { analysis: {...}, skill_match: {...} }   # after 10-min LLM call
```

**After:**
```
POST /api/tailor/analyse
→ 202 { job_id: "abc-123", status: "pending", type: "tailor_analyse" }

GET /api/async-jobs/abc-123          # polled every 3s by frontend
→ { status: "running", ... }
→ { status: "done", result: { analysis: {...}, skill_match: {...} } }
```

### Endpoint table

| Endpoint | Job type | Service method | LLM calls |
|---|---|---|---|
| `POST /api/tailor/analyse` | `tailor_analyse` | `TailorService.analyse_jd_text` | 1 |
| `POST /api/tailor/analyse/{job_id}` | `tailor_analyse` | `TailorService.analyse_job` | 1 |
| `POST /api/tailor/generate-cv` | `tailor_generate_cv` | `TailorService.generate_cv` | 2 |
| `POST /api/tailor/generate-cl` | `tailor_generate_cl` | `TailorService.generate_cover_letter` | 1 |
| `POST /api/tailor/generate` | `tailor_generate` | `TailorService.generate_all` | 3–4 |
| `POST /api/coach/sessions` | `coach_session` | `CoachService.create_session` | 10–15 |
| `POST /api/coach/sessions/{id}/submit-answer` | `submit_answer` | `CoachService.submit_answer` | 1 |
| `POST /api/coach/sessions/{id}/end` | `end_session` | `CoachService.end_session` | 1 |
| `POST /api/emails/generate/{id}` | `email_generate` | `EmailGenerator.generate` | 1 |
| `POST /api/ghost/analyse/{id}` | `ghost_analyse` | `GhostDetector.analyse` | 1 |

### Implementation pattern (same for all 10 endpoints)

```python
@router.post("/analyse", status_code=202)
async def analyse_jd_text(
    job_description: str = Query(...),
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    job = await AsyncJobService.create(db, "tailor_analyse")

    async def _work() -> None:
        try:
            result = await svc.analyse_jd_text(job_description, None)
            await AsyncJobService._finish(job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(job.id, None, str(exc))

    AsyncJobService.run(job.id, _work())
    return {"job_id": job.id, "status": "pending", "type": "tailor_analyse"}
```

**Existing SSE endpoint** (`GET /api/tailor/generate/stream`) is kept as-is. It serves a different use case — inline streaming for the generate pipeline when the user stays on the page.

---

## 4. Frontend Polling Layer

### 4.1 `useAsyncJob` Hook

```typescript
// frontend/src/hooks/useAsyncJob.ts
interface AsyncJobState<T> {
  jobId: string | null
  status: "idle" | "pending" | "running" | "done" | "failed"
  result: T | null
  error: string | null
}

function useAsyncJob<T>(options?: {
  pollIntervalMs?: number        // default 3000
  onComplete?: (result: T) => void
  onError?: (err: string) => void
}): {
  state: AsyncJobState<T>
  submit: (postFn: () => Promise<{ job_id: string }>) => Promise<void>
  reset: () => void
}
```

Behaviour:
- Calls `postFn()` → receives `{ job_id }`
- Polls `GET /api/async-jobs/{job_id}` every `pollIntervalMs`
- On `done`: stops polling, sets `result`, calls `onComplete`
- On `failed`: stops polling, sets `error`, calls `onError`
- On unmount: clears the interval (no memory leaks)

### 4.2 API additions in `api.ts`

```typescript
export interface AsyncJobResponse<T = unknown> {
  id: string
  type: string
  status: "pending" | "running" | "done" | "failed"
  result: T | null
  error: string | null
  created_at: string
}

export async function getAsyncJob<T>(jobId: string): Promise<AsyncJobResponse<T>>
export async function listCompletedJobs(since: string, limit?: number): Promise<AsyncJobResponse[]>
```

All 10 POST functions in `api.ts` are updated to return `{ job_id: string }` instead of the full result type. The pages/components that call them switch to `useAsyncJob`.

### 4.3 UI States

Every page that triggers a long LLM operation shows these states:

| State | UI |
|---|---|
| `idle` | Normal form, submit button enabled |
| `pending` | Button disabled, spinner, "Queuing…" |
| `running` | Spinner, human-readable label (e.g. "Analysing job description…") |
| `done` | Result renders, success toast: "Analysis complete" |
| `failed` | Error banner with the error message + Retry button |

Human-readable labels per job type:
```typescript
const JOB_LABELS: Record<string, string> = {
  tailor_analyse:      "Analysing job description…",
  tailor_generate_cv:  "Tailoring your CV…",
  tailor_generate_cl:  "Writing cover letter…",
  tailor_generate:     "Generating CV and cover letter…",
  coach_session:       "Preparing interview questions…",
  submit_answer:       "Evaluating your answer…",
  end_session:         "Generating feedback report…",
  email_generate:      "Drafting email…",
  ghost_analyse:       "Analysing job posting…",
}
```

### 4.4 Notification Bell

The existing `Navigation` component gains a `NotificationBell` sub-component:
- Stores `last_seen_at` in `localStorage`
- Polls `GET /api/async-jobs?status=done&since={last_seen_at}&limit=10` every **15 seconds** (separate from job polling)
- Shows a count badge on the bell icon for unseen completions
- Clicking opens a dropdown listing completed jobs: `"JD Analysis ready — Capgemini Scrum Consultant"`
- Each item links to the relevant page; clicking marks it seen (updates `last_seen_at`)

---

## 5. llama.cpp Server

### 5.1 Container

```yaml
# docker-compose.yml addition
llamacpp:
  image: ghcr.io/ggerganov/llama.cpp:server
  container_name: jobpilot-llamacpp
  volumes:
    - ./models:/models
  command: >
    --model /models/Qwen3-14B-Instruct-Q4_K_M.gguf
    --port 8080
    --host 0.0.0.0
    --ctx-size 8192
    --threads 4
    --chat-template qwen3
  networks: [jobpilot]
```

The `./models/` directory is bind-mounted. The GGUF file must be present before starting the container.

**RAM requirement:** ~8.5 GB for the model + ~1 GB overhead. Total system RAM needed alongside backend + frontend: ~12 GB minimum.

### 5.2 Model Download Script

```bash
# scripts/download-models.sh
#!/usr/bin/env bash
set -euo pipefail
MODEL_DIR="$(dirname "$0")/../models"
mkdir -p "$MODEL_DIR"

echo "Downloading Qwen3-14B-Instruct-Q4_K_M.gguf (~8.5 GB)…"
curl -L -o "$MODEL_DIR/Qwen3-14B-Instruct-Q4_K_M.gguf" \
  "https://huggingface.co/Qwen/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Instruct-Q4_K_M.gguf"

echo "Done. Run podman-compose up to start."
```

Run once before first `podman-compose up`. The `llamacpp` container fails to start if the file is missing (llama.cpp exits non-zero).

### 5.3 profile.yaml Changes

```yaml
llm:
  provider: llamacpp
  base_url: http://llamacpp:8080/v1
  primary_model: Qwen3-14B-Instruct
  triage_model: Qwen3-14B-Instruct
  temperature: 0.3
  max_retries: 2
  track_costs: true
  monthly_budget: 15.0
  currency: USD
```

### 5.4 llm_factory.py Changes

Add `llamacpp` provider branch using `ChatOpenAI` with a custom `base_url`:

```python
elif llm_cfg.provider == "llamacpp":
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=llm_cfg.primary_model,
        openai_api_base=llm_cfg.base_url,
        openai_api_key="not-required",   # llama.cpp doesn't check the key
        temperature=llm_cfg.temperature,
        max_retries=llm_cfg.max_retries,
    )
```

`get_json_model()` for llamacpp uses `response_format={"type": "json_object"}` via the API parameter — more reliable than Ollama's `format: "json"` because llama.cpp enforces JSON grammar sampling at the token level.

### 5.5 claude_client.py — Qwen3 Think-Block Stripping

Qwen3 can emit `<think>…</think>` reasoning blocks before the final answer. These must be stripped before `json.loads()`:

```python
# In complete_json(), after getting `text`:
import re
text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
```

This is a no-op for providers that don't emit think blocks.

---

## 6. Future Model Considerations

The llama.cpp container and `llamacpp` provider branch support drop-in model swaps via `profile.yaml`. Two models evaluated during design:

| Model | GGUF size (Q4_K_M) | Strength | Use case fit |
|---|---|---|---|
| **Phi-3.5-mini-instruct** | ~2.4 GB | Fast, low RAM, good instruction following | Suitable for lighter workloads or constrained hardware |
| **DeepSeek R1 Distill Qwen 14B** | ~8.5 GB | Strong reasoning, chain-of-thought, excels at evaluation tasks | Well-suited for interview answer evaluation and coaching feedback |

To switch to either model: update `profile.yaml` `primary_model` + `base_url` (if using a separate container), download the corresponding GGUF, and restart the `llamacpp` container. No code changes required.

For a per-module model split (tailor on one model, coach on another), `llm_factory.py` can be extended with `get_tailor_model()` and `get_coach_model()` getters, each reading a different `base_url` from an extended `profile.yaml` structure.

---

## 7. What Is Not Changing

- Background agent operations (job classifier, scorer, scout) run on the existing Ollama/gemma setup or via the new llama.cpp provider depending on profile.yaml — no special treatment needed since they are not user-blocking.
- The existing `GET /api/tailor/generate/stream` SSE endpoint is kept unchanged.
- The `EventBus` and `AgentEvent` table are not affected — they serve the agentic pipeline, not user-facing LLM jobs.
- The `ClaudeClient` interface (`complete`, `complete_json`, `complete_structured`) is unchanged — all callers continue to work.
