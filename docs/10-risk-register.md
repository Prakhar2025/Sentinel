# 10: Risk Register & Failure Modes

## System Failure Modes (runtime)

| # | Failure | Detection | Behavior (by design) | Blast radius |
|---|---------|-----------|----------------------|--------------|
| R1 | Bedrock timeout/error on explanation | client timeout (5 s) | verdict returns with `explanation_status=SKIPPED`; backfill on next fetch | Low, narrative only |
| R2 | Bedrock malformed JSON | jsonschema validation | 1 stricter retry → `FAILED` status; raw evidence still delivered | Low |
| R3 | Graph store corruption/absent file | load-time hash check | readiness fails; serving returns `SYS_DEGRADED` REVIEW verdicts | Medium, all verdicts degrade to REVIEW |
| R4 | SQLite locked/corrupt | exception mapper | 503 STORE_UNAVAILABLE + degraded payload; event accepted into a spool file for replay | Medium |
| R5 | Duplicate events (webhook retries) | event_id unique constraint | idempotent return of prior verdict | None |
| R6 | Poison event (pathological graph, huge cluster) | cluster size guard (radius + node cap) | feature computation on capped subgraph; flag `TRUNCATED_EVIDENCE` | Low, scored conservatively |
| R7 | Threshold lock violated (test set peeking) | process rule: test set hash-logged, single-run script writes timestamp | disclosed in report | Credibility |

## Project Risks (build)

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|-----------|--------|------------|
| P1 | Synthetic data too easy → inflated metrics that a sharp judge punctures | Med | High | Deliberately include benign overlap (shared family devices) + sophisticated low-velocity ring; report the missed ring |
| P2 | Ring-stratified split breaks if generator bugs leak entities across splits | Med | High | Unit test asserting zero entity overlap between splits |
| P3 | gpt-oss 120B throttled/unavailable in region | Med | Low | GLM-5 fallback configured by env; extraction has regex-only fallback |
| P4 | Console over-investment eats backend time | Med | Med | Console hard-scoped to the 4 views in doc 02; built only after Phase 6 evaluation is green; no auth screens/settings/multi-role UI |
| P5 | Scope creep now that the line cap is removed | Med | Med | No cap ≠ no discipline: every module must deliver a measured capability + test + docs (NFR-6); phases still gated by verification checkpoints; speculative features rejected in review |
| P5b | Baseline comparator unexpectedly beats the rule ensemble | Low | Low (honesty win either way) | Result is reported as-is; a baseline win strengthens the v2 GNN roadmap and the decision story |
| P6 | "What broke" section empty at the end (nothing genuine logged) | Low | High (it's a deliverable) | Log maintained in real time from day 1, doc 09; real failures always occur (LLM JSON quirks, Windows path bugs, SQLite locks are near-certainties) |
| P7 | Windows-specific issues (paths, SQLite locking), dev machine is Windows | High | Low | Pathlib everywhere; WAL mode on SQLite; tests run on Git Bash + PowerShell |
| P8 | FP-cost parameters challenged as made-up | High | Med | Every parameter carries a stated source/assumption; sensitivity table at 3 parameter settings included in report |

## Degradation Ladder (summary)

```
All healthy            → full verdict + evidence (+ async narrative)
LLM down               → verdict + evidence, narrative SKIPPED
Graph store down       → forced REVIEW verdicts, SYS_DEGRADED
Everything down        → 503 with problem JSON; client retries; spool file preserves events
```
The system never fabricates confidence, and never auto-blocks on the basis of a failure.
