.PHONY: setup sessions cache eval test run build docker
setup:
	uv sync && uv run playwright install chromium
	cd frontend && npm install
	cd scripts && npm install
build:
	cd frontend && npm run build
sessions:
	uv run scripts/generate_sessions.py
cache:
	uv run scripts/precompute_cache.py
eval:
	uv run eval/run_eval.py
test: build
	uv run pytest -q
run: build
	uv run uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
docker:
	docker build -t heard . && docker run --rm -p 8000:8000 --env-file .env heard
