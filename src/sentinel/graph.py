"""Identity link graph (docs/03 and docs/04).

Typed node ids ("<type>:<value>") in a directed networkx graph with
aggregated edge attributes (first_seen, last_seen, event_count) and
node-level derived attributes recomputed on write:

- entity nodes (upi/phone/device/email): merchant_count, fraud_taint
- device nodes: linked_identity_count
- customer nodes: event_count, confirmed_fraud, fraud_taint

Taint propagation matches feature F3 in docs/05: a confirmed-fraud
outcome taints the source customer at 1.0 and spreads with 0.6^hops up
to TAINT_MAX_HOPS, across identity and customer nodes only (never
merchants). The traversal is bounded (doc 10, R6) so a pathological
cluster cannot loop or explode.

Local-first by design: in-process networkx with GraphML persistence,
behind a single class so a sharded Neo4j can replace it later without
touching callers (port/adapter, doc 03).
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import networkx as nx

from .data.models import PaymentEvent, PriorOutcome
from .normalize import (
    NormalizedEntities,
    normalize_device_id,
    normalize_email,
    normalize_phone,
    normalize_vpa,
)

TAINT_DISCOUNT = 0.6
TAINT_MAX_HOPS = 3
# Cluster radius for stats: customer -> shared entities -> neighboring
# customers -> their entities and merchants (3 hops reaches the evidence
# the F-features consume; 2 was measured too tight in the fixture test).
CLUSTER_RADIUS = 3
FRAUD_OUTCOMES = frozenset(
    {
        PriorOutcome.CHARGEBACK,
        PriorOutcome.REFUND_ABUSE,
        PriorOutcome.CONFIRMED_FRAUD,
    }
)


class NodeType(StrEnum):
    CUSTOMER = "customer"
    UPI = "upi"
    PHONE = "phone"
    DEVICE = "device"
    EMAIL = "email"
    MERCHANT = "merchant"


def node_id(node_type: NodeType, value: str) -> str:
    """Canonical typed node id."""
    return f"{node_type.value}:{value}"


@dataclass(slots=True, frozen=True)
class ClusterStats:
    """Aggregate counts over a customer's local cluster (feature inputs)."""

    customers: int
    devices: int
    vpas: int
    phones: int
    emails: int
    merchants: int
    device_identity_ratio: float
    max_cross_merchant_fanout: int


class GraphStore:
    """In-process identity link graph with derived attributes."""

    def __init__(self, graph: nx.DiGraph | None = None) -> None:
        self._graph = graph if graph is not None else nx.DiGraph()
        # Taint sources survive persistence via the confirmed_fraud node
        # attribute, so rebuild the set for graphs loaded from GraphML.
        self._taint_sources: set[str] = {
            node for node, attrs in self._graph.nodes(data=True) if attrs.get("confirmed_fraud")
        }

    # ------------------------------------------------------------------ write

    def upsert_event(self, event: PaymentEvent, entities: NormalizedEntities) -> None:
        """Add one event's nodes and edges, refresh derived attributes."""
        ts = event.ts.timestamp()
        customer = self._touch_node(NodeType.CUSTOMER, event.customer_id, ts)
        merchant = self._touch_node(NodeType.MERCHANT, event.merchant_id, ts)

        created_edges = self._link(customer, merchant, ts)
        entity_nodes: list[str] = []
        for node_type, value in (
            (NodeType.UPI, entities.upi_vpa),
            (NodeType.PHONE, entities.phone),
            (NodeType.DEVICE, entities.device_id),
            (NodeType.EMAIL, entities.email),
        ):
            if value is None:
                continue
            entity = self._touch_node(node_type, value, ts)
            created_edges |= self._link(customer, entity, ts)
            entity_nodes.append(entity)

        self._graph.nodes[customer]["event_count"] += 1
        self._graph.nodes[customer]["amount_sum"] += float(event.amount_paise)
        self._graph.nodes[customer]["amount_count"] += 1
        for entity in entity_nodes:
            self._recompute_entity(entity)

        if event.prior_outcome in FRAUD_OUTCOMES:
            self._graph.nodes[customer]["confirmed_fraud"] = True
            self._graph.nodes[customer]["fraud_taint"] = 1.0
            current_fraud_ts = self._graph.nodes[customer]["fraud_ts"]
            if current_fraud_ts == 0.0 or ts < current_fraud_ts:
                self._graph.nodes[customer]["fraud_ts"] = ts
            self._taint_sources.add(customer)
            self._spread_taint(customer)
        elif created_edges and self._taint_sources:
            # A new identity linked into an already-tainted neighborhood
            # must receive its taint even though the outcome predates it.
            for source in self._taint_sources:
                self._spread_taint(source)

    def _touch_node(self, node_type: NodeType, value: str, ts: float) -> str:
        node = node_id(node_type, value)
        if node not in self._graph:
            self._graph.add_node(
                node,
                type=node_type.value,
                first_seen=ts,
                last_seen=ts,
                event_count=0,
                merchant_count=0,
                linked_identity_count=0,
                fraud_taint=0.0,
                confirmed_fraud=False,
                fraud_ts=0.0,
                amount_sum=0.0,
                amount_count=0,
            )
        else:
            self._graph.nodes[node]["last_seen"] = max(self._graph.nodes[node]["last_seen"], ts)
        return node

    def _link(self, customer: str, other: str, ts: float) -> bool:
        """Link customer to another node; True when a new edge was created."""
        if self._graph.has_edge(customer, other):
            attrs = self._graph.edges[customer, other]
            attrs["event_count"] += 1
            attrs["last_seen"] = max(attrs["last_seen"], ts)
            return False
        self._graph.add_edge(customer, other, first_seen=ts, last_seen=ts, event_count=1)
        return True

    def _recompute_entity(self, entity: str) -> None:
        """Refresh derived attributes from the entity's current neighborhood."""
        attrs = self._graph.nodes[entity]
        linked = {
            neighbor
            for neighbor in self._graph.neighbors(entity)
            if self._graph.nodes[neighbor]["type"] == NodeType.CUSTOMER.value
        } | {
            source
            for source in self._graph.predecessors(entity)
            if self._graph.nodes[source]["type"] == NodeType.CUSTOMER.value
        }
        merchants: set[str] = set()
        for customer in linked:
            for neighbor in self._graph.neighbors(customer):
                if self._graph.nodes[neighbor]["type"] == NodeType.MERCHANT.value:
                    merchants.add(neighbor)
        attrs["linked_identity_count"] = len(linked)
        attrs["merchant_count"] = len(merchants)

    def _spread_taint(self, source: str) -> None:
        """Bounded BFS taint spread: 0.6^hops, identity nodes only."""
        undirected = self._graph.to_undirected(as_view=True)
        visited: set[str] = {source}
        frontier: deque[tuple[str, int]] = deque([(source, 0)])
        while frontier:
            node, hops = frontier.popleft()
            if hops >= TAINT_MAX_HOPS:
                continue
            for neighbor in undirected.neighbors(node):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                if self._graph.nodes[neighbor]["type"] == NodeType.MERCHANT.value:
                    continue
                taint = round(TAINT_DISCOUNT ** (hops + 1), 6)
                current = self._graph.nodes[neighbor]["fraud_taint"]
                if taint > current:
                    self._graph.nodes[neighbor]["fraud_taint"] = taint
                frontier.append((neighbor, hops + 1))

    # ------------------------------------------------------------------- read

    def cluster(
        self, customer_id: str, radius: int = CLUSTER_RADIUS, max_nodes: int = 200
    ) -> tuple[set[str], bool]:
        """Local cluster (radius-bounded BFS); returns (nodes, truncated).

        Merchant nodes are included as leaves but never traversed
        through: a large merchant is adjacent to hundreds of unrelated
        clean customers, and walking across them dilutes every cluster
        (measured: ring clusters lost their identity ratio and cluster
        extraction crawled). Identity linkage flows through entities
        (device/phone/vpa/email) only, which is exactly the relational
        signal the detector exists to use.
        """
        start = node_id(NodeType.CUSTOMER, customer_id)
        if start not in self._graph:
            return set(), False
        undirected = self._graph.to_undirected(as_view=True)
        visited: set[str] = {start}
        frontier: deque[tuple[str, int]] = deque([(start, 0)])
        while frontier:
            node, hops = frontier.popleft()
            if hops >= radius:
                continue
            for neighbor in undirected.neighbors(node):
                if len(visited) >= max_nodes:
                    return visited, True
                if neighbor not in visited:
                    visited.add(neighbor)
                    if self._graph.nodes[neighbor]["type"] != NodeType.MERCHANT.value:
                        frontier.append((neighbor, hops + 1))
        return visited, False

    def cluster_stats(self, customer_id: str) -> ClusterStats | None:
        """Aggregate counts over the customer's radius-2 cluster."""
        nodes, _ = self.cluster(customer_id, radius=CLUSTER_RADIUS)
        if not nodes:
            return None
        counts = {node_type.value: 0 for node_type in NodeType}
        for node in nodes:
            counts[self._graph.nodes[node]["type"]] += 1
        customers = counts[NodeType.CUSTOMER.value]
        devices = counts[NodeType.DEVICE.value]

        fanout = 0
        for node in nodes:
            node_type = self._graph.nodes[node]["type"]
            if node_type in {NodeType.UPI.value, NodeType.PHONE.value, NodeType.DEVICE.value}:
                fanout = max(fanout, int(self._graph.nodes[node]["merchant_count"]))
        ratio = round(customers / devices, 3) if devices else 0.0
        return ClusterStats(
            customers=customers,
            devices=devices,
            vpas=counts[NodeType.UPI.value],
            phones=counts[NodeType.PHONE.value],
            emails=counts[NodeType.EMAIL.value],
            merchants=counts[NodeType.MERCHANT.value],
            device_identity_ratio=ratio,
            max_cross_merchant_fanout=fanout,
        )

    def node_attrs(
        self, node_type: NodeType, value: str
    ) -> dict[str, float | int | bool | str] | None:
        """Read a node's attributes (evidence and API views)."""
        node = node_id(node_type, value)
        if node not in self._graph:
            return None
        return dict(self._graph.nodes[node])

    def raw_node_attrs(self, node: str) -> dict[str, float | int | bool | str] | None:
        """Read attributes of a node by its canonical id string."""
        if node not in self._graph:
            return None
        return dict(self._graph.nodes[node])

    def successors(self, node: str) -> list[str]:
        """Out-neighbors of a node by canonical id."""
        return list(self._graph.successors(node)) if node in self._graph else []

    def edge_attrs(self, source: str, target: str) -> dict[str, float | int] | None:
        """Attributes of the directed edge between two canonical node ids."""
        if self._graph.has_edge(source, target):
            return dict(self._graph.edges[source, target])
        return None

    def has_node(self, node: str) -> bool:
        """Whether a canonical node id exists."""
        return node in self._graph

    def undirected_neighbors(self, node: str) -> list[str]:
        """Neighbors ignoring edge direction (identity traversal views)."""
        if node not in self._graph:
            return []
        return list(self._graph.to_undirected(as_view=True).neighbors(node))

    @property
    def size(self) -> int:
        """Total node count."""
        return len(self._graph)

    # ---------------------------------------------------------- persistence

    def save(self, path: Path) -> None:
        """Persist to GraphML; parent directories are created as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(self._graph, path)

    @classmethod
    def load(cls, path: Path) -> GraphStore:
        """Load from GraphML written by save()."""
        return cls(nx.read_graphml(path))

    def content_hash(self) -> str:
        """Stable digest of nodes and edges, independent of insertion order."""
        payload = {
            "nodes": [
                [node, dict(sorted(attrs.items()))]
                for node, attrs in sorted(self._graph.nodes(data=True))
            ],
            "edges": [
                [source, target, dict(sorted(attrs.items()))]
                for source, target, attrs in sorted(self._graph.edges(data=True))
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def entities_of(event: PaymentEvent) -> NormalizedEntities:
    """Normalize an event's identity fields for graph insertion."""
    return NormalizedEntities(
        upi_vpa=normalize_vpa(event.upi_vpa),
        phone=normalize_phone(event.phone),
        device_id=normalize_device_id(event.device_id),
        email=normalize_email(event.email),
        ip=None,
    )


def events_from_jsonl(path: Path) -> list[PaymentEvent]:
    """Load serving-shaped events from a generated events.jsonl file."""
    return [
        PaymentEvent.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def replay(events: list[PaymentEvent]) -> GraphStore:
    """Build a graph by replaying events in chronological order."""
    store = GraphStore()
    for event in sorted(events, key=lambda e: e.ts):
        store.upsert_event(event, entities_of(event))
    return store


__all__ = [
    "FRAUD_OUTCOMES",
    "TAINT_DISCOUNT",
    "TAINT_MAX_HOPS",
    "ClusterStats",
    "GraphStore",
    "NodeType",
    "entities_of",
    "events_from_jsonl",
    "node_id",
    "replay",
]
