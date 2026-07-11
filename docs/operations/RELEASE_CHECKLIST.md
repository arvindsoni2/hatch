# Hatch Release Checklist

This is the canonical release checklist and evidence record for public Hatch releases. Keep this file aligned with the exact commit being prepared for release. Do not create a parallel release checklist elsewhere.

## 1. Release identity

- [x] Repository confirmed as `arvindsoni2/hatch`.
- [x] Target release confirmed as `v0.1.0`.
- [x] Release title confirmed as `Hatch v0.1.0 — Public Portfolio Release`.
- [x] Default branch confirmed as `main`.
- [ ] Final publication date confirmed in `CHANGELOG.md` at tag time.
- [ ] Exact verified release commit SHA recorded after final `main` verification.

## 2. Scope freeze

- [x] Release-preparation work is limited to release readiness, documentation, evidence, and narrowly required release blockers.
- [x] The canonical checklist path remains `docs/operations/RELEASE_CHECKLIST.md`.
- [x] README installer commands remain pinned to `main` to preserve the rolling-install contract.
- [x] Release-note installer commands will use immutable `v0.1.0` URLs.
- [x] No tag or GitHub release will be created before maintainer approval.

## 3. Repository hygiene

- [x] Current local and remote `main` commit inspected before edits.
- [x] Existing local and remote tags inspected.
- [x] Existing GitHub releases inspected.
- [x] Open pull requests inspected.
- [x] Ignored files and tracked file patterns reviewed for release risks.
- [x] Release-preparation branch pushed and PR opened: <https://github.com/arvindsoni2/hatch/pull/32>.
- [ ] Final release commit confirmed clean after merge.

## 4. Documentation and link validation

- [x] README release-checklist link resolves to this file.
- [x] README installer commands still reference `main/install.sh` and `main/install.ps1`.
- [x] Release notes file for `v0.1.0` created under `docs/releases/`.
- [x] Documentation validators pass on the release-preparation branch.
- [x] Modified documentation links rechecked after final edits.
- [ ] GitHub rendered README and release-note links checked after publication.

## 5. Security and privacy checks

- [x] Tracked-file scan found no committed `.env`, database, export, or secret artefacts.
- [x] Secret-pattern grep reviewed; remaining matches are test fixtures or placeholder values.
- [x] Local reset performed before fresh-install validation: containers removed, app database cleared, profile reset, secrets blanked.
- [ ] Git history reviewed for release-blocking secrets if any new evidence appears.
- [ ] Fresh install and post-release logs reviewed for exposed secrets.

## 6. Backend verification

- [x] Backend test suite passed on the release-preparation branch.
- [ ] Backend lint/type checks passed if required by repository-native commands.
- [x] Backend health verified in a fresh runtime during smoke testing.

## 7. Frontend verification

- [x] `npm ci` completed in `frontend/`.
- [x] `npm run type-check` passed.
- [x] `npm test` passed.
- [x] `npm run build` passed.
- [ ] README screenshots confirmed to use fictional data only.

## 8. Compose and installer verification

- [x] `docker compose config --quiet` passed.
- [x] `docker compose -f docker-compose.easy.yml config --quiet` passed.
- [ ] Documented Compose override combinations validated as needed.
- [x] `bash -n install.sh` passed.
- [ ] Shell installer static analysis completed where tooling is available.
- [x] PowerShell installer parsing/static validation completed where tooling is available.
- [x] Windows installer regression in `scripts/tests/test_windows_installer.ps1` fixed for cross-platform CI determinism.

## 9. Clean-install smoke testing

- [x] Fresh local runtime rebuilt from the release-preparation candidate commit and validated at the documented ports.
- [ ] First-run app-lock setup verified manually in the browser.
- [ ] Onboarding completion verified manually in the browser.
- [ ] Starting new onboarding does not retain stale onboarding state.
- [ ] Manual job creation or import verified.
- [ ] AI-deferred mode verified without provider credentials.
- [ ] One safe AI-enabled workflow verified if infrastructure is available.
- [ ] Restart persistence verified.
- [ ] `hatch status`, `hatch doctor`, and `hatch probe` verified from the managed installer path.
- [ ] Uninstall or update flow verified when documented.

## 10. GitHub Actions and security checks

- [x] Workflow inventory reviewed under `.github/workflows/`.
- [x] Current `main` CI state inspected.
- [x] Current `main` CodeQL state inspected.
- [x] Release blocker identified: `windows-installer` test contract was failing on `main` due host-specific expectations.
- [x] Release-preparation PR checks all green.
- [ ] Exact merged `main` commit has successful required CI and CodeQL runs.

## 11. Tag verification

- [ ] Maintainer approved the verified `main` commit for publication.
- [ ] Annotated tag `v0.1.0` created locally from the verified commit.
- [ ] Remote tag `v0.1.0` pushed successfully.
- [ ] Remote tag SHA matches the approved verified commit SHA.
- [ ] No prior `v0.1.0` tag existed unexpectedly.

## 12. GitHub release publication

- [ ] `gh release create v0.1.0` executed with `docs/releases/v0.1.0.md`.
- [ ] Release is public and not a prerelease.
- [ ] Release is marked latest.
- [ ] Release notes render correctly on GitHub.

## 13. Post-release verification

- [ ] GitHub release page and source archives verified.
- [ ] Tagged installer flow retested against `v0.1.0`.
- [ ] README and documentation links verified from GitHub rendered pages.
- [ ] No unexpected workflow failed on tag push.
- [ ] Any known issue recorded without changing the tag.

## 14. Roll-forward policy

- [x] Published release tags must never be moved or rewritten.
- [x] Any correction after publication must use a later version, normally `v0.1.1`.
- [x] Unsupported claims, automatic application submission, and secret-in-browser flows remain out of scope.
- [x] README may continue using rolling `main` installer URLs while release notes pin the immutable release.

## 15. Release evidence

### Open PR decision

- [x] Open PR `#4` (`dependabot/pip/backend/pip-590e9db7b9`) reviewed.
- [x] Classification: safe to defer from `v0.1.0`.
- [x] Rationale: dependency bump is not required to publish the current portfolio release and should follow normal review.

### Repository metadata audit

- [x] Repository is public.
- [x] Current repository description captured for review: `Hatch — AI-powered job discovery board`.
- [x] Current repository topics appear unset through `gh repo view`.
- [ ] Maintainer decision on optional public description/topic refresh recorded.

### Evidence table

| Check | Command or method | Result | Evidence/reference | Verified by | Date |
|---|---|---|---|---|---|
| Repository identity and branch | `git status --short --branch`, `git log --oneline --decorate -10 origin/main` | Pass | `origin/main` at `4370ce6`; repository remote is `arvindsoni2/hatch` | Codex | 2026-07-11 |
| Existing tags | `git tag --list --sort=-version:refname`, `git ls-remote --tags origin` | Pass | No existing local or remote release tags found | Codex | 2026-07-11 |
| Existing GitHub releases | `gh release list` | Pass | No published GitHub releases found before `v0.1.0` | Codex | 2026-07-11 |
| Open pull requests | `gh pr list --state open` | Pass | One open PR: `#4` Dependabot pytest bump, classified safe to defer | Codex | 2026-07-11 |
| Workflow inventory | `find .github/workflows -maxdepth 1 -type f` | Pass | `CI` and `CodeQL` release-relevant workflows present | Codex | 2026-07-11 |
| Current GitHub checks on `main` | `gh run list --branch main --limit 20`, `gh run view 29145658843 --log-failed` | Action required | `CodeQL` green; `CI` failing on `windows-installer` test contract before this PR | Codex | 2026-07-11 |
| README release contract | README audit plus `scripts/check_readme_contract.py` rules review | Pass | README links this checklist and keeps installer URLs on `main` | Codex | 2026-07-11 |
| Tracked sensitive artefact scan | `git ls-files | grep -Ei '(\\.env$|\\.db$|\\.sqlite|\\.sqlite3|\\.log$|\\.mp4$|\\.mov$|\\.mkv$|\\.docx$|\\.pdf$|secret|credential|token)'` | Pass | No tracked sensitive artefacts matched | Codex | 2026-07-11 |
| Secret-pattern grep review | `git grep -nEI '(api[_-]?key|secret|token|password)...'` with manual review | Pass | Matches limited to tests and explicit placeholder values | Codex | 2026-07-11 |
| Local fresh-state reset | Docker container removal plus user-data reset script intent | Pass | All containers removed; app DB, generated data, recordings, uploads, profile, and saved secrets cleared before smoke testing | Codex | 2026-07-11 |
| Windows installer CI regression | `gh run view ... --log-failed`, local `pwsh -File scripts/tests/test_windows_installer.ps1` | Pass | Root cause traced to host-specific exit-code expectation; test now compares against live preflight result | Codex | 2026-07-11 |
| Backend tests | `cd backend && python -m pytest` | Pass | `773 passed, 2 skipped` in `99.70s`; warnings remain but suite is green | Codex | 2026-07-11 |
| Frontend checks | `cd frontend && npm ci && npm run type-check && npm test && npm run build` | Pass | `531 passed`; Next.js production build succeeded with one existing hook warning in `AnswerTimer.tsx` | Codex | 2026-07-11 |
| Compose validation | `docker compose config --quiet` and `docker compose -f docker-compose.easy.yml config --quiet` | Pass | Both documented Compose entry points validated successfully | Codex | 2026-07-11 |
| Installer static checks | `bash -n install.sh`; `pwsh -File scripts/tests/test_windows_installer.ps1` | Pass | Shell syntax clean; Windows installer suite passed after cross-platform exit-code fix | Codex | 2026-07-11 |
| Candidate runtime smoke test | `docker compose up -d --build backend frontend`; health, HTTP, and logs checks | Partial | Candidate branch runtime rebuilt cleanly; backend health and frontend HTTP verified, but browser-driven first-run/onboarding steps still pending | Codex | 2026-07-11 |
| Release-preparation PR | `git push`; `gh pr create` | Pass | Branch pushed and PR `#32` opened: <https://github.com/arvindsoni2/hatch/pull/32> | Codex | 2026-07-11 |
| Release-preparation PR checks | `gh pr checks 32`; `gh pr view 32 --json ...` | Pass | PR `#32` checks green at `4cec423f34d212b5741dbff3a18eee8fc8ad1b45`; merge state `CLEAN` | Codex | 2026-07-11 |
| Tag and release publication | Maintainer-gated remote operations | Pending | Blocked until merge, final `main` verification, and maintainer approval for publication | Codex | 2026-07-11 |
