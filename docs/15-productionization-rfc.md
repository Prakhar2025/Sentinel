# 15 — Productionization RFC

Status: proposed (v2) | Owner: platform | Everything below derives from *measured* numbers in this repo, not estimates.

## 1. Measured baseline (this repository, reference laptop)

From `make loadtest` (docs + evaluation/loadtest.json):

| Quantity | Measured | Notes |
|----------|----------|-------|
| Sequential ingest+score throughput | 178 events/s | single Python process, full pipeline incl. graph writes |
| End-to-end ingest+score latency | p50 4.8 ms / p95 15.2 ms | full path incl. graph writes; scoring alone is p50 1.5 ms / p95 2.7 ms (evaluation/latency.json) |
| 4-thread arrival probe | 183 events/s (flat), p99 346 ms | GIL + single-writer lock: threads do not scale a CPU-bound pipeline |
| Held-out evaluation | P 0.833 / R 0.882 | unchanged under load by design: scoring is deterministic |
| LLM narrative | ~7 s, ~$0.0003/event | async, off the hot path; narratives are generated for the REVIEW and BLOCK bands only |

## 2. Target envelope

UPI runs ~8,000 TPS average (NPCI Jan 2026: 21.7B transactions/month) with peaks well above 10k. A Razorpay-scale deployment target for this subsystem: **10,000 events/s sustained, p99 scoring < 100 ms, zero data loss on node failure.**

## 3. The gap, quantified

10,000 / 178 ≈ **57x**. Three changes close it, and only the first supplies throughput; the other two remove the bottlenecks that would otherwise cap it. None is "rewrite in a faster language" (5-20x at best, and it costs the audit story).

1. **Worker processes (the whole 57x, not a fraction of it):** each worker is an independent process (no GIL sharing) sustaining ~178 events/s, so 10,000 / 178 ≈ **56 workers**. At ~4 workers per node that is **56-64 workers across 14-16 nodes** with N+1 redundancy. The measurement that threads *don't* help (flat 183/s with exploding tails at p99 346 ms) is precisely why process sharding is the design.
2. **Sharded graph (the enabler, not a separate multiplier):** worker count is what buys throughput; sharding is what makes 56 concurrent writers possible at all, since a single in-process graph is one writer.  partition entities by hash(device_id) with customer-owned routing; cross-shard edges (a device and phone sharing no hash key) resolve through a async join tier. Roughly 80% of cluster reads stay local at 64 shards by the benign-overlap statistics of our own generator.
3. **Streaming ingest (unbounded):** Kinesis/Flink replaces synchronous POST at the edge; backpressure becomes queue depth, a monitored metric instead of a latency cliff.

## 4. Component plan

| Component | Local build | Production shape |
|-----------|-------------|------------------|
| Ingest | FastAPI POST | Kinesis shards + Flink operators (extraction, feature windows) |
| Graph | networkx in-process | Sharded graph service; Neo4j-compatible API per shard; our GraphStore port/adapter is the seam (proven by the Postgres swap) |
| Scoring | deterministic ensemble | Unchanged (that is the point); weights served from a config service with versioned rollout |
| Challenger | shadow GBDT | Shadow at 100% sample; promotion per docs/14 criteria, automated across seeds |
| LLM narrative | Bedrock, bounded backfill | Queue with concurrency caps; only REVIEW/BLOCK bands. On the held-out set that is 42.6% of events, but that set is fraud-enriched (8.6% base rate) and a production figure must be re-derived at real base rates; at 42.6% of 10k/s the queue would need ~4,260 narratives/s, so the queue is hard-capped and degrades to SKIPPED rather than ever blocking a verdict |
| Store | SQLite WAL | Postgres (proven in CI) with partitioned verdicts; audit log to immutable object storage |
| AuthN/Z | API key + JWT | OAuth2 client-credentials per merchant + mTLS internally; JWT scoping already enforces traffic separation |

## 5. Failure and rollout

- Degradation ladder carries over verbatim: every new component fails toward REVIEW + spool, never toward silent ALLOW.
- Rollout: shadow traffic at 1% -> 10% -> 100% (compare verdicts against the reference implementation), then canary the serving path by shard.
- Rollback: workers re-point at the previous weight version; graph schema is append-only (v1 columns still readable).

## 6. What deliberately stays out

GPU model serving (the champion is arithmetic), multi-region active-active (a v3 concern), and any component that cannot explain its decision to an auditor. The explainability contract is load-bearing and non-negotiable.
