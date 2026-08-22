# 02 — Product Requirements (PRD)

## Personas

| Persona | Description | Need |
|---------|-------------|------|
| **Risk Analyst (Riya)** | Reviews flagged identities at a large merchant | Wants ranked queue with *evidence*, not raw scores — "show me why" |
| **Merchant Ops (Arjun)** | Solo founder, 5k txns/month | Wants a simple API: "should I fulfil this order?" with a plain-language reason |
| **Risk Platform Team (Razorpay internal)** | Builds risk infra | Wants an explainable subsystem that plugs into the existing rule engine |

## User Stories

1. **US-1 (Ingest & Score)** — As a merchant system, when a payment event arrives, I want a risk verdict (ALLOW / REVIEW / BLOCK-recommend) + score + reason codes within **< 300 ms p95** (local; design target 100 ms at production scale).
2. **US-2 (Ring Detection)** — As a risk analyst, I want to see when an identity contacting my merchant is already linked to confirmed fraud at other merchants — with the cross-merchant evidence trail.
3. **US-3 (Explainability)** — As any user, I want every score backed by: top contributing signals, the linked entities, and a generated natural-language explanation.
4. **US-4 (Honest Metrics)** — As a platform team, I want a reproducible evaluation harness that reports precision, recall, F1, confusion matrix, and **false-positive cost in ₹** on a held-out set.
5. **US-5 (Safe Failure)** — As an operator, I want any subsystem failure (LLM timeout, graph store down) to degrade gracefully — verdict defaults to ALLOW-with-REVIEW flag, never a crash, never a silent auto-block.
6. **US-6 (Audit)** — As a compliance officer, I want every verdict persisted with its full evidence payload and model versions, queryable later.

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Ingest payment events (single + batch) via API | P0 |
| FR-2 | Entity extraction & normalization: UPI VPA, phone (E.164), device ID, email, IP | P0 |
| FR-3 | Identity link-graph store with cross-merchant linking | P0 |
| FR-4 | Ring-detection scorer (graph features + rules) producing 0–100 risk score | P0 |
| FR-5 | Verdict + reason codes + evidence list API response | P0 |
| FR-6 | LLM-generated natural-language explanation (Bedrock, structured output) | P0 |
| FR-7 | Evaluation harness: held-out test set, metrics report incl. FP cost in ₹ | P0 |
| FR-8 | Synthetic data generator (900 clean / 100 fraud, realistic ring patterns) | P0 |
| FR-9 | Audit log of every verdict | P1 |
| FR-10 | Analyst dashboard (simple web view of the ranked queue + graph) | P1 |
| FR-11 | Feedback ingestion (analyst confirms/rejects flag → future training signal) | P2 (stub only) |

## Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|------|
| NFR-1 | Latency (local, end-to-end per event) | p95 < 300 ms (graph scoring alone < 20 ms; LLM explanation async/cached) |
| NFR-2 | Determinism | Same input + same graph state → same score (LLM only explains, never scores) |
| NFR-3 | Reproducibility | `make evaluate` produces identical metrics from fixed random seed |
| NFR-4 | Cost | Full build + evaluation within $550 AWS credits |
| NFR-5 | Portability | Runs locally; no deployed infra required |
| NFR-6 | Codebase size | < 3000 lines (per buildathon constraint) |
| NFR-7 | Test coverage | Core scoring/graph logic ≥ 90% line coverage |

## Explicit Scope Boundaries (what we are NOT building, and why)

| Not building | Why |
|--------------|-----|
| Autonomous blocking / money movement | Defense-only + bounded-action principle; system recommends, human decides |
| Real Razorpay production integration | No access to production APIs; we simulate the merchant event stream with realistic synthetic data |
| Real PII / real transaction data | Legal + privacy (DPDP); synthetic data only, and it makes metrics honest by construction |
| Streaming infra (Kafka/Kinesis) | Local-first constraint; batch + synchronous API demonstrates the design; production topology documented in arch doc |
| Deep learning / GNN model training | At 1000-event scale, learned GNNs would overfit; deterministic graph heuristics + features are honest, explainable, and sufficient. GNN is the documented v2 path |
| Mule-account / AML detection | Different loss class; noted as roadmap extension |

## Success Definition (buildathon bar mapping)

| Evaluation criterion | How we satisfy it |
|----------------------|-------------------|
| Problem taste | Identity-reuse rings: the relational blind spot individual-transaction ML can't see |
| Build quality | Typed, tested, documented; runs with `make setup && make evaluate` |
| AI judgment | LLM used only where it's genuinely right (entity extraction assist + explanation); **scoring is deterministic** — we explicitly chose NOT to let an LLM score |
| Failure recovery | Doc 10 risk register + genuine "what broke" log maintained during build |
