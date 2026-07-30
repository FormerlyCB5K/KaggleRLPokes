#!/bin/bash
# Backward-compatible six-day engine-native training profile.
# Every setting can be overridden with the generic long-form switches.

#SBATCH --job-name=ENILTrainTest
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --open-mode=append

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
exec bash "$WORKDIR/Engine-Native-Architecture/cluster/train_il_dataset.sbatch" \
    --dataset test-six-days \
    --run-name test-six-days \
    --model-name "Engine-native six-day test" \
    --model-description "Accepted six-day engine-native imitation cache" \
    --seed 20260728 \
    --epochs 3 \
    --batch-size 256 \
    --num-workers 8 \
    --learning-rate 1e-3 \
    --early-stopping-patience 2 \
    --early-stopping-min-delta 1e-4 \
    --checkpoint-every-steps 1000 \
    --log-every-steps 100 \
    --max-runtime-minutes 330 \
    --max-resubmits 30 \
    "$@"
