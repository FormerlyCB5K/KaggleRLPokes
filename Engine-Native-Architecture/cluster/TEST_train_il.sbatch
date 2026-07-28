#!/bin/bash
# Full behavior-cloning optimization on the accepted six-day engine-native cache.

#SBATCH --job-name=ENILTrainTest
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
CACHE_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-test-six-days"
OUT_DIR="$WORKDIR/Imitation-Learning/engine-native-training/test-six-days/seed-20260728"
SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/TEST_train_il.sbatch"
MAX_RESUBMITS=30

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"

echo "Engine-native IL training ${SLURM_JOB_ID:-manual} started at $(date)"
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
    --epochs 3 \
    --batch-size 256 \
    --num-workers 8 \
    --learning-rate 1e-3 \
    --device cuda \
    --precision auto \
    --gradient-clip 1.0 \
    --seed 20260728 \
    --early-stopping-patience 2 \
    --early-stopping-min-delta 1e-4 \
    --checkpoint-every-steps 1000 \
    --log-every-steps 100 \
    --max-runtime-minutes 330 \
    --skip-cache-hash-verification \
    --resume
STATUS=$?
set -e

if [ "$STATUS" -eq 75 ]; then
    if [ "$RESUBMIT_COUNT" -ge "$MAX_RESUBMITS" ]; then
        echo "Maximum continuation count reached; checkpoint is resumable." >&2
        exit 1
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

echo "Engine-native IL training completed at $(date)"
