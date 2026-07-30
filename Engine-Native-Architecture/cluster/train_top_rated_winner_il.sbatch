#!/bin/bash
# Backward-compatible July 23-25 top-rated winner training profile.
# Every setting can be overridden with the generic long-form switches.

#SBATCH --job-name=ENILTopTrain
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=06:00:00
#SBATCH --open-mode=append

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
exec bash "$WORKDIR/Engine-Native-Architecture/cluster/train_il_dataset.sbatch" \
    --dataset top-rated-winner-three-days \
    --run-name top-rated-winner-three-days \
    --model-name "Top-rated winner three days" \
    --model-description "July 23-25 top 10 percent by floor rating; winner labels" \
    --seed 20260728 \
    --epochs 100 \
    --batch-size 256 \
    --num-workers 8 \
    --learning-rate 1e-4 \
    --early-stopping-patience 5 \
    --early-stopping-min-delta 1e-4 \
    --checkpoint-every-steps 250 \
    --log-every-steps 50 \
    --max-runtime-minutes 300 \
    --max-resubmits 2 \
    "$@"
