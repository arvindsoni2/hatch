---
title: Async LLM Latency Architecture Implementation Plan
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

# Async LLM Latency Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate user-facing 500 timeouts on all LLM-heavy endpoints by (A) replacing the slow gemma model with llama.cpp + Qwen3 14B Q4_K_M, and (B) converting all 10 user-blocking LLM endpoints to return 202 + job_id immediately, with the frontend polling for results.

**Architecture:** Phase A: Add a `llamacpp` container serving Qwen3 14B Q4_K_M via an OpenAI-compatible API; update `llm_factory.py` and `profile.yaml` to route all LLM calls through it. Phase B: Add an `async_jobs` table and `AsyncJobService`; every LLM-heavy POST returns `{job_id}` immediately while a background `asyncio.Task` runs the work; the frontend polls `GET /api/async-jobs/{job_id}` every 3 seconds and shows a notification bell on completion.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / SQLite, llama.cpp server container (OpenAI-compatible), LangChain `ChatOpenAI`, Next.js 14 / TypeScript / React hooks, vitest + @testing-library/react.

**Natural split point:** Tasks 1–3 (Phase A) and Tasks 4–14 (Phase B) can be done independently. Phase A gives immediate speed improvement even without the async pattern.

---

## File Map

### New files
| File | Purpose |
|---|---|
| `scripts/download-models.sh` | One-time GGUF download from HuggingFace |
| `models/.gitkeep` | Directory placeholder (GGUFs are gitignored) |
| `backend/app/models/async_job.py` | AsyncJob SQLAlchemy model |
| `backend/app/services/async_job_service.py` | create / run / _finish / get / list |
| `backend/app/routers/async_jobs.py` | GET /api/async-jobs/{id} + list endpoint |
| `backend/tests/test_services/test_async_job_service.py` | Service unit tests |
| `backend/tests/test_routers/test_async_jobs_router.py` | Router integration tests |
| `frontend/src/hooks/useAsyncJob.ts` | React polling hook |
| `frontend/src/components/NotificationBell.tsx` | Notification bell with badge |
| `frontend/src/__tests__/hooks/useAsyncJob.test.ts` | Hook tests |
| `frontend/src/__tests__/components/NotificationBell.test.tsx` | Bell tests |

### Modified files
| File | Change |
|---|---|
| `docker-compose.yml` | Add `llamacpp` service |
| `.gitignore` | Add `models/*.gguf` |
| `data/profile.yaml` | Switch provider to `llamacpp` |
| `backend/app/agents/tools/llm_factory.py` | Add `llamacpp` provider branch to `_build_model` + `get_json_model` |
| `backend/app/services/claude_client.py` | Strip `<think>…</think>` blocks before JSON parse |
| `backend/app/models/__init__.py` | Register `AsyncJob` |
| `backend/app/database.py` | Import async_job in `init_db` |
| `backend/app/main.py` | Register `async_jobs_router` |
| `backend/app/routers/tailor.py` | Migrate 5 endpoints → 202 |
| `backend/app/routers/coach.py` | Migrate 4 endpoints → 202 |
| `backend/app/routers/emails.py` | Migrate `generate_email` → 202 |
| `backend/app/routers/ghost.py` | Migrate `analyse_job` → 202 |
| `frontend/src/lib/api.ts` | Add `AsyncJobRef`, `AsyncJobResponse`, `getAsyncJob`, `listCompletedJobs`; update 10 POST functions |
| `frontend/src/app/tailor/page.tsx` | Switch `handleAnalyse` to `useAsyncJob` |
| `frontend/src/components/coach/SessionLauncher.tsx` | Switch `handleStart` to `useAsyncJob` |
| `frontend/src/components/Navigation.tsx` | Add `NotificationBell` |

---

## Phase A — Model Infrastructure

---

### Task 1: llama.cpp container + model download script

**Files:**
- Create: `scripts/download-models.sh`
- Create: `models/.gitkeep`
- Modify: `docker-compose.yml`
- Modify: `.gitignore`

- [ ] **Step 1: Create the models directory and gitignore the GGUF**

```bash
mkdir -p /path/to/project/models
```

Add to `.gitignore` (open the file and append):
```
# LLM model files — large binaries, download separately
models/*.gguf
models/*.bin
```

Create `models/.gitkeep` (empty file so the directory is tracked):
```bash
touch models/.gitkeep
```

- [ ] **Step 2: Write the download script**

Create `scripts/download-models.sh`:
```bash
#!/usr/bin/env bash
# Downloads Qwen3 14B Q4_K_M GGUF into ./models/
# Run once before first podman-compose up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_DIR="${SCRIPT_DIR}/../models"
MODEL_FILE="${MODEL_DIR}/Qwen3-14B-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/bartowski/Qwen3-14B-GGUF/resolve/main/Qwen3-14B-Q4_K_M.gguf"

mkdir -p "${MODEL_DIR}"

if [[ -f "${MODEL_FILE}" ]]; then
  echo "Model already present at ${MODEL_FILE} — skipping download."
  exit 0
fi

echo "Downloading Qwen3-14B-Q4_K_M.gguf (~8.5 GB) from HuggingFace…"
echo "URL: ${MODEL_URL}"
curl -L --progress-bar -o "${MODEL_FILE}" "${MODEL_URL}"

echo ""
echo "Done. Run 'podman-compose up' to start all services."
```

Make it executable:
```bash
chmod +x scripts/download-models.sh
```

- [ ] **Step 3: Add llamacpp service to docker-compose.yml**

Open `docker-compose.yml`. After the `frontend` service block, before the `networks:` section, add:

```yaml
  llamacpp:
    image: ghcr.io/ggerganov/llama.cpp:server
    container_name: jobpilot-llamacpp
    volumes:
      - ./models:/models:z
    command: >
      --model /models/Qwen3-14B-Q4_K_M.gguf
      --port 8080
      --host 0.0.0.0
      --ctx-size 8192
      --threads 4
      --chat-template qwen3
      --parallel 1
    ports:
      - "127.0.0.1:8080:8080"
    restart: unless-stopped
    networks:
      - jobpilot
```

Also add `llamacpp` to the backend's `depends_on` (optional but helpful):
```yaml
  backend:
    ...
    depends_on:
      llamacpp:
        condition: service_started
```

- [ ] **Step 4: Verify the compose file is valid**

Run from the project root:
```bash
podman-compose config --quiet
```
Expected: No errors printed.

- [ ] **Step 5: Commit**

```bash
git add scripts/download-models.sh models/.gitkeep docker-compose.yml .gitignore
git commit -m "feat: add llamacpp container + Qwen3 model download script"
```

---

### Task 2: llamacpp provider in llm_factory.py + think-block stripping in claude_client.py

**Files:**
- Modify: `backend/app/agents/tools/llm_factory.py`
- Modify: `backend/app/services/claude_client.py`
- Test: `backend/tests/test_tools/test_llm_factory.py`

- [ ] **Step 1: Write the failing test for llamacpp provider**

Open `backend/tests/test_tools/test_llm_factory.py`. Add these test cases (keep any existing tests):

```python
"""Tests for llm_factory — provider branches."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_llm_cfg(provider: str, base_url: str = "http://llamacpp:8080/v1") -> MagicMock:
    cfg = MagicMock()
    cfg.provider = provider
    cfg.primary_model = "Qwen3-14B-Instruct"
    cfg.triage_model = "Qwen3-14B-Instruct"
    cfg.temperature = 0.3
    cfg.max_retries = 2
    cfg.base_url = base_url
    cfg.api_key_env = ""
    return cfg


def _make_profile(provider: str) -> MagicMock:
    profile = MagicMock()
    profile.llm = _make_llm_cfg(provider)
    return profile


class TestLlamaCppProvider:
    def test_build_model_llamacpp_returns_chat_openai(self):
        """_build_model with provider=llamacpp returns a ChatOpenAI instance."""
        from langchain_openai import ChatOpenAI
        from app.agents.tools.llm_factory import _build_model

        cfg = _make_llm_cfg("llamacpp")
        with patch("app.agents.tools.llm_factory.load_profile"):
            model = _build_model("Qwen3-14B-Instruct", cfg)

        assert isinstance(model, ChatOpenAI)

    def test_get_primary_model_llamacpp_uses_base_url(self):
        """get_primary_model for llamacpp passes openai_api_base."""
        from langchain_openai import ChatOpenAI
        from app.agents.tools.llm_factory import get_primary_model

        with patch("app.agents.tools.llm_factory.load_profile", return_value=_make_profile("llamacpp")):
            model = get_primary_model()

        assert isinstance(model, ChatOpenAI)
        assert model.openai_api_base == "http://llamacpp:8080/v1"

    def test_get_json_model_llamacpp_sets_response_format(self):
        """get_json_model for llamacpp sets response_format=json_object in model_kwargs."""
        from langchain_openai import ChatOpenAI
        from app.agents.tools.llm_factory import get_json_model

        with patch("app.agents.tools.llm_factory.load_profile", return_value=_make_profile("llamacpp")):
            model = get_json_model()

        assert isinstance(model, ChatOpenAI)
        assert model.model_kwargs.get("response_format") == {"type": "json_object"}


class TestThinkBlockStripping:
    def test_complete_json_strips_think_blocks(self):
        """complete_json strips <think>…</think> before JSON parsing."""
        import asyncio
        from unittest.mock import AsyncMock, patch

        from app.services.claude_client import ClaudeClient

        raw = '<think>Let me think about this carefully.</think>\n{"key": "value"}'
        mock_response = MagicMock()
        mock_response.content = raw

        async def run():
            client = ClaudeClient()
            with patch(
                "app.services.claude_client.get_json_model",
                return_value=MagicMock(ainvoke=AsyncMock(return_value=mock_response)),
            ):
                result = await client.complete_json("system", "user")
            return result

        result = asyncio.get_event_loop().run_until_complete(run())
        assert result == {"key": "value"}
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_tools/test_llm_factory.py::TestLlamaCppProvider -v 2>&1 | tail -20
```
Expected: `FAILED` — `_build_model` has no llamacpp branch yet.

- [ ] **Step 3: Add llamacpp branch to `_build_model` in llm_factory.py**

Open `backend/app/agents/tools/llm_factory.py`. Replace the `_build_model` function with:

```python
def _build_model(model_name: str, llm_cfg: Any) -> BaseChatModel:
    """Instantiate a LangChain chat model from profile LLM config."""
    if not model_name:
        raise ValueError(
            f"LLM model name is empty for provider '{llm_cfg.provider}'. "
            "Set triage_model / primary_model in profile.yaml → llm section."
        )

    # llamacpp exposes an OpenAI-compatible API — use ChatOpenAI directly
    if llm_cfg.provider == "llamacpp":
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        return ChatOpenAI(
            model=model_name,
            openai_api_base=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
        )

    provider = llm_cfg.provider

    kwargs: dict[str, Any] = {
        "temperature": llm_cfg.temperature,
        "max_retries": llm_cfg.max_retries,
    }

    if llm_cfg.api_key_env:
        api_key = os.getenv(llm_cfg.api_key_env, "")
        if api_key:
            kwargs["api_key"] = api_key

    if llm_cfg.base_url:
        kwargs["base_url"] = llm_cfg.base_url

    return init_chat_model(
        model=model_name,
        model_provider=provider,
        **kwargs,
    )
```

- [ ] **Step 4: Add llamacpp branch to `get_json_model` in llm_factory.py**

Find the `get_json_model` function. After the `if llm_cfg.provider == "ollama":` block and before the final `return _build_model(...)`, insert:

```python
    if llm_cfg.provider == "llamacpp":
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        return ChatOpenAI(
            model=llm_cfg.primary_model,
            openai_api_base=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
```

So `get_json_model` reads:
```python
def get_json_model() -> BaseChatModel:
    profile = load_profile()
    llm_cfg = profile.llm
    if llm_cfg.provider == "ollama":
        # ... existing ollama block unchanged ...
        kwargs: dict[str, Any] = {
            "temperature": llm_cfg.temperature,
            "max_retries": llm_cfg.max_retries,
            "format": "json",
        }
        if llm_cfg.base_url:
            kwargs["base_url"] = llm_cfg.base_url
        return init_chat_model(
            model=llm_cfg.primary_model,
            model_provider="ollama",
            **kwargs,
        )
    if llm_cfg.provider == "llamacpp":
        from langchain_openai import ChatOpenAI  # noqa: PLC0415
        return ChatOpenAI(
            model=llm_cfg.primary_model,
            openai_api_base=llm_cfg.base_url,
            openai_api_key="not-required",
            temperature=llm_cfg.temperature,
            max_retries=llm_cfg.max_retries,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _build_model(llm_cfg.primary_model, llm_cfg)
```

- [ ] **Step 5: Add think-block stripping in claude_client.py**

Open `backend/app/services/claude_client.py`. In `complete_json`, after retrieving `text` from the response, add the strip before the `cleaned = text.strip()` line:

```python
    async def complete_json(
        self,
        system: str,
        user: str,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                llm = get_json_model()
                messages = [SystemMessage(content=system + _JSON_INSTRUCTION), HumanMessage(content=user)]
                response = await llm.ainvoke(messages)
                text = response.content if isinstance(response.content, str) else str(response.content)
                # Strip Qwen3 / DeepSeek reasoning blocks before JSON parsing
                import re  # noqa: PLC0415
                text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
                cleaned = text.strip()
                if cleaned.startswith("```"):
                    lines = cleaned.split("\n")
                    cleaned = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                    if match:
                        return json.loads(match.group())
                    raise
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning("JSON parse failed (attempt %d/3): %s", attempt + 1, exc)

        raise ValueError(f"LLM did not return valid JSON after 3 attempts: {last_error}")
```

Move the `import re` to the top of the file instead of the inline import. Open `claude_client.py`, find the existing imports, and add `import re` if not already present.

- [ ] **Step 6: Run all tests to confirm passing**

```bash
cd backend && python -m pytest tests/test_tools/test_llm_factory.py -v 2>&1 | tail -20
```
Expected: All tests in `TestLlamaCppProvider` and `TestThinkBlockStripping` pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/agents/tools/llm_factory.py backend/app/services/claude_client.py backend/tests/test_tools/test_llm_factory.py
git commit -m "feat: add llamacpp provider to llm_factory + strip think-blocks in claude_client"
```

---

### Task 3: Update profile.yaml to llamacpp provider

**Files:**
- Modify: `data/profile.yaml`

No unit test for this task — verified by smoke-testing the running container.

- [ ] **Step 1: Update data/profile.yaml**

Open `data/profile.yaml`. Find the `llm:` section and replace it with:

```yaml
llm:
  provider: llamacpp
  base_url: http://llamacpp:8080/v1
  primary_model: Qwen3-14B-Instruct
  triage_model: Qwen3-14B-Instruct
  api_key_env: ''
  temperature: 0.3
  max_retries: 2
  track_costs: true
  monthly_budget: 15.0
  currency: USD
```

- [ ] **Step 2: Download the model (first time only)**

```bash
./scripts/download-models.sh
```
Expected: `Done. Run 'podman-compose up' to start all services.` (or "already present" if previously downloaded).

- [ ] **Step 3: Start the llamacpp container and verify health**

```bash
podman-compose up llamacpp -d
sleep 10
curl -s http://localhost:8080/health | python3 -m json.tool
```
Expected output contains `{"status": "ok"}`.

- [ ] **Step 4: Smoke-test JSON output**

```bash
curl -s http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen3-14B-Instruct",
    "messages": [{"role": "user", "content": "Return JSON: {\"ok\": true}"}],
    "response_format": {"type": "json_object"},
    "max_tokens": 50
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print(r['choices'][0]['message']['content'])"
```
Expected: A string containing valid JSON like `{"ok": true}`.

- [ ] **Step 5: Commit**

```bash
git add data/profile.yaml
git commit -m "feat: switch LLM provider to llamacpp + Qwen3-14B-Q4_K_M"
```

---

## Phase B — Async Job Layer + Frontend

---

### Task 4: AsyncJob SQLAlchemy model + database registration

**Files:**
- Create: `backend/app/models/async_job.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/database.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_models/` directory if it doesn't exist, then create `backend/tests/test_models/test_async_job.py`:

```python
"""Tests for AsyncJob model."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.async_job import AsyncJob


@pytest.mark.asyncio
async def test_async_job_created_with_pending_status(db_session):
    """AsyncJob defaults to status=pending on creation."""
    job = AsyncJob(type="tailor_analyse")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.id is not None
    assert job.status == "pending"
    assert job.result_json is None
    assert job.error is None
    assert job.created_at is not None
    assert job.updated_at is not None


@pytest.mark.asyncio
async def test_async_job_type_stored_correctly(db_session):
    """AsyncJob.type is persisted and retrieved correctly."""
    job = AsyncJob(type="coach_session")
    db_session.add(job)
    await db_session.commit()

    result = await db_session.execute(select(AsyncJob).where(AsyncJob.id == job.id))
    fetched = result.scalar_one()
    assert fetched.type == "coach_session"
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_models/test_async_job.py -v 2>&1 | tail -10
```
Expected: `ModuleNotFoundError: No module named 'app.models.async_job'`

- [ ] **Step 3: Create backend/app/models/async_job.py**

```python
"""AsyncJob — persisted record for background LLM jobs."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


def _new_uuid() -> str:
    return str(uuid.uuid4())


class AsyncJob(Base):
    """Background LLM job — created immediately, result written when done."""

    __tablename__ = "async_jobs"
    __table_args__ = (
        Index("idx_async_jobs_status_type", "status", "type"),
        Index("idx_async_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
```

- [ ] **Step 4: Register AsyncJob in models/__init__.py**

Open `backend/app/models/__init__.py`. Add the import line:
```python
from .async_job import AsyncJob  # noqa: F401
```
Add `"AsyncJob"` to the `__all__` list.

- [ ] **Step 5: Register AsyncJob in database.py init_db**

Open `backend/app/database.py`. In `init_db()`, add the import line alongside the other model imports:
```python
    from .models import async_job as _async_job_models  # noqa: F401
```

- [ ] **Step 6: Run tests to confirm passing**

```bash
cd backend && python -m pytest tests/test_models/test_async_job.py -v 2>&1 | tail -10
```
Expected: Both tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/async_job.py backend/app/models/__init__.py backend/app/database.py backend/tests/test_models/test_async_job.py
git commit -m "feat: add AsyncJob model and register with database"
```

---

### Task 5: AsyncJobService

**Files:**
- Create: `backend/app/services/async_job_service.py`
- Test: `backend/tests/test_services/test_async_job_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_services/test_async_job_service.py`:

```python
"""Tests for AsyncJobService."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from app.models.async_job import AsyncJob
from app.services.async_job_service import AsyncJobService


@pytest.mark.asyncio
async def test_create_returns_pending_job(db_session):
    """AsyncJobService.create persists a pending job and returns it."""
    job = await AsyncJobService.create(db_session, "tailor_analyse")

    assert job.id is not None
    assert job.type == "tailor_analyse"
    assert job.status == "pending"


@pytest.mark.asyncio
async def test_finish_sets_done_status_and_result(db_session):
    """AsyncJobService._finish updates job to done with result_json."""
    job = await AsyncJobService.create(db_session, "tailor_analyse")
    await db_session.commit()

    await AsyncJobService._finish(job.id, '{"key": "value"}', None)

    refreshed = await AsyncJobService.get(db_session, job.id)
    assert refreshed is not None
    assert refreshed.status == "done"
    assert refreshed.result_json == '{"key": "value"}'
    assert refreshed.error is None


@pytest.mark.asyncio
async def test_finish_sets_failed_status_on_error(db_session):
    """AsyncJobService._finish with error=str and no result sets status=failed."""
    job = await AsyncJobService.create(db_session, "coach_session")
    await db_session.commit()

    await AsyncJobService._finish(job.id, None, "LLM timeout")

    refreshed = await AsyncJobService.get(db_session, job.id)
    assert refreshed is not None
    assert refreshed.status == "failed"
    assert refreshed.error == "LLM timeout"
    assert refreshed.result_json is None


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_id(db_session):
    """AsyncJobService.get returns None for a non-existent job ID."""
    result = await AsyncJobService.get(db_session, "no-such-id")
    assert result is None


@pytest.mark.asyncio
async def test_list_completed_since_returns_recent_done_jobs(db_session):
    """list_completed_since returns done jobs created after the given datetime."""
    old_job = await AsyncJobService.create(db_session, "ghost_analyse")
    recent_job = await AsyncJobService.create(db_session, "email_generate")
    await db_session.commit()

    cutoff = datetime.utcnow() - timedelta(seconds=1)

    # Finish both
    await AsyncJobService._finish(old_job.id, '{}', None)
    await AsyncJobService._finish(recent_job.id, '{}', None)

    results = await AsyncJobService.list_completed_since(db_session, cutoff, limit=10)
    ids = [r.id for r in results]
    assert old_job.id in ids
    assert recent_job.id in ids
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_services/test_async_job_service.py -v 2>&1 | tail -10
```
Expected: `ModuleNotFoundError: No module named 'app.services.async_job_service'`

- [ ] **Step 3: Create backend/app/services/async_job_service.py**

```python
"""AsyncJobService — create, run, and poll background LLM jobs."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Coroutine

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.async_job import AsyncJob

logger = logging.getLogger(__name__)


class AsyncJobService:
    """Manages background LLM jobs persisted in the async_jobs table."""

    @staticmethod
    async def create(db: AsyncSession, job_type: str) -> AsyncJob:
        """Persist a new pending job and return it (not yet committed)."""
        job = AsyncJob(type=job_type)
        db.add(job)
        await db.flush()  # populate job.id without committing
        return job

    @staticmethod
    def run(job_id: str, coro: Coroutine[Any, Any, None]) -> None:
        """Fire-and-forget: wrap coro in a task that sets status=running first."""

        async def _run_and_track() -> None:
            from ..database import AsyncSessionLocal  # noqa: PLC0415
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(AsyncJob)
                    .where(AsyncJob.id == job_id)
                    .values(status="running", updated_at=datetime.utcnow())
                )
                await db.commit()
            try:
                await coro
            except Exception as exc:
                logger.exception("Unhandled error in async job %s: %s", job_id, exc)
                await AsyncJobService._finish(job_id, None, str(exc))

        asyncio.create_task(_run_and_track())

    @staticmethod
    async def _finish(
        job_id: str, result_json: str | None, error: str | None
    ) -> None:
        """Open a fresh DB session and persist the final status.

        Called from inside background coroutines where the request
        session is already closed.
        """
        from ..database import AsyncSessionLocal  # noqa: PLC0415
        status = "done" if result_json is not None else "failed"
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(AsyncJob)
                .where(AsyncJob.id == job_id)
                .values(
                    status=status,
                    result_json=result_json,
                    error=error,
                    updated_at=datetime.utcnow(),
                )
            )
            await db.commit()
        logger.info("AsyncJob %s → %s", job_id, status)

    @staticmethod
    async def get(db: AsyncSession, job_id: str) -> AsyncJob | None:
        """Return a job by ID, or None if not found."""
        result = await db.execute(
            select(AsyncJob).where(AsyncJob.id == job_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_completed_since(
        db: AsyncSession, since: datetime, limit: int = 20
    ) -> list[AsyncJob]:
        """Return done jobs created after `since`, newest first."""
        result = await db.execute(
            select(AsyncJob)
            .where(AsyncJob.status == "done", AsyncJob.created_at >= since)
            .order_by(AsyncJob.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
cd backend && python -m pytest tests/test_services/test_async_job_service.py -v 2>&1 | tail -15
```
Expected: All 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/async_job_service.py backend/tests/test_services/test_async_job_service.py
git commit -m "feat: add AsyncJobService with create/run/_finish/get/list"
```

---

### Task 6: async_jobs router + main.py wiring

**Files:**
- Create: `backend/app/routers/async_jobs.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routers/test_async_jobs_router.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_routers/test_async_jobs_router.py`:

```python
"""Tests for async_jobs router."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.async_job_service import AsyncJobService


@pytest.mark.asyncio
async def test_get_async_job_returns_job(db_session):
    """GET /api/async-jobs/{id} returns the job as JSON."""
    job = await AsyncJobService.create(db_session, "tailor_analyse")
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/async-jobs/{job.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == job.id
    assert data["type"] == "tailor_analyse"
    assert data["status"] == "pending"
    assert data["result"] is None
    assert data["error"] is None


@pytest.mark.asyncio
async def test_get_async_job_returns_404_for_unknown(_):
    """GET /api/async-jobs/{id} returns 404 for a non-existent job."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/async-jobs/no-such-id")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_async_jobs_returns_done_jobs(db_session):
    """GET /api/async-jobs?status=done returns completed jobs."""
    job = await AsyncJobService.create(db_session, "email_generate")
    await db_session.commit()
    await AsyncJobService._finish(job.id, '{"subject": "Hi"}', None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/async-jobs?status=done&limit=5")

    assert response.status_code == 200
    items = response.json()
    assert any(item["id"] == job.id for item in items)
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_routers/test_async_jobs_router.py -v 2>&1 | tail -10
```
Expected: `404 Not Found` or routing error — the router doesn't exist yet.

- [ ] **Step 3: Create backend/app/routers/async_jobs.py**

```python
"""Router for polling background LLM jobs."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.async_job_service import AsyncJobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/async-jobs", tags=["async-jobs"])


class AsyncJobRead(BaseModel):
    id: str
    type: str
    status: str
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: datetime


def _to_read(job) -> AsyncJobRead:  # type: ignore[no-untyped-def]
    result = None
    if job.result_json:
        try:
            result = json.loads(job.result_json)
        except Exception:
            result = job.result_json
    return AsyncJobRead(
        id=job.id,
        type=job.type,
        status=job.status,
        result=result,
        error=job.error,
        created_at=job.created_at,
    )


@router.get("/{job_id}", response_model=AsyncJobRead)
async def get_async_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> AsyncJobRead:
    """Return the current status and result of a background job."""
    job = await AsyncJobService.get(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_read(job)


@router.get("", response_model=list[AsyncJobRead])
async def list_async_jobs(
    status: str = Query("done"),
    since: Optional[str] = Query(None, description="ISO-8601 datetime; defaults to 24h ago"),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> list[AsyncJobRead]:
    """List background jobs, filtered by status. Used by the notification bell."""
    if since:
        since_dt = datetime.fromisoformat(since)
    else:
        since_dt = datetime.utcnow() - timedelta(hours=24)

    jobs = await AsyncJobService.list_completed_since(db, since_dt, limit=limit)
    return [_to_read(j) for j in jobs]
```

- [ ] **Step 4: Register async_jobs router in main.py**

Open `backend/app/main.py`. Add the import at the top with the other router imports:
```python
from .routers.async_jobs import router as async_jobs_router
```

In `create_app()`, add the router registration with the other `app.include_router` calls:
```python
    app.include_router(async_jobs_router)
```

- [ ] **Step 5: Run tests to confirm passing**

```bash
cd backend && python -m pytest tests/test_routers/test_async_jobs_router.py -v 2>&1 | tail -15
```
Expected: All 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/async_jobs.py backend/app/main.py backend/tests/test_routers/test_async_jobs_router.py
git commit -m "feat: add async_jobs router and register in main.py"
```

---

### Task 7: Migrate tailor router — 5 endpoints to 202

**Files:**
- Modify: `backend/app/routers/tailor.py`
- Test: `backend/tests/test_routers/test_tailor_async.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_routers/test_tailor_async.py`:

```python
"""Tests that tailor endpoints return 202 + job_id instead of blocking."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

from app.main import app


@pytest.mark.asyncio
async def test_analyse_jd_text_returns_202(_):
    """POST /api/tailor/analyse returns 202 with job_id immediately."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/tailor/analyse",
            params={"job_description": "Senior Python developer role in London"},
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "pending"
    assert data["type"] == "tailor_analyse"


@pytest.mark.asyncio
async def test_generate_cv_returns_202(_):
    """POST /api/tailor/generate-cv returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/tailor/generate-cv",
            json={
                "application_id": "test-app-id",
                "variant": "A",
                "jd_text": "Senior Python developer",
            },
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "tailor_generate_cv"


@pytest.mark.asyncio
async def test_generate_cl_returns_202(_):
    """POST /api/tailor/generate-cl returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/tailor/generate-cl",
            json={
                "application_id": "test-app-id",
                "variant": "A",
                "jd_text": "Senior Python developer",
            },
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "tailor_generate_cl"


@pytest.mark.asyncio
async def test_generate_all_returns_202(_):
    """POST /api/tailor/generate returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/tailor/generate",
            json={
                "application_id": "test-app-id",
                "variant": "A",
                "jd_text": "Senior Python developer",
            },
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "tailor_generate"
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_routers/test_tailor_async.py -v 2>&1 | tail -10
```
Expected: `FAILED` — endpoints return 200/201/422, not 202.

- [ ] **Step 3: Rewrite the 5 tailor endpoints in tailor.py**

Open `backend/app/routers/tailor.py`. Replace the four async endpoint functions (not the stream endpoint) as follows. Add the import at the top:

```python
from ..services.async_job_service import AsyncJobService
```

Replace `analyse_jd_text` (the `POST /analyse` endpoint — no job_id param):

```python
@router.post("/analyse", status_code=202)
async def analyse_jd_text(
    job_description: str = Query(..., description="Raw JD text to analyse"),
    job_url: Optional[str] = Query(None, description="Optional URL to fetch JD from"),
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off JD analysis as a background job. Poll /api/async-jobs/{job_id} for result."""
    job = await AsyncJobService.create(db, "tailor_analyse")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.analyse_jd_text(job_description, job_url)
            await AsyncJobService._finish(job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(job.id, None, str(exc))

    AsyncJobService.run(job.id, _work())
    return {"job_id": job.id, "status": "pending", "type": "tailor_analyse"}
```

Replace `analyse_job` (the `POST /analyse/{job_id}` endpoint):

```python
@router.post("/analyse/{job_id}", status_code=202)
async def analyse_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off JD analysis for a saved job posting. Poll /api/async-jobs/{job_id} for result."""
    async_job = await AsyncJobService.create(db, "tailor_analyse")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.analyse_job(job_id, db)
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_analyse"}
```

Replace `generate_cv`:

```python
@router.post("/generate-cv", status_code=202)
async def generate_cv(
    request: TailorRequest,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off CV generation. Poll /api/async-jobs/{job_id} for result."""
    jd_text = request.model_extra.get("jd_text", "")
    if not jd_text:
        raise HTTPException(status_code=422, detail="jd_text is required")

    async_job = await AsyncJobService.create(db, "tailor_generate_cv")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.generate_cv(
                request.application_id,
                request.variant,
                jd_text,
                db,
                request.custom_instructions,
            )
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_generate_cv"}
```

Replace `generate_cover_letter`:

```python
@router.post("/generate-cl", status_code=202)
async def generate_cover_letter(
    request: TailorRequest,
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off cover letter generation. Poll /api/async-jobs/{job_id} for result."""
    jd_text = request.model_extra.get("jd_text", "")
    async_job = await AsyncJobService.create(db, "tailor_generate_cl")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.generate_cover_letter(
                request.application_id, request.variant, jd_text, db
            )
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_generate_cl"}
```

Replace `generate_all`:

```python
@router.post("/generate", status_code=202)
async def generate_all(
    request: TailorRequest,
    generate_variants: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    svc: TailorService = Depends(get_tailor_service),
) -> dict:
    """Kick off full pipeline (JD + CV + CL). Poll /api/async-jobs/{job_id} for result."""
    jd_text = request.model_extra.get("jd_text", "")
    async_job = await AsyncJobService.create(db, "tailor_generate")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.generate_all(
                request.application_id, request.variant, jd_text, db, generate_variants
            )
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "tailor_generate"}
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
cd backend && python -m pytest tests/test_routers/test_tailor_async.py -v 2>&1 | tail -15
```
Expected: All 4 tests pass.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
cd backend && python -m pytest -q 2>&1 | tail -5
```
Expected: No new failures.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/tailor.py backend/tests/test_routers/test_tailor_async.py
git commit -m "feat: migrate tailor endpoints to async 202 pattern"
```

---

### Task 8: Migrate coach router — 4 endpoints to 202

**Files:**
- Modify: `backend/app/routers/coach.py`
- Test: `backend/tests/test_routers/test_coach_async.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_routers/test_coach_async.py`:

```python
"""Tests that coach endpoints return 202 + job_id."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.async_job_service import AsyncJobService


@pytest.mark.asyncio
async def test_create_session_returns_202(_):
    """POST /api/coach/sessions returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/coach/sessions",
            json={
                "company_name": "Acme Corp",
                "role_title": "Senior Developer",
                "config": {
                    "question_count": 5,
                    "categories": ["Technical"],
                    "recording_mode": "text",
                    "difficulty": "medium",
                },
            },
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "coach_session"


@pytest.mark.asyncio
async def test_submit_answer_returns_202(db_session):
    """POST /api/coach/sessions/{id}/submit-answer returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/coach/sessions/fake-session-id/submit-answer",
            params={"question_id": "fake-q-id"},
            json={"transcript": "I led a team of five engineers...", "duration_ms": 45000},
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "submit_answer"


@pytest.mark.asyncio
async def test_end_session_returns_202(_):
    """POST /api/coach/sessions/{id}/end returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/coach/sessions/fake-session-id/end")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "end_session"
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_routers/test_coach_async.py -v 2>&1 | tail -10
```
Expected: `FAILED` — endpoints return 201/200, not 202.

- [ ] **Step 3: Rewrite the 4 coach endpoints in coach.py**

Open `backend/app/routers/coach.py`. Add the import:
```python
from ..services.async_job_service import AsyncJobService
```

Replace `create_session`:

```python
@router.post("/sessions", status_code=202)
async def create_session(
    request: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Kick off session creation (question generation). Poll /api/async-jobs/{job_id}."""
    async_job = await AsyncJobService.create(db, "coach_session")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.create_session(request, db)
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            logger.error("create_session job %s failed: %s", async_job.id, exc)
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "coach_session"}
```

Replace `submit_answer`:

```python
@router.post("/sessions/{session_id}/submit-answer", status_code=202)
async def submit_answer(
    session_id: str,
    question_id: str = Query(...),
    request: SubmitAnswerRequest = ...,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Kick off answer evaluation. Poll /api/async-jobs/{job_id} for scores + feedback."""
    async_job = await AsyncJobService.create(db, "submit_answer")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.submit_answer(session_id, question_id, request, db)
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            logger.error("submit_answer job %s failed: %s", async_job.id, exc)
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "submit_answer"}
```

Replace `end_session`:

```python
@router.post("/sessions/{session_id}/end", status_code=202)
async def end_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    svc: CoachService = Depends(get_coach_service),
) -> dict:
    """Kick off feedback report generation. Poll /api/async-jobs/{job_id} for report."""
    async_job = await AsyncJobService.create(db, "end_session")
    await db.commit()

    async def _work() -> None:
        try:
            result = await svc.end_session(session_id, db)
            await AsyncJobService._finish(async_job.id, result.model_dump_json(), None)
        except Exception as exc:
            logger.error("end_session job %s failed: %s", async_job.id, exc)
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "end_session"}
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
cd backend && python -m pytest tests/test_routers/test_coach_async.py -v 2>&1 | tail -15
```
Expected: All 3 tests pass.

- [ ] **Step 5: Run full suite**

```bash
cd backend && python -m pytest -q 2>&1 | tail -5
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/coach.py backend/tests/test_routers/test_coach_async.py
git commit -m "feat: migrate coach endpoints to async 202 pattern"
```

---

### Task 9: Migrate emails + ghost routers to 202

**Files:**
- Modify: `backend/app/routers/emails.py`
- Modify: `backend/app/routers/ghost.py`
- Test: `backend/tests/test_routers/test_emails_ghost_async.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_routers/test_emails_ghost_async.py`:

```python
"""Tests that emails/generate and ghost/analyse return 202."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_generate_email_returns_202(_):
    """POST /api/emails/generate/{id} returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/emails/generate/fake-app-id",
            json={"email_type": "post_application"},
        )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "email_generate"


@pytest.mark.asyncio
async def test_analyse_ghost_returns_202(_):
    """POST /api/ghost/analyse/{job_id} returns 202 with job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/ghost/analyse/fake-job-id")
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["type"] == "ghost_analyse"
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd backend && python -m pytest tests/test_routers/test_emails_ghost_async.py -v 2>&1 | tail -10
```
Expected: `FAILED` — both endpoints return non-202.

- [ ] **Step 3: Migrate generate_email in emails.py**

Open `backend/app/routers/emails.py`. Add the import:
```python
from ..services.async_job_service import AsyncJobService
```

Replace the `generate_email` function (lines starting at `@router.post("/generate/{application_id}"`):

```python
@router.post("/generate/{application_id}", status_code=202)
async def generate_email(
    application_id: str,
    body: EmailGenerateRequest,
    db: AsyncSession = Depends(get_db),
    generator: EmailGenerator = Depends(_get_email_generator),
) -> dict:
    """Kick off email generation. Poll /api/async-jobs/{job_id} for the draft."""
    async_job = await AsyncJobService.create(db, "email_generate")
    await db.commit()

    email_type = body.email_type

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415
        from ..models.application import Application, InterviewRound  # noqa: PLC0415
        from ..models.job import JobPosting  # noqa: PLC0415
        from datetime import datetime as dt  # noqa: PLC0415
        from sqlalchemy import select as sa_select  # noqa: PLC0415

        try:
            async with AsyncSessionLocal() as own_db:
                app_result = await own_db.execute(
                    sa_select(Application).where(Application.id == application_id)
                )
                application = app_result.scalars().first()
                if not application:
                    await AsyncJobService._finish(async_job.id, None, "Application not found")
                    return
                if not application.job_id:
                    await AsyncJobService._finish(async_job.id, None, "Application has no linked job")
                    return

                job_result = await own_db.execute(
                    sa_select(JobPosting).where(JobPosting.id == application.job_id)
                )
                job = job_result.scalars().first()
                if not job:
                    await AsyncJobService._finish(async_job.id, None, "Job not found")
                    return

                now = dt.utcnow()
                days_since = (
                    (now - application.applied_date).days if application.applied_date
                    else (now - application.created_at).days
                )

                if email_type == "post_application":
                    generated = await generator.generate_post_application(application, job, days_since)
                elif email_type == "post_interview_thankyou":
                    iv_result = await own_db.execute(
                        sa_select(InterviewRound)
                        .where(
                            InterviewRound.application_id == application_id,
                            InterviewRound.status == "completed",
                        )
                        .order_by(InterviewRound.updated_at.desc())
                    )
                    interview = iv_result.scalars().first()
                    if interview:
                        generated = await generator.generate_post_interview_thankyou(
                            application, job, interview
                        )
                    else:
                        generated = await generator.generate_warm_reengagement(
                            application, job, days_since
                        )
                elif email_type == "warm_reengagement":
                    generated = await generator.generate_warm_reengagement(application, job, days_since)
                else:
                    await AsyncJobService._finish(async_job.id, None, f"Unknown email_type: {email_type}")
                    return

                draft = generator.save_draft(
                    email=generated,
                    application=application,
                    generation_params={"email_type": email_type, "triggered_by": "manual"},
                )
                own_db.add(draft)
                await own_db.commit()
                await own_db.refresh(draft)

                enriched = await _enrich(draft, own_db)
                await AsyncJobService._finish(async_job.id, enriched.model_dump_json(), None)

        except Exception as exc:
            logger.error("email_generate job %s failed: %s", async_job.id, exc)
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "email_generate"}
```

- [ ] **Step 4: Migrate analyse_job in ghost.py**

Open `backend/app/routers/ghost.py`. Add the import:
```python
from ..services.async_job_service import AsyncJobService
```

Replace `analyse_job` (the `@router.post("/analyse/{job_id}")` function):

```python
@router.post("/analyse/{job_id}", status_code=202)
async def analyse_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kick off ghost detection for a job. Poll /api/async-jobs/{async_job_id} for result."""
    async_job = await AsyncJobService.create(db, "ghost_analyse")
    await db.commit()

    async def _work() -> None:
        from ..database import AsyncSessionLocal  # noqa: PLC0415
        from sqlalchemy import select as sa_select  # noqa: PLC0415
        from ..models.job import JobPosting  # noqa: PLC0415

        try:
            async with AsyncSessionLocal() as own_db:
                result = await own_db.execute(
                    sa_select(JobPosting).where(
                        JobPosting.id == job_id, JobPosting.is_active == True  # noqa: E712
                    )
                )
                job = result.scalar_one_or_none()
                if job is None:
                    await AsyncJobService._finish(async_job.id, None, "Job not found")
                    return

                score = await detector.analyse_job(job, own_db)
                await AsyncJobService._finish(async_job.id, score.model_dump_json(), None)

        except Exception as exc:
            logger.error("ghost_analyse job %s failed: %s", async_job.id, exc)
            await AsyncJobService._finish(async_job.id, None, str(exc))

    AsyncJobService.run(async_job.id, _work())
    return {"job_id": async_job.id, "status": "pending", "type": "ghost_analyse"}
```

- [ ] **Step 5: Run tests to confirm passing**

```bash
cd backend && python -m pytest tests/test_routers/test_emails_ghost_async.py -v 2>&1 | tail -15
```
Expected: Both tests pass.

- [ ] **Step 6: Run full suite**

```bash
cd backend && python -m pytest -q 2>&1 | tail -5
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/emails.py backend/app/routers/ghost.py backend/tests/test_routers/test_emails_ghost_async.py
git commit -m "feat: migrate emails/generate and ghost/analyse to async 202 pattern"
```

---

### Task 10: Frontend api.ts — async job types + updated POST functions

**Files:**
- Modify: `frontend/src/lib/api.ts`

No dedicated test file — the type changes are verified by TypeScript compilation and by the hook tests in Task 11.

- [ ] **Step 1: Add AsyncJobRef and AsyncJobResponse types to api.ts**

Open `frontend/src/lib/api.ts`. Find the block `// ── Agentic pipeline ──` near the bottom. Before that block, add:

```typescript
// ──────────────────────── Async Jobs ────────────────────────

export interface AsyncJobRef {
  job_id: string
  status: "pending"
  type: string
}

export interface AsyncJobResponse<T = unknown> {
  id: string
  type: string
  status: "pending" | "running" | "done" | "failed"
  result: T | null
  error: string | null
  created_at: string
}

export async function getAsyncJob<T = unknown>(
  jobId: string
): Promise<AsyncJobResponse<T>> {
  return apiFetch<AsyncJobResponse<T>>(`/api/async-jobs/${jobId}`)
}

export async function listCompletedJobs(
  since: string,
  limit = 20
): Promise<AsyncJobResponse[]> {
  const params = buildQueryString({ status: "done", since, limit })
  return apiFetch<AsyncJobResponse[]>(`/api/async-jobs${params}`)
}
```

- [ ] **Step 2: Update analyseJdText to return AsyncJobRef**

Find `export async function analyseJdText(` in `api.ts`. Change:
```typescript
export async function analyseJdText(
  jobDescription: string,
  jobUrl?: string,
): Promise<JDAnalysisResponse> {
  const params = new URLSearchParams({ job_description: jobDescription });
  if (jobUrl) params.set("job_url", jobUrl);
  return apiFetch<JDAnalysisResponse>(`/api/tailor/analyse?${params}`, { method: "POST" });
}
```
To:
```typescript
export async function analyseJdText(
  jobDescription: string,
  jobUrl?: string,
): Promise<AsyncJobRef> {
  const params = new URLSearchParams({ job_description: jobDescription });
  if (jobUrl) params.set("job_url", jobUrl);
  return apiFetch<AsyncJobRef>(`/api/tailor/analyse?${params}`, { method: "POST" });
}
```

- [ ] **Step 3: Update analyseJob to return AsyncJobRef**

Find `export async function analyseJob(`. Change return type from `Promise<JDAnalysisResponse>` to `Promise<AsyncJobRef>` and response type from `JDAnalysisResponse` to `AsyncJobRef`.

- [ ] **Step 4: Update generateAll, generateCV, generateCL to return AsyncJobRef**

Apply the same pattern — change `Promise<TailorResultBundle>` → `Promise<AsyncJobRef>`, `Promise<GeneratedDocument>` → `Promise<AsyncJobRef>` for each function.

- [ ] **Step 5: Update createSession to return AsyncJobRef**

Find `export async function createSession(`. Change:
```typescript
export async function createSession(
  request: CreateSessionRequest
): Promise<SessionResponse> {
  return apiFetch<SessionResponse>("/api/coach/sessions", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
```
To:
```typescript
export async function createSession(
  request: CreateSessionRequest
): Promise<AsyncJobRef> {
  return apiFetch<AsyncJobRef>("/api/coach/sessions", {
    method: "POST",
    body: JSON.stringify(request),
  });
}
```

- [ ] **Step 6: Update submitAnswer, endSession, generateEmail to return AsyncJobRef**

`submitAnswer` → `Promise<AsyncJobRef>` (was `Promise<AnswerEvaluation>`)
`endSession` → `Promise<AsyncJobRef>` (was `Promise<SessionFeedbackReport>`)
`generateEmail` → `Promise<AsyncJobRef>` (was `Promise<FollowUpEmailRead>`)

- [ ] **Step 7: Add also analyseGhostJob to return AsyncJobRef**

Find `export async function analyseGhostJob(`. Change return type from `Promise<GhostScore>` to `Promise<AsyncJobRef>` and the `apiFetch` generic accordingly.

- [ ] **Step 8: Verify TypeScript compiles cleanly**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: Errors only from files that still use the old return types (tailor/page.tsx and SessionLauncher.tsx — these are fixed in Tasks 13 and 14). No errors inside api.ts itself.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: update api.ts POST functions to return AsyncJobRef"
```

---

### Task 11: useAsyncJob hook

**Files:**
- Create: `frontend/src/hooks/useAsyncJob.ts`
- Test: `frontend/src/__tests__/hooks/useAsyncJob.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/__tests__/hooks/useAsyncJob.test.ts`:

```typescript
import { renderHook, act, waitFor } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach, afterEach } from "vitest";
import { useAsyncJob } from "@/hooks/useAsyncJob";

const mockFetch = vi.fn();
global.fetch = mockFetch;

function makeJobResponse(status: string, result: unknown = null) {
  return {
    ok: true,
    json: async () => ({
      id: "job-123",
      type: "tailor_analyse",
      status,
      result,
      error: null,
      created_at: new Date().toISOString(),
    }),
  };
}

describe("useAsyncJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockFetch.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("starts idle, transitions to pending after submit", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
      })
      .mockResolvedValue(makeJobResponse("running"));

    const { result } = renderHook(() => useAsyncJob());

    expect(result.current.state.status).toBe("idle");

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    expect(result.current.state.status).toBe("running");
    expect(result.current.state.jobId).toBe("job-123");
  });

  it("transitions to done when poll returns status=done", async () => {
    const resultData = { analysis: { role_title: "Dev" } };
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
      })
      .mockResolvedValueOnce(makeJobResponse("running"))
      .mockResolvedValueOnce(makeJobResponse("done", resultData));

    const onComplete = vi.fn();
    const { result } = renderHook(() => useAsyncJob({ onComplete }));

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    // Advance timer to trigger second poll
    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.state.status).toBe("done"));
    expect(result.current.state.result).toEqual(resultData);
    expect(onComplete).toHaveBeenCalledWith(resultData);
  });

  it("transitions to failed when poll returns status=failed", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          id: "job-123",
          type: "tailor_analyse",
          status: "failed",
          result: null,
          error: "LLM timeout",
          created_at: new Date().toISOString(),
        }),
      });

    const onError = vi.fn();
    const { result } = renderHook(() => useAsyncJob({ onError }));

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    await act(async () => {
      vi.advanceTimersByTime(3000);
      await Promise.resolve();
    });

    await waitFor(() => expect(result.current.state.status).toBe("failed"));
    expect(result.current.state.error).toBe("LLM timeout");
    expect(onError).toHaveBeenCalledWith("LLM timeout");
  });

  it("reset returns state to idle", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ job_id: "job-123", status: "pending", type: "tailor_analyse" }),
    });

    const { result } = renderHook(() => useAsyncJob());

    await act(async () => {
      await result.current.submit(() =>
        fetch("/api/tailor/analyse", { method: "POST" }).then((r) => r.json())
      );
    });

    act(() => {
      result.current.reset();
    });

    expect(result.current.state.status).toBe("idle");
    expect(result.current.state.jobId).toBeNull();
  });
});
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd frontend && npx vitest run src/__tests__/hooks/useAsyncJob.test.ts 2>&1 | tail -10
```
Expected: `Cannot find module '@/hooks/useAsyncJob'`

- [ ] **Step 3: Create frontend/src/hooks/useAsyncJob.ts**

```typescript
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAsyncJob, AsyncJobResponse } from "@/lib/api";

export interface AsyncJobState<T> {
  jobId: string | null;
  status: "idle" | "pending" | "running" | "done" | "failed";
  result: T | null;
  error: string | null;
}

interface UseAsyncJobOptions<T> {
  pollIntervalMs?: number;
  onComplete?: (result: T) => void;
  onError?: (err: string) => void;
}

export function useAsyncJob<T = unknown>(options?: UseAsyncJobOptions<T>) {
  const { pollIntervalMs = 3000, onComplete, onError } = options ?? {};

  const [state, setState] = useState<AsyncJobState<T>>({
    jobId: null,
    status: "idle",
    result: null,
    error: null,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIdRef = useRef<string | null>(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const poll = useCallback(async () => {
    const jobId = jobIdRef.current;
    if (!jobId) return;

    try {
      const job = await getAsyncJob<T>(jobId);
      setState((prev) => ({ ...prev, status: job.status as AsyncJobState<T>["status"] }));

      if (job.status === "done") {
        stopPolling();
        setState((prev) => ({ ...prev, result: job.result }));
        onComplete?.(job.result as T);
      } else if (job.status === "failed") {
        stopPolling();
        setState((prev) => ({ ...prev, error: job.error }));
        onError?.(job.error ?? "Job failed");
      }
    } catch {
      // Network error during poll — keep trying
    }
  }, [stopPolling, onComplete, onError]);

  const submit = useCallback(
    async (postFn: () => Promise<{ job_id: string }>) => {
      stopPolling();
      setState({ jobId: null, status: "pending", result: null, error: null });

      try {
        const ref = await postFn();
        jobIdRef.current = ref.job_id;
        setState((prev) => ({ ...prev, jobId: ref.job_id, status: "pending" }));

        // First poll immediately, then on interval
        await poll();
        intervalRef.current = setInterval(() => void poll(), pollIntervalMs);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Request failed";
        setState({ jobId: null, status: "failed", result: null, error: msg });
        onError?.(msg);
      }
    },
    [stopPolling, poll, pollIntervalMs, onError]
  );

  const reset = useCallback(() => {
    stopPolling();
    jobIdRef.current = null;
    setState({ jobId: null, status: "idle", result: null, error: null });
  }, [stopPolling]);

  // Cleanup on unmount
  useEffect(() => () => stopPolling(), [stopPolling]);

  return { state, submit, reset };
}
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
cd frontend && npx vitest run src/__tests__/hooks/useAsyncJob.test.ts 2>&1 | tail -15
```
Expected: All 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useAsyncJob.ts frontend/src/__tests__/hooks/useAsyncJob.test.ts
git commit -m "feat: add useAsyncJob polling hook"
```

---

### Task 12: NotificationBell component + Navigation wiring

**Files:**
- Create: `frontend/src/components/NotificationBell.tsx`
- Modify: `frontend/src/components/Navigation.tsx`
- Test: `frontend/src/__tests__/components/NotificationBell.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/__tests__/components/NotificationBell.test.tsx`:

```typescript
import { render, screen, act } from "@testing-library/react";
import { vi, describe, it, expect, beforeEach } from "vitest";
import { NotificationBell } from "@/components/NotificationBell";

const mockFetch = vi.fn();
global.fetch = mockFetch;

function makeCompletedJobs(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    id: `job-${i}`,
    type: "tailor_analyse",
    status: "done",
    result: null,
    error: null,
    created_at: new Date().toISOString(),
  }));
}

describe("NotificationBell", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    localStorage.clear();
  });

  it("shows no badge when there are no completed jobs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [],
    });

    await act(async () => {
      render(<NotificationBell />);
    });

    expect(screen.queryByTestId("bell-badge")).toBeNull();
  });

  it("shows badge count when there are unseen completed jobs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => makeCompletedJobs(3),
    });

    await act(async () => {
      render(<NotificationBell />);
    });

    const badge = screen.getByTestId("bell-badge");
    expect(badge).toBeTruthy();
    expect(badge.textContent).toBe("3");
  });

  it("shows job type labels in the dropdown", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => [
        {
          id: "job-1",
          type: "tailor_analyse",
          status: "done",
          result: null,
          error: null,
          created_at: new Date().toISOString(),
        },
      ],
    });

    await act(async () => {
      render(<NotificationBell />);
    });

    // Click to open dropdown
    const bell = screen.getByRole("button", { name: /notifications/i });
    await act(async () => {
      bell.click();
    });

    expect(screen.getByText("JD Analysis complete")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
cd frontend && npx vitest run src/__tests__/components/NotificationBell.test.tsx 2>&1 | tail -10
```
Expected: `Cannot find module '@/components/NotificationBell'`

- [ ] **Step 3: Create frontend/src/components/NotificationBell.tsx**

```typescript
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { listCompletedJobs, AsyncJobResponse } from "@/lib/api";

const JOB_LABELS: Record<string, string> = {
  tailor_analyse:      "JD Analysis complete",
  tailor_generate_cv:  "CV tailoring complete",
  tailor_generate_cl:  "Cover letter complete",
  tailor_generate:     "CV & cover letter complete",
  coach_session:       "Interview session ready",
  submit_answer:       "Answer evaluated",
  end_session:         "Feedback report ready",
  email_generate:      "Email draft ready",
  ghost_analyse:       "Job posting analysed",
};

const LAST_SEEN_KEY = "notif_last_seen_at";

export function NotificationBell() {
  const [jobs, setJobs] = useState<AsyncJobResponse[]>([]);
  const [open, setOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const fetchUnseen = useCallback(async () => {
    const lastSeen = localStorage.getItem(LAST_SEEN_KEY) ?? new Date(0).toISOString();
    try {
      const result = await listCompletedJobs(lastSeen, 10);
      setJobs(result);
    } catch {
      // Non-critical
    }
  }, []);

  useEffect(() => {
    void fetchUnseen();
    const interval = setInterval(() => void fetchUnseen(), 15_000);
    return () => clearInterval(interval);
  }, [fetchUnseen]);

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function handleOpen() {
    setOpen((prev) => !prev);
    if (!open && jobs.length > 0) {
      localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
      // Keep jobs visible until dropdown closes
    }
  }

  function handleClose() {
    setOpen(false);
    setJobs([]);
    localStorage.setItem(LAST_SEEN_KEY, new Date().toISOString());
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        aria-label="notifications"
        onClick={handleOpen}
        className="relative rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800"
      >
        <Bell className="h-5 w-5" />
        {jobs.length > 0 && (
          <span
            data-testid="bell-badge"
            className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-600 text-[10px] font-bold text-white"
          >
            {jobs.length > 9 ? "9+" : jobs.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2.5 dark:border-slate-800">
            <span className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              Notifications
            </span>
            {jobs.length > 0 && (
              <button
                onClick={handleClose}
                className="text-xs text-slate-400 hover:text-slate-600"
              >
                Mark all read
              </button>
            )}
          </div>

          {jobs.length === 0 ? (
            <p className="px-4 py-4 text-center text-sm text-slate-400">No new notifications</p>
          ) : (
            <ul className="max-h-64 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
              {jobs.map((job) => (
                <li key={job.id} className="px-4 py-3">
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                    {JOB_LABELS[job.type] ?? job.type}
                  </p>
                  <p className="text-xs text-slate-400">
                    {new Date(job.created_at).toLocaleTimeString()}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Add NotificationBell to Navigation.tsx**

Open `frontend/src/components/Navigation.tsx`. Add the import:
```typescript
import { NotificationBell } from "@/components/NotificationBell";
```

In the JSX, find the `<ThemeToggle />` in the right side of the header. Add `<NotificationBell />` just before it:
```tsx
          {/* Right side */}
          <div className="flex items-center gap-1">
            <NotificationBell />
            <ThemeToggle />
            {/* ... existing settings link ... */}
          </div>
```

- [ ] **Step 5: Run tests to confirm passing**

```bash
cd frontend && npx vitest run src/__tests__/components/NotificationBell.test.tsx 2>&1 | tail -15
```
Expected: All 3 tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/NotificationBell.tsx frontend/src/components/Navigation.tsx frontend/src/__tests__/components/NotificationBell.test.tsx
git commit -m "feat: add NotificationBell component and wire into Navigation"
```

---

### Task 13: Update Tailor page to use useAsyncJob

**Files:**
- Modify: `frontend/src/app/tailor/page.tsx`

- [ ] **Step 1: Replace handleAnalyse in tailor/page.tsx**

Open `frontend/src/app/tailor/page.tsx`. The current `handleAnalyse` awaits `analyseJdText` directly. Replace the file's logic as follows.

Add the import at the top:
```typescript
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { JDAnalysisResponse } from "@/lib/api";
```

Remove the existing `const [stage, setStage] = useState<Stage>("idle")` — the hook manages status.

Add the hook after the existing `useState` declarations:
```typescript
  const {
    state: analyseState,
    submit: submitAnalyse,
    reset: resetAnalyse,
  } = useAsyncJob<JDAnalysisResponse>({
    onComplete: (result) => {
      setAnalysis(result);
      setActiveTab("analysis");
    },
    onError: (err) => {
      setError(err);
    },
  });
```

Replace `handleAnalyse`:
```typescript
  const handleAnalyse = useCallback(async () => {
    if (!jdText.trim() && !jobUrl.trim()) return;
    setError(null);
    setAnalysis(null);
    await submitAnalyse(() => analyseJdText(jdText, jobUrl || undefined));
  }, [jdText, jobUrl, submitAnalyse]);
```

Update the button and status display to use `analyseState.status` instead of `stage`:
```typescript
  // In JSX — replace the existing "Analyse" button logic:
  const isAnalysing = analyseState.status === "pending" || analyseState.status === "running";
  const stage = analyseState.status === "done" ? "analysed"
               : analyseState.status === "failed" ? "error"
               : analyseState.status === "idle" ? "idle"
               : "analysing";
```

This maps the new hook statuses back to the existing `stage` variable so the rest of the JSX (which uses `stage`) works unchanged.

- [ ] **Step 2: Add status label for the analysing state**

In the JSX, find where the "Analysing…" spinner is shown (currently tied to `stage === "analysing"`). Keep this — it will still work because `isAnalysing` is true during pending/running.

Add a small status label below the spinner:
```tsx
  {isAnalysing && (
    <div className="mt-2 flex items-center gap-2">
      <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
      <span className="text-sm text-slate-500">
        {analyseState.status === "pending" ? "Queuing analysis…" : "Analysing job description…"}
      </span>
    </div>
  )}
```

- [ ] **Step 3: Verify TypeScript compilation**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "tailor/page"
```
Expected: No errors for tailor/page.tsx.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/tailor/page.tsx
git commit -m "feat: migrate tailor page to useAsyncJob polling pattern"
```

---

### Task 14: Update SessionLauncher to use useAsyncJob

**Files:**
- Modify: `frontend/src/components/coach/SessionLauncher.tsx`

- [ ] **Step 1: Update SessionLauncher to use useAsyncJob**

Open `frontend/src/components/coach/SessionLauncher.tsx`. 

Add the imports:
```typescript
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { SessionResponse } from "@/lib/api";
```

Replace the existing `const [loading, setLoading] = useState` and `handleStart` with:

```typescript
  const { state: sessionState, submit: submitSession } = useAsyncJob<SessionResponse>({
    onComplete: (session) => {
      onSessionCreated(session);
    },
    onError: (err) => {
      setError(err);
    },
  });

  const loading = sessionState.status === "pending" || sessionState.status === "running";

  const handleStart = async () => {
    if (!companyName.trim() || !roleTitle.trim()) return;
    setError(null);
    const request: CreateSessionRequest = {
      company_name: companyName,
      role_title: roleTitle,
      jd_text: jdText || null,
      config: {
        question_count: questionCount,
        categories: selectedCategories,
        difficulty,
        recording_mode: "text",
      },
    };
    await submitSession(() => createSession(request));
  };
```

Remove the old `const [loading, setLoading] = useState(false)`.

The existing JSX uses `loading` already — it will now reflect the async job state automatically.

Add a status label in the button area so the user knows what's happening:
```tsx
  {/* Below the Start Session button */}
  {sessionState.status === "pending" && (
    <p className="mt-2 text-center text-xs text-slate-400">Queuing session…</p>
  )}
  {sessionState.status === "running" && (
    <p className="mt-2 text-center text-xs text-slate-400">
      Preparing interview questions — this takes 1–2 minutes…
    </p>
  )}
```

- [ ] **Step 2: Verify TypeScript compilation**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep "SessionLauncher"
```
Expected: No errors.

- [ ] **Step 3: Run full frontend test suite**

```bash
cd frontend && npm test 2>&1 | tail -10
```
Expected: All tests pass.

- [ ] **Step 4: Run full backend test suite**

```bash
cd backend && python -m pytest -q 2>&1 | tail -5
```
Expected: All tests pass.

- [ ] **Step 5: Final commit**

```bash
git add frontend/src/components/coach/SessionLauncher.tsx
git commit -m "feat: migrate SessionLauncher to useAsyncJob — fixes coach session timeout"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task(s) |
|---|---|
| async_jobs DB table | Task 4 |
| AsyncJobService (create/run/_finish/get/list) | Task 5 |
| GET /api/async-jobs/{id} + list endpoint | Task 6 |
| 10 endpoints → 202 | Tasks 7, 8, 9 |
| useAsyncJob hook | Task 11 |
| NotificationBell + last_seen localStorage | Task 12 |
| Tailor page UI migration | Task 13 |
| SessionLauncher migration | Task 14 |
| llamacpp container in docker-compose | Task 1 |
| llamacpp provider in llm_factory.py | Task 2 |
| think-block stripping in claude_client.py | Task 2 |
| profile.yaml update | Task 3 |
| get_json_model() for llamacpp with response_format | Task 2 |
| Model download script | Task 1 |
| Background coroutine uses own DB session | Task 5 (AsyncJobService._finish + run) |

**All spec requirements covered.**

**Placeholder scan:** No TBD, TODO, or "similar to Task N" patterns found.

**Type consistency check:**
- `AsyncJobRef.job_id` (api.ts Task 10) matches `submit(() => fn returning {job_id})` in hook (Task 11) ✓
- `AsyncJobResponse<T>.result` type matches `useAsyncJob<T>` generic (Task 11) ✓
- `AsyncJob.status` values ("pending"|"running"|"done"|"failed") consistent across model (Task 4), service (Task 5), router (Task 6), hook (Task 11) ✓
- `AsyncJobService.create` → `flush()` not `commit()` (request handler commits after) ✓
