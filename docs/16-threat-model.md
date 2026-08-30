# 16 — Threat Model (STRIDE, compact)

Scope: the Sentinel service, console, data pipeline, and the humans around them. Method: each STRIDE class mapped to concrete threats and the control that already exists in this repo, or the documented gap.

| # | Class | Threat | Control (built) | Gap / acceptance |
|---|-------|--------|-----------------|------------------|
| 1 | Spoofing | Stolen API key used to read verdicts | Timing-safe comparison; standard key reads only analyst views | Rotate keys via env; no expiry on demo keys (documented demo scope) |
| 2 | Spoofing | Forged merchant injecting another merchant's events | JWT signature + expiry + issuer checks; MERCHANT_MISMATCH 403 on cross-merchant ingest | Secret rotation runbook item; revocation list is v3 |
| 3 | Tampering | Payload tampering in transit | HTTPS termination assumption documented; HMAC-safe compares everywhere | mTLS internally is the production RFC item |
| 4 | Tampering | Manipulated verdicts post-hoc | Verdicts append-only; admin actions audit-logged with scope label; no update endpoint exists | Database-level immutability (triggers/grants) in production |
| 5 | Repudiation | Analyst denies having unmasked PII | unmask and entity-full lookups write audit rows (action, entity, scope, timestamp) | Add actor identity to JWT sub in production |
| 6 | Information disclosure | Cross-merchant identity leakage | Standard scope sees federated aggregates only (tested: merchant ids cannot appear in the response); JWT queue filtering; phones masked by default | Aggregate-only enforced at API layer; row-level security in Postgres is productionization |
| 7 | Information disclosure | PII exfiltration from repo/data | All data synthetic; labels never in serving payloads; gitleaks on every push; .env gitignored | Real-PII onboarding needs a DPA and field-level encryption |
| 8 | Denial of service | Ingest flood exhausting the service | Batch size cap; bounded thread pools; spool-to-disk on store failure; degradation ladder fails toward REVIEW | Rate limiting per merchant is the production RFC item |
| 9 | Denial of service | LLM cost bomb via explanation spam | Explanations off the hot path; botocore retries off; single bounded retry; per-run spend caps; cost log | Per-tenant narrative quotas in production |
| 10 | Elevation of privilege | Standard key escalating to raw entity lists | Separate admin key required for /full and unmask; JWTs structurally cannot carry admin scope | None known; tested by contract tests |

## Residual risks, accepted knowingly

- **Evasion pressure** (attacker knows published weights): inherent to any documented fraud system; taint propagation is post-hoc and cannot be pre-emptively evaded; the evasion pack quantifies the current blind spot honestly.
- **Single-process availability**: the local build is one process by design; the degradation ladder bounds the blast radius and the RFC removes the limitation at scale.
- **Supply chain**: pinned lockfile, 14 direct dependencies, no post-install scripts reviewed-in; Dependabot or equivalent is a production add.
