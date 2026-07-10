# Testing

Common checks:

```bash
make test
make lint
docker compose config --quiet
```

Frontend:

```bash
cd frontend
npm run type-check
npm test
npx playwright test
```

Backend:

```bash
cd backend
python -m pytest
```
