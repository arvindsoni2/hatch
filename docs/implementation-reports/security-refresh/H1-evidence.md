# H1 evidence — guarded public fetch

Task / spec sections / ACs: H1, spec §2, §8 H1, §12, §14.

Baseline SHA → head SHA: `2d01733bb481be09b0015580c7b95aa5fe4127e0` (origin/main) → this branch, `refresh/h1-public-fetch`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

Claude Code RED commit: not applicable (H1 is not a high-assurance task). No protected test or protected document was edited.

## Files changed

- `backend/app/services/public_fetch.py` — guarded fetch, one URL/address validator, pinned network backend, manual redirects, body/content-type/timeout limits.
- `backend/app/services/jd_analyser.py` — `_fetch_jd` uses the guarded fetch; no URL logging.
- `backend/app/services/job_url_importer.py` — `preview_url` uses the guarded fetch; old validator removed.
- `backend/app/services/company_watchlist.py` — careers-page fetch and URL validation use the guarded fetch.
- `backend/app/services/company_researcher.py` — search fetch uses the guarded fetch and `quote_plus`.
- `backend/app/scrapers/indeed_india.py`, `naukri.py`, `itjobswatch.py`, `linkedin.py` — fixed-host fetches use the guarded fetch with the 5 MB cap.
- `backend/app/routers/jobs.py` — import-time URL validation points at `public_fetch`.
- `backend/tests/security/test_public_fetch.py` — contract, address, redirect, size, content-type, timeout, TLS, pinning and caller tests.
- `docs/architecture/SECURITY_SURFACE.md` — outbound rows updated to the implemented control.
- `docs/implementation-reports/security-refresh/H1-evidence.md` — this report.

## RED

Initial collection failed because the service did not exist:

```text
$ python -m pytest -q --no-cov tests/security/test_public_fetch.py
ImportError: cannot import name 'public_fetch' from 'app.services'
1 error during collection
```

After the service existed but before the callers were wired:

```text
5 failed, 29 passed
```

The failures were the caller tests (`jd_analyser`, `job_url_importer`, `company_watchlist`, `company_researcher`), because those modules had no guarded `fetch` symbol yet.

## Guard checks (spec §12)

Each guard was disabled locally, the matching test was run, and the source was restored. All guard-disabled runs failed as expected; the restored public-fetch suite passed.

| Guard disabled | Matching test(s) | Result |
|---|---|---|
| global/embedded address check | private, loopback, link-local, mapped, 6to4, NAT64 and redirect-hop tests | 18 failed |
| redirect re-validation | redirect-to-private tests | 9 failed |
| body size cap | oversized stream test | 1 failed |
| content-type check | wrong content-type test | 1 failed |
| redirect limit | six-redirect test | 1 failed |
| redirect-loop detection | loop test | 1 failed |
| TLS hostname | original-hostname test | 1 failed |
| scheme check | ftp test | 1 failed |
| userinfo check | userinfo test | 1 failed |
| single resolution/pinning | pinned-host test | 1 failed |

Restored:

```text
$ python -m pytest -q --no-cov tests/security/test_public_fetch.py
41 passed
```

## GREEN

```text
$ python -m pytest -q --no-cov \
    tests/security/test_public_fetch.py \
    tests/test_services/test_jd_analyser.py \
    tests/test_job_url_importer_pr10.py \
    tests/test_scrapers \
    tests/test_tools/test_security_surface_contract.py \
    tests/test_routers/test_company_watchlist.py \
    tests/test_services/test_company_researcher.py \
    tests/test_routers/test_jobs_router.py
112 passed

$ ruff check app/ tests/
All checks passed!
```

Full backend suite:

```text
$ python -m pytest -q --no-cov \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4201 passed, 2 skipped in 642.48s
```

The first full run had 13 failures in `tests/runtime/test_cv_tailor_lifecycle.py` because the fresh worktree had no local `backend/app/templates/node_modules` (`Cannot find module 'docx'`). After `npm ci` in that directory, the file passed (17 passed) and the suite was rerun. The two ignored files are the known local CUDA-only suites; their failures are environment failures, not H1 changes.

## Fixed-host size cap

The fixed-host cap is **5 MB** (`FIXED_HOST_MAX_BYTES`). The user-URL cap remains 2 MB. The fixed hosts parse bounded listings and snippets (for example, company research keeps 5,000 characters of extracted text and the scrapers cap their result pages); 5 MB leaves headroom above the 2 MB user-URL cap while still bounding a single response. No third-party site was probed; the value is a code-level bound, not a measurement from a live page.

## Repository checks

```text
$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ git diff --check
exit 0
```

```text
$ grep -rn "follow_redirects=True" <wired files>
none

$ grep -rn "def _validate_url\|def validate_public_url" backend/app
backend/app/services/public_fetch.py:def validate_public_url(...)
```

## Privacy and model calls

- Model calls in tests: none; the fetch tests use a mock transport, fake resolver and fake network backend, never the network.
- No `data/` or `.env*` was read.
- Fetch failures log host and code only; no full URL, query string or body. The wired scrapers and `jd_analyser` no longer log URLs.
- Error messages are fixed and contain no URL, query or body.

## Migration

Not applicable: no schema or stored-data change.

## Not run / known limits

- The Playwright scrapers are out of H1 scope.
- The optional Firecrawl fallback remains a configured third-party service; it is outside this task's file list and is recorded in the surface inventory as an H1 follow-up.
- No live network or third-party site was contacted.
- The full suite excludes the two known CUDA-only test files.

Ready for review: yes.
