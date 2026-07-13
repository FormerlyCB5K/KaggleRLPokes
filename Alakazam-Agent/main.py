"""
Alakazam Rules-Based Agent — Pokémon TCG AI Battle Challenge

Priority-list agent following Alakazam-Agent/rules.md.
Two attackers:
  ZAM (Alakazam 743) — Powerful Hand: 20 × cards in hand
  TWM (Alakazam 245) — Psychic: 10 + 50 per opponent's energy (when STRANGE=ON)
"""

import os

from cg_download.api import (
    AreaType,
    Observation,
    OptionType,
    SelectContext,
    all_card_data,
    to_observation_class,
)

# ── Deck ──────────────────────────────────────────────────────────────────────

_deck_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Deck.csv")
if not os.path.exists(_deck_path):
    _deck_path = "/kaggle_simulations/agent/deck.csv"
with open(_deck_path) as _f:
    MY_DECK: list[int] = [int(l) for l in _f.read().splitlines() if l.strip()]

# ── Card metadata ─────────────────────────────────────────────────────────────

_all_cards = all_card_data()
card_table = {c.cardId: c for c in _all_cards}

# ── Card ID constants ─────────────────────────────────────────────────────────

# Energy
Basic_Psychic_Energy = 5    # ×2
Enriching_Energy     = 13   # ×1  — draw 4 on attach
Telepathic_Energy    = 19   # ×4  — bench 2 Basic {P} from deck on attach to {P} Pokémon

# Pokémon
Dudunsparce    = 66   # ×3  — Run Away Draw: draw 3, shuffle self back to deck
Fezandipiti_ex = 140  # ×1  — Flip the Script: draw 3 if KO'd last turn
Genesect       = 142  # ×1  — ACE Nullifier: prevents opp ACE SPEC if has Tool
TWM            = 245  # ×1  — Alakazam w/ Psychic + Strange Hacking
Dunsparce      = 305  # ×3  — 70 HP basic
Shaymin        = 343  # ×1  — Flower Curtain: prevent bench damage to non-rule-box
Abra           = 741  # ×4  — Teleportation Attack
Kadabra        = 742  # ×4  — Psychic Draw: draw 2 on evolve
ZAM            = 743  # ×3  — Powerful Hand: 20×hand; Psychic Draw: draw 3 on evolve

# Items
Rare_Candy      = 1079  # ×4
Buddy_Poffin    = 1086  # ×4
Night_Stretcher = 1097  # ×1
Sacred_Ash      = 1129  # ×1
Poke_Pad        = 1152  # ×4
Lucky_Helmet    = 1156  # ×2
Air_Balloon     = 1174  # ×1

# Supporters
Boss_Orders = 1182  # ×2
Lanas_Aid   = 1184  # ×1
Hilda       = 1225  # ×4
Dawn        = 1231  # ×4

# Stadium
Battle_Cage = 1264  # ×4
Watchtower  = 1256  # Team Rocket's Watchtower (opponent's)

# Psychic-type Pokémon in our deck — only attach Telepathic Energy to these
PSYCHIC_POKEMON_IDS = frozenset({Abra, Kadabra, ZAM, TWM, Fezandipiti_ex})

TOOL_IDS = frozenset({Lucky_Helmet, Air_Balloon})

# ── Trigger card ID sets (opponent cards) ─────────────────────────────────────

# BARRIER ON: bench Shaymin for bench protection
BARRIER_TRIGGERS = frozenset({
    1030,  # Staryu
    360,   # Misty's Staryu
    108,   # Wellspring Mask Ogerpon ex
    163,   # Slowking
    257,   # N's Darumaka
    171,   # Raging Bolt (non-ex)
})

# STRANGE ON: switch to TWM attacker
STRANGE_TRIGGERS = frozenset({
    344,   # Dwebble
    532,   # Dwebble (alt set)
    11,    # Mist Energy
    414,   # Team Rocket's Articuno
})

# CAGE ON: play Battle Cage immediately
CAGE_TRIGGERS = frozenset({
    112,   # Munkidori
    119,   # Dreepy
    104,   # Froslass (non-ex)
    131,   # Duskull
})

# ── Persistent game state ─────────────────────────────────────────────────────

_STRANGE: bool = False
_CAGE:    bool = False
_BARRIER: bool = False
_OPP_ACE_USED:      bool = False
_OPP_KO_LAST_TURN:  bool = False
_last_opp_prizes:   int | None = None  # opponent's prize count as of our last turn
_last_turn_seen:    int | None = None  # state.turn when we last updated KO status

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

def _hand(ps) -> list:
    return ps.hand if ps.hand else []

def _discard(ps) -> list:
    return ps.discard if ps.discard else []

def _count_hand(ps, *card_ids) -> int:
    return sum(1 for c in _hand(ps) if c.id in card_ids)

def _count_board(ps, *pokemon_ids) -> int:
    return sum(1 for p in _all_in_play(ps) if p.id in pokemon_ids)

def _count_bench(ps, *pokemon_ids) -> int:
    return sum(1 for p in _bench(ps) if p.id in pokemon_ids)

def _count_discard(ps, *card_ids) -> int:
    return sum(1 for c in _discard(ps) if c.id in card_ids)

def _in_hand(ps, *card_ids) -> bool:
    return any(c.id in card_ids for c in _hand(ps))

def _on_board(ps, *pokemon_ids) -> bool:
    return any(p.id in pokemon_ids for p in _all_in_play(ps))

def _in_discard(ps, *card_ids) -> bool:
    return any(c.id in card_ids for c in _discard(ps))

def _on_bench(ps, *pokemon_ids) -> bool:
    return any(p.id in pokemon_ids for p in _bench(ps))

def _has_energy(pokemon) -> bool:
    return bool(getattr(pokemon, 'energyCards', None))

def _has_psychic_energy(pokemon) -> bool:
    """True if pokemon has Basic Psychic Energy OR Telepathic Energy attached."""
    for c in getattr(pokemon, 'energyCards', []):
        if c.id in (Basic_Psychic_Energy, Telepathic_Energy):
            return True
    return False

def _has_tool(pokemon) -> bool:
    for attr in ('tool', 'toolCard'):
        val = getattr(pokemon, attr, None)
        if val is not None:
            return True
    for c in getattr(pokemon, 'energyCards', []):
        if c.id in TOOL_IDS:
            return True
    return False

def _tool_in_hand(ps) -> bool:
    return _in_hand(ps, Lucky_Helmet, Air_Balloon)

def _appeared_this_turn(pokemon) -> bool:
    return bool(getattr(pokemon, 'appearThisTurn', False))

def _board_not_placed_this_turn(ps, *pokemon_ids) -> list:
    """Return board Pokémon with given IDs that were NOT placed/evolved this turn."""
    return [p for p in _all_in_play(ps) if p.id in pokemon_ids and not _appeared_this_turn(p)]

def _bench_not_placed_this_turn(ps, *pokemon_ids) -> list:
    return [p for p in _bench(ps) if p.id in pokemon_ids and not _appeared_this_turn(p)]

def _prize_count(pokemon) -> int:
    data = card_table.get(getattr(pokemon, 'id', -1))
    if data is None:
        return 1
    return 3 if getattr(data, 'megaEx', False) else 2 if getattr(data, 'ex', False) else 1

def _is_first_turn(state, our_idx: int) -> bool:
    """True on our very first main-phase turn of the game."""
    return state.turn == our_idx + 1

def _get_target(obs: Observation, area, index, our_idx: int):
    """Resolve a board/hand area + index to the Card or Pokemon object."""
    ps = _ps(obs, our_idx)
    if area == AreaType.ACTIVE:
        active = ps.active
        if active and index is not None and index < len(active):
            return active[index]
    elif area == AreaType.BENCH:
        bench = ps.bench
        if bench and index is not None and index < len(bench):
            return bench[index]
    elif area == AreaType.HAND:
        h = _hand(ps)
        if index is not None and index < len(h):
            return h[index]
    elif area == AreaType.DISCARD:
        d = _discard(ps)
        if index is not None and index < len(d):
            return d[index]
    elif area == AreaType.DECK:
        deck = obs.select.deck
        if deck and index is not None and index < len(deck):
            return deck[index]
    elif area == AreaType.LOOKING:
        looking = obs.current.looking
        if looking and index is not None and index < len(looking):
            return looking[index]
    return None

# ── Global state updater ──────────────────────────────────────────────────────

def _update_state(obs: Observation, our_idx: int) -> None:
    global _STRANGE, _CAGE, _BARRIER, _OPP_ACE_USED, _OPP_KO_LAST_TURN
    global _last_opp_prizes, _last_turn_seen

    state   = obs.current
    opp_idx = 1 - our_idx
    opp_ps  = _ps(obs, opp_idx)

    # ── KO detection ──────────────────────────────────────────────────────────
    # When the opponent KOs one of our Pokémon, they take one of our prize cards,
    # which means their prize count DECREASES. We detect this by comparing their
    # current prize count with the last value we saw at the start of OUR turn.
    cur_opp_prizes = len(opp_ps.prize)
    cur_turn = state.turn
    if _last_turn_seen != cur_turn:
        # New turn has started — check if opponent took prizes since last time
        if _last_opp_prizes is not None:
            _OPP_KO_LAST_TURN = (cur_opp_prizes < _last_opp_prizes)
        else:
            _OPP_KO_LAST_TURN = False
        _last_opp_prizes = cur_opp_prizes
        _last_turn_seen = cur_turn

    # ── Opponent board scan (in-play only — discard excluded) ────────────────
    # Reset each call so flags reflect the CURRENT board, not history.
    # A trigger card that was KO'd and is now in discard should not keep the flag set.
    _BARRIER = False
    _STRANGE = False
    _CAGE    = False

    opp_in_play: list[int] = []
    if opp_ps.active:
        for p in opp_ps.active:
            if p:
                opp_in_play.append(p.id)
                for ec in getattr(p, 'energyCards', []):
                    opp_in_play.append(ec.id)
    for p in _bench(opp_ps):
        opp_in_play.append(p.id)
        for ec in getattr(p, 'energyCards', []):
            opp_in_play.append(ec.id)
    stadium = obs.current.stadium
    if stadium:
        for s in stadium:
            if s:
                opp_in_play.append(s.id)

    for cid in opp_in_play:
        if cid in BARRIER_TRIGGERS:
            _BARRIER = True
        if cid in STRANGE_TRIGGERS:
            _STRANGE = True
        if cid in CAGE_TRIGGERS:
            _CAGE    = True

    # ── ACE SPEC detection ────────────────────────────────────────────────────
    for c in _discard(opp_ps):
        data = card_table.get(c.id)
        if data and getattr(data, 'aceSpec', False):
            _OPP_ACE_USED = True


# ── Option finders ────────────────────────────────────────────────────────────

def _find_play(obs: Observation, card_id: int, our_idx: int) -> int | None:
    """Index of PLAY option for a specific card ID in hand."""
    ps = _ps(obs, our_idx)
    h  = _hand(ps)
    for i, o in enumerate(obs.select.option):
        if o.type == OptionType.PLAY and o.index is not None and o.index < len(h):
            if h[o.index].id == card_id:
                return i
    return None

def _find_evolve(obs: Observation, evo_id: int, target_id: int, our_idx: int,
                 area: AreaType | None = None) -> int | None:
    """Index of EVOLVE option: card evo_id evolving target_id in given area."""
    ps = _ps(obs, our_idx)
    h  = _hand(ps)
    for i, o in enumerate(obs.select.option):
        if o.type != OptionType.EVOLVE:
            continue
        if o.index is None or o.index >= len(h) or h[o.index].id != evo_id:
            continue
        if area is not None and o.inPlayArea != area:
            continue
        target = _get_target(obs, o.inPlayArea, o.inPlayIndex, our_idx)
        if target is not None and getattr(target, 'id', None) == target_id:
            return i
    return None

def _find_evolve_any_area(obs: Observation, evo_id: int, target_id: int, our_idx: int,
                          prefer_energized: bool = False) -> int | None:
    """Find EVOLVE option for any location; optionally prefer energized targets."""
    ps = _ps(obs, our_idx)
    h  = _hand(ps)
    best = None
    for i, o in enumerate(obs.select.option):
        if o.type != OptionType.EVOLVE:
            continue
        if o.index is None or o.index >= len(h) or h[o.index].id != evo_id:
            continue
        target = _get_target(obs, o.inPlayArea, o.inPlayIndex, our_idx)
        if target is None or getattr(target, 'id', None) != target_id:
            continue
        if prefer_energized and _has_energy(target):
            return i
        if best is None:
            best = i
    return best

def _find_ability(obs: Observation, pokemon_id: int, our_idx: int,
                  area: AreaType | None = None) -> int | None:
    """Index of ABILITY option for a given Pokémon ID."""
    ps = _ps(obs, our_idx)
    for i, o in enumerate(obs.select.option):
        if o.type != OptionType.ABILITY:
            continue
        if area is not None and o.area != area:
            continue
        target = _get_target(obs, o.area, o.index, our_idx)
        if target is not None and getattr(target, 'id', None) == pokemon_id:
            return i
    return None

def _find_attack(obs: Observation, prefer_name: str | None = None) -> int | None:
    """Index of first ATTACK option, or a specific attack by name (strict — returns None if not found)."""
    first = None
    for i, o in enumerate(obs.select.option):
        if o.type != OptionType.ATTACK:
            continue
        if prefer_name is None:
            return i
        name = getattr(o, 'name', '') or ''
        if prefer_name.lower() in name.lower():
            return i
        if first is None:
            first = i
    return None if prefer_name is not None else first

def _find_retreat(obs: Observation) -> int | None:
    for i, o in enumerate(obs.select.option):
        if o.type == OptionType.RETREAT:
            return i
    return None

def _find_end(obs: Observation) -> int | None:
    for i, o in enumerate(obs.select.option):
        if o.type == OptionType.END:
            return i
    return None

def _find_attach_to(obs: Observation, energy_id: int, target_poke_id: int,
                    our_idx: int, area: AreaType | None = None) -> int | None:
    """Find ATTACH option for energy → specific Pokémon ID. Optional area filter."""
    ps = _ps(obs, our_idx)
    h  = _hand(ps)
    for i, o in enumerate(obs.select.option):
        if o.type != OptionType.ATTACH:
            continue
        if o.index is None or o.index >= len(h) or h[o.index].id != energy_id:
            continue
        if area is not None and o.inPlayArea != area:
            continue
        target = _get_target(obs, o.inPlayArea, o.inPlayIndex, our_idx)
        if target is not None and getattr(target, 'id', None) == target_poke_id:
            return i
    return None

def _find_attach_no_psychic(obs: Observation, energy_id: int, target_poke_id: int,
                            our_idx: int, area: AreaType | None = None) -> int | None:
    """Like _find_attach_to but skips targets that already have Basic Psychic or Telepathic Energy."""
    ps = _ps(obs, our_idx)
    h  = _hand(ps)
    for i, o in enumerate(obs.select.option):
        if o.type != OptionType.ATTACH:
            continue
        if o.index is None or o.index >= len(h) or h[o.index].id != energy_id:
            continue
        if area is not None and o.inPlayArea != area:
            continue
        target = _get_target(obs, o.inPlayArea, o.inPlayIndex, our_idx)
        if target is None or getattr(target, 'id', None) != target_poke_id:
            continue
        if _has_psychic_energy(target):
            continue
        return i
    return None

def _find_attach_any_target(obs: Observation, energy_id: int, our_idx: int,
                             target_poke_ids: tuple[int, ...]) -> int | None:
    """Find ATTACH option for energy; search target_poke_ids in priority order."""
    for poke_id in target_poke_ids:
        r = _find_attach_to(obs, energy_id, poke_id, our_idx)
        if r is not None:
            return r
    return None

def _find_attach_active(obs: Observation, energy_id: int, our_idx: int) -> int | None:
    """Attach energy to whatever is in the active spot."""
    ps = _ps(obs, our_idx)
    h  = _hand(ps)
    for i, o in enumerate(obs.select.option):
        if o.type != OptionType.ATTACH:
            continue
        if o.index is None or o.index >= len(h) or h[o.index].id != energy_id:
            continue
        if o.inPlayArea == AreaType.ACTIVE:
            return i
    return None

def _find_attach_tool_to(obs: Observation, tool_id: int, target_poke_id: int,
                          our_idx: int) -> int | None:
    return _find_attach_to(obs, tool_id, target_poke_id, our_idx)

# ── Card-from-option resolver (used in sub-selection contexts) ────────────────

def _card_of_opt(obs: Observation, o, our_idx: int):
    ps = _ps(obs, our_idx)
    if o.area == AreaType.HAND:
        h = _hand(ps)
        if o.index is not None and o.index < len(h):
            return h[o.index]
    elif o.area == AreaType.DISCARD:
        player = obs.current.players[o.playerIndex] if o.playerIndex is not None else ps
        d = player.discard or []
        if o.index is not None and o.index < len(d):
            return d[o.index]
    elif o.area == AreaType.DECK:
        deck = obs.select.deck
        if deck and o.index is not None and o.index < len(deck):
            return deck[o.index]
    elif o.area == AreaType.LOOKING:
        looking = obs.current.looking
        if looking and o.index is not None and o.index < len(looking):
            return looking[o.index]
    elif o.area == AreaType.BENCH:
        player = obs.current.players[o.playerIndex] if o.playerIndex is not None else ps
        if player.bench and o.index is not None and o.index < len(player.bench):
            return player.bench[o.index]
    elif o.area == AreaType.ACTIVE:
        player = obs.current.players[o.playerIndex] if o.playerIndex is not None else ps
        if player.active and o.index is not None and o.index < len(player.active):
            return player.active[o.index]
    return None

def _indexed_cards(obs: Observation, opts, our_idx: int,
                   opt_type=OptionType.CARD) -> list[tuple[int, object]]:
    result = []
    for i, o in enumerate(opts):
        if o.type == opt_type:
            c = _card_of_opt(obs, o, our_idx)
            if c is not None:
                result.append((i, c))
    return result

def _pick_id(pairs: list, *card_ids: int) -> list[int] | None:
    for cid in card_ids:
        for i, c in pairs:
            if getattr(c, 'id', None) == cid:
                return [i]
    return None

# ── Setup phase ───────────────────────────────────────────────────────────────

def _setup_active(obs: Observation, our_idx: int) -> list[int]:
    """Choose starting active: Dunsparce > Abra > Genesect > Shaymin > Fezandipiti ex."""
    pairs = _indexed_cards(obs, obs.select.option, our_idx)
    for pid in (Dunsparce, Abra, Genesect, Shaymin, Fezandipiti_ex):
        r = _pick_id(pairs, pid)
        if r:
            return r
    return [0]

def _setup_bench(obs: Observation, our_idx: int) -> list[int]:
    """Setup bench: pick anything useful if asked."""
    if not obs.select.option:
        return []
    pairs = _indexed_cards(obs, obs.select.option, our_idx)
    for pid in (Dunsparce, Abra, Genesect, Shaymin, Fezandipiti_ex, Kadabra, Dudunsparce):
        r = _pick_id(pairs, pid)
        if r:
            return r
    if obs.select.minCount == 0:
        return []
    return [0]

# ── Promote priority ──────────────────────────────────────────────────────────

def _promote(obs: Observation, our_idx: int) -> list[int]:
    """
    After KO or Teleportation Attack: pick bench Pokémon to promote.
    Priority: ZAM w/energy > ZAM > Kadabra w/energy (not evolved this turn) >
              Kadabra (not evolved this turn) > Abra w/energy > Abra >
              Dunsparce > Shaymin > Genesect > any
    """
    opts  = obs.select.option
    pairs = _indexed_cards(obs, opts, our_idx)

    checks = [
        lambda c: c.id == ZAM and _has_energy(c),
        lambda c: c.id == ZAM,
        lambda c: c.id == Kadabra and _has_energy(c) and not _appeared_this_turn(c),
        lambda c: c.id == Kadabra and not _appeared_this_turn(c),
        lambda c: c.id == Abra and _has_energy(c),
        lambda c: c.id == Abra,
        lambda c: c.id == Dunsparce,
        lambda c: c.id == Shaymin,
        lambda c: c.id == Genesect,
    ]
    for check in checks:
        for i, c in pairs:
            if hasattr(c, 'id') and check(c):
                return [i]
    return [pairs[0][0]] if pairs else [0]

# ── First-turn main action ────────────────────────────────────────────────────

def _first_turn_action(obs: Observation, our_idx: int) -> list[int]:
    """
    Priority list for Turn 1.
    Returns the chosen action or falls back to END.
    """
    ps    = _ps(obs, our_idx)
    state = obs.current
    hand  = _hand(ps)
    bench = _bench(ps)
    act   = _active(ps)
    HAND  = len(hand)
    DECK  = ps.deckCount
    low   = DECK <= 5

    went_first = (state.turn == 1)

    abra_board   = [p for p in _all_in_play(ps) if p.id == Abra]
    duns_board   = [p for p in _all_in_play(ps) if p.id == Dunsparce]
    abra_bench   = [p for p in bench if p.id == Abra]

    # ── Telepathic Energy attachment ─────────────────────────────────────────
    if abra_board and _in_hand(ps, Telepathic_Energy) and not state.energyAttached:
        # Priority: active Abra if went first, then benched Abra, then any Abra
        if went_first and act and act.id == Abra and not _has_psychic_energy(act):
            r = _find_attach_to(obs, Telepathic_Energy, Abra, our_idx, AreaType.ACTIVE)
            if r is not None:
                return [r]
        r = _find_attach_no_psychic(obs, Telepathic_Energy, Abra, our_idx, AreaType.BENCH)
        if r is not None:
            return [r]
        r = _find_attach_no_psychic(obs, Telepathic_Energy, Abra, our_idx)
        if r is not None:
            return [r]

    # ── Bench Abra (if ≤2 total Dunsparce-family on board) ──────────────────
    if _in_hand(ps, Abra) and _count_board(ps, Dunsparce, Dudunsparce) <= 2:
        r = _find_play(obs, Abra, our_idx)
        if r is not None:
            return [r]

    # ── Bench Dunsparce (if ≤1 total Dunsparce-family on board) ─────────────
    if _in_hand(ps, Dunsparce) and _count_board(ps, Dunsparce, Dudunsparce) <= 1:
        r = _find_play(obs, Dunsparce, our_idx)
        if r is not None:
            return [r]

    # ── Bench Shaymin (only if BARRIER) ─────────────────────────────────────
    if _BARRIER and _in_hand(ps, Shaymin):
        r = _find_play(obs, Shaymin, our_idx)
        if r is not None:
            return [r]

    # ── Bench Genesect (if not OPP_ACE_USED, has tool in hand) ──────────────
    if _in_hand(ps, Genesect) and not _OPP_ACE_USED and _tool_in_hand(ps):
        r = _find_play(obs, Genesect, our_idx)
        if r is not None:
            return [r]

    # ── Buddy-Buddy Poffin ───────────────────────────────────────────────────
    r = _find_play(obs, Buddy_Poffin, our_idx)
    if r is not None:
        return [r]

    # ── Poké Pad (early — only if no Abra in play) ───────────────────────────
    if not abra_board and _in_hand(ps, Poke_Pad) and not low:
        r = _find_play(obs, Poke_Pad, our_idx)
        if r is not None:
            return [r]

    # ── Dawn (early — only if no Abra in play) ───────────────────────────────
    if not abra_board and _in_hand(ps, Dawn) and not low:
        r = _find_play(obs, Dawn, our_idx)
        if r is not None:
            return [r]

    # ── Hilda ────────────────────────────────────────────────────────────────
    if _in_hand(ps, Hilda) and not low:
        r = _find_play(obs, Hilda, our_idx)
        if r is not None:
            return [r]

    # ── Enriching Energy attachment ──────────────────────────────────────────
    # Priority: bench Dunsparce > active Dunsparce > Genesect > Shaymin > Abra > any
    if _in_hand(ps, Enriching_Energy) and not state.energyAttached and not low:
        r = _find_attach_to(obs, Enriching_Energy, Dunsparce, our_idx, AreaType.BENCH)
        if r is not None:
            return [r]
        r = _find_attach_to(obs, Enriching_Energy, Dunsparce, our_idx, AreaType.ACTIVE)
        if r is not None:
            return [r]
        for pid in (Genesect, Shaymin, Abra):
            r = _find_attach_to(obs, Enriching_Energy, pid, our_idx)
            if r is not None:
                return [r]
        # Any Pokémon
        h = _hand(ps)
        for i, o in enumerate(obs.select.option):
            if o.type == OptionType.ATTACH and o.index is not None and o.index < len(h):
                if h[o.index].id == Enriching_Energy:
                    return [i]

    # ── Dawn (second opportunity — broader) ─────────────────────────────────
    if _in_hand(ps, Dawn) and not low:
        r = _find_play(obs, Dawn, our_idx)
        if r is not None:
            return [r]

    # ── Poké Pad (main, broader conditions) ─────────────────────────────────
    if _in_hand(ps, Poke_Pad) and not low:
        # Use if: ≤1 Abra, or BARRIER+no Shaymin, or no Dunsparce, or no Kadabra in hand, or no Genesect+tool
        need_pad = (
            _count_board(ps, Abra) <= 1
            or (_BARRIER and not _on_board(ps, Shaymin))
            or not _on_board(ps, Dunsparce)
            or not _in_hand(ps, Kadabra)
            or (not _on_board(ps, Genesect) and _tool_in_hand(ps))
        )
        if need_pad:
            r = _find_play(obs, Poke_Pad, our_idx)
            if r is not None:
                return [r]

    # ── Basic Psychic Energy attach to Abra ─────────────────────────────────
    if _in_hand(ps, Basic_Psychic_Energy) and abra_board and not state.energyAttached:
        # Active Abra first
        if act and act.id == Abra and not _has_psychic_energy(act):
            r = _find_attach_to(obs, Basic_Psychic_Energy, Abra, our_idx, AreaType.ACTIVE)
            if r is not None:
                return [r]
        r = _find_attach_no_psychic(obs, Basic_Psychic_Energy, Abra, our_idx)
        if r is not None:
            return [r]

    # ── Tool on Genesect ────────────────────────────────────────────────────
    if _on_board(ps, Genesect) and _tool_in_hand(ps) and not _OPP_ACE_USED:
        g = next((p for p in _all_in_play(ps) if p.id == Genesect), None)
        if g and not _has_tool(g):
            for tid in (Air_Balloon, Lucky_Helmet):
                r = _find_attach_tool_to(obs, tid, Genesect, our_idx)
                if r is not None:
                    return [r]

    # ── Battle Cage (if CAGE) ────────────────────────────────────────────────
    if _CAGE and _in_hand(ps, Battle_Cage):
        r = _find_play(obs, Battle_Cage, our_idx)
        if r is not None:
            return [r]

    # ── Abra Teleportation Attack (if Abra is active and has energy) ─────────
    if act and act.id == Abra and _has_energy(act):
        r = _find_attack(obs)
        if r is not None:
            return [r]

    # ── End turn ─────────────────────────────────────────────────────────────
    r = _find_end(obs)
    return [r] if r is not None else [0]


# ── Main game action ──────────────────────────────────────────────────────────

def main_action(obs: Observation, our_idx: int) -> list[int]:
    ps    = _ps(obs, our_idx)
    state = obs.current
    hand  = _hand(ps)
    bench = _bench(ps)
    act   = _active(ps)
    HAND  = len(hand)
    DECK  = ps.deckCount
    low   = DECK <= 5

    opp_idx = 1 - our_idx
    opp_ps  = _ps(obs, opp_idx)
    opp_act = _active(opp_ps)
    opp_hp  = opp_act.hp if opp_act else 0

    # Computed damage values
    dud_bench_ct = _count_bench(ps, Dudunsparce)
    full_dmg     = HAND * 20 + 60 * dud_bench_ct   # potential before Boss/poffin
    boss_dmg     = full_dmg - 20                     # after playing Boss's Orders (-1 from hand)

    act_is_zam   = act and act.id in (ZAM, TWM)
    zam_active_energized = act_is_zam and _has_energy(act)

    # ── First turn? Delegate ─────────────────────────────────────────────────
    if _is_first_turn(state, our_idx):
        return _first_turn_action(obs, our_idx)

    # ── Battle Cage (CAGE or Watchtower in play) ─────────────────────────────
    stadium_ids = [s.id for s in (obs.current.stadium or []) if s]
    if _in_hand(ps, Battle_Cage) and (_CAGE or Watchtower in stadium_ids):
        r = _find_play(obs, Battle_Cage, our_idx)
        if r is not None:
            return [r]

    # ── Sacred Ash (≥3 Pokémon in discard) ──────────────────────────────────
    if _in_hand(ps, Sacred_Ash) and _count_discard(ps, ZAM, TWM, Kadabra, Abra, Dunsparce,
                                                     Dudunsparce, Shaymin, Genesect, Fezandipiti_ex) >= 3:
        r = _find_play(obs, Sacred_Ash, our_idx)
        if r is not None:
            return [r]

    # ── Buddy-Buddy Poffin ────────────────────────────────────────────────────
    r = _find_play(obs, Buddy_Poffin, our_idx)
    if r is not None:
        return [r]

    # ── Rare Candy: active Abra → ZAM/TWM (highest-priority evolution) ──────
    if (_in_hand(ps, Rare_Candy) and act and act.id == Abra
            and not _appeared_this_turn(act)):
        if not _STRANGE and _in_hand(ps, ZAM):
            # Try EVOLVE option first (simulator may present ZAM evolving Abra directly)
            r = _find_evolve(obs, ZAM, Abra, our_idx, AreaType.ACTIVE)
            if r is not None:
                return [r]
            # Fall back to playing Rare Candy as an item card
            r = _find_play(obs, Rare_Candy, our_idx)
            if r is not None:
                return [r]
        if _STRANGE and _in_hand(ps, TWM):
            r = _find_evolve(obs, TWM, Abra, our_idx, AreaType.ACTIVE)
            if r is not None:
                return [r]
            r = _find_play(obs, Rare_Candy, our_idx)
            if r is not None:
                return [r]

    # ── Fezandipiti Flip the Script ──────────────────────────────────────────
    if _on_board(ps, Fezandipiti_ex) and _OPP_KO_LAST_TURN and not low:
        r = _find_ability(obs, Fezandipiti_ex, our_idx)
        if r is not None:
            return [r]

    # ── Dudunsparce Run Away Draw (active) ──────────────────────────────────
    if act and act.id == Dudunsparce and bench and not low:
        r = _find_ability(obs, Dudunsparce, our_idx, area=AreaType.ACTIVE)
        if r is not None:
            return [r]

    # ── Evolve active Dunsparce → Dudunsparce ───────────────────────────────
    if act and act.id == Dunsparce and not _appeared_this_turn(act) and _in_hand(ps, Dudunsparce):
        r = _find_evolve(obs, Dudunsparce, Dunsparce, our_idx, AreaType.ACTIVE)
        if r is not None:
            return [r]

    # ── Evolve Dunsparce with Enriching Energy → Dudunsparce ────────────────
    if _in_hand(ps, Dudunsparce):
        for p in _all_in_play(ps):
            if p.id == Dunsparce and not _appeared_this_turn(p):
                # Check if this Dunsparce has Enriching Energy
                if any(ec.id == Enriching_Energy for ec in getattr(p, 'energyCards', [])):
                    area = AreaType.ACTIVE if (act and act.id == p.id and act is p) else AreaType.BENCH
                    r = _find_evolve(obs, Dudunsparce, Dunsparce, our_idx, area)
                    if r is not None:
                        return [r]

    # ── Evolve any Dunsparce → Dudunsparce ──────────────────────────────────
    if _in_hand(ps, Dudunsparce):
        r = _find_evolve_any_area(obs, Dudunsparce, Dunsparce, our_idx)
        if r is not None:
            return [r]

    # ── Bench Abra (if ≤2 Dunsparce-family) ─────────────────────────────────
    if _in_hand(ps, Abra) and _count_board(ps, Dunsparce, Dudunsparce) <= 2:
        r = _find_play(obs, Abra, our_idx)
        if r is not None:
            return [r]

    # ── Bench Dunsparce (if ≤1 Dunsparce-family) ────────────────────────────
    if _in_hand(ps, Dunsparce) and _count_board(ps, Dunsparce, Dudunsparce) <= 1:
        r = _find_play(obs, Dunsparce, our_idx)
        if r is not None:
            return [r]

    # ── Bench Shaymin (only if BARRIER) ─────────────────────────────────────
    if _BARRIER and _in_hand(ps, Shaymin):
        r = _find_play(obs, Shaymin, our_idx)
        if r is not None:
            return [r]

    # ── Bench Genesect (if not OPP_ACE_USED and has tool in hand) ────────────
    if _in_hand(ps, Genesect) and not _OPP_ACE_USED and _tool_in_hand(ps):
        r = _find_play(obs, Genesect, our_idx)
        if r is not None:
            return [r]

    # ── Evolve benched Abra → Kadabra (need ≥2 Abra on board) ───────────────
    if _count_board(ps, Abra) >= 2 and _in_hand(ps, Kadabra):
        r = _find_evolve(obs, Kadabra, Abra, our_idx, AreaType.BENCH)
        if r is not None:
            return [r]

    # ── Evolve active Kadabra → ZAM (STRANGE OFF) ────────────────────────────
    if (not _STRANGE and act and act.id == Kadabra
            and not _appeared_this_turn(act) and _in_hand(ps, ZAM)):
        r = _find_evolve(obs, ZAM, Kadabra, our_idx, AreaType.ACTIVE)
        if r is not None:
            return [r]

    # ── Evolve active Kadabra → TWM (STRANGE ON) ─────────────────────────────
    if (_STRANGE and act and act.id == Kadabra
            and not _appeared_this_turn(act) and _in_hand(ps, TWM)):
        r = _find_evolve(obs, TWM, Kadabra, our_idx, AreaType.ACTIVE)
        if r is not None:
            return [r]

    # ── Rare Candy: bench Abra → ZAM/TWM ────────────────────────────────────
    # (Active Abra case is handled earlier at higher priority.)
    if _in_hand(ps, Rare_Candy) and _board_not_placed_this_turn(ps, Abra):
        if not _STRANGE and _in_hand(ps, ZAM):
            # Prefer energized bench Abra first, then any bench Abra
            for i, o in enumerate(obs.select.option):
                if o.type != OptionType.EVOLVE:
                    continue
                h = _hand(ps)
                if o.index is None or o.index >= len(h) or h[o.index].id != ZAM:
                    continue
                if o.inPlayArea != AreaType.BENCH:
                    continue
                target = _get_target(obs, o.inPlayArea, o.inPlayIndex, our_idx)
                if target and target.id == Abra and _has_psychic_energy(target):
                    return [i]
            r = _find_evolve(obs, ZAM, Abra, our_idx, AreaType.BENCH)
            if r is not None:
                return [r]
            r = _find_play(obs, Rare_Candy, our_idx)
            if r is not None:
                return [r]
        if _STRANGE and _in_hand(ps, TWM):
            for i, o in enumerate(obs.select.option):
                if o.type != OptionType.EVOLVE:
                    continue
                h = _hand(ps)
                if o.index is None or o.index >= len(h) or h[o.index].id != TWM:
                    continue
                if o.inPlayArea != AreaType.BENCH:
                    continue
                target = _get_target(obs, o.inPlayArea, o.inPlayIndex, our_idx)
                if target and target.id == Abra and _has_psychic_energy(target):
                    return [i]
            r = _find_evolve(obs, TWM, Abra, our_idx, AreaType.BENCH)
            if r is not None:
                return [r]
            r = _find_play(obs, Rare_Candy, our_idx)
            if r is not None:
                return [r]

    # ── Attach energy to unenergized active ZAM/TWM (highest priority) ──────
    if act_is_zam and not _has_energy(act) and not state.energyAttached:
        for eid in (Telepathic_Energy, Basic_Psychic_Energy):
            if _in_hand(ps, eid):
                r = _find_attach_active(obs, eid, our_idx)
                if r is not None:
                    return [r]

    # ── Evolve benched Kadabra → ZAM (STRANGE OFF) ───────────────────────────
    if not _STRANGE and _in_hand(ps, ZAM):
        r = _find_evolve(obs, ZAM, Kadabra, our_idx, AreaType.BENCH)
        if r is not None:
            return [r]

    # ── Night Stretcher: Shaymin (BARRIER, in discard) ───────────────────────
    if _BARRIER and _in_hand(ps, Night_Stretcher) and _in_discard(ps, Shaymin):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── Poké Pad: Shaymin (BARRIER, not on board or in discard) ──────────────
    if (_BARRIER and not _on_board(ps, Shaymin) and not _in_discard(ps, Shaymin)
            and _in_hand(ps, Poke_Pad) and not low):
        r = _find_play(obs, Poke_Pad, our_idx)
        if r is not None:
            return [r]

    # ── Poké Pad: evolution setup (Abra/Dunsparce on board, not placed this turn) ─
    abra_evolvable   = _board_not_placed_this_turn(ps, Abra)
    duns_evolvable   = _board_not_placed_this_turn(ps, Dunsparce)
    kadabra_evolvable = _bench_not_placed_this_turn(ps, Kadabra)
    if _in_hand(ps, Poke_Pad) and not low and (abra_evolvable or duns_evolvable):
        r = _find_play(obs, Poke_Pad, our_idx)
        if r is not None:
            return [r]

    # ── Poké Pad: Kadabra not evolved this turn (has evolvable Kadabra) ───────
    if _in_hand(ps, Poke_Pad) and not low and kadabra_evolvable:
        r = _find_play(obs, Poke_Pad, our_idx)
        if r is not None:
            return [r]

    # ── Night Stretcher: Genesect (ACE Nullifier setup) ──────────────────────
    if (not _OPP_ACE_USED and _in_hand(ps, Night_Stretcher)
            and _tool_in_hand(ps) and _in_discard(ps, Genesect)):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── Night Stretcher: TWM (STRANGE ON, TWM in discard) ────────────────────
    if _STRANGE and _in_hand(ps, Night_Stretcher) and _in_discard(ps, TWM):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── Poké Pad: TWM (STRANGE ON, no TWM in play or hand) ───────────────────
    if (_STRANGE and not _on_board(ps, TWM) and not _in_hand(ps, TWM)
            and _in_hand(ps, Poke_Pad) and not low):
        r = _find_play(obs, Poke_Pad, our_idx)
        if r is not None:
            return [r]

    # ── Night Stretcher: ZAM (not in play or hand, ZAM in discard) ───────────
    if (not _on_board(ps, ZAM) and not _in_hand(ps, ZAM)
            and _in_hand(ps, Night_Stretcher) and _in_discard(ps, ZAM)):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── Lana's Aid: TWM (STRANGE ON, TWM in discard, not in play/hand) ───────
    if (_STRANGE and not _on_board(ps, TWM) and not _in_hand(ps, TWM)
            and _in_discard(ps, TWM) and _in_hand(ps, Lanas_Aid)):
        r = _find_play(obs, Lanas_Aid, our_idx)
        if r is not None:
            return [r]

    # ── Lana's Aid: ZAM (not in play or hand, ZAM in discard) ───────────────
    if (not _on_board(ps, ZAM) and not _in_hand(ps, ZAM)
            and _in_discard(ps, ZAM) and _in_hand(ps, Lanas_Aid)):
        r = _find_play(obs, Lanas_Aid, our_idx)
        if r is not None:
            return [r]

    # ── Night Stretcher: Basic Psychic Energy (active ZAM/TWM, no energy) ────
    if (act_is_zam and not _has_energy(act)
            and _in_hand(ps, Night_Stretcher) and _in_discard(ps, Basic_Psychic_Energy)):
        r = _find_play(obs, Night_Stretcher, our_idx)
        if r is not None:
            return [r]

    # ── Lana's Aid: Basic Psychic Energy (active ZAM/TWM, no energy) ─────────
    if (act_is_zam and not _has_energy(act)
            and _in_discard(ps, Basic_Psychic_Energy) and _in_hand(ps, Lanas_Aid)):
        r = _find_play(obs, Lanas_Aid, our_idx)
        if r is not None:
            return [r]

    # ── Attach energy + retreat to energized ZAM/TWM on bench ────────────────
    bench_energized_attacker = [p for p in bench if p.id in (ZAM, TWM) and _has_energy(p)]
    passive_active = act and act.id in (Genesect, Shaymin, Fezandipiti_ex)
    if bench_energized_attacker and passive_active:
        # First: attach any energy to active to enable retreat
        if not state.energyAttached:
            for eid in (Telepathic_Energy, Basic_Psychic_Energy, Enriching_Energy):
                r = _find_attach_active(obs, eid, our_idx)
                if r is not None:
                    return [r]
        # Then: retreat
        r = _find_retreat(obs)
        if r is not None:
            return [r]

    # ── Boss's Orders: condition A (active too bulky, bench KO-able) ─────────
    if (zam_active_energized and _in_hand(ps, Boss_Orders)
            and full_dmg < opp_hp and opp_act):
        # Check if any bench target is KO-able with boss_dmg
        bench_targets = [(p, p.hp) for p in _bench(opp_ps) if p and p.hp <= boss_dmg]
        if bench_targets:
            r = _find_play(obs, Boss_Orders, our_idx)
            if r is not None:
                return [r]

    # ── Boss's Orders: condition B (bench worth more prizes, KO-able) ────────
    if (zam_active_energized and _in_hand(ps, Boss_Orders) and opp_act):
        opp_act_prizes = _prize_count(opp_act)
        high_value_bench = [
            p for p in _bench(opp_ps)
            if p and _prize_count(p) > opp_act_prizes and p.hp <= boss_dmg
        ]
        if high_value_bench:
            r = _find_play(obs, Boss_Orders, our_idx)
            if r is not None:
                return [r]

    # ── Attach energy: active ZAM/TWM > bench ZAM/TWM > Kadabra > Abra ──────
    if not state.energyAttached:
        # 1. Active ZAM/TWM (needs psychic energy)
        if act_is_zam and not _has_psychic_energy(act):
            for eid in (Telepathic_Energy, Basic_Psychic_Energy):
                if _in_hand(ps, eid):
                    r = _find_attach_active(obs, eid, our_idx)
                    if r is not None:
                        return [r]
        # 2. Benched ZAM/TWM
        for eid in (Telepathic_Energy, Basic_Psychic_Energy):
            if _in_hand(ps, eid):
                for zmid in (ZAM, TWM):
                    r = _find_attach_no_psychic(obs, eid, zmid, our_idx, AreaType.BENCH)
                    if r is not None:
                        return [r]
        # 3. Benched Kadabra
        for eid in (Telepathic_Energy, Basic_Psychic_Energy):
            if _in_hand(ps, eid):
                r = _find_attach_no_psychic(obs, eid, Kadabra, our_idx, AreaType.BENCH)
                if r is not None:
                    return [r]
        # 4. Benched Abra (lowest priority)
        for eid in (Telepathic_Energy, Basic_Psychic_Energy):
            if _in_hand(ps, eid):
                r = _find_attach_no_psychic(obs, eid, Abra, our_idx, AreaType.BENCH)
                if r is not None:
                    return [r]

    # ── Enriching Energy: support Pokémon (active ZAM/TWM energized) ─────────
    if (zam_active_energized and _in_hand(ps, Enriching_Energy)
            and not state.energyAttached and not low):
        for pid in (Dudunsparce, Dunsparce, Shaymin, Genesect, Fezandipiti_ex):
            r = _find_attach_to(obs, Enriching_Energy, pid, our_idx)
            if r is not None:
                return [r]
        # Any Pokémon
        h = _hand(ps)
        for i, o in enumerate(obs.select.option):
            if o.type == OptionType.ATTACH and o.index is not None and o.index < len(h):
                if h[o.index].id == Enriching_Energy:
                    return [i]

    # ── Hilda (if not attached yet) ──────────────────────────────────────────
    if _in_hand(ps, Hilda) and not low and not state.energyAttached:
        r = _find_play(obs, Hilda, our_idx)
        if r is not None:
            return [r]

    # ── Dawn ─────────────────────────────────────────────────────────────────
    if _in_hand(ps, Dawn) and not low:
        r = _find_play(obs, Dawn, our_idx)
        if r is not None:
            return [r]

    # ── Hilda (unconditional second chance) ───────────────────────────────────
    if _in_hand(ps, Hilda) and not low:
        r = _find_play(obs, Hilda, our_idx)
        if r is not None:
            return [r]

    # ── Enriching Energy to benched Dudunsparce/Dunsparce ────────────────────
    if _in_hand(ps, Enriching_Energy) and not state.energyAttached and not low:
        for pid in (Dudunsparce, Dunsparce):
            r = _find_attach_to(obs, Enriching_Energy, pid, our_idx, AreaType.BENCH)
            if r is not None:
                return [r]

    # ── Tool on Genesect (only if HAND is high enough to attack after) ───────
    # Rule: only if (HAND*20 - 40) > opp active HP (meaning after -1 tool from hand,
    # we still have margin; -40 accounts for 2 "card slots" of safety)
    if (_on_board(ps, Genesect) and _tool_in_hand(ps) and not _OPP_ACE_USED
            and HAND * 20 - 40 > opp_hp):
        g = next((p for p in _all_in_play(ps) if p.id == Genesect), None)
        if g and not _has_tool(g):
            for tid in (Air_Balloon, Lucky_Helmet):
                r = _find_attach_tool_to(obs, tid, Genesect, our_idx)
                if r is not None:
                    return [r]

    # ── Bench Fezandipiti ex (draw prep for next loop or this loop) ───────────
    if (HAND * 20 < opp_hp and not _STRANGE
            and _OPP_KO_LAST_TURN and _in_hand(ps, Fezandipiti_ex)):
        r = _find_play(obs, Fezandipiti_ex, our_idx)
        if r is not None:
            return [r]

    # ── Dudunsparce Run Away Draw (bench — active ZAM unenergized) ───────────
    # Draw even if HAND is already large: active can't attack without energy.
    if act_is_zam and not _has_energy(act) and not _STRANGE and not low:
        for p in bench:
            if p.id == Dudunsparce:
                r = _find_ability(obs, Dudunsparce, our_idx, area=AreaType.BENCH)
                if r is not None:
                    return [r]

    # ── Dudunsparce Run Away Draw (bench — when HAND insufficient) ────────────
    if HAND * 20 < opp_hp and not _STRANGE and not low:
        # Prefer Dudunsparce with Enriching Energy
        for p in bench:
            if p.id == Dudunsparce:
                has_enrich = any(ec.id == Enriching_Energy for ec in getattr(p, 'energyCards', []))
                if has_enrich:
                    r = _find_ability(obs, Dudunsparce, our_idx, area=AreaType.BENCH)
                    if r is not None:
                        return [r]
        # Any benched Dudunsparce
        if _on_bench(ps, Dudunsparce):
            r = _find_ability(obs, Dudunsparce, our_idx, area=AreaType.BENCH)
            if r is not None:
                return [r]

    # ── Lucky Helmet attach (when HAND × 20 - 20 ≥ opp HP) ──────────────────
    if HAND * 20 - 20 >= opp_hp and _in_hand(ps, Lucky_Helmet) and act:
        # Attach to active (only if no tool already)
        if not _has_tool(act):
            r = _find_attach_active(obs, Lucky_Helmet, our_idx)
            if r is not None:
                return [r]

    # ── Attack with ZAM (Powerful Hand) ──────────────────────────────────────
    if act and act.id == ZAM and _has_energy(act):
        r = _find_attack(obs, 'Powerful Hand')
        if r is None:
            r = _find_attack(obs)
        if r is not None:
            return [r]

    # ── Attack with TWM (Psychic ONLY — never Strange Hacking) ───────────────
    if act and act.id == TWM and _has_energy(act):
        r = _find_attack(obs, 'Psychic')
        if r is not None:
            return [r]

    # ── End turn ─────────────────────────────────────────────────────────────
    r = _find_end(obs)
    return [r] if r is not None else [0]


# ── Sub-selection: TO_HAND ────────────────────────────────────────────────────

def _handle_to_hand(obs: Observation, our_idx: int) -> list[int]:
    ps        = _ps(obs, our_idx)
    opts      = obs.select.option
    effect_id = obs.select.effect.id if obs.select.effect else None
    pairs     = _indexed_cards(obs, opts, our_idx)
    min_count = obs.select.minCount
    max_count = obs.select.maxCount

    def pick(*ids):
        return _pick_id(pairs, *ids)

    # ── Night Stretcher ───────────────────────────────────────────────────────
    if effect_id == Night_Stretcher:
        return _ns_to_hand(obs, our_idx, ps, pairs)

    # ── Lana's Aid ────────────────────────────────────────────────────────────
    if effect_id == Lanas_Aid:
        return _lanas_to_hand(obs, our_idx, ps, pairs, max_count)

    # ── Rare Candy ────────────────────────────────────────────────────────────
    if effect_id == Rare_Candy:
        target_id = TWM if _STRANGE else ZAM
        for i, c in pairs:
            if getattr(c, 'id', None) == target_id:
                return [i]
        # Fallback: the other Alakazam
        fallback_id = ZAM if _STRANGE else TWM
        for i, c in pairs:
            if getattr(c, 'id', None) == fallback_id:
                return [i]
        return [pairs[0][0]] if pairs else [0]

    # ── Sacred Ash ────────────────────────────────────────────────────────────
    if effect_id == Sacred_Ash:
        return _sacred_ash_to_hand(obs, our_idx, ps, pairs, max_count)

    # ── Poké Pad ──────────────────────────────────────────────────────────────
    if effect_id == Poke_Pad:
        return _poke_pad_to_hand(obs, our_idx, ps, pairs)

    # ── Dawn ──────────────────────────────────────────────────────────────────
    if effect_id == Dawn:
        return _dawn_to_hand(obs, our_idx, ps, pairs, max_count)

    # ── Hilda ─────────────────────────────────────────────────────────────────
    if effect_id == Hilda:
        return _hilda_to_hand(obs, our_idx, ps, pairs, max_count)

    # ── Buddy-Buddy Poffin ────────────────────────────────────────────────────
    if effect_id == Buddy_Poffin:
        return _poffin_to_bench(obs, our_idx, ps, pairs, max_count)

    # ── Telepathic Energy bench search ────────────────────────────────────────
    if effect_id == Telepathic_Energy:
        # Bench up to 2 Basic {P} Pokémon; take max available
        result = []
        for i, c in pairs:
            if getattr(c, 'id', None) in PSYCHIC_POKEMON_IDS and len(result) < max_count:
                result.append(i)
        if len(result) < min_count and pairs:
            for i, _ in pairs:
                if i not in result:
                    result.append(i)
                    if len(result) >= min_count:
                        break
        return result or [0]

    # ── Enriching Energy draw trigger ─────────────────────────────────────────
    if effect_id == Enriching_Energy:
        # Draw 4 — just take up to max_count cards
        result = [i for i, _ in pairs[:max_count]]
        return result or (list(range(min(min_count, len(opts)))) or [0])

    # ── Generic fallback ──────────────────────────────────────────────────────
    count = max(min_count, 1)
    if pairs:
        return [p[0] for p in pairs[:count]]
    return list(range(min(count, len(opts)))) or [0]


def _ns_to_hand(obs: Observation, our_idx: int, ps, pairs) -> list[int]:
    """Night Stretcher: pick 1 card from discard (Pokémon or Basic Energy)."""
    act  = _active(ps)
    bench = _bench(ps)

    def pick(*ids):
        return _pick_id(pairs, *ids)

    act_is_zam = act and act.id in (ZAM, TWM)

    # Active ZAM/TWM has no energy → get Basic Psychic Energy first
    if act_is_zam and not _has_energy(act):
        r = pick(Basic_Psychic_Energy)
        if r: return r

    # BARRIER: get Shaymin
    if _BARRIER and not _on_board(ps, Shaymin):
        r = pick(Shaymin)
        if r: return r

    # STRANGE: get TWM
    if _STRANGE and not _on_board(ps, TWM) and not _in_hand(ps, TWM):
        r = pick(TWM)
        if r: return r

    # No ZAM in hand/play: get ZAM
    if not _on_board(ps, ZAM) and not _in_hand(ps, ZAM):
        r = pick(ZAM)
        if r: return r

    # Genesect for ACE Nullifier
    if not _OPP_ACE_USED and _tool_in_hand(ps) and not _on_board(ps, Genesect):
        r = pick(Genesect)
        if r: return r

    # Energy for attacker
    r = pick(Basic_Psychic_Energy)
    if r: return r

    # Any useful Pokémon
    for pid in (ZAM, TWM, Kadabra, Abra, Shaymin, Genesect, Dunsparce, Dudunsparce, Fezandipiti_ex):
        r = pick(pid)
        if r: return r

    return [pairs[0][0]] if pairs else [0]


def _lanas_to_hand(obs: Observation, our_idx: int, ps, pairs, max_count: int) -> list[int]:
    """Lana's Aid: retrieve up to 3 non-rule-box Pokémon and/or Basic Energies."""
    act = _active(ps)
    act_is_zam = act and act.id in (ZAM, TWM)
    selected = []

    def try_pick(*ids):
        for pid in ids:
            for i, c in pairs:
                if i not in selected and getattr(c, 'id', None) == pid:
                    selected.append(i)
                    return True
        return False

    # Active ZAM/TWM has no energy → get energy first
    if act_is_zam and not _has_energy(act):
        try_pick(Basic_Psychic_Energy)

    # TWM if STRANGE and not available
    if _STRANGE and not _on_board(ps, TWM) and not _in_hand(ps, TWM):
        try_pick(TWM)

    # ZAM if not available
    if not _on_board(ps, ZAM) and not _in_hand(ps, ZAM):
        try_pick(ZAM)

    # Fill remaining slots
    for pid in (Basic_Psychic_Energy, ZAM, Abra, Kadabra, Genesect, Shaymin, Dunsparce, Dudunsparce, Fezandipiti_ex):
        if len(selected) >= max_count:
            break
        try_pick(pid)

    # Fill any remaining with whatever is available
    for i, _ in pairs:
        if len(selected) >= max_count:
            break
        if i not in selected:
            selected.append(i)

    return selected[:max_count] if selected else ([pairs[0][0]] if pairs else [0])


def _sacred_ash_to_hand(obs: Observation, our_idx: int, ps, pairs, max_count: int) -> list[int]:
    """Sacred Ash: shuffle up to 5 Pokémon from discard into deck."""
    selected = []

    priority = []
    if _BARRIER:
        priority.append(Shaymin)
    if _STRANGE:
        priority.append(TWM)
    if not _OPP_ACE_USED:
        priority.append(Genesect)
    priority += [ZAM, Abra, Kadabra, Dunsparce, Dudunsparce, Fezandipiti_ex]

    for pid in priority:
        if len(selected) >= max_count:
            break
        for i, c in pairs:
            if i not in selected and getattr(c, 'id', None) == pid:
                selected.append(i)
                break

    # Fill remaining
    for i, _ in pairs:
        if len(selected) >= max_count:
            break
        if i not in selected:
            selected.append(i)

    return selected[:max_count] if selected else ([pairs[0][0]] if pairs else [0])


def _poke_pad_to_hand(obs: Observation, our_idx: int, ps, pairs) -> list[int]:
    """Poké Pad: pick 1 non-rule-box Pokémon from deck."""
    def pick(*ids):
        return _pick_id(pairs, *ids)

    # Turn 1: only fetch Kadabra (no ZAM or other evolutions)
    if _is_first_turn(obs.current, our_idx):
        r = pick(Kadabra)
        if r: return r
        return [pairs[0][0]] if pairs else [0]

    # Context-aware priority
    abra_evolvable   = _board_not_placed_this_turn(ps, Abra)
    duns_evolvable   = _board_not_placed_this_turn(ps, Dunsparce)
    kadabra_evolvable = _bench_not_placed_this_turn(ps, Kadabra)

    # BARRIER: Shaymin first
    if _BARRIER and not _on_board(ps, Shaymin) and not _in_discard(ps, Shaymin):
        r = pick(Shaymin)
        if r: return r

    # Genesect if has tool
    if _tool_in_hand(ps) and not _on_board(ps, Genesect):
        r = pick(Genesect)
        if r: return r

    # Rare Candy + not STRANGE → ZAM
    if _in_hand(ps, Rare_Candy) and not _STRANGE and abra_evolvable:
        r = pick(ZAM)
        if r: return r

    # Abra evolvable → Kadabra
    if abra_evolvable:
        r = pick(Kadabra)
        if r: return r

    # Dunsparce evolvable → Dudunsparce
    if duns_evolvable:
        r = pick(Dudunsparce)
        if r: return r

    # STRANGE → TWM
    if _STRANGE:
        r = pick(TWM)
        if r: return r

    # No Kadabra in hand → Kadabra
    if not _in_hand(ps, Kadabra):
        r = pick(Kadabra)
        if r: return r

    # General priority
    for pid in (ZAM, Kadabra, TWM, Dunsparce, Abra, Dudunsparce, Genesect, Shaymin, Fezandipiti_ex):
        r = pick(pid)
        if r: return r

    return [pairs[0][0]] if pairs else [0]


def _dawn_to_hand(obs: Observation, our_idx: int, ps, pairs, max_count: int) -> list[int]:
    """
    Dawn: search for 1 Basic + 1 Stage 1 + 1 Stage 2 Pokémon.
    Pairs may include cards of all 3 stages; pick the best of each.
    """
    # Categorize available cards
    basics   = [(i, c) for i, c in pairs if c.id in (Abra, Dunsparce, Shaymin, Genesect, Fezandipiti_ex)]
    stage1s  = [(i, c) for i, c in pairs if c.id in (Kadabra, Dudunsparce)]
    stage2s  = [(i, c) for i, c in pairs if c.id in (ZAM, TWM)]

    selected = []
    used_ids = set()

    def add_first(lst, cond_order):
        for check_id in cond_order:
            for i, c in lst:
                if i not in used_ids and c.id == check_id:
                    selected.append(i)
                    used_ids.add(i)
                    return True
        return False

    is_first = _is_first_turn(obs.current, our_idx)
    abra_evolvable = _board_not_placed_this_turn(ps, Abra)
    duns_evolvable = _board_not_placed_this_turn(ps, Dunsparce)

    # ── Basic ─────────────────────────────────────────────────────────────────
    if is_first:
        # First turn: only Abra (condition was no Abra in play)
        basic_order = [Abra, Dunsparce, Shaymin, Genesect, Fezandipiti_ex]
    else:
        basic_order = []
        if not _on_board(ps, Dunsparce):
            basic_order.append(Dunsparce)
        if _BARRIER:
            basic_order.append(Shaymin)
        if _count_board(ps, Abra) <= 1:
            basic_order.append(Abra)
        if _tool_in_hand(ps):
            basic_order.append(Genesect)
        basic_order += [Fezandipiti_ex, Dunsparce, Abra, Genesect, Shaymin]
    add_first(basics, basic_order)

    # ── Stage 1 ────────────────────────────────────────────────────────────────
    if is_first:
        s1_order = []
        if not _in_hand(ps, Kadabra):
            s1_order.append(Kadabra)
        if not _in_hand(ps, Dudunsparce):
            s1_order.append(Dudunsparce)
        s1_order += [Kadabra, Dudunsparce]
    else:
        s1_order = []
        if abra_evolvable:
            s1_order.append(Kadabra)
        if duns_evolvable:
            s1_order.append(Dudunsparce)
        s1_order += [Kadabra, Dudunsparce]
    add_first(stage1s, s1_order)

    # ── Stage 2 ────────────────────────────────────────────────────────────────
    s2_order = [TWM, ZAM] if _STRANGE else [ZAM, TWM]
    add_first(stage2s, s2_order)

    # Fill any unfilled slots (never fail)
    if len(selected) < max_count:
        for i, c in pairs:
            if i not in used_ids:
                selected.append(i)
                used_ids.add(i)
                if len(selected) >= max_count:
                    break

    return selected[:max_count] if selected else ([pairs[0][0]] if pairs else [0])


def _hilda_to_hand(obs: Observation, our_idx: int, ps, pairs, max_count: int) -> list[int]:
    """
    Hilda: search for 1 Evolution Pokémon + 1 Energy card.
    Never fail either slot.
    """
    energies  = [(i, c) for i, c in pairs if c.id in (Telepathic_Energy, Enriching_Energy, Basic_Psychic_Energy)]
    evolutions = [(i, c) for i, c in pairs if c.id in (ZAM, TWM, Kadabra, Dudunsparce)]

    selected = []
    used_ids = set()

    def add_first(lst, cond_order):
        for check_id in cond_order:
            for i, c in lst:
                if i not in used_ids and c.id == check_id:
                    selected.append(i)
                    used_ids.add(i)
                    return True
        return False

    state = obs.current
    act   = _active(ps)
    act_has_energy = act and _has_energy(act)
    abra_bench_ct  = _count_bench(ps, Abra)
    abra_evolvable = _board_not_placed_this_turn(ps, Abra)
    kad_evolvable  = _bench_not_placed_this_turn(ps, Kadabra)

    # ── Energy slot ───────────────────────────────────────────────────────────
    energy_order = []
    if not state.energyAttached and not act_has_energy:
        energy_order.append(Telepathic_Energy)
        energy_order.append(Basic_Psychic_Energy)
    if not state.energyAttached and act_has_energy:
        energy_order.append(Enriching_Energy)
    energy_order += [Enriching_Energy, Basic_Psychic_Energy, Telepathic_Energy]
    add_first(energies, energy_order)

    # ── Pokémon slot ──────────────────────────────────────────────────────────
    poke_order = []
    if abra_evolvable and _in_hand(ps, Rare_Candy):
        poke_order.append(ZAM)
    if kad_evolvable:
        poke_order.append(ZAM)
    if not _in_hand(ps, Kadabra):
        poke_order.append(Kadabra)
    if not _in_hand(ps, Dudunsparce):
        poke_order.append(Dudunsparce)
    if _STRANGE:
        poke_order.append(TWM)
    if not _in_hand(ps, ZAM):
        poke_order.append(ZAM)
    poke_order += [Kadabra, Dudunsparce, ZAM, TWM]
    add_first(evolutions, poke_order)

    # Fill remaining (never fail)
    for i, c in pairs:
        if len(selected) >= max_count:
            break
        if i not in used_ids:
            selected.append(i)
            used_ids.add(i)

    return selected[:max_count] if selected else ([pairs[0][0]] if pairs else [0])


def _poffin_to_bench(obs: Observation, our_idx: int, ps, pairs, max_count: int) -> list[int]:
    """
    Buddy-Buddy Poffin: bench up to 2 Basics with ≤70 HP.
    Priority each slot: Dunsparce (if none in play), Abra (if ≤1/≤2), then Dunsparce, Abra.
    """
    selected  = []
    used_idxs = set()

    def take(pid):
        for i, c in pairs:
            if i not in used_idxs and getattr(c, 'id', None) == pid:
                selected.append(i)
                used_idxs.add(i)
                return True
        return False

    for _slot in range(min(max_count, 2)):
        duns_ct = _count_board(ps, Dunsparce, Dudunsparce)
        abra_ct = _count_board(ps, Abra)
        taken   = False

        if duns_ct == 0:
            taken = take(Dunsparce)
        if not taken and abra_ct <= 1:
            taken = take(Abra)
        if not taken and abra_ct <= 2:
            taken = take(Abra)
        if not taken:
            taken = take(Dunsparce)
        if not taken:
            take(Abra)

    return selected if selected else ([pairs[0][0]] if pairs else [0])


# ── Sub-selection: SWITCH ─────────────────────────────────────────────────────

def _handle_switch(obs: Observation, our_idx: int) -> list[int]:
    """
    SWITCH context: Boss's Orders target selection OR retreat destination
    (Teleportation Attack / Trading Places / Abra's switch).
    """
    opp_idx   = 1 - our_idx
    ps        = _ps(obs, our_idx)
    effect_id = obs.select.effect.id if obs.select.effect else None
    opts      = obs.select.option

    if effect_id == Boss_Orders:
        # Pick opponent's benched Pokémon closest to boss_dmg without exceeding it
        HAND = len(_hand(ps))
        dud_bench_ct = _count_bench(ps, Dudunsparce)
        boss_dmg = HAND * 20 + 60 * dud_bench_ct - 20
        best_i, best_hp = None, -1
        for i, o in enumerate(opts):
            if o.type == OptionType.CARD and o.playerIndex == opp_idx:
                c = _card_of_opt(obs, o, our_idx)
                if c and hasattr(c, 'hp') and c.hp <= boss_dmg and c.hp > best_hp:
                    best_hp, best_i = c.hp, i
        return [best_i] if best_i is not None else [0]

    # Retreat / Teleportation Attack → promote per Promote Priority
    return _promote(obs, our_idx)


# ── Sub-selection: TO_ACTIVE ──────────────────────────────────────────────────

def _handle_to_active(obs: Observation, our_idx: int) -> list[int]:
    """Promote after KO."""
    return _promote(obs, our_idx)


# ── Sub-selection: ACTIVATE ───────────────────────────────────────────────────

def _handle_activate(obs: Observation, our_idx: int) -> list[int]:
    """
    YES/NO for optional abilities (Psychic Draw on Kadabra/ZAM, Flip the Script, Run Away Draw).
    Say YES unless deck ≤ 5 (low deck protection — skip draws to avoid decking out).
    """
    ps   = _ps(obs, our_idx)
    DECK = ps.deckCount

    if DECK <= 5:
        # Skip the draw: look for NO, then END, else pick option that is NOT YES
        yes_idx = None
        for i, o in enumerate(obs.select.option):
            if o.type == OptionType.YES:
                yes_idx = i
            elif o.type in (OptionType.END,):
                return [i]
            elif o.type not in (OptionType.YES,):
                return [i]
        # Only YES found — no way to skip; pick YES as last resort
        if yes_idx is not None:
            return [yes_idx]
        return [0]

    # Say YES to draw
    for i, o in enumerate(obs.select.option):
        if o.type == OptionType.YES:
            return [i]
    return [0]


# ── Greedy fallback ───────────────────────────────────────────────────────────

def _greedy(obs: Observation) -> list[int]:
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
    return desc[:count] if desc else [0]


# ── Agent entry point ─────────────────────────────────────────────────────────

def agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)

    if obs.select is None:
        return MY_DECK

    ctx     = obs.select.context
    our_idx = obs.current.yourIndex

    _update_state(obs, our_idx)

    match ctx:
        case SelectContext.MAIN:
            return main_action(obs, our_idx)
        case SelectContext.SETUP_ACTIVE_POKEMON:
            return _setup_active(obs, our_idx)
        case SelectContext.SETUP_BENCH_POKEMON:
            return _setup_bench(obs, our_idx)
        case SelectContext.TO_HAND:
            return _handle_to_hand(obs, our_idx)
        case SelectContext.SWITCH:
            return _handle_switch(obs, our_idx)
        case SelectContext.TO_ACTIVE:
            return _handle_to_active(obs, our_idx)
        case SelectContext.ACTIVATE:
            return _handle_activate(obs, our_idx)
        case _:
            return _greedy(obs)
