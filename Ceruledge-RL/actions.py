"""
actions.py — Map between obs.select options and policy action vocab.

For MAIN context:
  - Classifies each legal option into a Stage 1 action category.
  - Runs Stage 1 to pick the best category (masked over illegal categories).
  - If the chosen category has multiple options (e.g. multiple attach targets),
    runs Stage 2 dot-product scoring to pick among them.
  - Returns a single option index.

For sub-selection contexts (TO_HAND, DISCARD, SWITCH, etc.):
  - Encodes each candidate via pile_mlp (cards) or board word vectors (Pokemon).
  - Runs sequential Stage 2 scoring to pick the required number of items.
  - Returns a list of option indices.
"""
from __future__ import annotations

import torch
import torch.nn.functional as F

from cg_download.api import (
    AreaType,
    Observation,
    OptionType,
    SelectContext,
)
from features import (
    Ceruledge_ex, Charcadet, Solrock, Lunatone, Drilbur,
    Fire_Energy, Fighting_Energy,
    Night_Stretcher, Brilliant_Blender, Fighting_Gong,
    Ultra_Ball, Poke_Pad, Boss_Orders, Explorers_Guidance, Carmine,
    GameStateTracker, N_POKEMON_SLOTS, encode_card_as_zone, extract_features,
)

_OPP_ACTIVE_WORD = N_POKEMON_SLOTS
_OPP_BENCH_WORD = _OPP_ACTIVE_WORD + 1
from model import (
    CeruledgePolicy,
    ACTION_PLAY_CERULEDGE, ACTION_PLAY_CHARCADET, ACTION_PLAY_SOLROCK,
    ACTION_PLAY_LUNATONE, ACTION_PLAY_DRILBUR, ACTION_PLAY_NIGHT_STRETCHER,
    ACTION_PLAY_BLENDER, ACTION_PLAY_FIGHTING_GONG, ACTION_PLAY_ULTRA_BALL,
    ACTION_PLAY_POKE_PAD, ACTION_PLAY_BOSS_ORDERS, ACTION_PLAY_EG,
    ACTION_PLAY_CARMINE, ACTION_ATTACH_FIRE, ACTION_ATTACH_FIGHTING,
    ACTION_RETREAT, ACTION_ATTACK, ACTION_LUNATONE_ABILITY, ACTION_PASS,
    N_ACTIONS, D_MODEL,
)

# Map card ID → Stage 1 action for PLAY options
_CARD_TO_ACTION: dict[int, int] = {
    Ceruledge_ex:       ACTION_PLAY_CERULEDGE,
    Charcadet:          ACTION_PLAY_CHARCADET,
    Solrock:            ACTION_PLAY_SOLROCK,
    Lunatone:           ACTION_PLAY_LUNATONE,
    Drilbur:            ACTION_PLAY_DRILBUR,
    Night_Stretcher:    ACTION_PLAY_NIGHT_STRETCHER,
    Brilliant_Blender:  ACTION_PLAY_BLENDER,
    Fighting_Gong:      ACTION_PLAY_FIGHTING_GONG,
    Ultra_Ball:         ACTION_PLAY_ULTRA_BALL,
    Poke_Pad:           ACTION_PLAY_POKE_PAD,
    Boss_Orders:        ACTION_PLAY_BOSS_ORDERS,
    Explorers_Guidance: ACTION_PLAY_EG,
    Carmine:            ACTION_PLAY_CARMINE,
}

_SUPPORTER_IDS = frozenset({Boss_Orders, Explorers_Guidance, Carmine})


def _get_hand_card_id(obs: Observation, opt, our_idx: int) -> int | None:
    ps = obs.current.players[our_idx]
    h  = ps.hand or []
    if opt.index is not None and opt.index < len(h):
        return h[opt.index].id
    return None


def _get_card_from_area(obs: Observation, opt, our_idx: int):
    """Resolve a CARD/ENERGY_CARD option to its card object."""
    ps = obs.current.players[our_idx]
    match opt.area:
        case AreaType.HAND:
            h = ps.hand or []
            if opt.index is not None and opt.index < len(h):
                return h[opt.index]
        case AreaType.DISCARD:
            target_ps = obs.current.players[opt.playerIndex] if opt.playerIndex is not None else ps
            d = target_ps.discard or []
            if opt.index is not None and opt.index < len(d):
                return d[opt.index]
        case AreaType.DECK:
            deck = obs.select.deck or []
            if opt.index is not None and opt.index < len(deck):
                return deck[opt.index]
        case AreaType.LOOKING:
            looking = obs.current.looking or []
            if opt.index is not None and opt.index < len(looking):
                return looking[opt.index]
        case AreaType.BENCH:
            target_ps = obs.current.players[opt.playerIndex] if opt.playerIndex is not None else ps
            b = target_ps.bench or []
            if opt.index is not None and opt.index < len(b):
                return b[opt.index]
        case AreaType.ACTIVE:
            target_ps = obs.current.players[opt.playerIndex] if opt.playerIndex is not None else ps
            a = target_ps.active or []
            if opt.index is not None and opt.index < len(a):
                return a[opt.index]
    return None


# ── Stage 2 sequential picker ─────────────────────────────────────────────────

def _stage2_pick_n(
    pooled:    torch.Tensor,          # (D_MODEL,)
    cands:     list[tuple[int, torch.Tensor]],  # [(option_idx, encoded_vec)]
    n:         int,
    model:     CeruledgePolicy,
    with_stop: bool = False,
) -> list[int]:
    """
    Sequentially pick n items from cands using dot-product scoring.
    If with_stop=True, adds a STOP token; stops early when STOP wins.
    Returns list of chosen option indices.
    """
    remaining = list(cands)
    chosen    = []

    for _ in range(n):
        if not remaining:
            break
        vecs       = torch.stack([v for _, v in remaining])    # (K, D)
        scores     = model.stage2_scores(pooled, vecs, include_stop=with_stop)
        best_local = int(scores.argmax().item())

        if with_stop and best_local == len(remaining):
            break  # STOP token won

        opt_idx, _ = remaining[best_local]
        chosen.append(opt_idx)
        remaining = [(i, v) for i, v in remaining if i != opt_idx]

    return chosen


# ── MAIN context helpers ───────────────────────────────────────────────────────

def build_action_map(obs: Observation, our_idx: int) -> dict[int, list[int]]:
    """
    Classify each legal MAIN-context option into a Stage 1 action category.
    Returns {action_id: [option_indices]}.
    """
    ps   = obs.current.players[our_idx]
    opts = obs.select.option
    action_map: dict[int, list[int]] = {}
    for i, o in enumerate(opts):
        act_id = None
        match o.type:
            case OptionType.PLAY:
                cid = _get_hand_card_id(obs, o, our_idx)
                act_id = _CARD_TO_ACTION.get(cid)
            case OptionType.EVOLVE:
                cid = _get_hand_card_id(obs, o, our_idx)
                if cid == Ceruledge_ex:
                    act_id = ACTION_PLAY_CERULEDGE
            case OptionType.ATTACH:
                h   = ps.hand or []
                cid = h[o.index].id if (o.index is not None and o.index < len(h)) else None
                if cid == Fire_Energy:
                    act_id = ACTION_ATTACH_FIRE
                elif cid == Fighting_Energy:
                    act_id = ACTION_ATTACH_FIGHTING
            case OptionType.RETREAT:
                act_id = ACTION_RETREAT
            case OptionType.ATTACK:
                act_id = ACTION_ATTACK
            case OptionType.ABILITY:
                b = ps.bench or []
                if (o.area == AreaType.BENCH and o.index is not None
                        and o.index < len(b) and b[o.index]
                        and b[o.index].id == Lunatone):
                    act_id = ACTION_LUNATONE_ABILITY
            case OptionType.END:
                act_id = ACTION_PASS
        if act_id is not None:
            action_map.setdefault(act_id, []).append(i)
    return action_map


def select_main_stage2(
    obs:        Observation,
    our_idx:    int,
    words:      torch.Tensor,         # (23, D_MODEL) post-transformer
    pooled:     torch.Tensor,         # (D_MODEL,)
    action1:    int,
    action_map: dict[int, list[int]],
    model:      CeruledgePolicy,
) -> list[int]:
    """
    Given the chosen Stage 1 action, pick the best option(s) from its
    candidate list using dot-product Stage 2 scoring.
    Returns list of selected option indices.
    """
    opts       = obs.select.option
    candidates = action_map.get(action1, [])
    if not candidates:
        return []
    if len(candidates) == 1:
        return [candidates[0]]

    cand_vecs: list[tuple[int, torch.Tensor]] = []
    for opt_i in candidates:
        o = opts[opt_i]
        if action1 in (ACTION_ATTACH_FIRE, ACTION_ATTACH_FIGHTING):
            if o.inPlayArea == AreaType.ACTIVE:
                vec = words[0]
            elif o.inPlayArea == AreaType.BENCH and o.inPlayIndex is not None:
                vec = words[1 + o.inPlayIndex]
            else:
                vec = torch.zeros(D_MODEL)
        elif action1 == ACTION_PLAY_CERULEDGE and o.type == OptionType.EVOLVE:
            if o.inPlayArea == AreaType.BENCH and o.inPlayIndex is not None:
                vec = words[1 + o.inPlayIndex]
            else:
                vec = torch.zeros(D_MODEL)
        else:
            vec = torch.zeros(D_MODEL)
        cand_vecs.append((opt_i, vec))

    picked = _stage2_pick_n(pooled, cand_vecs, n=1, model=model)
    return picked if picked else [candidates[0]]


# ── MAIN context handler ───────────────────────────────────────────────────────

def select_main_action(
    obs:     Observation,
    our_idx: int,
    model:   CeruledgePolicy,
    tracker: GameStateTracker,
    greedy:  bool = True,
) -> tuple[list[int], torch.Tensor]:
    """
    Handle a MAIN context decision.
    Returns (selected_option_indices, log_prob_tensor).
    """
    action_map = build_action_map(obs, our_idx)
    if not action_map:
        return [0], torch.tensor(0.0)

    our_poke, opp_poke, zones, glob = extract_features(obs, our_idx, tracker)
    with torch.no_grad() if greedy else torch.enable_grad():
        words, pooled, logits, _ = model(
            our_poke.unsqueeze(0),
            opp_poke.unsqueeze(0),
            zones.unsqueeze(0),
            glob.unsqueeze(0),
        )
    words  = words.squeeze(0)
    pooled = pooled.squeeze(0)
    logits = logits.squeeze(0)

    mask = torch.full((N_ACTIONS,), float('-inf'))
    for act_id in action_map:
        mask[act_id] = 0.0
    masked_logits = logits + mask

    probs = F.softmax(masked_logits, dim=-1)
    if greedy:
        chosen_act = int(probs.argmax().item())
    else:
        chosen_act = int(torch.multinomial(probs, 1).item())
    log_prob = torch.log(probs[chosen_act] + 1e-9)

    selected = select_main_stage2(obs, our_idx, words, pooled, chosen_act, action_map, model)
    return selected if selected else [action_map[chosen_act][0]], log_prob


# ── Sub-selection context handlers ────────────────────────────────────────────

def select_sub_action(
    obs:     Observation,
    our_idx: int,
    model:   CeruledgePolicy,
    tracker: GameStateTracker,
    greedy:  bool = True,
) -> tuple[list[int], torch.Tensor]:
    """
    Handle TO_HAND, DISCARD, SWITCH, TO_ACTIVE, DISCARD_ENERGY_CARD contexts.
    Returns (selected_option_indices, sum_log_prob_tensor).
    """
    ctx      = obs.select.context
    opts     = obs.select.option
    min_cnt  = obs.select.minCount or 1
    max_cnt  = obs.select.maxCount or 1
    effect   = obs.select.effect.id if obs.select.effect else None

    our_poke, opp_poke, zones, glob = extract_features(obs, our_idx, tracker)
    with torch.no_grad() if greedy else torch.enable_grad():
        words, pooled, _, __ = model(
            our_poke.unsqueeze(0),
            opp_poke.unsqueeze(0),
            zones.unsqueeze(0),
            glob.unsqueeze(0),
        )
    words  = words.squeeze(0)
    pooled = pooled.squeeze(0)

    match ctx:
        case SelectContext.TO_HAND | SelectContext.DISCARD | SelectContext.DISCARD_CARD_OR_ATTACHED_CARD:
            return _handle_card_selection(obs, our_idx, opts, pooled, model,
                                          min_cnt, max_cnt, greedy)

        case SelectContext.DISCARD_ENERGY_CARD:
            # Discard energy attached to retreating Pokemon — pick min_cnt energies
            return _handle_energy_discard(opts, pooled, model, min_cnt, greedy)

        case SelectContext.SWITCH:
            # Boss's Orders target OR retreat destination
            return _handle_switch(obs, our_idx, opts, words, pooled, model, effect, greedy)

        case SelectContext.TO_ACTIVE:
            # Promote after KO — pick a bench Pokemon
            return _handle_to_active(obs, our_idx, opts, words, pooled, model, greedy)

        case SelectContext.ACTIVATE:
            # Always YES for Drilbur / similar
            for i, o in enumerate(opts):
                if o.type == OptionType.YES:
                    return [i], torch.tensor(0.0)
            return [0], torch.tensor(0.0)

        case _:
            # Fallback: pick min_cnt random valid options
            avail = list(range(min(min_cnt, len(opts))))
            return avail, torch.tensor(0.0)


def _handle_card_selection(obs, our_idx, opts, pooled, model,
                            min_cnt, max_cnt, greedy):
    """
    TO_HAND or DISCARD: score individual cards as pile candidates.
    """
    cand_vecs: list[tuple[int, torch.Tensor]] = []
    for i, o in enumerate(opts):
        card = _get_card_from_area(obs, o, our_idx)
        if card is not None:
            zone_vec = encode_card_as_zone(card.id)
            vec      = model.encode_pile_candidate(zone_vec)
        else:
            vec = torch.zeros(D_MODEL)
        cand_vecs.append((i, vec))

    # Use STOP token for variable-length selections (Drilbur, Blender)
    use_stop   = max_cnt > min_cnt
    n_to_pick  = max_cnt

    with_stop_flag = use_stop and len(cand_vecs) > 0

    if not greedy:
        # During training, pick sequentially and accumulate log probs
        log_prob = torch.tensor(0.0, requires_grad=True)
        chosen   = []
        remaining = list(cand_vecs)
        for _ in range(n_to_pick):
            if not remaining:
                break
            vecs   = torch.stack([v for _, v in remaining])
            scores = model.stage2_scores(pooled, vecs, include_stop=with_stop_flag)
            probs  = F.softmax(scores, dim=-1)
            idx    = int(torch.multinomial(probs, 1).item())
            if with_stop_flag and idx == len(remaining):
                break
            opt_i, _ = remaining[idx]
            chosen.append(opt_i)
            log_prob = log_prob + torch.log(probs[idx] + 1e-9)
            remaining = [(i, v) for i, v in remaining if i != opt_i]
        return chosen, log_prob
    else:
        chosen = _stage2_pick_n(pooled, cand_vecs, n_to_pick, model, with_stop=with_stop_flag)
        if len(chosen) < min_cnt and cand_vecs:
            # Pad to min_cnt if STOP fired too early
            used = set(chosen)
            for opt_i, _ in cand_vecs:
                if opt_i not in used:
                    chosen.append(opt_i)
                    if len(chosen) >= min_cnt:
                        break
        return chosen, torch.tensor(0.0)


def _handle_energy_discard(opts, pooled, model, min_cnt, greedy):
    """Retreat cost: discard energy attached to active Pokemon."""
    energy_opts = [
        (i, torch.zeros(D_MODEL))
        for i, o in enumerate(opts)
        if o.type in (OptionType.ENERGY_CARD, OptionType.ENERGY)
    ]
    if not energy_opts:
        return [0], torch.tensor(0.0)
    if greedy:
        chosen = _stage2_pick_n(pooled, energy_opts, min_cnt, model)
        return chosen or [energy_opts[0][0]], torch.tensor(0.0)
    # Training: score and log prob
    vecs   = torch.stack([v for _, v in energy_opts])
    scores = model.stage2_scores(pooled, vecs)
    probs  = F.softmax(scores, dim=-1)
    chosen_local = int(torch.multinomial(probs, 1).item())
    return [energy_opts[chosen_local][0]], torch.log(probs[chosen_local] + 1e-9)


def _handle_switch(obs, our_idx, opts, words, pooled, model, effect, greedy):
    """
    SWITCH: Boss's Orders picks an opponent bench slot;
            Retreat picks a friendly bench slot.
    """
    opp_idx  = 1 - our_idx

    cand_vecs: list[tuple[int, torch.Tensor]] = []
    for i, o in enumerate(opts):
        if o.type != OptionType.CARD:
            continue
        if effect == Boss_Orders:
            # Opponent bench — use opponent bench word vectors (words[10-17])
            if o.area == AreaType.BENCH and o.playerIndex == opp_idx:
                slot = o.index or 0
                vec  = words[_OPP_BENCH_WORD + slot]  # opp bench: words 10-17
                cand_vecs.append((i, vec))
        else:
            # Retreat destination — our bench
            if o.area == AreaType.BENCH:
                slot = o.index or 0
                vec  = words[1 + slot]  # our bench: words 1-8
                cand_vecs.append((i, vec))

    if not cand_vecs:
        return [0], torch.tensor(0.0)

    if greedy:
        chosen = _stage2_pick_n(pooled, cand_vecs, 1, model)
        return chosen or [cand_vecs[0][0]], torch.tensor(0.0)

    vecs   = torch.stack([v for _, v in cand_vecs])
    scores = model.stage2_scores(pooled, vecs)
    probs  = F.softmax(scores, dim=-1)
    idx    = int(torch.multinomial(probs, 1).item())
    return [cand_vecs[idx][0]], torch.log(probs[idx] + 1e-9)


def _handle_to_active(obs, our_idx, opts, words, pooled, model, greedy):
    """TO_ACTIVE: promote a bench Pokemon after KO."""
    cand_vecs: list[tuple[int, torch.Tensor]] = []
    for i, o in enumerate(opts):
        if o.type == OptionType.CARD and o.area == AreaType.BENCH:
            slot = o.index or 0
            vec  = words[1 + slot]
            cand_vecs.append((i, vec))

    if not cand_vecs:
        return [0], torch.tensor(0.0)

    if greedy:
        chosen = _stage2_pick_n(pooled, cand_vecs, 1, model)
        return chosen or [cand_vecs[0][0]], torch.tensor(0.0)

    vecs   = torch.stack([v for _, v in cand_vecs])
    scores = model.stage2_scores(pooled, vecs)
    probs  = F.softmax(scores, dim=-1)
    idx    = int(torch.multinomial(probs, 1).item())
    return [cand_vecs[idx][0]], torch.log(probs[idx] + 1e-9)


# ── Unified entry point ────────────────────────────────────────────────────────

def select_action(
    obs:     Observation,
    our_idx: int,
    model:   CeruledgePolicy,
    tracker: GameStateTracker,
    greedy:  bool = True,
) -> tuple[list[int], torch.Tensor]:
    """
    Dispatch to the right handler based on obs.select.context.
    Returns (option_indices, log_prob).
    """
    ctx = obs.select.context
    match ctx:
        case SelectContext.MAIN:
            result = select_main_action(obs, our_idx, model, tracker, greedy)
            # Mark supporter used if we played one
            if result[0]:
                opt = obs.select.option[result[0][0]]
                if opt.type == OptionType.PLAY:
                    ps  = obs.current.players[our_idx]
                    h   = ps.hand or []
                    if opt.index is not None and opt.index < len(h):
                        if h[opt.index].id in (Boss_Orders, Explorers_Guidance, Carmine):
                            tracker.mark_supporter()
                elif opt.type == OptionType.ABILITY:
                    tracker.mark_lunar()
            return result

        case SelectContext.SETUP_ACTIVE_POKEMON | SelectContext.SETUP_BENCH_POKEMON:
            # Handled by the calling agent using simple heuristics
            return [], torch.tensor(0.0)

        case _:
            return select_sub_action(obs, our_idx, model, tracker, greedy)
