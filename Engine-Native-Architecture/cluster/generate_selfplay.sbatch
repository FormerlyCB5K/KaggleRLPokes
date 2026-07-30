#!/bin/bash
# Generate latest-network AlphaZero self-play shards.
# All search switches are recorded in both the replay manifest and run config.

#SBATCH --job-name=ENSelfPlay
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=06:00:00

set -euo pipefail

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
ENVIRONMENT="$WORKDIR/../myenv"
CHECKPOINT=""
DECK=""
OUTPUT_DIR=""
RUN_NAME="selfplay"
MODEL_NAME="Engine Native Self-Play"
MODEL_DESCRIPTION=""
GAMES="1"
START_GAME=""
MAX_ACTIONS="20000"
DEVICE="cuda"
TABLES="$WORKDIR/Engine-Native-Architecture/artifacts/frozen_tables.pt"
CONFIG_ROOT="$WORKDIR/config"
MCTS_SIMULATIONS="800"
MCTS_MAX_DEPTH="32"
MCTS_C_PUCT="1.5"
MCTS_DIRICHLET_ALPHA="0.3"
MCTS_DIRICHLET_EPSILON="0.25"
MCTS_TEMPERATURE="1.0"
MCTS_PER_DECISION_SECONDS=""
MCTS_GAME_BUDGET_SECONDS=""
MCTS_SEED="20260730"

require_value() {
    if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        echo "$1 requires a value." >&2
        exit 2
    fi
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --checkpoint) require_value "$@"; CHECKPOINT="$2"; shift 2 ;;
        --deck) require_value "$@"; DECK="$2"; shift 2 ;;
        --output-dir) require_value "$@"; OUTPUT_DIR="$2"; shift 2 ;;
        --run-name) require_value "$@"; RUN_NAME="$2"; shift 2 ;;
        --model-name) require_value "$@"; MODEL_NAME="$2"; shift 2 ;;
        --model-description) require_value "$@"; MODEL_DESCRIPTION="$2"; shift 2 ;;
        --games) require_value "$@"; GAMES="$2"; shift 2 ;;
        --start-game) require_value "$@"; START_GAME="$2"; shift 2 ;;
        --max-actions) require_value "$@"; MAX_ACTIONS="$2"; shift 2 ;;
        --device) require_value "$@"; DEVICE="$2"; shift 2 ;;
        --tables) require_value "$@"; TABLES="$2"; shift 2 ;;
        --config-root) require_value "$@"; CONFIG_ROOT="$2"; shift 2 ;;
        --mcts-simulations) require_value "$@"; MCTS_SIMULATIONS="$2"; shift 2 ;;
        --mcts-max-depth) require_value "$@"; MCTS_MAX_DEPTH="$2"; shift 2 ;;
        --mcts-c-puct) require_value "$@"; MCTS_C_PUCT="$2"; shift 2 ;;
        --mcts-dirichlet-alpha) require_value "$@"; MCTS_DIRICHLET_ALPHA="$2"; shift 2 ;;
        --mcts-dirichlet-epsilon) require_value "$@"; MCTS_DIRICHLET_EPSILON="$2"; shift 2 ;;
        --mcts-temperature) require_value "$@"; MCTS_TEMPERATURE="$2"; shift 2 ;;
        --mcts-per-decision-seconds) require_value "$@"; MCTS_PER_DECISION_SECONDS="$2"; shift 2 ;;
        --mcts-game-budget-seconds) require_value "$@"; MCTS_GAME_BUDGET_SECONDS="$2"; shift 2 ;;
        --mcts-seed) require_value "$@"; MCTS_SEED="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$CHECKPOINT" ] || [ -z "$DECK" ] || [ -z "$OUTPUT_DIR" ]; then
    echo "--checkpoint, --deck, and --output-dir are required." >&2
    exit 2
fi

CONFIG_LOG="$CONFIG_ROOT/$RUN_NAME/selfplay-generation-${SLURM_JOB_ID:-manual}.json"
mkdir -p "$WORKDIR/logs" "$OUTPUT_DIR" "$(dirname "$CONFIG_LOG")"
cd "$WORKDIR"
module purge > /dev/null 2>&1 || true
source "$ENVIRONMENT/bin/activate"

ARGS=(
    --checkpoint "$CHECKPOINT"
    --deck "$DECK"
    --output-dir "$OUTPUT_DIR"
    --tables "$TABLES"
    --games "$GAMES"
    --max-actions "$MAX_ACTIONS"
    --device "$DEVICE"
    --model-name "$MODEL_NAME"
    --model-description "$MODEL_DESCRIPTION"
    --config-log "$CONFIG_LOG"
    --mcts-simulations "$MCTS_SIMULATIONS"
    --mcts-max-depth "$MCTS_MAX_DEPTH"
    --mcts-c-puct "$MCTS_C_PUCT"
    --mcts-dirichlet-alpha "$MCTS_DIRICHLET_ALPHA"
    --mcts-dirichlet-epsilon "$MCTS_DIRICHLET_EPSILON"
    --mcts-temperature "$MCTS_TEMPERATURE"
    --mcts-seed "$MCTS_SEED"
)
if [ -n "$START_GAME" ]; then
    ARGS+=(--start-game "$START_GAME")
fi
if [ -n "$MCTS_PER_DECISION_SECONDS" ]; then
    ARGS+=(--mcts-per-decision-seconds "$MCTS_PER_DECISION_SECONDS")
fi
if [ -n "$MCTS_GAME_BUDGET_SECONDS" ]; then
    ARGS+=(--mcts-game-budget-seconds "$MCTS_GAME_BUDGET_SECONDS")
fi

python -u Engine-Native-Architecture/scripts/generate_selfplay.py "${ARGS[@]}"
