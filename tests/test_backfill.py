"""Tests for the explanation backfill pipeline (no network)."""

from __future__ import annotations

from pathlib import Path

from sentinel.backfill import backfill, rebuild_store
from sentinel.data.generate import generate_dataset
from sentinel.explain import ExplanationResult
from sentinel.graph import GraphStore, entities_of
from sentinel.store import AuditStore
from sentinel.verdict import VerdictEngine, verdict_to_json

VALID = '{"summary":"ok","risk_factors":["a"],"recommended_action":"review"}'


def seed_store(db_path: Path, seed: int = 42, n_events: int = 30) -> AuditStore:
    """Small deterministic store with pending verdicts."""
    events, _, _ = generate_dataset(seed=seed)
    store = AuditStore(db_path)
    from sentinel.service import _event_row

    graph = GraphStore()
    engine = VerdictEngine()
    for event in sorted(events, key=lambda e: e.ts)[:n_events]:
        store.insert_event(_event_row(event))
        graph.upsert_event(event, entities_of(event))
        verdict = engine.score_event(event, graph)
        payload = verdict_to_json(verdict)
        store.insert_verdict(
            {
                "event_id": verdict.event_id,
                "score": verdict.score,
                "verdict": verdict.verdict,
                "reason_codes": payload["reason_codes"],
                "evidence": payload["evidence"],
                "features": payload["features"],
                "contributions": payload["contributions"],
                "model_version": payload["model_version"],
                "explanation_status": "PENDING",
            }
        )
    return store


class ScriptedService:
    """Deterministic stand-in for ExplanationService."""

    def __init__(self, status: str = "DONE") -> None:
        self.status = status
        self.explained = 0

    def explain(self, payload) -> ExplanationResult:
        self.explained += 1
        return ExplanationResult(
            status=self.status,
            model_used="model-a" if self.status == "DONE" else None,
            narrative=VALID if self.status == "DONE" else None,
            calls_made=1,
            latency_ms=10,
        )


def test_backfill_fills_pending_and_updates_status(tmp_path: Path) -> None:
    store = seed_store(tmp_path / "demo.db")
    service = ScriptedService("DONE")
    counts = backfill(store, service, limit=10)
    assert counts["DONE"] == 10
    remaining = store.pending_explanations(limit=100)
    assert len(remaining) == 20  # 30 seeded, 10 explained
    explained = [v for v in store.list_verdicts(limit=100) if v["explanation_status"] == "DONE"]
    assert len(explained) == 10
    assert all(v["explanation"] for v in explained)


def test_backfill_skipped_marks_status(tmp_path: Path) -> None:
    store = seed_store(tmp_path / "demo.db")
    counts = backfill(store, ScriptedService("SKIPPED"), limit=5)
    assert counts["SKIPPED"] == 5
    skipped = [v for v in store.list_verdicts(limit=100) if v["explanation_status"] == "SKIPPED"]
    assert len(skipped) == 5


def test_backfill_respects_limit_and_priority(tmp_path: Path) -> None:
    store = seed_store(tmp_path / "demo.db")
    pending = store.pending_explanations(limit=3)
    scores = [row["score"] for row in pending]
    assert scores == sorted(scores, reverse=True)  # highest risk first


def test_rebuild_store_is_deterministic_and_clean(tmp_path: Path) -> None:
    db = tmp_path / "rebuild.db"
    first = rebuild_store(db, seed=42)
    reader = AuditStore(db)
    pending_first = len(reader.pending_explanations(limit=10_000))
    reader.close()  # Windows: the pool holds the file open until disposed
    second = rebuild_store(db, seed=42)
    assert first == second
    assert pending_first == first
    second_reader = AuditStore(db)
    assert len(second_reader.pending_explanations(limit=10_000)) == first
    second_reader.close()
