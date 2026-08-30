"""Tests for observability: metrics, request ids, drift gauges."""

from __future__ import annotations

from fastapi.testclient import TestClient
from tests.test_api import API_KEY, event_payload, make_settings

from sentinel.observability import MetricsRegistry, new_request_id
from sentinel.service import create_app
from sentinel.store import AuditStore
from sentinel.verdict import VerdictEngine


class TestRegistry:
    def test_counters_with_labels_render_prometheus_text(self) -> None:
        registry = MetricsRegistry()
        registry.inc("sentinel_verdicts_total", band="block_rec")
        registry.inc("sentinel_verdicts_total", band="block_rec")
        registry.inc("sentinel_verdicts_total", band="allow")
        text = registry.render()
        assert "# TYPE sentinel_verdicts_total counter" in text
        assert 'sentinel_verdicts_total{band="block_rec"} 2' in text
        assert 'sentinel_verdicts_total{band="allow"} 1' in text

    def test_histogram_buckets_and_sum(self) -> None:
        registry = MetricsRegistry()
        registry.observe("sentinel_event_latency_seconds", 0.01)
        registry.observe("sentinel_event_latency_seconds", 0.60)
        text = registry.render()
        assert 'sentinel_event_latency_seconds_bucket{le="0.01"} 1' in text
        assert 'sentinel_event_latency_seconds_bucket{le="+Inf"} 2' in text
        assert "sentinel_event_latency_seconds_count 2" in text

    def test_drift_warms_up_then_tracks(self) -> None:
        registry = MetricsRegistry(recent_window=5, baseline_window=10)
        for score in range(5):
            registry.observe_score(score)
        assert "sentinel_score_drift 0.0" in registry.render()  # still warming
        for score in range(5, 10):
            registry.observe_score(score)  # baseline completes at mean 4.5
        for score in (90, 95, 85, 92, 88):
            registry.observe_score(score)
        text = registry.render()
        # Baseline mean 4.5, recent mean 90.0 -> drift 85.5.
        assert "sentinel_score_mean_recent 90.0" in text
        assert "sentinel_score_drift 85.5" in text

    def test_render_never_raises_when_empty(self) -> None:
        assert MetricsRegistry().render()


class TestServiceInstrumentation:
    def make_client(self, tmp_path) -> TestClient:
        settings = make_settings(tmp_path, tmp_path / "spool")
        app = create_app(
            settings=settings,
            store=AuditStore(tmp_path / "audit.db"),
            engine=VerdictEngine(),
        )
        return TestClient(app, raise_server_exceptions=False)

    def test_request_id_echoed_and_generated(self, tmp_path) -> None:
        client = self.make_client(tmp_path)
        response = client.get("/healthz")
        assert response.headers.get("X-Request-Id")
        passed = client.get("/healthz", headers={"X-Request-Id": "fixed-id-42"})
        assert passed.headers["X-Request-Id"] == "fixed-id-42"

    def test_metrics_endpoint_requires_key_and_reports_ingest(self, tmp_path) -> None:
        client = self.make_client(tmp_path)
        assert client.get("/metrics").status_code == 401
        client.post("/v1/events", json=event_payload(1), headers=API_KEY)
        body = client.get("/metrics", headers=API_KEY).text
        assert "sentinel_events_total 1" in body
        assert "sentinel_verdicts_total" in body
        assert "sentinel_event_latency_seconds" in body

    def test_new_request_id_unique_and_short(self) -> None:
        ids = {new_request_id() for _ in range(200)}
        assert len(ids) == 200
        assert all(len(value) == 16 for value in ids)
