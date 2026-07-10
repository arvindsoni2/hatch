---
title: Hardening: LLM Fix, Test Coverage, Security, Dependencies
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

# Hardening: LLM Fix, Test Coverage, Security, Dependencies

**Date:** 2026-06-02  
**Approach:** UX-first — fix 500 errors → fix tests + coverage → security → deps

---

## 1. Fix 500 Errors (Tailor + Coach)

### Root cause
Gemma returns malformed JSON. `complete_json()` in `claude_client.py` retries 3× then raises `ValueError`, which becomes a 500/503.

### 1a. Switch model to phi3:mini
- Update `data/profile.yaml`: set `triage_model` and `primary_model` to `phi3:mini`
- Pull image: `ollama pull phi3:mini` (one-time; add to backend entrypoint or README)
- phi3:mini (3.8B, ~2.3GB) has better instruction-following than Gemma and fits within the Quadro P520's 2GB VRAM + system RAM split

### 1b. Enable Ollama JSON-mode factory
- Add `get_json_model()` to `backend/app/agents/tools/llm_factory.py`
- `ChatOllama(format="json", ...)` — constrained decoding guarantees valid JSON tokens
- `ClaudeClient.complete_json()` calls `get_json_model()` instead of `get_primary_model()`
- `complete()` and `complete_structured()` continue using `get_primary_model()` (no format constraint)
- The existing 3-retry loop in `complete_json()` is retained as a safety net for non-Ollama providers

### 1c. Coach router error handling
- `backend/app/routers/coach.py` `create_session` currently raises 500 on LLM failure
- Change to 503 with user-friendly message, matching the pattern already in `tailor.py`

---

## 2. Fix 14 Test Failures + Raise Coverage to 75%

### 2a. Fix failing tests

| Root cause | Files | Fix |
|---|---|---|
| `fit_reasoning` MagicMock not JSON-serialisable | `tests/test_scorer_agent.py` | Replace `MagicMock()` with `"mock reasoning string"` |
| Scraper passed as string instead of class | `tests/test_scout_agent.py` | Pass class reference, not string name |
| `needs_enrichment` threshold changed | `tests/test_linkedin.py` | Update assertion to match current logic |
| `sentence-transformers` absent | `tests/test_embedder.py`, `tests/test_semantic_scorer.py` | Add `pytest.importorskip("sentence_transformers")` guard; add `sentence-transformers` to `requirements-dev.txt` so tests run in CI |

### 2b. New tests for coverage (routers + services)

**Routers** (`app/routers/` — 39% → ~70%):  
FastAPI `TestClient` with mocked service dependencies. Cover happy path + primary error branches (404, 422, 503) for:
- `tailor` (analyse, generate-cv, generate-cl, download)
- `coach` (create_session, get_session)
- `jobs` (list, get, approve)
- `applications` (list, get, update status)
- `resume` (upload, parse)

**Services** (`app/services/` — 48% → ~70%):  
Unit tests with mocked LLM client and DB session for:
- `tailor_service` (analyse_jd_text, generate_cv)
- `jd_analyser` (analyse, _fetch_jd validation)
- `email_generator` (generate)
- `job_classifier` (classify)

Target: ~25–35 new test functions across two new test files:  
`tests/test_routers.py` and `tests/test_services.py`

### 2c. Enforce coverage threshold
Add `--cov-fail-under=75` to the pytest invocation in `backend/pyproject.toml` (or `Makefile`). Build fails automatically below threshold.

---

## 3. Security Fixes

### 3a. SSRF — `backend/app/services/jd_analyser.py:_fetch_jd()`

Add `_validate_url(url: str) -> None` before the `httpx` call:
- Allow schemes: `http`, `https` only
- Resolve hostname via `socket.getaddrinfo`
- Block: RFC-1918 private ranges, loopback (`127.x`, `::1`), link-local (`169.254.x`)
- Raise `ValueError` on violation (caught by router's existing 503 handler)
- No new dependency — stdlib `ipaddress` + `socket`

### 3b. Race condition — `backend/app/routers/profile.py:test-connection`

Remove global `os.environ` mutation. Instead, pass the API key directly to the LLM client constructor for the test call. LangChain provider classes (`ChatOpenAI`, `ChatAnthropic`, etc.) accept `api_key=` in their constructor — use that. The restore-on-exit pattern is eliminated entirely.

### 3c. Missing security headers

**Backend** — add `SecurityHeadersMiddleware` to `backend/app/main.py`:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
```
Pure Starlette `BaseHTTPMiddleware` — no new dependency.

**Frontend** — add `headers()` to `frontend/next.config.js`:
```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Referrer-Policy: strict-origin-when-cross-origin
```
Applied to all routes via `source: '/(.*)'`.

### Deferred (next release)
- **Jinja2 autoescape disabled** (`app/prompts/__init__.py`) — prompt injection risk from scraped JD text. Lower priority since prompts are not browser-rendered; documented in CVE report.

---

## 4. Dependency Updates

### 4a. Backend — patch + minor only
- Run `pip list --outdated` inside container; update same-major packages in `requirements.txt`
- Run `pip-audit` after to verify no new CVEs introduced

### 4b. Frontend — patch + minor only
- Run `npm outdated`; update via `npm update` (respects semver ranges)
- Run `npm audit` after to verify

### 4c. Major-version CVE report
For packages where the CVE fix requires a major-version bump, produce `docs/cve-report-2026-06-02.md` listing:
- Package name + current version
- CVE ID + severity
- Fixed-in version
- Estimated migration effort

### 4d. Rebuild container images
After dep updates: rebuild both `job_pilot_v2_backend` and `job_pilot_v2_frontend` podman images and verify with `podman images`.

---

## Execution Order

1. `data/profile.yaml` — switch to phi3:mini  
2. `llm_factory.py` — add `get_json_model()`  
3. `claude_client.py` — use `get_json_model()` in `complete_json()`  
4. `coach.py` — change 500 → 503  
5. Fix 14 failing tests  
6. Write router + service tests  
7. Add `--cov-fail-under=75` to pytest config  
8. SSRF validation in `jd_analyser.py`  
9. Race condition fix in `profile.py`  
10. Security headers middleware + next.config.js  
11. Backend dep updates + `pip-audit`  
12. Frontend dep updates + `npm audit`  
13. Write CVE report  
14. Rebuild podman images  

---

## Out of Scope
- Auto-apply pipeline changes
- Jinja2 autoescape fix (deferred — see CVE report)
- Any UI/UX changes beyond error message wording in coach router
