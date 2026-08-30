# 15 — Productionization RFC

Status: proposed (v2) | Owner: platform | Everything below derives from *measured* numbers in this repo, not estimates.

## 1. Measured baseline (this repository, reference laptop)

From `make loadtest` (docs + evaluation/loadtest.json):

| Quantity | Measured | Notes |
|----------|----------|-------|
| Sequential ingest+score throughput | 178 events/s | single Python process, full pipeline incl. graph writes |
| Scoring latency | p50 4.8 ms / p95 15.2 ms | includes upsert + features + verdict |
| 4-thread arrival probe | 183 events/s (flat), p99 346 ms | GIL + single-writer lock: threads do not scale a CPU-bound pipeline |
| Held-out evaluation | P 0.833 / R 0.882 | unchanged under load by design: scoring is deterministic |
| LLM narrative | ~7 s, ~$0.0003/event | async, off the hot path; ~5% of events flagged for narrative in practice |

## 2. Target envelope

UPI runs ~8,000 TPS average (NPCI Jan 2026: 21.7B transactions/month) with peaks well above 10k. A Razorpay-scale deployment target for this subsystem: **10,000 events/s sustained, p99 scoring < 100 ms, zero data loss on node failure.**

## 3. The gap, quantified

10,000 / 178 ≈ **57x**. Three multipliers close it; none of them is "rewrite in a faster language" (which buys 5-20x at best and costs the audit story).

1. **Worker processes (57 / ~4 = ~15x realistic):** each worker is an independent process (no GIL sharing) at ~178 events/s and ~4 cores of headroom per node. **16-24 workers across 4-6 nodes** delivers the target with N+1 redundancy. The measurement that threads *don't* help (flat 183/s with exploding tails) is precisely why process sharding is the design.
2. **Sharded graph (~5x effective):** partition entities by hash(device_id) with customer-owned routing; cross-shard edges (a device and phone sharing no hash key) resolve through a async join tier. Roughly 80% of cluster reads stay local at 64 shards by the benign-overlap statistics of our own generator.
3. **Streaming ingest (unbounded):** Kinesis/Flink replaces synchronous POST at the edge; backpressure becomes queue depth, a monitored metric instead of a latency cliff.

## 4. Component plan

| Component | Local build | Production shape |
|-----------|-------------|------------------|
| Ingest | FastAPI POST | Kinesis shards + Flink operators (extraction, feature windows) |
| Graph | networkx in-process | Sharded graph service; Neo4j-compatible API per shard; our GraphStore port/adapter is the seam (proven by the Postgres swap) |
| Scoring | deterministic ensemble | Unchanged (that is the point); weights served from a config service with versioned rollout |
| Challenger | shadow GBDT | Shadow at 100% sample; promotion per docs/14 criteria, automated across seeds |
| LLM narrative | Bedrock, bounded backfill | Queue with concurrency caps; only REVIEW/BLOCK bands (~5-8% of traffic); worst case 10k × 6% ≈ 600 narratives/s needs ~600 concurrent calls at 1s each — cap the queue, degrade to SKIPPED, never block |
| Store | SQLite WAL | Postgres (proven in CI) with partitioned verdicts; audit log to immutable object storage |
| AuthN/Z | API key + JWT | OAuth2 client-credentials per merchant + mTLS internally; JWT scoping already enforces traffic separation |

## 5. Failure and rollout

- Degradation ladder carries over verbatim: every new component fails toward REVIEW + spool, never toward silent ALLOW.
- Rollout: shadow traffic at 1% -> 10% -> 100% (compare verdicts against the reference implementation), then canary the serving path by shard.
- Rollback: workers re-point at the previous weight version; graph schema is append-only (v1 columns still readable).

## 6. What deliberately stays out

GPU model serving (the champion is arithmetic), multi-region active-active (a v3 concern), and any component that cannot explain its decision to an auditor. The explainability contract is load-bearing and non-negotiable.
