# 12 — Pitch Script (5 minutes)

> **Placeholder policy:** everything marked ⟨P6⟩ is filled from the real Phase 6 evaluation run — results are never pre-written and reverse-engineered. The FP-cost constant (₹321) is a design input from doc 05, safe to state before measurement; measured results are not.

**0:00–0:30 — The Problem**
"UPI fraud losses nearly doubled in a year — ₹573 crore to ₹1,087 crore. But here's the part nobody talks about: organized rings recycle the *same* UPI ID, phone, and device across many merchants. Each merchant sees a clean first-time customer. The fraud is only visible across merchants — and no single merchant can see it. That's the blind spot."

**0:30–1:30 — The Solution / Architecture**
"Abuse-Ring Sentinel builds an identity link graph — devices, phones, UPI IDs, merchants — and scores every payment event for ring membership using deterministic graph features: device fan-out across merchants, taint propagation from confirmed fraud, velocity, burn-and-rotate patterns. Verdict: ALLOW, REVIEW, or BLOCK-recommendation — with evidence. And here's my AI judgment call: the LLM never scores. Scoring is deterministic and auditable. The LLM — gpt-oss on Bedrock — does what LLMs are actually good at: turning evidence into an audit-grade explanation."

**1:30–3:00 — Live Demo**
- Show dashboard: event comes in at Merchant 4 → verdict BLOCK_REC (quote the **measured** p95 from Phase 6, not the design target) → drill into evidence: same device linked to 6 identities across 4 merchants, taint path from a confirmed chargeback. LLM narrative explains it in one paragraph.
- Show the ranked queue; click a sophisticated-ring case flagged only by taint.

**3:00–4:00 — Metrics and Honest Evaluation**
"Held-out test set, ring-stratified so no entity leaks between splits. Precision ⟨P6: value⟩ with 95% CI, recall ⟨P6: value⟩ at both event and ring level — and I'll name the ring I missed and why. ⟨P6: the missed ring + reason, from the real run⟩. False positives cost money: I price every FP at ₹321 — review time plus lost fulfillment plus churn risk, every constant named and sourced in the docs — and report net ₹ saved per 1,000 events at three thresholds, so you see the tradeoff, not one cherry-picked number. Full reproducibility: `make evaluate`, seed 42, identical metrics twice."

**4:00–4:30 — What Broke**
(From the real log only — doc 09, `what-broke.md`. The examples below are ⟨P6: likely candidates, replaced with the actual 2–3 failure stories from the log⟩: LLM JSON occasionally wrapped in markdown fences → jsonschema gate + single structured retry; benign family device-sharing caused early FPs → benign-overlap in the synthetic population forced honest feature weighting; SQLite lock on Windows → WAL mode.)

**4:30–5:00 — What's Next**
"GNN on the same feature schema when real labeled data exists. Federated verdict sharing so merchants get the network signal without sharing customer data. The pattern extends to return-risk and chargeback response. Defense-only, bounded by design — it recommends, humans decide. Thank you."

---

### Anticipated Q&A

- **"Synthetic data — why should I believe the metrics?"** The generator includes deliberate benign overlap and a sophisticated ring designed to be missed; the metric protocol (stratified splits, locked thresholds, CIs) is the contribution — swap in real data and the harness doesn't change.
- **"Why not a GNN?"** At 1,000 events it would overfit shared-entity clusters and break the explainability contract. The features are the GNN's future inputs — documented v2.
- **"Can this be used offensively?"** No attack tooling, no real PII, verdicts scoped to a merchant's own traffic, and it moves no money. Evasion pressure exists for every published fraud system — taint propagation is post-hoc and can't be pre-emptively evaded.
