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
| 4-8 | API, LLM layer, evaluation, console | planned (see [docs/11-roadmap.md](docs/11-roadmap.md)) |

## Quick start

```bash
make setup          # venv (Python 3.12), pinned deps, git hooks
make check          # lint + format check + mypy strict + pytest with coverage
make models         # one-shot Bedrock constrained-JSON verification (bounded spend)
```

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
