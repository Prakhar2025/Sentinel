"""Tests for calibration machinery (fast units + one slow integration)."""

from __future__ import annotations

import pytest

from sentinel.calibrate import (
    REVIEW_PRECISION_FLOOR,
    WEIGHT_CAPS,
    ScoredRow,
    _f1_at,
    _renormalize,
    calibrate,
    coordinate_ascent,
    lock_thresholds,
)
from sentinel.features import feature_vector_from_raw
from sentinel.scorer import DEFAULT_WEIGHTS, FEATURE_NAMES


def row(fraud: bool, taint: float, group: str) -> ScoredRow:
    raw = {
        "device_identity_ratio": 6.0 if fraud else 1.0,
        "cross_merchant_fanout": 6 if fraud else 1,
        "taint": taint,
        "velocity_merchants_72h": 5 if fraud else 0,
        "burn_rotate": 1 if fraud else 0,
        "amount_band_hit": 1.0 if fraud else 0.0,
        "new_identity_fraction": 1.0 if fraud else 0.0,
    }
    return ScoredRow(features=feature_vector_from_raw(raw), is_fraud=fraud, group=group)


def test_f1_at_perfect_separation() -> None:
    rows = [row(True, 1.0, "r1")] * 3 + [row(False, 0.0, "c1")] * 3
    precision, recall, f1 = _f1_at(rows, DEFAULT_WEIGHTS, threshold=50)
    assert (precision, recall, f1) == (1.0, 1.0, 1.0)


def test_f1_at_counts_errors() -> None:
    taint_only = {name: 0 for name in FEATURE_NAMES}
    taint_only["taint_propagation"] = 100
    rows = [row(True, 1.0, "r1"), row(False, 0.6, "c1"), row(False, 0.0, "c2")]
    precision, recall, _ = _f1_at(rows, taint_only, threshold=50)
    assert precision == 0.5  # the 0.6-taint clean row is a false positive
    assert recall == 1.0


def test_renormalize_sums_to_100() -> None:
    scaled = _renormalize({name: 7 for name in FEATURE_NAMES})
    assert sum(scaled.values()) == 100
    assert all(value >= 0 for value in scaled.values())


def test_coordinate_ascent_respects_caps() -> None:
    rows = [row(True, 1.0, "r1"), row(True, 1.0, "r2"), row(False, 0.0, "c1")]
    weights, _cv = coordinate_ascent(rows)
    assert sum(weights.values()) == 100
    assert weights["amount_pattern"] <= WEIGHT_CAPS["amount_pattern"]


def test_lock_thresholds_design_point_on_clean_separation() -> None:
    rows = [row(True, 1.0, "r1")] * 10 + [row(False, 0.0, "c1")] * 10
    thresholds, metrics = lock_thresholds(rows, DEFAULT_WEIGHTS)
    assert metrics["design_point_hit"] is True
    assert thresholds["review"] <= thresholds["block"]
    assert metrics["calibration_precision"] == 1.0
    assert metrics["calibration_recall"] == 1.0


def test_review_floor_constant_is_published() -> None:
    assert 0 < REVIEW_PRECISION_FLOOR < 1


@pytest.mark.slow
def test_full_calibration_hits_design_point() -> None:
    """The phase checkpoint: P >= 0.80 at R >= 0.70 on the calibration split.

    Runs the full deterministic pipeline (~100 s): online replay, ring-
    grouped CV ascent, threshold lock. Excluded from fast CI; the design
    point is the Phase 6 evaluate gate's job to enforce on every run.
    """
    config = calibrate(seed=42)
    assert config["design_point_hit"] is True
    assert config["calibration_precision"] >= 0.80
    assert config["calibration_recall"] >= 0.70
    weights = config["weights"]
    assert sum(weights.values()) == 100
    assert weights["amount_pattern"] <= WEIGHT_CAPS["amount_pattern"]
    thresholds = config["thresholds"]
    assert 0 < thresholds["review"] <= thresholds["block"] <= 100
