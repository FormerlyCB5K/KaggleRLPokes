#!/bin/bash
# Submit the selected-replay/cache build and dependent GPU training job.

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
BUILD_SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/build_top_rated_winner_il.sbatch"
TRAIN_SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/train_top_rated_winner_il.sbatch"

BUILD_JOB=$(sbatch --parsable "$BUILD_SCRIPT")
BUILD_JOB=${BUILD_JOB%%;*}
if [[ ! "$BUILD_JOB" =~ ^[0-9]+$ ]]; then
    echo "Build submission did not return a numeric job ID: $BUILD_JOB" >&2
    exit 1
fi

TRAIN_JOB=$(sbatch --parsable \
    --dependency="afterok:$BUILD_JOB" \
    "$TRAIN_SCRIPT" \
    "$@")
TRAIN_JOB=${TRAIN_JOB%%;*}
if [[ ! "$TRAIN_JOB" =~ ^[0-9]+$ ]]; then
    echo "Training submission did not return a numeric job ID: $TRAIN_JOB" >&2
    exit 1
fi

echo "Build job: $BUILD_JOB"
echo "Training job: $TRAIN_JOB (afterok:$BUILD_JOB)"
