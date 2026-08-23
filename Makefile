.PHONY: setup check lint format type test test-all serve backfill calibrate evaluate models hooks clean

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

# Run the API service locally on port 8000.
serve:
	.venv/Scripts/python -m uvicorn sentinel.service:create_app --factory --port 8000

# Backfill LLM explanations for pending verdicts (bounded; costs Bedrock money).
backfill:
	.venv/Scripts/python -m sentinel.backfill --limit 20

# Calibrate weights/thresholds on train+calibration splits (writes evaluation/model_config.json).
calibrate:
	.venv/Scripts/python -m sentinel.calibrate

# Phase 6: regenerate data, run evaluation, write metrics (added in Phase 6).
evaluate:
	.venv/Scripts/python -m sentinel.evaluate

# Phase 0: one-shot Bedrock model verification (bounded spend; see docs/08).
models:
	.venv/Scripts/python scripts/verify_models.py

clean:
	@rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	@find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
