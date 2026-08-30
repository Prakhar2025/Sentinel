# 18 — Architecture Decision Records

Short-form ADRs for the six decisions that define this system. Format: context, decision, consequences. Status: all accepted and shipped.

## ADR-001: The LLM never scores

**Context:** the obvious build sprinkles an LLM over everything; the tempting one asks an LLM to rate risk. Money-adjacent decisions must be explainable, reproducible, and auditable.
**Decision:** scoring is a deterministic weighted ensemble over published features. LLMs are used exactly where they are strong: evidence-to-narrative generation and messy-field extraction, off the hot path, cost-logged, with a fallback chain.
**Consequences:** byte-identical metrics across runs; every verdict decomposes into per-feature contributions; the GBDT baseline beating the ensemble on F1 (0.909 vs 0.857) is visible and survivable rather than hidden inside a model. Cost of the decision: we carry the F1 gap until the v2 hybrid earns promotion per docs/14.

## ADR-002: Merchants are leaves, never traversal paths

**Context:** the first cluster BFS walked through merchant nodes; one popular merchant's hundreds of clean customers flooded every cluster, diluting ring signals and slowing extraction.
**Decision:** merchants count in evidence but the identity traversal crosses device/phone/VPA/email edges only.
**Consequences:** clusters stay dense and meaningful (ring ratio restored), cluster_stats p95 dropped to 0.64 ms, and the cross-merchant phenomenon stays representable through per-entity merchant fan-out counts.

## ADR-003: Deterministic-first, challenger second

**Context:** we could ship the GBDT as the scorer (higher F1) or the rule ensemble (auditable). Fintech practice: never replace a serving model on a leaderboard delta.
**Decision:** the rule ensemble serves; a GBDT challenger shadows every verdict, agreement is measured on the held-out set, and four written promotion criteria gate any cutover.
**Consequences:** the uncomfortable baseline result became an architecture instead of a confession; promotion is now a documented, reviewable process.

## ADR-004: Feature priors cap calibration

**Context:** unconstrained coordinate ascent inflated the amount-band feature (designed minor) to weight 32 by exploiting the synthetic amount distribution, contradicting the design intent that typical pricing must never be punished.
**Decision:** the calibrator enforces published per-feature weight caps (WEIGHT_CAPS), a design constraint, not post-hoc tuning.
**Consequences:** calibration optimizes within honest bounds; the cap, its reason, and the measured before/after are in the code and what-broke log.

## ADR-005: Federated aggregates plus identity-scoped access

**Context:** cross-merchant detection temptingly exposes cross-merchant data; a fraudster with a standard key could probe "is this identity burned?" and enumerate next targets.
**Decision:** standard scope receives counts/fan-out/recency/taint only (tested: merchant ids cannot appear in the payload); raw listings require the admin key and are audit-logged; merchant JWTs can ingest and read only their own traffic (403 MERCHANT_MISMATCH otherwise).
**Consequences:** the network signal ships without a data-sharing agreement between merchants; the dual-use surface is closed rather than asserted closed.

## ADR-006: Ring-stratified single-pass evaluation

**Context:** random splits leak entities between train/calibration/test, silently inflating metrics on shared-cluster data; repeated peeking at the test set converts measurement into tuning.
**Decision:** splits assign whole identity components (union-find); weights fit on train only via ring-grouped CV; thresholds lock on calibration; the test set is scored exactly once per model version; timings live outside metrics.json so it stays byte-identical.
**Consequences:** every published number is reproducible by `make calibrate && make evaluate`; adversarial results (slow-rate evasion) get documented rather than silently patched, because patching on test data would forfeit the protocol that makes any of the numbers meaningful.
