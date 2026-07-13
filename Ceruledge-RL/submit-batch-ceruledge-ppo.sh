#!/bin/bash
# ============================================================================
#  AiMOS / NPL  --  Ceruledge PPO training
#
#  Submit from the NPL front end:   ssh nplfen01   then:
#      sbatch /gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/Ceruledge-RL/submit-batch-ceruledge-ppo.sh
#
#  NPL notes:
#    * We request 1 GPU (auto-allocates 10 CPU cores). Episodes are collected
#      sequentially on CPU; the GPU is used only for the PPO gradient update.
#    * Time limit is 6 h. train.py writes OUT_DIR/checkpoint.pth after
#      every update; when the wall approaches, this script re-queues itself and
#      the new job continues from that checkpoint via --resume (model, optimizer,
#      update counter, epsilon, and the same wandb run).
# ============================================================================

#SBATCH --job-name=CeruledgePPO
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --gres=gpu:1                 # 1 GPU for the PPO gradient update (episodes collected on CPU)
#SBATCH --time=06:00:00
#SBATCH --signal=B:USR1@180          # fire SIGUSR1 180 s before the wall
#SBATCH --open-mode=append

set -euo pipefail

# ============================================================================
#  EDIT ME
# ============================================================================
# Single naming knob: drives OUT_DIR and the wandb run name. When you change it,
# also update #SBATCH --job-name above and (if you rename this file) SCRIPT below.
MODEL_NAME="rules-v2"
# Free-text note recorded in run_config.json + wandb notes — say what this run is
DESCRIPTION="No description provided for this run."

WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
SCRIPT="$WORKDIR/Ceruledge-RL/submit-batch-ceruledge-ppo.sh"  # for self-requeue
MAX_RESUBMITS=20

# ── Output ────────────────────────────────────────────────────────────────────
OUT_DIR="$WORKDIR/Ceruledge-RL/out/$MODEL_NAME"

# ── Opponent ──────────────────────────────────────────────────────────────────
# Single opponent — any registry name from Ceruledge-RL/opponents.py:
#   "ceruledge_rules" ("rules" = legacy alias) | "clefable" | "alakazam"
#   | "lucario" | "random" | "self"
# OR a weighted per-episode pool — set OPPONENT_POOL (OPPONENT is then ignored):
#   OPPONENT_POOL="clefable:2,lucario:1,self:1,random:0.5,ceruledge_rules:1"
#
# DEPLOY: every file-agent in the active set needs its folder copied next to
# Ceruledge-RL/ under $WORKDIR, deck file at EXACT casing (Linux is
# case-sensitive), in addition to cg_download/:
#   Ceruledge-Agent/   main.py + deck.csv                («ceruledge_rules»)
#   Clefable-Agent/    main.py + deck.csv                («clefable»)
#   Alakazam-Agent/    main.py + Deck.csv  — capital D   («alakazam»)
#   Lucario-Baseline/  mega_lucario_baseline.py          («lucario»)
# train.py validates the whole active set before episode 0 and aborts naming
# the missing path if a folder wasn't copied — never mid-run.
OPPONENT="random"
OPPONENT_POOL=""
SELF_PLAY_UPDATE_EVERY=20

# ── PPO hyperparameters ───────────────────────────────────────────────────────
EPISODES_PER_UPDATE=128
PPO_EPOCHS=10
PPO_CLIP=0.2
# Early-stop epochs when approx KL(old||new) exceeds this (0.0 = disabled).
# This is what makes 8-10 epochs safe: extra epochs only run while the
# policy stays close to the rollout policy.
TARGET_KL=0.02
VALUE_LOSS_COEF=0.5
ENTROPY_COEF=0.01
GAMMA=0.99
GAE_LAMBDA=0.95
MAX_GRAD_NORM=0.5
LR=1e-3
N_UPDATES=50

# ── Reward shaping ────────────────────────────────────────────────────────────
# 0.0 = win/loss only; 0.01 = small per-prize bonus
PRIZE_REWARD=0.0
# 0.0 = off; reward per 10 damage dealt to the opponent (0.01 = cluster default)
DAMAGE_REWARD=0.01

# ── Exploration ───────────────────────────────────────────────────────────────
# Pass --use-stochastic-sampling or --use-epsilon-greedy to enable.
# Leave blank for fully greedy collection (argmax).
# EXPLORATION_FLAGS=""
EXPLORATION_FLAGS="--use-stochastic-sampling"
# EXPLORATION_FLAGS="--use-epsilon-greedy"
EPSILON_START=0.3
EPSILON_END=0.05
EPSILON_DECAY=0.998

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_EVERY=10
SAVE_EVERY=50

# ── Weights & Biases ──────────────────────────────────────────────────────────
# Requires: pip install wandb  AND  wandb login  (run once on the cluster)
# OR set WANDB_API_KEY env var before submitting.
# Leave WANDB_RUN_NAME blank to let wandb auto-generate a name.
WANDB_PROJECT="batch-rules-v2"
WANDB_RUN_NAME="wandb_$MODEL_NAME"
# Uncomment to disable wandb entirely:
WANDB_FLAGS="--no-wandb"
# WANDB_FLAGS=""
# ============================================================================

mkdir -p "$WORKDIR/logs" "$OUT_DIR"
cd "$WORKDIR"

# ---- environment ----
module purge > /dev/null 2>&1 || true

export http_proxy=http://proxy:8888
export https_proxy=${http_proxy}
module load gcc

CONDA_BASE="/gpfs/u/barn/MINF/MINFlshm/miniforge3"

if [ ! -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    echo "ERROR: conda.sh not found at $CONDA_BASE/etc/profile.d/conda.sh"
    exit 1
fi

source "$CONDA_BASE/etc/profile.d/conda.sh"
source "$WORKDIR/../myenv/bin/activate"

# ---- self-requeue on approaching time limit ----
: "${RESUBMIT_COUNT:=0}"
requeue() {
    if [ "$RESUBMIT_COUNT" -lt "$MAX_RESUBMITS" ]; then
        echo "[$(date)] Time limit approaching -- re-queueing"
        echo "          (resubmit $((RESUBMIT_COUNT + 1))/$MAX_RESUBMITS)"
        sbatch --export=ALL,RESUBMIT_COUNT=$((RESUBMIT_COUNT + 1)) "$SCRIPT"
    else
        echo "[$(date)] Hit MAX_RESUBMITS=$MAX_RESUBMITS; not re-queueing."
    fi
    [ -n "${PYPID:-}" ] && kill "$PYPID" 2>/dev/null || true
    exit 0
}
trap requeue USR1

# ---- debug info ----
echo "Job $SLURM_JOB_ID  (resubmit #$RESUBMIT_COUNT)  starting at $(date)"
echo "Node: $(hostname)   CPUs: $(nproc)"
echo "Working dir: $(pwd)"
if [ -n "$OPPONENT_POOL" ]; then
    OPPONENT_ARGS=(--opponent-pool "$OPPONENT_POOL")
    echo "Opponent pool: $OPPONENT_POOL"
else
    OPPONENT_ARGS=(--opponent "$OPPONENT")
    echo "Opponent:    $OPPONENT"
fi
echo "Out dir:     $OUT_DIR"

# ---- run training ----
# --resume is always passed: first run finds no checkpoint and starts fresh;
# requeued runs continue from OUT_DIR/checkpoint.pth.
python -u Ceruledge-RL/train.py \
    --resume \
    --episodes-per-update "$EPISODES_PER_UPDATE" \
    --ppo-epochs          "$PPO_EPOCHS" \
    --ppo-clip            "$PPO_CLIP" \
    --target-kl           "$TARGET_KL" \
    --value-loss-coef     "$VALUE_LOSS_COEF" \
    --entropy-coef        "$ENTROPY_COEF" \
    --gamma               "$GAMMA" \
    --gae-lambda          "$GAE_LAMBDA" \
    --max-grad-norm       "$MAX_GRAD_NORM" \
    --lr                  "$LR" \
    --n-updates           "$N_UPDATES" \
    --prize-reward        "$PRIZE_REWARD" \
    --damage-reward       "$DAMAGE_REWARD" \
    --log-every           "$LOG_EVERY" \
    --save-every          "$SAVE_EVERY" \
    --out-dir             "$OUT_DIR" \
    --epsilon-start       "$EPSILON_START" \
    --epsilon-end         "$EPSILON_END" \
    --epsilon-decay       "$EPSILON_DECAY" \
    "${OPPONENT_ARGS[@]}" \
    --self-play-update-every  "$SELF_PLAY_UPDATE_EVERY" \
    --wandb-project           "$WANDB_PROJECT" \
    --wandb-run-name          "$WANDB_RUN_NAME" \
    --description             "$DESCRIPTION" \
    $EXPLORATION_FLAGS \
    $WANDB_FLAGS &

PYPID=$!
wait "$PYPID"

echo "[$(date)] Training completed cleanly. No re-queue needed."
