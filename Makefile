.PHONY: setup check lint format type test test-all console-setup console serve backfill merchant-token challenger loadtest calibrate evaluate models hooks clean

# One-time setup: virtualenv, pinned deps, git hooks.
setup:
	py -3.12 -m venv .venv
	.venv/Scripts/python -m pip install --upgrade pip
	.venv/Scripts/python -m pip install -r requirements.txt
	.venv/Scripts/python -m pip install -e . --no-deps
	@cp scripts/hooks/pre-commit .git/hooks/pre-commit 2>/dev/null || true
	@echo "Setup complete. Activate: .venv/Scripts/activate"

# Install git hooks only (idempotent).
hooks:
	@cp scripts/hooks/pre-commit .git/hooks/pre-commit 2>/dev/null || true
	@echo "hooks installed"

# Everything CI runs, locally.
check: lint format-check type test

lint:
	.venv/Scripts/python -m ruff check src tests scripts

format:
	.venv/Scripts/python -m ruff format src tests scripts

format-check:
	.venv/Scripts/python -m ruff format --check src tests scripts

type:
	.venv/Scripts/python -m mypy src

test:
	.venv/Scripts/python -m pytest -m "not slow"

test-all:
	.venv/Scripts/python -m pytest

# One-time console setup: install the Next.js analyst console dependencies.
console-setup:
	cd console && npm install

# Run the analyst console on port 3000 (needs `make serve` on 8000).
console:
	cd console && npm run dev

# Run the API service locally on port 8000.
serve:
	.venv/Scripts/python -m uvicorn sentinel.service:create_app --factory --port 8000

# Backfill LLM explanations for pending verdicts (bounded; costs Bedrock money).
backfill:
	.venv/Scripts/python -m sentinel.backfill --limit 20

# Mint a per-merchant JWT (default TTL 24h): make merchant-token MERCHANT_ID=mcht_00001
merchant-token:
	.venv/Scripts/python -m sentinel.merchant_token $(MERCHANT_ID) $(TTL)

# Train the shadow challenger on train-split features (writes evaluation/challenger.pkl).
challenger:
	.venv/Scripts/python -m sentinel.challenger_train

# Load test: measured throughput and latency of the verdict pipeline.
loadtest:
	.venv/Scripts/python -m sentinel.loadtest

# Calibrate weights/thresholds on train+calibration splits (writes evaluation/model_config.json).
calibrate:
	.venv/Scripts/python -m sentinel.calibrate

# Held-out evaluation; calibrates first on a fresh clone (no locked config yet).
evaluate:
	@test -f evaluation/model_config.json || $(MAKE) calibrate
	.venv/Scripts/python -m sentinel.evaluate

# Phase 0: one-shot Bedrock model verification (bounded spend; see docs/08).
models:
	.venv/Scripts/python scripts/verify_models.py

clean:
	@rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	@find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
