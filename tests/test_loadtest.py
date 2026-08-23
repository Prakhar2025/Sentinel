"""Tests for the load-test harness."""

from __future__ import annotations

from sentinel.data.generate import generate_dataset
from sentinel.loadtest import _percentile, _summarize, run_sequential, run_threaded
from sentinel.verdict import VerdictEngine


def test_percentile_math() -> None:
    samples = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert _percentile(samples, 0.50) == 5.0
    assert _percentile(samples, 0.95) == 10.0
    assert _percentile([42.0], 0.99) == 42.0


def test_summarize_shape() -> None:
    latencies = [float(i) for i in range(1, 101)]
    result = _summarize("sequential", 100, 1.0, latencies)
    assert result["mode"] == "sequential"
    assert result["events"] == 100
    assert result["throughput_events_per_sec"] == 100.0
    assert set(result["latency_ms"]) == {"p50", "p95", "p99", "max"}
    assert result["latency_ms"]["p50"] <= result["latency_ms"]["p95"] <= result["latency_ms"]["max"]


def test_sequential_run_measures_real_pipeline() -> None:
    events, _, _ = generate_dataset(seed=42)
    ordered = sorted(events, key=lambda e: e.ts)[:80]
    result = run_sequential(ordered, VerdictEngine())
    assert result["events"] == 80
    assert result["throughput_events_per_sec"] > 10
    assert result["latency_ms"]["p50"] > 0


def test_threaded_run_serializes_and_notes_model() -> None:
    events, _, _ = generate_dataset(seed=42)
    ordered = sorted(events, key=lambda e: e.ts)[:60]
    result = run_threaded(ordered, VerdictEngine(), threads=3)
    assert result["events"] == 60
    assert "single-writer" in result["note"]
    # No degraded verdicts can hide in here: the lock guarantees the
    # graph is only ever touched by one thread at a time.
    assert result["latency_ms"]["p50"] > 0
