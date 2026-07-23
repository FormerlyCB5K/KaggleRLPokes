# Ceruledge-RL Specifications

This directory contains the current implementation plan and completed design contracts
for the Ceruledge policy.

## Active

- [`16-generalized-action-space.md`](16-generalized-action-space.md) — a deck-agnostic
  action space, a new from-scratch policy model consuming spec 13a/15's 174-word
  observation, and an imitation-learning training pipeline over recorded ladder games.
  Independent of `Ceruledge-RL/actions.py`/`model.py`/`train.py`, which continue running
  unchanged. Broken into:
  - [`16a-action-classification.md`](16a-action-classification.md) — verb vocabulary +
    universal per-`OptionType` candidate resolution.
  - [`16b-model-architecture.md`](16b-model-architecture.md) — tensor packing, transformer
    body, Stage 1/Stage 2 heads (placeholder-precision v1).
  - [`16c-imitation-learning.md`](16c-imitation-learning.md) — data extraction, label
    construction, loss, training loop.
- [`15-live-engine-adapter.md`](15-live-engine-adapter.md) — the adapter that builds
  spec 13a's `GameState` from the real `cg_download.api.Observation` wire format, so
  `build_observation()` can run against a live/replayed game instead of hand-built test
  fixtures. Implemented and validated 2026-07-22 (`Imitation-Learning/observation/
  live_adapter.py`): fixture unit tests plus an end-to-end run against 2,170 real states
  from recorded Top-ladder episodes, zero exceptions. Model/training integration
  (consuming the resulting `Word` list) remains a separate future spec.
- [`14-effect-baking-audit.md`](14-effect-baking-audit.md) — redo of effect baking
  (Tools/Stadiums/Abilities → KO math) for the symmetric any-deck design, scoped to the
  meta card pool only. Audit complete: HP and resistance need no baking at all (engine
  already resolves HP; resistance can never change); retreat cost, weakness, attack cost,
  and flat damage deltas still do. Candidate list and new condition predicates locked.
- [`13-card-zone-observation-space.md`](13-card-zone-observation-space.md) — card-zone
  words (hand/discard/deck/prizes/Stadium), attachment/evolution/Tool representation, and
  global state, building on spec 11's Pokémon word. Design phase. Broken into:
  - [`13a-observation-space-design.md`](13a-observation-space-design.md) — the design
    itself: fixed-capacity padded zone arrays, compact attachment/Tool fields (no separate
    binding mechanism needed), PAD/UNK masking behavior. **174-word budget locked
    2026-07-16.**
- [`11-pokemon-word-observation-encoding.md`](11-pokemon-word-observation-encoding.md) —
  overview for the any-deck Pokémon board-slot observation encoding: static/live word
  split, card-ID embedding, and design philosophy. Design complete and transcribed into
  tested standalone code under `Imitation-Learning/observation/`; live-engine integration
  is complete (spec 15), training integration remains open. Broken into:
  - [`11a-pokemon-attribute-tag-vocabulary.md`](11a-pokemon-attribute-tag-vocabulary.md) —
    completed and independently re-verified Pokémon attack/ability tag vocabulary,
    transcribed into the observation package.
  - [`11b-trainer-energy-tag-vocabulary.md`](11b-trainer-energy-tag-vocabulary.md) — the
    completed and independently re-verified Trainer/Energy vocabulary, also transcribed
    into the observation package.
- [`10-archaludon-opponent.md`](10-archaludon-opponent.md) — register the public
  rule-based Archaludon agent (`sample-archaludon/`, repo root) as a pool opponent.
  Implemented 2026-07-15; all validation steps green (self-test, pool, dispatch,
  smoke train).
- [`09-opponent-pool.md`](09-opponent-pool.md) — **overview/index** for the per-episode
  sampled multi-agent opponent pool. Current phase. Broken into five independently
  buildable parts, each with validation steps and success conditions:
  - [`09a-registry-and-loading.md`](09a-registry-and-loading.md) — registry, collision-safe
    loader, deck resolution
  - [`09b-side-aware-dispatch.md`](09b-side-aware-dispatch.md) — opponent-parameterized
    episode, side-correct decks, `--opponent` via registry
  - [`09c-pool-sampling-cli.md`](09c-pool-sampling-cli.md) — weighted per-episode sampling +
    `--opponent-pool` CLI
  - [`09d-startup-validation-and-deploy.md`](09d-startup-validation-and-deploy.md) —
    fail-fast pool validation + copy-all-folders deploy
  - [`09e-per-opponent-metrics.md`](09e-per-opponent-metrics.md) — per-opponent winrate
    logging + plots
- [`04-training-plan.md`](04-training-plan.md) — the training decisions accompanying the
  generalized encoder that motivate the pool; `09` is its concrete implementation
  contract.

## Completed

Completed specifications remain authoritative descriptions of implemented behavior and
live under [`completed/`](completed/):

- [`01-prize-tracker.md`](completed/01-prize-tracker.md)
- [`02-observation-encoding.md`](completed/02-observation-encoding.md)
- [`03-attack-ability-tagging.md`](completed/03-attack-ability-tagging.md)
- [`05-new-attack-tags-full-audit.md`](completed/05-new-attack-tags-full-audit.md)
- [`06-effect-baking.md`](completed/06-effect-baking.md)
- [`07-effect-baking-audit.md`](completed/07-effect-baking-audit.md)
- [`Spec 12 — Top-Ladder Meta-Card Registry`](completed/spec-12/README.md) — complete
  exact-ID inventory, engine-backed semantic audit, dynamic formulas, final registry,
  and consumer handoff

For a reader-oriented description of the full current model rather than an implementation
plan, start with [`../MODEL-ARCHITECTURE.md`](../MODEL-ARCHITECTURE.md).

## Historical or deferred

Superseded, incomplete, or currently irrelevant proposals are retained under
[`../old/specs/`](../old/specs/) and are not active implementation contracts.
