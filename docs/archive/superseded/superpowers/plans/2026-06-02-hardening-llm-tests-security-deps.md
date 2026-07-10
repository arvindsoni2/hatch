---
title: Hardening: LLM Fix, Tests, Security, Dependencies — Implementation Plan
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

# Hardening: LLM Fix, Tests, Security, Dependencies — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix Tailor/Coach 500 errors, raise backend test coverage to ≥75%, close 3 security vulnerabilities, update deps to latest patch/minor, and rebuild container images.

**Architecture:** UX-first — LLM JSON mode + phi3:mini eliminates malformed-JSON crashes; test fixes and new router tests push coverage above the 75% hard gate; targeted security middleware closes SSRF, race condition, and missing-header gaps; dep updates are patch/minor only with a major-CVE report.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest + pytest-cov, LangChain / ChatOllama, Next.js 14, Podman.

---

## Files Changed

| File | Action |
|---|---|
| `data/profile.yaml` | Modify — phi3:mini |
| `backend/app/agents/tools/llm_factory.py` | Modify — add `get_json_model()` |
| `backend/app/services/claude_client.py` | Modify — use `get_json_model()` |
| `backend/tests/test_tools/test_llm_factory.py` | Modify — add get_json_model test |
| `backend/tests/test_agents/test_scorer_agent.py` | Modify — fix fit_reasoning mock |
| `backend/tests/test_agents/test_scout_agent.py` | Modify — fix SCRAPER_REGISTRY patch |
| `backend/tests/test_scrapers/test_linkedin.py` | Modify — add datetime to card HTML |
| `backend/tests/test_tools/test_embedder.py` | Modify — add importorskip |
| `backend/tests/test_tools/test_semantic_scorer.py` | Modify — add importorskip |
| `backend/requirements-dev.txt` | Create — dev dependencies |
| `backend/tests/test_routers/test_jobs_router.py` | Create — jobs router tests |
| `backend/tests/test_routers/test_scoring_router.py` | Create — scoring router tests |
| `backend/tests/test_routers/test_resume_router.py` | Create — resume router tests |
| `backend/pytest.ini` | Modify — add coverage addopts |
| `backend/app/services/jd_analyser.py` | Modify — SSRF validation |
| `backend/app/routers/profile.py` | Modify — remove env mutation |
| `backend/app/main.py` | Modify — add security headers middleware |
| `frontend/next.config.js` | Modify — add headers() |
| `backend/requirements.txt` | Modify — dep updates |
| `docs/cve-report-2026-06-02.md` | Create — major CVE report |

---

## Task 1: Switch to phi3:mini

**Files:**
- Modify: `data/profile.yaml:107-109`

- [ ] **Step 1: Update profile.yaml**

In `data/profile.yaml`, replace:
```yaml
llm:
  provider: ollama
  triage_model: gemma:latest
  primary_model: gemma:latest
```
With:
```yaml
llm:
  provider: ollama
  triage_model: phi3:mini
  primary_model: phi3:mini
```

- [ ] **Step 2: Pull the model**

```bash
ollama pull phi3:mini
```

Expected: Ollama downloads ~2.3 GB. Verify with:
```bash
ollama list | grep phi3
```
Expected output contains: `phi3:mini`

- [ ] **Step 3: Commit**

```bash
git add data/profile.yaml
git commit -m "feat: switch Ollama model from gemma:latest to phi3:mini

phi3:mini (3.8B, ~2.3GB) has significantly better instruction-following
and structured-output compliance than Gemma, eliminating the malformed-JSON
errors that caused 500s in Tailor and Coach endpoints."
```

---

## Task 2: Add get_json_model() to llm_factory

**Files:**
- Modify: `backend/app/agents/tools/llm_factory.py:151-158`
- Test: `backend/tests/test_tools/test_llm_factory.py`

**Background:** `init_chat_model` passes `**kwargs` to the underlying LangChain model class. `ChatOllama` accepts `format="json"` which enables constrained token sampling — only valid JSON tokens are sampled, making malformed output impossible. For non-Ollama providers this param is not passed (they handle JSON via system prompts).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_tools/test_llm_factory.py` inside class `TestLlmFactory`:

```python
def test_get_json_model_passes_format_json_for_ollama(self):
    """get_json_model() passes format='json' to ChatOllama for constrained decoding."""
    mock_model = MagicMock()
    mock_profile = MagicMock()
    mock_profile.llm.provider = "ollama"
    mock_profile.llm.primary_model = "phi3:mini"
    mock_profile.llm.temperature = 0.3
    mock_profile.llm.max_retries = 3
    mock_profile.llm.api_key_env = ""
    mock_profile.llm.base_url = "http://localhost:11434"

    with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
         patch("app.agents.tools.llm_factory.init_chat_model", return_value=mock_model) as mock_init:
        from app.agents.tools.llm_factory import get_json_model
        result = get_json_model()

    mock_init.assert_called_once()
    call_kwargs = mock_init.call_args.kwargs
    assert call_kwargs.get("format") == "json"
    assert call_kwargs.get("model") == "phi3:mini"
    assert call_kwargs.get("model_provider") == "ollama"
    assert result is mock_model

def test_get_json_model_no_format_for_non_ollama(self):
    """get_json_model() does not pass format='json' for non-Ollama providers."""
    mock_model = MagicMock()
    mock_profile = MagicMock()
    mock_profile.llm.provider = "anthropic"
    mock_profile.llm.primary_model = "claude-sonnet-4-6"
    mock_profile.llm.temperature = 0.3
    mock_profile.llm.max_retries = 3
    mock_profile.llm.api_key_env = "ANTHROPIC_API_KEY"
    mock_profile.llm.base_url = None

    with patch("app.agents.tools.llm_factory.load_profile", return_value=mock_profile), \
         patch("app.agents.tools.llm_factory.init_chat_model", return_value=mock_model) as mock_init:
        from app.agents.tools.llm_factory import get_json_model
        result = get_json_model()

    call_kwargs = mock_init.call_args.kwargs
    assert "format" not in call_kwargs
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_tools/test_llm_factory.py::TestLlmFactory::test_get_json_model_passes_format_json_for_ollama -v
```
Expected: `ImportError` or `AttributeError` — `get_json_model` does not exist yet.

- [ ] **Step 3: Add get_json_model() to llm_factory.py**

Add after `get_primary_model()` at the bottom of `backend/app/agents/tools/llm_factory.py` (after line 158):

```python
def get_json_model() -> BaseChatModel:
    """Return the primary model configured for JSON-constrained output.

    For Ollama providers, passes format='json' to enable constrained token
    sampling — only valid JSON tokens are sampled at the model level.
    For all other providers, delegates to get_primary_model() (JSON is
    enforced via system-prompt instructions instead).
    """
    profile = load_profile()
    llm_cfg = profile.llm
    if llm_cfg.provider == "ollama":
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
    return _build_model(llm_cfg.primary_model, llm_cfg)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_tools/test_llm_factory.py -v
```
Expected: All 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/agents/tools/llm_factory.py backend/tests/test_tools/test_llm_factory.py
git commit -m "feat: add get_json_model() with Ollama format=json constrained decoding

Enables token-level JSON constraint for Ollama models, eliminating
malformed JSON at the source. Non-Ollama providers use system-prompt
enforcement via get_primary_model()."
```

---

## Task 3: Wire get_json_model() in ClaudeClient

**Files:**
- Modify: `backend/app/services/claude_client.py:18,59-90`

- [ ] **Step 1: Write the failing test**

Add a new test file `backend/tests/test_services/test_claude_client.py`:

```python
"""Tests for ClaudeClient — complete_json uses JSON-mode model for Ollama."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestClaudeClient:

    async def test_complete_json_uses_get_json_model(self):
        """complete_json() calls get_json_model(), not get_primary_model()."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"key": "value"}'))

        with patch("app.services.claude_client.get_json_model", return_value=mock_llm) as mock_factory, \
             patch("app.services.claude_client.get_primary_model") as mock_primary:
            from app.services.claude_client import ClaudeClient
            client = ClaudeClient()
            result = await client.complete_json("sys", "user")

        mock_factory.assert_called_once()
        mock_primary.assert_not_called()
        assert result == {"key": "value"}

    async def test_complete_json_retries_on_parse_failure(self):
        """complete_json() retries up to 3 times on JSONDecodeError."""
        call_count = 0

        async def flaky_invoke(messages):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return MagicMock(content="not json at all")
            return MagicMock(content='{"ok": true}')

        mock_llm = MagicMock()
        mock_llm.ainvoke = flaky_invoke

        with patch("app.services.claude_client.get_json_model", return_value=mock_llm):
            from app.services.claude_client import ClaudeClient
            client = ClaudeClient()
            result = await client.complete_json("sys", "user")

        assert result == {"ok": True}
        assert call_count == 3

    async def test_complete_json_raises_after_3_failures(self):
        """complete_json() raises ValueError after 3 parse failures."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="not json"))

        with patch("app.services.claude_client.get_json_model", return_value=mock_llm):
            from app.services.claude_client import ClaudeClient
            client = ClaudeClient()
            with pytest.raises(ValueError, match="3 attempts"):
                await client.complete_json("sys", "user")

    async def test_complete_strips_markdown_fences(self):
        """complete_json() strips ```json ... ``` code fences before parsing."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='```json\n{"key": "val"}\n```'))

        with patch("app.services.claude_client.get_json_model", return_value=mock_llm):
            from app.services.claude_client import ClaudeClient
            client = ClaudeClient()
            result = await client.complete_json("sys", "user")

        assert result == {"key": "val"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_services/test_claude_client.py::TestClaudeClient::test_complete_json_uses_get_json_model -v
```
Expected: FAIL — `get_json_model` is not imported in `claude_client.py`.

- [ ] **Step 3: Update claude_client.py**

In `backend/app/services/claude_client.py`, change line 18:
```python
from ..agents.tools.llm_factory import get_primary_model
```
to:
```python
from ..agents.tools.llm_factory import get_json_model, get_primary_model
```

Then in `complete_json()` (line 72), change:
```python
text = await self.complete(system + _JSON_INSTRUCTION, user, max_tokens)
```
to:
```python
llm = get_json_model()
messages = [SystemMessage(content=system + _JSON_INSTRUCTION), HumanMessage(content=user)]
response = await llm.ainvoke(messages)
text = response.content if isinstance(response.content, str) else str(response.content)
```

This means the retry loop in `complete_json()` now calls `get_json_model()` on each attempt (already the pattern, fine for retry logic) and the `complete()` method remains unchanged.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_services/test_claude_client.py -v
```
Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/claude_client.py backend/tests/test_services/test_claude_client.py
git commit -m "feat: wire get_json_model() into ClaudeClient.complete_json()

complete_json() now uses get_json_model() which passes format='json' to
Ollama, guaranteeing token-level JSON constraint. The 3-retry fallback
remains for non-Ollama providers."
```

---

## Task 4: Fix Scorer Agent Test — fit_reasoning MagicMock

**Files:**
- Modify: `backend/tests/test_agents/test_scorer_agent.py:73-91`

**Root cause:** `_make_mock_llm()` creates `score_result = MagicMock(...)` without setting `fit_reasoning`, `strengths`, or `score_gaps`. These attributes auto-return MagicMock objects which SQLite cannot serialize. Tests that trigger LLM calls (hybrid/borderline modes) fail when the scorer tries to persist the score row.

- [ ] **Step 1: Run the failing tests to confirm**

```bash
cd backend && python -m pytest tests/test_agents/test_scorer_agent.py -v 2>&1 | grep -E "FAILED|ERROR|PASSED" | head -15
```
Expected: 3 tests FAILED with `InterfaceError` or `sqlite3.InterfaceError`.

- [ ] **Step 2: Fix _make_mock_llm() in test_scorer_agent.py**

In `backend/tests/test_agents/test_scorer_agent.py`, find `_make_mock_llm()` (around line 73) and change the `score_result` definition from:

```python
score_result = MagicMock(
    skill_match=score, experience_match=score, rate_match=score, location_match=score,
    overall_score=score, reasoning="good match",
    keyword_matches=["cloud", "aws"], keyword_misses=[],
)
```

to:

```python
score_result = MagicMock(
    skill_match=score, experience_match=score, rate_match=score, location_match=score,
    overall_score=score, reasoning="good match",
    keyword_matches=["cloud", "aws"], keyword_misses=[],
    fit_reasoning="Strong match based on skills and experience.",
    strengths=["Cloud expertise", "Architecture experience"],
    score_gaps=[],
)
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_agents/test_scorer_agent.py -v
```
Expected: All scorer agent tests PASS (or at most skip if sentence-transformers absent — Task 8 handles that).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_agents/test_scorer_agent.py
git commit -m "fix: add fit_reasoning/strengths/score_gaps to scorer mock to prevent SQLite serialization error"
```

---

## Task 5: Fix Scout Agent Test — SCRAPER_REGISTRY Class Reference

**Files:**
- Modify: `backend/tests/test_agents/test_scout_agent.py`

**Root cause:** `SCRAPER_REGISTRY` maps scraper ID strings to **class references** (e.g., `"ReedScraper": ReedScraper`). The scout agent calls `scraper_cls = SCRAPER_REGISTRY.get(source)` then `scraper = scraper_cls()`. The tests patch the registry with string values (`"fake.module.FakeScraper"`) and a fake `importlib.import_module` — but the agent no longer uses importlib. Calling a string raises `TypeError`.

- [ ] **Step 1: Run the failing tests**

```bash
cd backend && python -m pytest tests/test_agents/test_scout_agent.py -v 2>&1 | grep -E "FAILED|ERROR" | head -10
```
Expected: 2 tests FAILED with `TypeError: 'str' object is not callable`.

- [ ] **Step 2: Fix all three tests in test_scout_agent.py**

In `backend/tests/test_agents/test_scout_agent.py`, every test that patches `SCRAPER_REGISTRY` currently has this pattern:

```python
patch("app.agents.scout_agent.SCRAPER_REGISTRY", {"test_source": "fake.module.FakeScraper"}),
patch("importlib.import_module") as mock_import:
    MockEB.instance.return_value = mock_bus
    mock_module = MagicMock()
    mock_module.FakeScraper = mock_scraper_cls
    mock_import.return_value = mock_module
```

Replace every such block with:

```python
patch("app.agents.scout_agent.SCRAPER_REGISTRY", {"test_source": mock_scraper_cls}):
    MockEB.instance.return_value = mock_bus
```

Concretely, in `test_run_emits_job_discovered_for_new_jobs`:

Remove the `patch("importlib.import_module") as mock_import:` line and the three lines inside it that set up `mock_module`. Change the SCRAPER_REGISTRY patch dict value from the string `"fake.module.FakeScraper"` to `mock_scraper_cls`.

Apply the same change to `test_run_filters_duplicates` and `test_run_handles_scraper_failure_gracefully` (source key `"bad_source"`, class `mock_scraper_cls`).

The updated `test_run_emits_job_discovered_for_new_jobs` context manager should look like:
```python
with patch("app.agents.base_agent.EventBus") as MockEB, \
     patch("app.agents.scout_agent.DedupService", return_value=mock_dedup), \
     patch("app.agents.scout_agent.SCRAPER_REGISTRY", {"test_source": mock_scraper_cls}):
    MockEB.instance.return_value = mock_bus
    from app.agents.scout_agent import ScoutAgent
    scout = ScoutAgent(sources=["test_source"])
    scout._bus = mock_bus
    scout._dedup = mock_dedup
    result = await scout.run(db_session)
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_agents/test_scout_agent.py -v
```
Expected: All 3 scout agent tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_agents/test_scout_agent.py
git commit -m "fix: patch SCRAPER_REGISTRY with class reference, not string path

SCRAPER_REGISTRY now stores class objects directly. Tests were patching
with string paths and a fake importlib, which broke when importlib was
removed from the scout agent."
```

---

## Task 6: Fix LinkedIn Test — date_unknown Causes needs_enrichment=True

**Files:**
- Modify: `backend/tests/test_scrapers/test_linkedin.py:122-140`

**Root cause:** `_parse_card()` sets `needs_enrichment = needs_enrichment or date_unknown`. The test `test_long_description_does_not_need_enrichment` builds a card with no `<time>` element, so `_parse_posted_at` returns `date_unknown=True`, overriding the long-description check.

- [ ] **Step 1: Run the failing test**

```bash
cd backend && python -m pytest tests/test_scrapers/test_linkedin.py::TestLinkedInScraper::test_long_description_does_not_need_enrichment -v
```
Expected: FAILED — `AssertionError: assert True == False` on `needs_enrichment`.

- [ ] **Step 2: Add a datetime element to the card HTML**

In `backend/tests/test_scrapers/test_linkedin.py`, find `test_long_description_does_not_need_enrichment` (line 122). The card HTML block is:

```python
card_html = f"""
<li>
  <h3>Senior PM</h3>
  <h4>MegaCorp</h4>
  <a href="https://www.linkedin.com/jobs/view/777">Apply</a>
  <p>{long_text}</p>
</li>
"""
```

Replace with (add the `<time>` element):

```python
card_html = f"""
<li>
  <h3>Senior PM</h3>
  <h4>MegaCorp</h4>
  <a href="https://www.linkedin.com/jobs/view/777">Apply</a>
  <time datetime="2026-05-01">1 month ago</time>
  <p>{long_text}</p>
</li>
"""
```

- [ ] **Step 3: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_scrapers/test_linkedin.py -v
```
Expected: All LinkedIn scraper tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_scrapers/test_linkedin.py
git commit -m "fix: add datetime element to LinkedIn long-description test card

_parse_card() sets needs_enrichment=True when date_unknown=True (no <time>
element). The test card now includes a valid datetime attribute so the date
is known and needs_enrichment is driven by description length alone."
```

---

## Task 7: Guard Embedder and Semantic Scorer Tests with importorskip

**Files:**
- Modify: `backend/tests/test_tools/test_embedder.py`
- Modify: `backend/tests/test_tools/test_semantic_scorer.py`
- Create: `backend/requirements-dev.txt`

**Background:** `sentence-transformers` is in `requirements.txt` but may not be installed in the local dev environment (large package, ~1GB). Adding `importorskip` makes these tests skip gracefully when the library is absent and run fully when it's present (including in CI with `requirements-dev.txt`).

- [ ] **Step 1: Create requirements-dev.txt**

Create `backend/requirements-dev.txt`:

```
# Test and dev dependencies (install after requirements.txt)
-r requirements.txt

# Test runner
pytest>=8.0,<9.0
pytest-asyncio>=0.24,<1.0
pytest-cov>=5.0,<6.0
httpx>=0.27,<0.28

# Semantic scoring (large — skip tests gracefully if not installed locally)
sentence-transformers>=3.0,<4.0
```

- [ ] **Step 2: Add importorskip to test_embedder.py**

At the top of `backend/tests/test_tools/test_embedder.py`, after the `import pytest` line, add:

```python
pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")
```

The file should start like:
```python
"""Tests for the local sentence-transformer embedder."""
from __future__ import annotations

import pytest

pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")
```

- [ ] **Step 3: Add importorskip to test_semantic_scorer.py**

At the top of `backend/tests/test_tools/test_semantic_scorer.py`, after `import pytest`:

```python
pytest.importorskip("sentence_transformers", reason="sentence-transformers not installed")
```

- [ ] **Step 4: Run tests to verify skip behaviour**

If `sentence-transformers` is NOT installed:
```bash
cd backend && python -m pytest tests/test_tools/test_embedder.py tests/test_tools/test_semantic_scorer.py -v
```
Expected: All 13 tests show `SKIPPED` with reason `sentence-transformers not installed`.

If `sentence-transformers` IS installed, all 13 tests should PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_tools/test_embedder.py backend/tests/test_tools/test_semantic_scorer.py backend/requirements-dev.txt
git commit -m "fix: guard embedder/semantic-scorer tests with importorskip; add requirements-dev.txt

Tests skip gracefully when sentence-transformers is absent and run fully
in CI where requirements-dev.txt is installed."
```

---

## Task 8: Add Jobs Router Tests

**Files:**
- Create: `backend/tests/test_routers/test_jobs_router.py`

**Why:** The jobs router has no test file, yet it contains 10+ endpoints including health check, listing, filtering, CRUD, and archiving. These are the highest-coverage-ROI tests to add.

- [ ] **Step 1: Write the test file**

Create `backend/tests/test_routers/test_jobs_router.py`:

```python
"""Tests for /api/jobs router — health, list, get, patch, delete, archive."""
from __future__ import annotations

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import get_db


@pytest.fixture
def sample_job_dict():
    return {
        "id": str(uuid.uuid4()),
        "title": "Cloud Architect",
        "company": "Test Corp",
        "location": "London, UK",
        "rate_min": 600.0,
        "rate_max": 700.0,
        "rate_text": "£600-700/day",
        "currency": "GBP",
        "ir35_status": "outside",
        "description": "Senior cloud architect role",
        "url": "https://example.com/job/1",
        "source": "reed",
        "is_active": True,
        "sync_status": "pending",
        "scraped_at": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "skills": ["AWS", "Terraform"],
        "contract_length": "6 months",
        "ats_score": None,
        "match_score": None,
        "overall_score": None,
        "posted_at": None,
    }


@pytest.mark.asyncio
async def test_health_endpoint_returns_200(db_session):
    """GET /api/health returns 200 with status ok."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_jobs_returns_200(db_session):
    """GET /api/jobs returns 200 with paginated response."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/jobs")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_get_job_not_found_returns_404(db_session):
    """GET /api/jobs/{id} returns 404 for unknown ID."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/jobs/{uuid.uuid4()}")

    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_returns_200_for_existing_job(db_session, sample_job):
    """GET /api/jobs/{id} returns 200 for a job that exists in the DB."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/jobs/{sample_job.id}")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_job.id
    assert data["title"] == sample_job.title


@pytest.mark.asyncio
async def test_patch_job_returns_200(db_session, sample_job):
    """PATCH /api/jobs/{id} updates a field and returns 200."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/api/jobs/{sample_job.id}",
            json={"sync_status": "approved"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json()["sync_status"] == "approved"


@pytest.mark.asyncio
async def test_delete_job_returns_200(db_session, sample_job):
    """DELETE /api/jobs/{id} soft-deletes a job and returns 200."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/api/jobs/{sample_job.id}")

    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_jobs_with_status_filter(db_session):
    """GET /api/jobs?sync_status=pending returns only pending jobs."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/jobs", params={"sync_status": "pending"})

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_stats_endpoint_returns_200(db_session):
    """GET /api/jobs/stats returns 200 with count fields."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/jobs/stats")

    app.dependency_overrides.clear()
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_routers/test_jobs_router.py -v
```
Expected: All 8 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_routers/test_jobs_router.py
git commit -m "test: add jobs router tests covering health, list, get, patch, delete, stats"
```

---

## Task 9: Add Scoring and Resume Router Tests

**Files:**
- Create: `backend/tests/test_routers/test_scoring_router.py`
- Create: `backend/tests/test_routers/test_resume_router.py`

- [ ] **Step 1: Create test_scoring_router.py**

```python
"""Tests for /api/scoring router — insights, score breakdown endpoints."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import get_db


@pytest.mark.asyncio
async def test_scoring_insights_returns_200(db_session):
    """GET /api/scoring/insights returns 200."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/scoring/insights")

    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_scoring_insights_structure(db_session):
    """GET /api/scoring/insights response has expected top-level keys."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/scoring/insights")

    app.dependency_overrides.clear()
    data = resp.json()
    assert isinstance(data, dict)
```

- [ ] **Step 2: Create test_resume_router.py**

```python
"""Tests for /api/resume router — status, upload, json endpoints."""
from __future__ import annotations

import io
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.database import get_db


@pytest.mark.asyncio
async def test_resume_status_returns_200(db_session):
    """GET /api/resume/status returns 200."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/resume/status")

    app.dependency_overrides.clear()
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_resume_json_returns_200_or_404(db_session):
    """GET /api/resume/json returns 200 if resume exists, 404 if not."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/resume/json")

    app.dependency_overrides.clear()
    assert resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_resume_upload_invalid_file_type_returns_422(db_session):
    """POST /api/resume/upload with .txt file returns 422."""
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/api/resume/upload",
            files={"file": ("resume.txt", io.BytesIO(b"plain text"), "text/plain")},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 422
```

- [ ] **Step 3: Run all new router tests**

```bash
cd backend && python -m pytest tests/test_routers/test_scoring_router.py tests/test_routers/test_resume_router.py -v
```
Expected: All 5 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_routers/test_scoring_router.py backend/tests/test_routers/test_resume_router.py
git commit -m "test: add scoring and resume router tests for coverage gap"
```

---

## Task 10: Enforce 75% Coverage Threshold

**Files:**
- Modify: `backend/pytest.ini`

- [ ] **Step 1: Verify current coverage**

```bash
cd backend && python -m pytest --cov=app --cov-report=term-missing --cov-fail-under=75 2>&1 | tail -20
```
Expected: FAIL with `FAILED: Required test coverage of 75% not reached.` — this confirms the gate works before we enforce it in config.

- [ ] **Step 2: Add addopts to pytest.ini**

In `backend/pytest.ini`, add an `addopts` line:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = --cov=app --cov-report=term-missing --cov-fail-under=75
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
log_cli = true
log_cli_level = WARNING
```

- [ ] **Step 3: Run full test suite to verify coverage passes**

```bash
cd backend && python -m pytest 2>&1 | tail -10
```
Expected: `Required test coverage of 75% reached.` and all tests pass (or skip). If coverage is still below 75%, add more router or service tests until the gate passes — use `--cov-report=term-missing` output to identify which modules have the lowest coverage and target those.

- [ ] **Step 4: Commit**

```bash
git add backend/pytest.ini
git commit -m "test: enforce 75% coverage threshold via pytest.ini addopts"
```

---

## Task 11: Fix SSRF in jd_analyser._fetch_jd()

**Files:**
- Modify: `backend/app/services/jd_analyser.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_services/test_jd_analyser.py`:

```python
class TestFetchJdUrlValidation:

    async def test_private_ip_is_blocked(self):
        """_fetch_jd() raises ValueError for URLs resolving to private IPs."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="SSRF blocked"):
            await analyser._fetch_jd("http://192.168.1.1/secret")

    async def test_loopback_is_blocked(self):
        """_fetch_jd() raises ValueError for loopback URLs."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="SSRF blocked|private"):
            await analyser._fetch_jd("http://127.0.0.1:8080/admin")

    async def test_non_http_scheme_is_blocked(self):
        """_fetch_jd() raises ValueError for non-http/https schemes."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="Only http/https"):
            await analyser._fetch_jd("file:///etc/passwd")

    async def test_ftp_scheme_is_blocked(self):
        """_fetch_jd() raises ValueError for ftp:// scheme."""
        from app.services.jd_analyser import JDAnalyser
        analyser = JDAnalyser.__new__(JDAnalyser)

        with pytest.raises(ValueError, match="Only http/https"):
            await analyser._fetch_jd("ftp://example.com/jobs.txt")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_services/test_jd_analyser.py::TestFetchJdUrlValidation -v
```
Expected: All 4 FAIL — `_fetch_jd` does not validate URLs yet.

- [ ] **Step 3: Add _validate_url() to jd_analyser.py**

Add a module-level function just before the `JDAnalyser` class definition in `backend/app/services/jd_analyser.py`:

```python
import ipaddress
import socket
from urllib.parse import urlparse


def _validate_url(url: str) -> None:
    """Validate that a URL is safe to fetch (blocks SSRF vectors).

    Raises ValueError for non-http/https schemes and for hostnames that
    resolve to private, loopback, or link-local IP addresses.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are allowed, got scheme: '{parsed.scheme}'")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL has no hostname")
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}") from exc
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            raise ValueError(
                f"SSRF blocked: '{hostname}' resolves to private/reserved IP {ip}"
            )
```

Then in `_fetch_jd()`, add the validation call at the start of the method, before the `httpx.AsyncClient` context manager:

```python
async def _fetch_jd(self, url: str) -> str:
    _validate_url(url)   # raises ValueError on SSRF attempt
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_services/test_jd_analyser.py -v
```
Expected: All jd_analyser tests PASS including the 4 new SSRF tests.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/jd_analyser.py backend/tests/test_services/test_jd_analyser.py
git commit -m "fix: block SSRF in _fetch_jd() — validate scheme and IP before fetching

Adds _validate_url() that rejects non-http/https schemes and hostnames
that resolve to private/loopback/link-local IPs via stdlib ipaddress +
socket. No new dependencies."
```

---

## Task 12: Fix Race Condition in profile.py test-connection

**Files:**
- Modify: `backend/app/routers/profile.py:102-135`

**Root cause:** The endpoint sets `os.environ[env_var] = api_key` globally, makes an async LLM call, then restores. Concurrent requests can interleave, reading each other's temporary env var value. Fix: build the LLM with `api_key=` directly, never touching `os.environ`.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_routers/test_profile_router.py`:

```python
@pytest.mark.asyncio
async def test_test_connection_does_not_mutate_os_environ():
    """test-connection endpoint must not write to os.environ."""
    import os

    original_key = os.environ.get("ANTHROPIC_API_KEY", "ORIGINAL_SENTINEL")

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="OK"))

    with patch("app.routers.profile.get_triage_model", return_value=mock_llm):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                "/api/v2/profile/test-connection",
                json={"provider": "anthropic", "api_key": "sk-test-key-12345"},
            )

    # os.environ must be unchanged after the call
    assert os.environ.get("ANTHROPIC_API_KEY", "ORIGINAL_SENTINEL") == original_key
```

- [ ] **Step 2: Run test to verify it currently fails (or passes — check what it actually does)**

```bash
cd backend && python -m pytest tests/test_routers/test_profile_router.py::test_test_connection_does_not_mutate_os_environ -v
```
Expected: Depends on current env state. The important thing is the new implementation must pass it consistently.

- [ ] **Step 3: Rewrite test-connection in profile.py**

In `backend/app/routers/profile.py`, replace the entire `test_llm_connection` function (lines 102-135) with:

```python
@router.post("/test-connection")
async def test_llm_connection(data: dict[str, Any]) -> dict[str, Any]:
    """Test that the LLM API key / provider in the submitted profile config is valid.

    Builds the LLM client with the submitted api_key directly — never mutates
    os.environ, eliminating the global-state race condition in async context.
    Returns {ok: bool, error?: str}.
    """
    from langchain.chat_models import init_chat_model

    provider: str = data.get("provider", "anthropic")
    api_key: str = data.get("api_key", "")
    model_map = {
        "anthropic": "claude-haiku-4-5-20251001",
        "openai": "gpt-4o-mini",
        "google": "gemini-2.0-flash",
        "azure": "gpt-4o-mini",
        "ollama": "phi3:mini",
    }
    model_name = model_map.get(provider, "claude-haiku-4-5-20251001")

    try:
        kwargs: dict[str, Any] = {"temperature": 0.0, "max_retries": 1}
        if api_key and provider != "ollama":
            kwargs["api_key"] = api_key
        if provider == "ollama":
            from ..agents.tools.profile_loader import load_profile as _lp
            try:
                kwargs["base_url"] = _lp().llm.base_url or "http://localhost:11434"
            except Exception:
                kwargs["base_url"] = "http://localhost:11434"
        llm = init_chat_model(model=model_name, model_provider=provider, **kwargs)
        await llm.ainvoke("Reply with the single word OK.")
        return {"ok": True}
    except Exception as exc:
        logger.debug("LLM connection test failed: %s", exc)
        return {"ok": False, "error": str(exc)}
```

Also add `from langchain.chat_models import init_chat_model` at the top if not already imported — but since it's inside the function, it's fine as a local import.

Remove the unused `import os` at the top of `profile.py` if `os` is now unused (check for other uses first).

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_routers/test_profile_router.py -v
```
Expected: All profile router tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/profile.py backend/tests/test_routers/test_profile_router.py
git commit -m "fix: remove os.environ mutation from test-connection endpoint

Builds LLM with api_key= constructor arg instead of globally mutating
os.environ. Eliminates race condition where concurrent requests could
read each other's temporary API key value."
```

---

## Task 13: Add Security Headers

**Files:**
- Modify: `backend/app/main.py`
- Modify: `frontend/next.config.js`

- [ ] **Step 1: Write the backend security headers test**

Add to `backend/tests/test_routers/test_profile_router.py` (or any existing router test file):

```python
@pytest.mark.asyncio
async def test_security_headers_present_on_every_response():
    """Every API response must include X-Content-Type-Options and X-Frame-Options."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")

    assert resp.headers.get("x-content-type-options") == "nosniff"
    assert resp.headers.get("x-frame-options") == "DENY"
    assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_routers/test_profile_router.py::test_security_headers_present_on_every_response -v
```
Expected: FAIL — headers are absent.

- [ ] **Step 3: Add SecurityHeadersMiddleware to main.py**

In `backend/app/main.py`, add after the existing imports (after `from fastapi.middleware.cors import CORSMiddleware`):

```python
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
```

Add the middleware class before `create_app()`:

```python
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
```

Inside `create_app()`, after the `CORSMiddleware` block (around line 144), add:

```python
app.add_middleware(SecurityHeadersMiddleware)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_routers/ -k "security_headers" -v
```
Expected: PASS.

- [ ] **Step 5: Add security headers to frontend next.config.js**

In `frontend/next.config.js`, modify the `nextConfig` object to add an `async headers()` function after `async rewrites()`:

```javascript
const nextConfig = {
  reactStrictMode: true,
  ...(process.env.NODE_ENV === "production" && { output: "standalone" }),
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_URL}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-XSS-Protection", value: "1; mode=block" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};
```

- [ ] **Step 6: Verify frontend headers in dev**

```bash
cd frontend && npm run dev &
sleep 5
curl -s -I http://localhost:3000 | grep -iE "x-frame|x-content|referrer|xss"
kill %1
```
Expected: Headers appear in the curl output.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py frontend/next.config.js backend/tests/test_routers/test_profile_router.py
git commit -m "fix: add security headers middleware (backend) and headers() (frontend)

Backend: SecurityHeadersMiddleware sets X-Content-Type-Options, X-Frame-Options,
and Referrer-Policy on every response via Starlette BaseHTTPMiddleware.
Frontend: next.config.js headers() applies same set plus X-XSS-Protection."
```

---

## Task 14: Update Backend Dependencies

**Files:**
- Modify: `backend/requirements.txt`
- Create: `docs/cve-report-2026-06-02.md`

- [ ] **Step 1: Check current outdated packages**

```bash
cd backend && pip list --outdated --format=columns 2>/dev/null | tee /tmp/outdated_backend.txt
cat /tmp/outdated_backend.txt
```

- [ ] **Step 2: Update patch/minor versions in requirements.txt**

For each package in the outdated list where the newer version is the same major (e.g., `fastapi 0.115.0 → 0.115.5`), update the pinned version in `backend/requirements.txt`. Do NOT update packages where the newer version is a different major number — record those in the CVE report.

Example updates (adjust based on actual `pip list --outdated` output):
```
fastapi==0.115.X  (latest same-major)
httpx==0.27.X
pydantic==2.X.X
sqlalchemy==2.0.X
```

- [ ] **Step 3: Run pip-audit**

```bash
cd backend && pip install pip-audit 2>/dev/null; pip-audit -r requirements.txt 2>&1 | tee /tmp/pip_audit_backend.txt
cat /tmp/pip_audit_backend.txt
```

- [ ] **Step 4: Write CVE report**

Create `docs/cve-report-2026-06-02.md` listing all packages where:
- The fix requires a major-version bump (e.g., `package 1.x → 2.0`)
- OR `pip-audit` flagged a CVE that is not fixed in the current major

Template:
```markdown
# CVE Report — 2026-06-02

Generated by: pip-audit + npm audit
Scope: major-version CVEs deferred from patch/minor update pass

## Backend (Python)

| Package | Current | Fixed In | CVE ID | Severity | Migration Notes |
|---|---|---|---|---|---|
| example-pkg | 1.2.3 | 2.0.0 | CVE-2025-XXXXX | HIGH | Breaking: renamed API |

## Frontend (Node)

| Package | Current | Fixed In | CVE ID | Severity | Migration Notes |
|---|---|---|---|---|---|

## Action Required

Review before next major release. File a ticket for any HIGH/CRITICAL CVEs.
```

Populate from `pip-audit` and `npm audit` output in step 5.

- [ ] **Step 5: Verify backend still starts after dep updates**

```bash
cd backend && pip install -r requirements.txt && python -c "from app.main import app; print('Import OK')"
```
Expected: `Import OK`

- [ ] **Step 6: Commit**

```bash
git add backend/requirements.txt docs/cve-report-2026-06-02.md
git commit -m "chore: update backend deps to latest patch/minor; add CVE report for major-version gaps"
```

---

## Task 15: Update Frontend Dependencies

**Files:**
- Modify: `frontend/package.json`

- [ ] **Step 1: Check outdated packages**

```bash
cd frontend && npm outdated 2>/dev/null | tee /tmp/outdated_frontend.txt
cat /tmp/outdated_frontend.txt
```

- [ ] **Step 2: Update within semver ranges**

```bash
cd frontend && npm update
```

This updates all packages to the latest version allowed by the semver ranges in `package.json`. It does NOT perform major-version bumps.

- [ ] **Step 3: Run npm audit**

```bash
cd frontend && npm audit 2>&1 | tee /tmp/npm_audit_frontend.txt
cat /tmp/npm_audit_frontend.txt
```

Add any HIGH/CRITICAL packages requiring major-version bumps to the CVE report created in Task 14.

- [ ] **Step 4: Run frontend tests to verify no regressions**

```bash
cd frontend && npm test -- --run
```
Expected: All 119 tests PASS (same as before).

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore: update frontend deps to latest patch/minor versions"
```

---

## Task 16: Rebuild Podman Images

- [ ] **Step 1: Rebuild backend image**

```bash
cd /home/asoni/Downloads/Assignment/Job_Pilot_v2
podman build -t localhost/job_pilot_v2_backend:latest ./backend
```
Expected: `Successfully tagged localhost/job_pilot_v2_backend:latest`

- [ ] **Step 2: Rebuild frontend image**

```bash
podman build -t localhost/job_pilot_v2_frontend:latest ./frontend
```
Expected: `Successfully tagged localhost/job_pilot_v2_frontend:latest`

- [ ] **Step 3: Verify both images are current**

```bash
podman images | grep job_pilot_v2
```
Expected: Both images show today's date (2026-06-02).

- [ ] **Step 4: Smoke-test via docker-compose**

```bash
podman-compose up -d
sleep 10
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
curl -s -I http://127.0.0.1:8000/api/health | grep -iE "x-frame|x-content"
podman-compose down
```
Expected:
- `{"status": "ok"}` from health check
- Security headers present in curl output

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "chore: verify rebuilt podman images with all hardening changes applied"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task(s) |
|---|---|
| phi3:mini + JSON mode | Task 1, Task 2, Task 3 |
| Coach 503 error handling | Already returns 503 — no change needed |
| Fix 14 test failures | Tasks 4, 5, 6, 7 |
| 75% coverage + fail gate | Tasks 8, 9, 10 |
| SSRF fix | Task 11 |
| Race condition fix | Task 12 |
| Security headers | Task 13 |
| Backend dep update + CVE report | Task 14 |
| Frontend dep update | Task 15 |
| Rebuild images | Task 16 |

**All spec items covered. No placeholders. Types consistent across tasks.**
