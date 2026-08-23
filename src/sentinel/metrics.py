"""Pure metric functions (docs/05 metrics specification).

Everything here is deterministic arithmetic: no I/O, no randomness, so
every number in the report is reproducible and unit-testable. The FP
cost constants mirror docs/05 exactly; changing a constant means
changing the doc, and vice versa.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Z_95 = 1.96

# Cost model constants (docs/05, named and sourced there).
FP_COST_INR = 321
FN_COST_INR = 1_100
REVIEW_COST_INR = 120


@dataclass(slots=True, frozen=True)
class Outcome:
    """One scored test event."""

    event_id: str
    score: int
    is_fraud: bool
    ring_id: str | None = None
    ring_strategy: str | None = None


def wilson_interval(successes: int, total: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = (z / denominator) * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))


def precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float]:
    """Point estimates from confusion counts."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def confusion(outcomes: list[Outcome], review_at: int, block_at: int) -> dict[str, dict[str, int]]:
    """3x2 confusion table: verdict band x ground truth (doc 05)."""
    table = {
        "ALLOW": {"clean": 0, "fraud": 0},
        "REVIEW": {"clean": 0, "fraud": 0},
        "BLOCK_REC": {"clean": 0, "fraud": 0},
    }
    for outcome in outcomes:
        band = (
            "ALLOW"
            if outcome.score < review_at
            else ("REVIEW" if outcome.score < block_at else "BLOCK_REC")
        )
        table[band]["fraud" if outcome.is_fraud else "clean"] += 1
    return table


def counts_from_confusion(table: dict[str, dict[str, int]]) -> dict[str, int]:
    """TP/FP/FN/REVIEW counts with positive = BLOCK_REC (doc 05)."""
    return {
        "tp": table["BLOCK_REC"]["fraud"],
        "fp": table["BLOCK_REC"]["clean"],
        "fn": table["ALLOW"]["fraud"] + table["REVIEW"]["fraud"],
        "review_fraud": table["REVIEW"]["fraud"],
        "review_clean": table["REVIEW"]["clean"],
    }


def per_ring_recall(
    outcomes: list[Outcome], block_at: int
) -> dict[str, dict[str, float | int | str]]:
    """Recall per fraud ring; a ring is 'caught' when at least half its
    events land in BLOCK_REC (doc 05: ring-level recall matters more
    than event-level)."""
    by_ring: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        if outcome.is_fraud and outcome.ring_id:
            by_ring.setdefault(outcome.ring_id, []).append(outcome)
    report: dict[str, dict[str, float | int | str]] = {}
    for ring_id, ring_outcomes in sorted(by_ring.items()):
        flagged = sum(1 for o in ring_outcomes if o.score >= block_at)
        strategy = ring_outcomes[0].ring_strategy or "standard"
        report[ring_id] = {
            "events": len(ring_outcomes),
            "flagged": flagged,
            "event_recall": round(flagged / len(ring_outcomes), 4),
            "caught": flagged * 2 >= len(ring_outcomes),
            "strategy": strategy,
        }
    return report


def fp_cost_summary(
    tp: int, fp: int, review_count: int, per_1000: int = 1000, n_events: int = 0
) -> dict[str, float]:
    """Net savings in INR (docs/05 formula), scaled per 1,000 events."""
    savings = tp * FN_COST_INR - fp * FP_COST_INR - review_count * REVIEW_COST_INR
    scale = per_1000 / n_events if n_events else 1.0
    return {
        "gross_saved_inr": round(tp * FN_COST_INR * scale, 2),
        "fp_cost_inr": round(fp * FP_COST_INR * scale, 2),
        "review_cost_inr": round(review_count * REVIEW_COST_INR * scale, 2),
        "net_saved_inr": round(savings * scale, 2),
    }


def calibration_deciles(outcomes: list[Outcome]) -> list[dict[str, float | int | str]]:
    """Fraud rate by score decile (reliability table)."""
    if not outcomes:
        return []
    scored = sorted(outcomes, key=lambda o: o.score)
    buckets: list[dict[str, float | int | str]] = []
    bucket_size = max(1, len(scored) // 10)
    for index in range(0, len(scored), bucket_size):
        chunk = scored[index : index + bucket_size]
        fraud = sum(1 for o in chunk if o.is_fraud)
        buckets.append(
            {
                "score_range": f"{chunk[0].score}-{chunk[-1].score}",
                "events": len(chunk),
                "fraud": fraud,
                "fraud_rate": round(fraud / len(chunk), 4),
            }
        )
    return buckets


def sensitivity_table(
    outcomes: list[Outcome], block_at: int, deltas: tuple[int, ...] = (-10, 0, 10)
) -> list[dict[str, float | int]]:
    """Operating-point tradeoff at alternative thresholds (doc 05)."""
    rows: list[dict[str, float | int]] = []
    for delta in deltas:
        threshold = block_at + delta
        tp = sum(1 for o in outcomes if o.score >= threshold and o.is_fraud)
        fp = sum(1 for o in outcomes if o.score >= threshold and not o.is_fraud)
        fn = sum(1 for o in outcomes if o.score < threshold and o.is_fraud)
        metrics = precision_recall_f1(tp, fp, fn)
        rows.append(
            {
                "threshold": threshold,
                "tp": tp,
                "fp": fp,
                "fn": fn,
                **metrics,
            }
        )
    return rows


__all__ = [
    "FN_COST_INR",
    "FP_COST_INR",
    "REVIEW_COST_INR",
    "Outcome",
    "calibration_deciles",
    "confusion",
    "counts_from_confusion",
    "fp_cost_summary",
    "per_ring_recall",
    "precision_recall_f1",
    "sensitivity_table",
    "wilson_interval",
]
