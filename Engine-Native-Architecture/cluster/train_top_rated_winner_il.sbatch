#!/bin/bash
# Resumable behavior cloning on the July 23-25 top-rated winner corpus.

#SBATCH --job-name=ENILTopTrain
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH --open-mode=append

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
ENVIRONMENT="$WORKDIR/../myenv"
CACHE_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-top-rated-winner-three-days"
OUT_DIR="$WORKDIR/Imitation-Learning/engine-native-training/top-rated-winner-three-days/seed-20260728"
SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/train_top_rated_winner_il.sbatch"
# Initial job plus two continuations, each with a five-hour internal budget.
MAX_RESUBMITS=2

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"

test -f "$CACHE_ROOT/manifest.json"
echo "Top-rated winner IL training ${SLURM_JOB_ID:-manual} started at $(date)"
echo "Node: $(hostname)  CPUs: ${SLURM_CPUS_PER_TASK:-unknown}"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
echo "Cache: $CACHE_ROOT"
echo "Output: $OUT_DIR"

: "${RESUBMIT_COUNT:=0}"
set +e
python -u Engine-Native-Architecture/scripts/train_il.py \
    --dataset-root "$CACHE_ROOT" \
    --out-dir "$OUT_DIR" \
    --tables "$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt" \
    --epochs 100 \
    --batch-size 256 \
    --num-workers 8 \
    --learning-rate 1e-4 \
    --device cuda \
    --precision auto \
    --gradient-clip 1.0 \
    --seed 20260728 \
    --early-stopping-patience 5 \
    --early-stopping-min-delta 1e-4 \
    --checkpoint-every-steps 250 \
    --log-every-steps 50 \
    --max-runtime-minutes 300 \
    --skip-cache-hash-verification \
    --resume
STATUS=$?
set -e

if [ "$STATUS" -eq 75 ]; then
    if [ "$RESUBMIT_COUNT" -ge "$MAX_RESUBMITS" ]; then
        echo "Fifteen-hour training budget reached; checkpoint is resumable." >&2
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

echo "Top-rated winner IL training completed at $(date)"
