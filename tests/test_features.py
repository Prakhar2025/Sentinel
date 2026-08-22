"""Tests for feature extraction F1-F7 on hand-built graph scenarios."""

from __future__ import annotations

from datetime import datetime, timedelta

from sentinel.data.models import PaymentEvent, PaymentMethod, PriorOutcome
from sentinel.features import extract_features, feature_vector_from_raw
from sentinel.graph import GraphStore, entities_of

BASE = datetime(2026, 8, 10, 12, 0, 0)


def event(
    index: int,
    customer: str,
    merchant: str,
    *,
    ts: datetime | None = None,
    amount: int = 100_000,
    vpa: str | None = "v@ybl",
    phone: str | None = "+919800000001",
    device: str | None = "d1",
    email: str | None = None,
    outcome: PriorOutcome | None = None,
) -> PaymentEvent:
    return PaymentEvent(
        event_id=f"e{index}",
        merchant_id=merchant,
        customer_id=customer,
        amount_paise=amount,
        upi_vpa=vpa,
        phone=phone,
        device_id=device,
        email=email,
        ip=None,
        ts=ts or (BASE + timedelta(minutes=index)),
        payment_method=PaymentMethod.UPI,
        prior_outcome=outcome,
    )


def build(events: list[PaymentEvent]) -> GraphStore:
    store = GraphStore()
    for e in events:
        store.upsert_event(e, entities_of(e))
    return store


def test_unknown_customer_returns_none() -> None:
    store = GraphStore()
    assert extract_features(event(0, "ghost", "m1"), store) is None


def test_f1_ratio_and_f2_fanout() -> None:
    store = build(
        [
            event(0, "c1", "m1", device="shared"),
            event(1, "c2", "m2", device="shared", vpa="v@ybl"),
            event(2, "c3", "m3", device="shared", vpa="v@ybl"),
            event(3, "c4", "m4", device="shared", vpa="v@ybl"),
            event(4, "c5", "m5", device="shared", vpa="v@ybl"),
            event(5, "c6", "m6", device="shared", vpa="v@ybl"),
        ]
    )
    features = extract_features(event(99, "c1", "m1", ts=BASE + timedelta(hours=1)), store)
    assert features is not None
    assert features.device_identity_ratio == 6.0
    assert features.cross_merchant_fanout == 6
    assert features.n_f2 == 1.0


def test_f3_taint_from_outcome() -> None:
    store = build(
        [
            event(0, "c1", "m1", device="d1", outcome=PriorOutcome.CHARGEBACK),
            event(1, "c2", "m2", device="d1", vpa="w@ybl", phone="+919800000002"),
        ]
    )
    features = extract_features(event(99, "c2", "m2"), store)
    assert features is not None
    # F3 is the max taint across the cluster; the source customer's 1.0
    # is in c2's cluster through the shared device. The neighbor-level
    # decay (0.36) is asserted in the graph tests.
    assert features.taint == 1.0


def test_f4_velocity_window_boundary() -> None:
    # Two merchants in-window, one just outside (72h boundary). The probe
    # event sits at BASE exactly so the hour offsets are the real ages.
    store = build(
        [
            event(0, "c1", "m1", ts=BASE - timedelta(hours=71)),
            event(1, "c1", "m2", ts=BASE - timedelta(hours=70)),
            event(2, "c1", "m3", ts=BASE - timedelta(hours=73)),
        ]
    )
    features = extract_features(event(99, "c1", "m1", ts=BASE), store)
    assert features is not None
    assert features.velocity_merchants_72h == 2


def test_f5_burn_and_rotate() -> None:
    store = build(
        [
            event(0, "c1", "m1", vpa="v1@ybl", device="d1", ts=BASE),
            event(
                1,
                "c1",
                "m1",
                vpa="v1@ybl",
                device="d1",
                ts=BASE + timedelta(hours=1),
                outcome=PriorOutcome.CHARGEBACK,
            ),
            event(2, "c2", "m2", vpa="v2@ybl", device="d1", ts=BASE + timedelta(hours=20)),
        ]
    )
    features = extract_features(event(99, "c2", "m2"), store)
    assert features is not None
    assert features.burn_rotate == 1


def test_f5_requires_replacement() -> None:
    store = build(
        [
            event(0, "c1", "m1", vpa="v1@ybl", device="d1"),
            event(1, "c1", "m1", vpa="v1@ybl", device="d1", outcome=PriorOutcome.REFUND_ABUSE),
        ]
    )
    features = extract_features(event(99, "c1", "m1"), store)
    assert features is not None
    assert features.burn_rotate == 0


def test_f6_amount_band_partial_and_full() -> None:
    store = build([event(0, "c1", "m1", amount=150_000)])  # event in band
    features = extract_features(event(99, "c1", "m1", amount=150_000), store)
    assert features is not None
    assert features.amount_band_hit == 1.0  # event and cluster mean in band

    store_big = build([event(0, "c1", "m1", amount=900_000)])  # outside band
    features_big = extract_features(event(99, "c1", "m1", amount=900_000), store_big)
    assert features_big is not None
    assert features_big.amount_band_hit == 0.0


def test_f7_new_identity_fraction() -> None:
    store = build(
        [
            event(0, "c1", "m1", ts=BASE - timedelta(days=2)),
            event(1, "c2", "m2", ts=BASE - timedelta(days=1), device="d1", vpa="v@ybl"),
        ]
    )
    features = extract_features(event(99, "c1", "m1"), store)
    assert features is not None
    assert features.new_identity_fraction == 1.0


def test_feature_vector_roundtrip_from_raw() -> None:
    original = extract_features(event(0, "c1", "m1"), build([event(0, "c1", "m1")]))
    assert original is not None
    rebuilt = feature_vector_from_raw(original.raw())
    assert rebuilt.normalized() == original.normalized()
    assert rebuilt.raw() == original.raw()
