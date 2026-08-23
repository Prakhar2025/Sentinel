"""Generate the console demo fixtures (static snapshot mode).

Builds a deterministic demo world from the seed-42 dataset and writes
JSON fixtures the console serves when NEXT_PUBLIC_DEMO=1, enabling a
zero-backend, zero-key, zero-cost static deployment (the clickable
link for cold outreach). Nothing here touches AWS.

Outputs console/src/demo/:
- queue.json        top 50 verdicts (same shape as GET /v1/verdicts)
- evaluation.json   metrics + latency (same shape as GET /v1/evaluation)
- scenario.json     the replay ring + a recorded, honestly-labeled feed
- clusters.json     cluster payloads for the top queue customers

Usage: python scripts/make_demo_fixtures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sentinel.data.generate import generate_dataset
from sentinel.graph import GraphStore, entities_of
from sentinel.service import _demo_scenario_cached, _event_row
from sentinel.store import AuditStore
from sentinel.verdict import VerdictEngine, verdict_to_json

OUT_DIR = Path(__file__).resolve().parents[1] / "console" / "src" / "demo"


def build_demo_store(db_path: Path, seed: int = 42) -> AuditStore:
    events, _, _ = generate_dataset(seed=seed)
    store = AuditStore(db_path)
    graph = GraphStore()
    engine = VerdictEngine()
    for event in sorted(events, key=lambda e: e.ts):
        if not store.insert_event(_event_row(event)):
            continue
        graph.upsert_event(event, entities_of(event))
        verdict = engine.score_event(event, graph)
        payload = verdict_to_json(verdict)
        store.insert_verdict(
            {
                "event_id": verdict.event_id,
                "score": verdict.score,
                "verdict": verdict.verdict,
                "reason_codes": payload["reason_codes"],
                "evidence": {
                    **payload["evidence"],
                    "customer_id": event.customer_id,
                    "merchant_id": event.merchant_id,
                },
                "features": payload["features"],
                "contributions": payload["contributions"],
                "model_version": payload["model_version"],
                "explanation_status": "PENDING",
            }
        )
    return store


def record_replay_feed(graph: GraphStore) -> list[dict[str, Any]]:
    """Replay the scenario ring into a fresh graph and record verdicts."""
    scenario = _demo_scenario_cached()
    engine = VerdictEngine()
    from sentinel.data.models import PaymentEvent

    feed: list[dict[str, Any]] = []
    fresh = GraphStore()
    for raw in sorted(scenario["events"], key=lambda e: e["ts"]):
        event = PaymentEvent.model_validate(raw)
        fresh.upsert_event(event, entities_of(event))
        verdict = engine.score_event(event, fresh)
        feed.append(
            {
                "index": len(feed),
                "merchant": event.merchant_id,
                "customer": event.customer_id,
                "amount_paise": event.amount_paise,
                "score": verdict.score,
                "verdict": verdict.verdict,
                "duplicate": False,
            }
        )
    del graph
    return feed


def main() -> int:
    import tempfile

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "demo.db"
        store = build_demo_store(db)

        queue = store.list_verdicts(limit=50)
        (OUT_DIR / "queue.json").write_text(json.dumps(queue, indent=1), encoding="utf-8")

        metrics_path = Path("evaluation/metrics.json")
        latency_path = Path("evaluation/latency.json")
        evaluation: dict[str, Any] = {}
        if metrics_path.exists():
            evaluation["metrics"] = json.loads(metrics_path.read_text(encoding="utf-8"))
        if latency_path.exists():
            evaluation["latency"] = json.loads(latency_path.read_text(encoding="utf-8"))
        (OUT_DIR / "evaluation.json").write_text(json.dumps(evaluation, indent=1), encoding="utf-8")

        scenario = _demo_scenario_cached()
        scenario["recorded_feed"] = record_replay_feed(GraphStore())
        (OUT_DIR / "scenario.json").write_text(json.dumps(scenario, indent=1), encoding="utf-8")

        clusters: dict[str, Any] = {}
        graph = _rebuild_graph(store)
        for row in queue[:8]:
            customer = (row.get("evidence") or {}).get("customer_id")
            if not customer:
                continue
            nodes, truncated = graph.cluster(customer)
            node_payloads = []
            for node in nodes:
                attrs = graph.raw_node_attrs(node) or {}
                kind, _, value = node.partition(":")
                if kind == "phone":
                    value = _mask_phone(value)
                node_payloads.append(
                    {"type": kind, "id": value, "taint": attrs.get("fraud_taint", 0.0)}
                )
            edges = [
                {"source": node, "target": target}
                for node in nodes
                for target in graph.successors(node)
            ]
            clusters[customer] = {
                "customer_id": customer,
                "nodes": node_payloads,
                "edges": edges,
                "truncated": truncated,
            }
        (OUT_DIR / "clusters.json").write_text(json.dumps(clusters, indent=1), encoding="utf-8")
        store.close()
    print(f"fixtures written to {OUT_DIR}")
    return 0


def _rebuild_graph(store: AuditStore) -> GraphStore:
    from datetime import datetime

    from sentinel.data.models import PaymentMethod, PriorOutcome

    graph = GraphStore()
    for row in store.all_events():
        from sentinel.data.models import PaymentEvent

        event = PaymentEvent(
            event_id=row["event_id"],
            merchant_id=row["merchant_id"],
            customer_id=row["customer_id"],
            amount_paise=row["amount_paise"],
            upi_vpa=row["upi_vpa"],
            phone=row["phone"],
            device_id=row["device_id"],
            email=row["email"],
            ip=row["ip"],
            ts=datetime.fromisoformat(row["ts"]),
            payment_method=PaymentMethod(row["payment_method"]),
            prior_outcome=PriorOutcome(row["prior_outcome"]) if row["prior_outcome"] else None,
        )
        graph.upsert_event(event, entities_of(event))
    return graph


def _mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 8:
        return "X" * len(phone)
    return f"+{digits[:4]}XXXX{digits[-4:]}"


if __name__ == "__main__":
    raise SystemExit(main())
