#!/bin/bash
# ============================================================================
#  AiMOS / NPL  --  evoV2.py  (Clefable MCTS evolutionary weight optimizer)
#
#  Submit from the NPL front end:   ssh nplfen01   then:
#      sbatch /gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/Evo-V2/submit-batch-evo-v2.sh
#
#  NPL notes:
#    * Each GPU auto-allocates 10 CPU cores. We request 2 GPUs → 20 CPU cores
#      to match WORKERS=20 below. No GPU compute is actually used.
#    * Default time limit is 6 h. evoV2.py checkpoints after every generation,
#      so if the wall approaches, this script re-queues itself with --resume.
# ============================================================================

#SBATCH --job-name=ClefableEvoV2
#SBATCH --output=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.out
#SBATCH --error=/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes/logs/%x-%j.err
#SBATCH --nodes=1
#SBATCH --gres=gpu:2                 # 2 GPUs → 20 CPU cores; no GPU compute used
#SBATCH --time=06:00:00
#SBATCH --signal=B:USR1@180          # fire SIGUSR1 180 s before the wall
#SBATCH --open-mode=append

set -euo pipefail

# ============================================================================
#  EDIT ME
# ============================================================================
WORKDIR="/gpfs/u/barn/MINF/MINFlshm/RL/KaggleRLPokes"
SCRIPT="$WORKDIR/Evo-V2/submit-batch-evo-v2.sh"   # absolute path for self-requeue
OUTDIR="$WORKDIR/Evo-V2/evo_output_v2"            # explicit — avoids nested-path bugs
MAX_RESUBMITS=20

GENERATIONS=10
POPULATION=8
WORKERS=20
ELITE=2
SIGMA_INIT=0.30
SIGMA_FINAL=0.05
GAMES=50                             # total evaluation games per candidate (split vs champ + baseline)
RESUME=false
# ============================================================================

mkdir -p "$WORKDIR/logs" "$OUTDIR"
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
source "$WORKDIR/myenv/bin/activate"

# ---- self-requeue on approaching time limit ----
: "${RESUBMIT_COUNT:=0}"
requeue() {
    if [ "$RESUBMIT_COUNT" -lt "$MAX_RESUBMITS" ]; then
        echo "[$(date)] Time limit approaching -- re-queueing with --resume"
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
echo "Output dir:  $OUTDIR"

# ---- run evoV2 ----
if [ "$RESUBMIT_COUNT" -gt 0 ] || [ "$RESUME" = "true" ]; then
    RESUME_FLAG="--resume"
else
    RESUME_FLAG=""
fi

python -u Evo-V2/evoV2.py \
    --generations  "$GENERATIONS" \
    --population   "$POPULATION" \
    --workers      "$WORKERS" \
    --elite        "$ELITE" \
    --sigma-init   "$SIGMA_INIT" \
    --sigma-final  "$SIGMA_FINAL" \
    --games        "$GAMES" \
    --output-dir   "$OUTDIR" \
    $RESUME_FLAG &

PYPID=$!
wait "$PYPID"

echo "[$(date)] Evolution completed cleanly. No re-queue needed."
