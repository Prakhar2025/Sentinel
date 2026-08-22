"""Weight calibration and threshold locking (docs/05 honesty protocol).

Order of operations, non-negotiable:
1. Features are extracted by replaying ALL events chronologically and
   scoring each train/calibration event against the graph state at its
   own timestamp (online; only the past is visible, so no leakage).
2. Weights are fitted on the TRAIN split only, by coordinate ascent
   maximizing F1 under 5-fold ring-grouped cross-validation (folds by
   ring for fraud events, by customer for clean events).
3. Thresholds are locked on the CALIBRATION split only, targeting the
   design point precision >= 0.80 at recall >= 0.70.
4. The test split is never touched here; it is consumed once by the
   evaluation harness.

Result: evaluation/model_config.json with weights, thresholds, and
metadata. Deterministic: same seed, same config.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

from sklearn.model_selection import GroupKFold

from .data.generate import generate_dataset
from .data.models import Split
from .features import FeatureVector, extract_features
from .graph import GraphStore, entities_of
from .scorer import DEFAULT_WEIGHTS, FEATURE_NAMES, score_features

DESIGN_PRECISION = 0.80
DESIGN_RECALL = 0.70
WEIGHT_STEPS = (-15, -10, -5, 5, 10, 15)
ASCENT_PASSES = 3

# Feature priors (docs/05): amount_pattern is a deliberately minor signal
# so the detector never punishes normal merchants for typical pricing.
# The first unconstrained ascent run inflated it to 32 by exploiting the
# synthetic amount distribution; the cap is a published design constraint,
# not post-hoc tuning.
WEIGHT_CAPS = {"amount_pattern": 10}

# Minimum queue precision for the REVIEW abstention band.
REVIEW_PRECISION_FLOOR = 0.25


@dataclass(slots=True)
class ScoredRow:
    """One event's cached features and label (weights never change these)."""

    features: FeatureVector
    is_fraud: bool
    group: str


def extract_rows(split: Split, seed: int) -> tuple[list[ScoredRow], list[ScoredRow]]:
    """Online-replay feature extraction for train and calibration splits."""
    events, labels, _ = generate_dataset(seed=seed)
    label_by_id = {label.event_id: label for label in labels}
    ordered = sorted(events, key=lambda e: e.ts)

    store = GraphStore()
    rows: dict[Split, list[ScoredRow]] = {Split.TRAIN: [], Split.CALIBRATION: [], Split.TEST: []}
    for event in ordered:
        store.upsert_event(event, entities_of(event))
        label = label_by_id[event.event_id]
        if label.split is Split.TEST:
            continue  # never even cached for calibration
        features = extract_features(event, store)
        if features is None:
            continue
        group = label.ring_id or f"cust:{event.customer_id}"
        rows[label.split].append(ScoredRow(features=features, is_fraud=label.is_fraud, group=group))
    return rows[Split.TRAIN], rows[Split.CALIBRATION]


def _f1_at(
    rows: list[ScoredRow], weights: dict[str, int], threshold: float
) -> tuple[float, float, float]:
    """Precision, recall, F1 for a fixed threshold."""
    tp = fp = fn = 0
    for row in rows:
        score = score_features(row.features, weights).score
        predicted = score >= threshold
        if predicted and row.is_fraud:
            tp += 1
        elif predicted and not row.is_fraud:
            fp += 1
        elif not predicted and row.is_fraud:
            fn += 1
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def _best_threshold(rows: list[ScoredRow], weights: dict[str, int]) -> float:
    """Threshold maximizing F1 on the given rows."""
    candidates = sorted({score_features(r.features, weights).score for r in rows})
    best_t, best_f1 = 0.0, -1.0
    for threshold in candidates:
        f1 = _f1_at(rows, weights, threshold)[2]
        if f1 > best_f1:
            best_t, best_f1 = float(threshold), f1
    return best_t


def _renormalize(weights: dict[str, int]) -> dict[str, int]:
    """Scale weights back to a sum of 100, keeping proportions."""
    total = sum(weights.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    scaled = {name: round(value * 100 / total) for name, value in weights.items()}
    drift = 100 - sum(scaled.values())
    if drift:
        largest = max(scaled, key=lambda name: scaled[name])
        scaled[largest] += drift
    return scaled


def cv_f1(rows: list[ScoredRow], weights: dict[str, int], folds: int = 5) -> float:
    """Ring-grouped cross-validated F1 (threshold fitted inside each fold)."""
    if len(rows) < folds:
        return _f1_at(rows, weights, _best_threshold(rows, weights))[2]
    groups = [row.group for row in rows]
    splitter = GroupKFold(n_splits=folds)
    scores: list[float] = []
    for train_idx, holdout_idx in splitter.split(rows, groups=groups):
        train_rows = [rows[i] for i in train_idx]
        holdout_rows = [rows[i] for i in holdout_idx]
        if not any(r.is_fraud for r in train_rows) or not any(r.is_fraud for r in holdout_rows):
            continue
        threshold = _best_threshold(train_rows, weights)
        scores.append(_f1_at(holdout_rows, weights, threshold)[2])
    return sum(scores) / len(scores) if scores else 0.0


def coordinate_ascent(rows: list[ScoredRow]) -> tuple[dict[str, int], float]:
    """Fit weights on the train split; deterministic greedy coordinate ascent."""
    weights = dict(DEFAULT_WEIGHTS)
    best = cv_f1(rows, weights)
    for _ in range(ASCENT_PASSES):
        improved = False
        for name in FEATURE_NAMES:
            for step in WEIGHT_STEPS:
                candidate = dict(weights)
                candidate[name] = max(0, candidate[name] + step)
                if candidate[name] > WEIGHT_CAPS.get(name, 100):
                    continue
                candidate = _renormalize(candidate)
                value = cv_f1(rows, candidate)
                if value > best + 1e-9:
                    weights, best, improved = candidate, value, True
        if not improved:
            break
    return weights, best


def lock_thresholds(
    rows: list[ScoredRow], weights: dict[str, int]
) -> tuple[dict[str, int], dict[str, float]]:
    """Choose review/block thresholds on the calibration split.

    Block threshold: smallest score where precision >= 0.80 and
    recall >= 0.70; if unreachable, the F1-optimal threshold (disclosed).
    Review threshold: smallest score where queue precision reaches
    REVIEW_PRECISION_FLOOR (at least one in four queued events is
    fraud - a defensible analyst triage bar). The first run's
    "90% of max F1" rule collapsed review onto block because the score
    distribution is strongly bimodal; the floor keeps a real abstention
    band without dragging in the bulk clean mass.
    """
    candidates = sorted({score_features(r.features, weights).score for r in rows})
    block_at = None
    for threshold in candidates:
        precision, recall, _ = _f1_at(rows, weights, float(threshold))
        if precision >= DESIGN_PRECISION and recall >= DESIGN_RECALL:
            block_at = int(threshold)
            break
    design_point_hit = block_at is not None
    if block_at is None:
        block_at = round(_best_threshold(rows, weights))

    review_at = block_at
    for threshold in candidates:
        if _f1_at(rows, weights, float(threshold))[0] >= REVIEW_PRECISION_FLOOR:
            review_at = int(threshold)
            break
    review_at = min(review_at, block_at)

    precision, recall, f1 = _f1_at(rows, weights, float(block_at))
    metrics = {
        "calibration_precision": precision,
        "calibration_recall": recall,
        "calibration_f1": f1,
        "design_point_hit": design_point_hit,
    }
    return {"review": review_at, "block": block_at}, metrics


def calibrate(seed: int = 42) -> dict[str, object]:
    """Full calibration run: weights (train) then thresholds (calibration)."""
    started = time.perf_counter()
    train_rows, calibration_rows = extract_rows(Split.TRAIN, seed)
    weights, cv_score = coordinate_ascent(train_rows)
    thresholds, metrics = lock_thresholds(calibration_rows, weights)
    return {
        "model_version": "rules-v1.1",
        "seed": seed,
        "weights": weights,
        "thresholds": thresholds,
        "cv_f1_train": round(cv_score, 4),
        "train_events": len(train_rows),
        "calibration_events": len(calibration_rows),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        **{k: round(v, 4) if isinstance(v, float) else v for k, v in metrics.items()},
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m sentinel.calibrate [--seed 42] [--out evaluation]."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=Path("evaluation"))
    args = parser.parse_args(argv)

    config = calibrate(seed=args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "model_config.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(config, indent=2))
    if not config["design_point_hit"]:
        print(
            "NOTE: design point (P>=0.80 at R>=0.70) not reached on calibration; "
            "F1-optimal threshold locked instead. Disclosed in the report."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
