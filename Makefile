.DEFAULT_GOAL := help
SHELL := /bin/bash

API := apps/ingest-api
SIM := apps/device-simulator
WEB := apps/dashboard

.PHONY: help up down restart logs ps build seed test test-domain lint format typecheck contracts ci clean

help: ## Show available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

up: ## Start the whole system
	docker compose up -d --build
	@echo "dashboard  http://localhost:$${DASHBOARD_PORT:-3000}"
	@echo "api        http://localhost:$${API_PORT:-8000}/docs"
	@echo "simulator  http://localhost:$${SIMULATOR_API_PORT:-8001}/docs"

down: ## Stop and remove containers
	docker compose down

restart: down up ## Recreate the stack

logs: ## Tail logs from every service
	docker compose logs -f

ps: ## Show container status
	docker compose ps

build: ## Build all images without starting them
	docker compose build

seed: ## Apply database migrations
	docker compose run --rm ingest-api alembic upgrade head

test: ## Run backend and frontend test suites
	cd $(API) && pytest
	cd $(WEB) && npm run typecheck

test-domain: ## Run only the domain rule tests (no containers required)
	cd $(API) && pytest tests/unit -q

lint: ## Lint everything
	ruff check $(API) $(SIM) ml
	ruff format --check $(API) $(SIM) ml
	cd $(WEB) && npm run lint

format: ## Autoformat everything
	ruff check --fix $(API) $(SIM) ml
	ruff format $(API) $(SIM) ml
	cd $(WEB) && npm run format

typecheck: ## Type-check backend and frontend
	cd $(API) && mypy src
	cd $(SIM) && mypy src
	cd $(WEB) && npm run typecheck

contracts: ## Verify the layering rules hold
	cd $(API) && lint-imports

ci: lint typecheck contracts test ## Everything CI runs

clean: ## Remove containers, volumes and caches
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .mypy_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
