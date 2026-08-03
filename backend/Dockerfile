# ---- Stage 1: Builder ----
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

# The lockfile pins non-macOS Torch to the explicit CPU-only index.
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

RUN uv sync --frozen --no-dev

# ---- Stage 2: Runtime ----
FROM python:3.12-slim

RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/obsidianrag /app/obsidianrag

RUN mkdir -p /home/appuser/.cache/huggingface && \
    chown -R appuser:appgroup /home/appuser

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

USER appuser

ENTRYPOINT ["uvicorn", "obsidianrag.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
