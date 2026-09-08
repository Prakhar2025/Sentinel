LIVE_API := https://jwss73rdpj.us-east-1.awsapprunner.com
LIVE_KEY := pk_live_eee2a134ff8835d0

.PHONY: setup check lint format type test test-all console-setup console snapshot-live serve backfill snapshot merchant-token challenger loadtest calibrate evaluate models hooks clean

# Interpreter path. Absolute via CURDIR: GNU make on Windows without a POSIX
# shell resolves a bare relative command through PATH, which can silently pick
# up another project's virtualenv. Absolute paths remove the ambiguity.
ifeq ($(OS),Windows_NT)
PY := $(CURDIR)/.venv/Scripts/python
DEMOENV := set NEXT_PUBLIC_DEMO=1&&
else
PY := $(CURDIR)/.venv/bin/python
DEMOENV := NEXT_PUBLIC_DEMO=1
endif

# One-time setup: virtualenv, pinned deps, git hooks.
setup:
	py -3.12 -m venv .venv
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -r requirements.txt
	$(PY) -m pip install -e . --no-deps
	@-$(PY) -c "import shutil;shutil.copy('scripts/hooks/pre-commit','.git/hooks/pre-commit')"
	@echo "Setup complete. Activate: .venv/Scripts/activate"

# Install git hooks only (idempotent).
hooks:
	@-$(PY) -c "import shutil;shutil.copy('scripts/hooks/pre-commit','.git/hooks/pre-commit')"
	@echo "hooks installed"

# Everything CI runs, locally.
check: lint format-check type test

lint:
	$(PY) -m ruff check src tests scripts

format:
	$(PY) -m ruff format src tests scripts

format-check:
	$(PY) -m ruff format --check src tests scripts

type:
	$(PY) -m mypy src

test:
	$(PY) -m pytest -m "not slow"

test-all:
	$(PY) -m pytest

# One-time console setup: install the Next.js analyst console dependencies.
console-setup:
	cd console && npm install

# Run the analyst console on port 3000 (needs `make serve` on 8000).
console:
	cd console && npm run dev

# Run the API service locally on port 8000.
serve:
	$(PY) -m uvicorn sentinel.service:create_app --factory --port 8000

# Backfill LLM explanations for pending verdicts (bounded; costs Bedrock money).
backfill:
	$(PY) -m sentinel.backfill --limit 20

# Zero-backend static demo snapshot into console/out/ (hostable anywhere, free).
snapshot:
	$(PY) scripts/make_demo_fixtures.py
	cd console && $(DEMOENV) npx next build

# Console build wired to the deployed App Runner API (playground works; needs
# the service running). Contrast with `snapshot`, which bakes fixtures and
# needs no backend at all.
snapshot-live:
	$(PY) scripts/build_live_console.py $(LIVE_API) $(LIVE_KEY)

# Mint a per-merchant JWT (default TTL 24h): make merchant-token MERCHANT_ID=mcht_00001
merchant-token:
	$(PY) -m sentinel.merchant_token $(MERCHANT_ID) $(TTL)

# Train the shadow challenger on train-split features (writes evaluation/challenger.pkl).
challenger:
	$(PY) -m sentinel.challenger_train

# Load test: measured throughput and latency of the verdict pipeline.
loadtest:
	$(PY) -m sentinel.loadtest

# Calibrate weights/thresholds on train+calibration splits (writes evaluation/model_config.json).
calibrate:
	$(PY) -m sentinel.calibrate

# Held-out evaluation; calibrates first on a fresh clone (no locked config yet).
evaluate:
ifeq ($(wildcard evaluation/model_config.json),)
	$(PY) -m sentinel.calibrate
endif
	$(PY) -m sentinel.evaluate

# Phase 0: one-shot Bedrock model verification (bounded spend; see docs/08).
models:
	$(PY) scripts/verify_models.py

clean:
	@$(PY) scripts/clean.py
