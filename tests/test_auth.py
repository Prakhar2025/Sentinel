"""Tests for per-merchant JWT authentication."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from tests.test_api import API_KEY, event_payload, make_settings

from sentinel.auth import issue_token, verify_token
from sentinel.service import create_app
from sentinel.store import AuditStore
from sentinel.verdict import VerdictEngine

SECRET = "unit-jwt-secret"


class TestTokenPrimitives:
    def test_issue_and_verify_roundtrip(self) -> None:
        token = issue_token(SECRET, "mcht_1")
        identity = verify_token(SECRET, token)
        assert identity is not None
        assert identity.merchant_id == "mcht_1"
        assert identity.scope == "standard"

    def test_wrong_secret_rejected(self) -> None:
        token = issue_token(SECRET, "mcht_1")
        assert verify_token("other-secret", token) is None

    def test_expired_token_rejected(self) -> None:
        token = issue_token(SECRET, "mcht_1", ttl_seconds=-10)
        assert verify_token(SECRET, token) is None

    def test_garbage_token_rejected(self) -> None:
        assert verify_token(SECRET, "not.a.jwt") is None


class TestBearerService:
    @pytest.fixture()
    def client(self, tmp_path: Path) -> TestClient:
        settings = make_settings(tmp_path, tmp_path / "spool")
        settings.jwt_secret = SECRET
        app = create_app(
            settings=settings,
            store=AuditStore(tmp_path / "audit.db"),
            engine=VerdictEngine(),
            enable_challenger=False,
        )
        return TestClient(app, raise_server_exceptions=False)

    def bearer(self, merchant: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {issue_token(SECRET, merchant)}"}

    def test_bearer_can_ingest_own_merchant(self, client: TestClient) -> None:
        payload = event_payload(10)
        payload["merchant_id"] = "mcht_mine"
        response = client.post("/v1/events", json=payload, headers=self.bearer("mcht_mine"))
        assert response.status_code == 200

    def test_bearer_cannot_ingest_other_merchant(self, client: TestClient) -> None:
        payload = event_payload(11)
        payload["merchant_id"] = "mcht_theirs"
        response = client.post("/v1/events", json=payload, headers=self.bearer("mcht_mine"))
        assert response.status_code == 403
        assert response.json()["type"] == "MERCHANT_MISMATCH"

    def test_queue_scoped_to_own_traffic(self, client: TestClient) -> None:
        mine = event_payload(20)
        mine["merchant_id"] = "mcht_mine"
        theirs = event_payload(21)
        theirs["merchant_id"] = "mcht_theirs"
        client.post("/v1/events", json=mine, headers=self.bearer("mcht_mine"))
        client.post("/v1/events", json=theirs, headers=API_KEY)
        rows = client.get("/v1/verdicts", headers=self.bearer("mcht_mine")).json()
        assert rows, "at least own row present"
        evidence = [row.get("evidence", {}).get("merchant_id") for row in rows]
        assert all(merchant == "mcht_mine" for merchant in evidence)

    def test_legacy_key_still_works_alongside(self, client: TestClient) -> None:
        response = client.post("/v1/events", json=event_payload(30), headers=API_KEY)
        assert response.status_code == 200

    def test_invalid_bearer_rejected(self, client: TestClient) -> None:
        response = client.post(
            "/v1/events",
            json=event_payload(31),
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        assert response.status_code == 401

    def test_no_credentials_rejected(self, client: TestClient) -> None:
        assert client.post("/v1/events", json=event_payload(32)).status_code == 401
