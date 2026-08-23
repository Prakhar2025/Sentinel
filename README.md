# Abuse-Ring Sentinel

**Defense-only fraud detection for cross-merchant identity reuse.** Catches the same UPI ID, phone number, or device fingerprint being recycled across multiple merchants to commit fraud, with explainable verdicts and honestly measured precision, recall, and false-positive cost in ₹.

> Razorpay AI Buildathon, Track 02 (AI Risk Manager). The system recommends, never acts: no autonomous blocking, no money movement, strictly defense-only.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Scaffold, tooling, CI, Bedrock model verification | done |
| 1 | Seeded synthetic generator (900 clean / 100 fraud, ring-stratified splits) | done |
| 2 | Entity normalization + identity link graph with taint propagation | done |
| 3 | F1-F7 features, deterministic scorer, verdict engine, calibration lock | done |
| 4 | FastAPI service: two-key auth, audit store, masking, spooling, degradation | done |
| 5 | Bedrock LLM layer: explanation chain, fence-stripping, cost log, backfill | done |
| 6 | Evaluation harness: held-out test, FP cost, baselines, evasion pack | done |
| 7 | Analyst console: ranked queue, evidence + cluster graph, metrics dossier, ring replay | done |
| 8 | Pitch polish | planned (see [docs/11-roadmap.md](docs/11-roadmap.md)) |

## Measured results (held-out test set, seed 42)

| Metric | Value |
|--------|-------|
| Precision (positive = BLOCK_REC) | 0.833 (95% CI 0.586-0.946) |
| Recall (event level) | 0.882 (95% CI 0.622-0.966) |
| F1 | 0.857 |
| Rings caught | 2 of 2 (incl. the sophisticated low-and-slow ring) |
| Fraud silently allowed (ALLOW band) | 0 |
| Net saving after FP + review cost | ~Rs.38,665 per 1,000 events |
| Scoring latency | p50 2.3 ms / p95 4.1 ms |

Honest disclosures in [evaluation/report.md](evaluation/report.md) once regenerated:
the GBDT baseline edges the rule ensemble on F1 (0.909 vs 0.857; the
deterministic scorer keeps the explainability contract), and slow-rate
evasion rings evade the current weights, documented as the v2
time-windowed-fanout fix. Regenerate everything with `make calibrate && make evaluate`.

## Quick start

```bash
make setup              # venv (Python 3.12), pinned deps, git hooks
make check              # lint + format check + mypy strict + pytest with coverage
make models             # one-shot Bedrock constrained-JSON verification (bounded spend)
make calibrate          # lock weights/thresholds on train + calibration splits
make evaluate           # single held-out test pass -> evaluation/report.md + metrics.json
make backfill           # seed 1,000 verdicts + generate top-20 LLM narratives (bounded spend)
make serve              # API on http://localhost:8000 (docs at /docs)
make console-setup      # install the analyst console (Node 20+)
make console            # console on http://localhost:3000
```

### The analyst console

Three views against the live API: the **ranked queue** with the evidence
panel (signal decomposition, cross-merchant links, taint path, the
hand-drawn SVG identity-cluster graph, and the LLM narrative), the
**evaluation dossier** (every metric from the held-out run, including the
baseline comparison and the evasion table), and **ring replay** (watch a
fraud ring's scores climb 23 to 82 as it spreads across six merchants,
live). For a fresh replay, delete `sentinel.db` before `make serve`.
Design: the watchroom system, a warm-dark observatory theme with a
radar-amber accent, custom logo/favicon, three type voices, and no
template UI. Screenshots in [docs/screenshots/](docs/screenshots/).

Requires AWS credentials via the default chain (no keys in the repo, ever) for `make models` and the LLM features. Everything else runs offline.

## Documentation

The complete design suite lives in [docs/](docs/README.md): problem statement and loss model, architecture, data design, ML and evaluation protocol (including the false-positive cost model), API specification, security and DPDP/PCI alignment, and the build roadmap with verification checkpoints.

## Repository layout

```
src/sentinel/    Core package (config, ingestion, graph, scorer, API)
tests/           Unit and integration tests
scripts/         Operational scripts (model verification, hooks)
docs/            Design documents and the living what-broke log
.github/         CI: lint, strict types, coverage-gated tests, secret scanning
```

## License

MIT.
