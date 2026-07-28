# Engine-Native Architecture

This folder is the isolated design and implementation workspace for the engine-native
architecture.

It is a new pipeline. It does not replace, extend, or share runtime state with:

- `Ceruledge-RL/`;
- `Imitation-Learning/observation/`; or
- `Imitation-Learning/policy/`.

Those implementations remain intact as historical baselines and possible test or data
references.

## Active contract

Read
[`specs/01-implementation-decisions-and-deferrals.md`](specs/01-implementation-decisions-and-deferrals.md).
The friend's reported implementation is authoritative where it conflicts with
`architecture-overview-v3.pdf`; all differences are logged in that contract.

The old [`specs/00-architecture-contract.md`](specs/00-architecture-contract.md) is a
superseded first-PDF baseline retained only for provenance.

The implementation remains free of learned card-ID and attack-ID identity tables.
Card and attack IDs select frozen mechanics only.

## Implementation status

The reference-compatible Python and imitation-data milestone is implemented:

- exact interleaved `float32[2239]` packing and typed decoding;
- installed and hash-pinned real frozen mechanics;
- pure `cg_download.api.Observation` featurization with no trackers;
- aggregate own-deck state and engine-option entity pointers;
- the exact 2,370,259-parameter network;
- fog-only value operation with retained zero-initialized oracle modules;
- single- and multi-select decoding; and
- a stateless serving wrapper;
- exact golden replay/checkpoint parity;
- direct sanitized-replay extraction with complete multi-selection labels;
- deterministic game splitting and immutable tensor-only PyTorch shards;
- mmap-backed shard-aware loading, supervised losses, and validation metrics;
- a finite real-model train-input smoke command;
- a full mixed-precision behavior-cloning trainer with complete validation, atomic
  best/latest checkpoints, and exact mid-epoch resume; and
- an automatically continued six-day SLURM training entry point.

The user reported that the six-day uncapped cluster cache and CUDA smoke completed
successfully. The full six-day optimization run remains pending.

See [`specs/02-implementation-plan.md`](specs/02-implementation-plan.md) for completed and
deferred architecture phases and
[`specs/03-imitation-data-to-train-handoff.md`](specs/03-imitation-data-to-train-handoff.md)
for the implemented data contract, and
[`specs/04-behavior-cloning-trainer.md`](specs/04-behavior-cloning-trainer.md)
for full optimizer and checkpoint semantics.

## Engine-first rule

The game engine is the primary source of live state and legality.

- Encode directly from `cg_download.api.Observation` and its nested engine objects.
- Score the legal options in `observation.select.option`; do not recreate legality.
- Read HP, conditions, attachments, turn flags, zone counts, selection context, and
  mid-effect counters from the engine when it exposes them.
- Use the submitted 60-card deck only for the acting player's known decklist and for
  count-by-elimination facts that follow from visible information.
- Keep deck and Prize contents combined as `unknown` when the engine does not reveal
  their identities. Do not infer hidden Prize identities.
- Do not introduce a parallel `GameStateTracker` or `PrizeTracker`.

Derived values are allowed only when the architecture requires them and the engine does
not provide them directly. Each such derivation must be documented with its engine inputs,
hidden-information boundary, and validation test.

## Layout

- `specs/` - architecture contracts, decisions, and implementation phases.
- `src/engine_native_policy/` - the new implementation package.
- `src/engine_native_policy/il/` - replay, target, cache, loader, loss, and trainer.
- `artifacts/` - retained real tables, schemas, checkpoint, and golden fixtures.
- `scripts/` - local cache construction, smoke, and full-training entry points.
- `cluster/` - isolated six-day cache, smoke, and full-training SLURM jobs.
- `tables/` - historical placeholder-table manifest.
- `tests/` - focused tests and engine/replay integration checks.

Start with
[`specs/01-implementation-decisions-and-deferrals.md`](specs/01-implementation-decisions-and-deferrals.md).
