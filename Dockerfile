# --- frontend build ---
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- runtime: Python (uv) + Playwright Chromium + ffmpeg + espeak-ng ---
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.7.5 /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng nodejs npm && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev && uv run --no-sync playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
COPY scripts/package*.json scripts/
RUN cd scripts && npm install --no-audit --no-fund
COPY backend backend
COPY demo_sites demo_sites
COPY scripts scripts
COPY eval eval
COPY data data
COPY --from=web /app/frontend/dist frontend/dist
# cached demo results + sessions are baked into the image (data/); only env vars are needed for "Run live"
ENV PORT=8000 PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
