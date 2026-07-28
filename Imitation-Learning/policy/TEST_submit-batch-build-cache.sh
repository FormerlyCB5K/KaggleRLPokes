#!/bin/bash
# ============================================================================
# TEST ONLY -- build IL Example caches for the six currently sanitized days:
#   7-12, 7-13, 7-14, 7-23, 7-24, 7-25
#
# This is intentionally incomplete relative to the production 14-day corpus,
# but it uses every episode from these six days and is suitable for an
# end-to-end cluster training test.
#
# Submit from the NPL front end:
#   sbatch /gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/Imitation-Learning/policy/TEST_submit-batch-build-cache.sh
# ============================================================================

#SBATCH --job-name=ILCacheTest
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00

set -euo pipefail

# ============================================================================
# EDIT ME only if the cluster checkout/environment moved.
# ============================================================================
WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
SOURCE="sanitized"
RAW_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data"
SANITIZED_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data/sanitized"
# Separate from the production 14-day cache so test artifacts cannot be
# mistaken for a complete production cache.
CACHE_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data/example-cache-test-six-days"
DAYS="7-12,7-13,7-14,7-23,7-24,7-25"
MAX_EPISODES_PER_ZIP="all"
MAX_STEPS=300
WORKERS="${SLURM_CPUS_PER_TASK:-16}"
# Set to 1 only when intentionally rebuilding otherwise-current cache files.
FORCE=0
# ============================================================================

mkdir -p "$WORKDIR/logs" "$CACHE_DIR"
cd "$WORKDIR"

module purge > /dev/null 2>&1 || true
source "$WORKDIR/../myenv/bin/activate"

echo "TEST six-day cache job ${SLURM_JOB_ID:-manual} starting at $(date)"
echo "Node: $(hostname)   CPUs: $(nproc)"
echo "Days: $DAYS"
echo "Sanitized dir: $SANITIZED_DIR"
echo "Cache dir: $CACHE_DIR"
echo "Episode limit: $MAX_EPISODES_PER_ZIP   max steps: $MAX_STEPS"

EXTRA_ARGS=(--days "$DAYS")
if [ "$FORCE" -eq 1 ]; then
    EXTRA_ARGS+=(--force)
fi

python -u Imitation-Learning/build_example_cache.py \
    --source               "$SOURCE" \
    --raw-dir              "$RAW_DIR" \
    --sanitized-dir        "$SANITIZED_DIR" \
    --cache-dir            "$CACHE_DIR" \
    --max-episodes-per-zip "$MAX_EPISODES_PER_ZIP" \
    --max-steps            "$MAX_STEPS" \
    --workers              "$WORKERS" \
    "${EXTRA_ARGS[@]}"

echo "[$(date)] TEST six-day cache build completed."
