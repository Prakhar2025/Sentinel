"""Tests for the identity link graph (docs/03, docs/04, feature inputs)."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sentinel.data.models import PaymentEvent, PaymentMethod, PriorOutcome
from sentinel.graph import GraphStore, NodeType, entities_of, node_id, replay
from sentinel.normalize import NormalizedEntities

BASE_TS = datetime(2026, 8, 1, 12, 0, 0)


def make_event(
    index: int,
    customer: str,
    merchant: str,
    vpa: str | None = "v1@ybl",
    phone: str | None = "+919800000001",
    device: str | None = "dev_a",
    email: str | None = None,
    outcome: PriorOutcome | None = None,
) -> PaymentEvent:
    return PaymentEvent(
        event_id=f"e{index}",
        merchant_id=merchant,
        customer_id=customer,
        amount_paise=50_000,
        upi_vpa=vpa,
        phone=phone,
        device_id=device,
        email=email,
        ip="103.0.0.1",
        ts=BASE_TS + timedelta(minutes=index),
        payment_method=PaymentMethod.UPI,
        prior_outcome=outcome,
    )


def entities(
    vpa: str | None = "v1@ybl",
    phone: str | None = "+919800000001",
    device: str | None = "dev_a",
    email: str | None = None,
) -> NormalizedEntities:
    return NormalizedEntities(upi_vpa=vpa, phone=phone, device_id=device, email=email)


class TestUpsertAndDerivedAttributes:
    def test_nodes_and_edges_created_with_types(self) -> None:
        store = GraphStore()
        store.upsert_event(make_event(0, "c1", "m1"), entities())
        assert store.size == 5  # customer + merchant + vpa + phone + device
        attrs = store.node_attrs(NodeType.CUSTOMER, "c1")
        assert attrs is not None and attrs["type"] == "customer"
        assert store.node_attrs(NodeType.DEVICE, "dev_a") is not None
        assert store.node_attrs(NodeType.MERCHANT, "m1") is not None

    def test_repeat_event_increments_aggregates_without_duplicates(self) -> None:
        store = GraphStore()
        event = make_event(0, "c1", "m1")
        store.upsert_event(event, entities())
        store.upsert_event(event, entities())
        customer = store.node_attrs(NodeType.CUSTOMER, "c1")
        assert customer is not None and customer["event_count"] == 2
        assert store.size == 5  # no duplicate nodes

    def test_entity_derived_attributes(self) -> None:
        store = GraphStore()
        # c1 and c2 share device dev_a and vpa v1; different merchants.
        store.upsert_event(make_event(0, "c1", "m1"), entities())
        store.upsert_event(
            make_event(1, "c2", "m2"),
            entities(vpa="v1@ybl", phone="+919800000002", device="dev_a"),
        )
        device = store.node_attrs(NodeType.DEVICE, "dev_a")
        vpa = store.node_attrs(NodeType.UPI, "v1@ybl")
        assert device is not None
        assert device["linked_identity_count"] == 2
        assert device["merchant_count"] == 2  # m1 via c1, m2 via c2
        assert vpa is not None and vpa["merchant_count"] == 2

    def test_none_entities_skipped(self) -> None:
        store = GraphStore()
        store.upsert_event(
            make_event(0, "c1", "m1"),
            NormalizedEntities(upi_vpa=None, phone=None, device_id=None, email=None),
        )
        assert store.size == 2


class TestTaintPropagation:
    def test_outcome_taints_source_and_neighbors(self) -> None:
        store = GraphStore()
        store.upsert_event(make_event(0, "c1", "m1", outcome=PriorOutcome.CHARGEBACK), entities())
        store.upsert_event(
            make_event(1, "c2", "m2"),
            entities(vpa="v2@ybl", phone="+919800000002", device="dev_a"),
        )
        c1 = store.node_attrs(NodeType.CUSTOMER, "c1")
        device = store.node_attrs(NodeType.DEVICE, "dev_a")
        c2 = store.node_attrs(NodeType.CUSTOMER, "c2")
        assert c1 is not None and c1["confirmed_fraud"] is True
        assert c1["fraud_taint"] == 1.0
        assert device is not None and device["fraud_taint"] == pytest.approx(0.6)
        assert c2 is not None and c2["fraud_taint"] == pytest.approx(0.36)

    def test_merchants_never_tainted(self) -> None:
        store = GraphStore()
        store.upsert_event(
            make_event(0, "c1", "m1", outcome=PriorOutcome.CONFIRMED_FRAUD), entities()
        )
        merchant = store.node_attrs(NodeType.MERCHANT, "m1")
        assert merchant is not None and merchant["fraud_taint"] == 0.0

    def test_taint_bounded_at_max_hops(self) -> None:
        # Chain: c1 -(d1)- c2 -(d2)- c3 -(d3)- c4; taint source c1.
        store = GraphStore()
        store.upsert_event(
            make_event(0, "c1", "m1", outcome=PriorOutcome.CHARGEBACK),
            entities(vpa="a@ybl", phone="+919800000001", device="d1"),
        )
        store.upsert_event(
            make_event(1, "c2", "m1"),
            entities(vpa="b@ybl", phone="+919800000002", device="d1"),
        )
        store.upsert_event(
            make_event(2, "c3", "m1"),
            entities(vpa="c@ybl", phone="+919800000003", device="d2"),
        )
        # c2 gets d2 only via this event; c3 carries d2.
        store.upsert_event(
            make_event(3, "c3", "m1"),
            entities(vpa="d@ybl", phone="+919800000003", device="d2"),
        )
        store.upsert_event(
            make_event(4, "c4", "m1"),
            entities(vpa="e@ybl", phone="+919800000004", device="d3"),
        )
        # Link c3-c4 via shared phone.
        store.upsert_event(
            make_event(5, "c4", "m1"),
            entities(vpa="f@ybl", phone="+919800000003", device="d3"),
        )
        c4 = store.node_attrs(NodeType.CUSTOMER, "c4")
        assert c4 is not None and c4["fraud_taint"] == 0.0

    def test_benign_outcomes_absent(self) -> None:
        store = GraphStore()
        store.upsert_event(make_event(0, "c1", "m1"), entities())
        c1 = store.node_attrs(NodeType.CUSTOMER, "c1")
        assert c1 is not None and c1["fraud_taint"] == 0.0


class TestTwelveNodeFixture:
    """The hand-built fixture from the phase checkpoint: 12 nodes exactly.

    C1 pays V1 on D1 at M1 with phone P1
    C2 pays V2 on D1 at M2 with email E1
    C3 pays V2 on D1 at M3 with phone P1
    """

    def _build(self) -> GraphStore:
        store = GraphStore()
        store.upsert_event(
            make_event(0, "c1", "m1"),
            entities(vpa="v1@ybl", phone="p1", device="d1"),
        )
        store.upsert_event(
            make_event(1, "c2", "m2"),
            entities(vpa="v2@ybl", phone="+919800000002", device="d1", email="e1@x.com"),
        )
        store.upsert_event(
            make_event(2, "c3", "m3"),
            entities(vpa="v2@ybl", phone="p1", device="d1"),
        )
        return store

    def test_exact_node_count(self) -> None:
        assert self._build().size == 12

    def test_feature_inputs_for_c1(self) -> None:
        stats = self._build().cluster_stats("c1")
        assert stats is not None
        assert stats.customers == 3
        assert stats.devices == 1
        assert stats.device_identity_ratio == 3.0
        assert stats.merchants == 3
        assert stats.max_cross_merchant_fanout == 3  # d1 touches m1, m2, m3
        assert stats.vpas == 2
        assert stats.phones == 2  # p1 and c2's phone
        assert stats.emails == 1


class TestClusterGuard:
    def test_unknown_customer_returns_empty(self) -> None:
        store = GraphStore()
        nodes, truncated = store.cluster("nobody")
        assert nodes == set() and truncated is False
        assert store.cluster_stats("nobody") is None

    def test_truncation_flag_on_huge_cluster(self) -> None:
        store = GraphStore()
        for i in range(50):
            store.upsert_event(
                make_event(i, f"c{i}", "m1"),
                entities(vpa=f"v{i}@ybl", phone=f"+9198000001{i:02d}", device="d_shared"),
            )
        nodes, truncated = store.cluster("c0", radius=2, max_nodes=10)
        assert truncated is True
        assert len(nodes) == 10


class TestPersistence:
    def test_graphml_round_trip_stable_hash(self, tmp_path: Path) -> None:
        store = GraphStore()
        store.upsert_event(make_event(0, "c1", "m1"), entities())
        store.upsert_event(
            make_event(1, "c2", "m2"),
            entities(vpa="v2@ybl", phone="+919800000002", device="dev_a"),
        )
        path = tmp_path / "graph" / "identity.graphml"
        store.save(path)
        reloaded = GraphStore.load(path)
        assert reloaded.content_hash() == store.content_hash()
        assert reloaded.cluster_stats("c1") == store.cluster_stats("c1")

    def test_replay_of_generated_events_is_deterministic(self) -> None:
        from sentinel.data.generate import generate_dataset

        events, _, _ = generate_dataset(seed=42)
        first = replay(events)
        second = replay(events)
        assert first.content_hash() == second.content_hash()
        assert first.size > 900  # every event contributes at least a customer node


class TestReplayFromDataset:
    def test_ring_produces_high_fanout_cluster(self) -> None:
        from sentinel.data.generate import generate_dataset

        events, labels, _ = generate_dataset(seed=42)
        fraud_ids = {label.event_id for label in labels if label.is_fraud}
        store = replay(events)
        ring_customer = next(event.customer_id for event in events if event.event_id in fraud_ids)
        stats = store.cluster_stats(ring_customer)
        assert stats is not None
        assert stats.max_cross_merchant_fanout >= 3
        assert stats.device_identity_ratio >= 2.0


def test_node_id_format() -> None:
    assert node_id(NodeType.DEVICE, "dev_x") == "device:dev_x"


def test_entities_of_normalizes_event_fields() -> None:
    event = make_event(0, "c1", "m1", vpa=" PRIYA@YBL ", phone="09812345678")
    normalized = entities_of(event)
    assert normalized.upi_vpa == "priya@ybl"
    assert normalized.phone == "+919812345678"
