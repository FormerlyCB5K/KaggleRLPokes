# 01 - Implementation Decisions and Deferrals

Status: active review contract, 2026-07-28.

This document records the decisions and assumptions approved before implementation.
It supersedes the provisional design in `00-architecture-contract.md`.

No implementation code is authorized by this document alone. The next step is a reviewed
implementation plan.

## 1. Authority and provenance

Use sources in this order:

1. the friend's executable implementation, generated artifacts, tests, and checkpoint,
   when supplied;
2. the friend's `sprint-2026-07-28-handoff` documentation and generated
   `reference/schemas.json`, as the current report of that implementation;
3. `architecture-overview-v3.pdf` where the implementation is silent;
4. the earlier architecture PDF only where it does not conflict with v3 or the
   implementation; and
5. the local `cg_download.api` and engine source for local runtime facts and adapter
   behavior.

Implementation behavior wins over v3 wherever they differ. Every such difference must be
recorded rather than silently normalized back to the document.

The handoff archive does not contain the cited implementation source, generated frozen
tables, or reference checkpoint. Claims based only on the handoff remain
**reported implementation behavior** until the corresponding source or artifact is
available for direct verification.

## 2. Locked architecture decisions

### 2.1 Observation and engine boundary

- One packed decision is `float32[2239]`.
- The physical field order is the implementation's interleaved order, not four
  contiguous conceptual blocks.
- IDs cross the flat boundary as exactly representable `float32` values and are decoded
  to `int64`; masks decode to Boolean tensors; numerics remain `float32`.
- Forty entity slots are populated dynamically in this order:
  my Active, my Bench, opponent Active, opponent Bench, my hand, Stadium.
- Bench and hand entries retain engine array order.
- The encoder is a pure function of the acting player's masked engine observation,
  current selection, acting-player index, and submitted deck.
- No persistent game-state, Prize, hidden-card, or prior-observation tracker is part of
  the policy encoder.
- Engine-provided options define legality. The model does not reconstruct legal actions.
- Local enums are mapped by symbolic member, never by copying raw integer values from the
  friend's environment. In particular, local `AreaType` numeric values differ.

### 2.2 Frozen card representation

- Card IDs and attack IDs are lookup keys only.
- There is no learned parameter indexed by card ID, attack ID, card name, printing,
  serial, or mechanical-identity ID.
- The frozen table shapes are:

  | Table | Shape | Dtype |
  |---|---:|---|
  | `STAT` | `(1300, 79)` | float32 |
  | `ATK` | `(1300, 2, 130)` | float32 |
  | `ABL` | `(1300, 130)` | float32 |
  | `PLAY` | `(1300, 130)` | float32 |
  | `PRIZE` | `(1300, 1)` | float32 |
  | `ATTACK_SLOT` | `(1600,)` | int64 |

- The learned static-card path is:
  `79 -> 32`, one frozen Prize scalar, three applications of the shared
  `130 -> 48` projection, concatenation to 177, then `177 -> 224`.
- The three static effect slots are attack 0, attack 1, and Ability. `PLAY` is not part
  of the static card row.
- Trainer and other play effects enter through option encoding only.
- Missing effects use an all-zero 130-field descriptor.
- No activation is applied in the static-card projection path.

### 2.3 Deck, attachments, and entities

- The deck summary uses repeated aggregate counts per card ID:
  `[hand, discard, in play, unknown] / 4`.
- `unknown` combines the acting player's remaining deck and Prize cards.
- The deck vector is a masked mean over nonzero deck IDs.
- FiLM is conditioned by the pooled deck vector before the deck role embedding.
- Only the first attached Tool and first attached Special Energy contribute identity.
  All attachments still contribute to counts.
- Tool and Special Energy gates are independent, bias-free, zero-initialized
  `224 -> 224` linear layers applied before FiLM.

### 2.4 Network and heads

- The transformer sequence is:
  `40 entities | deck | match | 3 registers | readout`.
- Width is 224; there are four pre-norm layers, four heads, FFN width 448, GELU,
  zero dropout, no positional encoding, and a final LayerNorm.
- The three registers and readout are one learned `(4, 224)` parameter initialized from
  `Normal(0, 0.02)`.
- FiLM modifies only the 40 entity tokens and starts as the exact identity transform.
- The policy and include heads are independent
  `672 -> 224 -> 1` MLPs with GELU.
- The value head is `224 -> 224 -> 1` with GELU and no output activation.
- The value predicts a shaped, discounted GAE return, not win probability.
- The implemented model, including the oracle modules, has 2,370,259 parameters.

### 2.5 Options and decoding

- An attack option points to the attacker. Its card and entity pointer both resolve to my
  Active, while its target card is zero.
- The option vector sums option-type, card, target-card, selected frozen effect,
  four-numeric, and projected post-transformer entity terms.
- One `130 -> 224` option-effect projection is shared across attack, Ability, Skill,
  and play effects.
- Missing card, target, and attack use index 0. Missing entity uses `-1`, remapped to a
  learned 224-wide no-entity vector.
- Single-select decoding uses the policy argmax.
- Multi-select decoding uses only sigmoid include scores, threshold 0.5, followed by
  deterministic projection to `minCount` and `maxCount`.
- Repeated prompts are stateless separate decisions.

### 2.6 Training and serving

- The reference training design is self-play PPO with a PFSP snapshot league.
- Multi-select actions use a factorized Bernoulli policy-gradient path rather than a
  separate supervised include loss.
- The public value target uses shaped rewards with GAE, `gamma=0.997` and
  `lambda=0.99`.
- Serving uses the same Python model and frozen table artifacts; no quantization, ONNX,
  tracing, or scripting is part of the reported implementation.
- Contrary to v3, the oracle modules remain in the served state dict and are structurally
  required by the reported loader.

## 3. Approved temporary assumptions

### 3.1 Placeholder tables

Implementation may proceed with correctly shaped, correctly typed placeholder tables
until the friend's real artifacts arrive.

- Placeholders are provisional artifacts, not inferred card mechanics.
- Placeholder mechanical rows are zero.
- `ATTACK_SLOT` uses zero as its provisional slot.
- Tests may inject synthetic nonzero tables to exercise lookup, sharing, and option
  selection paths.
- Placeholder artifacts must carry an unmistakable provisional marker and must not be
  presented as semantically valid.
- Meaningful training, gameplay evaluation, collision analysis, and card-mechanics
  acceptance remain blocked until the real tables replace the placeholders.
- Replacing placeholders must not require a model-architecture or observation-schema
  change.

### 3.2 Oracle module present but inactive

Oracle-assisted training is deferred, but the architecture remains compatible with the
friend's implementation:

- `ora_zone_emb: Embedding(8, 224)` remains present;
- `ora_proj: Linear(224, 224)` remains present and zero-initialized;
- both remain in model state dicts and parameter counts;
- no privileged `ora_*` inputs are constructed or supplied for now;
- oracle-to-fog distillation is disabled while oracle inputs are unavailable; and
- the ordinary fog value path remains usable.

No hidden identities may be reconstructed using a tracker as a substitute for the
deferred engine-native omniscient training interface.

### 3.3 Compatibility and implementation order

- Target state-dict compatibility with the friend's implementation wherever the handoff
  determines module names, shapes, and behavior.
- Implement the Python engine-native encoder/model/serving path first.
- Add the native/C++ featurizer mirror and bit-for-bit parity testing later.
- Keep self-play PPO/PFSP in the overall scope, after the observation, tables, model,
  option path, and serving path are validated.

### 3.4 Existing edge behavior

To remain as unchanged as possible, reproduce the reported behavior:

- card and attack IDs are reduced modulo their vocabulary sizes;
- entities beyond 40 are silently omitted after preserving the first 40;
- options beyond 64 are silently omitted after preserving the first 64;
- the first two attacks are retained;
- a second Ability/skill is dropped;
- the first qualifying Tool and Special Energy supply attachment identity; and
- no overflow indicator is added to the model input.

Tests must document these behaviors. Additional diagnostics may observe them, but must
not change the encoded result or action choice.

### 3.5 Unspecified no-entity initialization

The handoff identifies a learned 224-wide `no_entity` parameter but does not state its
initialization. The provisional implementation initializes it to zero.

- This does not affect loading a supplied checkpoint because checkpoint weights replace
  the initialization.
- Confirm the friend's source initialization before treating a fresh training run as
  exactly reproducible.
- A source-confirmed difference may change initialization only; it must not change the
  parameter's shape, role, or state-dict key.

## 4. Differences from architecture-overview-v3

The implementation is authoritative for each row.

| Topic | V3 | Reported implementation |
|---|---|---|
| Served oracle block | removed at export | retained and required by loader |
| Served parameters | about 2.32M | 2,370,259 |
| Value meaning | win probability | shaped discounted return |
| Attack entity link | defender/hit Pokémon | attacker/my Active |
| Deck zones | physical-copy location | repeated aggregate counts per card ID |
| Static third effect | suggests shared dictionary including play effects | always Ability; `PLAY` is option-only |
| Physical flat layout | four contiguous blocks | late-appended deck-zone and attachment arrays |
| Entity allocation | implies fixed subranges | dynamic append order |
| Typed live Energy counts | normalization omitted | each divided by 5 |
| CPU latency | about 0.58 ms at batch 64 | no checked-in benchmark evidence |

Other v3 claims remain accepted where the handoff does not report a conflict.

## 5. Deferred work

### 5.1 External dependencies

- Receive the friend's real frozen tables.
- Receive table manifests, schema/version identifiers, and hashes.
- Preferably receive the table generators and their engine binding output.
- Obtain a hash or exact revision for the friend's `Types.h`.
- Optionally obtain the reference checkpoint for direct compatibility validation.
- Confirm the fresh initialization of the learned `no_entity` vector.

### 5.2 Oracle-assisted training

- Identify or build an engine-native omniscient training-state interface.
- Determine the exact ordering and overflow behavior of the 66-card oracle input.
- Verify the exact oracle-to-fog distillation coefficient and training path.
- Add privileged-input isolation and gradient-flow tests.

### 5.3 Native and performance work

- Port the Python featurizer to the native path.
- Add Python/native bit-for-bit parity tests.
- Build a reproducible serving-bundle/export command.
- Add CPU latency and throughput benchmarks.

### 5.4 Training and evaluation

- Implement and validate the full PPO/PFSP loop.
- Recover the complete reference-run configuration, random seeds, reward parameters,
  and checkpoint/resume behavior.
- Reproduce gameplay and FiLM measurements only when their scripts, checkpoints, and
  metric definitions are available.

### 5.5 Frozen-table audit

- Verify deterministic generation and complete card/attack coverage.
- Audit mechanically identical collision groups and obtain the exact affected IDs.
- Confirm the friend's engine/database revision matches the local engine.
- Validate cards with multiple skills and all zero/fallback descriptor rows.

## 6. Facts already checked in the local engine

The local engine currently reports:

- card IDs 1 through 1267;
- attack IDs 1 through 1556;
- no card with more than two attacks; and
- five cards with two skills: IDs 1099, 1136, 1138, 1150, and 1151.

These establish local runtime facts, not proof that the friend's frozen tables were
generated from the identical engine revision.

## 7. Review status

No further architecture question is currently blocking the implementation plan.

The remaining unknowns are artifact provenance and deferred evidence, not permission to
invent missing mechanics. If later source code contradicts the handoff, update this
contract, record the discrepancy, and use the implementation as ground truth.
