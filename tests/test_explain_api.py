"""Tests for the public-demo helpers: daily cap and rate limiter."""

from __future__ import annotations

from pathlib import Path

from sentinel.explain_api import DailyCap, RateLimiter


class TestDailyCap:
    def test_acquire_under_cap(self, tmp_path: Path) -> None:
        cap = DailyCap(tmp_path / "cap.json", cap=2)
        assert cap.try_acquire() is True
        assert cap.try_acquire() is True
        assert cap.try_acquire() is False  # cap reached

    def test_cap_persists_across_instances(self, tmp_path: Path) -> None:
        first = DailyCap(tmp_path / "cap.json", cap=3)
        first.try_acquire()
        first.try_acquire()
        second = DailyCap(tmp_path / "cap.json", cap=3)
        assert second.status()["used"] == 2

    def test_status_shape(self, tmp_path: Path) -> None:
        status = DailyCap(tmp_path / "cap.json", cap=7).status()
        assert status == {"cap": 7, "used": 0, "day": status["day"]}


class TestRateLimiter:
    def test_allows_within_window(self) -> None:
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        assert limiter.allow("1.2.3.4") is True
        assert limiter.allow("1.2.3.4") is True
        assert limiter.allow("1.2.3.4") is True

    def test_blocks_past_max(self) -> None:
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        assert limiter.allow("ip") is True
        assert limiter.allow("ip") is True
        assert limiter.allow("ip") is False

    def test_keys_are_independent(self) -> None:
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        assert limiter.allow("a") is True
        assert limiter.allow("b") is True
        assert limiter.allow("a") is False
