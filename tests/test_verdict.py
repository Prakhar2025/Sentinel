"""Tests for the verdict engine (thresholds, degradation, evidence)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sentinel.data.models import PaymentEvent, PaymentMethod
from sentinel.graph import GraphStore, entities_of
from sentinel.verdict import (
    DEFAULT_BLOCK_THRESHOLD,
    DEFAULT_REVIEW_THRESHOLD,
    VerdictEngine,
    verdict_to_json,
)


def event(index: int, customer: str, merchant: str = "m1") -> PaymentEvent:
    return PaymentEvent(
        event_id=f"e{index}",
        merchant_id=merchant,
        customer_id=customer,
        amount_paise=100_000,
        upi_vpa=f"v{index}@ybl",
        phone="+919800000001",
        device_id="d1",
        email=None,
        ip=None,
        ts=datetime(2026, 8, 10, 12, 0, 0) + timedelta(minutes=index),
        payment_method=PaymentMethod.UPI,
    )


def store_with(events: list[PaymentEvent]) -> GraphStore:
    store = GraphStore()
    for e in events:
        store.upsert_event(e, entities_of(e))
    return store


def test_threshold_boundaries(monkeypatch) -> None:
    """Scores at 34/35/69/70 land in ALLOW/REVIEW/REVIEW/BLOCK_REC."""
    engine = VerdictEngine()
    store = store_with([event(0, "c1")])
    probe = event(1, "c1")

    from sentinel import scorer as scorer_module
    from sentinel import verdict as verdict_module

    for score_value, expected in (
        (34, "ALLOW"),
        (35, "REVIEW"),
        (69, "REVIEW"),
        (70, "BLOCK_REC"),
    ):
        # verdict.py binds score_features into its own namespace at import,
        # so the patch must target that binding.
        monkeypatch.setattr(
            verdict_module,
            "score_features",
            lambda f, w=None, _s=score_value: scorer_module.ScoreResult(
                score=_s, contributions={"patched": float(_s)}
            ),
        )
        verdict = engine.score_event(probe, store)
        assert verdict.verdict == expected, f"score {score_value} should be {expected}"
        assert verdict.degraded is False


def test_unknown_customer_degrades_to_review() -> None:
    engine = VerdictEngine()
    store = store_with([event(0, "c1")])
    verdict = engine.score_event(event(1, "ghost"), store)
    assert verdict.verdict == "REVIEW"
    assert verdict.reason_codes == ["SYS_DEGRADED"]
    assert verdict.degraded is True


def test_internal_error_degrades_never_raises(monkeypatch) -> None:
    engine = VerdictEngine()
    store = store_with([event(0, "c1")])

    from sentinel import verdict as verdict_module

    def exploding_extract(evt, _store):
        raise RuntimeError("boom")

    monkeypatch.setattr(verdict_module, "extract_features", exploding_extract)
    verdict = engine.score_event(event(1, "c1"), store)
    assert verdict.verdict == "REVIEW"
    assert verdict.reason_codes == ["SYS_DEGRADED"]
    assert "RuntimeError" in verdict.evidence["degradation_note"]


def test_verdict_carries_features_reasons_and_evidence() -> None:
    engine = VerdictEngine()
    ring = [
        PaymentEvent(
            event_id=f"r{i}",
            merchant_id=f"m{i}",
            customer_id=f"c{i}",
            amount_paise=120_000,
            upi_vpa=f"v{i}@ybl",
            phone="+919800000009",
            device_id="ring_device",
            email=None,
            ip=None,
            ts=datetime(2026, 8, 10, 12, 0, 0) + timedelta(minutes=i),
            payment_method=PaymentMethod.UPI,
        )
        for i in range(6)
    ]
    store = store_with(ring)
    verdict = engine.score_event(ring[-1], store)
    assert 0 <= verdict.score <= 100
    assert verdict.reason_codes
    assert "RNG_DEVICE_FANOUT" in verdict.reason_codes
    assert verdict.evidence["linked_merchants"]
    assert verdict.features
    payload = verdict_to_json(verdict)
    assert payload["event_id"] == "r5"
    assert payload["model_version"]


def test_engine_thresholds_exposed() -> None:
    engine = VerdictEngine(review_threshold=40, block_threshold=80)
    assert engine.thresholds == {"review": 40, "block": 80}
    assert DEFAULT_REVIEW_THRESHOLD < DEFAULT_BLOCK_THRESHOLD
