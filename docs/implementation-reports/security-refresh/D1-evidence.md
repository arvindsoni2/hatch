# D1 evidence — frontend packages

Task / spec sections / ACs: D1 (frontend packages), spec §2, §6, §11, §12; D1 acceptance in §6.

Baseline SHA → head SHA: `00d4bbde80a2dae38984a409e6e632c226fa7817` (origin/main) → this commit on `refresh/d1-frontend-packages`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

Claude Code RED commit: not applicable (D1 is not a high-assurance task). No protected test file was edited; the two P9 protected files and the spec/plan are untouched.

Files changed:

- `frontend/package.json` — dependency ranges, overrides and removal of the uncovered `test:coverage` script.
- `frontend/package-lock.json` — one resolution for the updated tree.
- `docs/implementation-reports/security-refresh/D1-evidence.md` — this report.

No `vitest.config.ts` or test-file change was needed for Vitest 4.

## Versions

| Package | Before | After | Note |
|---|---|---|---|
| `next` | 15.5.26 | 15.5.29 | stays on 15.x |
| `eslint-config-next` | 15.5.26 | 15.5.29 | stays on 15.x |
| `vitest` | 3.2.6 | 4.1.12 | the only major upgrade |
| `vite` | 7.3.6 | 7.3.8 | override, stays below 8 |
| `sharp` (next override) | 0.35.4 | 0.35.5 | stays on 0.35.x |
| `undici` (override) | 7.29.0 | 7.30.2 | stays below 8 |
| `zod` (transitive) | 4.4.3 | 4.6.7 | stays on 4.x |
| `minimatch` where ≥ 7 | 10.2.5 | 11.0.9 | 3.1.5 copies stay, as allowed |
| `postcss-selector-parser` | 6.1.2 | 6.1.6 | stays on 6.x |
| `source-map-js` | 1.2.1 | 1.2.4 | stays on 1.x |

`npm ls minimatch source-map-js postcss-selector-parser` reports only `minimatch@11.0.9`, `minimatch@3.1.5`, `source-map-js@1.2.4` and `postcss-selector-parser@6.1.6`; there is no vulnerable copy of any listed package.

Vitest 4 migration: the suite needed no test or config change (no `poolOptions`, `coverage.all`, `coverage.extensions`, or `new`-called mocks in the tree). `test:coverage` was removed because `@vitest/coverage-v8` is not installed and adding it needs owner approval; D1 permits removing the script instead. No dependency was added.

## Audit and test count

Before (`npm ci` from the clean checkout):

```text
$ npm audit
16 packages: 3 critical, 5 high, 8 moderate

$ npm audit --omit=dev
3 packages: 1 critical, 2 high

$ TZ=UTC npx vitest run
120 files passed, 736 tests passed

$ TZ=Europe/London npx vitest run
120 files passed, 736 tests passed
```

After:

```text
$ npm ci
exit 0

$ npm audit
0 vulnerabilities

$ npm audit --omit=dev
0 vulnerabilities

$ TZ=UTC npx vitest run
120 files passed, 736 tests passed

$ TZ=Europe/London npx vitest run
120 files passed, 736 tests passed
```

## GREEN (real output)

```text
$ npm ci
exit 0

$ npm audit
0 vulnerabilities

$ npm audit --omit=dev
0 vulnerabilities

$ TZ=UTC npx vitest run
120 files passed, 736 tests passed

$ TZ=Europe/London npx vitest run
120 files passed, 736 tests passed

$ npm run type-check
exit 0

$ npm run build
exit 0

$ npm run lint
exit 0 (existing warnings only)

$ PLAYWRIGHT_BASE_URL=http://localhost:3001 npx playwright test \
    e2e/coach-readiness.spec.ts --project=chromium
3 passed (11.1s)

$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ python -m pytest -q --no-cov scripts/tests
40 passed

$ git diff --check
exit 0
```

Regressions: full frontend suite in UTC and Europe/London, type-check, build, lint and the mocked readiness e2e spec. `e2e/api-flows.spec.ts` was not run.

Model calls in tests: none live.

Privacy / deletion / fencing evidence: not applicable to D1; no product code changed.

Migration: none.

Not run / known limits:

- Node runtime in this environment is 22.23.2; the Node version move is D3, not D1.
- `npm run lint` keeps the repository's existing warnings; no rule was disabled.
- No major upgrade other than Vitest 4; no new dependency; no protected test broke.

Ready for review: yes.
