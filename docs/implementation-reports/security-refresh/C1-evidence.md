# C1 evidence — close replaced Dependabot PRs

Status: **complete.** Both replaced PRs are closed and their branches are gone, all four `opentelemetry-api` alerts are fixed, and no Dependabot PR remains open. No alert was dismissed.

## D1 half — PR #65

- Confirmed `origin/main` at `2fe6d8ac2a8910b3b596e7756f64ff60989e7fb1`; `frontend/package-lock.json` shipped `postcss-selector-parser` **6.1.6** (≥ 6.1.4, the version PR #65 proposed).
- Commented on #65: "Replaced by #92 (D1), which ships 6.1.6".
- Closed PR #65 at **2026-11-26T10:45:39Z**; state is CLOSED.
- Deleted only its branch `dependabot/npm_and_yarn/frontend/npm_and_yarn-4e74362abf`; `git ls-remote --heads origin 'dependabot/*'` returns nothing.

## D2 half — PR #81

- PR #81 (opentelemetry-api 1.44.0 → 1.45.1) was replaced by D2, which moves the OpenTelemetry group to **1.45.2**.
- Closed PR #81 at **2026-11-26T20:45:31Z**, before D2 (#94) merged at **2026-11-26T22:01:14Z**.
- Deleted only its branch `dependabot/pip/backend/pip-7cb61790e1`; no `dependabot/*` branches remain.

## Alert recount (final)

`gh api repos/arvindsoni2/hatch/dependabot/alerts?state=open -q length` returns **0**.

The four alerts that were open before GitHub rescanned `main` are now fixed:

| Alert | Package | Manifest | State | Fixed at |
|---|---|---|---|---|
| 111 | opentelemetry-api | `backend/requirements-observability.txt` | fixed | 2026-11-26T22:19:26Z |
| 122 | opentelemetry-api | `backend/requirements-full.txt` | fixed | 2026-11-26T22:19:25Z |
| 126 | opentelemetry-api | `backend/requirements-observability.txt` | fixed | 2026-11-26T22:19:26Z |
| 127 | opentelemetry-api | `backend/requirements-full.txt` | fixed | 2026-11-26T22:19:25Z |

No alert was dismissed. Open Dependabot PRs: **0** (`gh pr list --state open`, filtered to Dependabot authors). No frontend alerts remain after D1.
