# 12c — Card-ID Semantic Registry and Encoder Handoff

Part C of [`12-top-ladder-meta-card-registry.md`](12-top-ladder-meta-card-registry.md).
Depends on completed Parts A and B.

Status: **COMPLETE — deterministic registry package accepted with 232 cards and 314 effects**

## Purpose

Compile the approved Part-B verdicts into a deterministic, versioned registry keyed by
exact integer card ID. The registry supplies the difficult non-obvious attack, ability,
effect, maximum-damage, and calculated-feature semantics needed by a separate instance
that will design and wire the future imitation-learning observation encoder.

The handoff must make omissions obvious and must not require the recipient to interpret
free-form audit prose.

## Registry boundary

The registry stores semantic values in raw units and structured categories. It does not
store final vector indices or normalization constants.

Every Part-A card ID appears in the coverage registry, even if its payload is simply a
verified `generic_exact`, `ordinary_field`, or `no_non_obvious_effect` verdict. A smaller
override view may contain only cards requiring special behavior, but it is derived from
the complete coverage registry and may not be maintained independently.

## Required schema

The exact syntax may be Python plus a generated JSON snapshot, but the canonical schema
must include:

```text
registry_schema_version
source_catalog_hash
source_audit_hash
engine_version_or_hash
cards: {
  <integer card_id>: {
    identity: {name, class, subtype},
    coverage_verdict,
    attacks: [ordered semantic records...],
    abilities: [ordered semantic records...],
    effects: [Trainer/Tool/Stadium/Energy or cross-card records...],
    calculations: [formula references and raw output contracts...],
    engine_refs: [...],
    validation_refs: [...],
    integration_notes: [...]
  }
}
```

Attack and ability arrays preserve source identity/order explicitly; they must not inherit
the old encoder's two-attack/one-ability truncation. Records use named semantic fields,
raw values, scope, timing, conditions, stochasticity, and targets rather than positional
embedding arrays.

## Formula registry

Dynamic calculations live in a separately enumerable formula registry keyed by stable
names. Each formula entry includes:

- formula key and schema version;
- affected card/effect records;
- typed input contract and observability (`current`, `tracker`, or `hidden`);
- output name/unit/meaning;
- deterministic algorithm or expression;
- bounds and fallback/unknown behavior;
- order-of-operations notes;
- engine and scenario-test references.

If executable pure helpers are supplied, the declarative metadata remains canonical and
the executable result must be parity-tested against it. Do not embed arbitrary opaque
lambdas inside card entries.

## Small-step build plan

### C0 — Freeze approved inputs

1. Hash the completed Part-A catalog and Part-B audit artifacts.
2. Assert zero unresolved required verdicts.
3. Freeze registry/formula schema versions.

Completion condition: the precise evidence set being compiled is immutable and recorded.

Validation: hash and exact-ID coverage checks pass before generation begins.

### C1 — Generate the complete coverage registry

1. Create one card entry for every Part-A ID.
2. Preserve all attacks/abilities/effects and approved verdicts in source order.
3. Attach provenance, engine, and validation references.
4. Reject missing required fields, duplicate IDs, unknown verdicts, and dangling formula
   or evidence references.

Completion condition: registry key set equals the Part-A catalog key set exactly.

Validation: schema validation, set equality by class, and audit-to-registry row-count
reconciliation.

### C2 — Generate the integration/override views

1. Derive lists for exact card-ID categorical identity, stratified Pokémon/Trainer/Energy.
2. Derive the special-override subset from coverage verdicts.
3. Derive the formula registry and reverse index formula → affected cards.
4. Emit Python-consumable and language-neutral JSON forms from one canonical source.

Completion condition: all derivative views regenerate without manual edits and point
back to canonical card records.

Validation: Python/JSON semantic parity, pairwise-disjoint class lists whose union equals
all IDs, and reverse-index round trips.

### C3 — Formula and semantic regression suite

1. Port every approved Part-B scenario fixture into registry-level tests.
2. Test positive, negative, boundary, stacking, suppression, expiry, and hidden-input
   behavior as applicable.
3. Snapshot canonical payloads and formula outputs.
4. Add “but no more” tests for nearby cards/mechanics that must remain generic.

Completion condition: every override and formula has a direct test reference and all
approved scenarios pass.

Validation: focused registry tests plus exact pre-approved audit/registry diff; no
unexplained semantic field changes.

### C4 — Consumer contract and handoff package

Write a concise handoff README that tells the next instance:

- which file is canonical and how to load it;
- schema/version/hash information;
- the exact-ID vocabulary and stable ordering rule;
- how generic fallback and card-specific precedence work;
- which fields are ordinary/delegated versus supplied here;
- how to evaluate or port dynamic calculations;
- which history/hidden-state inputs the later encoder must provide;
- how engine-baked fields avoid double counting;
- exact validation commands and expected results; and
- the explicit next task: design and wire the full observation encoding in a new spec.

Completion condition: a fresh consumer can enumerate all cards, find every override,
understand every formula input/output, and run validation without reading chat history.

Validation: perform a clean-room read/check from the README instructions and record any
missing assumption as a handoff defect.

### C5 — Final reproducibility and closure

1. Regenerate all derivative files twice from frozen inputs.
2. Compare deterministic hashes.
3. Re-run Part-A set/invariant checks, Part-B coverage checks, and all Part-C tests.
4. Record exact commands, registry counts, formula counts, hashes, and conclusions in
   `docs/experiments.md`.
5. Update `PROJECT_MEMORY.md` with the completed registry location and next-spec boundary.

Completion condition: deterministic hashes match, every validation is green, and the
handoff has no unresolved semantic or referential-integrity issue.

## Expected handoff artifacts

Under a clearly documented directory in `Imitation-Learning/`:

1. canonical complete card-ID semantic registry;
2. generated JSON/Python consumer forms;
3. formula registry and formula-to-card reverse index;
4. exact-ID lists stratified by Pokémon/Trainer/Energy;
5. override-only view;
6. schema definition and validation tests;
7. audit/engine provenance manifest; and
8. consumer README.

Exact filenames are chosen during implementation and then frozen in the README.

## Part-C acceptance criteria

- Complete registry keys equal the Part-A exact card-ID set.
- Every non-obvious Part-B verdict is represented once with no semantic loss.
- Every override/formula points to engine evidence and passing tests.
- All derivative files come from one canonical source and agree semantically.
- Stable ID ordering is numeric and deterministic.
- No positional final-embedding layout is imposed.
- Generic fallback behavior is documented for unseen IDs.
- The handoff is self-contained and ready for a separate encoder implementation spec.

## Out of scope

- Editing the final observation encoder or model.
- Selecting tensor shapes, feature indices, or normalizations.
- Training or evaluating imitation-learning performance.
- Manually expanding the exhaustive registry to unseen cards.

## Completion record

Completed on 2026-07-15.

- C0: nine approved catalog/audit/engine/schema inputs are frozen by path, size, and
  SHA-256 in `Imitation-Learning/meta-card-registry/provenance.json`. Registry and
  formula schema versions are both `1.0.0`.
- C1: `registry.json` contains exactly 232 numerically ordered exact card-ID keys and
  all 314 source-ordered attack/ability/effect rows, with no truncation or unresolved
  verdict.
- C2: generated views contain the disjoint 115 Pokémon / 99 Trainer / 18 Energy ID
  vocabulary, 201 override-bearing cards / 237 special effect rows, and 79 formulas
  with round-tripping card/effect reverse indexes. JSON and Python views agree.
- C3: all 237 serialized formula scenarios pass, every effect retains validation and
  engine references, and nearby cards without special verdicts remain absent from the
  override view.
- C4: `Imitation-Learning/meta-card-registry/README.md` documents canonical loading,
  precedence, unseen fallback, formula inputs/outputs, delegated ordinary fields,
  double-count protection, validation, and the next-spec boundary. Its Python example
  succeeds without audit prose or chat history.
- C5: all 100 focused Spec-12 tests pass. Eleven generated files reproduce byte-for-byte
  across consecutive builds; exact hashes are frozen in `artifact-manifest.json` and
  `docs/experiments.md`.
- Post-closure cleanup on 2026-07-16 preserved printed attack cost/damage in every attack
  row, reconciled dynamic damage-profile bounds with the final formula registry, and
  expanded the consumer README with concrete complex-card and semantic-encoding examples.
  All 20 current Part-C checks pass after regeneration.

Spec 12 is complete. A new specification owns the final observation layout, masks,
normalization, tracker interfaces, encoder wiring, and imitation-learning integration.
