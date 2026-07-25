# Backend Dependency Security Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the eight remaining moderate Python dependency alerts without changing application behaviour or runtime-profile boundaries.

**Architecture:** Upgrade the two vulnerable direct pins to their minimum fixed releases and update only the two pytest plugins whose existing pins make Pytest 9 unsatisfiable. Preserve asyncio fixture semantics explicitly in pytest configuration, then validate resolution, the real aiosmtplib call signatures, all backend tests, the Coach smoke path, and every canonical requirements audit before publishing PR 2.

**Tech Stack:** Python 3.12 CI, Python virtual environments, pip, pip-audit, pytest 9, pytest-asyncio, pytest-httpx, aiosmtplib

## Global Constraints

- Work only on `chore/security-deps-backend`, based on `origin/main` after merged PR #50 at `71080e2`.
- Do not modify frontend files, backend application source, database migrations, public APIs, or Coach contracts.
- Resolve `aiosmtplib` exactly at 5.1.1 and `pytest` exactly at 9.0.3, the minimum releases that fix the active advisories.
- Resolve the required compatibility floor with `pytest-asyncio==1.3.0` and `pytest-httpx==0.36.0`; do not upgrade unrelated packages.
- Preserve `asyncio_mode = auto` and explicitly preserve function-scoped async fixtures.
- Preserve every core, browser, local-AI, observability, perception, full, development, and test profile boundary.
- Do not ignore audit findings, loosen vulnerable pins, or use dependency-resolver bypass flags.
- Commit only the approved security plan, `backend/requirements.txt`, `backend/requirements-core.txt`, `backend/requirements-dev.txt`, and `backend/pytest.ini`.

---

### Task 1: Capture the reconciled Python baseline and solver constraints

**Files:**
- Read: `backend/requirements.txt`
- Read: `backend/requirements-core.txt`
- Read: `backend/requirements-dev.txt`
- Read: `backend/pytest.ini`

**Interfaces:**
- Consumes: merged PR #50 and GitHub's eight-alert Python-only baseline
- Produces: exact vulnerable packages, manifest propagation, and the minimum compatible pytest plugin set

- [ ] **Step 1: Verify branch ancestry and clean scope**

Run:

```bash
git status --short --branch
git merge-base --is-ancestor 71080e2 HEAD
```

Expected: branch `chore/security-deps-backend`; only this committed plan may be ahead of `origin/main`; ancestry exits 0.

- [ ] **Step 2: Reconcile GitHub's remaining alerts**

Run:

```bash
gh api --paginate repos/arvindsoni2/hatch/dependabot/alerts \
  -f state=open -f per_page=100 --method GET \
  --jq '[.[] | {package:.dependency.package.name, ecosystem:.dependency.package.ecosystem, severity:.security_advisory.severity, manifest:.dependency.manifest_path, ghsa:.security_advisory.ghsa_id}]'
```

Expected: exactly eight `pip` records, all moderate: seven `aiosmtplib` records and one `pytest` record; no npm record remains.

- [ ] **Step 3: Capture local core and development audit baselines**

Run:

```bash
python -m pip_audit -r backend/requirements-core.txt
python -m pip_audit -r backend/requirements-dev.txt
```

Expected: core reports only `aiosmtplib 3.0.1` / `PYSEC-2026-2338`, fixed in 5.1.1; development reports that finding plus `pytest 8.3.3` / `PYSEC-2026-1845`, fixed in 9.0.3. Both commands exit 1 because findings are present.

- [ ] **Step 4: Prove the existing pytest plugin pins block Pytest 9**

Run:

```bash
python -m pip install --dry-run \
  'pytest==9.0.3' \
  'pytest-asyncio==0.24.0' \
  'pytest-httpx==0.35.0'
```

Expected: resolution fails because `pytest-asyncio 0.24.0` and `pytest-httpx 0.35.0` require pytest below 9.

- [ ] **Step 5: Prove the minimum compatible plugin set resolves**

Run:

```bash
python -m pip install --dry-run \
  'pytest==9.0.3' \
  'pytest-asyncio==1.3.0' \
  'pytest-httpx==0.36.0' \
  'pytest-cov>=5.0.0'
```

Expected: exit 0 with a consistent Pytest 9 dependency solution and no unrelated requested upgrade.

### Task 2: Update the vulnerable pins and required pytest compatibility pins

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/requirements-core.txt`
- Modify: `backend/requirements-dev.txt`
- Modify: `backend/pytest.ini`

**Interfaces:**
- Consumes: the compatible version set proven by Task 1
- Produces: consistent runtime/development manifests with explicit async fixture-loop behaviour

- [ ] **Step 1: Patch both canonical aiosmtplib pins**

In `backend/requirements.txt` and `backend/requirements-core.txt`, replace:

```text
aiosmtplib==3.0.1
```

with:

```text
aiosmtplib==5.1.1
```

Expected: the standalone runtime profile and every profile including core resolve the same fixed release.

- [ ] **Step 2: Patch Pytest and only its incompatible pinned plugins**

In `backend/requirements-dev.txt`, replace the three pins with:

```text
pytest==9.0.3
pytest-asyncio==1.3.0
pytest-httpx==0.36.0
```

Expected: `pytest-cov`, Ruff, Factory Boy, and every application dependency specification remain unchanged.

- [ ] **Step 3: Preserve current async fixture-loop semantics explicitly**

In the `[pytest]` section of `backend/pytest.ini`, keep `asyncio_mode = auto` and add immediately after it:

```ini
asyncio_default_fixture_loop_scope = function
```

Expected: the pytest-asyncio 1.3 migration does not change the suite's existing function-scoped async fixture behaviour.

- [ ] **Step 4: Verify manifest consistency and diff scope**

Run:

```bash
rg -n 'aiosmtplib|pytest==|pytest-asyncio|pytest-httpx|asyncio_(mode|default_fixture_loop_scope)' \
  backend/requirements.txt backend/requirements-core.txt backend/requirements-dev.txt backend/pytest.ini
git diff -- backend/requirements.txt backend/requirements-core.txt backend/requirements-dev.txt backend/pytest.ini
git diff --check
```

Expected: only the six approved version/configuration lines changed and no whitespace error exists.

- [ ] **Step 5: Commit the Python dependency remediation**

Run:

```bash
git add backend/requirements.txt backend/requirements-core.txt backend/requirements-dev.txt backend/pytest.ini
git commit -m "build(backend): remediate dependency advisories"
```

Expected: one dependency/configuration-only commit is created.

### Task 3: Prove Python audit closure and application compatibility

**Files:**
- Verify: `backend/requirements.txt`
- Verify: `backend/requirements-core.txt`
- Verify: `backend/requirements-dev.txt`
- Verify: `backend/pytest.ini`
- Verify: `backend/app/services/email_sender.py`
- Verify: `backend/app/services/digest_service.py`

**Interfaces:**
- Consumes: the remediated Python dependency set from Task 2
- Produces: isolated resolution, API compatibility, regression, smoke, and audit evidence

- [ ] **Step 1: Create an isolated overlay environment and install the changed set**

Run from the repository root:

```bash
python -m venv --system-site-packages .venv-security
.venv-security/bin/python -m pip install --upgrade \
  'aiosmtplib==5.1.1' \
  'pytest==9.0.3' \
  'pytest-asyncio==1.3.0' \
  'pytest-httpx==0.36.0'
.venv-security/bin/python -m pip check
```

Expected: installation and `pip check` exit 0. The environment overlays only the four changed packages on the already-installed backend dependency graph.

- [ ] **Step 2: Verify installed versions and actual SMTP call signatures**

Run:

```bash
.venv-security/bin/python - <<'PY'
from email.message import EmailMessage
from inspect import signature

import aiosmtplib
import pytest
import pytest_asyncio
import pytest_httpx

message = EmailMessage()
send_signature = signature(aiosmtplib.send)
send_signature.bind(
    message,
    hostname="smtp.example.test",
    port=465,
    username="sender@example.test",
    password="secret",
    use_tls=True,
)
send_signature.bind(
    message,
    hostname="smtp.example.test",
    port=587,
    username="sender@example.test",
    password="secret",
    start_tls=True,
)
assert aiosmtplib.__version__ == "5.1.1"
assert pytest.__version__ == "9.0.3"
assert pytest_asyncio.__version__ == "1.3.0"
assert pytest_httpx.__version__ == "0.36.0"
print("dependency versions and SMTP call signatures verified")
PY
```

Expected: exit 0 and the verification message, proving both production call shapes bind against the installed 5.1.1 API.

- [ ] **Step 3: Run the complete backend test suite with coverage**

Run:

```bash
cd backend
../.venv-security/bin/python -m pytest --cov=app --cov-report=xml -q
```

Expected: all collected tests pass, coverage remains at or above the configured 58% floor, and no pytest-asyncio loop-scope or plugin compatibility warning appears.

- [ ] **Step 4: Run the bounded Coach contract smoke**

Run from `backend`:

```bash
timeout 180s ../.venv-security/bin/python -m benchmarks.coach smoke \
  --suite benchmarks/coach/fixtures/v1
```

Expected: exit 0 within 180 seconds.

- [ ] **Step 5: Audit every requirements profile**

Run from the repository root:

```bash
for requirement_file in \
  backend/requirements.txt \
  backend/requirements-core.txt \
  backend/requirements-browser.txt \
  backend/requirements-local-ai.txt \
  backend/requirements-observability.txt \
  backend/requirements-perception.txt \
  backend/requirements-full.txt \
  backend/requirements-dev.txt \
  backend/requirements-test.txt; do
  echo "Auditing $requirement_file"
  python -m pip_audit -r "$requirement_file"
done
```

Expected: every audit exits 0 with no known vulnerability. The included-profile audits repeat safe packages but produce no finding.

- [ ] **Step 6: Run repository documentation and committed-range checks**

Run:

```bash
python scripts/check_readme_contract.py
python scripts/check_docs.py
git diff --check origin/main...HEAD
git status --short --branch
```

Expected: both documentation checks and diff check pass; the tracked tree is clean and only `.venv-security` may exist as ignored local state.

### Task 4: Publish PR 2 and reconcile the final security gate

**Files:**
- Read: `.github/workflows/ci.yml`
- Read: `docs/superpowers/specs/2026-07-24-dependency-security-remediation-design.md`
- Read: `docs/superpowers/plans/2026-07-25-backend-dependency-security-remediation.md`

**Interfaces:**
- Consumes: clean local Python security and regression evidence
- Produces: one reviewable backend security PR targeting `main`

- [ ] **Step 1: Push the branch without altering `main`**

Run:

```bash
git push -u origin chore/security-deps-backend
```

Expected: the remote branch is created and the local branch tracks it.

- [ ] **Step 2: Open the backend housekeeping PR**

Run:

```bash
gh pr create --repo arvindsoni2/hatch --base main --head chore/security-deps-backend \
  --title "build(backend): remediate dependency advisories" \
  --body-file /tmp/hatch-pr2-body.md
```

The PR body must state the eight moderate Python alert records covered by `aiosmtplib` and `pytest`; explain the required pytest-asyncio and pytest-httpx compatibility upgrades; list before/after versions; include solver, signature, zero-audit, test, Coach smoke, and docs results; state that no application source changed; and link the design and plan files.

Expected: GitHub returns the new PR URL.

- [ ] **Step 3: Wait for and inspect every CI job**

Run:

```bash
pr_number="$(gh pr view --repo arvindsoni2/hatch --json number --jq .number)"
gh pr checks --repo arvindsoni2/hatch --watch --interval 10 "$pr_number"
```

Expected: documentation, backend, frontend, Windows-installer, and CodeQL jobs pass. Any failure is diagnosed before merge.

- [ ] **Step 4: Review the final PR diff and alert projection**

Run:

```bash
pr_number="$(gh pr view --repo arvindsoni2/hatch --json number --jq .number)"
gh pr diff --repo arvindsoni2/hatch "$pr_number"
gh pr view --repo arvindsoni2/hatch "$pr_number" \
  --json mergeable,mergeStateStatus,reviewDecision,statusCheckRollup
```

Expected: GitHub reports a clean, mergeable PR; the diff contains only the approved plan and four backend dependency/configuration files; merging projects removal of all eight moderate Python alert records.

- [ ] **Step 5: Stop at the owner review gate**

Do not merge PR 2 until the owner reviews it and explicitly authorizes merge. Report the PR URL, exact dependency changes, audit result, test evidence, CI state, and projected zero high/moderate repository alert baseline.
