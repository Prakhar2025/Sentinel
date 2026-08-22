# 01: Problem Statement

## The Problem (one paragraph)

Organized fraud rings operating across India's digital payment ecosystem recycle the **same identity artifacts** (UPI IDs/VPAs, phone numbers, device fingerprints) across multiple merchants and customer accounts, exploiting the fact that **each merchant only sees its own slice of the attack**. A ring hits Merchant A with UPI ID `fraud@ybl` until chargebacks and refund abuse force a block, then simply moves to Merchant B, where the identity is pristine. By the time any single merchant notices, the ring has already monetized elsewhere. Individual-transaction fraud ML (which Razorpay already does well with its AI payments foundation model) cannot see this pattern, because each transaction *looks clean in isolation*; the signal is **relational**: entity reuse, velocity across merchants, and cluster geometry. No merchant-side tool today gives a merchant the network-level answer: *"this identity contacting your checkout has already been flagged by 4 other merchants in the last 72 hours."*

## Why Now (market evidence)

| Fact | Source / Context |
|------|------------------|
| UPI fraud losses: **₹573 crore (FY23) → ₹1,087 crore (FY24)**, nearly doubled in one year | PwC India, *Combating Payments Fraud* |
| UPI processed **~22,000 crore transactions in CY2025**; ~7,500 TPS sustained, 10,000+ TPS peaks | PIB / NPCI |
| RBI proposed a **1-hour cooling period for first-time high-risk payments** (Oct 2025), a direct regulatory response to first-payment fraud | RBI draft framework, widely reported |
| Refund abuse is now the **#1 attack vector** (47% of merchants report it); merchants average 5 fraud tools yet still lose margin | The Payments Association, 2025 fraud trends |
| AI-enabled fraud (synthetic identities, scripted ring attacks) is the fastest-growing category in Indian BFSI | Track 02 brief |

The pattern: **volume is exploding, fraud is industrializing, and the relational blind spot is the gap.**

## The Loss Model (what this system defends against)

For a mid-size Razorpay merchant (~50k transactions/month):

```
Fraud-ring exposure per month (illustrative, conservative):
  Chargebacks filed by ring         : 120 × avg ₹850   = ₹1,02,000
  Refund abuse                      :  80 × avg ₹600   =   ₹48,000
  Chargeback penalties (₹100–500)   : 120 × ₹200       =   ₹24,000
  Manual review labor               :  30 hrs × ₹500   =   ₹15,000
  -----------------------------------------------------------------
  Total monthly bleed               ≈ ₹1,89,000  (~₹22.7 lakh/year)
```

Rough ROI at the design operating point (recall ≈ 60% of ring events caught, precision ≈ 0.80; FP cost ₹321 per doc 05):

```
Fraud events in the bleed model: 200/month (120 chargebacks + 80 refund abuse)
  Gross fraud recovered : 120 caught events × ₹1,100        = ₹1,32,000/month
  False-positive cost   : 30 FP (at P = 0.80) × ₹321        =   ₹9,630/month
  Review overhead       : ~100 REVIEW events × ₹120         =  ₹12,000/month
  ---------------------------------------------------------------------
  Net saving            ≈ ₹1,10,400/month  ≈ ₹13.2 lakh/year
```

That ₹13 lakh/year net, with the false-positive cost **priced in, not hand-waved**, is the ROI story, and it is why FP cost is a first-class metric (constants and assumptions in doc 05).

## Attack Model, What an Abuse Ring Looks Like

```mermaid
graph LR
    subgraph "Fraud Ring (ground truth pattern)"
        D1[Device DF-9F2]
        P1[+91 98XXXXXX01]
        U1[ring@ybl]
        D1 -->|used to create| C1[Cust A @ Merchant 1]
        D1 -->|used to create| C2[Cust B @ Merchant 2]
        P1 -->|linked to| C3[Cust C @ Merchant 3]
        U1 -->|pays with| C4[Cust D @ Merchant 4]
        C1 -->|chargeback| M1[Merchant 1 loses ₹]
        C2 -->|refund abuse| M2[Merchant 2 loses ₹]
        C3 -->|chargeback| M3[Merchant 3 loses ₹]
    end
```

**Key relational signals (features, not secrets):**
1. **Identity velocity**: same phone/UPI/device appearing at N merchants within a time window.
2. **Cluster density**: a device connected to > K distinct payment identities is anomalous (normal users: 1–3).
3. **Post-hoc taint**: identities linked to a confirmed chargeback/fraud event spread risk to their graph neighbors.
4. **Burn-and-rotate pattern**: identity discarded shortly after first chargeback, replaced by a linked neighbor.
5. **Temporal bursts**: ring activity clusters in short windows (scripted), unlike organic spread.

## Scope: What Class of Loss We Address

Per the track brief ("one class of loss"), we target **identity-reuse fraud rings**: the abuse that only network-level detection can catch. We explicitly do **not** re-solve card-not-present scoring, account takeover, or mule-account detection as separate problems (see scope boundaries in doc 02), though the graph we build naturally extends to them (noted in roadmap).

## Defense-Only Position

This system detects, scores, explains, and recommends. It cannot be repurposed offensively because it: (a) generates no attack tooling, (b) produces merchant-scoped, access-controlled verdicts, (c) never executes financial actions, and (d) is trained only on synthetic data with no real PII. Full analysis in doc 07.

## Success Criteria (from the track bar)

- Working detector for identity-reuse abuse rings ✅
- **Measured precision & recall on a held-out test set** (900 clean / 100 fraud) ✅
- **False-positive cost quantified in ₹ INR** ✅
- Strictly defense-only ✅
