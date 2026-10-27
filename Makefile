.PHONY: setup sessions cache eval test run build docker
setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt && playwright install chromium
	cd frontend && npm install
	cd scripts && npm install
build:
	cd frontend && npm run build
sessions:
	python scripts/generate_sessions.py
cache:
	python scripts/precompute_cache.py
eval:
	python eval/run_eval.py
test: build
	python -m pytest backend/tests -q
run: build
	uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
docker:
	docker build -t heard . && docker run --rm -p 8000:8000 --env-file .env heard
