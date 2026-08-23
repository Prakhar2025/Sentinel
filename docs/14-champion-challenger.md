# 14 — Champion/Challenger Shadow Model

## What this is

The deterministic rule ensemble is the **champion**: it serves every verdict. A gradient-boosted **challenger**, trained on the same cached train-split features under the same ring-stratified protocol, runs in **shadow**: for every ingested event the service records the challenger's opinion (`score`, `probability`, `flag`) next to the verdict, and nothing more. The challenger cannot alter a verdict, a threshold, or a reason code. Delete the artifact and the system behaves identically to before; the field is simply `null`.

This is the standard mechanism fintech risk teams use to evaluate a model replacement without touching production decisions, and it converts our most uncomfortable Phase 6 disclosure (the GBDT baseline edged the rule ensemble on F1, 0.909 vs 0.857) from an admission into an architecture.

## How it runs

```
make challenger   # trains on cached train-split features (online replay),
                  # saves evaluation/challenger.pkl (versioned, seed-stamped)
make serve        # service loads the artifact if present; shadow on
make evaluate     # held-out run adds the agreement block below
```

- Training uses only the train split; thresholds and weights of the champion remain locked from Phase 3 calibration. The challenger's own operating point is probability >= 0.5.
- The artifact carries a version string; a stale or corrupt file disables shadow mode instead of failing startup (degradation ladder semantics).
- Every stored verdict gains a `challenger` field; pre-v2 databases are migrated in place (`ALTER TABLE verdicts ADD COLUMN challenger JSON`).

## What the evaluation reports

The held-out report's champion/challenger block states, verbatim:

- events compared, both-flag count, champion-only flags, challenger-only flags, neither, and the agreement rate
- an explicit note that this is shadow opinion, not a leaderboard

## Promotion criteria (all four must hold)

1. **Superiority across seeds**: challenger F1 strictly exceeds the champion on the held-out set across multiple dataset seeds, not a single lucky split.
2. **No precision regression** beyond -0.02 at the operating threshold.
3. **Explainability parity**: per-feature attributions (SHAP or equivalent) surfaced in the evidence panel before any cutover; a risk system that cannot explain itself does not ship.
4. **Shadow soak with review**: a soak period with agreement >= 95%, and every BLOCK_REC-band disagreement reviewed by an analyst.

Until all four hold, the deterministic scorer stays. The criteria are deliberately conservative because the champion's property under protection, explainability with a full audit trail, is harder to recover than F1.

## Why this matters for the v2 story

The measured GBDT edge told us the ceiling is higher than the rule ensemble alone. Shadow mode is how you act on that information responsibly: measure in production-shaped conditions, promote only against written criteria, keep the audit contract the whole way down.
