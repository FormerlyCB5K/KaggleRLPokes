#!/bin/bash
# Build the July 12-27 engine-native cache directly from daily raw ZIPs.

#SBATCH --job-name=ENILCacheFull
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
ENVIRONMENT="$WORKDIR/../myenv"
RAW_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data"
CACHE_ROOT="$RAW_ROOT/engine-native-cache-full-2026-07-12-to-2026-07-27"
DAYS="7-12,7-13,7-14,7-15,7-16,7-17,7-18,7-19,7-20,7-21,7-22,7-23,7-24,7-25,7-26,7-27"
WORKERS="${SLURM_CPUS_PER_TASK:-16}"
REQUIRED_GIB="${REQUIRED_GIB:-180}"

mkdir -p "$WORKDIR/logs"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

for day in 7-12 7-13 7-14 7-15 7-16 7-17 7-18 7-19 7-20 7-21 7-22 7-23 7-24 7-25 7-26 7-27; do
    test -d "$RAW_ROOT/$day"
    count=$(find "$RAW_ROOT/$day" -maxdepth 1 -type f -name '*.zip' | wc -l)
    if [ "$count" -ne 1 ]; then
        echo "$day: expected exactly one raw ZIP, found $count" >&2
        exit 1
    fi
done

echo "Full raw-ZIP IL cache build ${SLURM_JOB_ID:-manual} started at $(date)"
echo "Source: $RAW_ROOT"
echo "Output: $CACHE_ROOT"
AVAILABLE_KB=$(df -Pk "$RAW_ROOT" | awk 'NR==2 {print $4}')
REQUIRED_KB=$((REQUIRED_GIB * 1024 * 1024))
df -h "$RAW_ROOT"
if [ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]; then
    echo "Need at least ${REQUIRED_GIB} GiB free for the full tensor cache." >&2
    echo "Override only after measuring with REQUIRED_GIB=<value> sbatch ..." >&2
    exit 1
fi

python -u Engine-Native-Architecture/scripts/build_il_dataset.py \
    --source raw-zip \
    --raw-root "$RAW_ROOT" \
    --output-root "$CACHE_ROOT" \
    --days "$DAYS" \
    --validation-fraction 0.10 \
    --seed 20260728 \
    --target-shard-rows 8192 \
    --workers "$WORKERS" \
    --tables "$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt" \
    --artifact-manifest "$WORKDIR/Engine-Native-Architecture/artifacts/installed-manifest.json"

echo "Full raw-ZIP IL cache build completed at $(date)"
