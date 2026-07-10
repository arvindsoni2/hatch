# Repository Structure

```text
backend/        FastAPI services, agents, storage, and document workflows
frontend/       Next.js app, tests, and screenshot tooling
data/           Local application data for manual/dev installs
locales/        Market-specific packs and legal fields
scripts/        Host CLI, reset flows, model fetch, and validation helpers
docs/           Current docs, implementation specs, and archive
```

Easy installs also create `${HATCH_HOME}` for host-managed config, models, probe results, logs, and backups.
