#!/bin/bash
# ============================================================================
# AiMOS / NPL -- Build reusable per-day imitation-learning Example caches.
#
# Submit from the NPL front end:
#   ssh nplfen01
#   sbatch /gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/Imitation-Learning/policy/submit-batch-build-cache.sh
#
# Run this once after the sanitized dataset is present. Training jobs reuse the
# resulting cache and must use the same MAX_EPISODES_PER_ZIP and MAX_STEPS.
# ============================================================================

#SBATCH --job-name=ILCache
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=24:00:00

set -euo pipefail

# ============================================================================
# EDIT ME
# ============================================================================
WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
SOURCE="sanitized"
RAW_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data"
SANITIZED_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data/sanitized"
CACHE_DIR="$WORKDIR/Imitation-Learning/Top-ladder-data/example-cache"
# "all" means every episode in each selected day.
MAX_EPISODES_PER_ZIP="all"
MAX_STEPS=300
WORKERS="${SLURM_CPUS_PER_TASK:-16}"
# The agreed full corpus (2026-07-12 through 2026-07-25). The builder fails if
# any requested day is absent, preventing an accidentally partial "full" run.
# Set empty only when intentionally caching every day currently present.
DAYS="7-12,7-13,7-14,7-15,7-16,7-17,7-18,7-19,7-20,7-21,7-22,7-23,7-24,7-25"
# Set to 1 to rebuild matching entries instead of reporting them up to date.
FORCE=0
# ============================================================================

mkdir -p "$WORKDIR/logs" "$CACHE_DIR"
cd "$WORKDIR"

module purge > /dev/null 2>&1 || true
source "$WORKDIR/../myenv/bin/activate"

echo "Job ${SLURM_JOB_ID:-manual} starting at $(date)"
echo "Node: $(hostname)   CPUs: $(nproc)"
echo "Source: $SOURCE"
echo "Sanitized dir: $SANITIZED_DIR"
echo "Cache dir: $CACHE_DIR"
echo "Episode limit: $MAX_EPISODES_PER_ZIP   max steps: $MAX_STEPS"

EXTRA_ARGS=()
if [ -n "$DAYS" ]; then
    EXTRA_ARGS+=(--days "$DAYS")
fi
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

echo "[$(date)] Cache build completed."
