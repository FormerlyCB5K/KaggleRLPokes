#!/bin/bash
# Select, sanitize, and tensorize the top-rated games from the full replay range.
#
# Ranking is stored in each raw ZIP's manifest.csv, so selection must consult the
# raw archives. Only the selected members are materialized as sanitized JSON; the
# engine-native cache is then built from that compact selected corpus.

#SBATCH --job-name=ENILTopFull
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

# These values may be overridden with sbatch --export=ALL,NAME=value,...
DATASET="${DATASET:-top-rated-winner-2026-07-12-to-2026-07-27}"
DAYS="${DAYS:-7-12,7-13,7-14,7-15,7-16,7-17,7-18,7-19,7-20,7-21,7-22,7-23,7-24,7-25,7-26,7-27}"
FRACTION="${FRACTION:-0.10}"
SCORE_COLUMN="${SCORE_COLUMN:-min_score}"
PERSPECTIVES="${PERSPECTIVES:-winner}"
REQUIRED_GIB="${REQUIRED_GIB:-60}"
OVERWRITE_SELECTED="${OVERWRITE_SELECTED:-0}"
REUSE_SELECTED="${REUSE_SELECTED:-1}"
WORKERS="${SLURM_CPUS_PER_TASK:-16}"

if [[ ! "$DATASET" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "DATASET must contain only letters, numbers, dots, underscores, or hyphens." >&2
    exit 2
fi
if [[ "$SCORE_COLUMN" != "min_score" && "$SCORE_COLUMN" != "avg_score" ]]; then
    echo "SCORE_COLUMN must be min_score or avg_score." >&2
    exit 2
fi
if [[ "$PERSPECTIVES" != "winner" && "$PERSPECTIVES" != "all" ]]; then
    echo "PERSPECTIVES must be winner or all." >&2
    exit 2
fi
if [[ "$OVERWRITE_SELECTED" != "0" && "$OVERWRITE_SELECTED" != "1" ]]; then
    echo "OVERWRITE_SELECTED must be 0 or 1." >&2
    exit 2
fi
if [[ "$REUSE_SELECTED" != "0" && "$REUSE_SELECTED" != "1" ]]; then
    echo "REUSE_SELECTED must be 0 or 1." >&2
    exit 2
fi

SELECTED_ROOT="$RAW_ROOT/$DATASET"
CACHE_ROOT="$RAW_ROOT/engine-native-cache-$DATASET"

mkdir -p "$WORKDIR/logs"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1

IFS=',' read -r -a DAY_LIST <<< "$DAYS"
if [ "${#DAY_LIST[@]}" -eq 0 ]; then
    echo "DAYS must contain at least one M-D day name." >&2
    exit 2
fi
for day in "${DAY_LIST[@]}"; do
    day="${day//[[:space:]]/}"
    if [[ ! "$day" =~ ^[0-9]{1,2}-[0-9]{1,2}$ ]]; then
        echo "Invalid day '$day'; expected M-D such as 7-12." >&2
        exit 2
    fi
    test -d "$RAW_ROOT/$day"
    count=$(find "$RAW_ROOT/$day" -maxdepth 1 -type f -name '*.zip' | wc -l)
    if [ "$count" -ne 1 ]; then
        echo "$day: expected exactly one raw ZIP, found $count" >&2
        exit 1
    fi
done

echo "Top-rated full-corpus build ${SLURM_JOB_ID:-manual} started at $(date)"
echo "Days: $DAYS"
echo "Ranking: $SCORE_COLUMN; fraction: $FRACTION"
echo "Supervised perspectives: $PERSPECTIVES"
echo "Selected sanitized replays: $SELECTED_ROOT"
echo "Tensor cache: $CACHE_ROOT"
echo "Reuse completed selected days: $REUSE_SELECTED"

AVAILABLE_KB=$(df -Pk "$RAW_ROOT" | awk 'NR==2 {print $4}')
REQUIRED_KB=$((REQUIRED_GIB * 1024 * 1024))
df -h "$RAW_ROOT"
if [ "$AVAILABLE_KB" -lt "$REQUIRED_KB" ]; then
    echo "Need at least ${REQUIRED_GIB} GiB free for selected replays and tensors." >&2
    echo "Override only after measuring with REQUIRED_GIB=<value>." >&2
    exit 1
fi

PREPARE_ARGS=(
    --data-root "$RAW_ROOT"
    --output-root "$SELECTED_ROOT"
    --days "$DAYS"
    --fraction "$FRACTION"
    --score-column "$SCORE_COLUMN"
    --perspectives "$PERSPECTIVES"
    --workers "$WORKERS"
)
if [ "$OVERWRITE_SELECTED" = "1" ]; then
    PREPARE_ARGS+=(--overwrite)
elif [ "$REUSE_SELECTED" = "1" ]; then
    PREPARE_ARGS+=(--reuse-existing)
fi

python -u Imitation-Learning/prepare_top_rated_winner_dataset.py \
    "${PREPARE_ARGS[@]}"

# The tensor builder can leave a non-empty directory without a manifest if a
# job is interrupted. Preserve that partial output for inspection, then allow
# the retry to start from a clean destination. Completed caches retain their
# manifest and are validated/reused by build_il_dataset.py below.
if [ -d "$CACHE_ROOT" ] && [ ! -f "$CACHE_ROOT/manifest.json" ] && \
        [ -n "$(find "$CACHE_ROOT" -mindepth 1 -print -quit)" ]; then
    RAW_REAL=$(realpath "$RAW_ROOT")
    CACHE_REAL=$(realpath -m "$CACHE_ROOT")
    CACHE_NAME=$(basename "$CACHE_REAL")
    if [ "$(dirname "$CACHE_REAL")" != "$RAW_REAL" ] || \
            [[ "$CACHE_NAME" != engine-native-cache-* ]]; then
        echo "Refusing to move unsafe incomplete cache path: $CACHE_REAL" >&2
        exit 1
    fi
    PARTIAL_CACHE="$RAW_ROOT/.incomplete-$CACHE_NAME-${SLURM_JOB_ID:-manual}-$(date +%s)"
    mv -- "$CACHE_REAL" "$PARTIAL_CACHE"
    echo "Moved incomplete tensor cache to recoverable path: $PARTIAL_CACHE"
fi

python -u Engine-Native-Architecture/scripts/build_il_dataset.py \
    --source sanitized \
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
    "from pathlib import Path; import json; p=Path('$CACHE_ROOT/manifest.json'); m=json.loads(p.read_text()); assert m['totals']['games'] > 0, m['totals']; assert m['totals']['examples'] > 0, m['totals']; print(json.dumps(m['totals'], indent=2, sort_keys=True))"

echo "Top-rated full-corpus build completed at $(date)"
