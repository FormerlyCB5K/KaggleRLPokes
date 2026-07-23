# 12b03 — Deterministic Audit Worklist

Step B03 of [`12b`](12b-meta-card-semantics-audit.md). Depends on B02.

Status: **COMPLETE — 2026-07-15**

## Goal

Create the complete, reviewable source dossier and freeze small audit batches.

## Actions

1. Join Part-A frequency/provenance, all English card rows, the B02 engine mapping, and
   engine handler/opcode references.
2. Attach current generic parser output, card-ID overrides, stat bakes, and hardcoded
   dynamic formulas for comparison.
3. Preserve every attack, ability, and Trainer/Energy effect in source order; do not
   inherit the old two-attack/one-ability truncation.
4. Create atomic effect-row IDs and one dossier per exact card ID.
5. Freeze class-specific ≤20-card batches using the ordering rule in the B index.

## Termination condition

Every one of the 232 cards and every source effect row appears exactly once in the
worklist, and the batch manifest is frozen.

## Validation

- Card-key equality and 115/99/18 class counts pass.
- Database effect-row counts reconcile with dossier rows.
- No attack/ability/effect is omitted or duplicated.
- Every current meta-card override/bake/formula is attached to its dossier.
- Worklist and batch-manifest hashes match across two generations.

Stop if any source behavior remains implicit or unassigned.

## Completion record

- `audit-worklist.json` contains all 232 exact card IDs and 314 atomic effects:
  155 attacks, 46 abilities, 99 Trainer effects, 10 Special Energy effects, and
  4 Tera rules.
- Class coverage is exactly 115 Pokémon / 99 Trainer / 18 Energy.
- The frozen manifest contains 12 class-specific batches, each with at most 20 cards.
- All database, binary-engine, and active-source effect counts reconcile; the issue
  ledger is empty.
- Current comparison evidence attaches 23 overrides, 14 stat bakes, and hardcoded
  dynamic references for 15 meta card IDs.
- Eight focused tests passed. Two consecutive generations produced identical bytes for
  all five B03 outputs. Worklist SHA-256:
  `338fbd810960461b423affed4e0c33a2714ef3dabb13afd57e82dba5fdfb801b`;
  batch-manifest SHA-256:
  `1c4b31b2a9cae12a7a4f0601838df0509533c7f52ca3248a48a60470a0fae187`.
