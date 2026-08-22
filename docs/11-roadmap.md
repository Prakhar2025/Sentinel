# 11: Roadmap & Build Plan

Phased plan, each phase ends with a **verification checkpoint** (a runnable command or checkable artifact). Line budgets enforce the 3,000-line constraint. Ordering principle: data + evaluation harness first (so every scoring change is measured from day one), UI last.

## Phase 0, Foundations (0.5 day)

- Repo scaffold: `src/sentinel/` layout, `pyproject.toml`, pinned deps, `.env.example`, `.gitignore`, ruff+mypy config, GitHub Actions CI.
- Initialize `docs/what-broke.md` + pre-commit freshness hook (commit fails if the file wasn't touched in the last 24 h of active development), enforcement for the honesty deliverable.
- **Verify:** `pip install -r requirements.txt && ruff check . && mypy src && pytest` (empty suite passes green). CI green on GitHub. `what-broke.md` exists with the hook armed.

## Phase 1, Data Generator + Splits (1 day, ~450 lines)

- Seeded generator: clean population (Zipf merchants, log-normal amounts, benign device sharing), ring injector (attack model doc 01), ring-stratified 60/20/20 split, labels.
- **Verify:** unit tests (determinism, split integrity, distribution assertions) pass; `python -m sentinel.generate --seed 42` writes 1,000 events with exactly 100 labeled fraud. `what-broke.md` updated with any failures hit in this phase.

## Phase 2, Entity Pipeline + Graph (1 day, ~400 lines)

- Parsers/normalizers, Pydantic models, networkx GraphStore adapter, upsert + derived attributes.
- **Verify:** unit tests on all parser cases; a hand-built 12-node fixture produces the expected feature inputs; GraphML round-trip stable hash. `what-broke.md` updated with any failures hit in this phase.

## Phase 3, Scorer + Verdict Engine (1.5 days, ~450 lines)

- Features F1–F7, weighted ensemble, reason codes, thresholds, degradation paths, audit writes.
- **Verify:** unit tests ≥ 90% on scorer; calibration-split metrics hit design point (P ≥ 0.80, R ≥ 0.70); thresholds locked and recorded. `what-broke.md` updated with any failures hit in this phase.

## Phase 4, API + Audit (1 day, ~350 lines)

- FastAPI endpoints (doc 06), idempotency, error mapper, masking, health/readiness.
- **Verify:** contract tests green; idempotent replay test; failure-injection tests show REVIEW-not-500. `what-broke.md` updated with any failures hit in this phase.

## Phase 5, Bedrock LLM Services (1 day, ~250 lines)

- Explanation service (gpt-oss 120B → GLM-5 fallback), extraction backfill (Nova Lite), jsonschema validation + retry, cost logging.
- **Verify:** stub tests green in CI; one manual `@pytest.mark.bedrock` run: real narratives generated, all `explanation_status=DONE`, spend < $2. `what-broke.md` updated with any failures hit in this phase.

## Phase 6, Evaluation Harness + Report (1 day, ~300 lines)

- Single held-out test run → `metrics.json` + `report.md` with CI-bounded precision/recall, per-ring recall, FP cost ₹, sensitivity table.
- **Verify:** `make evaluate` reproduces identical `metrics.json` twice; report contains all metric spec items from doc 05. **Back-fill measured p95 latency into docs 02/03 (replacing design targets).** `what-broke.md` updated with any failures hit in this phase.

## Phase 7, Dashboard + Demo Data (1 day, ≤ 150 lines)

- Single-page analyst view: ranked queue, entity drill-down, embedded cluster graph.
- **Verify:** served by FastAPI at `/dashboard`; demo scenario (ring caught across 4 merchants) renders with evidence visible. `what-broke.md` updated with any failures hit in this phase.

## Phase 8, README, Pitch, Polish (1 day)

- README (metrics table, ASCII architecture, setup, what-broke), pitch script + recorded video, final repo hygiene.
- **Verify:** fresh-clone setup works (`make setup && make evaluate`); 5-min video within time; CLAUDE.md deliverable checklist fully ticked. `what-broke.md` complete, every entry real, timestamped.

## Buffer, 1 day (Windows environment quirks, threshold honest-look adjustments with disclosure, video re-takes)

## Line Budget Accounting

```
Phase itemized budgets:  450 + 400 + 450 + 350 + 250 + 300 + 150   = 2,350
Scaffold + config (pyproject, env, CI, .env.example)               =   ~150
  src/ total (what the 3,000-line cap counts)                      ≈ 2,500
Tests (budgeted separately, ~900–1,200 lines for ≥90% coverage)    = 1,000–1,200
```

**Scope of the cap (decided explicitly, disclosed in README):** the 3,000-line constraint counts `src/` production code + the single-file dashboard. Tests are tracked separately, a 90% coverage requirement (NFR-7) is impossible to meet inside a 3,000-line total that also contains the product, and hiding test lines to fit a cap would be the opposite of honest. If `src/` approaches 2,800 mid-build, the P2 feedback endpoint is cut first, then the dashboard shrinks to 100 lines (risk P5, doc 10).

## v2 Roadmap (documented only, not built)

1. GNN (GraphSAGE) on the same feature schema at ≥ 10⁵ labeled events.
2. Streaming ingestion (Kinesis/Flink) + sharded Neo4j, production topology already in doc 03.
3. Federated cross-merchant privacy layer (verdict sharing without identity sharing).
4. Extension to return-risk scoring and chargeback evidence auto-response (other loss classes).
