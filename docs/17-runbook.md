# 17 — Operations Runbook

Written for the on-call engineer at 3 AM. Every procedure is something the build actually exercised.

## Health model

- `/healthz` liveness: process is up.
- `/readyz` readiness: store reachable AND graph populated (node count reported). 503 means do-not-route.
- `/metrics` (standard key): the numbers below assume Prometheus scraping.

## Golden signals and what to do

| Signal (from /metrics) | Healthy look | If wrong |
|------------------------|--------------|----------|
| `sentinel_events_total` rate | matches expected traffic | flat = upstream or auth break; check spool dir growth |
| `sentinel_degraded_total` rate | 0 | nonzero = degradation ladder engaged; identify leg below |
| `sentinel_score_mean_recent` / `sentinel_score_drift` | drift near 0 after warm-up | sustained drift > 15 = population shift or attack wave; page risk engineer, do not retune thresholds at 3 AM |
| `sentinel_event_latency_seconds` p99 | < 100 ms local | growing tails = contention; scale workers (RFC section 3), do not add threads |
| explanation `SKIPPED` share (store query) | < 5% of flagged | Bedrock throttling; queue drains async, verify fallback chain in logs |

## Degradation ladder incidents

**LLM down (R1/R2):** verdicts unaffected; narratives SKIPPED. Action: none at night; verify Bedrock status in the morning; backfill restores narratives retroactively (`make backfill`).

**Store down (R4):** events spool to `data/spool/ingest.spool`; API returns 503 STORE_UNAVAILABLE with a REVIEW-shaped payload; nothing is lost. Action: restore the database, then replay the spool through `POST /v1/events:batch` (idempotent; duplicates return prior verdicts), then verify `readyz`.

**Graph empty after restart (R3):** the service rebuilds the graph from stored events on boot; if `readyz` shows 0 nodes with a populated store, check store connectivity first; the rebuild is the recovery, not the incident.

**Poison event (R6):** clusters are capped (200 nodes) and flagged `truncated`; scoring degrades to REVIEW for that event only. Action: quarantine by event_id in the store; file a what-broke entry.

## Deploy and rollback

- Deploy: full suite green (CI), then `docker compose up --build -d` (or service equivalent). Readiness gates routing.
- Rollback: redeploy the previous image tag; the graph rebuilds from the store on boot; schema changes are additive (the challenger column migration is the template: ALTER TABLE ADD COLUMN, safe both directions).
- Model changes: weights are versioned in `metrics.json`/`model_config.json`; rollback is pointing the engine at the previous locked config. Never hot-edit weights on a live verdict path.

## Morning-after checklist

1. `git log --oneline` since last shift; read any what-broke.md additions.
2. Spool directory empty; `/readyz` green on all replicas.
3. `sentinel_degraded_total` flat over the shift window.
4. Cost log (`evaluation/llm_cost.jsonl`) spend within budget.
5. Shadow challenger agreement (evaluation report) within 95-100%; investigate any drift in disagreement structure before it drifts in size.
