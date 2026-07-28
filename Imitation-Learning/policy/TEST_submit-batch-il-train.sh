#!/bin/bash
# ============================================================================
# TEST ONLY -- train on the complete cached contents of these six days:
#   7-12, 7-13, 7-14, 7-23, 7-24, 7-25
#
# The matching TEST cache-build job writes to a dedicated cache directory.
# This training job deliberately loads in cache-only mode: it does not pass the
# live sanitized source root, so later-added day folders cannot silently expand
# this fixed six-day test run.
#
# Submit only after TEST_submit-batch-build-cache.sh succeeds.
# ============================================================================

#SBATCH --job-name=ILTrainTest
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --signal=B:USR1@300
#SBATCH --open-mode=append

set -euo pipefail

# ============================================================================
# EDIT ME only if the cluster checkout/environment moved.
# ============================================================================
WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
OUT_DIR="$WORKDIR/Imitation-Learning/policy/out/il-test-six-days"
SCRIPT="$WORKDIR/Imitation-Learning/policy/TEST_submit-batch-il-train.sh"
MAX_RESUBMITS=30
CACHE_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data/example-cache-test-six-days"
SOURCE="sanitized"
DAYS_PER_CHUNK=1
# These must exactly match TEST_submit-batch-build-cache.sh.
MAX_EPISODES_PER_ZIP="all"
MAX_STEPS=300
EPOCHS=3
LR=1e-3
BATCH_SIZE=256
VAL_FRAC=0.1
DEVICE="cuda"
EARLY_STOPPING_PATIENCE=5
EARLY_STOPPING_MIN_DELTA=0.001
RUN_NAME="${SLURM_JOB_NAME:-ILTrainTest}-${SLURM_JOB_ID:-manual}"
DESCRIPTION="Incomplete six-day corpus (7-12,7-13,7-14,7-23,7-24,7-25); good for full pipeline testing"
# ============================================================================

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"

module purge > /dev/null 2>&1 || true
source "$WORKDIR/../myenv/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-10}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-10}"

echo "TEST six-day training job ${SLURM_JOB_ID:-manual} starting at $(date)"
echo "Node: $(hostname)   CPUs: $(nproc)"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
echo "Cache dir: $CACHE_DIR"
echo "Out dir: $OUT_DIR"

: "${RESUBMIT_COUNT:=0}"
requeue() {
    if [ "$RESUBMIT_COUNT" -lt "$MAX_RESUBMITS" ]; then
        echo "[$(date)] Time limit approaching; submitting TEST continuation "
        echo "          ($((RESUBMIT_COUNT + 1))/$MAX_RESUBMITS)"
        sbatch --export=ALL,RESUBMIT_COUNT=$((RESUBMIT_COUNT + 1)) "$SCRIPT"
    else
        echo "[$(date)] MAX_RESUBMITS=$MAX_RESUBMITS reached; not continuing."
    fi
    [ -n "${PYPID:-}" ] && kill "$PYPID" 2>/dev/null || true
    exit 0
}
trap requeue USR1

python -u Imitation-Learning/policy/train.py \
    --resume \
    --run-name             "$RUN_NAME" \
    --description          "$DESCRIPTION" \
    --source               "$SOURCE" \
    --cache-dir            "$CACHE_DIR" \
    --days-per-chunk       "$DAYS_PER_CHUNK" \
    --out                  "$OUT_DIR/checkpoint.pt" \
    --max-episodes-per-zip "$MAX_EPISODES_PER_ZIP" \
    --max-steps            "$MAX_STEPS" \
    --epochs               "$EPOCHS" \
    --lr                   "$LR" \
    --batch-size           "$BATCH_SIZE" \
    --device               "$DEVICE" \
    --val-frac             "$VAL_FRAC" \
    --early-stopping-patience "$EARLY_STOPPING_PATIENCE" \
    --early-stopping-min-delta "$EARLY_STOPPING_MIN_DELTA" &

PYPID=$!
wait "$PYPID"

echo "[$(date)] TEST six-day training completed cleanly. No continuation needed."
