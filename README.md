# MR–HCP Academic Visit Management

A desktop web application for planning, recording, and reviewing regulated academic visits between medical representatives (MRs) and healthcare professionals (HCPs).

## Status

The repository contains the runnable MVP:

- FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, PostgreSQL configuration, and pytest;
- React, TypeScript, Vite, Ant Design, React Router, and Axios;
- visit planning, check-in/check-out compliance evaluation, report management, and a monthly product dashboard;
- health endpoints/pages and shared development commands.

The confirmed business and technical design is documented under [`docs/`](docs/).

## Prerequisites

- Docker with Docker Compose for the one-command stack; or
- Python 3.12, managed locally with [uv](https://docs.astral.sh/uv/);
- Node.js 22 or later;
- PostgreSQL for database-backed development. The health endpoint does not require a live database.

## Configuration

Copy the example environment file and replace placeholder values locally:

```bash
cp .env.example .env
```

Secrets and local `.env` files must not be committed.

## Docker Compose

Copy the example environment file, replace the placeholder password in all related values,
then start PostgreSQL, the migrated API, and the production frontend:

```bash
cp .env.example .env
docker compose up --build -d
docker compose exec backend uv run --locked --no-sync python -m app.db.seed
```

The application is available at `http://localhost:5173`, the API at
`http://localhost:8000`, and the API health endpoint at `GET /health`.
Database migrations run before the backend starts. Seed data remains an explicit command and
is never loaded implicitly in production startup.

Stop the stack with:

```bash
docker compose down
```

## Backend

```bash
make backend-sync
cd backend
uv run --locked --no-sync uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`, with health at `GET /health` and OpenAPI docs at `/docs`.

### Local demo data

After configuring `DATABASE_URL`, apply migrations and explicitly load the deterministic demo data:

```bash
cd backend
uv run --locked --no-sync alembic upgrade head
cd ..
make backend-seed
```

The seed contains one MR, two hospitals with coordinates, three HCPs and three products,
plus their department and practice relationships. It never creates visit plans, visits,
reports, material distributions, or compliance findings. The command is idempotent and may
be run repeatedly. It is not part of application startup and refuses to run when
`APP_ENV=production`.

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
export TEST_DATABASE_URL=postgresql+psycopg://mr_hcp:your-password@localhost:5432/mr_hcp_test
make backend-check
make frontend-check
```

Backend integration tests deliberately fail with a clear setup error when `TEST_DATABASE_URL`
is missing; use a dedicated disposable PostgreSQL database because migrations reset its schema.

Run all non-mutating checks:

```bash
make check
```

Formatting commands are available as `make backend-format` and `make frontend-format`.
