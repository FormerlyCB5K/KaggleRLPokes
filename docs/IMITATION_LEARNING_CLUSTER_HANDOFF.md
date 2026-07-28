# Imitation-Learning Cluster Handoff

Last updated: 2026-07-28

## Current engine-native pipeline

The engine-native implementation supersedes the 174-word cache/training path for current
work. Its data and optimizer contracts are:

- `Engine-Native-Architecture/specs/03-imitation-data-to-train-handoff.md`
- `Engine-Native-Architecture/specs/04-behavior-cloning-trainer.md`

It builds tensor-only shards at:

```text
Imitation-Learning/Top-ladder-data/engine-native-cache-test-six-days/
```

The user reported that the repaired `7-14` sanitization, uncapped six-day cache build,
and finite CUDA forward/backward acceptance chain completed successfully:

```text
2156105 Sanitize714
2156106 ENILCacheTest
2156107 ENILSmokeTest
```

Exact cache totals, GPU model, throughput, and smoke losses were not supplied and must
not be invented. Retrieve the logs if those measurements are needed.

From the repository root on NPL:

```bash
REPO="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"

CACHE_JOB=$(sbatch --parsable \
  "$REPO/Engine-Native-Architecture/cluster/TEST_build_il_dataset.sbatch")
CACHE_JOB=${CACHE_JOB%%;*}
echo "Cache job: $CACHE_JOB"

if [[ "$CACHE_JOB" =~ ^[0-9]+$ ]]; then
  SMOKE_JOB=$(sbatch --parsable \
    --dependency="afterok:$CACHE_JOB" \
    "$REPO/Engine-Native-Architecture/cluster/TEST_smoke_il_train.sbatch")
  SMOKE_JOB=${SMOKE_JOB%%;*}
  echo "Smoke job: $SMOKE_JOB"
else
  echo "Cache submission did not return a numeric job ID; smoke not submitted."
  exit 1
fi
```

Both scripts activate `myenv` one directory above the checkout. The cache build requires
all six sanitized day directories and reports. Before submission, verify the cluster
filesystem has approximately 100 GB free for the cache. Acceptance requires a complete
manifest, verified shard hashes, nonzero single/multi examples in both splits, and a
finite CUDA smoke step.

### Full six-day behavior cloning

The full trainer is implemented at
`Engine-Native-Architecture/scripts/train_il.py`. Its checked-in first-run settings are
random initialization, three maximum epochs, batch 256, Adam at `1e-3`, automatic
BF16/FP16, gradient clipping at 1.0, full baseline/epoch validation, and patience-two
early stopping by validation NLL.

After pulling the trainer commit on NPL, submit:

```bash
REPO="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
TRAIN_JOB=$(sbatch --parsable \
  "$REPO/Engine-Native-Architecture/cluster/TEST_train_il.sbatch")
TRAIN_JOB=${TRAIN_JOB%%;*}
echo "Training job: $TRAIN_JOB"
```

Outputs are isolated under:

```text
Imitation-Learning/engine-native-training/test-six-days/seed-20260728/
```

The Python trainer stops safely after 330 minutes inside the six-hour allocation and
returns exit code 75. The SLURM wrapper then self-submits a continuation, which restores
the exact next shard-aware batch from `checkpoint.latest.pt`. A zero exit means the run
finished; any other nonzero exit is treated as a failure and does not resubmit.

Monitor the initial job with:

```bash
squeue -j "$TRAIN_JOB"
tail -n 100 "$REPO/logs/ENILTrainTest-${TRAIN_JOB}.out"
tail -n 100 "$REPO/logs/ENILTrainTest-${TRAIN_JOB}.err"
```

Continuations receive new job IDs, printed in the preceding job's output. Do not run a
second independent training job against the same output directory.

## Preserved legacy 174-word handoff

The remainder of this document records the previous pipeline and job history. Do not use
its `Imitation-Learning/policy/TEST_*` commands for the engine-native milestone.

## Legacy immediate objective

Run the complete cache-and-training pipeline on the intended six-day sanitized test
corpus:

`7-12, 7-13, 7-14, 7-23, 7-24, 7-25`

This is intentionally an incomplete corpus, but it is a full pipeline run over every
episode in those days. The dedicated `TEST_` scripts and output directories keep its
artifacts separate from the future 14-day production run.

## Last known state

- Latest implementation commit pushed to `origin/master`:
  `def8cb1 Fix empty SLURM argument arrays`.
- The first cluster cache attempt failed on an older Bash behavior:
  `EXTRA_ARGS[@]: unbound variable`. Commit `def8cb1` fixes both cache scripts and the
  production training script.
- The next submission attempt was run from the user's home directory (`~`), so relative
  paths such as `Imitation-Learning/policy/TEST_submit-batch-build-cache.sh` did not
  exist. `sbatch` returned `Unable to open file`; both captured job variables were empty,
  and no jobs were submitted by those commands.
- Therefore, as of this handoff there is no confirmed active cache or training job.
  Check `squeue`/`sacct` rather than assuming this is still true tomorrow.
- `7-14` was previously reported missing on the cluster. Verify all six directories
  before submission. The TEST cache builder intentionally fails rather than silently
  creating a five-day run.
- The local worktree is clean relative to `origin/master` except for the unrelated,
  untracked `KaggleRLPokes-825d528.bundle`. Preserve it and do not stage it.

## What is implemented

- Parallel, per-day sanitized-example cache construction with strict manifests.
- Fixed global 90/10 train/validation split by game, not by decision position.
- All games are shuffled together with a fixed seed; validation games have no training
  positions. There is no rare-position oversampling.
- Reusable per-day validation shards bound to a cache inventory and split hash.
- One cached day per shuffled mini-epoch; every day is visited once per outer epoch.
- True GPU-vectorized batches (`batch_size=256` in cluster scripts), CUDA float16
  autocast/scaling, and TF32.
- Atomic resume state after every day, including model, optimizer, AMP scaler, RNG,
  split identity, progress cursor, best metric, and early-stopping state.
- Fixed-validation evaluation once per complete outer epoch.
- Six-hour SLURM jobs with a `USR1` signal five minutes before the walltime. Training
  submits a continuation and resumes; at most the interrupted day is repeated.
- Early stopping defaults to patience 5 and minimum accuracy improvement 0.001.

The implementation/regression suite last passed 93 policy and observation tests. Local
CUDA smoke, fixed-split integrity, checkpoint round-trip, resume, and early-stop paths
passed. No uncapped six-day cluster run has yet been confirmed.

## Tomorrow: preflight and submit

Run this on the NPL front end. Absolute paths make the commands independent of the
current directory.

```bash
REPO="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"

cd "$REPO"
git pull --ff-only origin master
git log -1 --oneline

for day in 7-12 7-13 7-14 7-23 7-24 7-25; do
    DAY_DIR="$REPO/Imitation-Learning/Top-ladder-data/sanitized/$day"
    if test -d "$DAY_DIR"; then
        echo "FOUND $day: $(find "$DAY_DIR" -maxdepth 1 -type f -name '*.json' | wc -l) JSON files"
    else
        echo "MISSING $day"
    fi
done

ls -l \
  "$REPO/Imitation-Learning/policy/TEST_submit-batch-build-cache.sh" \
  "$REPO/Imitation-Learning/policy/TEST_submit-batch-il-train.sh"
```

The log should show commit `def8cb1` or a newer commit containing it, six nonzero
`FOUND` counts, and both scripts. Resolve any missing or empty day before continuing.

Submit the cache and a dependent training job:

```bash
TRAIN_JOB=""

CACHE_JOB=$(sbatch --parsable \
  "$REPO/Imitation-Learning/policy/TEST_submit-batch-build-cache.sh")
CACHE_JOB=${CACHE_JOB%%;*}
echo "Cache job: $CACHE_JOB"

if [[ "$CACHE_JOB" =~ ^[0-9]+$ ]]; then
    TRAIN_JOB=$(sbatch --parsable \
      --dependency="afterok:$CACHE_JOB" \
      "$REPO/Imitation-Learning/policy/TEST_submit-batch-il-train.sh")
    TRAIN_JOB=${TRAIN_JOB%%;*}
    echo "Training job: $TRAIN_JOB"
else
    echo "Cache submission did not return a numeric job ID; training not submitted."
fi

if [[ "$CACHE_JOB" =~ ^[0-9]+$ && "$TRAIN_JOB" =~ ^[0-9]+$ ]]; then
    squeue -j "$CACHE_JOB,$TRAIN_JOB"
fi
```

It is normal for training to show `PD (Dependency)` until the cache job succeeds. Do not
submit training with an empty cache job ID.

## Monitoring and diagnosis

`squeue` only shows pending/running jobs. A short-lived completed or failed job can
disappear immediately. Use accounting to see its terminal state:

```bash
sacct -j "$CACHE_JOB,$TRAIN_JOB" \
  --format=JobID,JobName,State,ExitCode,Elapsed,Reason
```

Inspect logs from the repository root:

```bash
tail -n 100 "$REPO/logs/ILCacheTest-${CACHE_JOB}.out"
tail -n 100 "$REPO/logs/ILCacheTest-${CACHE_JOB}.err"
tail -n 100 "$REPO/logs/ILTrainTest-${TRAIN_JOB}.out"
tail -n 100 "$REPO/logs/ILTrainTest-${TRAIN_JOB}.err"
```

Interpretation:

- `COMPLETED`: the job is done even though it no longer appears in `squeue`.
- `FAILED`: inspect the matching `.err` file first.
- `TIMEOUT`: unexpected for cache; training should normally receive `USR1`, submit a
  continuation, and exit before the six-hour wall.
- `DependencyNeverSatisfied`: the cache failed or was cancelled; fix the cache problem
  and submit a new dependency chain.
- `PartitionTimeLimit`: the cluster checkout is probably stale or a different script was
  submitted. Current scripts request exactly `06:00:00`.

The continuation job gets a new SLURM job ID. Its output is appended to its own
`ILTrainTest-<job-id>.out`; the shared resume checkpoint is the source of truth for
progress.

## Expected TEST artifacts

Cache:

```text
Imitation-Learning/Top-ladder-data/example-cache-test-six-days/
  sanitized/<day>.pkl
  sanitized/<day>.manifest.json
```

Training:

```text
Imitation-Learning/policy/out/il-test-six-days/checkpoint.pt
Imitation-Learning/policy/out/il-test-six-days/checkpoint.resume.pt
Imitation-Learning/policy/out/il-test-six-days/checkpoint.config.json
Imitation-Learning/policy/out/il-test-six-days/checkpoint.game-split.json
Imitation-Learning/policy/out/il-test-six-days/checkpoint.game-split.validation/
```

`checkpoint.pt` is the best fixed-validation model. `checkpoint.resume.pt` is the latest
mini-epoch state and is what `--resume` uses. The split JSON and validation directory
must be preserved with the run; they enforce validation integrity.

The TEST script currently requests 3 outer epochs. On first launch, split construction
loads all caches and builds validation shards once. Later continuations reuse them.

## Production transition

Do not use the production scripts until all 14 sanitized day directories from `7-12`
through `7-25` exist. Then use:

- `Imitation-Learning/policy/submit-batch-build-cache.sh`
- `Imitation-Learning/policy/submit-batch-il-train.sh`

Production artifacts use `example-cache/` and `policy/out/il-run/`, separate from the
six-day TEST run. The cache and training scripts must keep identical
`MAX_EPISODES_PER_ZIP` and `MAX_STEPS` values.

## Still to verify or decide

1. Confirm all six sanitized directories, especially `7-14`, are actually on the
   cluster checkout/storage.
2. Complete one uncapped six-day cache build and record cache sizes, elapsed time, and
   peak memory if available.
3. Complete the three-epoch TEST run and record per-day throughput, validation counts,
   baseline accuracy, per-epoch accuracy, continuation behavior, and final artifact
   paths in `docs/experiments.md`.
4. Use the measured cluster throughput to choose production epoch count and whether
   batch 256 remains optimal on the assigned GPU.
5. Sanitize and cache the remaining eight days before calling any run a full 14-day
   corpus run.
