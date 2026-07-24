# Frontend Dependency Security Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate all npm high and moderate dependency advisories from the Hatch frontend without changing application behaviour or leaving Next.js 15.

**Architecture:** Patch Next.js and its matching ESLint configuration, then use narrowly parent-scoped npm overrides only where upstream dependency constraints still select vulnerable PostCSS, Sharp, or brace-expansion versions. Treat the lockfile and audited resolved tree as the deliverable, and prove compatibility with the existing frontend CI gates plus a production build.

**Tech Stack:** npm lockfile v3, Next.js 15.5, React 18, TypeScript 5, Vitest, GitHub Actions

## Global Constraints

- Work only on `chore/security-deps-frontend`, based on `origin/main` after PR #48.
- Do not modify frontend application source, backend files, database migrations, public APIs, or Coach contracts.
- Keep Next.js on major version 15 and React on major version 18.
- Resolve `next` at 15.5.21 or later, `postcss` at 8.5.18 or later, `sharp` at 0.35.0 or later, and each `brace-expansion` line at 1.1.16 or 5.0.7 or later within its existing major.
- Retain the existing `undici` override.
- Do not use `npm audit fix --force`, `--legacy-peer-deps`, or alert dismissal.
- Commit only dependency manifests, the generated lockfile, the approved security design, and this execution plan.

---

### Task 1: Capture the reproducible npm baseline

**Files:**
- Read: `frontend/package.json`
- Read: `frontend/package-lock.json`

**Interfaces:**
- Consumes: the post-PR-#48 dependency graph on `origin/main`
- Produces: an audit summary and exact vulnerable paths used to review the remediation

- [ ] **Step 1: Verify the branch and clean scope**

Run:

```bash
git status --short --branch
git merge-base --is-ancestor origin/main HEAD
```

Expected: the branch is `chore/security-deps-frontend`; only the committed design and plan are ahead of `origin/main`; the ancestry command exits 0.

- [ ] **Step 2: Record the package audit baseline**

Run:

```bash
cd frontend
npm audit --package-lock-only --json > /tmp/hatch-pr1-before-audit.json || test $? -eq 1
node -e 'const a=require("/tmp/hatch-pr1-before-audit.json"); console.log(a.metadata.vulnerabilities)'
```

Expected: npm reports 4 vulnerable package nodes, all high: `brace-expansion`, `next`, `postcss`, and `sharp`.

- [ ] **Step 3: Record every vulnerable resolved path**

Run:

```bash
npm ls next postcss sharp brace-expansion js-yaml --all --package-lock-only
```

Expected: Next.js 15.5.19, PostCSS 8.5.16 and nested 8.4.31, Sharp 0.34.5, brace-expansion 1.1.15 and 5.0.6, and js-yaml 4.3.0.

### Task 2: Update the manifest and lockfile with narrow overrides

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: npm's parent-version-scoped `overrides` resolution and the existing `undici` override
- Produces: a Next.js 15 dependency graph with no version matching the known vulnerable ranges

- [ ] **Step 1: Patch the direct Next.js package pair**

In `frontend/package.json`, change only these two specifications:

```json
"next": "^15.5.21"
```

```json
"eslint-config-next": "^15.5.21"
```

Expected: Next.js runtime and its ESLint integration stay aligned on the 15.5 patch line.

- [ ] **Step 2: Add parent-scoped transitive overrides**

Replace the `overrides` object in `frontend/package.json` with:

```json
"overrides": {
  "undici": "^7.28.0",
  "next@^15.5.21": {
    "postcss": "^8.5.18",
    "sharp": "^0.35.0"
  },
  "minimatch@3": {
    "brace-expansion": "^1.1.16"
  },
  "minimatch@10": {
    "brace-expansion": "^5.0.7"
  }
}
```

Expected: the override does not replace Next.js or minimatch themselves; it replaces only the named vulnerable children for matching parent versions.

- [ ] **Step 3: Regenerate the dependency graph without force flags**

Run:

```bash
cd frontend
npm install --package-lock-only
npm ci --ignore-scripts
```

Expected: both commands exit 0 with no `EOVERRIDE`, peer-range, or lockfile consistency error.

- [ ] **Step 4: Inspect the complete manifest/lockfile diff**

Run:

```bash
git diff -- frontend/package.json frontend/package-lock.json
git diff --check
```

Expected: changes are limited to the two direct patch specifications, four narrow transitive resolutions, associated integrity metadata, and unavoidable npm lockfile graph updates; there is no application source change or whitespace error.

- [ ] **Step 5: Commit the resolved dependency graph**

Run:

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "build(frontend): remediate dependency advisories"
```

Expected: one dependency-only commit is created.

### Task 3: Prove audit closure and frontend compatibility

**Files:**
- Verify: `frontend/package.json`
- Verify: `frontend/package-lock.json`
- Verify: `scripts/check_docs.py`

**Interfaces:**
- Consumes: the remediated npm graph from Task 2
- Produces: local security and regression evidence suitable for the PR description

- [ ] **Step 1: Verify exact resolved versions and override placement**

Run:

```bash
cd frontend
npm ls next eslint-config-next postcss sharp brace-expansion js-yaml --all
```

Expected: Next.js and eslint-config-next are at least 15.5.21 and remain below 16; all PostCSS nodes are at least 8.5.18; Sharp is at least 0.35.0; brace-expansion is at least 1.1.16 on major 1 and at least 5.0.7 on major 5; js-yaml remains 4.3.0; npm reports no invalid dependency.

- [ ] **Step 2: Require a zero-vulnerability npm audit**

Run:

```bash
npm audit --package-lock-only --audit-level=moderate
```

Expected: exit 0 and `found 0 vulnerabilities`.

- [ ] **Step 3: Run the complete frontend unit suite**

Run:

```bash
npm test
```

Expected: all existing Vitest test files and tests pass; pre-existing non-failing React `act(...)` or MediaPipe stderr does not count as a failure but is recorded in the PR evidence.

- [ ] **Step 4: Run static type checking**

Run:

```bash
npm run type-check
```

Expected: exit 0 with no TypeScript errors.

- [ ] **Step 5: Produce the production build**

Run:

```bash
npm run build
```

Expected: Next.js completes a production build. The pre-existing `AnswerTimer.tsx` hook-dependency warning may remain, but no new warning or build failure is accepted.

- [ ] **Step 6: Validate repository documentation**

Run from the repository root:

```bash
python scripts/check_docs.py
git diff --check origin/main...HEAD
```

Expected: documentation validation passes and the committed range has no whitespace errors.

### Task 4: Publish PR 1 and reconcile GitHub

**Files:**
- Read: `.github/workflows/ci.yml`
- Read: `docs/superpowers/specs/2026-07-24-dependency-security-remediation-design.md`
- Read: `docs/superpowers/plans/2026-07-24-frontend-dependency-security-remediation.md`

**Interfaces:**
- Consumes: clean local security and regression evidence
- Produces: one reviewable frontend security PR targeting `main`

- [ ] **Step 1: Push the branch without altering `main`**

Run:

```bash
git push -u origin chore/security-deps-frontend
```

Expected: the remote branch is created and the local branch tracks it.

- [ ] **Step 2: Open the frontend housekeeping PR**

Run:

```bash
gh pr create --repo arvindsoni2/hatch --base main --head chore/security-deps-frontend --title "build(frontend): remediate dependency advisories" --body-file /tmp/hatch-pr1-body.md
```

The PR body must state the 13 npm alert records covered by `next`, `postcss`, `sharp`, and `brace-expansion`; list before/after resolved versions; include the zero-audit, test, type-check, build, and docs-check results; state that no application source changed; and link the design and plan files.

Expected: GitHub returns the new PR URL.

- [ ] **Step 3: Wait for and inspect every CI job**

Run:

```bash
pr_number="$(gh pr view --repo arvindsoni2/hatch --json number --jq .number)"
gh pr checks --repo arvindsoni2/hatch --watch --interval 10 "$pr_number"
```

Expected: documentation, backend, frontend, and Windows-installer jobs required by `.github/workflows/ci.yml` pass. Any failure is diagnosed before merge.

- [ ] **Step 4: Review the final PR diff and alert projection**

Run:

```bash
pr_number="$(gh pr view --repo arvindsoni2/hatch --json number --jq .number)"
gh pr diff --repo arvindsoni2/hatch "$pr_number"
gh pr view --repo arvindsoni2/hatch "$pr_number" --json mergeable,reviewDecision,statusCheckRollup
```

Expected: GitHub reports a mergeable PR; the diff contains only the approved documentation, `frontend/package.json`, and `frontend/package-lock.json`; the npm remediation projects removal of 7 high and 6 moderate GitHub alert records, leaving only the 8 Python records for PR 2.

- [ ] **Step 5: Stop at the review gate**

Do not merge PR 1 until the owner reviews the PR and explicitly authorizes merge. Report the PR URL, exact dependency changes, audit result, test evidence, CI state, and the expected remaining Python alert baseline.
