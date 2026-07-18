---
title: Hatch Backend Container Optimisation Spec
document_type: implementation-spec
status: active
implementation_status: partial
applies_to: main
last_verified: 2026-07-10
supersedes: []
superseded_by: []
---

> [!IMPORTANT]
> This specification is partially implemented. See the implementation-status table below before using it as a current product reference.

# Hatch Backend Container Optimisation Spec

## Implementation status

| Slice | Status | Evidence |
|---|---|---|
| Spec and measurement audit | Complete | Reflected in the current document content on `main` |
| Lightweight backend target and compose shape | Complete | `docker-compose.yml` and `docker-compose.easy.yml` build backend `target: core` |
| Optional backend capability profile flow | Complete | `install.sh`, `install.ps1`, and `scripts/hatch_cli.py` manage backend profiles |
| Remaining optimisation and measurement follow-up | Partial | Current repo still documents decision-gated follow-up work in this spec |

**Target repo:** `https://github.com/arvindsoni2/hatch`
**Primary objective:** reduce Hatch backend image size and rebuild time without changing default product behaviour for users.
**Audience:** Codex implementation agent
**Status:** Audited against current implementation; implementation must wait for the decision gates below.

---

## 0. Audit addendum - actual implementation snapshot

Date audited: 2026-07-08

This spec was re-checked against the current repository before implementation. The original direction is broadly correct, but several assumptions need to be made explicit before coding because the change touches installer flows, Compose overlays, the host CLI, CI dependency audit, and existing feature fallbacks.

Graphify was used as the repository mapping boundary for this audit. The current graphify detector recognises the `docs/` corpus as:

```text
135 supported files
384,273 words
8 code-like files
54 document files
73 image files
0 sensitive files skipped
```

The single target spec is a markdown document, so semantic graph generation was not available through the current tool surface. The audit therefore used the graphify corpus boundary plus direct validation of Docker, Compose, scripts, installers, README, and backend optional-dependency import paths.

### 0.1 Confirmed current Docker measurements

Local image sizes currently match the problem statement:

```text
hatch-backend:latest                         7.48GB
hatch-frontend:latest                        207MB
ghcr.io/ggml-org/llama.cpp:server            855MB
moby/buildkit:buildx-stable-1                243MB
```

`docker history hatch-backend:latest` confirms the main runtime layers:

```text
COPY /install /usr/local # buildkit          6.18GB
COPY /ms-playwright /ms-playwright # buildkit 670MB
COPY /usr/lib /usr/lib # buildkit            234MB
RUN apt-get install ...                      270MB
COPY app source                              11.5MB
```

The backend source tree itself is small relative to the image size:

```text
backend/                                     20MB
frontend/                                    1.2GB local checkout, mostly local/dev artefacts
repository checkout                          3.7GB
```

### 0.2 Validated assumptions

| Area | Audit result | Spec impact |
|---|---|---|
| Backend image bloat | Confirmed. `backend/Dockerfile` installs `requirements.txt`, then `requirements-perception.txt`, then copies Playwright browser binaries and broad system library directories into the final runner. | Keep the default-core image goal. The current image is a single full-capability runtime. |
| Playwright | Confirmed as default image content. The Dockerfile installs browser runtime packages, runs `playwright install chromium`, copies `/ms-playwright`, `/usr/lib`, and `/lib`, and installs browser packages again in the runner. | Browser capability must be opt-in or explicitly accepted as part of a full image. The default target must not copy browser system libraries wholesale. |
| Semantic embeddings | Confirmed as default image content. `backend/requirements.txt` includes `sentence-transformers>=5.0,<6.0` and `transformers>=5.0.0,<6.0`; the Dockerfile uses the CPU PyTorch index. | Splitting local embeddings out of core is valid, but note that semantic scoring already has a deterministic fallback path when embeddings are unavailable. |
| Perception | Confirmed as default image content. `backend/requirements-perception.txt` is installed by default in the Dockerfile. | The file already exists, but it is not optional in the current image. The implementation should stop installing it in the default target. |
| Optional import guards | Partially better than assumed. Playwright scrapers import `async_playwright` inside scraper methods and skip if missing. Perception services mostly lazy import or set optional modules to `None`. The semantic scorer is import-tolerant and falls back to local scoring on embedding runtime errors. | Do not over-scope this PR into broad app rewrites. Required code changes should focus on import-time smoke tests and any missing guards found after the requirements split. |
| Default Compose | `docker-compose.yml` builds `hatch-backend:latest` and starts `llm-primary` plus `llm-triage` by default. Models are mounted from `./data/models`, not baked into images. | Preserve legacy developer compose behaviour unless the decision gate below changes it. Any default target change must keep `backend` service name and `hatch-backend` container name stable. |
| Easy install Compose | `docker-compose.easy.yml` also builds `hatch-backend:latest`, but does not start local llama.cpp services. It mounts `${HATCH_HOME}/config` and `${HATCH_HOME}/models`. | Easy install is the highest-impact path. It should receive the lightweight backend first, with local LLM services remaining controlled by `docker-compose.local-ai.yml`. |
| Local AI Compose overlay | `docker-compose.local-ai.yml` currently means "llama.cpp local model services", not "Python local embeddings". | Do not reuse this file name for Python `sentence-transformers` unless the product decision intentionally merges those concepts. Prefer a clearly named backend profile/override such as browser/full/embeddings if needed. |
| Installers | `install.sh` and `install.ps1` both run `docker compose -f docker-compose.easy.yml up -d --build`. Local mode then runs `hatch probe` and `hatch models install`; it does not switch backend image capability. | Installer docs and scripts must stay compatible with the easy compose file and must not require users to understand image targets during first install. |
| Host CLI | `scripts/hatch_cli.py` composes with `docker-compose.easy.yml`, layering `docker-compose.local-ai.yml` only when runtime AI mode is local. `hatch update` validates easy compose and restarts with `--build`. | Any optional backend override must be represented in the host CLI only after a product-level decision. Keep `hatch status`, `hatch update`, and model install behaviour stable. |
| Makefile/developer commands | `make docker-build`, `make docker-up`, and `make docker-restart` use the default `docker-compose.yml`. | Developer commands should continue to build/start with one command. If the default image tag changes, these commands and README snippets need matching updates. |
| Systemd service | `infrastructure/systemd/hatch.service` runs `docker compose up -d --no-build` from the checkout. | If image tags/targets change, installers must ensure the right image exists before systemd starts. Service file likely does not need a target-specific change if Compose remains the source of truth. |
| CI | `.github/workflows/ci.yml` does not build Docker images. It installs `backend/requirements-dev.txt` for tests and runs a non-blocking `pip-audit -r backend/requirements.txt`. | Splitting requirements affects audit coverage. CI should audit all runtime requirement groups or a generated/full requirements file, otherwise heavy optional deps can drift unaudited. |
| Frontend | `frontend/Dockerfile` uses Next standalone output and `node:20-alpine`. It currently runs `npm ci --frozen-lockfile 2>/dev/null || npm install`; frontend `.dockerignore` is minimal. | Frontend is not the root cause. Keep changes low-risk: deterministic `npm ci` and safer ignore rules only. |
| Docker ignore | `backend/.dockerignore` excludes DBs, caches, `.env`, and `data/`, but still omits common build/test/local artefacts. `frontend/.dockerignore` is also minimal. | Expanding ignore files is valid, but verify runtime-required files are still included, especially `locales/`, templates, Alembic files, and examples used by tests/docs. |

### 0.3 Decision gates before implementation

Implementation should not begin until these decisions are accepted:

1. **Default image identity:** keep `image: hatch-backend:latest` pointing at the lightweight core target, or introduce `hatch-backend:core` and update every compose/script/doc reference. Recommendation: keep the service/container names stable and strongly consider keeping `hatch-backend:latest` as the default lightweight image to avoid breaking scripts and systemd.
2. **Meaning of "local AI":** distinguish bundled llama.cpp services from Python local embeddings. Current `docker-compose.local-ai.yml` is already used for llama.cpp model services. Recommendation: do not overload it with `sentence-transformers`; add a separate backend capability target/override if local embeddings remain opt-in.
3. **Browser scraping default:** decide whether losing Playwright-backed boards in the default image is acceptable. Current scrapers skip cleanly when Playwright is absent, but that may reduce job source coverage. Recommendation: lightweight default can skip browser-only scrapers if the UI/docs make the capability explicit.
4. **Semantic scoring default:** decide whether deterministic local scoring plus LLM scoring is acceptable when `sentence-transformers` is absent. Current code can fall back, but semantic golden tests use real `sentence-transformers`. Recommendation: default image should run without embeddings; optional embeddings image/profile should preserve the richer scoring path.
5. **Perception default:** decide whether Coach ASR/voice analysis must work out of the box. `data/profile.yaml` currently defaults ASR to `faster_whisper`; if the default image excludes perception deps, the runtime must either default to browser/web speech, show a clear unavailable-feature message, or require an optional full/perception image for those flows.
6. **CI audit strategy:** decide whether CI should audit `requirements-core.txt` plus optional groups, or a generated `requirements-full.txt`. Recommendation: audit all runtime dependency groups, even if optional installs are not tested in every CI run.
7. **PR slicing:** decide whether this is one larger backend-container PR or multiple smaller PRs. Recommendation: split into at least measurement/spec, dependency/import guards, Docker/Compose, and docs/install verification if the branch starts to grow.

### 0.4 Impact analysis checklist

The implementation plan must account for these files and behaviours:

```text
backend/Dockerfile
backend/requirements.txt
backend/requirements-perception.txt
backend/.dockerignore
backend/app/agents/scorer_agent.py
backend/app/agents/tools/embedder.py
backend/app/agents/tools/semantic_scorer.py
backend/app/agents/tools/perception_factory.py
backend/app/services/transcriber.py
backend/app/services/voice_emotion_analyser.py
backend/app/scrapers/cwjobs.py
backend/app/scrapers/contractoruk.py
backend/app/scrapers/jobserve.py
docker-compose.yml
docker-compose.easy.yml
docker-compose.local-ai.yml
frontend/Dockerfile
frontend/.dockerignore
install.sh
install.ps1
hatch
hatch.ps1
scripts/hatch_cli.py
scripts/reset-app-lock.sh
scripts/reset-user-data.sh
scripts/verify_runtime.sh
Makefile
README.md
infrastructure/systemd/hatch.service
.github/workflows/ci.yml
```

Special compatibility risks:

- Scripts and reset flows refer to the `hatch-backend` container by name. Keep that container name stable.
- `hatch_cli.py` treats `docker-compose.local-ai.yml` as the local llama.cpp overlay. Do not silently change its meaning.
- Easy install should remain beginner-safe and should not require GGUF files unless the user explicitly chooses local models.
- Systemd uses `--no-build`; users must have a built image matching the Compose file before enabling it.
- CI currently audits only `backend/requirements.txt`; splitting dependencies without CI updates weakens security visibility.
- README currently documents manual Docker install as `scripts/fetch_models.sh` plus `docker compose up -d --build`; easy install documents `hatch models install`. Both paths need matching language after image/profile changes.

### 0.5 Updated implementation posture

Treat this as a packaging/product-behaviour change, not a pure Docker cleanup.

Recommended PR sequence:

1. **PR A - measurement/spec only:** keep this audit in the spec and capture current size/history evidence.
2. **PR B - dependency split and import smoke tests:** add requirement groups, prove the app can import/start without optional browser/embedding/perception packages, and keep fallbacks explicit.
3. **PR C - Docker targets and Compose defaults:** make the default backend lightweight while preserving service/container names, install paths, and easy-install behaviour.
4. **PR D - optional capability profiles/docs:** add browser/local-embeddings/full backend targets or overrides only after the product decisions above are locked.
5. **PR E - installer/CI polish if needed:** update `hatch_cli.py`, README, CI dependency audit coverage, and validation scripts once the target structure is stable.

---

## 1. Problem statement

The current Hatch Docker stack works, but the backend runtime image is much larger than it needs to be for the default local/self-hosted workflow.

Observed from local Docker history:

```text
hatch-backend:latest                virtual 7.49GB
hatch-frontend:latest               virtual 207MB
ghcr.io/ggml-org/llama.cpp:server   virtual 855MB
moby/buildkit:buildx-stable-1        virtual 243MB
```

The frontend and BuildKit images are not the main issue. The backend image is the main optimisation target.

The backend currently combines several capability groups into one runtime image:

- Core API server
- Database/migrations
- Job/profile/document workflows
- Scraping dependencies
- Playwright/Chromium browser runtime
- Local semantic scoring via `sentence-transformers` / `transformers` / `torch`
- Perception stack via `faster-whisper`, `transformers`, `torch`

This creates a large default image even for users who only need the normal API + UI + local llama.cpp model workflow.

---

## 2. Current known bloat sources

From local `docker history -H hatch-backend:latest`:

```text
COPY /install /usr/local # buildkit             6.18GB
COPY /ms-playwright /ms-playwright # buildkit   670MB
COPY /usr/lib /usr/lib # buildkit               234MB
RUN apt-get install ...                         270MB
COPY app source                                 11.5MB
```

Root causes:

1. Python dependencies are installed into one large `/install` tree.
2. Heavy AI/perception dependencies are installed in the default backend image.
3. Playwright browser binaries are copied into the default backend image.
4. `/usr/lib` and `/lib` are copied wholesale from the Playwright stage.
5. Runtime image also installs browser/system packages again.
6. Frontend Dockerfile is mostly good, but can be made more deterministic.
7. `.dockerignore` files are minimal and should exclude more non-runtime files.

---

## 3. Goals

### G1. Reduce default backend image size

The default backend image should be a **core runtime** image, not a full AI/browser/perception image.

Target outcome:

```text
hatch-backend:core <= 1.5GB preferred
hatch-backend:core <= 2.0GB maximum acceptable for this PR
```

The exact final size may vary by platform, but the image should no longer contain Playwright browser binaries, Whisper, Torch, Transformers, or sentence-transformers unless explicitly requested by an optional profile.

### G2. Preserve current default user experience

The default compose flow must still start successfully:

```bash
docker compose up -d --build
```

Required default behaviour:

- Frontend starts on `127.0.0.1:3000`
- Backend starts on `127.0.0.1:8000`
- Backend health endpoint is healthy
- SQLite data remains mounted at `/app/data`
- llama.cpp services still mount GGUF models externally from `./data/models`
- No model weights are baked into Hatch images

### G3. Make heavy features opt-in

The following should become optional capability groups:

- Browser scraping / Playwright
- Local semantic embeddings
- Perception / voice / Whisper stack

Optional capability images may remain large, but the default backend image must not include them.

### G4. Improve rebuild time

Use BuildKit cache mounts and dependency layering so common rebuilds do not reinstall all Python and Node dependencies.

### G5. Keep implementation simple and maintainable

Prefer clear Dockerfiles and requirements files over clever micro-optimisations.

---

## 4. Non-goals

Do **not** optimise these in this PR unless trivial:

1. `moby/buildkit:buildx-stable-1` image size.
2. `ghcr.io/ggml-org/llama.cpp:server` image internals.
3. GGUF model sizes.
4. Application feature refactors unrelated to dependency/image splitting.
5. GPU/CUDA serving images.
6. Full CI publishing to GHCR, unless already simple and low-risk.

---

## 5. Current repo files to inspect first

Codex should inspect these files before editing:

```text
backend/Dockerfile
backend/requirements.txt
backend/requirements-perception.txt
backend/.dockerignore
frontend/Dockerfile
frontend/.dockerignore
docker-compose.yml
docker-compose.easy.yml
scripts/
README.md
```

Also search for imports/usages of optional dependencies:

```bash
rg "playwright|sentence_transformers|sentence-transformers|transformers|torch|faster_whisper|whisper|perception|browser|chromium" backend
```

---

## 6. Proposed dependency split

Create separate requirement files.

### 6.1 `backend/requirements-core.txt`

Move default runtime dependencies here.

Should include only the dependencies needed for:

- FastAPI backend
- Uvicorn
- DB and migrations
- Pydantic/settings
- HTTP requests
- HTML parsing that does not require browser automation
- scheduling
- utilities
- LangGraph / LangChain provider abstractions
- document parsing
- rapidfuzz / deterministic scoring

Candidate content based on current `requirements.txt`:

```text
# Web framework
fastapi==0.136.3
uvicorn[standard]==0.48.0
python-multipart>=0.0.9
bcrypt>=4.1.0

# Database
sqlalchemy[asyncio]==2.0.50
aiosqlite==0.22.1
alembic==1.18.4

# Data validation
pydantic==2.13.4
pydantic-settings==2.14.2

# HTTP and non-browser parsing
httpx==0.28.1
beautifulsoup4==4.14.3
lxml>=5.3.0

# Scheduling
apscheduler==3.11.2

# Utilities
icalendar>=5.0.0
jinja2==3.1.6
python-dotenv==1.2.2
rapidfuzz==3.14.5
pyyaml==6.0.3
aiosmtplib==3.0.1

# Agentic pipeline / LangGraph
langgraph>=1.0.10,<2.0
langgraph-checkpoint>=4.0.0,<5.0
langgraph-checkpoint-sqlite>=3.0.0,<4.0

# LangChain provider abstractions
langchain>=1.3.9,<2.0
langchain-core>=1.2.31,<2.0
langchain-anthropic>=1.0.0,<2.0
langchain-openai>=1.1.14,<2.0
langchain-google-genai>=3.0.0,<5.0
langchain-ollama>=1.0.0,<2.0

# Document parsing
python-docx>=1.1.0
pypdf>=4.0.0
```

Important: do **not** include these in core:

```text
playwright
sentence-transformers
transformers
torch
faster-whisper
tokenizers
```

### 6.2 `backend/requirements-browser.txt`

Create a browser capability requirements file:

```text
-r requirements-core.txt
playwright==1.60.0
```

This image/profile should be used only when browser automation is enabled.

### 6.3 `backend/requirements-local-ai.txt`

Create a local semantic scoring capability requirements file:

```text
-r requirements-core.txt
sentence-transformers>=5.0,<6.0
transformers>=5.0.0,<6.0
```

Install using the CPU-only PyTorch wheel index where applicable.

### 6.4 `backend/requirements-perception.txt`

Keep this file, but make sure it is only used by an explicit perception/full image.

Current contents can stay broadly similar:

```text
faster-whisper>=1.0.3
tokenizers>=0.19.0,<0.20
transformers>=4.35.0
torch>=2.0.0
```

Do not install this in the default backend image.

### 6.5 Optional `backend/requirements-full.txt`

If maintaining one full image is useful for advanced users, create:

```text
-r requirements-core.txt
-r requirements-browser.txt
-r requirements-local-ai.txt
-r requirements-perception.txt
```

Avoid duplicate `-r requirements-core.txt` expansion if pip resolver complains. If duplication is noisy, define the full file explicitly.

---

## 7. Dockerfile strategy

There are two acceptable implementation approaches.

### Option A — preferred: one Dockerfile with named targets

Refactor `backend/Dockerfile` to expose these targets:

```text
core
browser
local-ai
full
```

Default target should be `core`.

Advantages:

- One Dockerfile to maintain.
- Compose can choose target via `build.target`.
- Shared base stages reduce duplication.

### Option B: multiple Dockerfiles

Create:

```text
backend/Dockerfile.core
backend/Dockerfile.browser
backend/Dockerfile.local-ai
backend/Dockerfile.full
```

This is acceptable if it keeps the implementation clearer.

### Required default

`docker-compose.yml` and `docker-compose.easy.yml` must use the default/core backend image unless they intentionally enable advanced mode.

---

## 8. Backend core Dockerfile requirements

The default backend image must:

1. Use a slim Python base.
2. Install only core Python dependencies.
3. Avoid Playwright browser installation.
4. Avoid copying `/ms-playwright`.
5. Avoid copying `/usr/lib` and `/lib` from any browser stage.
6. Avoid installing `nodejs` and `npm` unless proven necessary for core runtime.
7. Keep app running as non-root user.
8. Continue using `/app/data` for persistent data.
9. Preserve existing `entrypoint.sh` behaviour.

Suggested shape:

```dockerfile
# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS core-builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-core.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements-core.txt

FROM python:3.12-slim-bookworm AS core
WORKDIR /app

ENV LANGGRAPH_STRICT_MSGPACK=true

COPY --from=core-builder /install /usr/local

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app /app/data

COPY --chown=appuser:appuser . .
COPY --chown=appuser:appuser entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

USER appuser
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
```

Notes:

- Validate whether `gcc` and `libpq-dev` are actually required by core deps. If not needed, remove them.
- Consider installing build deps only in builder and not runtime.
- Do not run `chown -R` after copying large application directories. Use `COPY --chown`.

---

## 9. Browser image requirements

If browser scraping must remain available, implement it as an opt-in image/target.

Acceptable patterns:

### Pattern A — backend browser target

A `browser` target extends core and installs Playwright + Chromium.

Requirements:

- Use `requirements-browser.txt`.
- Run `playwright install chromium` only in the browser target.
- Do not copy `/usr/lib` and `/lib` wholesale unless there is no alternative.
- Prefer installing only the exact required runtime packages.
- Keep `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`.

### Pattern B — separate browser worker service

Create a separate browser/scraper service that owns Playwright and browser dependencies.

The core backend calls the browser service for browser-only extraction.

This is architecturally cleaner, but may require more app changes. For this PR, use Pattern A unless the existing code already supports a clean service split.

---

## 10. Local AI / semantic scoring requirements

Local semantic scoring must become optional.

Implementation requirements:

1. Core backend must start without `sentence-transformers`, `transformers`, or `torch` installed.
2. Any imports of these libraries must be lazy imports inside the local semantic scoring path.
3. If local embeddings are requested but dependencies are missing, return a clear feature-unavailable error or fall back to deterministic scoring.
4. Default scoring should still work using deterministic/rule-based logic and `rapidfuzz`.

Recommended environment flag:

```text
HATCH_LOCAL_EMBEDDINGS_ENABLED=false
```

or reuse an existing AI mode/config flag if already present.

Expected behaviour:

```text
Default/core image:
- deterministic matching works
- cloud LLM providers work if configured
- llama.cpp chat/scoring paths work if they do not require torch
- local sentence-transformer embeddings are disabled or unavailable with a clear message

local-ai image:
- local sentence-transformer embeddings work
```

---

## 11. Perception requirements

Perception dependencies must be excluded from the default backend image.

Implementation requirements:

1. Core image must not install `requirements-perception.txt`.
2. Perception imports must be lazy or guarded.
3. If perception features are called in core mode, return a clear unavailable-feature message.
4. Full/perception image may keep the existing dependency set.
5. Whisper model cache should remain external under `/app/data/models` if perception mode is enabled.

---

## 12. Docker Compose changes

Update `docker-compose.yml` so backend uses the core target by default.

Example:

```yaml
backend:
  image: hatch-backend:core
  build:
    context: ./backend
    dockerfile: Dockerfile
    target: core
```

If optional images are implemented, add compose override files:

```text
docker-compose.browser.yml
docker-compose.local-ai.yml
docker-compose.full.yml
```

Example browser override:

```yaml
services:
  backend:
    image: hatch-backend:browser
    build:
      context: ./backend
      dockerfile: Dockerfile
      target: browser
    environment:
      - PLAYWRIGHT_HEADLESS=true
      - HATCH_BROWSER_ENABLED=true
```

Example local AI override:

```yaml
services:
  backend:
    image: hatch-backend:local-ai
    build:
      context: ./backend
      dockerfile: Dockerfile
      target: local-ai
    environment:
      - HATCH_LOCAL_EMBEDDINGS_ENABLED=true
```

Example full override:

```yaml
services:
  backend:
    image: hatch-backend:full
    build:
      context: ./backend
      dockerfile: Dockerfile
      target: full
    environment:
      - PLAYWRIGHT_HEADLESS=true
      - HATCH_BROWSER_ENABLED=true
      - HATCH_LOCAL_EMBEDDINGS_ENABLED=true
      - HATCH_PERCEPTION_ENABLED=true
```

Do not make optional heavy profiles active by default.

---

## 13. llama.cpp image handling

Do not change llama.cpp internals in this PR.

However, update compose comments or docs to recommend pinning the image tag/digest for reproducibility.

Current shape is acceptable because models are mounted externally:

```yaml
volumes:
  - ./data/models:/models:ro
```

Required rule:

```text
Never bake GGUF model files into Hatch service images.
```

Optional improvement:

```yaml
image: ghcr.io/ggml-org/llama.cpp:server-b9894
```

Only pin if a known stable tag is already documented or tested. Do not guess a tag if unverified.

---

## 14. Frontend improvements

Frontend is already reasonably optimised with Next standalone output and `node:20-alpine`.

Make only low-risk changes.

### 14.1 Make dependency install deterministic

Current pattern:

```dockerfile
RUN npm ci --frozen-lockfile 2>/dev/null || npm install
```

For npm projects, replace with:

```dockerfile
RUN --mount=type=cache,target=/root/.npm npm ci
```

Reason:

- `npm ci` should be deterministic.
- Falling back to `npm install` can hide lockfile drift.
- `--frozen-lockfile` is not the standard npm flag.

### 14.2 Keep standalone runtime pattern

Do not regress this pattern:

```dockerfile
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
```

---

## 15. `.dockerignore` improvements

### 15.1 Backend `.dockerignore`

Expand `backend/.dockerignore`.

Suggested content:

```dockerignore
.git
.gitignore

# Python caches
__pycache__/
**/__pycache__/
*.pyc
*.pyo
*.pyd

# Virtual environments
.venv/
venv/
env/

# Test and tooling caches
.pytest_cache/
.ruff_cache/
.mypy_cache/
.coverage
coverage.xml
htmlcov/

# Runtime data and local DBs
data/
**/*.db
**/*.db-shm
**/*.db-wal

# Logs/temp
*.log
*.tmp
.tmp/
tmp/

# Build artefacts
dist/
build/
*.egg-info/

# Secrets and local config
.env
.env.*
!.env.example

# Optional local model/cache artefacts
models/
.cache/
```

Validate that excluding these does not remove files required by runtime.

### 15.2 Frontend `.dockerignore`

Suggested additions:

```dockerignore
.git
.gitignore
node_modules/
.next/
out/
dist/
build/
coverage/
playwright-report/
test-results/
.vitest/
*.log
npm-debug.log*
.env
.env.*
!.env.example
```

---

## 16. Build speed improvements

Use BuildKit cache mounts where safe.

### Python pip cache

```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements-core.txt
```

Note: `--no-cache-dir` means pip does not store wheels in the final layer. The BuildKit cache mount can still help where pip uses cache during the build. If this does not materially help, remove `--no-cache-dir` only if cache content is definitely not baked into the final image.

### Optional uv migration

`uv` may improve build speed, but do not introduce it if it increases complexity.

Acceptable optional pattern:

```dockerfile
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --prefix=/install -r requirements-core.txt
```

Use pip first if that is safer for the current project.

### npm cache

```dockerfile
RUN --mount=type=cache,target=/root/.npm npm ci
```

---

## 17. App code changes required for optional dependencies

Codex must search for top-level imports of heavy optional packages.

Problem pattern:

```python
from sentence_transformers import SentenceTransformer
import torch
from playwright.async_api import async_playwright
```

If these exist at module import time in code loaded by the core backend, the core image will fail.

Required pattern:

```python
def get_local_embedding_model(...):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise FeatureUnavailableError(
            "Local embeddings are not installed in this backend image. "
            "Use the local-ai backend profile or disable local embeddings."
        ) from exc
```

For Playwright:

```python
async def run_browser_scrape(...):
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise FeatureUnavailableError(
            "Browser scraping is not installed in this backend image. "
            "Use the browser/full backend profile or disable browser scraping."
        ) from exc
```

For perception:

```python
def get_transcriber(...):
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise FeatureUnavailableError(
            "Perception/ASR dependencies are not installed in this backend image. "
            "Use the full/perception backend profile."
        ) from exc
```

Do not silently crash during app startup because an optional dependency is missing.

---

## 18. Backward compatibility

Existing users running the full image may rely on browser scraping or local embeddings.

Therefore:

1. Keep an opt-in full/advanced image path.
2. Document how to enable it.
3. Keep default install lightweight.
4. Avoid removing feature code.
5. Avoid changing database schema unless absolutely necessary.

Suggested docs wording:

```text
By default, Hatch uses the lightweight backend image. Browser automation, local sentence-transformer embeddings, and perception/voice features are available through optional backend profiles.
```

---

## 19. Tests and validation

### 19.1 Local build validation

Run:

```bash
docker compose build --no-cache backend
```

Then:

```bash
docker images hatch-backend:core
```

Expected:

```text
hatch-backend:core <= 2.0GB
```

### 19.2 Default stack validation

Run:

```bash
docker compose up -d --build
```

Then:

```bash
docker ps --size
curl -f http://127.0.0.1:8000/api/health
curl -f http://127.0.0.1:3000
```

Expected:

- backend healthy
- frontend healthy
- no missing optional dependency error during startup
- llama.cpp services still start
- models are mounted, not baked

### 19.3 Optional profile validation

If browser/local-ai/full profiles are added, validate each:

```bash
docker compose -f docker-compose.yml -f docker-compose.browser.yml build backend
docker compose -f docker-compose.yml -f docker-compose.browser.yml up -d backend
```

```bash
docker compose -f docker-compose.yml -f docker-compose.local-ai.yml build backend
docker compose -f docker-compose.yml -f docker-compose.local-ai.yml up -d backend
```

```bash
docker compose -f docker-compose.yml -f docker-compose.full.yml build backend
docker compose -f docker-compose.yml -f docker-compose.full.yml up -d backend
```

Expected:

- Browser profile can import Playwright.
- Local AI profile can import sentence-transformers.
- Full profile can import perception dependencies.
- Core profile cannot import heavy optional packages at startup, but still runs.

### 19.4 Import smoke tests

Inside the core backend container:

```bash
docker exec hatch-backend python - <<'PY'
import fastapi
import sqlalchemy
import pydantic
import httpx
print("core imports ok")
PY
```

Also verify optional heavy packages are absent in core:

```bash
docker exec hatch-backend python - <<'PY'
import importlib.util
for name in ["playwright", "sentence_transformers", "transformers", "torch", "faster_whisper"]:
    print(name, importlib.util.find_spec(name) is not None)
PY
```

Expected for core:

```text
playwright False
sentence_transformers False
transformers False
torch False
faster_whisper False
```

If any are still present, investigate transitive dependency leakage.

### 19.5 Frontend validation

```bash
docker compose build frontend
docker compose up -d frontend
curl -f http://127.0.0.1:3000
```

Expected:

- Next.js standalone runtime still works.
- No `node_modules` copied into final runtime except what standalone output includes.

---

## 20. Suggested size-report script

Add optional script:

```text
scripts/report_docker_sizes.sh
```

Suggested content:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "== Docker image sizes =="
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' \
  | grep -E 'hatch|llama.cpp|buildkit' || true

echo
echo "== Running container sizes =="
docker ps --size --format 'table {{.Names}}\t{{.Image}}\t{{.Size}}'

echo
echo "== Backend history =="
docker history -H hatch-backend:core || docker history -H hatch-backend:latest || true
```

Make executable:

```bash
chmod +x scripts/report_docker_sizes.sh
```

---

## 21. Acceptance criteria

Codex implementation is acceptable when all are true:

1. Default backend no longer installs `requirements-perception.txt`.
2. Default backend no longer installs Playwright/Chromium.
3. Default backend no longer installs `sentence-transformers`, `transformers`, or `torch` directly.
4. Default backend image size is reduced to `<= 2.0GB` or Codex explains exactly why not.
5. `docker compose up -d --build` works with the default lightweight backend.
6. Backend health endpoint passes.
7. Frontend health check passes.
8. Optional features fail gracefully when not installed.
9. Optional browser/local-ai/full profiles are documented if added.
10. `.dockerignore` files are expanded safely.
11. Frontend Dockerfile remains standalone-mode based.
12. No GGUF model files are copied into any Docker image.
13. No broad `COPY /usr/lib /usr/lib` or `COPY /lib /lib` exists in the default backend target.
14. Existing bind mounts for `/app/data` and `/app/locales` remain functional.

---

## 22. Implementation sequence for Codex

Follow this sequence to reduce risk.

### Phase 1 — audit imports and requirements

1. Inspect current backend imports.
2. Identify top-level imports of optional heavy dependencies.
3. Create requirements split files.
4. Do not change Dockerfile yet.

### Phase 2 — make optional dependency imports lazy

1. Guard Playwright imports.
2. Guard local embeddings imports.
3. Guard perception imports.
4. Add clear unavailable-feature errors or fallbacks.
5. Run backend tests/import checks locally if available.

### Phase 3 — refactor backend Dockerfile

1. Add core target.
2. Add optional browser/local-ai/full targets if needed.
3. Remove Playwright and perception from default target.
4. Remove broad library copying from default target.
5. Preserve non-root user and entrypoint behaviour.

### Phase 4 — compose and docs

1. Point default compose backend to core target.
2. Add optional override compose files if implemented.
3. Update README or install docs with profile explanation.
4. Add size-report script if useful.

### Phase 5 — validation

Run:

```bash
docker compose build --no-cache backend
docker compose up -d --build
curl -f http://127.0.0.1:8000/api/health
curl -f http://127.0.0.1:3000
scripts/report_docker_sizes.sh || true
```

Capture before/after image sizes in the implementation summary.

---

## 23. Codex review prompt

Use this prompt when asking Codex to review/implement:

```text
You are working in the Hatch repo.

Goal: reduce backend Docker image size and build time by making the default backend image lightweight.

Read docs/implementation-specs/active/Hatch_Backend_Container_Optimisation_Spec.md fully before editing.

Current problem:
- hatch-backend:latest is around 7.49GB.
- The largest layers come from /install (~6.18GB), /ms-playwright (~670MB), copied /usr/lib (~234MB), and runtime apt packages (~270MB).
- The default backend currently includes Playwright/Chromium, local semantic scoring dependencies, and perception/voice dependencies.

Implement a safe phased optimisation:
1. Split backend requirements into core/browser/local-ai/perception capability groups.
2. Make heavy optional imports lazy/guarded so the core backend starts without Playwright, torch, transformers, sentence-transformers, or faster-whisper installed.
3. Refactor backend Dockerfile so the default target is a lightweight core image.
4. Keep optional browser/local-ai/full image targets or compose overrides if needed.
5. Update docker-compose.yml so default backend uses the core target.
6. Expand .dockerignore files safely.
7. Keep frontend standalone Docker pattern; only make low-risk deterministic/cache improvements.
8. Do not bake GGUF model files into any image.
9. Preserve existing default docker compose startup and health checks.
10. Add or update docs explaining lightweight default and optional heavy profiles.

Acceptance criteria:
- docker compose up -d --build works.
- backend health endpoint passes.
- frontend health endpoint passes.
- core backend image is <= 2.0GB or explain exactly why not.
- core backend does not include Playwright, Chromium, torch, transformers, sentence-transformers, or faster-whisper unless required transitively and explained.
- optional features fail gracefully when unavailable.
- no broad COPY /usr/lib /usr/lib or COPY /lib /lib remains in the default backend target.

Before making changes, produce an implementation plan listing files to modify and risks. After changes, report exact before/after image sizes and validation commands/results.
```

---

## 24. Notes for reviewer

This optimisation should be treated as product polish, not only technical cleanup.

Why it matters:

- Smaller image improves first install experience.
- Smaller default backend makes Hatch feel more credible as a local self-hosted product.
- Faster rebuilds reduce developer friction.
- Optional heavy profiles preserve advanced capability without penalising normal users.

Recommended final product posture:

```text
Default Hatch = lightweight, local-first, easy to install.
Advanced Hatch = opt-in browser automation, local embeddings, and perception features.
```
