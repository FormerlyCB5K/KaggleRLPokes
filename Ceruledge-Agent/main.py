"""
Ceruledge Rules-Based Agent — Pokémon TCG AI Battle Challenge
Priority-list agent: scan rules 3.1–3.27 top-to-bottom, play first valid action.
"""

import os
import random

from cg_download.api import (
    AreaType,
    CardType,
    Observation,
    OptionType,
    SelectContext,
    all_card_data,
    to_observation_class,
)

# ── Deck ──────────────────────────────────────────────────────────────────────

_deck_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deck.csv")
if not os.path.exists(_deck_path):
    _deck_path = "/kaggle_simulations/agent/deck.csv"
with open(_deck_path) as _f:
    MY_DECK: list[int] = [int(l) for l in _f.read().splitlines() if l.strip()]

# ── Card metadata ─────────────────────────────────────────────────────────────

_all_cards = all_card_data()
card_table = {c.cardId: c for c in _all_cards}

# ── Card ID constants ─────────────────────────────────────────────────────────

Ceruledge_ex       = 320
Charcadet          = 796
Lunatone           = 675
Solrock            = 676
Drilbur            = 81

Fire_Energy        = 2
Fighting_Energy    = 6

Night_Stretcher    = 1097
Brilliant_Blender  = 1128
Fighting_Gong      = 1142
Ultra_Ball         = 1121
Poke_Pad           = 1152
Boss_Orders        = 1182
Explorers_Guidance = 1185
Carmine            = 1192

CERULEDGE_LINE = frozenset({Charcadet, Ceruledge_ex})
ENERGY_IDS     = frozenset({Fire_Energy, Fighting_Energy})

# ── State helpers ─────────────────────────────────────────────────────────────

def _ps(obs: Observation, idx: int):
    return obs.current.players[idx]

def _active(ps):
    return ps.active[0] if ps.active and ps.active[0] else None

def _bench(ps) -> list:
    return [p for p in ps.bench if p is not None]

def _all_in_play(ps) -> list:
    result = []
    a = _active(ps)
    if a:
        result.append(a)
    result.extend(_bench(ps))
    return result

def _has_fire(poke) -> bool:
    return any(c.id == Fire_Energy for c in poke.energyCards)

def _has_fighting(poke) -> bool:
    return any(c.id == Fighting_Energy for c in poke.energyCards)

def _has_energy(poke) -> bool:
    return len(poke.energyCards) > 0

def _hand(ps) -> list:
    return ps.hand if ps.hand else []

def _count_hand(ps, card_id: int) -> int:
    return sum(1 for c in _hand(ps) if c.id == card_id)

def _count_play(ps, *ids) -> int:
    return sum(1 for p in _all_in_play(ps) if p.id in ids)

def _count_discard(ps, card_id: int) -> int:
    return sum(1 for c in ps.discard if c.id == card_id)

def _energy_in_discard(ps) -> int:
    return sum(1 for c in ps.discard
               if card_table.get(c.id) and
               card_table[c.id].cardType == CardType.BASIC_ENERGY)

def _damage_count(ps) -> int:
    return 30 + 20 * _energy_in_discard(ps)

def _fire_in_hand(ps) -> int:
    return sum(1 for c in _hand(ps) if c.id == Fire_Energy)

def _fighting_in_hand(ps) -> int:
    return sum(1 for c in _hand(ps) if c.id == Fighting_Energy)

def _energy_in_hand(ps) -> int:
    return sum(1 for c in _hand(ps) if c.id in ENERGY_IDS)

def _has_bench_room(ps) -> bool:
    return len(_bench(ps)) < ps.benchMax

def _lunar_available(obs: Observation) -> bool:
    """True if Lunatone Lunar Cycle ability option exists in current MAIN options."""
    ps = _ps(obs, obs.current.yourIndex)
    for o in obs.select.option:
        if o.type == OptionType.ABILITY and o.area == AreaType.BENCH:
            if o.index is not None and o.index < len(ps.bench):
                p = ps.bench[o.index]
                if p and p.id == Lunatone:
                    return True
    return False

# ── Option finders ────────────────────────────────────────────────────────────

def _find_play(obs: Observation, card_id: int, our_idx: int) -> int | None:
    """Index of PLAY option for a card in hand."""
    ps = _ps(obs, our_idx)
    h = _hand(ps)
    for i, o in enumerate(obs.select.option):
        if o.type == OptionType.PLAY and o.index is not None and o.index < len(h):
            if h[o.index].id == card_id:
                return i
    return None

def _find_opt(obs: Observation, opt_type: OptionType) -> int | None:
    for i, o in enumerate(obs.select.option):
        if o.type == opt_type:
            return i
    return None

def _card_of_opt(obs: Observation, o, our_idx: int):
    """Resolve a CARD/ENERGY_CARD option to its Card or Pokemon object."""
    ps = _ps(obs, our_idx)
    if o.area == AreaType.HAND:
        h = _hand(ps)
        if o.index is not None and o.index < len(h):
            return h[o.index]
    elif o.area == AreaType.DISCARD:
        target_ps = obs.current.players[o.playerIndex] if o.playerIndex is not None else ps
        if o.index is not None and o.index < len(target_ps.discard):
            return target_ps.discard[o.index]
    elif o.area == AreaType.DECK:
        deck = obs.select.deck
        if deck and o.index is not None and o.index < len(deck):
            return deck[o.index]
    elif o.area == AreaType.LOOKING:
        looking = obs.current.looking
        if looking and o.index is not None and o.index < len(looking):
            return looking[o.index]
    elif o.area == AreaType.BENCH:
        target_ps = obs.current.players[o.playerIndex] if o.playerIndex is not None else ps
        if o.index is not None and o.index < len(target_ps.bench):
            return target_ps.bench[o.index]
    elif o.area == AreaType.ACTIVE:
        target_ps = obs.current.players[o.playerIndex] if o.playerIndex is not None else ps
        if target_ps.active and o.index is not None and o.index < len(target_ps.active):
            return target_ps.active[o.index]
    return None

def _indexed_cards(obs, opts, our_idx, opt_type=OptionType.CARD):
    """List of (option_index, card) for CARD-type options."""
    result = []
    for i, o in enumerate(opts):
        if o.type == opt_type:
            c = _card_of_opt(obs, o, our_idx)
            if c is not None:
                result.append((i, c))
    return result

def _pick_id(pairs, card_id) -> list[int] | None:
    for i, c in pairs:
        if c.id == card_id:
            return [i]
    return None

# ── Setup ─────────────────────────────────────────────────────────────────────

def _setup_active(obs: Observation, our_idx: int) -> list[int]:
    pairs = _indexed_cards(obs, obs.select.option, our_idx)
    for pid in (Solrock, Charcadet, Lunatone, Drilbur):
        r = _pick_id(pairs, pid)
        if r:
            return r
    return [0]

def _setup_bench(obs: Observation, our_idx: int) -> list[int]:
    if obs.select.minCount == 0 and not obs.select.option:
        return []
    pairs = _indexed_cards(obs, obs.select.option, our_idx)
    for pid in (Charcadet, Lunatone, Solrock, Drilbur):
        r = _pick_id(pairs, pid)
        if r:
            return r
    if obs.select.minCount == 0:
        return []
    return [0]

# ── Main phase ─────────────────────────────────────────────────────────────────

def main_action(obs: Observation, our_idx: int) -> list[int]:
    ps      = _ps(obs, our_idx)
    state   = obs.current
    opts    = obs.select.option
    deck_ct = ps.deckCount

    act    = _active(ps)
    bench  = _bench(ps)
    in_play = _all_in_play(ps)

    cer_play    = [p for p in in_play if p.id == Ceruledge_ex]
    char_play   = [p for p in in_play if p.id == Charcadet]
    lun_play    = [p for p in in_play if p.id == Lunatone]
    sol_play    = [p for p in in_play if p.id == Solrock]
    dril_play   = [p for p in in_play if p.id == Drilbur]
    cer_line_ct = len(cer_play) + len(char_play)

    lun_bench = any(p.id == Lunatone for p in bench)
    sol_bench = any(p.id == Solrock  for p in bench)
    has_room  = _has_bench_room(ps)

    cer_bench_fire  = [p for p in bench if p.id == Ceruledge_ex and _has_fire(p)]
    sol_bench_fight = [p for p in bench if p.id == Solrock and _has_fighting(p)]

    # ── 3.1 Play Drilbur ──────────────────────────────────────────────────────
    if not dril_play and has_room:
        r = _find_play(obs, Drilbur, our_idx)
        if r is not None:
            return [r]

    # ── 3.2 Play Lunatone ─────────────────────────────────────────────────────
    if not lun_play and has_room:
        r = _find_play(obs, Lunatone, our_idx)
        if r is not None:
            return [r]

    # ── 3.3 Play Solrock ──────────────────────────────────────────────────────
    if len(sol_play) < 2 and has_room:
        r = _find_play(obs, Solrock, our_idx)
        if r is not None:
            return [r]

    # ── 3.4 Play Charcadet ────────────────────────────────────────────────────
    if cer_line_ct < 3 and has_room:
        r = _find_play(obs, Charcadet, our_idx)
        if r is not None:
            return [r]

    # ── 3.5 Evolve Charcadet → Ceruledge ex ──────────────────────────────────
    if _count_hand(ps, Ceruledge_ex) > 0:
        eligible = [p for p in char_play if not p.appearThisTurn]
        if eligible:
            h = _hand(ps)
            for i, o in enumerate(opts):
                if (o.type == OptionType.EVOLVE and o.index is not None
                        and o.index < len(h) and h[o.index].id == Ceruledge_ex):
                    return [i]

    # ── 3.6 Lunar Cycle ───────────────────────────────────────────────────────
    if lun_play and sol_play and _fighting_in_hand(ps) > 0 and deck_ct > 5:
        for i, o in enumerate(opts):
            if o.type == OptionType.ABILITY and o.area == AreaType.BENCH:
                if o.index is not None and o.index < len(ps.bench):
                    p = ps.bench[o.index]
                    if p and p.id == Lunatone:
                        return [i]

    # ── 3.7 Brilliant Blender ─────────────────────────────────────────────────
    r = _find_play(obs, Brilliant_Blender, our_idx)
    if r is not None:
        return [r]

    # ── 3.8 Fighting Gong ─────────────────────────────────────────────────────
    r = _find_play(obs, Fighting_Gong, our_idx)
    if r is not None:
        return [r]

    # ── 3.9 Poké Pad ──────────────────────────────────────────────────────────
    r = _find_play(obs, Poke_Pad, our_idx)
    if r is not None:
        return [r]

    # ── 3.10 Attach fighting to active Solrock ────────────────────────────────
    if (not state.energyAttached and act and act.id == Solrock
            and not _has_energy(act) and lun_bench
            and _fighting_in_hand(ps) > 0):
        h = _hand(ps)
        for i, o in enumerate(opts):
            if (o.type == OptionType.ATTACH and o.inPlayArea == AreaType.ACTIVE
                    and o.index is not None and o.index < len(h)
                    and h[o.index].id == Fighting_Energy):
                return [i]

    # ── 3.11 Attach fire to Ceruledge ex ─────────────────────────────────────
    cer_with_fire = [p for p in cer_play if _has_fire(p)]
    if (not state.energyAttached and not cer_with_fire
            and _fire_in_hand(ps) > 0 and cer_play):
        h = _hand(ps)
        act_is_cer = act and act.id == Ceruledge_ex
        # prefer active first
        for i, o in enumerate(opts):
            if (o.type == OptionType.ATTACH and o.inPlayArea == AreaType.ACTIVE
                    and act_is_cer and o.index is not None and o.index < len(h)
                    and h[o.index].id == Fire_Energy):
                return [i]
        # then bench
        for i, o in enumerate(opts):
            if (o.type == OptionType.ATTACH and o.inPlayArea == AreaType.BENCH
                    and o.index is not None and o.index < len(h)
                    and h[o.index].id == Fire_Energy
                    and o.inPlayIndex is not None
                    and o.inPlayIndex < len(ps.bench)
                    and ps.bench[o.inPlayIndex]
                    and ps.bench[o.inPlayIndex].id == Ceruledge_ex):
                return [i]

    # ── 3.12 Attach any energy to active (bench ready to go) ──────────────────
    bench_cer_fire = bool(cer_bench_fire)
    bench_sol_fight_luna = bool(sol_bench_fight) and lun_bench
    if (not state.energyAttached and (bench_cer_fire or bench_sol_fight_luna)
            and _energy_in_hand(ps) > 0 and act):
        h = _hand(ps)
        for i, o in enumerate(opts):
            if o.type == OptionType.ATTACH and o.inPlayArea == AreaType.ACTIVE:
                if o.index is not None and o.index < len(h):
                    card = h[o.index]
                    if act.id in CERULEDGE_LINE and card.id == Fighting_Energy:
                        continue
                    if act.id == Solrock and card.id == Fire_Energy:
                        continue
                    return [i]

    # ── 3.13 Night Stretcher — fire for active Ceruledge ─────────────────────
    if (not state.energyAttached and act and act.id == Ceruledge_ex
            and not _has_fire(act) and _count_discard(ps, Fire_Energy) > 0):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── 3.14 Ultra Ball ───────────────────────────────────────────────────────
    if _ultra_ball_playable(ps):
        r = _find_play(obs, Ultra_Ball, our_idx)
        if r is not None:
            return [r]

    # ── 3.15 Night Stretcher — fighting for Solrock ───────────────────────────
    if (not state.energyAttached and act and act.id == Solrock
            and not _has_fighting(act) and lun_bench
            and _count_discard(ps, Fighting_Energy) > 0):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── 3.16 Night Stretcher — recover Ceruledge ──────────────────────────────
    eligible_char = [p for p in char_play if not p.appearThisTurn]
    if (_count_hand(ps, Ceruledge_ex) == 0 and not cer_play
            and _count_discard(ps, Ceruledge_ex) > 0 and eligible_char):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── 3.17 Night Stretcher — recover Charcadet ─────────────────────────────
    if cer_line_ct <= 1 and _count_discard(ps, Charcadet) > 0:
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── 3.18 Night Stretcher — recover missing Solrock / Lunatone ────────────
    has_sol = bool(sol_play)
    has_lun = bool(lun_play)
    if has_sol != has_lun:
        missing = Lunatone if has_sol else Solrock
        if _count_discard(ps, missing) > 0:
            r = _find_play(obs, Night_Stretcher, our_idx)
            if r is not None:
                return [r]

    # ── 3.19 Night Stretcher — fighting for Lunar Cycle ──────────────────────
    if (sol_play and lun_play and _fighting_in_hand(ps) == 0
            and _count_discard(ps, Fighting_Energy) > 0
            and _lunar_available(obs)):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── 3.20 Retreat into Ceruledge ex ───────────────────────────────────────
    if cer_bench_fire and act and act.id != Ceruledge_ex:
        r = _find_opt(obs, OptionType.RETREAT)
        if r is not None:
            return [r]

    # ── 3.21 Retreat into Solrock ─────────────────────────────────────────────
    if sol_bench_fight and lun_bench and act and act.id != Solrock:
        r = _find_opt(obs, OptionType.RETREAT)
        if r is not None:
            return [r]

    # ── 3.22 Boss's Orders ────────────────────────────────────────────────────
    opp_idx = 1 - our_idx
    opp_ps  = _ps(obs, opp_idx)
    opp_act = _active(opp_ps)
    dmg     = _damage_count(ps)
    if (act and act.id == Ceruledge_ex and _has_fire(act)
            and _count_hand(ps, Boss_Orders) > 0
            and opp_act and opp_act.hp > dmg
            and any(p is not None and p.hp <= dmg for p in opp_ps.bench)):
        r = _find_play(obs, Boss_Orders, our_idx)
        if r is not None:
            return [r]

    # ── 3.23 Explorer's Guidance ──────────────────────────────────────────────
    if deck_ct > 8:
        r = _find_play(obs, Explorers_Guidance, our_idx)
        if r is not None:
            return [r]

    # ── 3.24 Carmine ──────────────────────────────────────────────────────────
    if deck_ct > 8:
        r = _find_play(obs, Carmine, our_idx)
        if r is not None:
            return [r]

    # ── 3.25 Late energy attach ───────────────────────────────────────────────
    if not state.energyAttached and _energy_in_hand(ps) > 0:
        r = _late_attach(obs, our_idx, ps, state, act, bench)
        if r is not None:
            return r

    # ── 3.26 Attack ───────────────────────────────────────────────────────────
    r = _find_opt(obs, OptionType.ATTACK)
    if r is not None:
        return [r]

    # ── 3.27 End turn ─────────────────────────────────────────────────────────
    r = _find_opt(obs, OptionType.END)
    if r is not None:
        return [r]

    return [0]


def _ultra_ball_playable(ps) -> bool:
    total_e = _energy_in_hand(ps)
    excess  = (max(0, total_e - 2)
               + max(0, _count_hand(ps, Carmine) - 1)
               + max(0, _count_hand(ps, Ultra_Ball) - 2)
               + (_count_hand(ps, Lunatone) if any(p.id == Lunatone for p in _bench(ps)) else 0))
    return excess >= 2


def _late_attach(obs, our_idx, ps, state, act, bench):
    h    = _hand(ps)
    opts = obs.select.option

    def try_attach(energy_id, area, bench_idx=None):
        for i, o in enumerate(opts):
            if o.type != OptionType.ATTACH:
                continue
            if o.index is None or o.index >= len(h):
                continue
            if h[o.index].id != energy_id:
                continue
            if o.inPlayArea != area:
                continue
            if bench_idx is not None and o.inPlayIndex != bench_idx:
                continue
            return [i]
        return None

    # A: first turn, Charcadet active
    if act and act.id == Charcadet and state.turn <= 2 and _fire_in_hand(ps) > 0:
        r = try_attach(Fire_Energy, AreaType.ACTIVE)
        if r:
            return r

    # B: benched Ceruledge with no energy
    if _fire_in_hand(ps) > 0:
        for j, p in enumerate(ps.bench):
            if p and p.id == Ceruledge_ex and not _has_energy(p):
                r = try_attach(Fire_Energy, AreaType.BENCH, j)
                if r:
                    return r

    # C: benched Charcadet with no energy
    if _fire_in_hand(ps) > 0:
        for j, p in enumerate(ps.bench):
            if p and p.id == Charcadet and not _has_energy(p):
                r = try_attach(Fire_Energy, AreaType.BENCH, j)
                if r:
                    return r

    # D: benched Solrock with no energy
    if _fighting_in_hand(ps) > 0:
        for j, p in enumerate(ps.bench):
            if p and p.id == Solrock and not _has_energy(p):
                r = try_attach(Fighting_Energy, AreaType.BENCH, j)
                if r:
                    return r

    return None

# ── Sub-selection handlers ────────────────────────────────────────────────────

def _handle_activate(obs: Observation, our_idx: int) -> list[int]:
    """Always YES for Drilbur Dig Dig Dig."""
    for i, o in enumerate(obs.select.option):
        if o.type == OptionType.YES:
            return [i]
    return [0]


def _handle_to_hand(obs: Observation, our_idx: int) -> list[int]:
    ps        = _ps(obs, our_idx)
    effect_id = obs.select.effect.id if obs.select.effect else None
    opts      = obs.select.option
    pairs     = _indexed_cards(obs, opts, our_idx)

    if effect_id == Night_Stretcher:
        return _ns_to_hand(obs, our_idx, ps, pairs)
    if effect_id == Ultra_Ball:
        return _ub_to_hand(obs, our_idx, ps, pairs)
    if effect_id == Fighting_Gong:
        return _gong_to_hand(ps, pairs)
    if effect_id == Poke_Pad:
        return _pad_to_hand(ps, pairs)
    if effect_id == Explorers_Guidance:
        return _eg_to_hand(obs, our_idx, ps, pairs)
    if effect_id == Charcadet:
        return _gather_strength_to_hand(ps, pairs)

    count = max(obs.select.minCount, 1)
    if pairs:
        return [p[0] for p in pairs[:count]]
    # Deck not visible (e.g. Lunar Cycle / Gather Strength): pick first N options
    return list(range(min(count, len(opts)))) or [0]


def _ns_to_hand(obs, our_idx, ps, pairs) -> list[int]:
    """Night Stretcher: pick right card from discard based on game state."""
    in_play = _all_in_play(ps)
    bench   = _bench(ps)
    act     = _active(ps)

    sol_ip  = any(p.id == Solrock      for p in in_play)
    lun_ip  = any(p.id == Lunatone     for p in in_play)
    cer_ip  = any(p.id == Ceruledge_ex for p in in_play)
    lun_b   = any(p.id == Lunatone     for p in bench)
    cer_line = sum(1 for p in in_play if p.id in CERULEDGE_LINE)
    eligible_char = [p for p in in_play if p.id == Charcadet and not p.appearThisTurn]

    def pick(cid):
        return _pick_id(pairs, cid)

    # 3.13: fire for active Ceruledge
    if act and act.id == Ceruledge_ex and not _has_fire(act):
        r = pick(Fire_Energy);
        if r: return r
    # 3.15: fighting for Solrock
    if act and act.id == Solrock and not _has_fighting(act) and lun_b:
        r = pick(Fighting_Energy)
        if r: return r
    # 3.16: recover Ceruledge
    if not cer_ip and eligible_char:
        r = pick(Ceruledge_ex)
        if r: return r
    # 3.17: recover Charcadet
    if cer_line <= 1:
        r = pick(Charcadet)
        if r: return r
    # 3.18: recover missing
    if sol_ip and not lun_ip:
        r = pick(Lunatone)
        if r: return r
    if lun_ip and not sol_ip:
        r = pick(Solrock)
        if r: return r
    # 3.19: fighting for Lunar Cycle
    if sol_ip and lun_ip and _fighting_in_hand(ps) == 0:
        r = pick(Fighting_Energy)
        if r: return r

    return [pairs[0][0]] if pairs else [0]


def _ub_to_hand(obs, our_idx, ps, pairs) -> list[int]:
    """Ultra Ball: which Pokémon to search."""
    in_play  = _all_in_play(ps)
    bench    = _bench(ps)
    cer_ip   = [p for p in in_play if p.id == Ceruledge_ex]
    char_ip  = [p for p in in_play if p.id == Charcadet]
    sol_ip   = any(p.id == Solrock  for p in in_play)
    lun_ip   = any(p.id == Lunatone for p in in_play)
    cer_line = len(cer_ip) + len(char_ip)
    eligible_char = [p for p in char_ip if not p.appearThisTurn]

    def pick(cid):
        return _pick_id(pairs, cid)

    checks = [
        (not sol_ip and lun_ip,              Solrock),
        (not lun_ip and sol_ip,              Lunatone),
        (not cer_ip and bool(eligible_char), Ceruledge_ex),
        (cer_line <= 1,                      Charcadet),
        (not sol_ip,                         Solrock),
        (not lun_ip,                         Lunatone),
        (True,                               Drilbur),
        (True,                               Ceruledge_ex),
        (True,                               Charcadet),
        (True,                               Solrock),
        (True,                               Lunatone),
    ]
    for cond, cid in checks:
        if cond:
            r = pick(cid)
            if r: return r

    return [random.choice(pairs)[0]] if pairs else [0]


def _gong_to_hand(ps, pairs) -> list[int]:
    """Fighting Gong target."""
    in_play      = _all_in_play(ps)
    sol_ip       = any(p.id == Solrock  for p in in_play)
    lun_ip       = any(p.id == Lunatone for p in in_play)
    fight_ip     = any(p.id in (Solrock, Lunatone, Drilbur) for p in in_play)
    fight_in_h   = _fighting_in_hand(ps)

    def pick(cid):
        return _pick_id(pairs, cid)

    if not fight_ip:
        r = pick(Solrock);
        if r: return r
    if sol_ip and not lun_ip:
        r = pick(Lunatone);
        if r: return r
    if sol_ip and lun_ip:
        if fight_in_h < 2:
            r = pick(Fighting_Energy)
            if r: return r
        else:
            r = pick(Drilbur)
            if r: return r
    r = pick(Fighting_Energy)
    if r: return r
    return [pairs[0][0]] if pairs else [0]


def _pad_to_hand(ps, pairs) -> list[int]:
    """Poké Pad target."""
    in_play  = _all_in_play(ps)
    sol_ip   = any(p.id == Solrock  for p in in_play)
    lun_ip   = any(p.id == Lunatone for p in in_play)
    cer_line = sum(1 for p in in_play if p.id in CERULEDGE_LINE)

    def pick(cid):
        return _pick_id(pairs, cid)

    checks = [
        (not sol_ip,   Solrock),
        (not lun_ip,   Lunatone),
        (cer_line < 2, Charcadet),
        (True,         Drilbur),
        (True,         Solrock),
        (True,         Charcadet),
    ]
    for cond, cid in checks:
        if cond:
            r = pick(cid)
            if r: return r
    return [pairs[0][0]] if pairs else [0]


def _gather_strength_to_hand(ps, pairs) -> list[int]:
    """Gather Strength: take 1 Fire + 1 Fighting if possible."""
    fire_opts  = [i for i, c in pairs if c.id == Fire_Energy]
    fight_opts = [i for i, c in pairs if c.id == Fighting_Energy]
    result = []
    if fire_opts:
        result.append(fire_opts[0])
    if fight_opts:
        result.append(fight_opts[0])
    if len(result) < 2 and pairs:
        for i, _ in pairs:
            if i not in result:
                result.append(i)
                if len(result) == 2:
                    break
    return result[:2] if result else [0]


def _eg_to_hand(obs, our_idx, ps, pairs) -> list[int]:
    """Explorer's Guidance: keep best 2 of 6 revealed cards."""
    state    = obs.current
    in_play  = _all_in_play(ps)
    bench    = _bench(ps)

    sol_ip   = any(p.id == Solrock      for p in in_play)
    lun_ip   = any(p.id == Lunatone     for p in in_play)
    cer_ip   = any(p.id == Ceruledge_ex for p in in_play)
    char_ip  = [p for p in in_play if p.id == Charcadet]
    cer_line = sum(1 for p in in_play if p.id in CERULEDGE_LINE)
    fight_h  = _fighting_in_hand(ps)
    fire_h   = _fire_in_hand(ps)
    hand_ids = [c.id for c in _hand(ps)]
    other_eg_or_carm = any(i in (Carmine, Explorers_Guidance) for i in hand_ids)
    one_sol_lun = sol_ip != lun_ip
    fire_on_poke = any(_has_fire(p) for p in in_play)
    ns_in_hand = Night_Stretcher in hand_ids

    def score(cid, first_sel):
        if cid == Brilliant_Blender:                      return 1
        if cid == Night_Stretcher:                        return 2
        if cid == Carmine and not other_eg_or_carm:      return 3
        if cid == Solrock and lun_ip and not sol_ip:      return 4
        if cid == Lunatone and sol_ip and not lun_ip:     return 5
        if cid == Poke_Pad and one_sol_lun:               return 6
        if cid == Fighting_Gong:
            need = one_sol_lun or (sol_ip and lun_ip and fight_h == 0)
            if need:                                       return 7
        if cid == Explorers_Guidance and not other_eg_or_carm: return 8
        if cid == Fighting_Energy:
            need = sol_ip and lun_ip and fight_h == 0
            first_setup = first_sel in (Lunatone, Solrock, Poke_Pad, Fighting_Gong)
            if need or first_setup:                        return 9
        if cid == Ceruledge_ex:
            if char_ip and not cer_ip and _count_hand(ps, Ceruledge_ex) == 0:
                return 10
        if cid == Charcadet and cer_line <= 1:            return 11
        if cid == Fire_Energy:
            no_ns = not ns_in_hand and first_sel != Night_Stretcher
            if not fire_on_poke and not state.energyAttached and fire_h == 0 and no_ns:
                return 12
        if cid == Drilbur:                                return 13
        if cid == Boss_Orders:                            return 14
        if cid == Poke_Pad:                               return 15
        if cid == Fighting_Gong:                          return 16
        if cid == Ultra_Ball:                             return 17
        if cid == Ceruledge_ex:                           return 18
        if cid == Explorers_Guidance:                     return 19
        if cid == Charcadet:                              return 20
        if cid == Lunatone:                               return 21
        if cid == Solrock:                                return 22
        if cid == Carmine:                                return 23
        if cid == Fire_Energy:                            return 24
        if cid == Fighting_Energy:                        return 25
        return 26

    selected = []
    sel_ids  = []
    remaining = list(pairs)

    want = min(2, obs.select.maxCount)
    for _ in range(want):
        if not remaining:
            break
        best_i, best_c = min(remaining, key=lambda x: score(x[1].id, sel_ids[0] if sel_ids else None))
        selected.append(best_i)
        sel_ids.append(best_c.id)
        remaining = [(i, c) for i, c in remaining if i != best_i]

    return selected if selected else [0]


def _handle_discard(obs: Observation, our_idx: int) -> list[int]:
    ps        = _ps(obs, our_idx)
    effect_id = obs.select.effect.id if obs.select.effect else None
    opts      = obs.select.option
    deck      = obs.select.deck

    if effect_id == Brilliant_Blender or (deck and effect_id not in (Drilbur, None)):
        return _bb_discard(obs, our_idx, opts, deck or [])
    if effect_id == Drilbur or (deck and effect_id is None):
        # Drilbur: discard as many Fighting Energy from deck as possible
        fight = [i for i, o in enumerate(opts)
                 if o.type == OptionType.CARD and _card_of_opt(obs, o, our_idx)
                 and _card_of_opt(obs, o, our_idx).id == Fighting_Energy]
        return fight[:obs.select.maxCount]
    if effect_id == Ultra_Ball:
        return _ub_discard(obs, our_idx, ps, opts)

    # Generic: pick minCount items
    count = obs.select.minCount or 1
    avail = [i for i, o in enumerate(opts)
             if o.type in (OptionType.CARD, OptionType.ENERGY_CARD, OptionType.ENERGY)]
    return avail[:count] if avail else [0]


def _bb_discard(obs, our_idx, opts, deck) -> list[int]:
    """Brilliant Blender: choose up to 5 deck cards to discard."""
    fire_in_deck  = sum(1 for c in deck if c.id == Fire_Energy)
    fight_in_deck = sum(1 for c in deck if c.id == Fighting_Energy)
    max_sel       = obs.select.maxCount

    fire_opts  = [i for i, o in enumerate(opts)
                  if o.type == OptionType.CARD and _card_of_opt(obs, o, our_idx)
                  and _card_of_opt(obs, o, our_idx).id == Fire_Energy]
    fight_opts = [i for i, o in enumerate(opts)
                  if o.type == OptionType.CARD and _card_of_opt(obs, o, our_idx)
                  and _card_of_opt(obs, o, our_idx).id == Fighting_Energy]
    other_opts = [i for i, o in enumerate(opts)
                  if o.type == OptionType.CARD and _card_of_opt(obs, o, our_idx)
                  and _card_of_opt(obs, o, our_idx).id not in (*ENERGY_IDS, Night_Stretcher)]

    sel = []

    # Step A: fire down to 3 in deck
    a = min(max(0, fire_in_deck - 3), len(fire_opts), max_sel)
    sel += fire_opts[:a]
    fire_opts = fire_opts[a:]

    # Step B: fill with fighting
    b = min(len(fight_opts), max_sel - len(sel))
    sel += fight_opts[:b]
    fight_opts = fight_opts[b:]

    # Step C: fire down to 1 in deck
    fire_after_a = fire_in_deck - a
    c = min(max(0, fire_after_a - 1), len(fire_opts), max_sel - len(sel))
    sel += fire_opts[:c]

    # Step D: if no energy remains in deck, one other card
    if len(sel) < max_sel and fire_in_deck - a - c == 0 and fight_in_deck - b == 0:
        if other_opts:
            sel.append(other_opts[0])

    return sel


def _ub_discard(obs, our_idx, ps, opts) -> list[int]:
    """Ultra Ball: discard 2 cards from hand."""
    h         = _hand(ps)
    fire_cnt  = _fire_in_hand(ps)
    fight_cnt = _fighting_in_hand(ps)
    carm_cnt  = _count_hand(ps, Carmine)
    ub_cnt    = _count_hand(ps, Ultra_Ball)
    lun_bench = any(p.id == Lunatone for p in _bench(ps))

    cands = []
    seen  = set()

    for i, o in enumerate(opts):
        if o.type != OptionType.CARD or o.area != AreaType.HAND:
            continue
        if o.index is None or o.index >= len(h):
            continue
        cid = h[o.index].id
        if cid == Fire_Energy and fire_cnt > 1:
            cands.append((i, 0)); fire_cnt -= 1
        elif cid == Fighting_Energy and fight_cnt > 1:
            cands.append((i, 0)); fight_cnt -= 1
        elif cid == Carmine and carm_cnt > 1:
            cands.append((i, 1)); carm_cnt -= 1
        elif cid == Ultra_Ball and ub_cnt > 1:
            cands.append((i, 2)); ub_cnt -= 1
        elif cid == Lunatone and lun_bench:
            cands.append((i, 3))

    cands.sort(key=lambda x: x[1])
    sel = [idx for idx, _ in cands[:2]]

    if len(sel) < 2:
        for i in range(len(opts)):
            if i not in sel:
                sel.append(i)
                if len(sel) == 2:
                    break

    return sel[:2]


def _handle_switch(obs: Observation, our_idx: int) -> list[int]:
    """SWITCH context: Boss's Orders target OR retreat target."""
    effect_id = obs.select.effect.id if obs.select.effect else None
    opp_idx   = 1 - our_idx
    ps        = _ps(obs, our_idx)
    opts      = obs.select.option

    if effect_id == Boss_Orders:
        dmg  = _damage_count(ps)
        best_i, best_hp = None, -1
        for i, o in enumerate(opts):
            if o.type == OptionType.CARD and o.playerIndex == opp_idx:
                c = _card_of_opt(obs, o, our_idx)
                if c and hasattr(c, 'hp') and c.hp <= dmg and c.hp > best_hp:
                    best_hp, best_i = c.hp, i
        return [best_i] if best_i is not None else [0]

    # Retreat: choose which bench Pokémon to bring in
    bench = _bench(ps)
    cer_bench_fire  = [p for p in bench if p.id == Ceruledge_ex and _has_fire(p)]
    sol_bench_fight = [p for p in bench if p.id == Solrock and _has_fighting(p)]
    lun_bench       = any(p.id == Lunatone for p in bench)

    priority_checks = [
        lambda c: c.id == Ceruledge_ex and _has_fire(c),
        lambda c: c.id == Solrock and _has_fighting(c) and lun_bench,
    ]
    pairs = _indexed_cards(obs, opts, our_idx)
    for check in priority_checks:
        for i, c in pairs:
            if hasattr(c, 'hp') and check(c):
                return [i]

    return _promote_after_ko(obs, our_idx, ps, opts)


def _handle_to_active(obs: Observation, our_idx: int) -> list[int]:
    """TO_ACTIVE context: promote after KO."""
    ps   = _ps(obs, our_idx)
    opts = obs.select.option
    return _promote_after_ko(obs, our_idx, ps, opts)


def _promote_after_ko(obs, our_idx, ps, opts) -> list[int]:
    bench   = _bench(ps)
    cer_h   = _count_hand(ps, Ceruledge_ex) > 0
    lun_b   = any(p.id == Lunatone for p in bench)
    pairs   = _indexed_cards(obs, opts, our_idx)

    checks = [
        lambda c: c.id == Ceruledge_ex and _has_fire(c),
        lambda c: c.id == Ceruledge_ex,
        lambda c: c.id == Charcadet and _has_fire(c) and cer_h,
        lambda c: c.id == Charcadet and cer_h,
        lambda c: c.id == Solrock and _has_fighting(c) and lun_b,
        lambda c: c.id == Charcadet and _has_energy(c),
        lambda c: c.id == Charcadet,
        lambda c: c.id == Solrock,
        lambda c: c.id == Drilbur,
        lambda c: c.id == Lunatone,
    ]
    for check in checks:
        for i, c in pairs:
            if hasattr(c, 'hp') and check(c):
                return [i]
    return [0]


def _handle_discard_energy(obs: Observation, our_idx: int) -> list[int]:
    """Pay retreat cost: discard whatever energy is available."""
    count = obs.select.minCount or 1
    avail = [i for i, o in enumerate(obs.select.option)
             if o.type in (OptionType.ENERGY_CARD, OptionType.ENERGY)]
    return avail[:count] if avail else [0]


# ── Greedy fallback ───────────────────────────────────────────────────────────

def _greedy(obs: Observation, our_idx: int) -> list[int]:
    opts   = obs.select.option
    scores = []
    for o in opts:
        if   o.type == OptionType.YES:    scores.append(1.0)
        elif o.type == OptionType.END:    scores.append(-50.0)
        elif o.type == OptionType.ATTACK: scores.append(500.0)
        elif o.type == OptionType.NUMBER: scores.append(float(o.number or 0))
        else:                             scores.append(0.0)
    desc  = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    count = max(obs.select.minCount, min(obs.select.maxCount, len(desc)))
    return desc[:count]


# ── Agent entry point ─────────────────────────────────────────────────────────

def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)

    if obs.select is None:
        return MY_DECK

    ctx     = obs.select.context
    our_idx = obs.current.yourIndex

    match ctx:
        case SelectContext.MAIN:
            return main_action(obs, our_idx)
        case SelectContext.SETUP_ACTIVE_POKEMON:
            return _setup_active(obs, our_idx)
        case SelectContext.SETUP_BENCH_POKEMON:
            return _setup_bench(obs, our_idx)
        case SelectContext.ACTIVATE:
            return _handle_activate(obs, our_idx)
        case SelectContext.TO_HAND:
            return _handle_to_hand(obs, our_idx)
        case SelectContext.DISCARD | SelectContext.DISCARD_CARD_OR_ATTACHED_CARD:
            return _handle_discard(obs, our_idx)
        case SelectContext.DISCARD_ENERGY_CARD:
            return _handle_discard_energy(obs, our_idx)
        case SelectContext.SWITCH:
            return _handle_switch(obs, our_idx)
        case SelectContext.TO_ACTIVE:
            return _handle_to_active(obs, our_idx)
        case _:
            return _greedy(obs, our_idx)
