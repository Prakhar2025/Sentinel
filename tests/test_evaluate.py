"""Tests for baselines and the full evaluation run (doc 05 protocol)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sentinel.baselines import Row, evaluate_baselines
from sentinel.evaluate import run_evaluation, write_outputs
from sentinel.features import feature_vector_from_raw


def row(fraud: bool, taint: float, group: str) -> Row:
    raw = {
        "device_identity_ratio": 6.0 if fraud else 1.0,
        "cross_merchant_fanout": 6 if fraud else 1,
        "taint": taint,
        "velocity_merchants_72h": 5 if fraud else 0,
        "burn_rotate": 1 if fraud else 0,
        "amount_band_hit": 1.0 if fraud else 0.0,
        "new_identity_fraction": 1.0 if fraud else 0.0,
    }
    return Row(features=feature_vector_from_raw(raw), is_fraud=fraud, group=group)


def test_baselines_separate_easy_case() -> None:
    train = [row(True, 1.0, "r1")] * 4 + [row(False, 0.0, "c1")] * 6
    test = [row(True, 1.0, "r9")] * 2 + [row(False, 0.0, "c9")] * 4
    results = evaluate_baselines(train, test)
    for name, metrics in results.items():
        assert metrics["precision"] == 1.0, name
        assert metrics["recall"] == 1.0, name


def test_baselines_reported_side_by_side_keys() -> None:
    train = [row(True, 1.0, "r1")] * 3 + [row(False, 0.0, "c1")] * 5
    test = [row(True, 1.0, "r9")] + [row(False, 0.0, "c9")] * 3
    results = evaluate_baselines(train, test)
    assert set(results) == {"logistic_regression", "gradient_boosting"}


@pytest.fixture(scope="module")
def test_config(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A self-contained locked config.

    The real calibration (evaluation/model_config.json) is a gitignored
    local artifact; CI checks out without it, so no test may depend on
    it. Tests assert structure and mechanics against the default
    weights; the calibrated numbers come from
    `make calibrate && make evaluate` locally.
    """
    import json

    from sentinel.scorer import DEFAULT_WEIGHTS

    config_path = tmp_path_factory.mktemp("config") / "model_config.json"
    config_path.write_text(
        json.dumps(
            {
                "model_version": "rules-test",
                "weights": DEFAULT_WEIGHTS,
                "thresholds": {"review": 25, "block": 35},
            }
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.fixture(scope="module")
def evaluation(test_config: Path) -> dict:
    return run_evaluation(seed=42, config_path=test_config)


def test_evaluation_covers_doc05_spec(evaluation: dict) -> None:
    metrics = evaluation["metrics"]
    required = [
        "model_version",
        "weights",
        "thresholds",
        "event_metrics",
        "precision_ci95",
        "recall_ci95",
        "confusion",
        "ring_recall",
        "fp_cost_per_1000",
        "threshold_sensitivity",
        "calibration_deciles",
        "baselines",
        "evasion_pack",
        "champion_challenger",
    ]
    for key in required:
        assert key in metrics, f"doc 05 metric missing: {key}"
    assert len(metrics["precision_ci95"]) == 2


def test_evaluation_rings_all_accounted(evaluation: dict) -> None:
    rings = evaluation["metrics"]["ring_recall"]
    assert rings["rings_total"] >= 1
    assert rings["rings_caught"] >= 1
    assert len(rings["sophisticated"]) >= 1


def test_metrics_json_is_byte_identical_across_runs(
    tmp_path: Path, evaluation: dict, test_config: Path
) -> None:
    first_dir = tmp_path / "a"
    second_dir = tmp_path / "b"
    write_outputs(first_dir, evaluation)
    write_outputs(second_dir, run_evaluation(seed=42, config_path=test_config))
    first = (first_dir / "metrics.json").read_bytes()
    second = (second_dir / "metrics.json").read_bytes()
    assert first == second  # no timestamps or timings inside metrics.json


def test_report_renders_all_sections(tmp_path: Path, evaluation: dict) -> None:
    _metrics_path, _latency_path, report_path = write_outputs(tmp_path, evaluation)
    report = report_path.read_text(encoding="utf-8")
    for section in (
        "Event-level metrics",
        "Confusion matrix",
        "Ring-level recall",
        "False-positive cost",
        "Threshold sensitivity",
        "Baselines",
        "Adversarial evasion pack",
        "Score calibration",
        "Latency",
    ):
        assert section in report, f"report section missing: {section}"


def test_missing_locked_config_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="calibrate"):
        run_evaluation(seed=42, config_path=tmp_path / "absent.json")


def test_latency_measured(evaluation: dict) -> None:
    latency = evaluation["latency"]
    assert latency["events"] > 0
    assert 0 < latency["p50_ms"] < latency["p95_ms"] < 1000


def test_json_outputs_are_serializable(evaluation: dict) -> None:
    json.dumps(evaluation["metrics"], sort_keys=True)
    json.dumps(evaluation["latency"])
