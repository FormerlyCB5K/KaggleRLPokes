#!/bin/bash
# Train one latest-network update from a bounded self-play replay window.

#SBATCH --job-name=ENSelfTrain
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=06:00:00

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
ENVIRONMENT="$WORKDIR/../myenv"
REPLAY_ROOT=""
OUT_DIR=""
INITIAL_CHECKPOINT=""
TABLES="$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt"
REPLAY_WINDOW_GAMES="500000"
VALIDATION_FRACTION="0.10"
EPOCHS="1"
BATCH_SIZE="256"
NUM_WORKERS="8"
LEARNING_RATE="1e-3"
L2_WEIGHT="1e-4"
GRADIENT_CLIP="1.0"
SEED="20260730"
DEVICE="cuda"

require_value() {
    if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "$1 requires a value." >&2
        exit 2
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --replay-root) require_value "$@"; REPLAY_ROOT="$2"; shift 2 ;;
        --out-dir) require_value "$@"; OUT_DIR="$2"; shift 2 ;;
        --initial-checkpoint) require_value "$@"; INITIAL_CHECKPOINT="$2"; shift 2 ;;
        --tables) require_value "$@"; TABLES="$2"; shift 2 ;;
        --replay-window-games) require_value "$@"; REPLAY_WINDOW_GAMES="$2"; shift 2 ;;
        --validation-fraction) require_value "$@"; VALIDATION_FRACTION="$2"; shift 2 ;;
        --epochs) require_value "$@"; EPOCHS="$2"; shift 2 ;;
        --batch-size) require_value "$@"; BATCH_SIZE="$2"; shift 2 ;;
        --num-workers) require_value "$@"; NUM_WORKERS="$2"; shift 2 ;;
        --learning-rate) require_value "$@"; LEARNING_RATE="$2"; shift 2 ;;
        --l2-weight) require_value "$@"; L2_WEIGHT="$2"; shift 2 ;;
        --gradient-clip) require_value "$@"; GRADIENT_CLIP="$2"; shift 2 ;;
        --seed) require_value "$@"; SEED="$2"; shift 2 ;;
        --device) require_value "$@"; DEVICE="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$REPLAY_ROOT" ] || [ -z "$OUT_DIR" ] || [ -z "$INITIAL_CHECKPOINT" ]; then
    echo "--replay-root, --out-dir, and --initial-checkpoint are required." >&2
    exit 2
fi

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"

python -u Engine-Native-Architecture/scripts/train_selfplay.py \
    --replay-root "$REPLAY_ROOT" \
    --out-dir "$OUT_DIR" \
    --initial-checkpoint "$INITIAL_CHECKPOINT" \
    --tables "$TABLES" \
    --replay-window-games "$REPLAY_WINDOW_GAMES" \
    --validation-fraction "$VALIDATION_FRACTION" \
    --epochs "$EPOCHS" \
    --batch-size "$BATCH_SIZE" \
    --num-workers "$NUM_WORKERS" \
    --learning-rate "$LEARNING_RATE" \
    --l2-weight "$L2_WEIGHT" \
    --gradient-clip "$GRADIENT_CLIP" \
    --seed "$SEED" \
    --device "$DEVICE"
