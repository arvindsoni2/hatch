# H0 evidence — surface inventory and threat model

Task / spec sections / ACs: H0, spec §1, §2, §5, §8 (H0–H6), §12, §14.

Baseline SHA → head SHA: `4a9e5cfe5f3e0108400b673227976fb9f6a9f623` (origin/main) → this branch, `refresh/h0-security-surface`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

Claude Code RED commit: not applicable (H0 is not a high-assurance task). No protected test or protected document was edited.

## Files changed

- `docs/architecture/SECURITY_SURFACE.md` — public route, browser, request, file, parser, template, prompt and secret inventory; CodeQL disposition table.
- `backend/tests/test_tools/test_security_surface_contract.py` — fails on an app route without a row or a row without an app route.
- `backend/scripts/security_surface.py` — prints the generated route columns; the test does not depend on it.
- `docs/architecture/SECURITY_AND_PRIVACY.md` — one link to the inventory.
- `docs/README.md` — docs-index link to the inventory.
- `docs/implementation-reports/security-refresh/H0-evidence.md` — this report.

## RED

Initial run, before the inventory existed:

```text
$ python -m pytest -q --no-cov tests/test_tools/test_security_surface_contract.py
FAILED tests/test_tools/test_security_surface_contract.py::test_every_route_has_one_surface_row
AssertionError: missing .../docs/architecture/SECURITY_SURFACE.md
1 failed
```

Row-removal check (one `GET /api/health` row deleted):

```text
$ python -m pytest -q --no-cov tests/test_tools/test_security_surface_contract.py
E       assert not [('GET', '/api/health')]
FAILED tests/test_tools/test_security_surface_contract.py::test_every_route_has_one_surface_row
1 failed
```

The row was restored.

## GREEN

```text
$ python -m pytest -q --no-cov tests/test_tools/test_security_surface_contract.py
1 passed

$ python -m pytest -q --no-cov tests/test_tools \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
93 passed

$ ruff check app/ tests/ scripts/security_surface.py
All checks passed!
```

Route count: **249 `APIRoute` objects + 3 non-API `Route` objects = 255 method/path rows** (`/openapi.json`, `/docs` and `/docs/oauth2-redirect` each contribute `GET` and `HEAD`).

Baseline recount on `4a9e5cf`:

```text
$ gh api 'repos/arvindsoni2/hatch/dependabot/alerts?state=open' --paginate -q length
0

$ gh api 'repos/arvindsoni2/hatch/code-scanning/alerts?state=open' --paginate
26 alerts: 1 critical, 20 high, 5 medium

$ gh api 'repos/arvindsoni2/hatch/secret-scanning/alerts?state=open' --paginate -q length
0

$ shellcheck -S warning <16 tracked shell scripts>
1 warning: scripts/verify_runtime.sh:61 (SC2034)
```

The spec §5 baseline recorded 37 Dependabot alerts, 26 CodeQL alerts (1 critical, 20 high, 5 medium), 0 secret-scanning alerts and 1 shellcheck warning. Dependabot is now 0; the other counts match.

## Repository checks

```text
$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ git diff --check
exit 0
```

Forbidden-word grep on the committed diff (the listed words): **0 matches**.

## Privacy and model calls

- Model calls in tests: none.
- No `data/` or `.env*` was read; the inventory uses code and synthetic names only.
- The detailed findings list is kept outside git at `/home/asoni/.cache/hatch-review/private/security-refresh/H0-findings.md` (directory 0700, file 0600).
- No GitHub alert was dismissed and no GitHub setting was changed.

## Migration

Not applicable: no schema or stored-data change.

## Not run / known limits

- No live service, container or external site was probed; route effects are read from code.
- The two known CUDA-only test files were excluded from the `tests/test_tools` regression run; their unfiltered failures are local environment failures, not H0 changes.
- `e2e/api-flows.spec.ts` was not run.
- CodeQL counts are a point-in-time GitHub API recount on the baseline; the spec records daily variation as expected.

Ready for review: yes.
