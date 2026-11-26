# D2 evidence — Python packages

Task / spec sections / ACs: D2 (Python packages), spec §2, §5, §6 D2, §11, §12, §14.

Baseline SHA → head SHA: `2fe6d8ac2a8910b3b596e7756f64ff60989e7fb1` (origin/main) → this branch, `refresh/d2-python-packages`.

OpenCode version · model ID · effort · switches: harness-reported `opencode/deepseek-v4.1-flash-free`; plan id `opencode-go/deepseek-v4.1-flash`; no model switch.

Claude Code RED commit: not applicable (D2 is not a high-assurance task). No protected test or protected document was edited.

## Files changed

- `backend/requirements-observability.txt` — OpenTelemetry group at 1.45.2 / 0.66b2, kept aligned.
- `backend/requirements.txt`, `requirements-core.txt`, `requirements-browser.txt`, `requirements-dev.txt` — in-policy upgrades.
- `backend/requirements.txt`, `requirements-core.txt`, `requirements-test.txt` — floors raised past known advisories.
- `backend/constraints.txt` (new) — one Python 3.12 resolution covering every profile.
- `backend/Dockerfile`, `.github/workflows/ci.yml` — install with `-c constraints.txt` (CI install line only, plus the CPU PyTorch index).
- `backend/ruff.toml` (new, owner-approved) — keeps the pre-0.17 rule selection so the ruff upgrade is deterministic.
- `docs/implementation-reports/security-refresh/D2-evidence.md` — this report.

Commits:

1. `7491c71` `chore(deps): align OpenTelemetry at 1.45.2`
2. `6db64a1` `chore(deps): apply in-policy Python upgrades`
3. `d19f3eb` `build(deps): install from the Python 3.12 constraints`
4. `c0f1190` `chore(deps): raise Python floors past known advisories`
5. `405d215` `chore(lint): keep the ruff 0.17 rule selection stable`
6. `295a23a` `ci: use the CPU torch index with the constraints`
7. `a3f7f17` `chore(deps): keep FastAPI at 0.136.3 for the optional-dependency contract`
8. `ceefc21` `build(deps): regenerate constraints with FastAPI 0.136.3`

## Versions

| Package | Before | After |
|---|---|---|
| fastapi | 0.136.3 | **0.136.3 (kept)** |
| uvicorn | 0.48.0 | 0.54.0 |
| alembic | 1.18.4 | 1.20.1 |
| pydantic | 2.13.4 | 2.14.4 |
| pydantic-settings | 2.14.2 | 2.16.3 |
| beautifulsoup4 | 4.14.3 | 4.15.0 |
| playwright | 1.60.0 | 1.65.2 |
| apscheduler | 3.11.2 | 3.11.3 |
| rapidfuzz | 3.14.5 | 3.14.6 |
| pyyaml | 6.0.3 | 6.0.4 |
| aiosmtplib | 5.1.2 | 5.1.3 |
| python-dotenv | 1.2.2 | 1.2.4 |
| ruff | 0.15.15 | 0.17.6 |
| pytest | 9.0.3 | 9.2.0 |
| pytest-asyncio | 1.3.0 | 1.5.0 |
| sqlalchemy | 2.0.50 | 2.0.58 (stays on 2.0.x) |
| opentelemetry-api / sdk / otlp | 1.44.0 | 1.45.2 |
| opentelemetry instrumentation | 0.65b0 | 0.66b2 |

**FastAPI stays at 0.136.3.** 0.165.0 imports `opentelemetry` unconditionally from its telemetry module, which breaks
`test_optional_dependency_modules_import_without_optional_packages` (the test blocks optional imports and imports
`app.main`). Per D2's rule, the upgrade was left at the current version and the constraints were regenerated with
0.136.3. No test was changed.

Floors: `python-multipart>=0.0.31`, `pypdf>=6.21.4`, `lxml>=6.1.0`, `pytest>=9.2.0`, `pytest-asyncio>=1.5.0` — each
is the lowest version with no known advisory (checked with pip-audit). `pypdf` and `lxml` cross a major version
because the advisory fix requires it; no other major upgrade was made.

## Constraints

`backend/constraints.txt` was generated from `requirements-full.txt` + `requirements-dev.txt` with uv 0.13.7. The
exact command is in the file header. `--index-strategy unsafe-best-match` is required so the CPU PyTorch index does
not shadow newer PyPI versions (it otherwise selected an old `requests`/`urllib3` pair). The file pins 151 direct
requirements.

## Profile installs and audits (real output)

Each profile used a fresh Python 3.12 `uv venv --seed`, the constraints file, and the CPU PyTorch index where torch
is pulled.

| Profile | Install | `pip check` | `pip-audit` |
|---|---|---|---|
| core | exit 0 | No broken requirements found | 0 vulnerabilities |
| browser | exit 0 | No broken requirements found | 0 vulnerabilities |
| local-ai | exit 0 | No broken requirements found | 0 vulnerabilities (torch `+cpu` skipped by pip-audit) |
| observability | exit 0 | No broken requirements found | 0 vulnerabilities |
| perception (core + perception) | exit 0 | No broken requirements found | 0 vulnerabilities (torch skipped) |
| full | exit 0 | No broken requirements found | 0 vulnerabilities (torch skipped) |
| dev/test | exit 0 | No broken requirements found | 0 vulnerabilities (torch skipped) |

The local-ai and perception audits ran before the FastAPI revert; FastAPI 0.136.3 is the baseline version, whose
audit is clean in spec §5, and the final full/dev/core/browser/observability audits were rerun with the final
constraints.

## Test suites

Before (main, old environment; the fresh worktree needed the existing templates `node_modules` linked for the CV
renderer):

```text
$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4155 passed, 2 skipped in 721.41s
```

After (upgraded dev environment):

```text
$ python -m pytest -q --no-cov tests \
    --ignore=tests/test_tools/test_embedder.py \
    --ignore=tests/test_tools/test_semantic_scorer.py
4155 passed, 2 skipped in 661.80s

$ python -m pytest -q --no-cov tests/runtime
482 passed, 1 skipped in 103.73s
```

## Ruff

`ruff 0.17.6` with the owner-approved `backend/ruff.toml`:

```text
$ ruff check app/ tests/
All checks passed!
```

Ruff 0.17 enables a much broader default rule set (814 rules) than 0.15. The config preserves the previous
`E4,E7,E9,F` selection; no code changes were needed.

## Migration and image

```text
$ alembic heads
6e209652647a (head)

$ python -m app.database_setup   # disposable /tmp SQLite file
setup exit 0

$ alembic upgrade head
exit 0

$ alembic downgrade -1
exit 0 (6e209652647a -> 54f861f6f61d)

$ alembic upgrade head
exit 0 (54f861f6f61d -> 6e209652647a)
```

```text
$ podman build --target core -t hatch-backend:d2-review backend
exit 0
Successfully tagged localhost/hatch-backend:d2-review
```

No running container was restarted or replaced.

## Repository checks

```text
$ python scripts/check_docs.py
Documentation validation passed.

$ python scripts/check_readme_contract.py
README contract passed.

$ git diff --check
exit 0
```

Model calls in tests: fake/local only; no live model calls. No `data/` or `.env*` was read.

Not run / known limits:

- `pip-audit` cannot audit the local `torch==2.15.0+cpu` build (it reports a skip, not a vulnerability); the same
  build is used by the existing images.
- The Node runtime move is D3, not D2.
- The ruff config file was added with explicit owner approval because it was outside D2's original file list.
- `e2e/api-flows.spec.ts` was not run.

Ready for review: yes.
