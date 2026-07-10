# Hatch Release Checklist

Use this checklist before publishing a public portfolio release from `main`.

## Product Evidence

- Recreate README screenshots:

  ```bash
  cd frontend
  npx playwright test e2e/readme-screenshots.spec.ts --project=readme-screenshots
  ```

- Confirm screenshots use fictional demo data only.
- Review the main workflow: onboarding, Today, Pipeline, Applications, CV Studio, and Interview Prep.

## Contracts

- Run the README contract:

  ```bash
  python scripts/check_readme_contract.py
  ```

- Run frontend checks:

  ```bash
  cd frontend
  npm run type-check
  npm test
  ```

- Run backend checks when backend code changes:

  ```bash
  cd backend
  python -m pytest
  ```

## Safety Boundaries

- Hatch does not auto-apply or message recruiters.
- Generated documents require human review.
- Cloud provider secrets stay host-managed.
- DOCX remains the generated CV source of truth.
- Local `data/` content, models, sessions, databases, recordings, and generated documents remain untracked.

## Runtime

- Rebuild local containers from the latest source when validating the end-to-end app.
- Check backend health and frontend reachability.
- Inspect recent backend and frontend logs for startup errors.
