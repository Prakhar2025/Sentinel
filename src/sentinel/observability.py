"""Observability: Prometheus exposition, request ids, drift gauges.

Zero external dependencies: the registry is a thread-safe counter /
gauge / histogram set rendering the standard Prometheus text format,
which any scraper (Prometheus, Grafana Agent, a curl) can consume.
Losing the registry loses telemetry, never verdicts; every method is
best-effort and cannot raise into the request path.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque

RECENT_WINDOW = 500
BASELINE_WINDOW = 500

_LATENCY_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class MetricsRegistry:
    """Thread-safe Prometheus text-format registry."""

    def __init__(
        self, recent_window: int = RECENT_WINDOW, baseline_window: int = BASELINE_WINDOW
    ) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, float] = {}
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = {}
        self._recent_scores: deque[float] = deque(maxlen=recent_window)
        self._baseline_window = baseline_window
        self._baseline_mean = 0.0
        self._baseline_n = 0
        self._baseline_n = 0
        self.started_at = time.time()

    # ---------------------------------------------------------------- write

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = name
        if labels:
            rendered = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
            key = f"{name}{{{rendered}}}"
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def gauge(self, name: str, value: float) -> None:
        with self._lock:
            self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._histograms.setdefault(name, []).append(value)

    def observe_score(self, score: float) -> None:
        """Track verdict scores for the drift gauges.

        Drift needs a warm-up: the baseline mean settles over the first
        `baseline_window` scores, and only afterwards does
        recent-vs-baseline become meaningful. Before warm-up completes
        the drift gauge reads 0 by construction, not by accident.
        """
        with self._lock:
            self._recent_scores.append(score)
            if self._baseline_n < self._baseline_window:
                self._baseline_n += 1
                self._baseline_mean += (score - self._baseline_mean) / self._baseline_n

    # ----------------------------------------------------------------- read

    def render(self) -> str:
        """Prometheus text exposition (version 0.0.4)."""
        with self._lock:
            lines: list[str] = []
            emitted_types: set[str] = set()
            for name, value in sorted(self._counters.items()):
                family = name.split("{")[0]
                if family not in emitted_types:
                    lines.append(f"# TYPE {family} counter")
                    emitted_types.add(family)
                lines.append(f"{name} {value}")
            for name, value in sorted(self._gauges.items()):
                lines.append(f"# TYPE {name} gauge")
                lines.append(f"{name} {value}")
            for name, samples in sorted(self._histograms.items()):
                lines.append(f"# TYPE {name} histogram")
                counts = [0] * len(_LATENCY_BUCKETS)
                for sample in samples:
                    for index, bound in enumerate(_LATENCY_BUCKETS):
                        if sample <= bound:
                            counts[index] += 1
                for bound, count in zip(_LATENCY_BUCKETS, counts, strict=True):
                    lines.append(f'{name}_bucket{{le="{bound}"}} {count}')
                lines.append(f'{name}_bucket{{le="+Inf"}} {len(samples)}')
                lines.append(f"{name}_count {len(samples)}")
                if samples:
                    lines.append(f"{name}_sum {round(sum(samples), 6)}")
            if self._recent_scores:
                recent_mean = sum(self._recent_scores) / len(self._recent_scores)
                lines.append("# TYPE sentinel_score_mean_recent gauge")
                lines.append(f"sentinel_score_mean_recent {round(recent_mean, 4)}")
                lines.append("# TYPE sentinel_score_drift gauge")
                warmed = self._baseline_n >= self._baseline_window
                drift = recent_mean - self._baseline_mean if warmed else 0.0
                lines.append(f"sentinel_score_drift {round(drift, 4)}")
            lines.append("# TYPE sentinel_uptime_seconds gauge")
            lines.append(f"sentinel_uptime_seconds {round(time.time() - self.started_at, 1)}")
            return "\n".join(lines) + "\n"


def new_request_id() -> str:
    """Correlation id for one request, echoed in every response."""
    return uuid.uuid4().hex[:16]


__all__ = ["MetricsRegistry", "new_request_id"]
