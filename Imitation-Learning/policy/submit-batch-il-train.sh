#!/bin/bash
# ============================================================================
#  AiMOS / NPL  --  Imitation-learning training for the deck-agnostic policy
#
#  Submit from the NPL front end:   ssh nplfen01   then:
#      sbatch /gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/Imitation-Learning/policy/submit-batch-il-train.sh
#
#  Runs GPU-vectorized behavior cloning against recorded Top-ladder-data
#  episodes. The transformer processes a real mini-batch per forward pass;
#  variable candidate lists are scored from the resulting GPU embeddings.
# ============================================================================

#SBATCH --job-name=ILTrain
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
#  EDIT ME
# ============================================================================
WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
OUT_DIR="$WORKDIR/Imitation-Learning/policy/out/il-run"
SCRIPT="$WORKDIR/Imitation-Learning/policy/submit-batch-il-train.sh"
MAX_RESUBMITS=30

# Identifies this run in the printed config banner and the saved
# <out>.config.json -- fill in DESCRIPTION per submission with what this run
# is actually testing.
RUN_NAME="${SLURM_JOB_NAME:-ILTrain}-${SLURM_JOB_ID:-manual}"
DESCRIPTION=""

# SOURCE selects what policy/data.py:iter_all_examples reads: "raw" (only
# RAW_DIR, *.zip), "sanitized" (only SANITIZED_DIR, loose per-episode *.json
# from build_sanitized_top_ladder_dataset.py), or "both" (both dirs --
# only sensible if they cover non-overlapping days, since the sanitized set
# is a filtered copy of the same episodes).
SOURCE="sanitized"
RAW_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data"
SANITIZED_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data/sanitized"
CACHE_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data/example-cache"
DAYS_PER_CHUNK=1
# Must exactly match the cache-build job. "all" means uncapped/full day.
MAX_EPISODES_PER_ZIP="all"
MAX_STEPS=300
EPOCHS=3
LR=1e-3
BATCH_SIZE=256
VAL_FRAC=0.1
DEVICE="cuda"
EARLY_STOPPING_PATIENCE=5
EARLY_STOPPING_MIN_DELTA=0.001
# ============================================================================

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"

# ---- environment ----
module purge > /dev/null 2>&1 || true
source "$WORKDIR/../myenv/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-10}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-10}"

echo "Job $SLURM_JOB_ID  starting at $(date)"
echo "Node: $(hostname)   CPUs: $(nproc)"
echo "GPU: $(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)"
echo "Out dir: $OUT_DIR"

# ---- resume cleanly across the partition's six-hour walltime ----
: "${RESUBMIT_COUNT:=0}"
requeue() {
    if [ "$RESUBMIT_COUNT" -lt "$MAX_RESUBMITS" ]; then
        echo "[$(date)] Time limit approaching; submitting continuation "
        echo "          ($((RESUBMIT_COUNT + 1))/$MAX_RESUBMITS)"
        sbatch --export=ALL,RESUBMIT_COUNT=$((RESUBMIT_COUNT + 1)) "$SCRIPT"
    else
        echo "[$(date)] MAX_RESUBMITS=$MAX_RESUBMITS reached; not continuing."
    fi
    [ -n "${PYPID:-}" ] && kill "$PYPID" 2>/dev/null || true
    exit 0
}
trap requeue USR1

# ---- run training ----
CACHE_ARGS=(--cache-dir "$CACHE_DIR")

python -u Imitation-Learning/policy/train.py \
    --resume \
    --run-name             "$RUN_NAME" \
    --description          "$DESCRIPTION" \
    --source               "$SOURCE" \
    --raw-dir              "$RAW_DIR" \
    --sanitized-dir        "$SANITIZED_DIR" \
    --days-per-chunk       "$DAYS_PER_CHUNK" \
    "${CACHE_ARGS[@]}" \
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

echo "[$(date)] Training completed cleanly. No continuation needed."
