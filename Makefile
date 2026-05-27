.DEFAULT_GOAL := help
DC := docker compose

.PHONY: help install run worker bot test lint typecheck fmt check migrate revision upgrade downgrade compose-up compose-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install dev dependencies
	pip install -r requirements-dev.txt
	pre-commit install

run: ## Run the API locally with autoreload
	uvicorn app.main:app --host $${API_HOST:-0.0.0.0} --port $${API_PORT:-8000} --reload

bot: ## Run the Telegram bot
	python -m bot

test: ## Run the test suite
	pytest

lint: ## Lint with ruff
	ruff check app bot tests
	ruff format --check app bot tests

typecheck: ## Static type-check with mypy
	mypy app bot

fmt: ## Auto-format the codebase
	ruff format app bot tests
	ruff check --fix app bot tests

check: lint typecheck test ## Run lint, type-check and tests

migrate: upgrade ## Alias for `upgrade`

revision: ## Create a new Alembic revision (use: make revision m="message")
	alembic revision --autogenerate -m "$(m)"

upgrade: ## Apply all migrations
	alembic upgrade head

downgrade: ## Roll back one migration
	alembic downgrade -1

compose-up: ## Start the full stack (app + db + bot)
	$(DC) up --build

compose-down: ## Stop the stack and remove volumes
	$(DC) down -v

clean: ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
