.PHONY: backend-sync backend-format backend-lint backend-typecheck backend-test backend-check \
	frontend-format frontend-lint frontend-typecheck frontend-build frontend-check check

UV_CACHE_DIR ?= $(CURDIR)/work/uv-cache
UV_PYTHON_INSTALL_DIR ?= $(CURDIR)/work/uv-python
export UV_CACHE_DIR UV_PYTHON_INSTALL_DIR

backend-sync:
	cd backend && uv sync --group dev --locked

backend-format:
	cd backend && uv run --locked --no-sync ruff format app tests
	cd backend && uv run --locked --no-sync ruff check --fix app tests

backend-lint:
	cd backend && uv run --locked --no-sync ruff format --check app tests
	cd backend && uv run --locked --no-sync ruff check app tests

backend-typecheck:
	cd backend && uv run --locked --no-sync mypy app

backend-test:
	cd backend && uv run --locked --no-sync pytest

backend-check: backend-lint backend-typecheck backend-test

frontend-format:
	cd frontend && npm run format

frontend-lint:
	cd frontend && npm run lint
	cd frontend && npm run format:check

frontend-typecheck:
	cd frontend && npm run typecheck

frontend-build:
	cd frontend && npm run build

frontend-check: frontend-lint frontend-typecheck frontend-build

check: backend-check frontend-check
