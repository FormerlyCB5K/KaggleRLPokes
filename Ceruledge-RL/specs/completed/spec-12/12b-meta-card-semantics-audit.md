# 12b — Meta-Card Semantics Audit (Step Index)

Part B of [`12-top-ladder-meta-card-registry.md`](12-top-ladder-meta-card-registry.md).
Depends on completed Part A.

Status: **COMPLETE — B01–B09 passed; Part-C handoff has no open semantic decision**

## Outcome

Produce an engine-verified semantic verdict for every non-obvious attack, ability,
Trainer, Tool, Stadium, and Energy effect belonging to the 232 exact card IDs from
Part A. The result supplies raw semantic payloads and dynamic calculations to Part C;
it does not define the final observation vector.

## Execution order

| Step | Contract | Terminates when |
|---|---|---|
| B01 | [`12b01-engine-intake.md`](12b01-engine-intake.md) | Engine identity, paths, and baseline behavior are frozen. |
| B02 | [`12b02-card-id-crosswalk.md`](12b02-card-id-crosswalk.md) | All 232 IDs map unambiguously to exact engine definitions. |
| B03 | [`12b03-audit-worklist.md`](12b03-audit-worklist.md) | Deterministic per-effect dossiers and ≤20-card batches exist. |
| B04 | [`12b04-semantic-schema.md`](12b04-semantic-schema.md) | Every discovered mechanic has a validated representational home. |
| B05 | [`12b05-pokemon-audit.md`](12b05-pokemon-audit.md) | All 115 Pokémon and all their attacks/abilities are reviewed. |
| B06 | [`12b06-trainer-audit.md`](12b06-trainer-audit.md) | All 99 Trainers and their effects are reviewed. |
| B07 | [`12b07-energy-audit.md`](12b07-energy-audit.md) | All 18 Energy cards and their effects are reviewed. |
| B08 | [`12b08-dynamic-formulas.md`](12b08-dynamic-formulas.md) | Every dynamic/cross-card calculation is specified and engine-tested. |
| B09 | [`12b09-audit-closure.md`](12b09-audit-closure.md) | Coverage, evidence, determinism, and zero-unresolved gates all pass. |

Dependency chain: `B01 → B02 → B03 → B04 → B05 → B06 → B07 → B08 → B09`.
Do not start a later step because an earlier step is “mostly done.” Its termination and
validation gates must be recorded as passing first.

## Batch rule

Steps B05–B07 operate on deterministic batches of at most 20 exact card IDs:

1. class-specific cards sorted by `decks_with_card` descending;
2. ties sorted by integer card ID ascending; and
3. sequential batches numbered and frozen by B03.

Each batch is independently complete only when every card and every source effect row
has a verdict, evidence reference, and validation result. Frequency controls order, not
coverage.

## Evidence rule

Every nontrivial verdict records:

1. exact English card text;
2. exact engine card/effect handler reference;
3. current generic/override behavior for comparison; and
4. a focused engine scenario or documented proof when behavior is executable.

Card text and engine behavior disagreements are blocking issues until explicitly
resolved. Existing encoder behavior is a baseline, never authority.

## Mandatory human-review rule

Create a human-review record immediately whenever any of the following occurs:

- card wording or engine semantics admit more than one reasonable interpretation;
- it is unclear whether an effect should be represented, delegated, or omitted;
- a proposed mapping is approximate, conditional on an assumption, or otherwise not
  fully tight;
- a new effect category is proposed;
- an original-encoder category would be split, merged, renamed, generalized, narrowed,
  deprecated, or removed;
- card text, engine implementation, current encoder behavior, or observed state disagree;
  or
- any other decision would rely on reviewer judgment rather than direct evidence.

Each record contains card/effect IDs when applicable, the exact question, evidence,
viable options and tradeoffs, the auditor's recommendation, the step/batch that raised
it, and its eventual human decision. Do not silently resolve or omit these cases.

At each step/batch gate, consolidate new records into a short user interview. Unrelated
work may continue, but the affected gate cannot close until its blocking records are
resolved. The final Part-B report includes **all** human-review records, including
resolved ones, their decisions, and any remaining caveats. Any unresolved record blocks
B09 and Part C.

## Verdicts

Each atomic effect receives one primary verdict:

- `generic_exact`
- `override_static`
- `override_dynamic`
- `engine_baked`
- `ordinary_field`
- `no_non_obvious_effect`
- `unresolved`

`override_dynamic` may remain queued through B05–B07, but B08 must close its formula and
tests. Any `unresolved` verdict blocks B09 and Part C.

## Part-B termination condition

Part B is complete only when:

- audit card keys equal the 232 Part-A IDs exactly;
- class counts remain 115 Pokémon / 99 Trainer / 18 Energy;
- every source attack, ability, and effect row has one final non-`unresolved` verdict;
- every static override and dynamic formula has engine evidence and passing tests;
- engine-baked fields and ordinary delegated fields are explicit, preventing double
  counting;
- all generated audit artifacts reproduce byte-for-byte from frozen inputs; and
- the final report contains the complete human-review ledger and recorded decisions;
  zero human-review records remain unresolved; and
- B09 produces the approved payload set consumed by Part C.

## Scope boundary

Part B records only difficult/non-obvious semantics in raw units. It does not choose
tensor dimensions, positional feature indices, normalization constants, or model
architecture, and it does not wire an observation encoder.
