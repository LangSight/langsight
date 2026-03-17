# ─────────────────────────────────────────────────────────────────────────────
# Stage 1: builder — install dependencies with uv
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copy dependency manifests first (cache layer)
COPY pyproject.toml uv.lock ./

# Install dependencies into /app/.venv (no project itself yet)
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and install the project
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2: runtime — minimal image with only what's needed to run
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user
RUN groupadd --gid 1001 langsight \
 && useradd --uid 1001 --gid langsight --shell /bin/bash --create-home langsight

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder --chown=langsight:langsight /app/.venv /app/.venv
# Copy source
COPY --from=builder --chown=langsight:langsight /app/src /app/src

# Put the venv on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Runtime environment defaults (override via docker-compose or -e flags)
ENV LANGSIGHT_STORAGE_MODE=sqlite
ENV LANGSIGHT_CLICKHOUSE_URL=http://clickhouse:8123
ENV LANGSIGHT_CLICKHOUSE_DATABASE=langsight
ENV LANGSIGHT_POSTGRES_URL=""
ENV LANGSIGHT_LOG_LEVEL=INFO

USER langsight

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/status')"

CMD ["uvicorn", "langsight.api.server:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2"]
