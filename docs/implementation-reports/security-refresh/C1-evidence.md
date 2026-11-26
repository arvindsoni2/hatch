# C1 evidence — close replaced Dependabot PRs

Status: **complete except for GitHub's alert rescan.** Both replaced PRs are closed and their branches are gone; four `opentelemetry-api` alerts remain open until GitHub rescans `main` (no alert was dismissed).

## D1 half — PR #65

- Confirmed `origin/main` at `2fe6d8ac2a8910b3b596e7756f64ff60989e7fb1`; `frontend/package-lock.json` shipped `postcss-selector-parser` **6.1.6** (≥ 6.1.4, the version PR #65 proposed).
- Commented on #65: "Replaced by #92 (D1), which ships 6.1.6".
- Closed PR #65 at **2026-11-26T10:45:39Z**; state is CLOSED.
- Deleted only its branch `dependabot/npm_and_yarn/frontend/npm_and_yarn-4e74362abf`; `git ls-remote --heads origin 'dependabot/*'` returns nothing.

## D2 half — PR #81

- PR #81 (opentelemetry-api 1.44.0 → 1.45.1) was replaced by D2, which moves the OpenTelemetry group to **1.45.2**.
- Closed PR #81 at **2026-11-26T20:45:31Z**, before D2 (#94) merged at **2026-11-26T22:01:14Z**.
- Deleted only its branch `dependabot/pip/backend/pip-7cb61790e1`; no `dependabot/*` branches remain.

## Alert recount

`gh api repos/arvindsoni2/hatch/dependabot/alerts?state=open --paginate` currently returns **4** open alerts, all `pip` / `opentelemetry-api` (medium):

| Alert | Package | Manifest | Reason still open |
|---|---|---|---|
| 126 | opentelemetry-api | `backend/requirements-observability.txt` | GitHub has not rescanned after D2; `main` pins 1.45.2 |
| 127 | opentelemetry-api | `backend/requirements-full.txt` | same |
| 122 | opentelemetry-api | `backend/requirements-full.txt` | same |
| 111 | opentelemetry-api | `backend/requirements-observability.txt` | same |

No alert was dismissed. `origin/main` at `d41957e` pins `opentelemetry-api==1.45.2` in `requirements-observability.txt`; the alerts' `updated_at` values predate the D2 merge, so the expected state after GitHub's rescan is 0. No frontend alerts remain after D1.
