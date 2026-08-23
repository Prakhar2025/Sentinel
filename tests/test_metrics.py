"""Tests for the pure metric functions (docs/05 arithmetic)."""

from __future__ import annotations

import pytest

from sentinel.metrics import (
    FN_COST_INR,
    FP_COST_INR,
    REVIEW_COST_INR,
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


def outcome(score: int, fraud: bool, ring: str | None = None, strategy: str | None = None):
    return Outcome(
        event_id=f"e{score}-{fraud}-{ring}",
        score=score,
        is_fraud=fraud,
        ring_id=ring,
        ring_strategy=strategy,
    )


def test_wilson_known_values() -> None:
    low, high = wilson_interval(8, 10)
    assert 0.44 < low < 0.50
    assert 0.94 < high < 1.0
    assert wilson_interval(0, 0) == (0.0, 0.0)
    assert wilson_interval(10, 10)[0] > 0.7


def test_precision_recall_f1_counts() -> None:
    result = precision_recall_f1(tp=15, fp=3, fn=2)
    assert result["precision"] == pytest.approx(15 / 18, abs=1e-3)
    assert result["recall"] == pytest.approx(15 / 17, abs=1e-3)
    empty = precision_recall_f1(0, 0, 0)
    assert empty == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_confusion_bands_and_counts() -> None:
    outcomes = [
        outcome(80, True, "r1"),
        outcome(45, True, "r1"),
        outcome(20, True, "r1"),
        outcome(75, False),
        outcome(45, False),
        outcome(10, False),
    ]
    table = confusion(outcomes, review_at=42, block_at=49)
    assert table == {
        "ALLOW": {"clean": 1, "fraud": 1},
        "REVIEW": {"clean": 1, "fraud": 1},
        "BLOCK_REC": {"clean": 1, "fraud": 1},
    }
    counts = counts_from_confusion(table)
    assert counts["tp"] == 1
    assert counts["fp"] == 1
    assert counts["fn"] == 2  # ALLOW + REVIEW fraud


def test_per_ring_recall_catch_rule() -> None:
    outcomes = [
        outcome(80, True, "r1"),
        outcome(80, True, "r1"),
        outcome(10, True, "r1"),
        outcome(10, True, "r1"),  # 2 of 4 flagged -> caught
        outcome(80, True, "r2"),
        outcome(10, True, "r2"),
        outcome(10, True, "r2"),  # 1 of 3 flagged -> not caught
    ]
    report = per_ring_recall(outcomes, block_at=49)
    assert report["r1"]["caught"] is True
    assert report["r1"]["event_recall"] == 0.5
    assert report["r2"]["caught"] is False


def test_fp_cost_matches_docs_05_constants() -> None:
    assert (FP_COST_INR, FN_COST_INR, REVIEW_COST_INR) == (321, 1100, 120)
    summary = fp_cost_summary(tp=15, fp=3, review_count=66, n_events=197)
    expected = (15 * 1100 - 3 * 321 - 66 * 120) * 1000 / 197
    assert summary["net_saved_inr"] == pytest.approx(expected, abs=0.5)


def test_sensitivity_table_alternatives() -> None:
    outcomes = [outcome(80, True), outcome(45, False), outcome(55, True)]
    rows = sensitivity_table(outcomes, block_at=49, deltas=(-10, 0, 10))
    assert [r["threshold"] for r in rows] == [39, 49, 59]
    assert rows[0]["tp"] >= rows[1]["tp"] >= rows[2]["tp"]


def test_calibration_deciles_buckets_unique_and_complete() -> None:
    outcomes = [outcome(i % 101, i % 7 == 0) for i in range(200)]
    table = calibration_deciles(outcomes)
    assert table
    ranges = [row["score_range"] for row in table]
    assert len(ranges) == len(set(ranges))  # no duplicated labels
    assert sum(row["events"] for row in table) == 200
    assert sum(row["fraud"] for row in table) == sum(1 for o in outcomes if o.is_fraud)


def test_calibration_deciles_never_split_a_score() -> None:
    # Heavily tied, bimodal distribution: two big score masses.
    outcomes = [outcome(40, False) for _ in range(60)] + [outcome(85, True) for _ in range(20)]
    table = calibration_deciles(outcomes)
    ranges = [row["score_range"] for row in table]
    assert len(ranges) == len(set(ranges))
    assert sum(row["events"] for row in table) == 80
