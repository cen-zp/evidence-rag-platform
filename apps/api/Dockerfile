FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

COPY apps/api/pyproject.toml apps/api/uv.lock ./apps/api/
RUN cd apps/api && uv sync --frozen --no-dev

FROM python:3.14-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.9.17 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace

COPY --from=builder /workspace/apps/api/.venv ./apps/api/.venv
COPY . .

WORKDIR /workspace/apps/api

CMD ["uv", "run", "--no-sync", "python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
