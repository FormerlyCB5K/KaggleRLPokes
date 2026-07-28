# 02 - Implementation Plan

Status: Python foundation complete, 2026-07-28.

This plan implements the active decisions in
`01-implementation-decisions-and-deferrals.md`. It deliberately excludes work already
approved for deferral.

## Phase 1 - Isolated package and schemas

Status: complete.

- Create an installable package under `src/engine_native_policy/`.
- Pin every observation capacity, width, role, and option type in one schema module.
- Pin the ordered stat/effect layouts and reported frozen-feature vocabularies.
- Keep all runtime imports independent of existing Ceruledge and imitation-learning
  observation packages.

Acceptance:

- conceptual widths equal 1,280 entities, 300 deck, 18 match, and 641 options;
- physical flat width equals 2,239;
- transformer length equals 46; and
- literal tests pin all physical offsets.

## Phase 2 - Frozen-table boundary and flat interchange

Status: complete with provisional mechanics.

- Define the exact six-table shape/dtype contract.
- Supply explicit zero-filled provisional tables for architecture work.
- Register frozen mechanics as non-persistent model buffers.
- Implement variable-length features, first-N packing, and typed batch decoding.
- Prevent normal serving construction from silently accepting provisional tables.

Acceptance:

- placeholder tables validate against exact shapes and dtypes;
- replacement does not change the model schema;
- IDs/masks/numerics restore to `int64`/Boolean/`float32`; and
- first-40/first-64 behavior is tested.

Semantic card-mechanics acceptance remains blocked pending the real tables.

## Phase 3 - Pure engine-native featurizer

Status: complete.

- Consume only `cg_download.api.Observation` and the acting player's submitted deck.
- Build dynamic entity order and entity-pointer map in one pass.
- Encode all 27 live numerics, attachment identities, match state, aggregate deck zones,
  and legal options.
- Map engine enums symbolically.
- Ignore logs, prior observations, and hidden-state trackers.

Acceptance:

- mock-engine tests cover ordering, statuses, attachments, aggregate deck counts,
  attacker pointers, targets, numerics, and modulo behavior;
- hidden-information independence is tested by changing logs without changing features;
  and
- a real engine battle reaches setup and Active-board frames without adapter failure.

## Phase 4 - Network, heads, and oracle-compatible fog path

Status: complete.

- Implement frozen card projections and shared option effects.
- Assemble board, deck, match, register, and readout tokens.
- Implement board-only zero-initialized FiLM and attachment gates.
- Implement the four-layer pre-norm transformer.
- Implement independent policy/include heads and the shaped-return value head.
- Retain zero-initialized oracle modules while allowing fog-only operation.

Acceptance:

- instantiated trainable parameter total equals 2,370,259;
- every reported module count is pinned in a test;
- no learned card-ID or attack-ID embedding exists;
- frozen tables are absent from the state dict;
- padding masks and finite include sentinels are tested; and
- zero-initialized FiLM, gates, and oracle correction are invariant at initialization.

## Phase 5 - Decoding and serving

Status: complete for the Python path.

- Implement policy argmax for single selections.
- Implement include-threshold decoding and deterministic bound projection for
  multi-selections.
- Provide a stateless serving wrapper returning engine option indices.
- Require an explicit test override to run with provisional tables.

Acceptance:

- unit tests cover thresholding, min/max projection, and tie-breaking; and
- a live engine smoke accepts ten consecutive choices from the wrapper.

## Phase 6 - Validation and handoff

Status: complete for the provisional Python milestone.

- Run focused tests and bytecode compilation.
- Record exact verified behavior and remaining limitations.
- Keep v3 discrepancies and deferred work linked from the package README.

## Deferred phases

These remain out of the current implementation:

1. construct engine-native omniscient oracle training inputs and enable distillation;
2. implement native/C++ featurization and Python/native bit parity;
3. implement the full behavior-cloning trainer after the tensor-cache cluster smoke;
4. implement full PPO/PFSP training and checkpoint/resume;
5. build reproducible serving bundles; and
6. reproduce collision, FiLM, status-use, gameplay, and CPU-latency measurements.

None of these deferrals permits use of a parallel policy-time game-state or Prize tracker.

The real frozen mechanics, artifact hashes, exact checkpoint compatibility, golden replay
parity, and the data-to-train milestone are now implemented. See
`03-imitation-data-to-train-handoff.md`; the uncapped six-day cluster build and CUDA smoke
are still pending.
