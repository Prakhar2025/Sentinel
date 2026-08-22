"""Contract and failure-injection tests for the API service (docs/06)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sentinel.config import Settings
from sentinel.service import create_app, mask_phone
from sentinel.store import AuditStore, StoreUnavailableError
from sentinel.verdict import VerdictEngine

API_KEY = {"X-API-Key": "test-key"}
ADMIN_KEY = {"X-Admin-Key": "admin-key"}
BOTH = {**API_KEY, **ADMIN_KEY}


def make_settings(tmp_path: Path, spool_dir: Path) -> Settings:
    return Settings(
        _env_file=None,
        sentinel_api_key="test-key",
        sentinel_admin_api_key="admin-key",
        model_config_path=str(tmp_path / "nonexistent-model.json"),
        spool_dir=str(spool_dir),
    )


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    settings = make_settings(tmp_path, tmp_path / "spool")
    store = AuditStore(tmp_path / "audit.db")
    app = create_app(settings=settings, store=store, engine=VerdictEngine())
    return TestClient(app, raise_server_exceptions=False)


def event_payload(index: int, customer: str = "c1", device: str = "d1", **overrides) -> dict:
    payload = {
        "event_id": f"evt-{index:04d}",
        "merchant_id": f"mcht-{index % 3}",
        "customer_id": customer,
        "amount_paise": 120_000,
        "currency": "INR",
        "upi_vpa": "priya@ybl",
        "phone": "+919812345678",
        "device_id": device,
        "email": "priya@gmail.com",
        "ip": "103.21.58.7",
        "ts": "2026-08-20T14:31:05+05:30",
        "payment_method": "upi",
        "prior_outcome": None,
    }
    payload.update(overrides)
    return payload


class TestAuth:
    def test_missing_key_is_401_problem(self, client: TestClient) -> None:
        response = client.post("/v1/events", json=event_payload(1))
        assert response.status_code == 401
        assert response.json()["type"] == "HTTP_ERROR"

    def test_wrong_key_is_401(self, client: TestClient) -> None:
        response = client.post("/v1/events", json=event_payload(1), headers={"X-API-Key": "nope"})
        assert response.status_code == 401

    def test_admin_route_requires_admin_key(self, client: TestClient) -> None:
        client.post("/v1/events", json=event_payload(1, device="dev1"), headers=API_KEY)
        ok = client.get("/v1/risk/entities/device/dev1/full", headers=BOTH)
        assert ok.status_code == 200
        denied = client.get("/v1/risk/entities/device/dev1/full", headers=API_KEY)
        assert denied.status_code == 403


class TestIngest:
    def test_happy_path_verdict_shape(self, client: TestClient) -> None:
        response = client.post("/v1/events", json=event_payload(1), headers=API_KEY)
        assert response.status_code == 200
        body = response.json()
        assert body["event_id"] == "evt-0001"
        assert 0 <= body["score"] <= 100
        assert body["verdict"] in {"ALLOW", "REVIEW", "BLOCK_REC"}
        assert isinstance(body["reason_codes"], list)
        assert body["features"] and body["evidence"]
        assert body["explanation_status"] == "PENDING"
        assert body["duplicate"] is False
        assert body["schema_version"] == "1"

    def test_validation_failure_is_400_problem(self, client: TestClient) -> None:
        bad = event_payload(2)
        bad["amount_paise"] = -5
        response = client.post("/v1/events", json=bad, headers=API_KEY)
        assert response.status_code == 400
        assert response.json()["type"] == "VALIDATION_FAILED"

    def test_duplicate_returns_409_with_prior_verdict(self, client: TestClient) -> None:
        first = client.post("/v1/events", json=event_payload(3), headers=API_KEY)
        assert first.status_code == 200
        second = client.post("/v1/events", json=event_payload(3), headers=API_KEY)
        assert second.status_code == 409
        body = second.json()
        assert body["type"] == "DUPLICATE_EVENT"
        assert body["verdict"]["event_id"] == "evt-0003"

    def test_batch_partial_success(self, client: TestClient) -> None:
        client.post("/v1/events", json=event_payload(10), headers=API_KEY)  # will duplicate
        batch = [event_payload(10), event_payload(11), event_payload(12)]
        response = client.post("/v1/events:batch", json=batch, headers=API_KEY)
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] == 2
        assert body["duplicate"] == 1
        statuses = {item["status"] for item in body["results"]}
        assert statuses == {"accepted", "duplicate"}


class TestVerdictQueries:
    def test_unknown_event_404(self, client: TestClient) -> None:
        response = client.get("/v1/verdicts/nope", headers=API_KEY)
        assert response.status_code == 404

    def test_queue_filters_and_orders_by_score(self, client: TestClient) -> None:
        for i in range(5):
            client.post(
                "/v1/events",
                json=event_payload(20 + i, customer=f"c{i}", device="d_shared"),
                headers=API_KEY,
            )
        response = client.get("/v1/verdicts?limit=3", headers=API_KEY)
        assert response.status_code == 200
        rows = response.json()
        assert len(rows) == 3
        scores = [row["score"] for row in rows]
        assert scores == sorted(scores, reverse=True)

    def test_feedback_records_and_rejects_unknown(self, client: TestClient) -> None:
        ingested = client.post("/v1/events", json=event_payload(30), headers=API_KEY).json()
        verdict_id = None
        # verdict_id is not exposed on the ingest payload; fetch via queue
        queue = client.get("/v1/verdicts", headers=API_KEY).json()
        verdict_id = next(
            row["verdict_id"] for row in queue if row["event_id"] == ingested["event_id"]
        )
        accepted = client.post(
            "/v1/feedback",
            json={"verdict_id": verdict_id, "analyst_decision": "CLEAR", "note": "ok"},
            headers=API_KEY,
        )
        assert accepted.status_code == 202
        unknown = client.post(
            "/v1/feedback",
            json={"verdict_id": "missing", "analyst_decision": "CLEAR"},
            headers=API_KEY,
        )
        assert unknown.status_code == 404
        bad = client.post(
            "/v1/feedback",
            json={"verdict_id": verdict_id, "analyst_decision": "MAYBE"},
            headers=API_KEY,
        )
        assert bad.status_code == 400


class TestEntityEndpoints:
    def test_standard_scope_gets_aggregates_only(self, client: TestClient) -> None:
        client.post(
            "/v1/events", json=event_payload(40, customer="c1", device="dev_x"), headers=API_KEY
        )
        client.post(
            "/v1/events",
            json=event_payload(41, customer="c2", device="dev_x", upi_vpa="other@ybl"),
            headers=API_KEY,
        )
        response = client.get("/v1/risk/entities/device/dev_x", headers=API_KEY)
        assert response.status_code == 200
        signal = response.json()["federated_signal"]
        assert signal["linked_identity_count"] == 2
        # No merchant identifiers may leak at standard scope (doc 07).
        text = response.text
        assert "mcht-" not in text

    def test_admin_scope_gets_full_listing_and_is_audited(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        client.post("/v1/events", json=event_payload(42, device="dev_y"), headers=API_KEY)
        response = client.get("/v1/risk/entities/device/dev_y/full", headers=BOTH)
        assert response.status_code == 200
        assert "linked_nodes" in response.json()

    def test_unknown_entity_404_and_bad_type_400(self, client: TestClient) -> None:
        assert client.get("/v1/risk/entities/device/ghost", headers=API_KEY).status_code == 404
        assert client.get("/v1/risk/entities/merchant/m1", headers=API_KEY).status_code == 400


class TestClusterAndMasking:
    def test_cluster_masks_phones_by_default(self, client: TestClient) -> None:
        client.post("/v1/events", json=event_payload(50), headers=API_KEY)
        response = client.get("/v1/graph/cluster/c1", headers=API_KEY)
        assert response.status_code == 200
        phone_nodes = [n for n in response.json()["nodes"] if n["type"] == "phone"]
        assert phone_nodes
        assert "XXXX" in phone_nodes[0]["id"]

    def test_unmask_requires_admin_key_and_is_audited(
        self, client: TestClient, tmp_path: Path
    ) -> None:
        client.post("/v1/events", json=event_payload(51), headers=API_KEY)
        denied = client.get("/v1/graph/cluster/c1?unmask=true", headers=API_KEY)
        assert denied.status_code == 403
        allowed = client.get("/v1/graph/cluster/c1?unmask=true", headers=BOTH)
        assert allowed.status_code == 200
        phone_nodes = [n for n in allowed.json()["nodes"] if n["type"] == "phone"]
        assert phone_nodes[0]["id"] == "+919812345678"

    def test_unknown_customer_404(self, client: TestClient) -> None:
        assert client.get("/v1/graph/cluster/ghost", headers=API_KEY).status_code == 404


class TestHealthAndDegradation:
    def test_health_and_readiness(self, client: TestClient) -> None:
        assert client.get("/healthz").json() == {"status": "ok"}
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["store"] == "ok"

    def test_store_failure_spools_and_returns_503(self, tmp_path: Path) -> None:
        settings = make_settings(tmp_path, tmp_path / "spool")

        class BrokenStore(AuditStore):
            def insert_event(self, payload):  # type: ignore[override]
                raise StoreUnavailableError("injected failure")

        app = create_app(
            settings=settings, store=BrokenStore(tmp_path / "broken.db"), engine=VerdictEngine()
        )
        broken_client = TestClient(app, raise_server_exceptions=False)
        response = broken_client.post("/v1/events", json=event_payload(60), headers=API_KEY)
        assert response.status_code == 503
        assert response.json()["type"] == "STORE_UNAVAILABLE"
        spool_file = tmp_path / "spool" / "ingest.spool"
        assert spool_file.exists()
        assert "evt-0060" in spool_file.read_text(encoding="utf-8")

    def test_readiness_fails_when_store_down(self, tmp_path: Path) -> None:
        settings = make_settings(tmp_path, tmp_path / "spool")

        class UnreachableStore(AuditStore):
            def healthy(self) -> bool:
                return False

        app = create_app(
            settings=settings, store=UnreachableStore(tmp_path / "x.db"), engine=VerdictEngine()
        )
        client = TestClient(app)
        assert client.get("/readyz").status_code == 503


def test_mask_phone_shapes() -> None:
    assert mask_phone("+919812345678") == "+9198XXXX5678"
    assert mask_phone(None) is None
    assert mask_phone("123") == "XXX"
