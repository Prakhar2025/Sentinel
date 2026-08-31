# 12 - Pitch Script (5 minutes)

> Numbers below are the real Phase 6 results (seed 42, held-out test). Nothing here is pre-written aspiration; every figure regenerates from `make evaluate`.

**0:00-0:30 - The Problem**
"UPI fraud losses nearly doubled in a year, ₹573 crore to ₹1,087 crore. But here's the part nobody talks about: organized rings recycle the *same* UPI ID, phone, and device across many merchants. Each merchant sees a clean first-time customer. The fraud is only visible across merchants, and no single merchant can see it. That's the blind spot."

**0:30-1:30 - The Solution / Architecture**
"Abuse-Ring Sentinel builds an identity link graph (devices, phones, UPI IDs, merchants) and scores every payment event for ring membership using deterministic graph features: device fan-out across merchants, taint propagation from confirmed fraud, velocity, burn-and-rotate patterns. Verdict: ALLOW, REVIEW, or BLOCK-recommendation, with evidence. And here's my AI judgment call: the LLM never scores. Scoring is deterministic and auditable. The LLM, gpt-oss on Bedrock, does what LLMs are actually good at: turning evidence into an audit-grade explanation."

**1:30-3:00 - Live Demo**
- Analyst console: event comes in at Merchant 4 → verdict BLOCK_REC in about five milliseconds at the median under load (178 events per second, evaluation/loadtest.json) → drill into the evidence view: same device linked to 6 identities across 6 merchants, taint path from a confirmed chargeback, LLM narrative in one paragraph.
- Ring replay: press run, watch the ring's scores climb 23 → 50 → 69 → 82 as it spreads across six merchants. Fan-out and taint accumulate; that's the detection story in twelve seconds.
- Flash the evaluation-dossier view: metrics, FP cost in ₹, and the evasion table (we attacked our own detector and published what got through).

**3:00-4:00 - Metrics and Honest Evaluation**
"Held-out test set, ring-stratified so no identity leaks between splits. Precision 0.833 with a 95% confidence interval, recall 0.882 at event and ring level, both rings caught including the sophisticated one, and zero fraud passed silently. False positives cost money: I price every FP at ₹321, review time plus lost fulfillment plus churn risk, all constants named and sourced in the docs, and report net ₹38,665 saved per 1,000 events at three thresholds, so you see the tradeoff, not one cherry-picked number. Full reproducibility: `make evaluate`, seed 42, byte-identical metrics twice. And two disclosures: a GBDT baseline edges my rule ensemble on F1, 0.909 versus 0.857, which I show because it's the measured argument for the v2 hybrid while the deterministic scorer keeps the audit contract. And slow-rate evasion rings get through the current weights; that's documented with the fix, time-windowed fan-out, not silently patched."

**4:00-4:30 - What Broke**
(From the real log, docs/what-broke.md, thirty-plus entries.) Suggested picks:
- "My first calibration inflated the amount feature to weight 32 by exploiting my own synthetic data distribution. I capped it with a published feature prior and documented why."
- "My first dataset put all 100 fraud events in the train split, silently making the test set useless. A unit test now proves fraud reaches every split."
- "The graph walked through merchants, so one popular merchant flooded every identity cluster. Merchants are leaves now, and cluster extraction went from 15 seconds crawling to 0.64 milliseconds."

**4:30-5:00 - What's Next**
"GNN on the same feature schema when real labeled data exists. Federated verdict sharing so merchants get the network signal without sharing customer data. The pattern extends to return-risk and chargeback response. Defense-only, bounded by design, it recommends, humans decide. Thank you."

---

### Recording checklist

Full production kit (scene-by-scene shot list, OBS and audio setup, editing, the on-camera numbers card, publish checklist): `docs/20-video-production-guide.md`.

1. Fresh demo state: delete `sentinel.db*`, `make serve`, `make console`, run `make backfill` first for narratives on the seeded store, then restart serve for the fresh replay experience.
2. Record at 1440x900, console on the left half, terminal on the right.
3. Keep the demo to 90 seconds: one queue click, one replay run, one dossier scroll.
4. The 3 AM slide: three real entries from what-broke.md, shown on screen for 5 seconds each.

### Anticipated Q&A

- **"Synthetic data, why should I believe the metrics?"** The generator includes deliberate benign overlap and a sophisticated ring designed to be missed; the metric protocol (stratified splits, locked thresholds, CIs) is the contribution. Swap in real data and the harness doesn't change.
- **"Why not a GNN?"** At 1,000 events it would overfit shared-entity clusters and break the explainability contract. The features are the GNN's future inputs, documented v2.
- **"Can this be used offensively?"** No attack tooling, no real PII, verdicts scoped to a merchant's own traffic, and it moves no money. Evasion pressure exists for every published fraud system; taint propagation is post-hoc and can't be pre-emptively evaded.
- **"The baseline beat you. Ship the baseline?"** The baseline can't tell you why. For a system whose output a human must act on, the decomposition is the product; the hybrid that keeps both is v2, and the evaluation already proves the ceiling is there.
