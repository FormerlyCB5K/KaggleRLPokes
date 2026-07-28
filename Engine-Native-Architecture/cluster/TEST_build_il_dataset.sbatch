#!/bin/bash
# Six-day engine-native tensor-cache build. No full trainer is launched here.

#SBATCH --job-name=ENILCacheTest
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=06:00:00

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
ENVIRONMENT="$WORKDIR/../myenv"
SANITIZED_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data/sanitized"
CACHE_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-test-six-days"
DAYS="7-12,7-13,7-14,7-23,7-24,7-25"
WORKERS="${SLURM_CPUS_PER_TASK:-16}"

mkdir -p "$WORKDIR/logs"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"

for day in 7-12 7-13 7-14 7-23 7-24 7-25; do
    test -d "$SANITIZED_ROOT/$day"
    test -f "$SANITIZED_ROOT/$day/report.json"
done

echo "Engine-native IL cache build ${SLURM_JOB_ID:-manual} started at $(date)"
echo "Source: $SANITIZED_ROOT"
echo "Output: $CACHE_ROOT"
CACHE_PARENT="$(dirname "$CACHE_ROOT")"
AVAILABLE_KB=$(df -Pk "$CACHE_PARENT" | awk 'NR==2 {print $4}')
REQUIRED_KB=$((100 * 1024 * 1024))
df -h "$CACHE_PARENT"
if [ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]; then
    echo "Need at least 100 GiB free for the engine-native TEST cache." >&2
    exit 1
fi

python -u Engine-Native-Architecture/scripts/build_il_dataset.py \
    --sanitized-root "$SANITIZED_ROOT" \
    --output-root "$CACHE_ROOT" \
    --days "$DAYS" \
    --validation-fraction 0.10 \
    --seed 20260728 \
    --target-shard-rows 8192 \
    --workers "$WORKERS" \
    --tables "$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt" \
    --artifact-manifest "$WORKDIR/Engine-Native-Architecture/artifacts/installed-manifest.json"

echo "Engine-native IL cache build completed at $(date)"
