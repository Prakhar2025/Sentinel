"""Verdict engine (docs/03, docs/05, docs/06).

Combines feature extraction, scoring, thresholds, reason codes, and
evidence into one bounded decision. Degradation is explicit: any failure
in the deterministic path yields REVIEW with SYS_DEGRADED, never a
crash, never a silent auto-block (doc 10 degradation ladder).

Verdicts are recommendations only: BLOCK_REC explicitly means
"block recommended, human decides".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .data.models import PaymentEvent
from .features import FeatureVector, extract_features
from .graph import CLUSTER_RADIUS, GraphStore, NodeType
from .scorer import (
    DEFAULT_WEIGHTS,
    MODEL_VERSION,
    ScoreResult,
    reason_codes,
    score_features,
)

DEFAULT_REVIEW_THRESHOLD = 35
DEFAULT_BLOCK_THRESHOLD = 70


@dataclass(slots=True)
class Verdict:
    """One scored decision with its full audit payload."""

    event_id: str
    score: int
    verdict: str  # ALLOW | REVIEW | BLOCK_REC
    reason_codes: list[str] = field(default_factory=list)
    features: dict[str, float | int] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    model_version: str = MODEL_VERSION
    degraded: bool = False


def _verdict_for_score(score: int, review_at: int, block_at: int) -> str:
    if score >= block_at:
        return "BLOCK_REC"
    if score >= review_at:
        return "REVIEW"
    return "ALLOW"


class VerdictEngine:
    """Deterministic scoring pipeline over the identity graph."""

    def __init__(
        self,
        weights: dict[str, int] | None = None,
        review_threshold: int = DEFAULT_REVIEW_THRESHOLD,
        block_threshold: int = DEFAULT_BLOCK_THRESHOLD,
        model_version: str = MODEL_VERSION,
    ) -> None:
        self._weights = weights if weights is not None else DEFAULT_WEIGHTS
        self._review_at = review_threshold
        self._block_at = block_threshold
        self._model_version = model_version

    @property
    def thresholds(self) -> dict[str, int]:
        return {"review": self._review_at, "block": self._block_at}

    def score_event(self, event: PaymentEvent, store: GraphStore) -> Verdict:
        """Full pipeline for one event; failure degrades, never raises."""
        try:
            features = extract_features(event, store)
            if features is None:
                return self._degraded(event, "customer not in graph")
            result = score_features(features, self._weights)
            codes = reason_codes(features)
            return Verdict(
                event_id=event.event_id,
                score=result.score,
                verdict=_verdict_for_score(result.score, self._review_at, self._block_at),
                reason_codes=codes if codes else [],
                features=features.as_dict(),
                contributions=result.contributions,
                evidence=build_evidence(event, store, features),
                model_version=self._model_version,
            )
        except Exception as exc:  # bounded by design (doc 03 degradation ladder)
            return self._degraded(event, f"{type(exc).__name__}: {exc}"[:200])

    def _degraded(self, event: PaymentEvent, note: str) -> Verdict:
        return Verdict(
            event_id=event.event_id,
            score=0,
            verdict="REVIEW",
            reason_codes=["SYS_DEGRADED"],
            evidence={"degradation_note": note},
            model_version=self._model_version,
            degraded=True,
        )


def build_evidence(
    event: PaymentEvent, store: GraphStore, features: FeatureVector
) -> dict[str, Any]:
    """Human/analyst-facing evidence bundle for one verdict (doc 06 shape)."""
    nodes, truncated = store.cluster(event.customer_id, radius=CLUSTER_RADIUS)
    merchants: list[str] = []
    devices: list[dict[str, Any]] = []
    customers = 0
    for node in nodes:
        attrs = store.raw_node_attrs(node)
        if attrs is None:
            continue
        node_type = attrs.get("type")
        if node_type == NodeType.MERCHANT.value:
            merchants.append(node.split(":", 1)[1])
        elif node_type == NodeType.DEVICE.value:
            devices.append(
                {
                    "device_id": node.split(":", 1)[1],
                    "linked_identities": int(attrs.get("linked_identity_count", 0)),
                    "merchant_count": int(attrs.get("merchant_count", 0)),
                }
            )
        elif node_type == NodeType.CUSTOMER.value:
            customers += 1
    devices.sort(key=lambda d: (-d["linked_identities"], d["device_id"]))
    return {
        "linked_merchants": sorted(merchants)[:8],
        "shared_devices": devices[:3],
        "taint": features.taint,
        "taint_path": taint_path(event.customer_id, store),
        "cluster": {
            "customers": customers,
            "truncated": truncated,
        },
    }


def taint_path(customer_id: str, store: GraphStore) -> list[str]:
    """Shortest identity path from the customer to a confirmed-fraud node.

    Bounded at TAINT_MAX_HOPS; empty when the cluster is untainted.
    """
    from collections import deque

    from .graph import TAINT_MAX_HOPS

    start = f"{NodeType.CUSTOMER.value}:{customer_id}"
    if not store.has_node(start):
        return []
    previous: dict[str, str | None] = {start: None}
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    while queue:
        node, hops = queue.popleft()
        attrs = store.raw_node_attrs(node)
        if attrs is not None and attrs.get("confirmed_fraud") and node != start:
            path: list[str] = []
            step: str | None = node
            while step is not None:
                path.append(step.split(":", 1)[1])
                step = previous.get(step)
            return list(reversed(path))
        if hops >= TAINT_MAX_HOPS:
            continue
        for neighbor in store.undirected_neighbors(node):
            if neighbor in previous:
                continue
            neighbor_attrs = store.raw_node_attrs(neighbor)
            if neighbor_attrs is None or neighbor_attrs.get("type") == NodeType.MERCHANT.value:
                continue
            previous[neighbor] = node
            queue.append((neighbor, hops + 1))
    return []


def verdict_to_json(verdict: Verdict) -> dict[str, Any]:
    """Serializable verdict payload (audit trail; Phase 4 persists this)."""
    return {
        "event_id": verdict.event_id,
        "score": verdict.score,
        "verdict": verdict.verdict,
        "reason_codes": verdict.reason_codes,
        "features": verdict.features,
        "contributions": verdict.contributions,
        "evidence": verdict.evidence,
        "model_version": verdict.model_version,
        "degraded": verdict.degraded,
    }


def score_result_from_features(features: FeatureVector) -> ScoreResult:
    """Convenience wrapper used by the evaluation harness."""
    return score_features(features)
