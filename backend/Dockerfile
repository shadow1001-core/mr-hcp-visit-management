FROM ghcr.io/astral-sh/uv:0.6.9 AS uv

FROM python:3.12-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

CMD ["sh", "-c", "uv run --locked --no-sync alembic upgrade head && uv run --locked --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
