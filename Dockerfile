# --- frontend build ---
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- runtime: Python + Playwright Chromium + ffmpeg + espeak-ng ---
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg espeak-ng nodejs npm && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && pip install --no-cache-dir "playwright==1.49.0"
COPY scripts/package.json scripts/package.json
RUN cd scripts && npm install --no-audit --no-fund
COPY backend backend
COPY demo_sites demo_sites
COPY scripts scripts
COPY eval eval
COPY data data
COPY --from=web /app/frontend/dist frontend/dist
# cached demo results + sessions are baked into the image (data/); only env vars are needed for "Run live"
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
