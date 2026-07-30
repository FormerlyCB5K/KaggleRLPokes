#!/bin/bash
# Submit a full July 12-27 top-10% cache build followed by behavior cloning.
# Unlike the winner-only dataset, every accepted game supervises both players.
#
# All arguments after this script are forwarded to the configurable trainer.
# Example:
#   bash <this-script> --model-name "All perspectives v1" \
#     --model-description "Top 10 percent, both players" --evaluate true

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
BUILD_SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/FULL_build_top_rated_winner_il.sbatch"
TRAIN_SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/train_il_dataset.sbatch"

DATASET="top-rated-all-perspectives-2026-07-12-to-2026-07-27"
USER_ARGS=("$@")
for ((index = 0; index < ${#USER_ARGS[@]}; index++)); do
    if [ "${USER_ARGS[$index]}" = "--dataset" ]; then
        next=$((index + 1))
        if [ "$next" -ge "${#USER_ARGS[@]}" ]; then
            echo "--dataset requires a value." >&2
            exit 2
        fi
        DATASET="${USER_ARGS[$next]}"
    fi
done

BUILD_JOB=$(sbatch --parsable \
    --export="ALL,DATASET=$DATASET,SCORE_COLUMN=min_score,FRACTION=0.10,PERSPECTIVES=all" \
    "$BUILD_SCRIPT")
BUILD_JOB=${BUILD_JOB%%;*}

TRAIN_JOB=$(sbatch --parsable \
    --dependency="afterok:$BUILD_JOB" \
    "$TRAIN_SCRIPT" \
    --dataset "$DATASET" \
    --run-name top-rated-all-perspectives-full-20260730 \
    --model-name "Top-rated all perspectives full" \
    --model-description "July 12-27 top 10 percent by floor rating; both player perspectives" \
    --seed 20260729 \
    --epochs 100 \
    --learning-rate 1e-4 \
    --early-stopping-patience 5 \
    --max-resubmits 2 \
    "${USER_ARGS[@]}")
TRAIN_JOB=${TRAIN_JOB%%;*}

echo "Submitted all-perspectives cache build: $BUILD_JOB"
echo "Submitted dependent imitation training: $TRAIN_JOB"
