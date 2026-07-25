# Dependency Security Remediation Design

**Status:** Approved for housekeeping before Coach Phase 1 implementation

**Scope:** Resolve the 24 July 2026 GitHub Dependabot baseline of 7 high and 14 moderate alerts through two reviewable pull requests. Dependency manifests, lockfiles, tests, and security documentation may change; application behaviour and Coach implementation files may not.

## Baseline

PR #48 upgraded `js-yaml` from 4.2.0 to 4.3.0 and was independently verified before merge. GitHub closed that alert, then exposed a newer high-severity `postcss` advisory. The refreshed baseline therefore remains 21 open alert records:

| Ecosystem | Package | Alert records | Current version | Minimum fixed version | Dependency class |
|---|---|---:|---|---|---|
| npm | `brace-expansion` | 2 high | 1.1.15 and 5.0.6 | 1.1.16 and 5.0.7 | transitive development |
| npm | `next` | 3 high, 5 moderate | 15.5.19 | 15.5.21 | direct runtime |
| npm | `postcss` | 1 high, 1 moderate | 8.5.16 and nested 8.4.31 | advisory-specific; use a non-vulnerable resolved version | direct development and transitive runtime |
| npm | `sharp` | 1 high | 0.34.5 | 0.35.0 | transitive runtime through Next.js |
| Python | `aiosmtplib` | 7 moderate | 3.0.1 | 5.1.1 | direct runtime pin repeated across requirement profiles |
| Python | `pytest` | 1 moderate | 8.3.3 | 9.0.3 | direct development pin |

The 21 records represent six distinct affected packages. Repeated manifests and multiple advisories against one installed package are preserved in the record count so the local baseline reconciles with GitHub.

## Approaches considered

### 1. Two ecosystem-specific PRs with complete verification (selected)

PR 1 updates the frontend dependency graph; PR 2 updates the Python pins. Each PR carries its own audit output and regression evidence. This keeps lockfile review separate from Python compatibility review and makes either ecosystem independently revertible.

### 2. One combined security PR

This would reduce coordination overhead, but it would mix unrelated package managers, obscure which upgrade caused a regression, and increase rollback scope. It is rejected.

### 3. Record risk acceptance without upgrading

This would preserve the current runtime but leave known high-severity runtime dependencies in the baseline immediately before increasing the product's attack surface. It is rejected unless a fixed version proves incompatible and the residual risk is explicitly approved.

## PR 1: frontend/npm remediation

Branch `chore/security-deps-frontend` targets `main`.

- Upgrade `next` to a resolved version at or above 15.5.21 while remaining on Next.js 15.
- Resolve `sharp` at or above 0.35.0.
- Resolve both vulnerable `brace-expansion` lines at or above their respective fixed versions.
- Remove vulnerable `postcss` resolutions, including Next.js's nested copy.
- Prefer normal semver resolution and the narrowest package-manager override necessary. Do not use `npm audit fix --force`.
- Retain the existing `undici` override unless the refreshed graph proves it unnecessary in a separately reviewable change.

Verification gates are clean install, dependency-tree inspection, `npm audit`, unit tests, type checking, production build, and the repository documentation check. Any peer-range or runtime incompatibility stops the PR rather than being hidden with legacy-peer flags.

## PR 2: backend/Python remediation

Branch `chore/security-deps-backend` is created from the updated `main` after PR 1 lands.

- Upgrade the canonical `aiosmtplib` pin to 5.1.1 or later and ensure every included requirements profile resolves that same safe pin.
- Upgrade the development-only `pytest` pin to 9.0.3 or later.
- Make only compatibility changes that are required by these dependency upgrades; do not perform opportunistic refactoring.
- Preserve all runtime profiles and optional-dependency boundaries.

Verification gates are installation of the core and development profiles in isolated environments, `pip check`, `pip-audit` for every canonical profile, focused email tests, the complete backend unit/integration suite, and the repository documentation check. If Pytest 9 exposes test-suite incompatibilities, those repairs remain in this PR and must not change application behaviour.

## Evidence and alert reconciliation

Each PR description records before-and-after audit summaries, exact resolved versions, test commands, and results. After merge, GitHub alerts are refreshed and reconciled by advisory and manifest. A zero open high/moderate result is the completion criterion; GitHub processing lag is reported explicitly rather than treated as a local failure.

## Merge and branch sequencing

PR 1 merges first. PR 2 is then based on the new `main`, avoiding stacked security changes. Once both PRs pass CI, are merged, and GitHub's alert state is reconciled, `origin/main` is merged into `feature/coach-phase1-phase2`. The Coach branch remains the sole location for Phase 1 and eventual Phase 2 implementation and does not begin application work before this security gate closes.

## Rollback and residual risk

Each ecosystem is independently revertible through its merge commit. If a minimum fixed version cannot pass the relevant regression suite, the PR remains open with the incompatibility documented; no alert is dismissed as tolerable without explicit owner approval. No application implementation files, database migrations, public APIs, or approved Coach contracts are changed by this housekeeping work.
