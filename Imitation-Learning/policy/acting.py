"""Live inference: turn a fresh `cg_download.api.Observation` into `battle_select`-ready
option indices, for both the trainable and frozen self-play sides. Nothing in
`policy/data.py`/`policy/train.py` (imitation learning) produces a live action for a
fresh observation -- they only ever compute a loss against an already-known recorded one.
This module is that missing piece, used by `rl_train.py`'s `collect_episode`.
"""
from __future__ import annotations

import os
import random
import sys
from dataclasses import dataclass

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _IL_ROOT)

from cg_download.api import AreaType, Observation, OptionType  # noqa: E402
from observation import card_data  # noqa: E402
from observation.encoder import GameState, build_observation  # noqa: E402

from . import action_space as asp  # noqa: E402
from . import scoring  # noqa: E402
from .model import PolicyModel  # noqa: E402


def answer_yes_no(obs: Observation, yes: bool) -> list[int]:
    want = OptionType.YES if yes else OptionType.NO
    for i, o in enumerate(obs.select.option):
        if o.type == want:
            return [i]
    return [0] if obs.select.option else []


def setup_active_heuristic(obs: Observation, our_idx: int) -> list[int]:
    """Highest-HP Basic Pokemon in hand -- generic (card_data attribute lookup), unlike
    Track A's hardcoded per-card preference order, since this bot must work for any
    deck."""
    opts = obs.select.option
    hand = obs.current.players[our_idx].hand or ()
    best_i, best_hp = None, -1
    for i, o in enumerate(opts):
        if o.type != OptionType.CARD or o.area != AreaType.HAND:
            continue
        if o.index is None or o.index >= len(hand):
            continue
        static = card_data.get_card_static(hand[o.index].id)
        if static is None or static.card_class != "pokemon" or "Basic" not in (static.subtype or ""):
            continue
        hp = static.hp or 0
        if hp > best_hp:
            best_hp, best_i = hp, i
    if best_i is not None:
        return [best_i]
    return [0] if opts else []


def setup_bench_heuristic(obs: Observation) -> list[int]:
    """Decline whenever legal, satisfy only a forced minimum -- already deck-agnostic in
    Track A (no card names involved), reused verbatim."""
    if not obs.select.option or (obs.select.minCount or 0) == 0:
        return []
    return [0]


def random_legal_selection(obs: Observation) -> list[int]:
    """Defensive fallback for the `battle_select` `IndexError` retry."""
    opts = obs.select.option
    if not opts:
        return []
    min_cnt = obs.select.minCount or 0
    max_cnt = obs.select.maxCount if obs.select.maxCount is not None else len(opts)
    max_cnt = max(min_cnt, min(max_cnt, len(opts)))
    n = random.randint(min_cnt, max_cnt)
    return random.sample(range(len(opts)), n) if n > 0 else []


@dataclass
class ActResult:
    selected: list[int]
    log_prob: float | None = None
    value: float | None = None
    verb_index: int | None = None
    mask: torch.Tensor | None = None


def act_main(
    model: PolicyModel, obs: Observation, our_idx: int, game_state: GameState, sample: bool,
) -> ActResult:
    words = build_observation(game_state)
    word_embeddings, pooled = model.encode(words)

    action_map = asp.build_action_map(obs)
    if not action_map:
        return ActResult(selected=[0] if obs.select.option else [])

    logits = model.stage1_logits(pooled)
    mask = torch.full((asp.N_VERBS,), float("-inf"))
    for t in action_map:
        mask[asp.VERB_INDEX[t]] = 0.0
    masked_logits = torch.nan_to_num(logits + mask, nan=float("-inf"))
    value = model.value(pooled).item()

    legal_indices = {asp.VERB_INDEX[t] for t in action_map}
    if sample:
        probs = torch.softmax(masked_logits, dim=-1)
        verb_idx = int(torch.multinomial(probs, 1).item())
    else:
        verb_idx = int(masked_logits.argmax().item())
    if verb_idx not in legal_indices:
        verb_idx = min(legal_indices)  # NaN-argmax safety net

    log_prob = torch.log_softmax(masked_logits, dim=-1)[verb_idx].item()
    chosen_type = asp.VERBS[verb_idx]
    option_indices = action_map[chosen_type]

    candidates = asp.classify_candidates(obs, our_idx, option_indices)
    scores = scoring.score_candidates(model, words, word_embeddings, pooled, chosen_type, candidates)
    best_local = int(scores.argmax().item())  # Stage 2 always greedy, per the confirmed scope
    selected = [option_indices[best_local]]

    return ActResult(
        selected=selected, log_prob=log_prob, value=value, verb_index=verb_idx, mask=mask,
    )


def act_sub_selection(
    model: PolicyModel, obs: Observation, our_idx: int, game_state: GameState,
) -> list[int]:
    """Every non-MAIN/IS_FIRST/SETUP_* context. No STOP-token mechanism exists on this
    model (unlike Track A's `include_stop` scorer) -- always picks exactly
    `min(maxCount, len(options))` candidates sequentially, re-scoring the shrinking pool
    each pick. Always legal (`minCount <= maxCount <= len(option)` per the engine's own
    contract); accepted v1 simplification, see `Ceruledge-RL/specs/16-...` follow-on
    notes."""
    opts = obs.select.option
    if not opts:
        return []
    words = build_observation(game_state)
    word_embeddings, pooled = model.encode(words)

    min_cnt = obs.select.minCount or 0
    max_cnt = obs.select.maxCount if obs.select.maxCount is not None else len(opts)
    n_pick = max(0, min(max_cnt, len(opts)))
    option_type = opts[0].type  # representative type -- mirrors policy/data.py's own assumption

    remaining = list(range(len(opts)))
    chosen: list[int] = []
    for _ in range(n_pick):
        if not remaining:
            break
        candidates = asp.classify_candidates(obs, our_idx, remaining)
        scores = scoring.score_candidates(model, words, word_embeddings, pooled, option_type, candidates)
        pick = remaining[int(scores.argmax().item())]
        chosen.append(pick)
        remaining.remove(pick)
    while len(chosen) < min_cnt and remaining:
        chosen.append(remaining.pop(0))
    return chosen
