# Hatch — Project Commands
# Usage: make <target>

.PHONY: dev dev-back dev-front scrape scrape-one test test-back test-front \
        test-be test-fe migrate migrate-new docker-up docker-down docker-build docker-logs \
        docker-restart lint format models seed clean reset-user reset-app-lock \
        test-reset-user audit-scripts help ci

# ──────────────────────── Development ────────────────────────

dev: ## Start full stack locally (backend + frontend)
	@echo "Starting Hatch development environment..."
	@make dev-back &
	@make dev-front

dev-back: ## Start backend with hot reload
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-front: ## Start frontend with hot reload
	cd frontend && npm run dev

# ──────────────────────── Scraping ───────────────────────────

scrape: ## Run all scrapers manually
	@echo "Triggering all scrapers..."
	curl -s -X POST http://localhost:8000/api/jobs/scrape | python -m json.tool

scrape-one: ## Run a single scraper (usage: make scrape-one BOARD=reed)
	@echo "Triggering $(BOARD) scraper..."
	curl -s -X POST "http://localhost:8000/api/jobs/scrape?source=$(BOARD)" | python -m json.tool

# ──────────────────────── Testing ────────────────────────────

test: test-back test-front ## Run all tests

test-back: ## Run backend tests
	cd backend && python -m pytest tests/ -v --tb=short

test-front: ## Run frontend tests
	cd frontend && npm test

test-be: ## Run backend tests (quiet, CI-friendly)
	cd backend && pytest -q

test-fe: ## Run frontend tests (CI-friendly)
	cd frontend && npm test

ci: lint test-be test-fe ## Run full CI check (lint + tests)

test-cov: ## Run backend tests with coverage
	cd backend && python -m pytest tests/ -v --cov=app --cov-report=html

# ──────────────────────── Database ───────────────────────────

migrate: ## Set up or safely migrate the application database
	cd backend && python -m app.database_setup

migrate-new: ## Create new migration (usage: make migrate-new MSG="add_column")
	cd backend && alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback last migration
	cd backend && alembic downgrade -1

seed: ## Seed database with sample data
	cd backend && python -m app.seed

# ──────────────────────── Docker ─────────────────────────────

docker-build: ## Build all Docker images
	docker compose build

docker-up: ## Start all containers
	docker compose up -d --build
	@echo "Hatch starting..."
	@echo "  Dashboard: http://localhost:3000"
	@echo "  API:       http://localhost:8000/docs"

docker-down: ## Stop all containers
	docker compose down

docker-logs: ## Tail logs from all containers
	docker compose logs -f

docker-restart: ## Rebuild and restart
	docker compose down
	docker compose up -d --build

docker-shell-back: ## Shell into backend container
	docker compose exec backend bash

docker-shell-front: ## Shell into frontend container
	docker compose exec frontend sh

# ──────────────────────── AI models ──────────────────────────

models: ## Download bundled llama.cpp model files (run once before first docker-up)
	@bash scripts/fetch_models.sh

# ──────────────────────── Code Quality ───────────────────────

lint: ## Run linters
	cd backend && ruff check app/ tests/
	cd frontend && npm run lint

format: ## Format code
	cd backend && ruff format app/ tests/
	cd frontend && npx prettier --write "src/**/*.{ts,tsx}"

# ──────────────────────── Utilities ──────────────────────────

reset-user: ## Wipe all local user data and return Hatch to first-run state
	@bash scripts/reset-user-data.sh

test-reset-user: ## Verify reset behavior against an isolated temporary data directory
	@bash scripts/tests/test_reset_user_data.sh

reset-app-lock: ## Clear only the local app-lock password and sessions
	@bash scripts/reset-app-lock.sh

audit-scripts: ## Validate operational scripts without destructive live actions
	@bash -n install.sh backend/entrypoint.sh scripts/*.sh scripts/installer/*.sh scripts/tests/*.sh
	@bash scripts/tests/test_linux_installer.sh
	@python -m compileall -q scripts backend/app/skills
	@bash scripts/tests/test_reset_user_data.sh
	@cd backend && pytest -q --no-cov tests/test_scripts/test_reset_app_lock.py
	@python scripts/dead_code_check.py
	@docker compose config --quiet

clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf backend/htmlcov 2>/dev/null || true

stats: ## Show job statistics
	@curl -s http://localhost:8000/api/jobs/stats | python -m json.tool

help: ## Show this help
	@echo "Hatch — Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
