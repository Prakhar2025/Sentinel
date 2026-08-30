"""Load test: measured throughput and latency of the verdict pipeline.

Feeds the seed-42 dataset through the real serving path (normalize ->
graph upsert -> features -> score -> verdict) and reports events/sec,
p50/p95/p99 latency, and where the pipeline spends its time. Numbers
from this script feed the productionization RFC's capacity plan
(docs/14 by the end of the v2 branch).

Honesty notes, stated up front:
- Python's GIL caps CPU-bound scoring at roughly one core per process;
  the thread-mode result measures contention behavior, not scale-out.
- The production answer to that ceiling is process/worker sharding
  (documented in the RFC), not pretending threads fix it.
- Ingest order is chronological, exactly like serving, so graph growth
  cost is included in the measurements.

Usage: python -m sentinel.loadtest [--events 1000] [--threads 1 4]
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .data.generate import generate_dataset
from .graph import GraphStore, entities_of
from .verdict import VerdictEngine

SAMPLE_BURN_IN = 50


def _percentile(samples: list[float], fraction: float) -> float:
    """Nearest-rank percentile (ceil convention), the standard used by
    load-testing tools: P50 of 1..10 is the 5th value, 5.0."""
    import math

    ordered = sorted(samples)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank - 1, len(ordered) - 1)]


def run_sequential(events: list[Any], engine: VerdictEngine) -> dict[str, Any]:
    """One thread, chronological: the clean capacity number."""
    store = GraphStore()
    latencies: list[float] = []
    started = time.perf_counter()
    for event in events:
        t0 = time.perf_counter()
        store.upsert_event(event, entities_of(event))
        engine.score_event(event, store)
        latencies.append((time.perf_counter() - t0) * 1000)
    wall = time.perf_counter() - started
    return _summarize("sequential", len(events), wall, latencies)


def run_threaded(events: list[Any], engine: VerdictEngine, threads: int) -> dict[str, Any]:
    """N arrival threads against one single-writer graph.

    networkx is not thread-safe, so the upsert+score critical section is
    serialized behind a lock: exactly the SQLite single-writer model the
    service uses. This measures arrival contention and queueing delay,
    not scale-out; production scaling is worker-process sharding per the
    RFC, and the note in the result says so.
    """
    import threading

    store = GraphStore()
    latencies: list[float] = []
    write_lock = threading.Lock()

    def one(event: Any) -> None:
        t0 = time.perf_counter()
        with write_lock:
            store.upsert_event(event, entities_of(event))
            engine.score_event(event, store)
        latencies.append((time.perf_counter() - t0) * 1000)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=threads) as pool:
        list(pool.map(one, events))
    wall = time.perf_counter() - started
    result = _summarize(f"threads={threads}", len(events), wall, latencies)
    result["note"] = (
        "single-writer lock model (arrival contention), GIL-bound; production "
        "scaling is worker-process sharding per the RFC"
    )
    return result


def _summarize(mode: str, events: int, wall: float, latencies: list[float]) -> dict[str, Any]:
    steady = latencies[SAMPLE_BURN_IN:] if len(latencies) > SAMPLE_BURN_IN else latencies
    return {
        "mode": mode,
        "events": events,
        "throughput_events_per_sec": round(events / wall, 1),
        "latency_ms": {
            "p50": round(_percentile(steady, 0.50), 2),
            "p95": round(_percentile(steady, 0.95), 2),
            "p99": round(_percentile(steady, 0.99), 2),
            "max": round(max(steady), 2),
        },
        "wall_seconds": round(wall, 2),
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: python -m sentinel.loadtest [--events 1000] [--threads 1 4]."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--threads", type=int, nargs="*", default=[1, 4])
    parser.add_argument("--out", type=Path, default=Path("evaluation/loadtest.json"))
    args = parser.parse_args(argv)

    events, _, _ = generate_dataset(seed=args.seed)
    ordered = sorted(events, key=lambda e: e.ts)[: args.events]
    engine = VerdictEngine()

    results = [run_sequential(ordered, engine)]
    for threads in args.threads:
        if threads > 1:
            results.append(run_threaded(ordered, engine, threads))

    payload = {
        "dataset": f"seed {args.seed}, {len(ordered)} events, chronological",
        "hardware_note": "single machine, reference laptop, Python 3.12",
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
