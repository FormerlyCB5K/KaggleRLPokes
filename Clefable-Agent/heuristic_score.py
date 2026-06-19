"""
Heuristic position evaluator for the Clefable MCTS Agent.

Development file — iterate weights in weights.py, then paste the final
heuristic_score() function and helpers into main.py before submission.

Raw scores are divided by HEURISTIC_NORM then clamped to [-1.0, 1.0] so that
the MCTS UCB exploration constant remains meaningful.

Heuristics implemented (H3 removed; H16 lives in greedy_action):
  H1   Clefairy/Clefable count bonuses
  H2   Dunsparce in play
  H2b  Energy wasted on Dunsparce (penalty)
  H4   Mega Clefable ex in play
  H5   Dudunsparce in hand ready to evolve
  H6   Poke Pad in hand
  H7   Smoochum-active setup bonus
  H8   Smoochum-in-play early bonus
  H9   Energy distribution on attackers (tiered)
  H10  Active/benched Clefable + Hero's Cape
  H11  Attack damage potential (KO bonus, prize bonus)
  H12  Cannot-attack energy penalties/rewards
  H13  Prize differential
  H14  Combined damage progress toward 2-shot
  H15  Attacking with unused trainers in hand
  H17  Psychic Energy in hand
  H18  Opponent energy in play
  H19  Non-attacker active when opponent has 1 prize left
  H20  Damage on our Clefairy/Mega Clefable ex
  H21  Deck thinning penalty
  H22  Hand-size bonus
  P2   Recovery cards live
  P3   Opponent bench size
  P4   Prize lead + attack-ready momentum
  P5   Dunsparce + Dudunsparce both in play
"""

from math import floor

from weights import (
    HEURISTIC_NORM,
    W_ATTACKER_1, W_ATTACKER_2, W_ATTACKER_3,
    W_DUNSPARCE, W_DUNSPARCE_ENERGY,
    W_MEGA_CLEFABLE_EX,
    W_DUDUNSPARCE_HAND,
    W_POKE_PAD_HAND,
    W_SMOOCHUM_ACTIVE, W_SMOOCHUM_PLAY,
    W_E_A1_E1, W_E_A1_E2, W_E_A2_E1, W_E_A2_E2, W_E_EXCESS,
    W_ACTIVE_CLEFABLE_E0, W_ACTIVE_CLEFABLE_E1, W_ACTIVE_CLEFABLE_E2,
    W_ACTIVE_CLEFABLE_CAPE, W_ACTIVE_CLEFAIRY_CAPE, W_ACTIVE_NONA_CAPE,
    W_BENCH_CLEFABLE_CAPE, W_BENCH_CLEFAIRY_CAPE, W_BENCH_NONA_CAPE,
    W_ONE_ENERGY_AWAY, W_BENCH_ATTACKER_READY,
    W_KO_FLAT, W_KO_PER_PRIZE,
    W_WASTED_ENERGY, W_BENCH_ENERGY,
    W_PRIZE_DIFF,
    W_DMG_PROGRESS,
    W_ATTACK_WITH_TRAINERS,
    W_PSYCHIC_IN_HAND,
    W_OPP_ENERGY_IN_PLAY,
    W_NONATT_ACTIVE_LATE,
    W_ATTACKER_DAMAGE,
    W_DECK_LOW_PENALTY, W_DECK_CRIT_PENALTY,
    W_HAND_TIER1, W_HAND_TIER2,
    W_NIGHT_STRETCHER_LIVE, W_ENERGY_RETRIEVAL_LIVE, W_DAWN_LIVE,
    W_OPP_BENCH_PENALTY,
    W_PRIZE_LEAD_MOMENTUM,
    W_ENGINE_COMPLETE,
)

# ── Card ID constants (mirror of main.py — keep in sync) ─────────────────────
Basic_Psychic_Energy  = 5
Dudunsparce           = 66
Smoochum              = 183
Dunsparce             = 305
Clefairy              = 1039
Mega_Clefable_ex      = 1040
Buddy_Buddy_Poffin    = 1086
Night_Stretcher       = 1097
Energy_Retrieval      = 1118
Pokegear_3            = 1122
Mega_Signal           = 1145
Poke_Pad              = 1152
Hero_Cape             = 1159
Boss_Orders           = 1182
Mortys_Conviction     = 1187
Lillie_Determination  = 1227
Dawn                  = 1231
Jacinthe              = 1241

_ATTACKER_IDS = frozenset({Clefairy, Mega_Clefable_ex})

_TRAINER_IDS = frozenset({
    Buddy_Buddy_Poffin, Night_Stretcher, Energy_Retrieval, Pokegear_3,
    Mega_Signal, Poke_Pad, Hero_Cape, Boss_Orders, Mortys_Conviction,
    Lillie_Determination, Dawn, Jacinthe,
})

# ── Card table (lazy-loaded so this file is importable without cg.api) ────────
_card_table: dict = {}

def _load_card_table() -> dict:
    global _card_table
    if not _card_table:
        try:
            from cg.api import all_card_data
            _card_table = {c.cardId: c for c in all_card_data()}
        except ImportError:
            pass
    return _card_table


# ── Helpers ───────────────────────────────────────────────────────────────────

def _prize_count(pokemon) -> int:
    ct = _load_card_table()
    data = ct.get(pokemon.id)
    if data is None:
        return 1
    count = 3 if data.megaEx else 2 if data.ex else 1
    for card in getattr(pokemon, 'energyCards', []):
        if card.id == 12:
            count -= 1
    return max(0, count)


def _has_tool_attached(pokemon, tool_id: int) -> bool:
    for attr in ('tool', 'toolCard'):
        val = getattr(pokemon, attr, None)
        if val is not None and getattr(val, 'id', None) == tool_id:
            return True
    for c in getattr(pokemon, 'energyCards', []):
        if getattr(c, 'id', None) == tool_id:
            return True
    return False


def _weakness_multiplier(pokemon, ct) -> float:
    data = ct.get(getattr(pokemon, 'id', -1))
    if not data:
        return 1.0
    for attr in ('weaknessTypes', 'weakness', 'weaknesses'):
        val = getattr(data, attr, None)
        if val is None:
            continue
        if isinstance(val, str):
            return 2.0 if 'psychic' in val.lower() else 1.0
        if hasattr(val, '__iter__'):
            for item in val:
                s = str(getattr(item, 'type', item) or '').lower()
                if 'psychic' in s:
                    return 2.0
    return 1.0


def _max_hp(pokemon, ct) -> int:
    data = ct.get(getattr(pokemon, 'id', -1))
    return getattr(data, 'hp', pokemon.hp) if data else pokemon.hp


# ── Main scoring function ─────────────────────────────────────────────────────

def heuristic_score(obs, our_index: int, unknown_cards: int = 0) -> float:
    """
    Score the current game position from our_index's perspective.
    Returns float in [-1.0, 1.0]; positive means we are ahead.
    """
    state = obs.current
    us    = state.players[our_index]
    them  = state.players[1 - our_index]
    ct    = _load_card_table()

    score = 0.0

    # ── Pre-compute reused values ──────────────────────────────────────────────
    all_our   = [p for p in (us.active + us.bench) if p]
    all_them  = [p for p in (them.active + them.bench) if p]
    our_active = us.active[0]  if us.active  and us.active[0]  else None
    opp_active = them.active[0] if them.active and them.active[0] else None

    hand_cards       = us.hand if isinstance(us.hand, list) else []
    hand_ids         = {c.id for c in hand_cards}
    discard          = getattr(us, 'discard', [])
    discard_ids      = {c.id for c in discard}
    psychic_in_hand  = sum(1 for c in hand_cards if c.id == Basic_Psychic_Energy)
    total_our_energy = sum(len(p.energies) for p in all_our)

    # ── H1: Clefairy / Clefable count bonuses ─────────────────────────────────
    attackers = [p for p in all_our if p.id in _ATTACKER_IDS]
    for i, w in enumerate((W_ATTACKER_1, W_ATTACKER_2, W_ATTACKER_3)):
        if i >= len(attackers):
            break
        score += w

    # ── H2: Dunsparce bench-setter bonus ──────────────────────────────────────
    score += W_DUNSPARCE * sum(1 for p in all_our if p.id == Dunsparce)

    # ── H2b: Penalty for energy wasted on Dunsparce ───────────────────────────
    for p in all_our:
        if p.id == Dunsparce:
            score += W_DUNSPARCE_ENERGY * len(p.energies)

    # (H3 removed)

    # ── H4: Mega Clefable ex presence bonus ───────────────────────────────────
    score += W_MEGA_CLEFABLE_EX * min(
        sum(1 for p in all_our if p.id == Mega_Clefable_ex), 2
    )

    # ── H5: Dudunsparce in hand ready to evolve ───────────────────────────────
    dunsparce_in_play   = sum(1 for p in all_our if p.id == Dunsparce)
    dudunsparce_in_hand = sum(1 for c in hand_cards if c.id == Dudunsparce)
    score += W_DUDUNSPARCE_HAND * min(dudunsparce_in_hand, dunsparce_in_play)

    # ── H6: Poke Pad in hand ──────────────────────────────────────────────────
    score += W_POKE_PAD_HAND * sum(1 for c in hand_cards if c.id == Poke_Pad)

    # ── H7 & H8: Smoochum early-setup bonuses ─────────────────────────────────
    if our_active and our_active.id == Smoochum and total_our_energy < 2:
        if any(p.id in _ATTACKER_IDS and len(p.energies) == 0 for p in us.bench if p):
            score += W_SMOOCHUM_ACTIVE
    if (any(p.id == Smoochum for p in all_our)
            and total_our_energy < 2
            and psychic_in_hand < 2):
        score += W_SMOOCHUM_PLAY

    # ── H9: Energy distribution across attackers ──────────────────────────────
    _etable = {
        (0, 1): W_E_A1_E1, (0, 2): W_E_A1_E2,
        (1, 1): W_E_A2_E1, (1, 2): W_E_A2_E2,
    }
    for i, att in enumerate(sorted(attackers, key=lambda p: len(p.energies), reverse=True)):
        for ei in range(1, len(att.energies) + 1):
            score += _etable.get((i, ei), W_E_EXCESS)

    # ── H10: Active / bench Clefable position and Hero's Cape ─────────────────
    if our_active:
        e_act  = len(our_active.energies)
        c_act  = _has_tool_attached(our_active, Hero_Cape)
        if our_active.id == Mega_Clefable_ex:
            if e_act == 0:
                score += W_ACTIVE_CLEFABLE_E0
            elif e_act == 1:
                score += W_ACTIVE_CLEFABLE_E1
            else:
                score += W_ACTIVE_CLEFABLE_E2
            if e_act >= 1 and c_act:
                score += W_ACTIVE_CLEFABLE_CAPE
        elif our_active.id == Clefairy:
            if c_act:
                score += W_ACTIVE_CLEFAIRY_CAPE
        else:
            if c_act:
                score += W_ACTIVE_NONA_CAPE

    for p in us.bench:
        if p is None:
            continue
        cape = _has_tool_attached(p, Hero_Cape)
        if p.id == Mega_Clefable_ex:
            if cape and len(p.energies) > 0:
                score += W_BENCH_CLEFABLE_CAPE
        elif p.id == Clefairy:
            if cape:
                score += W_BENCH_CLEFAIRY_CAPE
        else:
            if cape:
                score += W_BENCH_NONA_CAPE

    # ── H11: Attack damage potential ──────────────────────────────────────────
    can_attack    = False
    psychic_for_dmg = 0

    if our_active and our_active.id == Mega_Clefable_ex:
        e_active = len(our_active.energies)
        if e_active >= 2:
            can_attack = True
            psychic_for_dmg = psychic_in_hand
        elif e_active == 1 and psychic_in_hand >= 1:
            can_attack = True
            psychic_for_dmg = psychic_in_hand - 1
            score += W_ONE_ENERGY_AWAY

    if not can_attack:
        for p in us.bench:
            if p and p.id == Mega_Clefable_ex and len(p.energies) >= 1 and psychic_in_hand >= 1:
                score += W_BENCH_ATTACKER_READY
                break

    if can_attack and opp_active:
        w_mult        = _weakness_multiplier(opp_active, ct)
        attack_damage = int((120 + 40 * min(psychic_for_dmg, 4)) * w_mult)

        if attack_damage >= opp_active.hp:
            score += W_KO_FLAT + W_KO_PER_PRIZE * _prize_count(opp_active)

        # H14: cumulative damage progress toward 2-shot
        existing_dmg = max(0, _max_hp(opp_active, ct) - opp_active.hp)
        combined_dmg = attack_damage + existing_dmg
        if combined_dmg > 100:
            score += floor(combined_dmg / 100) * W_DMG_PROGRESS

    # ── H12: Cannot-attack penalties / bench-energy rewards ───────────────────
    if not can_attack:
        if our_active:
            score += W_WASTED_ENERGY * len(our_active.energies)
        for p in us.bench:
            if p and p.id in _ATTACKER_IDS:
                score += W_BENCH_ENERGY * len(p.energies)

    # ── H13: Prize differential ────────────────────────────────────────────────
    score += W_PRIZE_DIFF * (len(them.prize) - len(us.prize))

    # ── H15: Attacking with unused trainers still in hand ─────────────────────
    if can_attack and any(c.id in _TRAINER_IDS for c in hand_cards):
        score += W_ATTACK_WITH_TRAINERS

    # ── H17: Psychic Energy in hand ───────────────────────────────────────────
    score += W_PSYCHIC_IN_HAND * psychic_in_hand

    # ── H18: Opponent energy in play ──────────────────────────────────────────
    score += W_OPP_ENERGY_IN_PLAY * sum(len(p.energies) for p in all_them)

    # ── H19: Non-attacker in active when opponent has 1 prize left ────────────
    if len(them.prize) == 1 and our_active and our_active.id not in _ATTACKER_IDS:
        score += W_NONATT_ACTIVE_LATE

    # ── H20: Damage on our Clefairy / Mega Clefable ex ────────────────────────
    for p in all_our:
        if p.id in _ATTACKER_IDS:
            damage_taken = max(0, _max_hp(p, ct) - p.hp)
            score += W_ATTACKER_DAMAGE * (damage_taken // 10)

    # ── H21: Deck thinning penalty ────────────────────────────────────────────
    deck_count = getattr(us, 'deckCount', None)
    if deck_count is not None and deck_count < 10:
        base = 10 - deck_count
        mult = W_DECK_CRIT_PENALTY if deck_count < 3 else W_DECK_LOW_PENALTY
        score -= base * mult

    # ── H22: Hand-size bonus ──────────────────────────────────────────────────
    hc = len(hand_cards)
    if hc <= 10:
        score += hc * W_HAND_TIER1
    else:
        score += 10 * W_HAND_TIER1 + min(hc - 10, 10) * W_HAND_TIER2

    # ── P2: Recovery cards live ───────────────────────────────────────────────
    if Night_Stretcher in hand_ids and any(c.id in _ATTACKER_IDS for c in discard):
        score += W_NIGHT_STRETCHER_LIVE
    if Energy_Retrieval in hand_ids and Basic_Psychic_Energy in discard_ids:
        score += W_ENERGY_RETRIEVAL_LIVE
    if Dawn in hand_ids and sum(1 for c in discard if c.id == Basic_Psychic_Energy) >= 2:
        score += W_DAWN_LIVE

    # ── P3: Opponent bench size ───────────────────────────────────────────────
    score += W_OPP_BENCH_PENALTY * sum(1 for p in them.bench if p is not None) * -1

    # ── P4: Prize lead + attack-ready momentum ────────────────────────────────
    if len(us.prize) < len(them.prize) and our_active and our_active.id == Mega_Clefable_ex:
        e = len(our_active.energies)
        if e >= 2 or (e >= 1 and psychic_in_hand >= 1):
            score += W_PRIZE_LEAD_MOMENTUM

    # ── P5: Dunsparce + Dudunsparce engine pair in play ───────────────────────
    if (any(p.id == Dunsparce   for p in all_our) and
            any(p.id == Dudunsparce for p in all_our)):
        score += W_ENGINE_COMPLETE

    return max(-1.0, min(1.0, score / HEURISTIC_NORM))
