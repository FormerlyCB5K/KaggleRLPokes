#!/bin/bash
# Fully configurable, resumable engine-native behavior-cloning job.
#
# Example:
#   sbatch Engine-Native-Architecture/cluster/train_il_dataset.sbatch \
#     --dataset top-rated-winner-2026-07-12-to-2026-07-27 \
#     --run-name winner-full-v2 \
#     --model-name "Winner Full v2" \
#     --model-description "Top 10 percent by floor rating, winner labels" \
#     --epochs 100 --learning-rate 1e-4 --evaluate true

#SBATCH --job-name=ENILTrain
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
ENVIRONMENT="$WORKDIR/../myenv"
SCRIPT="$WORKDIR/Engine-Native-Architecture/cluster/train_il_dataset.sbatch"
ORIGINAL_ARGS=("$@")

DATASET="${DATASET:-}"
RUN_NAME="${RUN_NAME:-}"
MODEL_NAME="${MODEL_NAME:-}"
MODEL_DESCRIPTION="${MODEL_DESCRIPTION:-}"
SEED="${SEED:-20260728}"
EPOCHS="${EPOCHS:-100}"
BATCH_SIZE="${BATCH_SIZE:-256}"
NUM_WORKERS="${NUM_WORKERS:-8}"
LEARNING_RATE="${LEARNING_RATE:-1e-4}"
MODEL_WIDTH="${MODEL_WIDTH:-224}"
MODEL_LAYERS="${MODEL_LAYERS:-4}"
MODEL_HEADS="${MODEL_HEADS:-4}"
MODEL_FEEDFORWARD_WIDTH="${MODEL_FEEDFORWARD_WIDTH:-448}"
MODEL_STATIC_WIDTH="${MODEL_STATIC_WIDTH:-32}"
MODEL_EFFECT_WIDTH="${MODEL_EFFECT_WIDTH:-48}"
MODEL_REGISTERS="${MODEL_REGISTERS:-4}"
MODEL_DROPOUT="${MODEL_DROPOUT:-0.0}"
VALUE_LOSS_WEIGHT="${VALUE_LOSS_WEIGHT:-0.01}"
TREE_SEARCH="${TREE_SEARCH:-false}"
MCTS_SIMULATIONS="${MCTS_SIMULATIONS:-800}"
MCTS_MAX_DEPTH="${MCTS_MAX_DEPTH:-32}"
MCTS_C_PUCT="${MCTS_C_PUCT:-1.5}"
MCTS_DIRICHLET_ALPHA="${MCTS_DIRICHLET_ALPHA:-0.3}"
MCTS_DIRICHLET_EPSILON="${MCTS_DIRICHLET_EPSILON:-0.25}"
MCTS_TEMPERATURE="${MCTS_TEMPERATURE:-1.0}"
MCTS_PER_DECISION_SECONDS="${MCTS_PER_DECISION_SECONDS:-}"
MCTS_GAME_BUDGET_SECONDS="${MCTS_GAME_BUDGET_SECONDS:-}"
MCTS_SEED="${MCTS_SEED:-20260730}"
DEVICE="${DEVICE:-cuda}"
PRECISION="${PRECISION:-auto}"
GRADIENT_CLIP="${GRADIENT_CLIP:-1.0}"
PATIENCE="${PATIENCE:-5}"
MIN_DELTA="${MIN_DELTA:-1e-4}"
MAX_RUNTIME_MINUTES="${MAX_RUNTIME_MINUTES:-300}"
MAX_OPTIMIZER_STEPS="${MAX_OPTIMIZER_STEPS:-}"
MAX_RESUBMITS="${MAX_RESUBMITS:-2}"
CHECKPOINT_EVERY_STEPS="${CHECKPOINT_EVERY_STEPS:-250}"
LOG_EVERY_STEPS="${LOG_EVERY_STEPS:-50}"
SKIP_CACHE_HASH_VERIFICATION="${SKIP_CACHE_HASH_VERIFICATION:-true}"
RESUME="${RESUME:-true}"
INITIAL_CHECKPOINT="${INITIAL_CHECKPOINT:-}"
TABLES="${TABLES:-$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt}"
CONFIG_ROOT="${CONFIG_ROOT:-$WORKDIR/config}"
EVALUATE="${EVALUATE:-false}"
EVALUATION_GAMES="${EVALUATION_GAMES:-100}"
EVALUATION_OPPONENT_FOLDER="${EVALUATION_OPPONENT_FOLDER:-$WORKDIR/sample-archaludon}"
EVALUATION_OPPONENT_DECK="${EVALUATION_OPPONENT_DECK:-}"
EVALUATION_OWN_DECK="${EVALUATION_OWN_DECK:-$WORKDIR/Rising-Tide-Fixed-Metal-v15/deck.csv}"
EVALUATION_CHECKPOINT="${EVALUATION_CHECKPOINT:-best}"
EVALUATION_MAX_ACTIONS="${EVALUATION_MAX_ACTIONS:-20000}"

usage() {
    cat <<'EOF'
Usage: sbatch train_il_dataset.sbatch --dataset NAME [options]

Identity and data:
  --dataset NAME
  --run-name PATH_SAFE_NAME
  --model-name "Display name"
  --model-description "Free-form description"
  --config-root PATH

Training:
  --seed N
  --epochs N
  --batch-size N
  --num-workers N
  --learning-rate FLOAT
  --model-width N
  --model-layers N
  --model-heads N
  --model-feedforward-width N
  --model-static-width N
  --model-effect-width N
  --model-registers N
  --model-dropout FLOAT
  --value-loss-weight FLOAT
  --tree-search true|false
  --mcts-simulations N
  --mcts-max-depth N
  --mcts-c-puct FLOAT
  --mcts-dirichlet-alpha FLOAT
  --mcts-dirichlet-epsilon FLOAT
  --mcts-temperature FLOAT
  --mcts-per-decision-seconds FLOAT
  --mcts-game-budget-seconds FLOAT
  --mcts-seed N
  --device auto|cpu|cuda
  --precision auto|fp32|fp16|bf16
  --gradient-clip FLOAT
  --early-stopping-patience N
  --early-stopping-min-delta FLOAT
  --checkpoint-every-steps N
  --log-every-steps N
  --max-runtime-minutes FLOAT
  --max-optimizer-steps N
  --max-resubmits N
  --initial-checkpoint PATH
  --tables PATH
  --resume true|false
  --skip-cache-hash-verification true|false

Post-training evaluation:
  --evaluate true|false
  --evaluation-games N
  --evaluation-opponent-folder PATH
  --evaluation-opponent-deck PATH
  --evaluation-own-deck PATH
  --evaluation-checkpoint best|latest|PATH
  --evaluation-max-actions N
EOF
}

require_value() {
    if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "$1 requires a value." >&2
        exit 2
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dataset) require_value "$@"; DATASET="$2"; shift 2 ;;
        --run-name) require_value "$@"; RUN_NAME="$2"; shift 2 ;;
        --model-name) require_value "$@"; MODEL_NAME="$2"; shift 2 ;;
        --model-description) require_value "$@"; MODEL_DESCRIPTION="$2"; shift 2 ;;
        --config-root) require_value "$@"; CONFIG_ROOT="$2"; shift 2 ;;
        --seed) require_value "$@"; SEED="$2"; shift 2 ;;
        --epochs) require_value "$@"; EPOCHS="$2"; shift 2 ;;
        --batch-size) require_value "$@"; BATCH_SIZE="$2"; shift 2 ;;
        --num-workers) require_value "$@"; NUM_WORKERS="$2"; shift 2 ;;
        --learning-rate) require_value "$@"; LEARNING_RATE="$2"; shift 2 ;;
        --model-width) require_value "$@"; MODEL_WIDTH="$2"; shift 2 ;;
        --model-layers) require_value "$@"; MODEL_LAYERS="$2"; shift 2 ;;
        --model-heads) require_value "$@"; MODEL_HEADS="$2"; shift 2 ;;
        --model-feedforward-width) require_value "$@"; MODEL_FEEDFORWARD_WIDTH="$2"; shift 2 ;;
        --model-static-width) require_value "$@"; MODEL_STATIC_WIDTH="$2"; shift 2 ;;
        --model-effect-width) require_value "$@"; MODEL_EFFECT_WIDTH="$2"; shift 2 ;;
        --model-registers) require_value "$@"; MODEL_REGISTERS="$2"; shift 2 ;;
        --model-dropout) require_value "$@"; MODEL_DROPOUT="$2"; shift 2 ;;
        --value-loss-weight) require_value "$@"; VALUE_LOSS_WEIGHT="$2"; shift 2 ;;
        --tree-search) require_value "$@"; TREE_SEARCH="$2"; shift 2 ;;
        --mcts-simulations) require_value "$@"; MCTS_SIMULATIONS="$2"; shift 2 ;;
        --mcts-max-depth) require_value "$@"; MCTS_MAX_DEPTH="$2"; shift 2 ;;
        --mcts-c-puct) require_value "$@"; MCTS_C_PUCT="$2"; shift 2 ;;
        --mcts-dirichlet-alpha) require_value "$@"; MCTS_DIRICHLET_ALPHA="$2"; shift 2 ;;
        --mcts-dirichlet-epsilon) require_value "$@"; MCTS_DIRICHLET_EPSILON="$2"; shift 2 ;;
        --mcts-temperature) require_value "$@"; MCTS_TEMPERATURE="$2"; shift 2 ;;
        --mcts-per-decision-seconds) require_value "$@"; MCTS_PER_DECISION_SECONDS="$2"; shift 2 ;;
        --mcts-game-budget-seconds) require_value "$@"; MCTS_GAME_BUDGET_SECONDS="$2"; shift 2 ;;
        --mcts-seed) require_value "$@"; MCTS_SEED="$2"; shift 2 ;;
        --device) require_value "$@"; DEVICE="$2"; shift 2 ;;
        --precision) require_value "$@"; PRECISION="$2"; shift 2 ;;
        --gradient-clip) require_value "$@"; GRADIENT_CLIP="$2"; shift 2 ;;
        --early-stopping-patience) require_value "$@"; PATIENCE="$2"; shift 2 ;;
        --early-stopping-min-delta) require_value "$@"; MIN_DELTA="$2"; shift 2 ;;
        --checkpoint-every-steps) require_value "$@"; CHECKPOINT_EVERY_STEPS="$2"; shift 2 ;;
        --log-every-steps) require_value "$@"; LOG_EVERY_STEPS="$2"; shift 2 ;;
        --max-runtime-minutes) require_value "$@"; MAX_RUNTIME_MINUTES="$2"; shift 2 ;;
        --max-optimizer-steps) require_value "$@"; MAX_OPTIMIZER_STEPS="$2"; shift 2 ;;
        --max-resubmits) require_value "$@"; MAX_RESUBMITS="$2"; shift 2 ;;
        --initial-checkpoint) require_value "$@"; INITIAL_CHECKPOINT="$2"; shift 2 ;;
        --tables) require_value "$@"; TABLES="$2"; shift 2 ;;
        --resume) require_value "$@"; RESUME="$2"; shift 2 ;;
        --skip-cache-hash-verification) require_value "$@"; SKIP_CACHE_HASH_VERIFICATION="$2"; shift 2 ;;
        --evaluate) require_value "$@"; EVALUATE="$2"; shift 2 ;;
        --evaluation-games) require_value "$@"; EVALUATION_GAMES="$2"; shift 2 ;;
        --evaluation-opponent-folder) require_value "$@"; EVALUATION_OPPONENT_FOLDER="$2"; shift 2 ;;
        --evaluation-opponent-deck) require_value "$@"; EVALUATION_OPPONENT_DECK="$2"; shift 2 ;;
        --evaluation-own-deck) require_value "$@"; EVALUATION_OWN_DECK="$2"; shift 2 ;;
        --evaluation-checkpoint) require_value "$@"; EVALUATION_CHECKPOINT="$2"; shift 2 ;;
        --evaluation-max-actions) require_value "$@"; EVALUATION_MAX_ACTIONS="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [ -z "$DATASET" ]; then
    echo "--dataset is required." >&2
    usage >&2
    exit 2
fi
RUN_NAME="${RUN_NAME:-$DATASET}"
MODEL_NAME="${MODEL_NAME:-$RUN_NAME}"

if [[ ! "$DATASET" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "--dataset must contain only letters, numbers, dots, underscores, or hyphens." >&2
    exit 2
fi
if [[ ! "$RUN_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
    echo "--run-name must contain only letters, numbers, dots, underscores, or hyphens." >&2
    exit 2
fi
for boolean_name in RESUME SKIP_CACHE_HASH_VERIFICATION EVALUATE TREE_SEARCH; do
    boolean_value="${!boolean_name}"
    case "$boolean_value" in
        1|yes|on) printf -v "$boolean_name" '%s' true ;;
        0|no|off) printf -v "$boolean_name" '%s' false ;;
    esac
    boolean_value="${!boolean_name}"
    if [[ "$boolean_value" != "true" && "$boolean_value" != "false" ]]; then
        echo "$boolean_name must be true or false." >&2
        exit 2
    fi
done
if [[ ! "$MAX_RESUBMITS" =~ ^[0-9]+$ ]]; then
    echo "--max-resubmits must be a non-negative integer." >&2
    exit 2
fi
if [[ ! "${RESUBMIT_COUNT:-0}" =~ ^[0-9]+$ ]]; then
    echo "RESUBMIT_COUNT must be a non-negative integer." >&2
    exit 2
fi

CACHE_ROOT="$WORKDIR/Imitation-Learning/Top-ladder-data/engine-native-cache-$DATASET"
OUT_DIR="$WORKDIR/Imitation-Learning/engine-native-training/$RUN_NAME/seed-$SEED"
CONFIG_LOG="$CONFIG_ROOT/$RUN_NAME/seed-$SEED.json"

mkdir -p "$WORKDIR/logs" "$OUT_DIR" "$(dirname "$CONFIG_LOG")"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-8}"

test -f "$CACHE_ROOT/manifest.json"
echo "Engine-native IL training ${SLURM_JOB_ID:-manual} started at $(date)"
echo "Model: $MODEL_NAME"
echo "Description: $MODEL_DESCRIPTION"
echo "Dataset: $DATASET"
echo "Cache: $CACHE_ROOT"
echo "Output: $OUT_DIR"
echo "Config log: $CONFIG_LOG"
echo "Epochs: $EPOCHS; batch: $BATCH_SIZE; learning rate: $LEARNING_RATE"
echo "Model: width=$MODEL_WIDTH layers=$MODEL_LAYERS heads=$MODEL_HEADS ff=$MODEL_FEEDFORWARD_WIDTH static=$MODEL_STATIC_WIDTH effect=$MODEL_EFFECT_WIDTH registers=$MODEL_REGISTERS dropout=$MODEL_DROPOUT"
echo "Value loss weight: $VALUE_LOSS_WEIGHT"
echo "Tree search: $TREE_SEARCH; simulations: $MCTS_SIMULATIONS; depth: $MCTS_MAX_DEPTH; c_puct: $MCTS_C_PUCT"
echo "Evaluation: $EVALUATE; games: $EVALUATION_GAMES"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

TRAIN_ARGS=(
    --dataset-name "$DATASET"
    --run-name "$RUN_NAME"
    --dataset-root "$CACHE_ROOT"
    --out-dir "$OUT_DIR"
    --tables "$TABLES"
    --epochs "$EPOCHS"
    --batch-size "$BATCH_SIZE"
    --num-workers "$NUM_WORKERS"
    --learning-rate "$LEARNING_RATE"
    --model-width "$MODEL_WIDTH"
    --model-layers "$MODEL_LAYERS"
    --model-heads "$MODEL_HEADS"
    --model-feedforward-width "$MODEL_FEEDFORWARD_WIDTH"
    --model-static-width "$MODEL_STATIC_WIDTH"
    --model-effect-width "$MODEL_EFFECT_WIDTH"
    --model-registers "$MODEL_REGISTERS"
    --model-dropout "$MODEL_DROPOUT"
    --value-loss-weight "$VALUE_LOSS_WEIGHT"
    --tree-search "$TREE_SEARCH"
    --mcts-simulations "$MCTS_SIMULATIONS"
    --mcts-max-depth "$MCTS_MAX_DEPTH"
    --mcts-c-puct "$MCTS_C_PUCT"
    --mcts-dirichlet-alpha "$MCTS_DIRICHLET_ALPHA"
    --mcts-dirichlet-epsilon "$MCTS_DIRICHLET_EPSILON"
    --mcts-temperature "$MCTS_TEMPERATURE"
    --mcts-seed "$MCTS_SEED"
    --device "$DEVICE"
    --precision "$PRECISION"
    --gradient-clip "$GRADIENT_CLIP"
    --seed "$SEED"
    --early-stopping-patience "$PATIENCE"
    --early-stopping-min-delta "$MIN_DELTA"
    --checkpoint-every-steps "$CHECKPOINT_EVERY_STEPS"
    --log-every-steps "$LOG_EVERY_STEPS"
    --max-runtime-minutes "$MAX_RUNTIME_MINUTES"
    --max-resubmits "$MAX_RESUBMITS"
    --model-name "$MODEL_NAME"
    --model-description "$MODEL_DESCRIPTION"
    --config-log "$CONFIG_LOG"
    --evaluate "$EVALUATE"
    --evaluation-games "$EVALUATION_GAMES"
    --evaluation-opponent-folder "$EVALUATION_OPPONENT_FOLDER"
    --evaluation-own-deck "$EVALUATION_OWN_DECK"
    --evaluation-checkpoint "$EVALUATION_CHECKPOINT"
    --evaluation-max-actions "$EVALUATION_MAX_ACTIONS"
)
if [ -n "$MAX_OPTIMIZER_STEPS" ]; then
    TRAIN_ARGS+=(--max-optimizer-steps "$MAX_OPTIMIZER_STEPS")
fi
if [ -n "$MCTS_PER_DECISION_SECONDS" ]; then
    TRAIN_ARGS+=(--mcts-per-decision-seconds "$MCTS_PER_DECISION_SECONDS")
fi
if [ -n "$MCTS_GAME_BUDGET_SECONDS" ]; then
    TRAIN_ARGS+=(--mcts-game-budget-seconds "$MCTS_GAME_BUDGET_SECONDS")
fi
if [ -n "$INITIAL_CHECKPOINT" ]; then
    TRAIN_ARGS+=(--initial-checkpoint "$INITIAL_CHECKPOINT")
fi
if [ -n "$EVALUATION_OPPONENT_DECK" ]; then
    TRAIN_ARGS+=(--evaluation-opponent-deck "$EVALUATION_OPPONENT_DECK")
fi
if [ "$SKIP_CACHE_HASH_VERIFICATION" = "true" ]; then
    TRAIN_ARGS+=(--skip-cache-hash-verification)
fi
if [ "$RESUME" = "true" ]; then
    TRAIN_ARGS+=(--resume)
fi

: "${RESUBMIT_COUNT:=0}"
set +e
python -u Engine-Native-Architecture/scripts/train_il.py "${TRAIN_ARGS[@]}"
STATUS=$?
set -e

if [ "$STATUS" -eq 75 ]; then
    if [ "$RESUBMIT_COUNT" -ge "$MAX_RESUBMITS" ]; then
        echo "Maximum continuation count reached; checkpoint and config are resumable." >&2
        exit 0
    fi
    NEXT_COUNT=$((RESUBMIT_COUNT + 1))
    NEXT_JOB=$(sbatch --parsable \
        --export="ALL,RESUBMIT_COUNT=$NEXT_COUNT" \
        "$SCRIPT" "${ORIGINAL_ARGS[@]}")
    NEXT_JOB=${NEXT_JOB%%;*}
    echo "Submitted continuation $NEXT_JOB ($NEXT_COUNT/$MAX_RESUBMITS)."
    exit 0
fi

if [ "$STATUS" -ne 0 ]; then
    echo "Training or evaluation failed with exit code $STATUS." >&2
    exit "$STATUS"
fi

echo "Engine-native IL training and optional evaluation completed at $(date)"
