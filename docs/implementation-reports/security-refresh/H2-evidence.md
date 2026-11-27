# H2 evidence — browser-to-localhost boundary

Task / spec sections / ACs: H2, spec §2, §8 H2, §12, §14. Repair cycle 1 adds the unlock reservation, the narrowed setup boundary, proxy/trusted-host documentation and the Compose frontend setting.

Baseline SHA → head SHA: `1bc2f9aae0d393b9d5243b72a5484db6806055bc` (origin/main) → this branch, `refresh/h2-local-boundary`. Repair cycle 1 starts from `b345a65`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

Claude Code RED commit: not applicable (H2 is not a high-assurance task). No protected test or protected document was edited.

## Files changed

- `backend/app/main.py` — trusted-host, origin-check and bounded rate-limit middleware; constant-time bearer compare; setup session boundary.
- `backend/app/config.py` — `HATCH_TRUSTED_HOSTS`, `RATE_LIMIT_MAX_CLIENTS`, list properties, and the `[::1]` origin.
- `backend/app/routers/app_lock.py` — cookie `Secure` from the request scheme only; constant-time status bearer compare.
- `backend/app/services/app_lock_service.py` — reserve an unlock attempt atomically before checking the password; reset on success.
- `frontend/src/middleware.ts` — host allow-list on every request; bearer injection only after the host check.
- `Makefile` — `HOST ?= 127.0.0.1`; `dev-back` uses it.
- `.env.example` — trusted hosts, allowed origins and the optional `FORWARDED_ALLOW_IPS`.
- `docker-compose.yml`, `docker-compose.easy.yml` — pass `HATCH_TRUSTED_HOSTS` to the frontend service.
- `docs/operations/OPERATIONS.md` — reverse-proxy, trusted-host and LAN development guidance.
- `docs/architecture/SECURITY_SURFACE.md` — app-lock columns for the setup boundary.
- `backend/tests/security/test_local_boundary.py` — backend contract, including the repair-cycle unlock tests.
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
| repair: reserve before password | parallel mixed unlock and re-arm window | 2 failed |

The repair guard restored the old check-then-count `unlock` path (password checked first, failed count updated in memory without the atomic reservation). The parallel mixed test checked the password 10 times for a limit of 5; the window test returned 200 for the correct password after the single post-delay check. Restored:

```text
$ python -m pytest -q --no-cov tests/security/test_local_boundary.py
47 passed
```

## GREEN

Original H2 focused suite:

```text
$ python -m pytest -q --no-cov \
    tests/security/test_local_boundary.py \
    tests/test_middleware \
    tests/test_routers/test_app_lock.py \
    tests/test_routers/test_setup_onboarding.py \
    tests/test_routers/test_setup_provider.py \
    tests/test_routers/test_setup_router.py
107 passed
```

Repair cycle 1 focused suite:

```text
$ python -m pytest -q --no-cov \
    tests/security/test_local_boundary.py \
    tests/test_middleware \
    tests/test_routers \
    tests/test_tools/test_docker_contract.py
629 passed
```

The new unlock contract has three tests:

- 9 wrong and 1 correct parallel attempts: `_password_matches` is spied (not replaced) and called at most the configured limit; no attempt beyond the limit returns 200.
- After the limit and the delay, one wrong attempt returns 401, then the correct password returns 429 until the delay passes again.
- HTTP route: limit wrong `POST /api/app-lock/unlock` calls return 401, the next returns 429, and a second ASGI client on the same database also returns 429.

Docker contract:

```text
$ python -m pytest -q --no-cov tests/test_tools/test_docker_contract.py
10 passed
```

Full backend suite:

```text
$ python -m pytest -q --no-cov \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4255 passed, 2 skipped in 698.14s
```

The first full run of the original H2 branch had 13 failures in `tests/runtime/test_cv_tailor_lifecycle.py` because the fresh worktree had no local `backend/app/templates/node_modules` (`Cannot find module 'docx'`). After `npm ci` in that directory, the file passed (17 passed) and the suite was rerun. The two ignored files are the known local CUDA-only suites.

Frontend (unchanged by repair cycle 1):

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

## Unlock reservation

`AppLockService.unlock` reserves one password check with a single atomic statement before calling `_password_matches`:

```sql
UPDATE app_lock_config
SET failed_attempt_count = failed_attempt_count + 1,
    last_failed_attempt_at = :now
WHERE id = 1
  AND (failed_attempt_count < :limit
       OR last_failed_attempt_at IS NULL
       OR last_failed_attempt_at <= :now - :retry_delay)
RETURNING failed_attempt_count
```

The transaction is committed before the password check. No returned row means the limit is active: the request gets 429 without a password check. A matching password resets the count and `last_failed_attempt_at` to zero/NULL. A wrong password leaves the reservation in place, so after the window one check is allowed and a wrong result re-arms the delay. At most `limit` password checks run per window, including parallel requests and separate app instances sharing the database.

## Setup boundary after password

After a password exists, only this GET route remains public for the unlock and
onboarding screens:

- `/api/setup/status` — setup/onboarding state read before the unlock page or a retry.

`/api/setup/providers` and `/api/setup/models/discovery` were removed from the public list. Their callers are `frontend/src/components/setup/AiCapabilitiesForm.tsx`, used from `frontend/src/app/onboarding/page.tsx` (runs before a password exists, when the bootstrap setup routes are public) and `frontend/src/app/settings/ai/page.tsx` (rendered behind `AppLockGate` and therefore only after unlock). No screen calls either route while the app is locked.

All other bootstrap GET routes and every mutating bootstrap route require a valid app-lock session once a password exists. Before a password exists, the bootstrap setup routes remain available so onboarding can run; the resume upload keeps its existing pre-setup exception.

## Live check (test ports only)

Backend on `127.0.0.1:18000`; frontend on `127.0.0.1:13000`; temporary SQLite, config and profile paths. No request went to ports 3000 or 8000.

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

The frontend proxy path used `API_URL=http://127.0.0.1:18000`; the default trusted-host list includes `127.0.0.1` and `backend`, so the real rewrite and server-side fetch paths remain accepted.

Secure-cookie check on repair test port `127.0.0.1:18001`, with temporary SQLite/config paths:

```text
FORWARDED_ALLOW_IPS=127.0.0.1
POST /api/app-lock/setup with X-Forwarded-Proto: https
set-cookie: hatch_app_session=...; HttpOnly; Path=/; SameSite=lax; Secure

FORWARDED_ALLOW_IPS=10.0.0.1
POST /api/app-lock/setup with X-Forwarded-Proto: https
set-cookie: hatch_app_session=...; HttpOnly; Path=/; SameSite=lax
```

A real TLS terminator was not run; the check simulates TLS termination by sending the proxy header from a trusted peer. The second case shows uvicorn ignores the header from an untrusted peer. `request.url.scheme` is the only input to the `Secure` flag.

## Repository checks

```text
$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ git diff --check
exit 0

$ make -n dev-back
cd backend && python -m app.database_setup
cd backend && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

$ make -n dev-back HOST=0.0.0.0
cd backend && python -m app.database_setup
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
- The Secure-cookie check used a trusted `X-Forwarded-Proto` header, not a real TLS terminator.
- `FORWARDED_ALLOW_IPS` is documented for Compose; the backend container was not restarted with a TLS proxy in this cycle.

Ready for review: yes.
