.PHONY: up down migrate shell-api test-backend type-check-frontend seed eval-local build logs

up:
	docker compose up -d --build

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

migrate:
	docker compose run --rm migrate

shell-api:
	docker compose exec api bash

seed:
	docker compose exec api python -m app.scripts.seed_demo_data

# Run the eval CLI against a local test set
# Usage: make eval-local TEST_SET_ID=<uuid>
eval-local:
	cd runner && python -m runner.cli run --config ../rageval.yaml --test-set $(TEST_SET_ID)

# Run backend unit tests
test-backend:
	docker compose exec api pytest tests/ -v --cov=app

# Run frontend type check
type-check-frontend:
	cd frontend && npx tsc --noEmit

# Install Python dev dependencies locally (for IDE support)
install-dev:
	pip install -r backend/requirements-dev.txt
	pip install -r runner/requirements.txt

# Format and lint
lint:
	docker compose exec api ruff check app/
	docker compose exec api ruff format --check app/

format:
	docker compose exec api ruff format app/
	docker compose exec api ruff check --fix app/
