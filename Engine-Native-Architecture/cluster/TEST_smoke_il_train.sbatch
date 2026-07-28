#!/bin/bash
# Finite train-input smoke for the six-day engine-native tensor cache.

#SBATCH --job-name=ENILSmokeTest
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=01:00:00

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
ENVIRONMENT="$WORKDIR/../myenv"
CACHE_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-test-six-days"

mkdir -p "$WORKDIR/logs"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

echo "Engine-native IL train-input smoke ${SLURM_JOB_ID:-manual} started at $(date)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

python -u Engine-Native-Architecture/scripts/smoke_il_batch.py \
    --dataset-root "$CACHE_ROOT" \
    --tables "$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt" \
    --device cuda \
    --batch-size 256 \
    --num-workers 4 \
    --seed 20260728

echo "Engine-native IL train-input smoke completed at $(date)"
