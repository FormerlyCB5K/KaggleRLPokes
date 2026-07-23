# 12b05 — Pokémon Attack and Ability Audit

Step B05 of [`12b`](12b-meta-card-semantics-audit.md). Depends on B04.

Status: **COMPLETE — all six frozen batches pass; B06 may begin**

## Goal

Audit all 115 meta Pokémon, including every printed attack and every ability.

## Per-batch actions

For each frozen ≤20-card batch:

1. Read every English effect row and its exact engine implementation.
2. Compare the current generic output and existing override/bake behavior.
3. Assign one verdict per atomic effect and record raw semantic payloads.
4. Record targeting, timing, probability, locks, movement, healing, prevention,
   Energy/card operations, and other non-obvious effects.
5. Record damage quantities separately: printed/base, live-calculable, and credible
   maximum. Queue required formulas as `override_dynamic` for B08.
6. Add focused engine scenarios for every static correction or engine-baked claim.
7. Flag every unclear meaning, uncertain inclusion decision, approximate mapping, or
   non-tight boundary in the mandatory human-review ledger.

## Batch termination condition

Every card and effect row in the batch has evidence, a verdict, and validation; no
`unresolved` or pending human-review case remains. Dynamic verdicts may be queued only
with a complete input/output question for B08.

## Termination condition

All Pokémon batches are closed and the audit covers exactly 115 IDs.

## Validation

- Batch and global Pokémon ID/effect-row set equality.
- Generic-versus-approved diff reviewed for every changed field.
- Static override scenarios pass positive, negative, and boundary cases.
- No old two-attack/one-ability truncation appears in the audit.
- Every dynamic queue item has a unique formula key and B08 owner.

Do not advance past an incomplete batch.

## Batch progress

| Batch | Cards | Effects | Status |
|---|---:|---:|---|
| `pokemon-01` | 20 | 34 | complete |
| `pokemon-02` | 20 | 38 | complete |
| `pokemon-03` | 20 | 34 | complete |
| `pokemon-04` | 20 | 34 | complete |
| `pokemon-05` | 20 | 39 | complete |
| `pokemon-06` | 15 | 26 | complete |

`pokemon-01` has 9 `ordinary_field`, 4 `generic_exact`, 16 `override_static`, and
5 `override_dynamic` verdicts. Twelve nontrivial attacks have three distinct recorded
module-1.32.0 executions each. The Alakazam hand-count formula passes all observed
checks. Five unique dynamic items are queued to B08. `HR-B05-001` and `HR-B05-002` are
resolved; the latter is the sole registered lossiness exception.

`pokemon-02` has 10 `ordinary_field`, 3 `generic_exact`, 19 `override_static`,
5 `override_dynamic`, and 1 `engine_baked` verdict. Its five dynamic questions are
queued to B08. A complete scan of all 15,018 games found recorded executions for 12 of
16 nontrivial attacks: 11 have three distinct samples, Absolute Snow has one, and four
were never executed. Sparse/absent cases retain exact source-handler fallback evidence;
the report does not claim recorded behavior that does not exist.

`HR-B05-003` is resolved: Cursed Blast's canonical order follows the exact competition
engine—self-KO first, then counter placement—even though the English presentation lists
counter placement first.

Mega Froslass ex's theoretical maximum is 2,900 (`50 × 58`) in a legal 60-card-deck
attack state. Its credible meta maximum remains explicitly null and queued to B08. No
new approximation was introduced.

`pokemon-03` has 9 `ordinary_field`, 2 `generic_exact`, 10 `override_static`,
12 `override_dynamic`, and 1 `engine_baked` verdict. Twelve unique dynamic questions
are queued to B08, including Festival Lead's full two-attack sequence and Alakazam's
conserved damage-counter relocation. A complete 15,018-game scan found executions for
17 of 18 nontrivial attacks: 16 have three distinct samples, Dig has one, and Swirlix's
Sneaky Placement was never executed. Exact source fallback covers both sparse cases.

Alakazam Psychic retains its exact `10 + 50 × attached Energy units` live formula, but
both credible and theoretical maxima are null pending B08 because one Energy card need
not equal one Energy unit. This follows `HR-B04-003` rather than introducing an
unsupported bound. No new approximation or human-review issue was added.

`pokemon-04` has 8 `ordinary_field`, 6 `generic_exact`, 9 `override_static`, and
11 `override_dynamic` verdicts. Its complete 15,018-game scan observed 14 of 19
targeted attacks; Rellor's Slight Intrusion has two samples, while five attacks were
absent. Exact source-handler fallbacks cover every sparse or absent target. Eleven
unique formulas are assigned to B08. Full Moon Rondo preserves normal and expanded
Bench maxima of 220 and 340; Tenacious Tail preserves 360 and 540 respectively.

`pokemon-05` has 11 `ordinary_field`, 4 `generic_exact`, 14 `override_static`, and
10 `override_dynamic` verdicts. Its full scan observed 15 of 20 targeted attacks.
The exact registry retains copied-attack composition for Night Joker, multi-target
Torrential Pump damage, conditionally baked Okidogi HP/damage modifiers, and Energy-unit
rather than Energy-card scaling. Unsupported maxima remain null and owned by B08.

`pokemon-06` has 7 `ordinary_field`, 4 `generic_exact`, 7 `override_static`, and
8 `override_dynamic` verdicts. Its full scan observed 8 of 14 targeted attacks; all
sparse and absent targets have exact source fallbacks. Wild Growth's doubled Basic
Grass Energy provision and nonstacking rule, Adrena-Pheromone's exact fair-coin damage
prevention, and Sinister Surge's same-target attach/counter coupling are explicit.

## Closure result

The six canonical batches cover exactly 115 unique Pokémon card IDs and all 205 source
effect rows, with no duplicate or omitted card/effect ownership. Verdict totals are 54
`ordinary_field`, 23 `generic_exact`, 75 `override_static`, 51 `override_dynamic`, and
2 `engine_baked`. All 51 formula keys are unique and assigned to B08. Every batch is
`complete`; every effect validation passes; no human-review record is pending; and
`HR-B05-002` remains the sole approved lossiness exception.
