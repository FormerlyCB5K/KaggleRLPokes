#!/bin/bash
# ============================================================================
#  AiMOS / NPL  --  Imitation-learning training for the deck-agnostic policy
#
#  Submit from the NPL front end:   ssh nplfen01   then:
#      sbatch /gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/Imitation-Learning/policy/submit-batch-il-train.sh
#
#  Just runs Imitation-Learning/policy/train.py (behavior cloning against
#  recorded Top-ladder-data episodes) -- no self-play, no resume, no wandb.
#  CPU-only: nothing in policy/model.py moves tensors to a device, so a GPU
#  allocation wouldn't be used.
# ============================================================================

#SBATCH --job-name=ILTrain
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=48:00:00

set -euo pipefail

# ============================================================================
#  EDIT ME
# ============================================================================
WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
OUT_DIR="$WORKDIR/Imitation-Learning/policy/out/il-run"

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
BATCH_SIZE=8
VAL_FRAC=0.2
# ============================================================================

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"

# ---- environment ----
module purge > /dev/null 2>&1 || true
source "$WORKDIR/../myenv/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

echo "Job $SLURM_JOB_ID  starting at $(date)"
echo "Node: $(hostname)   CPUs: $(nproc)"
echo "Out dir: $OUT_DIR"

# ---- run training ----
CACHE_ARGS=()
if [ -n "$CACHE_DIR" ]; then
    CACHE_ARGS=(--cache-dir "$CACHE_DIR")
fi

python -u Imitation-Learning/policy/train.py \
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
    --val-frac             "$VAL_FRAC"

echo "[$(date)] Training completed."
