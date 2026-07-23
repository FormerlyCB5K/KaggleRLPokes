# 12b06 — Trainer Effect Audit

Step B06 of [`12b`](12b-meta-card-semantics-audit.md). Depends on B05.

Status: **COMPLETE — all five frozen batches pass; B07 may begin**

## Goal

Audit all 99 meta Trainers: Items, Supporters, Pokémon Tools, and Stadiums.

## Per-batch actions

For each frozen ≤20-card batch:

1. Compare exact text, engine handler, and current bake/override behavior.
2. Record search/draw/discard, movement, healing, Energy operations, locks, modifiers,
   scopes, conditions, durations, replacement, and suppression.
3. Assign one verdict per atomic effect and raw semantic payloads.
4. Mark engine-resolved values explicitly to prevent double counting.
5. Queue history-, board-, or cross-card-dependent calculations for B08 with named
   inputs and expected outputs.
6. Add focused engine scenarios for every non-generic claim.
7. Flag every unclear meaning, uncertain inclusion decision, approximate mapping, or
   non-tight boundary in the mandatory human-review ledger.

## Batch termination condition

Every card/effect row has evidence, a verdict, and validation; no `unresolved` case
or pending human-review case remains.

## Termination condition

All Trainer batches are closed and cover exactly 99 IDs with subtype totals matching
Part A.

## Validation

- Batch/global card and effect-row set equality.
- Apply/non-apply tests for every modifier family.
- Suppression, replacement, expiry, and stacking tests where applicable.
- Every changed field in the generic/bake diff is explained.
- Every dynamic item has a unique B08 formula key.

Do not advance past an incomplete batch.

## Batch results

| Batch | Cards | Effects | Dynamic formulas | Status |
|---|---:|---:|---:|---|
| `trainer-01` | 20 | 20 | 5 | complete |
| `trainer-02` | 20 | 20 | 6 | complete |
| `trainer-03` | 20 | 20 | 5 | complete |
| `trainer-04` | 20 | 20 | 5 | complete |
| `trainer-05` | 19 | 19 | 3 | complete |

The exact subtype totals are 32 Items, 39 Supporters, 11 Pokémon Tools, and 17
Stadiums. Verdict totals are 67 `override_static`, 24 `override_dynamic`, and 8
`engine_baked`. The 24 calculation keys are unique and assigned to B08.

## Evidence and closure

The unified Trainer evidence pass scanned all 15,018 games and followed both `Play`
logs and Tool `Attach` logs. Ninety-eight of 99 Trainers were observed: 92 have three
distinct traces, Larry's Skill has two, five rare cards have one, and Janine's Secret
Art has none. Every sparse or absent case has exact source-handler fallback evidence.

The audit preserves non-effect card rules and operation ordering where the atomic
effect chain alone is insufficient. In particular, Neutralization Zone retains its
card-level discard-to-hand/deck prohibition, Hand Trimmer resolves the opponent's
discard first, Area Zero Underdepths resolves the Stadium owner's Bench reduction
first when leaving play, and Tool triggers remain active even when their holder is
Knocked Out when the text requires it.

All 99 exact card IDs and 99 source effect rows are owned exactly once. All effect
validations pass, all canonical files reproduce byte-for-byte, no human-review record
is pending, and `HR-B05-002` remains the sole approved approximation.
