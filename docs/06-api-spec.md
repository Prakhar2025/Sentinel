# 06 — API Specification

Base URL (local): `http://localhost:8000`, all responses JSON. Auth: `X-API-Key` header (static key from env for the demo; production design in doc 07). Errors follow RFC 7807-style problem JSON.

---

## POST /v1/events

Ingest a single payment event and return the risk verdict.

**Request** — event schema from doc 04.

**Response `200`**
```json
{
  "event_id": "evt_01HZY...",
  "score": 78,
  "verdict": "BLOCK_REC",
  "reason_codes": ["RNG_DEVICE_FANOUT", "RNG_TAINT_LINK"],
  "features": {"device_identity_ratio": 6.0, "cross_merchant_fanout": 4, "taint": 0.36, "velocity": 3},
  "evidence": {
    "linked_merchants": ["mcht_88231", "mcht_90112", "mcht_77210", "mcht_10233"],
    "shared_device_identities": ["cust_55102", "cust_55189", "cust_56200"],
    "taint_path": ["cust_54011 (confirmed_fraud)", "dev_9f2a1c", "cust_55102"]
  },
  "explanation_status": "PENDING",
  "model_version": "rules-v1.0",
  "schema_version": "1"
}
```

**Errors**: `400` VALIDATION_FAILED · `409` DUPLICATE_EVENT (returns prior verdict) · `503` STORE_UNAVAILABLE (with degraded `REVIEW` verdict payload).

## POST /v1/events:batch

Array of ≤ 1,000 events; per-item status array in response; partial success semantics (valid items processed, invalid items reported with index + error). Used by the evaluation harness and the demo backfill.

**Semantics:** synchronous, intended **for evaluation and backfill only** — not a production ingestion path (production is streaming; see doc 03). Only the deterministic scoring path runs inline (~20 ms/event design target → a 1,000-event batch is expected well under 1 minute); LLM explanations are enqueued async, same as the single-event endpoint.

## GET /v1/verdicts/{event_id}

Fetch a stored verdict, including the LLM explanation once generated. `404` if unknown.

## GET /v1/verdicts?verdict=BLOCK_REC&limit=50

Analyst ranked queue: verdicts filtered + sorted by score desc, with evidence summaries. Powers the P1 dashboard.

## GET /v1/risk/entities/{entity_type}/{entity_value}

Entity-centric lookup: the merchants, identities, and devices linked to a given VPA / phone / device, plus current taint and fan-out stats. Entity types: `upi | phone | device | email`.

## GET /v1/graph/cluster/{customer_id}

The local identity cluster (radius ≤ 2) around a customer — node/edge list for the dashboard's graph visualization.

## POST /v1/feedback

```json
{ "verdict_id": "...", "analyst_decision": "CONFIRM_FRAUD | CLEAR | UNKNOWN", "note": "..." }
```
P2 (stub): persisted for future training signal; never mutates a past verdict (append-only).

## GET /healthz · GET /readyz

Liveness / readiness (readiness = graph store loaded + Bedrock reachable-flag, where failure degrades but does not fail readiness).

---

## Verdict & Reason Code Reference

| Verdict | Meaning | Automated action |
|---------|---------|------------------|
| `ALLOW` | score < 35 | none |
| `REVIEW` | 35–69 or system-degraded | queue for analyst |
| `BLOCK_REC` | ≥ 70 | **recommendation only** — merchant/analyst must act |

| Reason code | Fired by |
|-------------|----------|
| `RNG_DEVICE_FANOUT` | F2 ≥ 3 |
| `RNG_IDENTITY_FARM` | F1, F7 |
| `RNG_TAINT_LINK` | F3 above threshold |
| `RNG_VELOCITY` | F4 |
| `RNG_BURN_ROTATE` | F5 |
| `RNG_AMOUNT_PATTERN` | F6 (minor contributor) |
| `SYS_DEGRADED` | any subsystem failure → forced REVIEW |

## Cross-Cutting Contracts

- **Idempotency**: `event_id` is the key; replays return the stored verdict (`200`, `duplicate: true`).
- **Money**: always integer paise.
- **PII**: phone numbers returned masked by default (`+9198XXXX5678`); full value only via `?unmask=true`, which requires the separate **admin credential** (`X-Admin-Key` = `SENTINEL_ADMIN_API_KEY`, distinct from the standard API key) — and **every unmask request is appended to the audit store** (entity, requester key id, timestamp, verdict context).
- **Versioning**: URL-versioned (`/v1`); `schema_version` in every payload; breaking changes bump the URL.
