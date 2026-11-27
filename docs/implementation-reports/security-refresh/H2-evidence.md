# H2 evidence — browser-to-localhost boundary

Task / spec sections / ACs: H2, spec §2, §8 H2, §12, §14.

Baseline SHA → head SHA: `1bc2f9aae0d393b9d5243b72a5484db6806055bc` (origin/main) → this branch, `refresh/h2-local-boundary`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

Claude Code RED commit: not applicable (H2 is not a high-assurance task). No protected test or protected document was edited.

## Files changed

- `backend/app/main.py` — trusted-host, origin-check and bounded rate-limit middleware; constant-time bearer compare.
- `backend/app/config.py` — `HATCH_TRUSTED_HOSTS`, `RATE_LIMIT_MAX_CLIENTS`, and list properties.
- `backend/app/routers/app_lock.py` — cookie `Secure` from the request scheme only; constant-time status bearer compare.
- `backend/app/services/app_lock_service.py` — atomic failed-attempt update with `RETURNING`.
- `frontend/src/middleware.ts` — host allow-list on every request; bearer injection only after the host check.
- `Makefile` — `HOST ?= 127.0.0.1`; `dev-back` uses it.
- `.env.example` — trusted hosts and allowed origins.
- `docs/operations/OPERATIONS.md` — reverse-proxy, trusted-host and LAN development guidance.
- `docs/architecture/SECURITY_SURFACE.md` — app-lock columns for the setup boundary.
- `backend/tests/security/test_local_boundary.py` — backend contract.
- `frontend/src/__tests__/middleware.test.ts` — frontend middleware contract.
- `backend/conftest.py` — test-only `test` host alias for the shared ASGI client; the production default remains the five required hosts.
- `docs/implementation-reports/security-refresh/H2-evidence.md` — this report.

## RED

Backend collection failed before the middleware existed:

```text
$ python -m pytest -q --no-cov tests/security/test_local_boundary.py
ImportError: cannot import name 'OriginCheckMiddleware' from 'app.main'
1 error during collection
```

Frontend middleware test before the host check:

```text
$ npx vitest run src/__tests__/middleware.test.ts
1 failed | 8 passed
FAILED rejects an untrusted host before adding the bearer token
expected 400, received 200
```

## Guard checks (spec §12)

Each guard was disabled locally, the matching test was run, and the source was restored.

| Guard disabled | Matching test(s) | Result |
|---|---|---|
| backend trusted host | evil host and host-before-auth tests | 3 failed |
| origin check | cross-site Origin test | 1 failed |
| constant-time bearer compare | equal-length wrong-token test | 1 failed |
| cookie scheme | untrusted `X-Forwarded-Proto` test | 1 failed |
| setup session boundary | mutating bootstrap routes after setup | 9 failed |
| atomic unlock limit | 10 parallel wrong passwords | 1 failed |
| rate-limiter cap | bounded client-map test | 1 failed |
| frontend trusted host | untrusted-host middleware test | 1 failed |

Restored:

```text
$ python -m pytest -q --no-cov tests/security/test_local_boundary.py
44 passed
```

## GREEN

Backend:

```text
$ python -m pytest -q --no-cov \
    tests/security/test_local_boundary.py \
    tests/test_middleware \
    tests/test_routers/test_app_lock.py \
    tests/test_routers/test_setup_onboarding.py \
    tests/test_routers/test_setup_provider.py \
    tests/test_routers/test_setup_router.py
107 passed

$ ruff check app/ tests/ conftest.py
All checks passed!
```

Full backend suite:

```text
$ python -m pytest -q --no-cov \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4252 passed, 2 skipped in 651.26s
```

The first full run had 13 failures in `tests/runtime/test_cv_tailor_lifecycle.py` because the fresh worktree had no local `backend/app/templates/node_modules` (`Cannot find module 'docx'`). After `npm ci` in that directory, the file passed (17 passed) and the suite was rerun. The two ignored files are the known local CUDA-only suites.

Frontend:

```text
$ npx vitest run src/__tests__/middleware.test.ts
11 passed

$ TZ=UTC npx vitest run
121 files passed, 747 tests passed

$ npx vitest run  # local time
121 files passed, 747 tests passed

$ npm run type-check
exit 0

$ npm run build
exit 0
```

## Setup boundary after password

After a password exists, only these GET routes remain public for the unlock and
onboarding screens:

- `/api/setup/status` — onboarding/setup state read before the unlock page or a retry.
- `/api/setup/providers` — provider catalog used by the onboarding AI form.
- `/api/setup/models/discovery` — local-model discovery used by the onboarding AI form.

All other bootstrap GET routes and every mutating bootstrap route require a
valid app-lock session once a password exists. Before a password exists, the
bootstrap setup routes remain available so onboarding can run; the resume
upload keeps its existing pre-setup exception.

## Live check (test ports only)

Backend on `127.0.0.1:18000`; frontend on `127.0.0.1:13000`; temporary SQLite,
config and profile paths. No request went to ports 3000 or 8000.

```text
backend /api/health                         200
frontend /api/health through proxy          200
backend Host: evil.example                  400  {"detail":"Untrusted host","code":"untrusted_host"}
frontend Host: evil.example                 400  {"error":{"code":"untrusted_host"}}

POST /api/setup/onboarding/progress          200  (before password)
POST /api/app-lock/setup                     200  (cookie set)
PATCH /api/setup/intent                      200  (with session)
POST /api/setup/onboarding/finalize          200  (with session; status complete)
```

The frontend proxy path used `API_URL=http://127.0.0.1:18000`; the default
trusted-host list includes `127.0.0.1` and `backend`, so the real rewrite and
server-side fetch paths remain accepted.

## Repository checks

```text
$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ git diff --check
exit 0

$ make -n dev-back
cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

$ make -n dev-back HOST=0.0.0.0
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Privacy and model calls

- No `data/`, `.env*`, real CV or real document was read; the live check used synthetic data and temporary paths.
- No model calls were made in the tests or live check.
- Error responses use fixed codes and do not echo the rejected host or origin.

## Migration

Not applicable: no schema or stored-data change.

## Not run / known limits

- The full suite excludes the two known CUDA-only test files.
- The test-only `backend/conftest.py` adds the `test` host alias used by the shared ASGI client; production uses the configured/default list.
- The SECURITY_SURFACE app-lock columns were updated in place; the H0 generator script is outside this task's file list.

Ready for review: yes.
