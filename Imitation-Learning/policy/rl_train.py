"""Spec 16 follow-on: self-play PPO training for the deck-agnostic policy model.

Mirrors `Ceruledge-RL/train.py`'s proven PPO design (structure and the Stage-1-only
gradient precedent -- Stage 2 candidate selection always runs greedy, no RL gradient),
adapted to this model's very different I/O (174-word observation, 8 verbs, variable-length
Stage-2 candidates instead of Track A's fixed 19-action/23-word tensors). Independent of
`Ceruledge-RL/actions.py`/`model.py`/`train.py`, which are not touched.

Algorithm : PPO (clipped surrogate + clipped value baseline), Stage-1 verb only.
Reward    : +1.0 win, -1.0 loss, 0.0 draw.
Deck      : FULL_DECK on both sides (confirmed scope -- see
            Ceruledge-RL/specs/16-generalized-action-space.md's follow-on plan).
"""
from __future__ import annotations

import argparse
import copy
import os
import random
import sys
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
_CERULEDGE_RL = os.path.join(_REPO_ROOT, "Ceruledge-RL")
sys.path.insert(0, _REPO_ROOT)     # cg_download
sys.path.insert(0, _CERULEDGE_RL)  # features.FULL_DECK/GameStateTracker, prize_check.PrizeTracker
sys.path.insert(0, _IL_ROOT)       # observation, policy

import torch
import torch.nn.functional as F

from cg_download.api import SelectContext, to_observation_class  # noqa: E402
from cg_download.game import battle_finish, battle_select, battle_start  # noqa: E402
from features import FULL_DECK, GameStateTracker  # noqa: E402
from observation.encoder import GameState, build_observation  # noqa: E402
from observation.live_adapter import build_game_state  # noqa: E402
from prize_check import PrizeTracker  # noqa: E402

from . import acting  # noqa: E402
from .model import PolicyModel  # noqa: E402


@dataclass
class Step:
    state: GameState
    action: int              # Stage-1 verb index, 0..7
    log_prob: float
    value: float
    reward: float = 0.0       # 0.0 except the terminal step of an episode
    done: bool = False
    mask: torch.Tensor = None  # (8,) additive mask -- a fact about that decision


# ── Episode collection ──────────────────────────────────────────────────────────

def collect_episode(
    model: PolicyModel, opponent_model: PolicyModel, our_side: int, go_first: bool,
    deck: list[int],
) -> tuple[list[Step], float]:
    obs_dict, start_data = battle_start(deck, deck)
    if obs_dict is None or start_data.errorPlayer >= 0:
        battle_finish()
        return [], 0.0

    trackers = {0: GameStateTracker(), 1: GameStateTracker()}
    prize_trackers = {0: PrizeTracker(), 1: PrizeTracker()}

    steps: list[Step] = []
    pending: dict | None = None

    while True:
        if obs_dict["current"]["result"] >= 0:
            break
        obs = to_observation_class(obs_dict)
        ctx = obs.select.context if obs.select else None
        your_idx = obs.current.yourIndex
        acting_model = model if your_idx == our_side else opponent_model
        sample = your_idx == our_side

        if ctx == SelectContext.IS_FIRST:
            yes = go_first if your_idx == our_side else not go_first
            selected = acting.answer_yes_no(obs, yes)
        elif ctx == SelectContext.SETUP_ACTIVE_POKEMON:
            selected = acting.setup_active_heuristic(obs, your_idx)
        elif ctx == SelectContext.SETUP_BENCH_POKEMON:
            selected = acting.setup_bench_heuristic(obs)
        else:
            state = build_game_state(
                obs, your_idx, prize_trackers[your_idx],
                trackers[your_idx], trackers[1 - your_idx],
            )
            if ctx == SelectContext.MAIN:
                result = acting.act_main(acting_model, obs, your_idx, state, sample=sample)
                selected = result.selected
                if your_idx == our_side:
                    if pending is not None:
                        steps.append(Step(**pending, reward=0.0, done=False))
                    pending = dict(
                        state=state, action=result.verb_index,
                        log_prob=result.log_prob, value=result.value, mask=result.mask,
                    )
            else:
                selected = acting.act_sub_selection(acting_model, obs, your_idx, state)

        try:
            obs_dict = battle_select(selected)
        except IndexError:
            selected = acting.random_legal_selection(obs)
            obs_dict = battle_select(selected)

    result = obs_dict["current"]["result"]
    reward = 1.0 if result == our_side else (-1.0 if result != 2 else 0.0)
    if pending is not None:
        steps.append(Step(**pending, reward=reward, done=True))
    battle_finish()
    return steps, reward


# ── GAE ──────────────────────────────────────────────────────────────────────────

def compute_gae(steps: list[Step], gamma: float, gae_lambda: float) -> tuple[list[float], list[float]]:
    advantages = [0.0] * len(steps)
    returns = [0.0] * len(steps)
    gae = 0.0
    for t in reversed(range(len(steps))):
        s = steps[t]
        if s.done:
            next_val = 0.0
            gae = 0.0
        else:
            next_val = steps[t + 1].value if t + 1 < len(steps) else 0.0
        delta = s.reward + gamma * next_val - s.value
        gae = delta + gamma * gae_lambda * gae
        advantages[t] = gae
        returns[t] = gae + s.value
    return advantages, returns


# ── PPO update ─────────────────────────────────────────────────────────────────

def ppo_update(
    model: PolicyModel, optimizer: torch.optim.Optimizer, steps: list[Step],
    advantages: list[float], returns: list[float], ppo_epochs: int, ppo_clip: float,
    value_loss_coef: float, entropy_coef: float, max_grad_norm: float,
) -> dict:
    n = len(steps)
    if n == 0:
        return {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "epochs_run": 0}

    all_words = [build_observation(s.state) for s in steps]  # pure, weight-independent -- hoisted
    actions_b = torch.tensor([s.action for s in steps], dtype=torch.long)
    old_lp_b = torch.tensor([s.log_prob for s in steps], dtype=torch.float32)
    old_val_b = torch.tensor([s.value for s in steps], dtype=torch.float32)
    masks_b = torch.stack([s.mask for s in steps])  # (N, 8)
    adv_b = torch.tensor(advantages, dtype=torch.float32)
    ret_b = torch.tensor(returns, dtype=torch.float32)
    adv_b = (adv_b - adv_b.mean()) / (adv_b.std(unbiased=False) + 1e-8)

    total_pl = total_vl = total_ent = 0.0
    epochs_run = 0
    for _ in range(ppo_epochs):
        pooled_b = torch.stack([model.encode(w)[1] for w in all_words])  # (N, D) -- re-run every epoch
        logits_b = model.stage1_logits(pooled_b)   # (N, 8)
        values_b = model.value(pooled_b)           # (N,)

        masked_logits = torch.nan_to_num(logits_b + masks_b, nan=float("-inf"))
        log_probs = F.log_softmax(masked_logits, dim=-1)
        new_lp = log_probs.gather(1, actions_b.unsqueeze(1)).squeeze(1)
        ratio = torch.exp(new_lp - old_lp_b)
        clipped = torch.clamp(ratio, 1 - ppo_clip, 1 + ppo_clip)
        policy_loss = -torch.min(ratio * adv_b, clipped * adv_b).mean()

        v_unclipped = (values_b - ret_b) ** 2
        v_clipped_val = old_val_b + torch.clamp(values_b - old_val_b, -ppo_clip, ppo_clip)
        v_clipped = (v_clipped_val - ret_b) ** 2
        value_loss = 0.5 * torch.max(v_unclipped, v_clipped).mean()

        probs = torch.softmax(masked_logits, dim=-1)
        entropy = -(probs * log_probs).sum(-1).mean()

        loss = policy_loss + value_loss_coef * value_loss - entropy_coef * entropy
        if not torch.isfinite(loss):
            print("[ppo_update] NaN/Inf loss -- skipping gradient step", flush=True)
            continue

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
        optimizer.step()

        total_pl += policy_loss.item()
        total_vl += value_loss.item()
        total_ent += entropy.item()
        epochs_run += 1

    d = max(epochs_run, 1)
    return {
        "policy_loss": total_pl / d, "value_loss": total_vl / d,
        "entropy": total_ent / d, "epochs_run": epochs_run,
    }


# ── Checkpointing ──────────────────────────────────────────────────────────────

def _load_weights(model: PolicyModel, path: str) -> None:
    """Accepts an RL checkpoint ("model" key), an IL checkpoint ("model_state_dict" key,
    from policy/train.py), or a bare state dict. strict=False so an IL checkpoint missing
    the value head (added after IL was written) still loads cleanly."""
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    state_dict = ckpt.get("model") or ckpt.get("model_state_dict") or ckpt
    result = model.load_state_dict(state_dict, strict=False)
    if result.missing_keys or result.unexpected_keys:
        print(f"[load_weights] {path}: missing={result.missing_keys} unexpected={result.unexpected_keys}")


def save_checkpoint(path: str, model: PolicyModel, optimizer: torch.optim.Optimizer,
                     update: int, history: dict) -> None:
    tmp = path + ".tmp"
    torch.save({
        "model": {k: v.cpu() for k, v in model.state_dict().items()},
        "optimizer": optimizer.state_dict(),
        "update": update,
        "history": history,
    }, tmp)
    os.replace(tmp, path)


# ── Training loop ────────────────────────────────────────────────────────────────

def train(args):
    os.makedirs(args.out_dir, exist_ok=True)
    ckpt_path = os.path.join(args.out_dir, "checkpoint.pt")

    model = PolicyModel()
    if args.self_bot:
        _load_weights(model, args.self_bot)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    start_update = 1
    history = {"reward": [], "policy_loss": [], "value_loss": [], "entropy": []}
    if args.resume and os.path.exists(ckpt_path):
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        start_update = ckpt["update"] + 1
        history = ckpt.get("history", history)
        print(f"[resume] continuing from update {start_update}")

    opponent_model = PolicyModel()
    if args.opponent_bot:
        _load_weights(opponent_model, args.opponent_bot)
    else:
        opponent_model = copy.deepcopy(model).cpu()
    opponent_model.eval()

    for update in range(start_update, args.n_updates + 1):
        all_steps: list[Step] = []
        results = []
        for ep in range(args.episodes_per_update):
            our_side = ep % 2
            go_first = (ep // 2) % 2 == 0
            steps, reward = collect_episode(model, opponent_model, our_side, go_first, FULL_DECK)
            all_steps.extend(steps)
            results.append(reward)

        advantages, returns = compute_gae(all_steps, args.gamma, args.gae_lambda)
        metrics = ppo_update(
            model, optimizer, all_steps, advantages, returns,
            args.ppo_epochs, args.ppo_clip, args.value_loss_coef,
            args.entropy_coef, args.max_grad_norm,
        )

        wins = sum(1 for r in results if r > 0)
        losses = sum(1 for r in results if r < 0)
        draws = sum(1 for r in results if r == 0)
        avg_reward = sum(results) / len(results) if results else 0.0
        history["reward"].append(avg_reward)
        history["policy_loss"].append(metrics["policy_loss"])
        history["value_loss"].append(metrics["value_loss"])
        history["entropy"].append(metrics["entropy"])

        if update % args.log_every == 0:
            print(
                f"[update {update}] avg_reward={avg_reward:.3f} "
                f"wins={wins} losses={losses} draws={draws} "
                f"policy_loss={metrics['policy_loss']:.4f} "
                f"value_loss={metrics['value_loss']:.4f} "
                f"entropy={metrics['entropy']:.4f} "
                f"n_steps={len(all_steps)}",
                flush=True,
            )

        if args.self_play_update_every and update % args.self_play_update_every == 0:
            opponent_model = copy.deepcopy(model).cpu()
            opponent_model.eval()
            print(f"[update {update}] refreshed frozen self-play opponent", flush=True)

        if update % args.save_every == 0 or update == args.n_updates:
            save_checkpoint(ckpt_path, model, optimizer, update, history)

    print(f"done -- checkpoint at {ckpt_path}")
    return history


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--episodes-per-update", type=int, default=16)
    p.add_argument("--ppo-epochs", type=int, default=4)
    p.add_argument("--ppo-clip", type=float, default=0.2)
    p.add_argument("--value-loss-coef", type=float, default=0.5)
    p.add_argument("--entropy-coef", type=float, default=0.01)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--gae-lambda", type=float, default=0.95)
    p.add_argument("--max-grad-norm", type=float, default=0.5)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--n-updates", type=int, default=10)
    p.add_argument("--log-every", type=int, default=1)
    p.add_argument("--save-every", type=int, default=5)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--self-bot", default=None, help="checkpoint path for the trainable policy's starting weights")
    p.add_argument("--opponent-bot", default=None, help="checkpoint path for the frozen opponent's starting weights")
    p.add_argument("--self-play-update-every", type=int, default=0,
                   help="refresh the frozen opponent from live weights every N updates (0 = never)")
    p.add_argument("--resume", action="store_true")
    return p.parse_args(argv)


if __name__ == "__main__":
    random.seed(0)
    torch.manual_seed(0)
    train(parse_args())
