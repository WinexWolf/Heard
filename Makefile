.PHONY: setup sessions cache eval test run build
setup:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r backend/requirements.txt && playwright install chromium
	cd frontend && npm install
	cd scripts && npm install
sessions:
	python scripts/generate_sessions.py
cache:
	python scripts/precompute_cache.py
eval:
	python eval/run_eval.py
build:
	cd frontend && npm run build
run: build
	uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
test:
	python -m pytest backend/tests -q
	cd frontend && npm run test:e2e
