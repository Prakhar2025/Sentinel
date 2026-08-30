# 11: Roadmap & Build Plan

Phased plan, each phase ends with a **verification checkpoint** (a runnable command or checkable artifact). **No line cap** (owner decision): quality is enforced by checkpoints and the NFR-6 rule that every module delivers a measured capability, a test, and docs. Ordering principle: data + evaluation harness first (so every scoring change is measured from day one), console after the evaluation is green.

## Phase 0, Foundations (0.5 day)

- Repo scaffold: `src/sentinel/` layout, `pyproject.toml`, pinned deps, `.env.example`, `.gitignore`, ruff+mypy config, GitHub Actions CI.
- Initialize `docs/what-broke.md` + pre-commit freshness hook (commit fails if the file wasn't touched in the last 24 h of active development), enforcement for the honesty deliverable.
- **Verify:** `pip install -r requirements.txt && ruff check . && mypy src && pytest` (empty suite passes green). CI green on GitHub. `what-broke.md` exists with the hook armed.

## Phase 1, Data Generator + Splits (1 day)

- Seeded generator: clean population (Zipf merchants, log-normal amounts, benign device sharing), ring injector (attack model doc 01), ring-stratified 60/20/20 split, labels.
- **Verify:** unit tests (determinism, split integrity, distribution assertions) pass; `python -m sentinel.generate --seed 42` writes 1,000 events with exactly 100 labeled fraud. `what-broke.md` updated with any failures hit in this phase.

## Phase 2, Entity Pipeline + Graph (1 day)

- Parsers/normalizers, Pydantic models, networkx GraphStore adapter, upsert + derived attributes.
- **Verify:** unit tests on all parser cases; a hand-built 12-node fixture produces the expected feature inputs; GraphML round-trip stable hash. `what-broke.md` updated with any failures hit in this phase.

## Phase 3, Scorer + Verdict Engine (1.5 days)

- Features F1–F7, weighted ensemble, reason codes, thresholds, degradation paths, audit writes.
- **Verify:** unit tests ≥ 90% on scorer; calibration-split metrics hit design point (P ≥ 0.80, R ≥ 0.70); thresholds locked and recorded. `what-broke.md` updated with any failures hit in this phase.

## Phase 4, API + Audit (1 day)

- FastAPI endpoints (doc 06), idempotency, error mapper, masking, health/readiness.
- **Verify:** contract tests green; idempotent replay test; failure-injection tests show REVIEW-not-500. `what-broke.md` updated with any failures hit in this phase.

## Phase 5, Bedrock LLM Services (1 day)

- Explanation service (gpt-oss 120B → GLM-5 fallback), extraction backfill (Nova Lite), jsonschema validation + retry, cost logging.
- **Verify:** stub tests green in CI; one manual `@pytest.mark.bedrock` run: real narratives generated, all `explanation_status=DONE`, spend < $2. `what-broke.md` updated with any failures hit in this phase.

## Phase 6, Evaluation Harness + Adversarial Pack (1.5 days)

- Single held-out test run → `metrics.json` + `report.md` with CI-bounded precision/recall, per-ring recall, FP cost ₹, sensitivity table.
- Baseline comparator (FR-13): LR + GBDT on the same features/splits, side-by-side in the report.
- Evasion pack (FR-12): slow-rate, rotation, benign-mimicry, partitioned-ring strategies with per-strategy evasion table.
- **Verify:** `make evaluate` reproduces identical `metrics.json` twice; report contains all metric spec items from doc 05 including evasion and baseline tables. **Back-fill measured p95 latency into docs 02/03 (replacing design targets).** `what-broke.md` updated with any failures hit in this phase.

## Phase 7, Analyst Console + Demo Replay (2 days)

- Next.js console, 4 views only (doc 02): Live Queue, Evidence drill-down with cluster graph (react-flow), Evaluation report (recharts on `metrics.json`), Demo replay.
- Demo replay CLI (FR-14): deterministic scripted scenario (ring caught across 4 merchants) powering the video and the console's replay view.
- **Verify:** console dev server against the FastAPI serves all 4 views with live data; replay scenario runs end-to-end twice with identical output; console renders the caught-ring evidence (merchants, taint path, LLM narrative). `what-broke.md` updated with any failures hit in this phase.

## Phase 8, README, Pitch, Polish (1 day)

- README (metrics table, ASCII architecture, setup, what-broke), pitch script + recorded video, final repo hygiene.
- **Verify:** fresh-clone setup works (`make setup && make evaluate`); 5-min video within time; repository checklist fully ticked. `what-broke.md` complete, every entry real, timestamped.

## Buffer, 1 day (Windows environment quirks, threshold honest-look adjustments with disclosure, video re-takes)

## Scope Discipline (replaces the old line budget)

The line cap was removed by owner decision. What still holds:

1. Every module must deliver a **measured capability** (a metric in the report, a working endpoint, a console view), a **test**, and **docs**. Anything that can't name all three is cut.
2. The console stays at 4 views (doc 02); no auth screens, settings, or multi-role UI.
3. No speculative abstraction, no microservice splitting, no GNN training at n=1,000 (doc 05 states why).
4. Phase verification checkpoints remain the build gate; if a checkpoint fails, the phase isn't done.
5. Cutting order if time runs short: FR-11 feedback stub → console replay view polish → evaluation-report chart styling. Core detector, evaluation honesty, and the API are never cut.

## v2 Roadmap (documented only, not built)

1. GNN (GraphSAGE) on the same feature schema at ≥ 10⁵ labeled events.
2. Streaming ingestion (Kinesis/Flink) + sharded Neo4j, production topology already in doc 03.
3. Federated cross-merchant privacy layer (verdict sharing without identity sharing).
4. Extension to return-risk scoring and chargeback evidence auto-response (other loss classes).
