# MR–HCP Academic Visit Management

A desktop web application for planning, recording, and reviewing regulated academic visits between medical representatives (MRs) and healthcare professionals (HCPs).

## Status

The repository contains the runnable project scaffold:

- FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, PostgreSQL configuration, and pytest;
- React, TypeScript, Vite, Ant Design, React Router, and Axios;
- health endpoints/pages and shared development commands.

Visit business features are intentionally not implemented yet. The confirmed design is documented under [`docs/`](docs/).

## Prerequisites

- Python 3.12, managed locally with [uv](https://docs.astral.sh/uv/);
- Node.js 22 or later;
- PostgreSQL for database-backed development. The health endpoint does not require a live database.

## Configuration

Copy the example environment file and replace placeholder values locally:

```bash
cp .env.example .env
```

Secrets and local `.env` files must not be committed.

## Backend

```bash
make backend-sync
cd backend
uv run --locked --no-sync uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`, with health at `GET /health` and OpenAPI docs at `/docs`.

## Frontend

```bash
cd frontend
npm ci
npm run dev
```

The Vite development server is available at `http://localhost:5173` and proxies `/api` to the backend.

## Quality Checks

Run individual checks from the repository root:

```bash
make backend-check
make frontend-check
```

Run all non-mutating checks:

```bash
make check
```

Formatting commands are available as `make backend-format` and `make frontend-format`.
