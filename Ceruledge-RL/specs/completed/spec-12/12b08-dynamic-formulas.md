# 12b08 — Dynamic Calculations and Cross-Card Interactions

Step B08 of [`12b`](12b-meta-card-semantics-audit.md). Depends on B05–B07.

Status: **COMPLETE — 79/79 formula keys and 237/237 executable cases pass.**

Canonical outputs:

- `Imitation-Learning/meta-card-analysis/part-b/dynamic-formulas.json`
- `Imitation-Learning/meta-card-analysis/part-b/dynamic-formula-validation.json`
- `Imitation-Learning/meta-card-analysis/part-b/B08-DYNAMIC-FORMULA-REPORT.md`

## Goal

Close every queued dynamic verdict, including maximum-damage calculations and
cross-card/order-of-operations behavior.

## Per-formula actions

1. Name the exact card/effect/output and stable formula key.
2. Declare each input, unit, side/scope, and source: current observation, tracker, or
   genuinely hidden information.
3. Define raw output meaning: live value, credible maximum, legal maximum, bound, or
   explicit unknown.
4. Specify algorithm, order of operations, bounds, fallback, and saturation behavior.
5. Verify interactions with Tools, Stadiums, Special Energy, archetype cards, prizes,
   discard/hand/deck state, damage, and prior turns as applicable.
6. Link exact engine source and executable scenarios.
7. Flag every ambiguous input, bound, fallback, inclusion decision, or approximation in
   the mandatory human-review ledger.

## Formula termination condition

The formula has no unspecified input/timing/fallback and passes positive, negative,
boundary, stacking, suppression, and conflict cases that apply to it.

## Termination condition

Every `override_dynamic` queue item from B05–B07 is closed; no dynamic placeholder or
ambiguous `max_damage` value remains, and all formula-related human-review records have
decisions.

## Validation

- Queue keys equal completed formula keys exactly.
- Formula outputs match engine scenarios in raw units.
- Hidden inputs yield declared bounds/unknowns, never invented exact values.
- Shared handlers reuse schema while preserving card-specific conditions.
- Re-running all formula scenarios produces identical results.

Stop if any formula depends on unavailable state without an approved fallback.

## Completion record

- Exact queue closure: 51 Pokémon + 24 Trainer + 4 Energy = 79 unique formulas.
- Every formula declares raw input units/sources, timing, order, bounds or explicit
  unknown, missing-state fallback, no-saturation behavior, and exact engine evidence.
- All 237 negative/positive/boundary and applicable stacking/suppression/conflict
  scenarios pass and reproduce deterministically.
- Missing state raises `MissingFormulaInput`; it is never imputed as zero.
- `HR-B05-002` remains the only approved approximation; the exact Kangaskhan evaluator
  remains unbounded while its practical probability table stops at three heads.
- No human-review item is pending and no category was created, merged, or removed.
