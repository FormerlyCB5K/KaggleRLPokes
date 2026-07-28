# 03 - Engine-Native Imitation Data-to-Train Handoff

Status: implemented locally; uncapped six-day cluster acceptance pending, 2026-07-28.

This handoff defines the shortest correct path from the already-sanitized TEST ladder
replays to supervised batches for the engine-native policy. It covers extraction,
immutable tensor caching, game-level splitting, data loading, tensor preparation,
behavior-cloning losses, validation, and the six-day cluster smoke run.

It does **not** reuse the previous imitation model's observation, action, candidate,
tracker, cache, or training-example classes. The only retained replay facts are generic
facts verified directly against the sanitized episode format.

## 1. Objective and scope

Build and validate the data-to-train pipeline on every sanitized episode from:

```text
7-12, 7-13, 7-14, 7-23, 7-24, 7-25
```

Cluster source root:

```text
/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/
  Imitation-Learning/Top-ladder-data/sanitized/
```

Each day is expected at `<source-root>/<day>/`, with one compact
`<episode_id>.json` per retained game and one excluded `report.json`.

“TEST” means this is the reduced six-day end-to-end corpus, not that all examples are
evaluation examples. It still receives a deterministic game-level train/validation
split. It must remain separate from any later 14-day production cache.

The v1 training objective is behavioral cloning of action choice only:

- the policy logits learn single selections;
- the include logits learn multi-selections; and
- the value head receives no supervised target.

Oracle inputs, oracle distillation, PPO, PFSP, replay-derived value targets, class
balancing, and rare-context oversampling remain outside this handoff.

## 2. Preconditions that must be completed first

Do not build the final cache with a featurizer known not to match the supplied golden
implementation.

1. Replace the provisional frozen tables with the supplied real artifacts and validate
   their manifest and hashes before constructing a trainable model.
2. Correct replay area handling: integer-valued `area` and `inPlayArea` fields must be
   converted through the local `cg_download.api.AreaType` before symbolic lookup.
3. Normalize all option numerics by 10:
   `[number, count, minCount, maxCount] / 10`.
4. Add a permanent golden test using the supplied replay and reference checkpoint. It
   must reproduce the expected flat-feature hash, policy logits, include logits, and
   value.
5. Increment and pin an engine-native featurizer/schema version in the cache manifest.

The real frozen tables are required for training but do not need to be duplicated into
every cached example. The cache stores observations and labels, not card mechanics.

## 3. Source replay contract

Use the sanitized JSON without engine replay or inferred state.

### 3.1 Authoritative replay facts

- `steps[i][player].action` answers
  `steps[i - 1][player].observation`.
- A player's submitted deck is the unique action in the episode containing exactly 60
  integer card IDs for that player.
- `observation.select.option` is the ordered engine legal-option list.
- An action is a list of indices into that exact list. Preserve the complete list; never
  reduce it to `action[0]`.
- `observation.select.usable == false` identifies a forced/no-choice frame that should
  not contribute a supervised example.
- The observation is already masked to the acting player's allowed information.
- The submitted acting deck may be supplied to the engine-native featurizer.

### 3.2 Per-episode extraction algorithm

For each day and episode filename in sorted order:

1. Ignore `report.json`.
2. Load the episode JSON.
3. Scan the complete `steps` list and extract one authoritative 60-card deck for each
   player. Missing or conflicting submissions are hard errors.
4. For response step `i` from 1 through the end of the episode, and for each player:
   - read `action = steps[i][player].action`;
   - read `obs_json = steps[i - 1][player].observation`;
   - require a non-empty action, `obs_json.current`, and `obs_json.select`;
   - skip when `select.usable` is false;
   - convert `obs_json` directly to `cg_download.api.Observation`;
   - featurize it with that player's submitted deck;
   - encode the result with the canonical engine-native `float32[2239]` encoder; and
   - construct the target from the complete action list.

Use the complete episode. The final TEST cache has no `max_steps` truncation. A
developer-only sample limit may exist for local smoke tests, but it must be recorded in
the manifest and may not share the final TEST cache directory.

The extractor must not instantiate or import `PrizeTracker`, `GameStateTracker`, the
174-word observation encoder, a candidate classifier, or a staged action vocabulary.
Logs and earlier observations are not inputs to featurization.

### 3.3 Target classification and validation

Let:

```text
n_options = len(observation.select.option)
minimum   = observation.select.minCount
maximum   = observation.select.maxCount
selected  = action
is_multi  = maximum > 1
```

For every emitted example:

- require `2 <= n_options <= 64`;
- require every selected value to be an integer in `[0, n_options)`;
- require selected indices to be unique;
- require the encoded `n_options` and option mask to agree with the source;
- for a single selection, require `len(selected) == 1`;
- for a multi-selection, require `minimum <= len(selected) <= maximum`; and
- for a multi-selection, set one target bit for every selected option.

Classification is based on `maximum > 1`, not on the observed action length. A
multi-select prompt can legally produce a one-element action.

Frames with more than 64 legal options are skipped and counted as
`option_overflow`; they are not silently relabelled against a truncated legal set.
Unexpected invalid indices, duplicate selections, cardinality violations, missing
decks, or source/encoded option disagreement are hard build failures, because they
indicate a pairing or schema error rather than ordinary dirty data.

The declared non-example categories are:

```text
no_action
no_current
no_select
unusable
fewer_than_two_options
option_overflow
```

All six counts must be recorded by day. No other silent skip path is permitted.

## 4. Canonical cached dataset format

Use uncompressed, tensor-only PyTorch shards. This is the simplest format that:

- writes in one streaming pass;
- does not retain millions of Python objects;
- is immediately consumable by `torch.utils.data`;
- preserves the exact canonical flat encoder output;
- supports memory-mapped loading with current PyTorch; and
- avoids spending cluster CPU time decompressing every epoch.

Do not use pickle files of custom `Example` objects, JSON as the training-time format,
compressed NPZ, Parquet list columns, or one monolithic tensor for an entire day.

### 4.1 Directory layout

```text
Imitation-Learning/Top-ladder-data/engine-native-cache-test-six-days/
  manifest.json
  split.json
  episode-table.json
  train/
    shard-000000.pt
    shard-000001.pt
    ...
  validation/
    shard-000000.pt
    ...
```

The actual cluster cache may live on scratch/GPFS outside the repository. The path above
is a logical layout, not a requirement to commit generated data.

### 4.2 Shard contents

Each shard is a `torch.save` dictionary containing tensors only:

```python
{
    "features":       float32 [N, 2239],
    "is_multi":       bool    [N],
    "single_target":  int64   [N],
    "multi_target":   bool    [N, 64],
    "n_options":      uint8   [N],
    "min_count":      uint8   [N],
    "max_count":      uint8   [N],
    "origin":         int32   [N, 3],
}
```

Field semantics:

| Field | Meaning |
|---|---|
| `features` | Exact output of `engine_native_policy.flat.encode` |
| `is_multi` | `select.maxCount > 1` |
| `single_target` | Selected option index for single rows; `-100` for multi rows |
| `multi_target` | 64-wide multi-hot selected-option target; all false for single rows |
| `n_options` | Number of live engine options, 2 through 64 |
| `min_count` / `max_count` | Unnormalized source cardinality bounds |
| `origin[:, 0]` | Index into `episode-table.json` |
| `origin[:, 1]` | Acting player index |
| `origin[:, 2]` | Response-step index `i` whose action supplied the label |

`episode-table.json` maps the stable integer episode index to the day and filename. This
keeps the hot tensors compact while retaining exact traceability to the source frame.

Target tensors use storage-efficient types. The loader converts `multi_target` to the
logit dtype and already receives `single_target` in the `int64` dtype required by
cross-entropy.

### 4.3 Sharding rules

- Target approximately 8,192 examples per shard.
- Finish the current episode before flushing, so a game is never split merely to hit
  the target size.
- Never mix train and validation games in one shard.
- Write to a temporary sibling path, flush and close it, calculate SHA-256, then rename
  atomically to the final shard name.
- A rerun may reuse a shard only when the manifest, source inventory, split hash,
  featurizer version, and shard hash all agree.
- Partial or unmanifested shards are never training inputs.

At 8,192 rows, the flat feature tensor is about 70 MiB. This keeps individual loads
reasonable while avoiding thousands of tiny files.

### 4.4 Required manifest

`manifest.json` must contain:

- schema name and version: `engine-native-il-v1`;
- flat dimension and all tensor names, shapes, and dtypes;
- repository revision, when available;
- engine-native featurizer version;
- frozen-table manifest hash used by the intended model;
- exact requested days and sanitized source root;
- source inventory hash over sorted day/filename/file-size tuples;
- split seed, split hash, and validation fraction;
- total games and examples by split and day;
- single- and multi-select example counts;
- histograms for `n_options`, `min_count`, `max_count`, and selected count;
- all declared skip counts by day;
- every shard's path, row count, byte size, and SHA-256; and
- build start/end time and host.

`report.json` files from sanitization should be summarized in the manifest and checked
against the discovered episode-file count, but are never examples.

## 5. Deterministic game-level split

Build the split before featurizing:

1. Inventory every requested `<day>/<episode_id>.json`.
2. Form the stable game key `<day>/<episode_id>`.
3. Sort all keys.
4. Shuffle once with seed `20260728`.
5. Set `n_validation = max(1, round(0.10 * n_games))`; assign the first
   `n_validation` shuffled keys to validation and the remainder to training.
6. Save every assignment and a hash in `split.json`.

The seed must remain a command-line option, with `20260728` as the checked-in TEST
default. A resumed or repeated cache build must load the existing split rather than
create a new one.

`split.json` has this logical schema:

```json
{
  "schema_version": 1,
  "seed": 20260728,
  "validation_fraction": 0.1,
  "source_inventory_hash": "...",
  "train": ["7-12/85480905.json"],
  "validation": ["7-12/85481000.json"],
  "split_hash": "..."
}
```

No episode may occur in both splits. Splitting decisions from one game across train and
validation is forbidden.

## 6. Standard PyTorch loading and tensor preparation

Implement a shard-backed `torch.utils.data.Dataset` plus an efficient sampler:

- load shards with `torch.load(..., map_location="cpu", weights_only=True, mmap=True)`;
- validate shard keys, dtypes, shapes, and manifest hash on first access;
- shuffle train shard order each epoch;
- shuffle row order within each train shard;
- keep validation shard and row order fixed;
- batch with the ordinary PyTorch `DataLoader`;
- use pinned host memory, persistent workers, and non-blocking device copies when CUDA
  is selected; and
- expose deterministic worker and epoch seeding.

Use a shard-aware batch sampler instead of globally random individual indices. Global
random indexing would thrash hundreds of memory-mapped files while providing no useful
statistical advantage over independently shuffled shards and rows.

The collated batch contract is:

```python
{
    "features":       torch.float32 [B, 2239],
    "is_multi":       torch.bool    [B],
    "single_target":  torch.int64   [B],
    "multi_target":   torch.bool    [B, 64],
    "n_options":      torch.uint8   [B],
    "min_count":      torch.uint8   [B],
    "max_count":      torch.uint8   [B],
    "origin":         torch.int32   [B, 3],
}
```

Immediately before the forward pass:

1. run `engine_native_policy.flat.decode_batch(batch["features"])`;
2. assert the decoded option mask sums equal `batch["n_options"]`;
3. move the decoded model tensors and targets to the device;
4. call the engine-native network; and
5. route rows by `is_multi`.

Do not save decoded `int64` model tensors in the cache. The canonical flat float record
is smaller than an all-`int64` expansion, versioned already, and cheap to slice and cast
once per batch.

## 7. Supervised maximum-likelihood loss

Each replay decision contributes one negative log-likelihood.

For single rows:

```python
loss_i = cross_entropy(output.logits[i], single_target[i])
```

The model already masks padded options to negative infinity. Assert that every target is
live before evaluating the loss.

For multi rows:

```python
per_option = binary_cross_entropy_with_logits(
    output.incl[i],
    multi_target[i].to(output.incl.dtype),
    reduction="none",
)
loss_i = (per_option * option_mask[i]).sum()
```

The sum is intentional: it is the negative log-probability of the complete factorized
Bernoulli action, matching the distribution used later by PPO. Average `loss_i` across
decisions in the mini-batch:

```python
loss = torch.stack(per_decision_losses).mean()
```

Do not:

- apply BCE to padded options;
- train policy logits on multi rows;
- train include logits on single rows;
- add a separate STOP label;
- add class weights or positive-label balancing in v1; or
- train the value head from terminal win/loss without a separately approved target
  definition.

## 8. Validation metrics

Report loss and metrics separately for the two action distributions.

Single-select:

- mean negative log-likelihood;
- top-1 accuracy;
- top-3 accuracy where at least three options exist; and
- accuracy by selection context and option type.

Multi-select:

- mean joint negative log-likelihood;
- exact-set accuracy after the standard threshold-and-cardinality projection;
- option-level precision, recall, and F1 over live options only;
- selected-count accuracy; and
- cardinality-bound validity after decoding.

Data-quality reporting:

- examples per game/day/split;
- single/multi ratio;
- legal-option-count histogram;
- declared skip counts;
- zero train/validation episode overlap;
- zero invalid or padded targets; and
- source trace for every validation mismatch inspected.

The best-checkpoint metric should not be chosen until the first TEST run reports these
baselines. Validation loss is the simplest safe initial default.

## 9. Required implementation files

Keep all new work under `Engine-Native-Architecture/`:

```text
src/engine_native_policy/il/
  __init__.py
  replay.py          # deck extraction and off-by-one decision pairing
  targets.py         # single/multi validation and labels
  cache.py           # shard writer, manifests, hashes, resume/reuse
  dataset.py         # Dataset, shard-aware sampler, DataLoader construction
  losses.py          # supervised NLL and metrics

scripts/
  build_il_dataset.py
  smoke_il_batch.py

cluster/
  TEST_build_il_dataset.sbatch
  TEST_smoke_il_train.sbatch

tests/
  test_il_replay.py
  test_il_targets.py
  test_il_cache.py
  test_il_dataset.py
  test_il_losses.py
```

`smoke_il_batch.py` must load at least one cached train batch and one validation batch,
run the real model forward, compute the combined supervised loss, backpropagate once,
and verify finite gradients. It is not a long training run.

The TEST SLURM scripts must use a new cache and output directory. They must not call or
overwrite the existing 174-word cache scripts or artifacts.

## 10. Required implementation order

1. Install the real artifacts, apply the two featurizer corrections, and make golden
   replay/checkpoint parity pass.
2. Implement and test replay pairing, submitted-deck extraction, target construction,
   and hard validation.
3. Implement deterministic inventory/splitting, tensor shard writing, manifests,
   hashing, and safe restart behavior.
4. Implement the shard-backed dataset, shard-aware sampler, DataLoader factory, losses,
   and metrics.
5. Run a small local cache build and one-batch forward/backward smoke.
6. Run the complete six-day TEST cache build on the cluster.
7. Verify the manifest and hashes, then run the cluster train-input smoke.
8. Record measured cache size, build throughput, loader throughput, memory, and the smoke
   result before choosing longer behavior-cloning settings.

Proposed cluster build command contract:

```bash
python -u Engine-Native-Architecture/scripts/build_il_dataset.py \
  --sanitized-root \
    "$WORKDIR/Imitation-Learning/Top-ladder-data/sanitized" \
  --output-root \
    "$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-test-six-days" \
  --days "7-12,7-13,7-14,7-23,7-24,7-25" \
  --validation-fraction 0.10 \
  --seed 20260728 \
  --target-shard-rows 8192 \
  --workers "${SLURM_CPUS_PER_TASK:-16}"
```

There is intentionally no full-corpus `--max-steps` or episode-limit argument in the
checked-in TEST job. Developer smoke commands may use separate `--max-episodes` and
`--max-decisions` options only when writing to a different output root.

Proposed cluster train-input smoke command contract:

```bash
python -u Engine-Native-Architecture/scripts/smoke_il_batch.py \
  --dataset-root \
    "$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-test-six-days" \
  --tables "$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt" \
  --device cuda \
  --batch-size 256 \
  --num-workers 4 \
  --seed 20260728
```

The cache root must be ignored by Git; generated shards and training outputs are never
committed.

The checked-in cluster jobs activate `myenv` one directory above the cluster checkout,
matching the deployed repository/environment layout.

## 11. Test and acceptance checklist

### Local focused tests

- A fixture proves the response action pairs with the previous observation.
- Both 60-card decks are found regardless of submission step.
- A one-element action under `maxCount > 1` is classified as multi-select.
- Multi-actions preserve every selected index.
- Forced choices emit no examples and need no tracker updates.
- Invalid, duplicate, and out-of-range actions fail loudly.
- More than 64 options are counted and skipped.
- No tracker or old observation/action package is imported.
- One extracted replay frame matches the supplied golden flat hash.
- Cache shards round-trip with exact tensor equality.
- Split tests prove determinism and zero episode overlap.
- Loader tests cover last partial batches and single-only/multi-only/mixed batches.
- Loss tests prove padding contributes zero and gradients reach the correct head only.

### Cluster TEST cache acceptance

- All six requested day directories exist and contain nonzero episode counts.
- All six sanitization reports are present.
- The cache job finishes with no undeclared skips.
- Manifest totals equal the sum of shard rows.
- Every shard hash verifies.
- Train and validation contain nonzero single- and multi-select examples.
- Observed cache size, wall time, examples/second, and peak memory are recorded.

### Cluster train-input acceptance

- A normal `DataLoader` yields correctly typed batches.
- Decoded option-mask counts equal cached `n_options` for every checked batch.
- A real-model forward/backward optimizer step is finite.
- Validation iteration is deterministic.
- Two seeded train-loader constructions produce the same first batches.
- CPU loading keeps the GPU supplied during the smoke run, or the measured bottleneck is
  recorded before optimizing.

Only after these checks pass should the full behavior-cloning trainer and longer TEST
run be treated as unblocked.

## 12. Deliberate v1 simplifications

- Cache the canonical flat record rather than inventing a second typed storage schema.
- Use tensor-only `.pt` shards rather than custom examples or another data framework.
- Use one exact game-level 90/10 split.
- Use ordinary maximum likelihood with no class reweighting.
- Exclude forced decisions.
- Skip representational option overflow and count it.
- Do not produce a replay-derived value label.
- Do not depend on game logs, state trackers, or engine re-simulation.

These simplifications reduce implementation time without weakening correctness or
changing the engine-native architecture.
