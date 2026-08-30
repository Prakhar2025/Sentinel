# Abuse-Ring Sentinel, Documentation Suite

> A defense-only fraud detection system that identifies the **same UPI ID, phone number, or device fingerprint being reused across multiple merchants and customers to commit fraud**, with honest, measured precision, recall, and false-positive cost.

---

## Document Index

| # | Document | Purpose |
|---|----------|---------|
| 01 | [Problem Statement](./01-problem-statement.md) | Market research, loss model, why this matters now |
| 02 | [Product Requirements (PRD)](./02-product-requirements.md) | Personas, user stories, scope, success criteria |
| 03 | [System Architecture](./03-architecture.md) | End-to-end design, data flow, diagrams, model selection |
| 04 | [Data Design](./04-data-design.md) | Database schema, synthetic data generation plan |
| 05 | [ML & Evaluation Design](./05-ml-evaluation-design.md) | Detection approach, metrics framework, FP-cost model |
| 06 | [API Specification](./06-api-spec.md) | Endpoint contracts, request/response schemas |
| 07 | [Security & Compliance](./07-security-compliance.md) | Defense-only mandate, DPDP Act, PCI-DSS alignment |
| 08 | [Tech Stack Decisions](./08-tech-stack.md) | Every choice, justified, and what we rejected |
| 09 | [Testing & Quality Strategy](./09-testing-strategy.md) | Test pyramid, evaluation harness, CI gates |
| 10 | [Risk Register & Failure Modes](./10-risk-register.md) | What can go wrong, blast radius, mitigations |
| 11 | [Roadmap & Build Plan](./11-roadmap.md) | Phased plan with verification checkpoints |
| 12 | [Pitch Script](./12-pitch-script.md) | 5-minute video structure |
| 13 | [Glossary](./13-glossary.md) | Domain terms |
| 14 | [Champion/Challenger](./14-champion-challenger.md) | Shadow model, agreement reporting, promotion criteria |
| 15 | [Productionization RFC](./15-productionization-rfc.md) | Measured capacity plan to fintech scale |
| 16 | [Threat Model](./16-threat-model.md) | STRIDE analysis mapped to built controls |
| 17 | [Runbook](./17-runbook.md) | Deploy, rollback, and 3 AM incident procedures |
| 18 | [ADRs](./18-adrs.md) | The six decisions that define the system |

---

## One-Paragraph Summary

Indian digital payments are under sustained attack by organized fraud rings that recycle the same identities (UPI IDs, phone numbers, device fingerprints) across many merchants until each merchant individually blocks them. No single merchant sees the whole pattern; only a network-level view can. **Abuse-Ring Sentinel** ingests payment events, extracts and links identity entities, builds a cross-merchant link graph, scores each identity cluster for abuse-ring membership, and produces a ranked, explainable risk verdict (ALLOW / REVIEW / BLOCK recommendation) with a full audit trail, every score backed by evidence, never a black box. It is strictly **defense-only**: it detects and informs, it never moves money, and it generates no offensive capability.

## Local Build Limitations (read before judging the demo)

The local build proves the **detection logic, evaluation honesty, and API contracts**. It deliberately does not demonstrate, and makes no measured claims about:

- **Streaming ingestion / production throughput**: no Kinesis/Flink; synchronous API only. The production topology is documented (doc 03) but unbuilt.
- **Graph scale**: in-process networkx, not sharded Neo4j. No claims about behavior at UPI-scale volumes (8,000+ TPS average).
- **Real-world data**: all data is synthetic by design (no real PII); metrics measure the detector against a specified synthetic attack model, not observed fraud in the wild.
- **Measured latency**: all latency figures are design targets until Phase 6 benchmarks are back-filled into doc 02.
- **Multi-tenant authN/Z, HA, deployment**: static demo keys, single process, local SQLite.

None of these are hidden; each maps to a documented production design and a roadmap v2 item (doc 11).

## Design Principles (non-negotiable)

1. **Explainable or it doesn't ship.** Every risk score carries a reason code, evidence list, and feature attribution.
2. **Honest metrics.** Precision/recall on a held-out set, plus false-positive cost in ₹ INR. No cherry-picked thresholds.
3. **Bounded actions.** The system recommends; humans (or explicitly configured merchant rules) decide. No autonomous money movement.
4. **Fail safe, not silent.** Every failure path is explicit, degrade to ALLOW-with-flag, never crash, never silently block.
5. **Local-first.** Runs end-to-end on a laptop with AWS CLI credentials, within $550 of Bedrock credits.
