"""Public-demo helpers: daily-capped live explanations and rate limiting.

The hosted demo has no AWS secret exposure beyond the server itself:
Bedrock runs server-side behind POST /v1/explain/{event_id}, gated by a
persisted daily counter (EXPLAIN_DAILY_CAP). When the cap is hit the
endpoint serves the stored narrative (or a "cap reached" marker) and
never errors the visitor. The in-memory limiter bounds request abuse
per IP; it resets on restart, which is acceptable for a demo whose
expensive path is independently capped.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class DailyCap:
    """Persisted daily counter: survive restarts, reset at UTC midnight."""

    def __init__(self, path: Path, cap: int) -> None:
        self._path = path
        self._cap = cap
        self._lock = threading.Lock()
        self._day = ""
        self._count = 0
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._day, self._count = data["day"], int(data["count"])
        except (OSError, KeyError, json.JSONDecodeError):
            self._day, self._count = self._today(), 0

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"day": self._day, "count": self._count}), encoding="utf-8"
        )

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%d")

    def try_acquire(self) -> bool:
        """True when a paid call is allowed under today's cap."""
        with self._lock:
            today = self._today()
            if self._day != today:
                self._day, self._count = today, 0
            if self._count >= self._cap:
                self._save()
                return False
            self._count += 1
            self._save()
            return True

    def status(self) -> dict[str, int | str]:
        return {"cap": self._cap, "used": self._count, "day": self._day}


class RateLimiter:
    """Fixed-window per-IP limiter; in-memory by design for the demo."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self._window:
                hits.popleft()
            if len(hits) >= self._max:
                return False
            hits.append(now)
            return True

    def client_key(self, request: Any) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        return (forwarded.split(",")[0].strip() if forwarded else None) or (
            request.client.host if request.client else "unknown"
        )


def new_session_id() -> str:
    """Playground session correlation."""
    return uuid.uuid4().hex[:12]


__all__ = ["DailyCap", "RateLimiter", "new_session_id"]
