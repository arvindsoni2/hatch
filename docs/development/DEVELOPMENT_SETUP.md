# Development Setup

Use the manual checkout flow when changing backend, frontend, or documentation from source.

```bash
git clone https://github.com/arvindsoni2/hatch.git
cd hatch
cp .env.example .env
cp data/profile.yaml.example data/profile.yaml
docker compose up -d --build
```

Useful local checks:

```bash
make test
make lint
docker compose config --quiet
```
