# 07: Security & Compliance

## Defense-Only Mandate (track rule: offense-capable = disqualified)

We treat this as a formal security property. Analysis of dual-use surface:

| Capability we build | Could it be used offensively? | Control |
|---------------------|-------------------------------|---------|
| Identity link graph across merchants | A fraudster would love cross-merchant identity graphs of victims | Data is 100% synthetic; entity-scoped access; no bulk-export endpoint; rate-limited queue endpoints |
| Ring-pattern detection features | Knowing features lets attackers evade | Features published only in repo docs (defense community standard, like fraud conferences); detection also uses taint + post-hoc signals that evasion cannot fully erase |
| Risk scoring API | Could be used to test stolen identities ("is this identity burned?") | Verdicts scoped to submitting merchant's own events in production design (merchant sees only verdicts on their own traffic + federated signals, never other merchants' raw data); demo runs local-only |
| Chargeback/outcome data | - | Read-only ingestion of the merchant's own outcomes |

**Explicit statement:** the system generates no attack tooling, performs no offensive scanning, and its output is a defensive recommendation. The one genuine dual-use vector, *evasion by knowing the scoring weights*, is accepted knowingly (same tradeoff every published fraud system makes) and mitigated by taint propagation, which is post-hoc and cannot be evaded pre-emptively.

## Data Protection (India DPDP Act 2023 alignment)

- **No real PII anywhere.** Synthetic data only; generator produces Indian-format identifiers that are provably non-real (reserved number ranges, synthetic VPA handles).
- **Data minimization:** store only entities needed for linking; mask phones in API responses by default. Unmasking requires a **separate admin credential** (`SENTINEL_ADMIN_API_KEY`, distinct from the standard API key) and every unmask request is written to the audit store (doc 06).
- **Purpose limitation:** labels (fraud/clean) exist only for evaluation, physically separated from the serving path.
- **Audit trail:** every verdict queryable with evidence (DPDP accountability principle).
- Production notes: consent artifacts for entity graph building, retention policy (identity graph TTL per entity type), erasure workflow (right to erasure → node deletion + re-link integrity check), documented as production requirements, out of local build scope.

## PCI-DSS Alignment (design-level)

- No PAN/card data is ingested at all (UPI/phone/device/email only), keeps the system out of PCI CDE by design.
- Money as integer paise; no card-data fields even in schema.

## Secrets & Credential Hygiene (non-negotiable build rules)

1. AWS access via **boto3 default credential chain only**, never explicit keys in code.
2. Never read/print/echo `~/.aws/credentials`, `.env`, or any `*SECRET*`/`*KEY*` variable, including for debugging. Auth failures report the error message only.
3. `.env` in `.gitignore`; `.env.example` documents required variables with placeholder values.
4. Demo credentials come from env: `SENTINEL_API_KEY` (standard scope) and `SENTINEL_ADMIN_API_KEY` (admin scope, the only key that can unmask PII); production design uses OAuth2 client-credentials per merchant with scope-limited tokens.

## Production AuthN/Z Design (documented, not built)

- Merchant-scoped JWTs; verdict visibility restricted to each merchant's own events + **federated signals only** ("linked to N confirmed-fraud events elsewhere", count and recency, never another merchant's identity data). This federated-privacy pattern is what makes cross-merchant detection deployable without merchants sharing customer data with each other.
- Immutable audit store with separate write-only credentials.
- Rate limits: 100 req/min/merchant (demo), production per-contract.

## Supply Chain & Code Quality Gates

- Dependencies pinned (`requirements.txt` with exact versions), minimal dependency count (target < 15 direct).
- No shell-outs, no `eval`/`exec`, no dynamic imports of untrusted input.
- Pre-commit: ruff (lint + format), mypy (strict on core modules), gitleaks scan (secret detection in CI).
