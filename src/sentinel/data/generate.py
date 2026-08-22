"""Dataset orchestration and CLI.

Produces the evaluation dataset per docs/04:
- events.jsonl  : serving-shaped events (schema of the API input, no labels)
- labels.jsonl  : event_id -> is_fraud, ring_id, ring_strategy, split
- summary.json  : counts, split proportions, distribution statistics, hashes

Deterministic: the same seed yields byte-identical artifacts. The command
validates its own invariants (exact fraud count, split proportions within
tolerance, zero identity leakage) and exits non-zero if any fails.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from .clean import IST_OFFSET, CleanGenerator
from .entities import EntityFactory
from .models import EventLabel, PaymentEvent, RingStrategy
from .rings import RingResult, RingSpec, generate_ring, sample_specs
from .splits import assert_no_identity_leakage, assign_splits

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 42
DEFAULT_CLEAN = 900
DEFAULT_FRAUD = 100
DEFAULT_N_RINGS = 10
MERCHANT_POOL_SIZE = 45
WINDOW_START = datetime(2026, 6, 1, 0, 0, 0) + IST_OFFSET
WINDOW_DAYS = 85
SPLIT_TOLERANCE = 0.10  # absolute share tolerance for the invariant check

# Deterministic UUID namespace for event ids (uuid5 keeps runs reproducible).
EVENT_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # ns:URL


def generate_dataset(
    seed: int = DEFAULT_SEED,
    n_clean: int = DEFAULT_CLEAN,
    n_fraud: int = DEFAULT_FRAUD,
    n_rings: int = DEFAULT_N_RINGS,
) -> tuple[list[PaymentEvent], list[EventLabel], dict[str, Any]]:
    """Generate events, labels, and a summary dict. Pure and deterministic."""
    str_rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    factory = EntityFactory(random.Random(seed * 1_000_003 + 7))
    merchants = factory.merchant_pool(MERCHANT_POOL_SIZE)

    clean = CleanGenerator(
        factory=factory,
        str_rng=str_rng,
        np_rng=np_rng,
        merchants=merchants,
        start=WINDOW_START,
        days=WINDOW_DAYS,
    )
    clean_events = clean.generate(n_clean)

    ring_results: list[RingResult] = []
    specs = sample_specs(random.Random(seed * 1_000_033 + 11), n_rings, n_fraud)
    for spec in specs:
        window_start = WINDOW_START + timedelta(
            days=random.Random(seed * 10_007 + len(ring_results)).randint(
                0, max(0, WINDOW_DAYS - spec.window.days - 1)
            )
        )
        ring_results.append(
            generate_ring(
                spec,
                factory,
                random.Random(seed + 977 * len(ring_results)),
                merchants,
                window_start,
            )
        )

    # Chronological order, stable for equal timestamps (clean before fraud
    # by generation order), then deterministic event ids.
    ring_events = [event for result in ring_results for event in result.events]
    all_events = sorted(clean_events + ring_events, key=lambda e: e.ts)
    for index, event in enumerate(all_events):
        event.event_id = str(uuid.uuid5(EVENT_NAMESPACE, f"sentinel/{seed}/{index}"))
    fraud_event_ids = {event.event_id for event in ring_events}

    splits = assign_splits(all_events, fraud_event_ids)
    assert_no_identity_leakage(all_events, splits)

    ring_by_event_id: dict[str, RingSpec] = {
        event.event_id: result.spec for result in ring_results for event in result.events
    }
    labels: list[EventLabel] = []
    for event, split in zip(all_events, splits, strict=True):
        if event.event_id in fraud_event_ids:
            spec = ring_by_event_id[event.event_id]
            labels.append(
                EventLabel(
                    event_id=event.event_id,
                    is_fraud=True,
                    ring_id=spec.ring_id,
                    ring_strategy=spec.strategy,
                    split=split,
                )
            )
        else:
            labels.append(EventLabel(event_id=event.event_id, is_fraud=False, split=split))

    summary = _summary(all_events, labels, ring_results, seed)
    return all_events, labels, summary


def _summary(
    events: list[PaymentEvent],
    labels: list[EventLabel],
    ring_results: list[RingResult],
    seed: int,
) -> dict[str, Any]:
    n = len(events)
    fraud = [label for label in labels if label.is_fraud]
    split_counts: dict[str, dict[str, int]] = {}
    for label in labels:
        bucket = split_counts.setdefault(label.split.value, {"clean": 0, "fraud": 0})
        bucket["fraud" if label.is_fraud else "clean"] += 1
    merchant_counts: dict[str, int] = {}
    for event in events:
        merchant_counts[event.merchant_id] = merchant_counts.get(event.merchant_id, 0) + 1
    top_share = max(merchant_counts.values()) / n if merchant_counts else 0.0
    clean_amounts = sorted(
        event.amount_paise
        for event, label in zip(events, labels, strict=True)
        if not label.is_fraud
    )
    median_clean = clean_amounts[len(clean_amounts) // 2] if clean_amounts else 0
    fraud_ids = {label.event_id for label in labels if label.is_fraud}
    fraud_with_outcome = sum(
        1 for event in events if event.event_id in fraud_ids and event.prior_outcome is not None
    )
    strategies = {
        RingStrategy.STANDARD.value: 0,
        RingStrategy.SOPHISTICATED.value: 0,
    }
    for result in ring_results:
        strategies[result.spec.strategy.value] += 1
    return {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "total_events": n,
        "fraud_events": len(fraud),
        "clean_events": n - len(fraud),
        "rings": len(ring_results),
        "ring_strategies": strategies,
        "splits": split_counts,
        "top_merchant_share": round(top_share, 4),
        "median_clean_amount_paise": median_clean,
        "fraud_outcome_share": round(fraud_with_outcome / max(len(fraud), 1), 4),
    }


def validate(summary: dict[str, Any]) -> list[str]:
    """Return a list of invariant violations (empty means healthy)."""
    problems: list[str] = []
    if summary["fraud_events"] != DEFAULT_FRAUD:
        problems.append(
            f"expected exactly {DEFAULT_FRAUD} fraud events, got {summary['fraud_events']}"
        )
    if summary["total_events"] != DEFAULT_CLEAN + DEFAULT_FRAUD:
        problems.append(
            f"expected {DEFAULT_CLEAN + DEFAULT_FRAUD} total events, got {summary['total_events']}"
        )
    for split, share in (("train", 0.6), ("calibration", 0.2), ("test", 0.2)):
        actual = (
            summary["splits"].get(split, {}).get("clean", 0)
            + summary["splits"].get(split, {}).get("fraud", 0)
        ) / max(summary["total_events"], 1)
        if abs(actual - share) > SPLIT_TOLERANCE:
            problems.append(
                f"split {split} share {actual:.2f} outside {share:.2f} +/- {SPLIT_TOLERANCE}"
            )
    if summary["ring_strategies"][RingStrategy.SOPHISTICATED.value] < 1:
        problems.append("no sophisticated ring injected")
    for split in ("calibration", "test"):
        fraud_in_split = summary["splits"].get(split, {}).get("fraud", 0)
        if fraud_in_split < 8:  # at least one whole ring
            problems.append(
                f"split {split} has only {fraud_in_split} fraud events; "
                "calibration and test each need at least one ring"
            )
    return problems


def write_artifacts(
    out_dir: Path, events: list[PaymentEvent], labels: list[EventLabel], summary: dict[str, Any]
) -> dict[str, str]:
    """Write the three artifacts and return their sha256 digests."""
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "events.jsonl"
    labels_path = out_dir / "labels.jsonl"
    summary_path = out_dir / "summary.json"

    events_path.write_text(
        "\n".join(event.model_dump_json() for event in events) + "\n", encoding="utf-8"
    )
    labels_path.write_text(
        "\n".join(label.model_dump_json() for label in labels) + "\n", encoding="utf-8"
    )
    digests = {
        "events.jsonl": _sha256(events_path),
        "labels.jsonl": _sha256(labels_path),
    }
    summary["artifacts_sha256"] = digests
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return digests


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    """CLI entry: generate, validate, write, report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=Path("data/generated"))
    parser.add_argument("--clean", type=int, default=DEFAULT_CLEAN)
    parser.add_argument("--fraud", type=int, default=DEFAULT_FRAUD)
    args = parser.parse_args(argv)

    events, labels, summary = generate_dataset(
        seed=args.seed, n_clean=args.clean, n_fraud=args.fraud
    )
    problems = validate(summary)
    digests = write_artifacts(args.out, events, labels, summary)

    print(json.dumps(summary, indent=2))
    if problems:
        for problem in problems:
            print(f"INVARIANT VIOLATION: {problem}")
        return 1
    print(f"wrote {args.out}/events.jsonl ({digests['events.jsonl'][:12]}...) and labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
