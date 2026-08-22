"""Graph features F1-F7 (docs/05, the ring fingerprint).

All features are computed from the identity graph state at the moment of
the event (online replay: only past events are in the graph), so every
score is explainable by the evidence that existed at decision time.

Raw feature values are kept alongside their normalized [0,1] forms; the
normalization transforms are published constants, part of the model
version, and identical at calibration and serving time.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .data.models import PaymentEvent
from .graph import CLUSTER_RADIUS, GraphStore, NodeType, node_id

VELOCITY_WINDOW_SECONDS = 72 * 3600
BURN_ROTATE_WINDOW_SECONDS = 48 * 3600
NEW_IDENTITY_WINDOW_SECONDS = 7 * 24 * 3600
RING_AMOUNT_BAND_PAISE = (50_000, 200_000)  # 500 - 2,000 INR


@dataclass(slots=True, frozen=True)
class FeatureVector:
    """Raw and normalized ring features for one event."""

    # raw values (audit + evidence)
    device_identity_ratio: float
    cross_merchant_fanout: int
    taint: float
    velocity_merchants_72h: int
    burn_rotate: int  # 0 or 1
    amount_band_hit: float  # 0 / 0.5 / 1
    new_identity_fraction: float

    # normalized [0,1] values consumed by the scorer
    n_f1: float
    n_f2: float
    n_f3: float
    n_f4: float
    n_f5: float
    n_f6: float
    n_f7: float

    def normalized(self) -> list[float]:
        return [self.n_f1, self.n_f2, self.n_f3, self.n_f4, self.n_f5, self.n_f6, self.n_f7]

    def raw(self) -> dict[str, float | int]:
        return {
            "device_identity_ratio": self.device_identity_ratio,
            "cross_merchant_fanout": self.cross_merchant_fanout,
            "taint": self.taint,
            "velocity_merchants_72h": self.velocity_merchants_72h,
            "burn_rotate": self.burn_rotate,
            "amount_band_hit": self.amount_band_hit,
            "new_identity_fraction": self.new_identity_fraction,
        }

    def as_dict(self) -> dict[str, float | int]:
        return {
            **self.raw(),
            **{f"n_f{i}": value for i, value in enumerate(self.normalized(), start=1)},
        }


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def extract_features(event: PaymentEvent, store: GraphStore) -> FeatureVector | None:
    """Compute the ring fingerprint for one event from current graph state.

    Returns None when the customer is unknown (degradation path).
    """
    stats = store.cluster_stats(event.customer_id)
    if stats is None:
        return None
    nodes, _ = store.cluster(event.customer_id, radius=CLUSTER_RADIUS)
    ts = event.ts.timestamp()

    # F1: identities per device in the cluster.
    f1 = stats.device_identity_ratio

    # F2: max distinct merchants reached by any single entity.
    f2 = stats.max_cross_merchant_fanout

    # F3: strongest taint anywhere in the cluster.
    f3 = 0.0
    for node in nodes:
        attrs = store.raw_node_attrs(node)
        if attrs is None:
            continue
        f3 = max(f3, float(attrs.get("fraud_taint", 0.0)))

    # F4: distinct merchants touched by cluster customers in the last 72h.
    window_start = ts - VELOCITY_WINDOW_SECONDS
    recent_merchants: set[str] = set()
    for node in nodes:
        attrs = store.raw_node_attrs(node)
        if attrs is None or attrs.get("type") != NodeType.CUSTOMER.value:
            continue
        for neighbor in store.successors(node):
            neighbor_attrs = store.raw_node_attrs(neighbor)
            if neighbor_attrs is None or neighbor_attrs.get("type") != NodeType.MERCHANT.value:
                continue
            edge = store.edge_attrs(node, neighbor)
            if edge is not None and float(edge["last_seen"]) >= window_start:
                recent_merchants.add(neighbor)
    f4 = len(recent_merchants)

    # F5: burn-and-rotate: a VPA abandoned within 48h of a fraud outcome
    # on this cluster, with a replacement VPA appearing afterwards.
    f5 = 0
    fraud_customers = [
        node
        for node in nodes
        if (attrs := store.raw_node_attrs(node)) is not None and attrs.get("confirmed_fraud")
    ]
    if fraud_customers:
        vpa_attrs_list = [
            attrs
            for node in nodes
            if (attrs := store.raw_node_attrs(node)) is not None
            and attrs.get("type") == NodeType.UPI.value
        ]
        for fraud_customer in fraud_customers:
            fraud_attrs = store.raw_node_attrs(fraud_customer)
            if fraud_attrs is None:
                continue
            fraud_ts = float(fraud_attrs.get("fraud_ts", 0.0))
            if fraud_ts <= 0:
                continue
            abandoned = False
            for vpa in store.successors(fraud_customer):
                vpa_attrs = store.raw_node_attrs(vpa)
                if vpa_attrs is None or vpa_attrs.get("type") != NodeType.UPI.value:
                    continue
                edge = store.edge_attrs(fraud_customer, vpa)
                if edge is None:
                    continue
                last_use = float(edge["last_seen"])
                if fraud_ts <= last_use <= fraud_ts + BURN_ROTATE_WINDOW_SECONDS:
                    abandoned = True
            replaced = any(float(attrs["first_seen"]) > fraud_ts for attrs in vpa_attrs_list)
            if abandoned and replaced:
                f5 = 1

    # F6: event amount and cluster mean amount vs the ring-typical band.
    band_lo, band_hi = RING_AMOUNT_BAND_PAISE
    event_hit = band_lo <= event.amount_paise <= band_hi
    cluster_amounts = [
        (float(attrs["amount_sum"]) / int(attrs["amount_count"]))
        for node in nodes
        if (attrs := store.raw_node_attrs(node)) is not None
        and attrs.get("type") == NodeType.CUSTOMER.value
        and int(attrs.get("amount_count", 0)) > 0
    ]
    mean_hit = bool(cluster_amounts) and all(band_lo <= m <= band_hi for m in cluster_amounts)
    f6 = 1.0 if (event_hit and mean_hit) else (0.5 if (event_hit or mean_hit) else 0.0)

    # F7: fraction of cluster customers created within the last 7 days.
    customer_attrs = [
        attrs
        for node in nodes
        if (attrs := store.raw_node_attrs(node)) is not None
        and attrs.get("type") == NodeType.CUSTOMER.value
    ]
    fresh = [
        attrs
        for attrs in customer_attrs
        if ts - float(attrs["first_seen"]) <= NEW_IDENTITY_WINDOW_SECONDS
    ]
    f7 = (len(fresh) / len(customer_attrs)) if customer_attrs else 0.0

    return FeatureVector(
        device_identity_ratio=f1,
        cross_merchant_fanout=f2,
        taint=round(f3, 6),
        velocity_merchants_72h=f4,
        burn_rotate=f5,
        amount_band_hit=f6,
        new_identity_fraction=round(f7, 6),
        n_f1=round(_clip(f1 / 6.0), 6),
        n_f2=round(_clip((f2 - 2) / 4.0), 6),
        n_f3=round(_clip(f3), 6),
        n_f4=round(_clip(f4 / 5.0), 6),
        n_f5=float(f5),
        n_f6=f6,
        n_f7=round(_clip(f7), 6),
    )


def feature_vector_from_raw(raw: dict[str, float | int]) -> FeatureVector:
    """Rebuild a feature vector from raw values (calibration caching)."""
    f1 = float(raw["device_identity_ratio"])
    f2 = int(raw["cross_merchant_fanout"])
    f3 = float(raw["taint"])
    f4 = int(raw["velocity_merchants_72h"])
    f5 = int(raw["burn_rotate"])
    f6 = float(raw["amount_band_hit"])
    f7 = float(raw["new_identity_fraction"])
    return FeatureVector(
        device_identity_ratio=f1,
        cross_merchant_fanout=f2,
        taint=f3,
        velocity_merchants_72h=f4,
        burn_rotate=f5,
        amount_band_hit=f6,
        new_identity_fraction=f7,
        n_f1=round(_clip(f1 / 6.0), 6),
        n_f2=round(_clip((f2 - 2) / 4.0), 6),
        n_f3=round(_clip(f3), 6),
        n_f4=round(_clip(f4 / 5.0), 6),
        n_f5=float(f5),
        n_f6=f6,
        n_f7=round(_clip(f7), 6),
    )


def cluster_customer_nodes(store: GraphStore, customer_id: str) -> list[str]:
    """Customer nodes in a customer's cluster (evidence helper)."""
    nodes, _ = store.cluster(customer_id, radius=CLUSTER_RADIUS)
    return [
        node
        for node in nodes
        if (attrs := store.raw_node_attrs(node)) is not None
        and attrs.get("type") == NodeType.CUSTOMER.value
    ]


def customer_node_id(customer_id: str) -> str:
    """Canonical node id for a customer."""
    return node_id(NodeType.CUSTOMER, customer_id)


def features_to_dict(vector: FeatureVector) -> dict[str, float | int]:
    """Serializable form (audit trail and metrics payloads)."""
    return asdict(vector)
