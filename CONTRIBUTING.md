# Contributing

Thanks for taking a look at Hatch.

Hatch is a self-hosted, human-in-the-loop job-search workspace. Contributions should preserve that trust boundary: the system may assist, prepare, and recommend, but the user approves every external action.

## Development Basics

1. Start from the latest `main`.
2. Keep changes focused and covered by tests where behavior changes.
3. Do not commit local profile data, databases, generated documents, recordings, model files, API keys, or browser sessions.
4. Keep DOCX as the source of truth for generated CV documents.
5. Keep cloud-provider secrets host-managed; do not collect provider API keys in the browser.

## Useful Checks

```bash
python scripts/check_readme_contract.py
docker compose config --quiet
```

Frontend:

```bash
cd frontend
npm run type-check
npm test
```

Backend:

```bash
cd backend
python -m pytest
```

## Pull Requests

Open focused pull requests with:

- a short summary of the user-facing change;
- test evidence or a clear reason tests were not run;
- notes for any migration, reset, or capability requirement.
