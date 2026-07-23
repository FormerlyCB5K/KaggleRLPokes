# 12 — Top-Ladder Meta-Card Registry (Overview)

Status: **COMPLETE — Parts A, B, and C accepted; encoder implementation is a new spec**

## What this is

Build a reproducible, exact-card-ID inventory of every card submitted in the available
top-ladder episode datasets, then exhaustively audit those cards' non-obvious mechanics
against both their natural-language card text and the open-source game engine. Publish
the result as a versioned, card-ID-keyed semantic registry that another implementation
instance can compile into the future imitation-learning observation encoder.

This is deliberately a registry and evidence task, not the final encoder task. The
future encoder will combine these results with ordinary state and printed-card fields
such as current/max HP, retreat cost, type, Weakness, Resistance, and `new_in_play`.

In this spec, the earlier phrase “species one-hot” means **an exact card-ID categorical
identity**. Biological species, alternate forms, owners, and printings are not collapsed.

## Governing philosophy

> Accurate game representation of meta-relevant cards at all costs, with reasonable
> fallbacks for never-before-seen cards.

Consequences:

- Every exact card ID appearing in a top-ladder deck is mandatory audit scope, even if
  it appears only once.
- Frequency controls review order and reporting, never whether a card is covered.
- Generic text extraction remains valuable and is the fallback for unseen cards, but a
  generic result is accepted for a meta card only after it is verified as semantically
  exact for that card.
- Card-ID overrides and board/history-dependent calculations are preferred whenever
  they are necessary for fidelity.
- Unknown or hidden information is represented explicitly; it must not be replaced by
  a falsely exact value.
- No mechanic is accepted solely from remembered game knowledge. Card text and engine
  behavior/source are the evidence.

## Build order and parts

1. [`12a-top-ladder-card-inventory.md`](12a-top-ladder-card-inventory.md) — stream the
   archives, extract both submitted 60-card decks from each episode, produce a
   stratified exact-ID catalog with frequency/provenance, validate first on `7-12`, and
   then run every archive in `Imitation-Learning/Top-ladder-data/`.
2. [`12b-meta-card-semantics-audit.md`](12b-meta-card-semantics-audit.md) — after the
   user supplies the open-source engine, inspect every observed Pokémon, Trainer, and
   Energy card; compare natural text, generic extraction, existing overrides, and
   engine behavior; specify exact static overrides and dynamic calculations. Part B is
   itself split into nine gated steps (`B01`–`B09`) with ≤20-card audit batches.
3. [`12c-card-id-registry-and-handoff.md`](12c-card-id-registry-and-handoff.md) — compile
   all approved verdicts into a versioned card-ID registry, regression-test it, and
   prepare a self-contained handoff for the separate encoder implementation spec.

Dependencies: `12a → 12b → 12c`. Part `12b` has a hard engine-handoff gate.

## Shared terms

- **Episode**: one JSON member of a dated top-ladder ZIP archive.
- **Deck instance**: one player's submitted deck in one episode. Identical deck lists in
  different games remain distinct instances for frequency counts.
- **Meta card**: any exact card ID found in at least one accepted deck instance.
- **Card class**: one of `pokemon`, `trainer`, or `energy`, derived from the English card
  database's stage/type field.
- **Generic result**: semantics produced without a card-ID-specific override.
- **Override**: card-ID-specific semantic data needed to correct or complete the generic
  result.
- **Dynamic calculation**: a reviewed formula whose result depends on observable board
  state, tracked history, or a declared hidden/unknown input.
- **Non-obvious mechanic**: any attack, ability, Trainer, Tool, Stadium, or Energy effect
  that is not faithfully represented by the ordinary printed/static fields delegated
  to the later encoder task.

## Canonical data flow

```text
dated ZIP archives
    -> validated episode/deck extraction
    -> exact card-ID catalog + frequency/provenance
    -> per-card text/engine audit ledger
    -> approved semantic overrides and calculations
    -> versioned card-ID registry + integration handoff
```

All machine-readable outputs use raw semantic units (HP, card counts, Energy counts,
Boolean capabilities, timing/scope, and formula operands). This spec does **not** choose
the final neural-vector dimensions or normalization constants.

## Whole-feature acceptance criteria

- Every archive present at execution time is inventoried by path, size, SHA-256, member
  count, and processing outcome.
- Every accepted episode contributes exactly two validated 60-integer deck lists; any
  exception is recorded and resolved rather than silently skipped.
- Every observed card ID is retained, classified, and traceable to dataset date(s) and
  aggregate deck/game/copy counts.
- The union and all frequency metrics are reproducible from frozen inputs and stable
  across repeated runs.
- Every observed exact card ID receives an explicit Part-B verdict. All non-obvious
  mechanics are either engine-verified and represented or clearly marked unresolved;
  unresolved required cases block Part C.
- Every dynamic calculation has source evidence plus positive, negative, and boundary
  validation scenarios.
- The final registry is keyed by integer card ID, versioned, deterministic, documented,
  and mechanically consistent with the Part-A catalog and Part-B audit ledger.
- A separate instance can consume the handoff without rereading this conversation or
  reverse-engineering audit artifacts.

## Explicitly out of scope

- Designing or wiring the final observation tensor, one-hot layout, model architecture,
  or imitation-learning pipeline.
- Re-encoding ordinary printed/current fields that the later encoder can consume
  directly: current/max HP, base retreat, type, Weakness, Resistance, and basic
  in-play/turn flags.
- Training a model or claiming improvements in model performance.
- Treating historical files under `Ceruledge-RL/old/` as current contracts.
- Expanding the mandatory manual audit to cards absent from all top-ladder datasets.
  Such cards receive the generalized fallback in the later encoder.

## Decisions from the design interview (2026-07-15)

- All three parts will be completed in this session, with Part B paused until the user
  supplies the open-source engine.
- The Part-A output is a reproducible catalog with card metadata, dates, frequencies,
  copy counts, and provenance—not merely a set of IDs.
- Exact card ID is the identity unit; biological species identity is irrelevant here.
- Every top-ladder Pokémon, Trainer, and Energy card is mandatory audit scope.
- Accuracy for observed meta cards takes precedence over minimizing hand-authored logic.
- Spec 12 produces the difficult semantic registries and calculations only. A later spec
  owns final feature compilation and common state/static fields.

## Open questions

None. Spec 12 is complete. The next task is a separate specification for the full
observation encoding and imitation-learning pipeline integration.
