#!/bin/bash
# Submit a full July 12-27 top-10% cache build followed by behavior cloning.
# Unlike the winner-only dataset, every accepted game supervises both players.
#
# Optional overrides:
#   DATASET=... RUN_NAME=... SEED=... EPOCHS=... bash <this-script>

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
BUILD_SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/FULL_build_top_rated_winner_il.sbatch"
TRAIN_SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/train_il_dataset.sbatch"

DATASET="${DATASET:-top-rated-all-perspectives-2026-07-12-to-2026-07-27}"
RUN_NAME="${RUN_NAME:-top-rated-all-perspectives-full-20260730}"
SEED="${SEED:-20260729}"
EPOCHS="${EPOCHS:-100}"
LEARNING_RATE="${LEARNING_RATE:-1e-4}"
PATIENCE="${PATIENCE:-5}"
MAX_RESUBMITS="${MAX_RESUBMITS:-2}"

BUILD_JOB=$(sbatch --parsable \
    --export="ALL,DATASET=$DATASET,SCORE_COLUMN=min_score,FRACTION=0.10,PERSPECTIVES=all" \
    "$BUILD_SCRIPT")
BUILD_JOB=${BUILD_JOB%%;*}

TRAIN_JOB=$(sbatch --parsable \
    --dependency="afterok:$BUILD_JOB" \
    --export="ALL,DATASET=$DATASET,RUN_NAME=$RUN_NAME,SEED=$SEED,EPOCHS=$EPOCHS,LEARNING_RATE=$LEARNING_RATE,PATIENCE=$PATIENCE,MAX_RESUBMITS=$MAX_RESUBMITS" \
    "$TRAIN_SCRIPT")
TRAIN_JOB=${TRAIN_JOB%%;*}

echo "Submitted all-perspectives cache build: $BUILD_JOB"
echo "Submitted dependent imitation training: $TRAIN_JOB"
