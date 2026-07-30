# 04 - Engine-Native Behavior-Cloning Trainer

Status: implemented and locally validated; full six-day cluster training pending,
2026-07-28.

Value-learning amendment, 2026-07-30: this document preserves the original policy-only
trainer baseline. Active imitation training now follows spec 06's gated extension:
policy NLL plus `0.01 * terminal-outcome value MSE`, matching AlphaGo Zero's supervised
learning experiment, with `tanh` values, combined-loss checkpoint selection, and cache
schema v3. Forced one-option rows train only the value objective. Statements below
excluding value learning or selecting only by NLL are superseded to that narrow extent.

## Purpose

Train the exact engine-native policy from the immutable tensor cache defined by
[`03-imitation-data-to-train-handoff.md`](03-imitation-data-to-train-handoff.md).
This is policy behavior cloning, not PPO and not value learning.

The implementation is:

- `src/engine_native_policy/il/trainer.py` for the reusable trainer;
- `scripts/train_il.py` for the CLI; and
- `cluster/TEST_train_il.sbatch` for the accepted six-day cache.

## Locked first-run configuration

The first reproducibility run uses:

- the existing six-day `engine-native-il-v1` cache and fixed 90/10 game split;
- seed `20260728`;
- random initialization, not the supplied reference checkpoint;
- three maximum epochs;
- physical batch size 256;
- Adam with learning rate `1e-3`;
- gradient clipping at global norm 1.0;
- no weight decay or learning-rate schedule;
- automatic BF16 on supported CUDA devices, otherwise FP16 with gradient scaling;
- TF32 enabled for supported CUDA matrix operations;
- no dropout change, class weighting, oversampling, value loss, or oracle input;
- full validation before training and after every completed epoch;
- best-checkpoint selection by total validation NLL; and
- patience-two early stopping with minimum NLL improvement `1e-4`.

The cluster job skips re-hashing shard bytes because the immediately preceding
acceptance smoke already verified every hash. Structural and cache-identity checks
still run. Batch 256 is the proven value; larger physical batches should be benchmarked
separately before changing this baseline.

## Outputs

The six-day run writes beneath:

```text
Imitation-Learning/engine-native-training/test-six-days/seed-20260728/
```

Generated training output is ignored by Git. The directory contains:

- `config.json` - immutable cache identity, settings, and resolved device/precision;
- `checkpoint.latest.pt` - exact resume state;
- `checkpoint.best.pt` - serving-compatible best state and validation metrics;
- `history.json` - baseline and completed-epoch metrics; and
- `training-summary.json` - terminal result and checkpoint locations.

The latest checkpoint contains the model, optimizer, AMP scaler, epoch, exact next
shard-aware batch, partial-epoch NLL totals, global step, baseline, best metric,
early-stop state, history, and Python/NumPy/PyTorch/CUDA RNG states.

## Resume and walltime behavior

The shard sampler deterministically shuffles shard order and rows from `seed + epoch`.
Its resume cursor omits completed batches before the DataLoader reads them, so a
continuation neither restarts the epoch nor opens skipped mmap shards.

The SLURM job gives the trainer a 330-minute internal budget inside a six-hour
allocation. At that limit, the trainer atomically saves the next-batch cursor and exits
with code 75. The batch script submits a continuation with the same settings and
`--resume`. Unexpected termination can lose work only since the latest periodic
checkpoint.

Changing the cache manifest, frozen tables, initialization checkpoint, epochs, batch
size, learning rate, resolved precision, gradient clip, seed, or early-stop settings
invalidates resume rather than silently mixing runs.

## Metrics

Training reports total, single-select, and multi-select NLL, examples per second, and
peak allocated CUDA memory.

Full validation reports:

- total/single/multi NLL;
- single-select top-1 and top-3 accuracy;
- single-select accuracy by selected option type;
- multi-select exact-set and selected-count accuracy;
- multi-select live-option precision, recall, and F1;
- multi-select cardinality-valid rate;
- throughput and peak allocated CUDA memory.

The v1 cache does not retain `select.context` as target metadata, so the earlier
handoff's proposed validation breakdown by selection context cannot be reconstructed
without invalidating and rebuilding the accepted cache. No context is inferred.

## Validation

Local validation covers:

- vectorized multi-select projection matching serving-time threshold/bounds behavior;
- deterministic sampler resume from the exact next batch;
- interrupted and uninterrupted training producing identical final parameters;
- finished-run resume as a no-op;
- the complete engine-native test suite; and
- a real 2,370,259-parameter CPU run interrupted after one step, resumed, and completed
  with finite improving validation loss on the 32-example fixture.

The six-day cluster optimization remains pending and must be recorded in
`docs/experiments.md` only after it actually runs.
