# ---- Stage 1: Builder ----
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install CPU-only PyTorch (no CUDA) — GPU inference is handled by Ollama.
# --frozen ensures the lockfile is used exactly as-is.
RUN uv sync --frozen --no-dev --no-install-project \
    --extra-index-url https://download.pytorch.org/whl/cpu

COPY . .

RUN uv sync --frozen --no-dev \
    --extra-index-url https://download.pytorch.org/whl/cpu

# ---- Stage 2: Runtime ----
FROM python:3.12-slim

RUN groupadd --system appgroup && useradd --system --gid appgroup appuser

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/obsidianrag /app/obsidianrag

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000

USER appuser

ENTRYPOINT ["uvicorn", "obsidianrag.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
