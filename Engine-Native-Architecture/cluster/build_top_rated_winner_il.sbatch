#!/bin/bash
# Prepare July 23-25 top-minimum-rating winner replays and build tensor shards.

#SBATCH --job-name=ENILTopBuild
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
SELECTED_ROOT="$RAW_ROOT/top-rated-winner-three-days"
CACHE_ROOT="$RAW_ROOT/engine-native-cache-top-rated-winner-three-days"
DAYS="7-23,7-24,7-25"
WORKERS="${SLURM_CPUS_PER_TASK:-16}"

mkdir -p "$WORKDIR/logs"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS="$WORKERS"
export MKL_NUM_THREADS="$WORKERS"

echo "Top-rated winner IL build ${SLURM_JOB_ID:-manual} started at $(date)"
for day in 7-23 7-24 7-25; do
    test -d "$RAW_ROOT/$day"
    test "$(find "$RAW_ROOT/$day" -maxdepth 1 -type f -name '*.zip' | wc -l)" -eq 1
done

AVAILABLE_KB=$(df -Pk "$RAW_ROOT" | awk 'NR==2 {print $4}')
REQUIRED_KB=$((20 * 1024 * 1024))
df -h "$RAW_ROOT"
if [ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]; then
    echo "Need at least 20 GiB free for selected replays and tensor shards." >&2
    exit 1
fi

python -u Imitation-Learning/prepare_top_rated_winner_dataset.py \
    --data-root "$RAW_ROOT" \
    --output-root "$SELECTED_ROOT" \
    --days "$DAYS" \
    --fraction 0.10 \
    --score-column min_score \
    --workers "$WORKERS" \
    --overwrite

python -u Engine-Native-Architecture/scripts/build_il_dataset.py \
    --sanitized-root "$SELECTED_ROOT" \
    --output-root "$CACHE_ROOT" \
    --days "$DAYS" \
    --validation-fraction 0.10 \
    --seed 20260728 \
    --target-shard-rows 8192 \
    --workers "$WORKERS" \
    --tables "$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt" \
    --artifact-manifest "$WORKDIR/Engine-Native-Architecture/artifacts/installed-manifest.json"

python -u -c \
    "from pathlib import Path; import json; p=Path('$CACHE_ROOT/manifest.json'); m=json.loads(p.read_text()); assert m['totals']['games']==1355, m['totals']; assert m['totals']['examples']>0; print(json.dumps(m['totals'], indent=2, sort_keys=True))"

echo "Top-rated winner IL build completed at $(date)"
