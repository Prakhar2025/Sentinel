"""Evaluation harness (doc 05 protocol; the most judged artifact).

One deterministic run:
1. Online replay of the full dataset; every train/calibration event's
   features are cached for the baselines, every test event is scored
   exactly once with the locked model (single test pass).
2. Event metrics with Wilson CIs, 3x2 confusion, per-ring recall
   (sophisticated rings broken out), FP cost at three thresholds, and
   the score-calibration table.
3. Baselines (LR + GBDT) on identical rows and splits.
4. Adversarial evasion pack against the locked model.
5. Writes evaluation/metrics.json (byte-identical across runs; timing
   goes to a separate latency.json) and evaluation/report.md.

Requires the locked calibration (make calibrate) first; the harness
refuses to invent one.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

from .adversary import Strategy, evasion_rates, generate_evasion_events
from .baselines import Row, evaluate_baselines
from .challenger import ChallengerModel
from .data.generate import WINDOW_DAYS, WINDOW_START, generate_dataset
from .data.models import Split
from .features import extract_features
from .graph import GraphStore, entities_of
from .metrics import (
    Outcome,
    calibration_deciles,
    confusion,
    counts_from_confusion,
    fp_cost_summary,
    per_ring_recall,
    precision_recall_f1,
    sensitivity_table,
    wilson_interval,
)
from .verdict import VerdictEngine

# Evasion rings attack late in the timeline, after most dataset events.
LATE_START = WINDOW_START + timedelta(days=WINDOW_DAYS - 25)


def run_evaluation(seed: int = 42, config_path: Path | None = None) -> dict[str, Any]:
    """Full deterministic evaluation; returns the metrics dict."""
    path = config_path or Path("evaluation/model_config.json")
    if not path.exists():
        raise SystemExit(
            "locked model config missing: run `make calibrate` first "
            "(the evaluation must use the locked weights and thresholds)"
        )
    config = json.loads(path.read_text(encoding="utf-8"))
    engine = VerdictEngine(
        weights=config["weights"],
        review_threshold=config["thresholds"]["review"],
        block_threshold=config["thresholds"]["block"],
        model_version=config["model_version"],
    )
    review_at = config["thresholds"]["review"]
    block_at = config["thresholds"]["block"]

    events, labels, _summary = generate_dataset(seed=seed)
    label_by_id = {label.event_id: label for label in labels}
    ordered = sorted(events, key=lambda e: e.ts)

    store = GraphStore()
    train_rows: list[Row] = []
    test_rows: list[Row] = []
    test_outcomes: list[Outcome] = []
    latencies_ms: list[float] = []
    for event in ordered:
        store.upsert_event(event, entities_of(event))
        label = label_by_id[event.event_id]
        # Features are captured at the event's own timestamp (online): a
        # row extracted after the full replay would leak the future into
        # the baselines.
        features = extract_features(event, store)
        if features is not None:
            group = label.ring_id or f"cust:{event.customer_id}"
            row = Row(
                features=features,
                is_fraud=label.is_fraud,
                group=group,
                event_id=event.event_id,
            )
            (test_rows if label.split is Split.TEST else train_rows).append(row)
        if label.split is Split.TEST:
            started = time.perf_counter()
            verdict = engine.score_event(event, store)
            latencies_ms.append((time.perf_counter() - started) * 1000)
            test_outcomes.append(
                Outcome(
                    event_id=event.event_id,
                    score=verdict.score,
                    is_fraud=label.is_fraud,
                    ring_id=label.ring_id,
                    ring_strategy=(label.ring_strategy.value if label.ring_strategy else None),
                )
            )

    challenger = ChallengerModel.load(Path("evaluation/challenger.pkl"))
    metrics = _assemble_metrics(
        config, test_outcomes, review_at, block_at, seed, train_rows, test_rows, challenger
    )
    evasion = _run_evasion(engine, store, seed, review_at, block_at)
    metrics["evasion_pack"] = evasion
    metrics["latency_note"] = "timings in evaluation/latency.json (non-deterministic)"
    _latency = {
        "p50_ms": round(statistics.median(latencies_ms), 3),
        "p95_ms": round(sorted(latencies_ms)[int(0.95 * len(latencies_ms))], 3),
        "events": len(latencies_ms),
    }
    return {"metrics": metrics, "latency": _latency}


def _assemble_metrics(
    config: dict[str, Any],
    outcomes: list[Outcome],
    review_at: int,
    block_at: int,
    seed: int,
    train_rows: list[Row],
    test_rows: list[Row],
    challenger: ChallengerModel | None = None,
) -> dict[str, Any]:
    table = confusion(outcomes, review_at, block_at)
    counts = counts_from_confusion(table)
    event_metrics = precision_recall_f1(counts["tp"], counts["fp"], counts["fn"])
    p_low, p_high = wilson_interval(counts["tp"], counts["tp"] + counts["fp"])
    r_low, r_high = wilson_interval(counts["tp"], counts["tp"] + counts["fn"])
    rings = per_ring_recall(outcomes, block_at)
    caught = sum(1 for r in rings.values() if r["caught"])
    sophisticated = {ring: r for ring, r in rings.items() if r["strategy"] == "sophisticated"}

    return {
        "model_version": config["model_version"],
        "seed": seed,
        "weights": config["weights"],
        "thresholds": config["thresholds"],
        "test_events": len(outcomes),
        "test_fraud_events": sum(1 for o in outcomes if o.is_fraud),
        "event_metrics": event_metrics,
        "precision_ci95": [p_low, p_high],
        "recall_ci95": [r_low, r_high],
        "confusion": table,
        "review_abstentions": {
            "fraud": counts["review_fraud"],
            "clean": counts["review_clean"],
        },
        "ring_recall": {
            "rings_total": len(rings),
            "rings_caught": caught,
            "per_ring": rings,
            "sophisticated": sophisticated,
            "missed_rings": [ring for ring, r in rings.items() if not r["caught"]],
        },
        "fp_cost_per_1000": fp_cost_summary(
            counts["tp"],
            counts["fp"],
            counts["review_fraud"] + counts["review_clean"],
            n_events=len(outcomes),
        ),
        "threshold_sensitivity": sensitivity_table(outcomes, block_at),
        "calibration_deciles": calibration_deciles(outcomes),
        "baselines": evaluate_baselines(train_rows, test_rows),
        "champion_challenger": _shadow_agreement(outcomes, test_rows, block_at, challenger),
        "design_point_on_test": bool(
            event_metrics["precision"] >= 0.80 and event_metrics["recall"] >= 0.70
        ),
    }


def _shadow_agreement(
    outcomes: list[Outcome],
    test_rows: list[Row],
    block_at: int,
    challenger: ChallengerModel | None,
) -> dict[str, Any]:
    """Champion vs shadow-challenger agreement on the held-out set.

    The challenger never decides; this block is the promotion evidence
    (criteria in docs/14), not a leaderboard.
    """
    if challenger is None:
        return {
            "active": False,
            "note": "no challenger artifact; run `make challenger` to enable shadow mode",
        }
    by_event = {row.event_id: row for row in test_rows if row.event_id}
    both = champ_only = chall_only = total = 0
    for outcome in outcomes:
        row = by_event.get(outcome.event_id)
        if row is None:
            continue
        total += 1
        champ_flag = outcome.score >= block_at
        chall_flag = bool(challenger.predict(row.features)["flag"])
        if champ_flag and chall_flag:
            both += 1
        elif champ_flag:
            champ_only += 1
        elif chall_flag:
            chall_only += 1
    return {
        "active": True,
        "version": challenger.version,
        "events": total,
        "both_flag": both,
        "champion_only": champ_only,
        "challenger_only": chall_only,
        "neither": total - both - champ_only - chall_only,
        "agreement_rate": round((total - champ_only - chall_only) / total, 4) if total else 0.0,
        "note": "shadow opinion only; promotion criteria in docs/14",
    }


def _run_evasion(
    engine: VerdictEngine, store: GraphStore, seed: int, review_at: int, block_at: int
) -> dict[str, Any]:
    """Attack the locked model with the evasion pack on the live graph."""
    evasion_events = generate_evasion_events(seed=seed, start=LATE_START)
    scored: list[tuple[Any, Strategy, int]] = []
    for event, _strategy in sorted(evasion_events, key=lambda pair: pair[0].ts):
        store.upsert_event(event, entities_of(event))
        verdict = engine.score_event(event, store)
        scored.append((event, _strategy, verdict.score))
    return {
        "note": "adversarial rings are evaluation-only; never used for calibration",
        "strategies": evasion_rates(scored, review_at, block_at),
    }


def write_outputs(out_dir: Path, result: dict[str, Any]) -> tuple[Path, Path, Path]:
    """Write metrics.json (deterministic), latency.json, report.md."""
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "metrics.json"
    latency_path = out_dir / "latency.json"
    report_path = out_dir / "report.md"

    metrics_path.write_text(
        json.dumps(result["metrics"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    latency_path.write_text(
        json.dumps(result["latency"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report_path.write_text(_render_report(result["metrics"], result["latency"]), encoding="utf-8")
    return metrics_path, latency_path, report_path


def _render_report(metrics: dict[str, Any], latency: dict[str, Any]) -> str:
    """Human-readable report covering every doc 05 metric-spec item."""
    event = metrics["event_metrics"]
    cost = metrics["fp_cost_per_1000"]
    rings = metrics["ring_recall"]
    cc = metrics.get("champion_challenger", {"active": False, "note": ""})
    lines = [
        "# Abuse-Ring Sentinel, Evaluation Report",
        "",
        f"Model `{metrics['model_version']}` on seed {metrics['seed']} with locked "
        f"thresholds review={metrics['thresholds']['review']}, "
        f"block={metrics['thresholds']['block']}. Single pass over the held-out "
        "test split; ring-stratified so no identity spans splits.",
        "",
        "## Event-level metrics (positive = BLOCK_REC)",
        "",
        f"- Precision **{event['precision']:.3f}** (95% CI {metrics['precision_ci95']})",
        f"- Recall **{event['recall']:.3f}** (95% CI {metrics['recall_ci95']})",
        f"- F1 **{event['f1']:.3f}**",
        f"- Design point (P>=0.80 at R>=0.70): "
        f"**{'HIT' if metrics['design_point_on_test'] else 'MISSED'}**",
        f"- Test set: {metrics['test_events']} events, {metrics['test_fraud_events']} fraud",
        f"- REVIEW abstentions: {metrics['review_abstentions']['fraud']} fraud, "
        f"{metrics['review_abstentions']['clean']} clean",
        "",
        "## Confusion matrix",
        "",
        "| Band | clean | fraud |",
        "|------|-------|-------|",
    ]
    for band in ("ALLOW", "REVIEW", "BLOCK_REC"):
        row = metrics["confusion"][band]
        lines.append(f"| {band} | {row['clean']} | {row['fraud']} |")
    lines += [
        "",
        "## Ring-level recall",
        "",
        f"Caught **{rings['rings_caught']} of {rings['rings_total']}** rings "
        "(caught = at least half the ring's events in BLOCK_REC).",
        "",
        "| Ring | Strategy | Events | Flagged | Event recall | Caught |",
        "|------|----------|--------|---------|--------------|--------|",
    ]
    for ring, r in rings["per_ring"].items():
        lines.append(
            f"| {ring} | {r['strategy']} | {r['events']} | {r['flagged']} | "
            f"{r['event_recall']:.2f} | {'yes' if r['caught'] else 'NO'} |"
        )
    if rings["missed_rings"]:
        lines += [
            "",
            f"**Missed rings (named, per the honesty protocol):** "
            f"{', '.join(rings['missed_rings'])}",
        ]
    lines += [
        "",
        "## False-positive cost (per 1,000 events)",
        "",
        "| Gross saved | FP cost | Review cost | Net |",
        "|------------|---------|-------------|-----|",
        f"| Rs.{cost['gross_saved_inr']:,.0f} | -Rs.{cost['fp_cost_inr']:,.0f} | "
        f"-Rs.{cost['review_cost_inr']:,.0f} | **Rs.{cost['net_saved_inr']:,.0f}** |",
        "",
        "Constants: FP Rs.321, FN Rs.1,100, review Rs.120 (docs/05, named and sourced).",
        "",
        "### Threshold sensitivity",
        "",
        "| Threshold | TP | FP | FN | Precision | Recall | F1 |",
        "|-----------|----|----|----|-----------|--------|----|",
    ]
    for row in metrics["threshold_sensitivity"]:
        lines.append(
            f"| {row['threshold']} | {row['tp']} | {row['fp']} | {row['fn']} | "
            f"{row['precision']:.3f} | {row['recall']:.3f} | {row['f1']:.3f} |"
        )
    lines += [
        "",
        "## Baselines (same features, same splits)",
        "",
        "| Model | Precision | Recall | F1 |",
        "|-------|-----------|--------|----|",
        "| rule ensemble (ours) | "
        f"{event['precision']:.3f} | {event['recall']:.3f} | {event['f1']:.3f} |",
    ]
    for name, result in metrics["baselines"].items():
        lines.append(
            f"| {name} | {result['precision']:.3f} | {result['recall']:.3f} | {result['f1']:.3f} |"
        )
    lines += [
        "",
        "## Champion/challenger (shadow)",
        "",
        f"Challenger active: **{cc['active']}**"
        + (
            f" ({cc['version']}, agreement {cc['agreement_rate']:.1%} on {cc['events']} events; "
            f"champion-only flags {cc['champion_only']}, challenger-only {cc['challenger_only']})"
            if cc["active"]
            else f" ({cc['note']})"
        )
        + ". The challenger records opinions and never decides; promotion criteria in docs/14.",
        "",
        "## Adversarial evasion pack",
        "",
        metrics["evasion_pack"]["note"],
        "",
        "| Strategy | Events | Missed entirely | Not blocked |",
        "|----------|--------|-----------------|-------------|",
    ]
    for strategy, r in metrics["evasion_pack"]["strategies"].items():
        lines.append(
            f"| {strategy} | {r['events']} | {r['missed_entirely']} "
            f"({r['missed_entirely_rate']:.0%}) | {r['not_blocked']} "
            f"({r['not_blocked_rate']:.0%}) |"
        )
    lines += [
        "",
        "## Score calibration (fraud rate by decile)",
        "",
        "| Score range | Events | Fraud | Rate |",
        "|-------------|--------|-------|------|",
    ]
    for row in metrics["calibration_deciles"]:
        lines.append(
            f"| {row['score_range']} | {row['events']} | {row['fraud']} | {row['fraud_rate']:.2f} |"
        )
    lines += [
        "",
        "## Latency (informational, non-deterministic)",
        "",
        f"Scoring p50 {latency['p50_ms']} ms / p95 {latency['p95_ms']} ms over "
        f"{latency['events']} test events (design target: < 20 ms).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m sentinel.evaluate [--seed 42] [--out evaluation]."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("evaluation"))
    args = parser.parse_args(argv)

    result = run_evaluation(seed=args.seed)
    metrics_path, latency_path, report_path = write_outputs(args.out, result)
    print(f"wrote {metrics_path}, {latency_path}, {report_path}")
    event = result["metrics"]["event_metrics"]
    print(
        f"test: precision {event['precision']}, recall {event['recall']}, "
        f"f1 {event['f1']}; design point "
        f"{'HIT' if result['metrics']['design_point_on_test'] else 'MISSED'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
