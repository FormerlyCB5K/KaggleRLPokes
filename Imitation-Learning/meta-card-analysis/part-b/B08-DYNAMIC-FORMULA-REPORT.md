# Spec 12b08 Dynamic Formula Report

Status: complete on 2026-07-15.

## Outcome

All 79 `override_dynamic` queue keys are closed exactly: 51 Pokémon formulas, 24
Trainer formulas, and 4 Special Energy formulas. The canonical machine-readable
registry is `dynamic-formulas.json`; its executable validation record is
`dynamic-formula-validation.json`.

Each formula record identifies the exact card ID and effect, declares every input with
its raw unit and source, preserves source-program timing/order, defines missing-state
and saturation behavior, links the exact engine source and source-chain hash, and
contains three executable cases. The 237 cases collectively cover negative, positive,
boundary, and all applicable stacking, suppression, and conflict behavior.

## Accuracy policy

- Outputs stay in raw engine units. No encoder normalization or damage clipping occurs.
- Missing required state is never treated as zero. The executable evaluator raises
  `MissingFormulaInput`; a later integration boundary must emit explicit unknown.
- A state-dependent card has an exact live formula. When card text alone does not imply
  a safe constant maximum, the registry says so explicitly instead of inventing one.
- Cross-card attacks retain their referenced attack programs and card-specific gates:
  Tera for Gemstone Mimicry, N's Pokémon for Night Joker, visible pre-evolution stacks
  for Memory Dive, and Stadium/continuation state for Festival Lead.
- Shared evaluator handlers are implementation reuse only. They do not merge distinct
  card semantics or change the approved B04 category set.

## Human review and approximations

No human-review record is pending. No new category was created, merged, or removed in
B08, and no newly unclear effect mapping was found.

The sole approved approximation remains `HR-B05-002`: Mega Kangaskhan ex's practical
coin distribution lists 0–3 heads (200, 250, 300, and 350 damage). The exact evaluator
still accepts every nonnegative number of heads; only the practical probability table
omits the `>=4` tail, whose total probability is 0.0625. No other dynamic formula is
clipped or approximated.

## Validation

- Queue/completed-key equality: 79/79, with no duplicate key.
- Executable cases: 237/237 pass and reproduce identically.
- Focused suite through the serialized clean-room regression: 81 tests pass (13 B08
  plus the prior 68 inventory/audit tests).
- Registry SHA-256: `c94c7f88eddee1535194819ce6207fd4963520f0b4b28b1ae8bb8566ba4452cc`.
- Validation SHA-256: `92cd9f7219ce8a8cadcc53de0fc95e839ff3569904add91dff7021ad4edbc756`.

These hashes were reproduced by a second build. B08 is ready for the B09 closure audit.
