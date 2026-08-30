"""Postgres integration tests: the port/adapter swap, proven.

Skipped locally unless SENTINEL_TEST_DATABASE_URL is set; CI runs them
against a real Postgres 16 service container, demonstrating that the
same AuditStore code serves both engines unchanged.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest

from sentinel.store import AuditStore

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("SENTINEL_TEST_DATABASE_URL"),
        reason="SENTINEL_TEST_DATABASE_URL not configured (CI provides it)",
    ),
]

URL = os.environ.get("SENTINEL_TEST_DATABASE_URL", "")


@pytest.fixture()
def store() -> AuditStore:
    return AuditStore(url=URL)


def test_event_roundtrip(store: AuditStore) -> None:
    event = {
        "event_id": f"pg-{datetime.now(UTC).timestamp()}",
        "merchant_id": "mcht_pg",
        "customer_id": "cust_pg",
        "amount_paise": 42_000,
        "upi_vpa": "pg@ybl",
        "phone": "+919800000001",
        "device_id": "dev_pg",
        "email": None,
        "ip": None,
        "payment_method": "upi",
        "prior_outcome": None,
        "ts": datetime.now(UTC).isoformat(),
    }
    assert store.insert_event(event) is True
    assert store.insert_event(event) is False  # idempotent
    stored = store.all_events()
    assert any(row["event_id"] == event["event_id"] for row in stored)


def test_verdict_roundtrip_with_shadow(store: AuditStore) -> None:
    verdict = {
        "event_id": f"pgv-{datetime.now(UTC).timestamp()}",
        "score": 91,
        "verdict": "BLOCK_REC",
        "reason_codes": ["RNG_DEVICE_FANOUT"],
        "evidence": {"linked_merchants": ["m1", "m2"]},
        "features": {"device_identity_ratio": 6.0},
        "contributions": {"taint_propagation": 20.0},
        "model_version": "rules-v1.1",
        "explanation_status": "PENDING",
        "challenger": {"score": 88, "flag": True},
    }
    store.insert_verdict(verdict)
    fetched = store.get_verdict(verdict["event_id"])
    assert fetched is not None
    assert fetched["score"] == 91
    assert fetched["challenger"]["flag"] is True


def test_healthy(store: AuditStore) -> None:
    assert store.healthy() is True
