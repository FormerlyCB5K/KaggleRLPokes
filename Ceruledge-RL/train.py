"""
train.py — Canonical Ceruledge PPO trainer for local and cluster runs.

Algorithm : PPO (clipped surrogate objective + value baseline)
Reward    : +1.0 win, -1.0 loss, 0.0 draw  (no shaping in this experiment)
Exploration: epsilon-greedy at Stage 1 during rollout collection

Resume    : pass --resume to continue from OUT_DIR/checkpoint.pth if it exists
            (model + optimizer + update counter + epsilon + histories + wandb
            run id). A checkpoint is written atomically after every update, so
            an interrupted job loses at most one update's work.
"""
from __future__ import annotations

import sys
import os
_here   = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_here)
sys.path.insert(0, _here)    # Ceruledge-RL first — local imports win
sys.path.insert(1, _parent)  # parent for cg_download

import copy
import json
import random
from dataclasses import dataclass
from datetime import datetime

import torch
import torch.optim as optim
import torch.nn.functional as F
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

try:
    import wandb as _wandb
    _WANDB_AVAILABLE = True
except ImportError:
    _wandb = None
    _WANDB_AVAILABLE = False

from cg_download.api import to_observation_class, SelectContext, OptionType
from cg_download.game import battle_start, battle_finish, battle_select

from features import FULL_DECK, GameStateTracker, extract_features
from model import (CeruledgePolicy, N_ACTIONS,
                   D_MODEL, D_FF, N_HEADS, N_LAYERS)
from actions import select_action, build_action_map, select_main_stage2
from random_agent import random_agent
from opponents import OPPONENTS, parse_pool_spec, validate_opponents

def _self_play_action(obs, active_side, opp_model, opp_tracker):
    """Greedy action for the frozen self-play opponent; no Step is recorded."""
    ctx = obs.select.context if obs.select else None
    if ctx == SelectContext.SETUP_ACTIVE_POKEMON:
        return _setup_active(obs)
    if ctx == SelectContext.SETUP_BENCH_POKEMON:
        return _setup_bench(obs)
    selected, _ = select_action(obs, active_side, opp_model, opp_tracker, greedy=True)
    return selected or [0]


def _file_agent_move(opponent: dict, obs_dict) -> list[int]:
    """File-agent opponent move. Import failures crash loudly at resolve time
    (never silently train vs random); per-move agent errors fall back to a
    random legal action."""
    try:
        return opponent["policy"](obs_dict)
    except Exception as e:
        print(f"[{opponent['name']} agent error] {e}", flush=True)
        return random_agent(obs_dict)

# ── Hyperparameters ────────────────────────────────────────────────────────────
EPISODES_PER_UPDATE = 128    # rollout batch size (episodes)
PPO_EPOCHS          = 10       # gradient epochs per update
PPO_CLIP            = 0.2      # clipping epsilon
TARGET_KL           = 0.02     # stop epochs early when approx KL exceeds this; 0.0 = disabled
VALUE_LOSS_COEF     = 0.5
ENTROPY_COEF        = 0.01
GAMMA               = 0.99
GAE_LAMBDA          = 0.95
MAX_GRAD_NORM       = 0.5
LR                  = 1e-3
N_UPDATES           = 10      # total update iterations (= 300 × 16 = 4800 episodes)
PRIZE_REWARD        = 0.0      # per-prize shaping reward; 0.0 = disabled, 0.01 = light shaping
DAMAGE_REWARD       = 0.01     # reward per 10 damage dealt; 0.0 = disabled (cluster default 0.01)
LOG_EVERY           = 1       # print/plot every N updates
SAVE_EVERY          = 50
OUT_DIR             = "out/TEST_train-new-architecture"
DESCRIPTION         = "running a training run on laptop while I sleep. lets see how it goes."
# ── Exploration switches (both off = fully deterministic greedy policy) ────────
USE_EPSILON_GREEDY      = False  # Stage 1: random legal action with prob epsilon
USE_STOCHASTIC_SAMPLING = True  # Stage 1: sample from softmax instead of argmax
EPSILON_START           = 0.3
EPSILON_END             = 0.05
EPSILON_DECAY           = 0.998  # per update

# ── Opponent ──────────────────────────────────────────────────────────────────
OPPONENT = "rules"              # any OPPONENTS key; "rules" = ceruledge_rules alias
SELF_PLAY_UPDATE_EVERY = 50     # refresh frozen opponent copy every N updates
DEVICE                 = torch.device("cuda" if torch.cuda.is_available() else "cpu")
WANDB_PROJECT          = "ceruledge-ppo"
WANDB_RUN_NAME         = ""     # "" = wandb auto-generates a name
USE_WANDB              = True   # set False or pass --no-wandb to disable

# ── CLI overrides (used by batch submission scripts) ──────────────────────────
import argparse as _ap
_p = _ap.ArgumentParser(description="Ceruledge PPO training", add_help=True)
_p.add_argument("--episodes-per-update", type=int,   default=EPISODES_PER_UPDATE)
_p.add_argument("--ppo-epochs",          type=int,   default=PPO_EPOCHS)
_p.add_argument("--ppo-clip",            type=float, default=PPO_CLIP)
_p.add_argument("--target-kl",           type=float, default=TARGET_KL)
_p.add_argument("--value-loss-coef",     type=float, default=VALUE_LOSS_COEF)
_p.add_argument("--entropy-coef",        type=float, default=ENTROPY_COEF)
_p.add_argument("--gamma",               type=float, default=GAMMA)
_p.add_argument("--gae-lambda",          type=float, default=GAE_LAMBDA)
_p.add_argument("--max-grad-norm",       type=float, default=MAX_GRAD_NORM)
_p.add_argument("--lr",                  type=float, default=LR)
_p.add_argument("--n-updates",           type=int,   default=N_UPDATES)
_p.add_argument("--prize-reward",        type=float, default=PRIZE_REWARD)
_p.add_argument("--damage-reward",       type=float, default=DAMAGE_REWARD)
_p.add_argument("--log-every",           type=int,   default=LOG_EVERY)
_p.add_argument("--save-every",          type=int,   default=SAVE_EVERY)
_p.add_argument("--out-dir",             type=str,   default=OUT_DIR)
_p.add_argument("--epsilon-start",       type=float, default=EPSILON_START)
_p.add_argument("--epsilon-end",         type=float, default=EPSILON_END)
_p.add_argument("--epsilon-decay",       type=float, default=EPSILON_DECAY)
_p.add_argument("--use-epsilon-greedy",      action="store_true", default=USE_EPSILON_GREEDY)
_p.add_argument("--use-stochastic-sampling",  action="store_true", default=USE_STOCHASTIC_SAMPLING)
_p.add_argument("--opponent",                 type=str, choices=sorted(OPPONENTS) + ["rules"], default=None,
                help="single registry opponent for every episode ('rules' = ceruledge_rules)")
_p.add_argument("--opponent-pool",            type=str, default=None,
                help="weighted per-episode opponent pool: comma-separated name[:weight], "
                     "e.g. clefable:2,lucario:1,self:1,random:0.5 (weight defaults to 1.0; "
                     "relative). Mutually exclusive with --opponent.")
_p.add_argument("--self-play-update-every",   type=int, default=SELF_PLAY_UPDATE_EVERY)
_p.add_argument("--wandb-project",            type=str, default=WANDB_PROJECT)
_p.add_argument("--wandb-run-name",           type=str, default=WANDB_RUN_NAME)
_p.add_argument("--no-wandb",                 action="store_true", default=False)
_p.add_argument("--description",              type=str, default=DESCRIPTION,
                help="free-text note recorded in run_config.json and wandb notes")
_p.add_argument("--resume",                   action="store_true", default=False,
                help="continue from OUT_DIR/checkpoint.pth if it exists")
_p.add_argument("--workers",                  type=int, default=1,
                help="parallel episode-collection worker processes (1 = sequential)")
_args, _ = _p.parse_known_args()

EPISODES_PER_UPDATE     = _args.episodes_per_update
PPO_EPOCHS              = _args.ppo_epochs
PPO_CLIP                = _args.ppo_clip
TARGET_KL               = _args.target_kl
VALUE_LOSS_COEF         = _args.value_loss_coef
ENTROPY_COEF            = _args.entropy_coef
GAMMA                   = _args.gamma
GAE_LAMBDA              = _args.gae_lambda
MAX_GRAD_NORM           = _args.max_grad_norm
LR                      = _args.lr
N_UPDATES               = _args.n_updates
PRIZE_REWARD            = _args.prize_reward
DAMAGE_REWARD           = _args.damage_reward
LOG_EVERY               = _args.log_every
SAVE_EVERY              = _args.save_every
OUT_DIR                 = _args.out_dir
EPSILON_START           = _args.epsilon_start
EPSILON_END             = _args.epsilon_end
EPSILON_DECAY           = _args.epsilon_decay
USE_EPSILON_GREEDY      = _args.use_epsilon_greedy
USE_STOCHASTIC_SAMPLING = _args.use_stochastic_sampling
if _args.opponent is not None and _args.opponent_pool is not None:
    _p.error("--opponent and --opponent-pool are mutually exclusive")
OPPONENT                = _args.opponent if _args.opponent is not None else OPPONENT
if OPPONENT == "rules":
    OPPONENT = "ceruledge_rules"   # legacy alias
OPPONENT_POOL: dict[str, float] | None = None
if _args.opponent_pool is not None:
    try:
        OPPONENT_POOL = parse_pool_spec(_args.opponent_pool)
    except ValueError as e:
        _p.error(str(e))
SELF_PLAY_UPDATE_EVERY  = _args.self_play_update_every
WORKERS                 = _args.workers
WANDB_PROJECT           = _args.wandb_project
WANDB_RUN_NAME          = _args.wandb_run_name
USE_WANDB               = _WANDB_AVAILABLE and not _args.no_wandb
DESCRIPTION             = _args.description
RESUME                  = _args.resume
PLOT_DIR                = os.path.join(OUT_DIR, "plots")
CKPT_PATH               = os.path.join(OUT_DIR, "checkpoint.pth")

# Full run configuration: every CLI switch (resolved values) + runtime extras
# + model architecture constants. Dumped to OUT_DIR/run_config.json at start.
RUN_CONFIG: dict = {
    **dict(vars(_args)),
    "device":    str(DEVICE),
    "use_wandb": USE_WANDB,
    "model": {
        "d_model":  D_MODEL,
        "d_ff":     D_FF,
        "n_heads":  N_HEADS,
        "n_layers": N_LAYERS,
        "n_actions": N_ACTIONS,
    },
}


def save_run_config():
    """Write the resolved run configuration to OUT_DIR/run_config.json."""
    path = os.path.join(OUT_DIR, "run_config.json")
    with open(path, "w") as f:
        json.dump(
            {"started_at": datetime.now().isoformat(timespec="seconds"), **RUN_CONFIG},
            f, indent=2,
        )
    print(f"Run config saved: {path}", flush=True)

# ── Setup helpers ──────────────────────────────────────────────────────────────
from features import Ceruledge_ex, Charcadet, Solrock, Lunatone, Drilbur
from cg_download.api import AreaType


def _answer_yes_no(obs, yes: bool) -> list[int]:
    for i, o in enumerate(obs.select.option):
        if yes and o.type == OptionType.YES:
            return [i]
        if not yes and o.type == OptionType.NO:
            return [i]
    return [0]


def _setup_active(obs) -> list[int]:
    opts = obs.select.option
    ps   = obs.current.players[obs.current.yourIndex]
    h    = ps.hand or []
    for pid in [Solrock, Charcadet, Lunatone, Drilbur]:
        for i, o in enumerate(opts):
            if o.type == OptionType.CARD and o.area == AreaType.HAND:
                if o.index is not None and o.index < len(h) and h[o.index].id == pid:
                    return [i]
    return [0]


def _setup_bench(obs) -> list[int]:
    # We never bench during setup on purpose: there is no upside to committing extra
    # Pokemon before the turn develops, and benching is done later through normal MAIN
    # play. Decline whenever the engine allows it; only satisfy a forced minimum.
    if not obs.select.option or (obs.select.minCount or 0) == 0:
        return []
    return [0]


def _opp_hp_total(obs, our_side: int) -> int:
    """Sum of current HP across the opponent's in-play Pokemon."""
    opp   = obs.current.players[1 - our_side]
    total = 0
    for p in list(opp.active or []) + list(opp.bench or []):
        if p is not None:
            total += getattr(p, "hp", 0) or 0
    return total


# ── Trajectory storage ─────────────────────────────────────────────────────────

@dataclass
class Step:
    our_pokemon: torch.Tensor   # (9, 19)
    opp_pokemon: torch.Tensor   # (9, 75)
    zones:    torch.Tensor   # (4, 16)
    glob:     torch.Tensor   # (24,)
    action:   int            # Stage 1 action index
    log_prob: float          # log π(action | state) under masked dist at collection time
    value:    float          # V(state) at collection time
    reward:   float          # step reward (0 except terminal)
    done:     bool           # True on last step of episode
    mask:     torch.Tensor   # (N_ACTIONS,) additive mask: 0.0 legal, -inf illegal


# ── Episode collection ─────────────────────────────────────────────────────────

def collect_episode(
    model:          CeruledgePolicy,
    epsilon:        float,
    our_side:       int,
    go_first:       bool,
    opponent:       dict,
    opponent_model: CeruledgePolicy | None = None,
) -> tuple[list[Step], float]:
    """
    Run one episode vs `opponent` (a resolve_opponent() dict: name/kind/policy/
    deck), recording a Step for every policy decision in MAIN context.
    Returns (steps, episode_reward).
    Stage 2 selections are greedy and are not stored for PPO; Step.log_prob contains
    only the Stage 1 action probability.
    """
    # Our deck on our side, the opponent's native deck on the other —
    # battle_start(deck_for_side0, deck_for_side1) maps positionally.
    if our_side == 0:
        obs_dict, start_data = battle_start(FULL_DECK, opponent["deck"])
    else:
        obs_dict, start_data = battle_start(opponent["deck"], FULL_DECK)
    if obs_dict is None:
        return [], 0.0
    if start_data.errorPlayer >= 0:
        battle_finish()
        return [], 0.0

    tracker     = GameStateTracker()
    opp_tracker = GameStateTracker() if opponent_model is not None else None
    steps:  list[Step] = []
    # Hold pending step until we know the next value or episode end
    pending: dict | None = None
    our_prizes_prev = 6      # tracks our prize count to detect prize-taking
    opp_hp_prev: int | None = None  # opponent total in-play HP, for damage shaping
    inter_reward    = 0.0    # shaping rewards accumulated between MAIN steps

    def flush_pending(done: bool, reward: float = 0.0):
        if pending is not None:
            steps.append(Step(
                our_pokemon=pending['our_pokemon'],
                opp_pokemon=pending['opp_pokemon'],
                zones=pending['zones'],
                glob=pending['glob'],
                action=pending['action'],
                log_prob=pending['log_prob'],
                value=pending['value'],
                reward=reward,
                done=done,
                mask=pending['mask'],
            ))

    while True:
        result = obs_dict["current"]["result"]
        if result >= 0:
            break

        obs      = to_observation_class(obs_dict)
        ctx      = obs.select.context if obs.select else None
        your_idx = obs.current.yourIndex

        if your_idx == our_side:
            if ctx == SelectContext.IS_FIRST:
                selected = _answer_yes_no(obs, yes=go_first)
            elif ctx == SelectContext.SETUP_ACTIVE_POKEMON:
                selected = _setup_active(obs)
            elif ctx == SelectContext.SETUP_BENCH_POKEMON:
                selected = _setup_bench(obs)
            elif ctx == SelectContext.MAIN:
                our_poke, opp_poke, zones, glob = extract_features(obs, our_side, tracker)

                with torch.no_grad():
                    words, pooled, logits, val = model(
                        our_poke.unsqueeze(0),
                        opp_poke.unsqueeze(0),
                        zones.unsqueeze(0),
                        glob.unsqueeze(0),
                    )
                words  = words.squeeze(0)
                pooled = pooled.squeeze(0)
                logits = logits.squeeze(0)
                val    = val.item()

                # Build Stage 1 legal-action mask from current game state
                action_map = build_action_map(obs, our_side)
                step_mask  = torch.full((N_ACTIONS,), float('-inf'))
                for act_id in action_map:
                    step_mask[act_id] = 0.0

                if not action_map:
                    selected = [0]
                    # No legal policy decision — flush old pending but do NOT record
                    # a new step: storing lp=0.0 here produces exp(new_lp - 0) as IS
                    # ratio, which is invalid and can cause NaN entropy → NaN loss.
                    if pending is not None:
                        flush_pending(done=False, reward=inter_reward)
                        inter_reward = 0.0
                        pending = None
                else:
                    masked_logits = logits + step_mask
                    # NaN can arise from inf logits (transformer overflow with random
                    # init): inf + (-inf) = NaN, which breaks argmax. Clamp to -inf.
                    masked_logits = torch.nan_to_num(masked_logits, nan=float('-inf'))

                    # Stage 1 action selection
                    if USE_EPSILON_GREEDY and random.random() < epsilon:
                        action1 = random.choice(list(action_map.keys()))
                    elif USE_STOCHASTIC_SAMPLING:
                        probs   = F.softmax(masked_logits, dim=-1)
                        action1 = int(torch.multinomial(probs, 1).item())
                    else:
                        action1 = int(masked_logits.argmax().item())

                    # Safety: if all logits were NaN, argmax may still return an
                    # illegal index. Fall back to the first legal action.
                    if action1 not in action_map:
                        action1 = next(iter(action_map))

                    # Log-prob of chosen action under the masked policy distribution
                    lp = F.log_softmax(masked_logits, dim=-1)[action1].item()

                    # Stage 2: pick option(s) within the chosen category
                    selected = select_main_stage2(
                        obs, our_side, words, pooled, action1, action_map, model
                    )
                    if not selected:
                        selected = action_map[action1][:1]

                    if not selected:
                        selected = [0]

                    if pending is not None:
                        flush_pending(done=False, reward=inter_reward)
                        inter_reward = 0.0

                    pending = dict(
                        our_pokemon=our_poke.detach(),
                        opp_pokemon=opp_poke.detach(),
                        zones=zones.detach(),
                        glob=glob.detach(),
                        action=action1,
                        log_prob=lp,
                        value=val,
                        mask=step_mask,
                    )
            else:
                # Sub-selection context — greedy; log_prob not stored for PPO
                selected, _ = select_action(obs, our_side, model, tracker, greedy=True)
                if not selected:
                    selected = [0]
        else:
            if ctx == SelectContext.IS_FIRST:
                selected = _answer_yes_no(obs, yes=not go_first)
            elif opponent["kind"] == "self" and opponent_model is not None:
                selected = _self_play_action(obs, 1 - our_side, opponent_model, opp_tracker)
            elif opponent["kind"] == "file":
                selected = _file_agent_move(opponent, obs_dict)
            else:
                selected = random_agent(obs_dict)

        try:
            obs_dict = battle_select(selected)
        except IndexError:
            # The engine rejected `selected` as an illegal option set. This
            # happens intermittently when the rules opponent computes an
            # out-of-range option index for some board state. Fall back to a
            # uniformly random legal selection so a single bad move doesn't
            # crash the whole run. (random_agent samples valid indices only.)
            selected = random_agent(obs_dict)
            obs_dict = battle_select(selected)

        # Reward shaping, checked after every state change
        if (PRIZE_REWARD > 0.0 or DAMAGE_REWARD > 0.0) and obs_dict["current"]["result"] < 0:
            new_obs = to_observation_class(obs_dict)

            # Prize shaping: detect when our prize count drops (we took a prize)
            if PRIZE_REWARD > 0.0:
                new_ps  = new_obs.current.players[our_side]
                new_prizes = len(new_ps.prize) if new_ps.prize is not None else our_prizes_prev
                if new_prizes < our_prizes_prev:
                    inter_reward += PRIZE_REWARD * (our_prizes_prev - new_prizes)
                our_prizes_prev = new_prizes

            # Damage shaping: DAMAGE_REWARD per 10 damage, measured as drops in
            # the opponent's total in-play HP. A KO counts as the victim's
            # remaining HP. Increases (opponent playing/evolving Pokemon) only
            # raise the baseline — never a penalty.
            if DAMAGE_REWARD > 0.0:
                new_hp = _opp_hp_total(new_obs, our_side)
                if opp_hp_prev is not None and new_hp < opp_hp_prev:
                    inter_reward += DAMAGE_REWARD * (opp_hp_prev - new_hp) / 10.0
                opp_hp_prev = new_hp

    result = obs_dict["current"]["result"]
    reward = 1.0 if result == our_side else (-1.0 if result != 2 else 0.0)

    # Flush last pending step with terminal reward (+ any unsent prize rewards)
    if pending is not None:
        flush_pending(done=True, reward=reward + inter_reward)

    battle_finish()
    return steps, reward


# ── GAE computation ────────────────────────────────────────────────────────────

def compute_gae(steps: list[Step]) -> tuple[list[float], list[float]]:
    """
    Compute GAE advantages and discounted returns for a flat list of steps.
    Works across episode boundaries (done=True resets the bootstrap).
    """
    advantages = [0.0] * len(steps)
    returns    = [0.0] * len(steps)
    gae        = 0.0

    for t in reversed(range(len(steps))):
        s = steps[t]
        if s.done:
            next_val = 0.0
            gae      = 0.0
        else:
            next_val = steps[t + 1].value if t + 1 < len(steps) else 0.0

        delta        = s.reward + GAMMA * next_val - s.value
        gae          = delta + GAMMA * GAE_LAMBDA * gae
        advantages[t] = gae
        returns[t]    = gae + s.value

    return advantages, returns


# ── PPO update ─────────────────────────────────────────────────────────────────

def ppo_update(
    model:      CeruledgePolicy,
    optimizer:  optim.Optimizer,
    steps:      list[Step],
    advantages: list[float],
    returns:    list[float],
    device:     torch.device = torch.device("cpu"),
) -> tuple[float, float, float, float, int]:
    """
    Run up to PPO_EPOCHS gradient steps over the collected batch, stopping
    early once approx KL(old‖new) exceeds TARGET_KL (if enabled).
    Returns (mean_policy_loss, mean_value_loss, mean_entropy, approx_kl, epochs_run).
    """
    n = len(steps)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0, 0

    our_poke_b = torch.stack([s.our_pokemon for s in steps]).to(device)        # (N, 9, 19)
    opp_poke_b = torch.stack([s.opp_pokemon for s in steps]).to(device)        # (N, 9, 75)
    zones_b    = torch.stack([s.zones    for s in steps]).to(device)           # (N, 4, 16)
    glob_b     = torch.stack([s.glob     for s in steps]).to(device)           # (N, 24)
    masks_b    = torch.stack([s.mask     for s in steps]).to(device)           # (N, N_ACTIONS)
    actions_b  = torch.tensor([s.action   for s in steps], dtype=torch.long,    device=device)
    old_lp_b   = torch.tensor([s.log_prob for s in steps], dtype=torch.float32, device=device)
    old_val_b  = torch.tensor([s.value    for s in steps], dtype=torch.float32, device=device)
    adv_b      = torch.tensor(advantages,                  dtype=torch.float32, device=device)
    ret_b      = torch.tensor(returns,                     dtype=torch.float32, device=device)

    adv_b = (adv_b - adv_b.mean()) / (adv_b.std(unbiased=False) + 1e-8)

    total_pl = total_vl = total_ent = 0.0
    approx_kl  = 0.0
    epochs_run = 0

    for _ in range(PPO_EPOCHS):
        _, _, logits, values = model(our_poke_b, opp_poke_b, zones_b, glob_b)

        # Apply per-step legal-action mask — keeps new_lp and old_lp in the same
        # masked distribution so the ratio is valid.
        masked_logits = torch.nan_to_num(logits + masks_b, nan=float('-inf'))
        log_probs = F.log_softmax(masked_logits, dim=-1)
        new_lp    = log_probs.gather(1, actions_b.unsqueeze(1)).squeeze(1)

        logratio = new_lp - old_lp_b
        ratio    = torch.exp(logratio)

        # Approx KL(old‖new), k3 estimator (Schulman, kl-approx blog post).
        # If the policy has drifted past TARGET_KL, stop before pushing further —
        # this is what makes 8-10 epochs safe.
        with torch.no_grad():
            approx_kl = ((ratio - 1) - logratio).mean().item()
        if TARGET_KL > 0.0 and approx_kl > TARGET_KL:
            break

        clipped = torch.clamp(ratio, 1 - PPO_CLIP, 1 + PPO_CLIP)
        policy_loss = -torch.min(ratio * adv_b, clipped * adv_b).mean()

        # Clipped value loss (CleanRL default: clip new value around old value)
        v_loss_unclipped = (values - ret_b) ** 2
        v_clipped        = old_val_b + torch.clamp(
            values - old_val_b, -PPO_CLIP, PPO_CLIP
        )
        v_loss_clipped = (v_clipped - ret_b) ** 2
        value_loss = 0.5 * torch.max(v_loss_unclipped, v_loss_clipped).mean()

        # Entropy over the masked (legal-action) distribution
        probs   = F.softmax(masked_logits, dim=-1)
        entropy = -(probs * log_probs).sum(-1).mean()

        loss = policy_loss + VALUE_LOSS_COEF * value_loss - ENTROPY_COEF * entropy

        if not torch.isfinite(loss):
            print(f"[ppo_update] NaN/Inf loss — skipping gradient step", flush=True)
            continue

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), MAX_GRAD_NORM)
        optimizer.step()

        total_pl  += policy_loss.item()
        total_vl  += value_loss.item()
        total_ent += entropy.item()
        epochs_run += 1

    denom = max(epochs_run, 1)
    return total_pl / denom, total_vl / denom, total_ent / denom, approx_kl, epochs_run


# ── Checkpointing ──────────────────────────────────────────────────────────────

def save_checkpoint(model, optimizer, update, epsilon,
                    reward_history, winrate_history, update_nums,
                    per_opp_history, wandb_run_id):
    """Atomically write the complete resumable training state."""
    tmp = CKPT_PATH + ".tmp"
    torch.save({
        "model":           {k: v.cpu() for k, v in model.state_dict().items()},
        "optimizer":       optimizer.state_dict(),
        "update":          update,
        "epsilon":         epsilon,
        "reward_history":  reward_history,
        "winrate_history": winrate_history,
        "update_nums":     update_nums,
        "per_opponent_history": per_opp_history,
        "wandb_run_id":    wandb_run_id,
    }, tmp)
    os.replace(tmp, CKPT_PATH)


def _optimizer_to(optimizer, device):
    """Move restored optimizer tensors to the model's runtime device."""
    for state in optimizer.state.values():
        for key, value in state.items():
            if torch.is_tensor(value):
                state[key] = value.to(device)


# ── Training loop ──────────────────────────────────────────────────────────────

def train():
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(PLOT_DIR, exist_ok=True)
    save_run_config()

    # Validate the whole active set before episode 0 (spec 09d) — a missing or
    # broken member aborts here with its path named, never mid-run. Doubles as
    # warming the module-loader cache.
    if OPPONENT_POOL is not None:
        pool_names   = list(OPPONENT_POOL)
        pool_weights = [OPPONENT_POOL[n] for n in pool_names]
    else:
        pool_names   = [OPPONENT]
        pool_weights = [1.0]
    active   = validate_opponents(pool_names)
    has_self = any(o["kind"] == "self" for o in active.values())

    model     = CeruledgePolicy().to(DEVICE)
    optimizer = optim.Adam(model.parameters(), lr=LR, eps=1e-5)
    epsilon   = EPSILON_START

    reward_history:  list[float] = []
    winrate_history: list[float] = []
    update_nums:     list[int]   = []
    # name -> {"updates": [...], "winrates": [...]}; sparse per name because an
    # opponent can draw zero episodes in an update (spec 09e)
    per_opp_history: dict[str, dict[str, list]] = {}
    start_update = 1
    wandb_run_id: str | None = None

    if RESUME and os.path.exists(CKPT_PATH):
        ckpt = torch.load(CKPT_PATH, map_location="cpu", weights_only=False)
        model.load_state_dict(ckpt["model"])
        model.to(DEVICE)
        optimizer.load_state_dict(ckpt["optimizer"])
        _optimizer_to(optimizer, DEVICE)
        epsilon         = ckpt["epsilon"]
        reward_history  = ckpt["reward_history"]
        winrate_history = ckpt["winrate_history"]
        update_nums     = ckpt["update_nums"]
        # pre-09e checkpoints lack the key — start those histories fresh
        per_opp_history = ckpt.get("per_opponent_history", {})
        wandb_run_id    = ckpt.get("wandb_run_id")
        start_update    = ckpt["update"] + 1
        print(f"Resumed from {CKPT_PATH}: continuing at update {start_update}", flush=True)
    elif RESUME:
        print(f"--resume set but no checkpoint at {CKPT_PATH}; starting fresh", flush=True)

    for _name in pool_names:
        per_opp_history.setdefault(_name, {"updates": [], "winrates": []})

    # Frozen self-play opponent stays on CPU (episode collection runs on CPU).
    # Create it after resume so it starts from restored rather than random weights.
    opponent_model: CeruledgePolicy | None = None
    if has_self:
        opponent_model = copy.deepcopy(model).cpu()
        opponent_model.eval()

    # Parallel episode collection (spawn pool of CPU actors). Created after the
    # model/optimizer so the learner's own CUDA context already exists before the
    # actors hide CUDA. workers == 1 keeps the original single-process path.
    collector = None
    if WORKERS > 1:
        from parallel_collect import ParallelCollector
        collector = ParallelCollector(
            WORKERS, _here, _parent,
            dict(use_epsilon_greedy=USE_EPSILON_GREEDY,
                 use_stochastic_sampling=USE_STOCHASTIC_SAMPLING,
                 prize_reward=PRIZE_REWARD, damage_reward=DAMAGE_REWARD))
        print(f"Parallel collection: {WORKERS} spawn workers", flush=True)

    if OPPONENT_POOL is not None:
        opp_desc = "pool " + ",".join(f"{n}:{w:g}" for n, w in OPPONENT_POOL.items())
    else:
        opp_desc = OPPONENT
    print(f"Training: Ceruledge PPO vs. {opp_desc}")
    print(f"Updates: {start_update}..{N_UPDATES}  Episodes/update: {EPISODES_PER_UPDATE}  "
          f"PPO epochs: {PPO_EPOCHS}  clip: {PPO_CLIP}")
    print(f"Device: {DEVICE}", flush=True)

    if USE_WANDB:
        _wandb.init(
            project=WANDB_PROJECT,
            name=WANDB_RUN_NAME or None,
            id=wandb_run_id,
            resume="allow",
            notes=DESCRIPTION,
            config={
                "episodes_per_update":   EPISODES_PER_UPDATE,
                "ppo_epochs":            PPO_EPOCHS,
                "ppo_clip":              PPO_CLIP,
                "target_kl":             TARGET_KL,
                "value_loss_coef":       VALUE_LOSS_COEF,
                "entropy_coef":          ENTROPY_COEF,
                "gamma":                 GAMMA,
                "gae_lambda":            GAE_LAMBDA,
                "max_grad_norm":         MAX_GRAD_NORM,
                "lr":                    LR,
                "n_updates":             N_UPDATES,
                "prize_reward":          PRIZE_REWARD,
                "damage_reward":         DAMAGE_REWARD,
                "opponent":              opp_desc,
                "device":                str(DEVICE),
                "use_epsilon_greedy":    USE_EPSILON_GREEDY,
                "use_stochastic_sampling": USE_STOCHASTIC_SAMPLING,
                "epsilon_start":         EPSILON_START,
                "epsilon_end":           EPSILON_END,
                "epsilon_decay":         EPSILON_DECAY,
                "self_play_update_every": SELF_PLAY_UPDATE_EVERY,
            },
        )
        wandb_run_id = _wandb.run.id
        print(f"wandb run: {_wandb.run.name}  url: {_wandb.run.url}", flush=True)

    for update in range(start_update, N_UPDATES + 1):
            # Refresh frozen self-play opponent copy
            if opponent_model is not None and update % SELF_PLAY_UPDATE_EVERY == 0:
                opponent_model = copy.deepcopy(model).cpu()
                opponent_model.eval()
                print(f"  [self-play] Refreshed opponent copy at update {update}", flush=True)

            # ── Collect rollout (CPU inference; GPU used only for batch update) ──
            # One opponent drawn per episode, proportional to pool weight
            # (single-opponent mode is a one-name pool with weight 1).
            episode_opponents = random.choices(
                pool_names, weights=pool_weights, k=EPISODES_PER_UPDATE)
            model.eval()
            if collector is not None:
                # Parallel: learner stays on DEVICE; the collector broadcasts a CPU
                # snapshot to the actor pool and returns the same
                # (opp_name, steps, reward) tuples as the sequential path.
                results = collector.collect(
                    model, episode_opponents, epsilon,
                    self_model=opponent_model if has_self else None)
            else:
                model.cpu()
                results = [
                    (opp_name, *collect_episode(
                        model, epsilon,
                        ep % 2, (ep // 2) % 2 == 0,
                        active[opp_name],
                        opponent_model if active[opp_name]["kind"] == "self" else None,
                    ))
                    for ep, opp_name in enumerate(episode_opponents)
                ]
                model.to(DEVICE)

            all_steps: list[Step] = []
            wins = draws = losses = 0
            opp_results: dict[str, list[float]] = {n: [] for n in pool_names}
            for opp_name, steps, reward in results:
                all_steps.extend(steps)
                opp_results[opp_name].append(reward)
                if   reward > 0: wins   += 1
                elif reward < 0: losses += 1
                else:            draws  += 1

            # ── Compute advantages ─────────────────────────────────────────────
            advantages, returns = compute_gae(all_steps)

            # ── PPO update (on DEVICE) ─────────────────────────────────────────
            model.train()
            pl, vl, ent, kl, kl_epochs = ppo_update(
                model, optimizer, all_steps, advantages, returns, DEVICE)

            if USE_EPSILON_GREEDY:
                epsilon = max(EPSILON_END, epsilon * EPSILON_DECAY)

            # ── Logging ────────────────────────────────────────────────────────
            if update % LOG_EVERY == 0:
                total    = wins + draws + losses
                win_rate = wins / total if total else 0.0
                avg_rew  = (wins - losses) / total if total else 0.0

                reward_history.append(avg_rew)
                winrate_history.append(win_rate)
                update_nums.append(update)

                # Per-opponent winrate buckets (spec 09e). Sparse: an opponent
                # with zero episodes this update gets no point, no line.
                opp_lines: list[str] = []
                wandb_opp: dict[str, float] = {}
                for name in pool_names:
                    rs = opp_results[name]
                    if not rs:
                        continue
                    wr = sum(1 for r in rs if r > 0) / len(rs)
                    per_opp_history[name]["updates"].append(update)
                    per_opp_history[name]["winrates"].append(wr)
                    opp_lines.append(f"{name}={100*wr:.0f}% (n={len(rs)})")
                    wandb_opp[f"winrate/{name}"]  = wr
                    wandb_opp[f"episodes/{name}"] = len(rs)

                print(
                    f"Update {update:4d} | eps={epsilon:.3f} | "
                    f"win={wins} loss={losses} draw={draws} | "
                    f"win%={100*win_rate:.1f}  avg_r={avg_rew:.3f} | "
                    f"pi_loss={pl:.4f}  v_loss={vl:.4f}  ent={ent:.4f}  "
                    f"kl={kl:.4f} ({kl_epochs}/{PPO_EPOCHS} epochs)",
                    flush=True,
                )
                print(f"    opponents: {'  '.join(opp_lines)}", flush=True)
                if USE_WANDB:
                    _wandb.log({
                        "win_rate":        win_rate,
                        "avg_reward":      avg_rew,
                        "wins":            wins,
                        "losses":          losses,
                        "draws":           draws,
                        "policy_loss":     pl,
                        "value_loss":      vl,
                        "entropy":         ent,
                        "approx_kl":       kl,
                        "ppo_epochs_run":  kl_epochs,
                        "epsilon":         epsilon,
                        "steps_collected": len(all_steps),
                        **wandb_opp,
                    }, step=update)

            if update % SAVE_EVERY == 0:
                path = os.path.join(OUT_DIR, f"policy_update{update}.pth")
                torch.save(model.state_dict(), path)
                print(f"  Saved: {path}")

            save_checkpoint(model, optimizer, update, epsilon,
                            reward_history, winrate_history, update_nums,
                            per_opp_history, wandb_run_id)

    if collector is not None:
        collector.close()

    # ── Final plots ────────────────────────────────────────────────────────────
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 10), sharex=True)

    ax1.plot(update_nums, reward_history)
    ax1.set_ylabel("Avg Reward")
    ax1.grid(True)

    ax2.plot(update_nums, winrate_history)
    ax2.set_ylabel("Win Rate")
    ax2.set_ylim(0, 1)
    ax2.axhline(0.5, color='gray', linestyle='--', alpha=0.5)
    ax2.grid(True)

    # Per-opponent winrate curves (spec 09e); sparse x per opponent because an
    # opponent can draw zero episodes in some updates.
    for name, h in sorted(per_opp_history.items()):
        if h["updates"]:
            # markers so an opponent sampled in only one update stays visible
            ax3.plot(h["updates"], h["winrates"], label=name,
                     marker="o", markersize=2.5)
    ax3.set_ylabel("Win Rate by Opponent")
    ax3.set_xlabel(f"Update (×{EPISODES_PER_UPDATE} episodes)")
    ax3.set_ylim(0, 1)
    ax3.axhline(0.5, color='gray', linestyle='--', alpha=0.5)
    ax3.grid(True)
    if any(h["updates"] for h in per_opp_history.values()):
        ax3.legend(loc="best", fontsize=8)

    fig.suptitle(f"Ceruledge PPO vs. {opp_desc}")
    plt.tight_layout()
    plot_path = os.path.join(PLOT_DIR, "training_curves.png")
    plt.savefig(plot_path)
    print(f"\nPlot saved to {plot_path}")

    torch.save(model.state_dict(), os.path.join(OUT_DIR, "policy_final.pth"))
    if USE_WANDB:
        _wandb.finish()
    print("Done.")


if __name__ == "__main__":
    train()
