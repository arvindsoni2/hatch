# JobPilot — Project Commands
# Usage: make <target>

.PHONY: dev dev-back dev-front scrape scrape-one test test-back test-front \
        test-be test-fe migrate migrate-new docker-up docker-down docker-build docker-logs \
        docker-restart lint seed clean reset-user help ci \
        ghost-analyse ghost-stats email-pending email-generate

# ──────────────────────── Development ────────────────────────

dev: ## Start full stack locally (backend + frontend)
	@echo "Starting JobPilot development environment..."
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

scrape-one: ## Run a single scraper (usage: make scrape-one BOARD=contractoruk)
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

migrate: ## Run Alembic migrations
	cd backend && alembic upgrade head

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
	@echo "JobPilot starting..."
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

# ──────────────────────── Code Quality ───────────────────────

lint: ## Run linters
	cd backend && ruff check app/ tests/ --fix
	cd frontend && npm run lint

format: ## Format code
	cd backend && ruff format app/ tests/
	cd frontend && npx prettier --write "src/**/*.{ts,tsx}"

# ──────────────────────── Utilities ──────────────────────────

reset-user: ## Wipe all job/application data to start fresh as a new user
	@bash reset-user-data.sh

clean: ## Remove generated files and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .next -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf backend/htmlcov 2>/dev/null || true

stats: ## Show job statistics
	@curl -s http://localhost:8000/api/jobs/stats | python -m json.tool

ghost-analyse: ## Run ghost job analysis on all unscored jobs
	@curl -s -X POST http://localhost:8000/api/ghost/analyse-all | python -m json.tool

ghost-stats: ## Show ghost detection statistics
	@curl -s http://localhost:8000/api/ghost/stats | python -m json.tool

email-pending: ## Show pending follow-up emails awaiting review
	@curl -s http://localhost:8000/api/emails/pending | python -m json.tool

email-generate: ## Generate follow-up email: make email-generate APP_ID=xxx TYPE=post_application
	@curl -s -X POST http://localhost:8000/api/emails/generate/$(APP_ID) \
		-H 'Content-Type: application/json' \
		-d '{"email_type": "$(TYPE)"}' | python -m json.tool

help: ## Show this help
	@echo "JobPilot — Available Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
