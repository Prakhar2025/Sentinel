"""Explanation backfill (docs/03: async, never on the verdict hot path).

Fills explanation_status=PENDING verdicts concurrently (Phase 0 measured
a 14x latency spread across models; serial backfill would crawl). The
LLM calls run in a bounded thread pool, but store writes happen serially
in the calling thread: SQLite allows one writer at a time, and losing a
narrative to "database is locked" is worse than a few milliseconds of
sequencing.

CLI: python -m sentinel.backfill [--limit 20] [--db evaluation/demo.db]
     [--rebuild --seed 42]   # regenerate the dataset into the store first
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .config import get_settings
from .explain import CostLog, ExplanationService
from .llm import BedrockClient
from .service import _event_row
from .store import AuditStore
from .verdict import VerdictEngine, verdict_to_json

MAX_WORKERS = 8


def build_service(settings: Any, cost_log: CostLog) -> ExplanationService:
    """Wire the fallback chain with the real Bedrock client."""
    client = BedrockClient(
        region=settings.aws_region,
        timeout_seconds=settings.bedrock_timeout_seconds,
    )
    chain = [
        settings.explanation_model,
        settings.fallback1_explanation_model,
        settings.fallback2_explanation_model,
    ]
    return ExplanationService(
        converse=client.converse,
        chain=chain,
        max_tokens=settings.explanation_max_tokens,
        on_cost=cost_log,
    )


def rebuild_store(db_path: Path, seed: int) -> int:
    """Regenerate the dataset and ingest it (no LLM) into a clean store."""
    from .data.generate import generate_dataset
    from .graph import GraphStore, entities_of

    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(db_path) + suffix)
        if candidate.exists():
            candidate.unlink()

    events, _, _ = generate_dataset(seed=seed)
    store = AuditStore(db_path)
    graph = GraphStore()
    engine = VerdictEngine()
    count = 0
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
                "evidence": {**payload["evidence"], "customer_id": event.customer_id},
                "features": payload["features"],
                "contributions": payload["contributions"],
                "model_version": payload["model_version"],
                "explanation_status": "PENDING",
            }
        )
        count += 1
    store.close()  # Windows: release the file handle before any later rebuild
    return count


def backfill(
    store: AuditStore,
    service: ExplanationService,
    limit: int,
    max_workers: int = MAX_WORKERS,
) -> dict[str, int]:
    """Explain pending verdicts concurrently; returns status counts."""
    pending = store.pending_explanations(limit)

    def explain_one(verdict_row: dict[str, Any]) -> tuple[str, str, str]:
        result = service.explain(verdict_row)
        return verdict_row["event_id"], result.status, result.narrative or ""

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        outcomes: list[tuple[str, str, str]] = list(pool.map(explain_one, pending))

    counts = {"DONE": 0, "SKIPPED": 0}
    for event_id, status, narrative in outcomes:  # serial writes, one writer
        if status == "DONE":
            store.set_explanation(event_id, narrative, "DONE")
        else:
            store.set_explanation(event_id, "", "SKIPPED")
        counts[status] = counts.get(status, 0) + 1
    return counts


def main(argv: list[str] | None = None) -> int:
    """CLI entry with explicit, pre-announced spend bounds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("evaluation/demo.db"))
    parser.add_argument("--limit", type=int, default=20, help="max verdicts to explain")
    parser.add_argument("--rebuild", action="store_true", help="regenerate dataset first")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    if args.rebuild:
        ingested = rebuild_store(args.db, args.seed)
        print(f"rebuilt store with {ingested} verdicts (seed {args.seed})")

    settings = get_settings()
    cost_log = CostLog(Path("evaluation/llm_cost.jsonl"))
    store = AuditStore(args.db)
    service = build_service(settings, cost_log)

    print(f"explaining up to {args.limit} pending verdicts (bounded run)")
    counts = backfill(store, service, limit=args.limit)
    print(json.dumps(counts))
    print(cost_log.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
