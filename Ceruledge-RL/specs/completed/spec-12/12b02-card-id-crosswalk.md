# 12b02 — Exact Card-ID Crosswalk

Step B02 of [`12b`](12b-meta-card-semantics-audit.md). Depends on B01.

Status: **COMPLETE (2026-07-15)**

Result: all 232 meta IDs map one-to-one by exact numeric ID, exact card name, class,
source definition, attack/effect counts, names, full effect text, and Tera flag. Zero
unresolved or semantic definition mismatches remain. Forty-six ability-name differences
are verified formatting only (`[Ability]` prefix / leading whitespace). Artifacts:
`Imitation-Learning/meta-card-analysis/part-b/card-id-crosswalk.{json,csv}` plus summary
and empty issue ledger.

## Goal

Map each Part-A exact card ID to exactly one English database definition and one exact
engine definition.

## Actions

1. Load the canonical 232-card catalog and frozen English card database.
2. Determine the engine's primary card identifier and any expansion/printing keys.
3. Generate a machine-readable crosswalk with dataset ID, database rows, engine key,
   class/subtype, name, and match method.
4. List missing, duplicate, name-only, reprint, and text-mismatch cases separately.
5. Resolve every ambiguous case from IDs/expansion data or explicit user review; never
   choose by card name alone.

## Termination condition

Exactly 232 catalog IDs each have one unambiguous engine target; zero unresolved or
many-to-one printing collisions remain.

## Validation

- Crosswalk ID set equals the Part-A ID set.
- Counts equal 115 Pokémon / 99 Trainer / 18 Energy.
- Every repeated name/reprint receives an exact-ID/printing check.
- Engine and English text/name fields are diffed and every discrepancy is recorded.
- Two generated crosswalks from frozen inputs have identical hashes.

Stop if even one meta ID lacks an approved exact mapping.
