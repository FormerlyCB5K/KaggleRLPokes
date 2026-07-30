#!/bin/bash
# Dataset-selectable, resumable engine-native behavior-cloning job.
#
# DATASET is the suffix of a cache directory named engine-native-cache-$DATASET.
# Example:
#   sbatch --export=ALL,DATASET=top-rated-winner-three-days \
#     Engine-Native-Architecture/cluster/train_il_dataset.sbatch

#SBATCH --job-name=ENILTrain
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --open-mode=append

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
ENVIRONMENT="$WORKDIR/../myenv"
SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/train_il_dataset.sbatch"

if [ -z "${DATASET:-}" ]; then
    echo "DATASET is required." >&2
    echo "Submit with: sbatch --export=ALL,DATASET=<cache-suffix> $SCRIPT" >&2
    echo "Available cache directories:" >&2
    find "$WORKDIR/Imitation-Learning/Top-ladder-data" \
        -maxdepth 1 -type d -name 'engine-native-cache-*' -print >&2
    exit 2
fi
if [[ ! "$DATASET" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "DATASET must contain only letters, numbers, dots, underscores, or hyphens." >&2
    exit 2
fi

# Every setting may be overridden in the same --export argument. Use a distinct
# RUN_NAME when intentionally starting another configuration on the same cache.
SEED="${SEED:-20260728}"
RUN_NAME="${RUN_NAME:-$DATASET}"
EPOCHS="${EPOCHS:-100}"
BATCH_SIZE="${BATCH_SIZE:-256}"
NUM_WORKERS="${NUM_WORKERS:-8}"
LEARNING_RATE="${LEARNING_RATE:-1e-4}"
PATIENCE="${PATIENCE:-5}"
MAX_RUNTIME_MINUTES="${MAX_RUNTIME_MINUTES:-300}"
MAX_RESUBMITS="${MAX_RESUBMITS:-2}"
CHECKPOINT_EVERY_STEPS="${CHECKPOINT_EVERY_STEPS:-250}"
LOG_EVERY_STEPS="${LOG_EVERY_STEPS:-50}"
SKIP_CACHE_HASH_VERIFICATION="${SKIP_CACHE_HASH_VERIFICATION:-1}"

if [[ ! "$RUN_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "RUN_NAME must contain only letters, numbers, dots, underscores, or hyphens." >&2
    exit 2
fi
if [[ ! "$MAX_RESUBMITS" =~ ^[0-9]+$ ]]; then
    echo "MAX_RESUBMITS must be a non-negative integer." >&2
    exit 2
fi
if [[ ! "${RESUBMIT_COUNT:-0}" =~ ^[0-9]+$ ]]; then
    echo "RESUBMIT_COUNT must be a non-negative integer." >&2
    exit 2
fi
if [[ "$SKIP_CACHE_HASH_VERIFICATION" != "0" && "$SKIP_CACHE_HASH_VERIFICATION" != "1" ]]; then
    echo "SKIP_CACHE_HASH_VERIFICATION must be 0 or 1." >&2
    exit 2
fi

CACHE_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-$DATASET"
OUT_DIR="$WORKDIR/Imitation-Learning/engine-native-training/$RUN_NAME/seed-$SEED"

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"

test -f "$CACHE_ROOT/manifest.json"
echo "Dataset-selectable IL training ${SLURM_JOB_ID:-manual} started at $(date)"
echo "Dataset: $DATASET"
echo "Cache: $CACHE_ROOT"
echo "Output: $OUT_DIR"
echo "Epochs: $EPOCHS; batch: $BATCH_SIZE; learning rate: $LEARNING_RATE"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

TRAIN_ARGS=(
    --dataset-root "$CACHE_ROOT"
    --out-dir "$OUT_DIR"
    --tables "$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt"
    --epochs "$EPOCHS"
    --batch-size "$BATCH_SIZE"
    --num-workers "$NUM_WORKERS"
    --learning-rate "$LEARNING_RATE"
    --device cuda
    --precision auto
    --gradient-clip 1.0
    --seed "$SEED"
    --early-stopping-patience "$PATIENCE"
    --early-stopping-min-delta 1e-4
    --checkpoint-every-steps "$CHECKPOINT_EVERY_STEPS"
    --log-every-steps "$LOG_EVERY_STEPS"
    --max-runtime-minutes "$MAX_RUNTIME_MINUTES"
    --resume
)
if [ "$SKIP_CACHE_HASH_VERIFICATION" = "1" ]; then
    TRAIN_ARGS+=(--skip-cache-hash-verification)
fi

: "${RESUBMIT_COUNT:=0}"
set +e
python -u Engine-Native-Architecture/scripts/train_il.py "${TRAIN_ARGS[@]}"
STATUS=$?
set -e

if [ "$STATUS" -eq 75 ]; then
    if [ "$RESUBMIT_COUNT" -ge "$MAX_RESUBMITS" ]; then
        echo "Maximum continuation count reached; checkpoint is resumable." >&2
        exit 0
    fi
    NEXT_COUNT=$((RESUBMIT_COUNT + 1))
    NEXT_JOB=$(sbatch --parsable \
        --export="ALL,RESUBMIT_COUNT=$NEXT_COUNT" \
        "$SCRIPT")
    NEXT_JOB=${NEXT_JOB%%;*}
    echo "Submitted continuation $NEXT_JOB ($NEXT_COUNT/$MAX_RESUBMITS)."
    exit 0
fi

if [ "$STATUS" -ne 0 ]; then
    echo "Training failed with exit code $STATUS; no continuation submitted." >&2
    exit "$STATUS"
fi

echo "Dataset-selectable IL training completed at $(date)"
