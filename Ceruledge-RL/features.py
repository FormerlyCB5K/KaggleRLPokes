"""
features.py — Convert game observation to policy network input tensors.

Generalized encoding per specs/completed/02-observation-encoding.md: our side keeps deck-specific
identity (species one-hots, card-slot zone vectors); the opponent side is encoded purely
by attributes (HP, type, rule, attack/ability tag blocks from opponent_tags.py) so any
card the engine throws at us maps into a shared feature space.

    extract_features(obs, our_idx, tracker) -> (our_pokemon (9, 19),
                                                opp_pokemon (9, 75),
                                                zones       (4, 16),   # hand, discard, deck, prizes
                                                global      (24,))
"""
from __future__ import annotations
from collections import Counter

import torch
from cg_download.api import LogType, Observation

import card_data as cd
import opponent_tags as ot
import stat_bakes as sb
from attack_overrides import ITEM_LOCK_ATTACKERS, TYRANITAR, get_override

# ── Card ID constants ──────────────────────────────────────────────────────────
Ceruledge_ex       = 320
Charcadet          = 796
Solrock            = 676
Lunatone           = 675
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

# Ordered list of all 15 unique card IDs — index = position in zone vectors
DECK_CARDS: list[int] = [
    Ceruledge_ex, Charcadet, Solrock, Lunatone, Drilbur,
    Fire_Energy, Fighting_Energy,
    Night_Stretcher, Brilliant_Blender, Fighting_Gong,
    Ultra_Ball, Poke_Pad, Boss_Orders, Explorers_Guidance, Carmine,
]
DECK_COUNTS: dict[int, int] = {
    Ceruledge_ex: 4, Charcadet: 4, Solrock: 2, Lunatone: 2, Drilbur: 1,
    Fire_Energy: 7, Fighting_Energy: 13,
    Night_Stretcher: 4, Brilliant_Blender: 1, Fighting_Gong: 4,
    Ultra_Ball: 4, Poke_Pad: 3, Boss_Orders: 3, Explorers_Guidance: 4, Carmine: 4,
}
CARD_IDX: dict[int, int] = {cid: i for i, cid in enumerate(DECK_CARDS)}

FULL_DECK: list[int] = [cid for cid in DECK_CARDS for _ in range(DECK_COUNTS[cid])]

# Pokemon one-hot order
POKE_IDS: list[int] = [Ceruledge_ex, Charcadet, Solrock, Lunatone, Drilbur]
POKE_IDX: dict[int, int] = {cid: i for i, cid in enumerate(POKE_IDS)}

# Static attack damage for our species (Ceruledge ex is dynamic: 30 + 20 × discard)
STATIC_DAMAGE: dict[int, int] = {
    Solrock: 70, Lunatone: 50, Drilbur: 20, Charcadet: 0,
}

N_OUR_POKEMON_FEATURES = 19
N_OPP_POKEMON_FEATURES = 75
N_ZONE_FEATURES        = 16
N_GLOBAL_FEATURES      = 24
N_POKEMON_SLOTS        = 9    # per side: 1 active + 8 bench
N_ZONE_WORDS           = 4    # hand, discard, deck, prizes

# Stadium one-hot order in the global word.
STADIUM_IDS: list[int] = [
    1266,  # Nighttime Mine
    1256,  # Team Rocket's Watchtower
    1261,  # Forest of Vitality
    1253,  # N's Castle
    1250,  # Area Zero Underdepths
    1259,  # Spikemuth Gym
]

_OUR_HP_MAX  = 270.0
_OPP_HP_MAX  = 340.0
_ATTACK_CLIP = 270.0
_ATTACK_RECOIL_INDEX = ot.attack_block_schema().index("recoil")


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _hits_ratio(numerator: int, denominator: int) -> float:
    """Spec 02 hits convention: min(num // den, 4) / 4; denominator 0 -> 1.0."""
    if denominator <= 0:
        return 1.0
    return min(numerator // denominator, 4) / 4.0


# ── Per-game state tracker ─────────────────────────────────────────────────────

class GameStateTracker:
    """
    Maintains state that isn't directly visible in each observation call.
    One instance per game; call update(obs, our_idx) once per observation
    (extract_features does it for you, guarded against double-processing).
    """

    def __init__(self):
        # lazy import: prize_check imports DECK_CARDS/FULL_DECK back from us
        from prize_check import PrizeTracker
        self._prize_cls = PrizeTracker
        self.reset()

    def reset(self):
        self._last_turn:        int = -1
        self._last_obs_id:      int | None = None
        self.lunar_used:        bool = False
        self.supporter_used:    bool = False
        self.item_lock_tracked: bool = False        # Budew/Frillish attack observed
        self.evolved_serials:   set[int] = set()    # our serials evolved this turn
        self.prizes = self._prize_cls()

    # -- per-turn marks (called from actions.py) --
    def new_turn(self, turn: int):
        if turn != self._last_turn:
            self._last_turn      = turn
            self.lunar_used      = False
            self.supporter_used  = False
            self.evolved_serials = set()

    def mark_supporter(self):
        self.supporter_used = True

    def mark_lunar(self):
        self.lunar_used = True

    # -- per-observation update --
    def update(self, obs: Observation, our_idx: int):
        if obs.current is None:
            return
        self.new_turn(obs.current.turn)

        # obs.logs are "events since the last selection" — process each obs once.
        if id(obs) != self._last_obs_id:
            self._last_obs_id = id(obs)
            for log in (obs.logs or []):
                if (log.type == LogType.ATTACK and log.playerIndex != our_idx
                        and log.cardId in ITEM_LOCK_ATTACKERS):
                    self.item_lock_tracked = True
                elif log.type == LogType.TURN_END and log.playerIndex == our_idx:
                    self.item_lock_tracked = False     # cleared at end of our turn
                elif log.type == LogType.EVOLVE and log.playerIndex == our_idx:
                    if log.serial is not None:
                        self.evolved_serials.add(log.serial)
            self.prizes.update(obs, our_idx)


# ── Zone encoding ──────────────────────────────────────────────────────────────

def _encode_zone(counts, unknown: bool) -> list[float]:
    """Encode a card zone to 15 per-card count dims + is_unknown flag."""
    if unknown:
        return [0.0] * 15 + [1.0]
    vec = [_clip01(counts.get(cid, 0) / DECK_COUNTS[cid]) for cid in DECK_CARDS]
    vec.append(0.0)
    return vec


def encode_card_as_zone(card_id: int) -> list[float]:
    """
    Encode a single card (from deck/discard search) as a 16-float zone vector.
    Used when building Stage 2 candidate vectors for individual cards.
    """
    vec = [0.0] * 15
    idx = CARD_IDX.get(card_id)
    if idx is not None:
        vec[idx] = 1.0 / DECK_COUNTS.get(card_id, 1)
    vec.append(0.0)
    return vec


def _in_play_card_ids(ps) -> list[int]:
    """All our card ids bound up in play: Pokemon + energy + tools + pre-evolutions."""
    ids: list[int] = []
    pokes = []
    if ps.active:
        pokes += [p for p in ps.active if p is not None]
    if ps.bench:
        pokes += [p for p in ps.bench if p is not None]
    for poke in pokes:
        ids.append(poke.id)
        ids += [c.id for c in (poke.energyCards or [])]
        ids += [c.id for c in (poke.tools or [])]
        ids += [c.id for c in (poke.preEvolution or [])]
    return ids


# ── Our Pokemon vector — 19 dims ───────────────────────────────────────────────

def _status_flags(player_state, is_active: bool) -> list[float]:
    """5 flags, spec order: Asleep, Paralyzed, Burned, Poisoned, Confused.
    Only the active Pokemon carries them; bench slots are all zeros."""
    if not is_active:
        return [0.0] * 5
    return [float(player_state.asleep), float(player_state.paralyzed),
            float(player_state.burned), float(player_state.poisoned),
            float(player_state.confused)]


def _our_attack_damage(card_id: int, discard_energy: int) -> int:
    if card_id == Ceruledge_ex:
        return min(30 + 20 * discard_energy, int(_ATTACK_CLIP))
    return STATIC_DAMAGE.get(card_id, 0)


def _our_attacker_type(card_id: int):
    """Type symbol of one of our species (for weakness/resistance in our→opp KO math)."""
    return cd.CardRegistry.load().get(card_id).type_sym


def _encode_our_pokemon(poke, ps, is_active: bool, discard_energy: int,
                        opp_active, opp_max_damage: int,
                        tracker: GameStateTracker, board) -> list[float]:
    # HP with ability/stadium auras folded in (Tool HP already in observed maxHp)
    hp_max, hp_curr = sb.effective_hp(poke, True, board)

    onehot = [0.0] * 5
    idx = POKE_IDX.get(poke.id)
    if idx is not None:
        onehot[idx] = 1.0

    new_in_play = 1.0 if (poke.appearThisTurn
                          or poke.serial in tracker.evolved_serials) else 0.0

    fire_e  = sum(1 for e in (poke.energyCards or []) if e.id == Fire_Energy)
    fight_e = sum(1 for e in (poke.energyCards or []) if e.id == Fighting_Energy)

    dmg = _our_attack_damage(poke.id, discard_energy)
    dmg_eff = dmg + sb.damage_dealt_bonus(poke, True, opp_active, board)   # our own boosts
    dmg_eff = max(0, dmg_eff)

    # attack_hits_opponent: our effective damage (weakness/resist + opp reduction) vs the
    # opponent active's effective HP. damage 0 -> 1.0; no opp active -> 0.0 (0-HP active).
    if dmg <= 0:
        hits_opp = 1.0
    elif opp_active is None:
        hits_opp = 0.0
    else:
        eff_dmg = sb.effective_damage(dmg, _our_attacker_type(poke.id), poke, True,
                                      opp_active, False, board)
        _, opp_curr = sb.effective_hp(opp_active, False, board)
        hits_opp = 1.0 if eff_dmg <= 0 else (
            _hits_ratio(opp_curr, eff_dmg) if opp_curr > 0 else 0.0)

    # attacks_survivable: route the opponent's credible threat through the same
    # weakness/resistance and damage-reduction math as every other KO feature.
    # opp_max_damage was computed against our Active. Remove that target-specific
    # bonus, then recompute it against this slot (important for e.g. Belt vs ex).
    opp_type = (cd.CardRegistry.load().get(opp_active.id).type_sym
                if opp_active is not None else None)
    # The original target used by opp_active_max_damage is the board's marked our
    # Active; recover it directly rather than assuming every encoded slot is Active.
    original_target = next((p for p in board.our_pokes if board.is_active(p)), None)
    active_bonus = sb.damage_dealt_bonus(opp_active, False, original_target, board)
    base_threat = max(0, opp_max_damage - active_bonus)
    incoming = (sb.effective_damage(base_threat, opp_type, opp_active, False,
                                    poke, True, board)
                if opp_active is not None else 0)

    return (
        [_clip01(hp_max / _OUR_HP_MAX),
         _clip01(hp_curr / hp_max),
         1.0 if poke.id in (Ceruledge_ex, Charcadet) else 0.0]
        + onehot
        + [new_in_play,
           _clip01(fire_e / 2.0),
           _clip01(fight_e / 2.0),
           _hits_ratio(hp_curr, incoming),
           _clip01(dmg_eff / _ATTACK_CLIP),
           hits_opp]
        + _status_flags(ps, is_active)
    )


# ── Opponent Pokemon vector — 75 dims ──────────────────────────────────────────

def _encode_opp_pokemon(poke, opp_ps, is_active: bool,
                        our_discard_energy: int, board, our_active) -> list[float]:
    st = cd.CardRegistry.load().get(poke.id)
    static_hp_override = (get_override(poke.id) or {}).get("max_hp", 0)
    # override-aware base HP, then fold in ability/stadium HP auras (both max and curr)
    aura = sb.hp_aura(poke, False, board)
    hp_max  = max(1, max(poke.maxHp or 0, static_hp_override, st.max_hp or 0) + aura)
    hp_curr = min(max(0, (poke.hp or 0) + aura), hp_max)

    is_plain = not (st.is_ex or st.is_mega_ex)
    type_onehot = [1.0 if st.type_sym == t else 0.0 for t in cd.POK_TYPES]
    weak_fire, weak_fighting, resist_fire, resist_fighting = \
        sb.effective_weak_resist(poke, False, board)
    retreat = sb.effective_retreat(poke, False, board, st.retreat)

    # attacks_survivable_vs_ceruledge: our Ceruledge (Fire) effective damage vs eff HP
    ceruledge_dmg = 30 + 20 * our_discard_energy
    eff_cer = sb.effective_damage(ceruledge_dmg, sb.FIRE, our_active, True,
                                  poke, False, board)

    attack_flat, ability_vec, _max_dmg = ot.card_tag_vectors(poke.id)
    attack_flat = _apply_dynamic_attack_features(poke, attack_flat, board)

    base = (
        [_clip01(hp_max / _OPP_HP_MAX),
         _clip01(hp_curr / hp_max),
         1.0 if is_plain else 0.0,
         1.0 if st.is_ex else 0.0,
         1.0 if st.is_mega_ex else 0.0,
         1.0 if (poke.tools or []) else 0.0,
         _clip01(retreat / 4.0)]
        + type_onehot
        + [1.0 if weak_fire else 0.0,
           1.0 if weak_fighting else 0.0,
           1.0 if resist_fire else 0.0,
           1.0 if resist_fighting else 0.0,
           _hits_ratio(hp_curr, eff_cer),
           _clip01(len(poke.energyCards or []) / 5.0)]
        + _status_flags(opp_ps, is_active)
    )
    vec = base + attack_flat + ability_vec
    assert len(vec) == N_OPP_POKEMON_FEATURES
    return vec


def _palafin_recoil_hp(poke) -> int:
    """Vanguard Punch recoil: 10 HP per damage counter currently on Palafin."""
    damage_taken = max(0, (poke.maxHp or 0) - (poke.hp or 0))
    return 10 * (damage_taken // 10)


def _apply_dynamic_attack_features(poke, attack_flat: list[float], board) -> list[float]:
    """Apply live-board attack fields that cannot be represented by cached card tags."""
    out = list(attack_flat)
    if poke.id == 51:  # Palafin — Vanguard Punch
        out[_ATTACK_RECOIL_INDEX] = _clip01(_palafin_recoil_hp(poke) / 70.0)
    # Each attack block begins with normalized total Energy cost. Cost changes inform
    # realistic usability but never zero or otherwise alter damage capability.
    for i, cost in enumerate(sb.effective_attack_costs(poke, False, board)):
        if i >= 2:
            break
        out[i * ot.N_ATTACK_BLOCK] = _clip01(cost / 5.0)
    return out


_CYNTHIA_POKEMON = frozenset({379, 380, 381, 342, 341, 387})
_CYNTHIA_DAMAGE_BOOSTERS = frozenset({342, 341})
_IONO_POKEMON = frozenset({265, 268, 269, 270, 271})
_TEAM_ROCKET_SUPPORTERS = frozenset({1216, 1217, 1218, 1219, 1220})
_ENERGY_IDS = frozenset(range(1, 21))


def _pokemon_in_play(ps) -> list:
    return [p for p in list(ps.active or []) + list(ps.bench or []) if p is not None]


def opp_active_max_damage(opp_active, opp_ps=None, our_ps=None,
                          board=None, our_active=None) -> int:
    """Highest credible current damage for the opponent active.

    Uses the reviewed static override first, then realizes the small set of
    matchup-specific board-dependent formulas from attack_overrides.py, then folds in
    stat_bakes damage_dealt bonuses (tools/abilities/stadium) on the opponent's side.
    """
    if opp_active is None:
        return 0
    cid = opp_active.id
    base = ot.card_tags(cid).max_damage
    opp_in_play = _pokemon_in_play(opp_ps) if opp_ps is not None else []
    damage_on_active = max(0, (opp_active.maxHp or 0) - (opp_active.hp or 0))

    if cid == 743 and opp_ps is not None:                 # Alakazam — Powerful Hand
        base = max(base, 20 * (opp_ps.handCount or 0))
    elif cid == 190:                                      # Archaludon via Raging Hammer
        base = max(base, 80 + damage_on_active)
    elif cid == 532:                                      # Dwebble — Flail
        base = max(base, damage_on_active)
    elif cid == 387 and opp_ps is not None:                # Cynthia's Spiritomb
        other_damage = sum(max(0, (p.maxHp or 0) - (p.hp or 0))
                           for p in opp_in_play if p.serial != opp_active.serial)
        base = max(base, other_damage)
    elif cid == 474 and opp_ps is not None:                # Rocket's Porygon2
        supporters = sum(1 for c in (opp_ps.discard or [])
                         if c.id in _TEAM_ROCKET_SUPPORTERS)
        base = max(base, 20 * supporters)
    elif cid == 265 and opp_ps is not None:                # Iono's Voltorb
        iono_energy = sum(len(p.energyCards or []) for p in opp_in_play
                          if p.id in _IONO_POKEMON)
        base = max(base, 20 + 20 * iono_energy)
    elif cid == 293 and our_ps is not None:                # N's Zoroark ex — Night Joker
        our_discard_energy = sum(1 for c in (our_ps.discard or [])
                                 if c.id in _ENERGY_IDS)
        base = max(base, 2 * damage_on_active,
                   10 + 30 * our_discard_energy)

    if cid in _CYNTHIA_POKEMON and opp_ps is not None:
        rose_boost = 30 * sum(1 for p in opp_in_play
                              if p.id in _CYNTHIA_DAMAGE_BOOSTERS)
        base += rose_boost
    if board is not None:
        base += sb.damage_dealt_bonus(opp_active, False, our_active, board)
    return int(base)


# ── Main extraction function ───────────────────────────────────────────────────

def extract_features(
    obs: Observation,
    our_idx: int,
    tracker: GameStateTracker,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """
    Extract input tensors from an observation.

    Returns:
        our_pokemon : (9, 19)  — our active + bench 1-8
        opp_pokemon : (9, 75)  — opp active + bench 1-8
        zones       : (4, 16)  — hand, discard, deck, prizes
        global      : (24,)
    """
    ps     = obs.current.players[our_idx]
    opp_ps = obs.current.players[1 - our_idx]
    state  = obs.current

    tracker.update(obs, our_idx)

    # Fire + Fighting energy in our discard (Ceruledge damage driver)
    energy_in_disc = sum(
        1 for c in (ps.discard or [])
        if c.id in (Fire_Energy, Fighting_Energy)
    )

    opp_active = opp_ps.active[0] if (opp_ps.active and opp_ps.active[0] is not None) else None
    our_active = ps.active[0] if (ps.active and ps.active[0] is not None) else None

    # Board context for stat_bakes (tool/ability/stadium effects folded into KO math)
    stadium_id = state.stadium[0].id if state.stadium else None
    board = sb.Board(_pokemon_in_play(ps), _pokemon_in_play(opp_ps), stadium_id,
                     our_prizes=len(ps.prize or []), opp_prizes=len(opp_ps.prize or []))
    board.mark_active(our_active)
    board.mark_active(opp_active)

    opp_maxdmg = opp_active_max_damage(opp_active, opp_ps, ps, board, our_active)

    # ── Our Pokemon slots (6) ──────────────────────────────────────────────────
    our_slots: list[list[float]] = []
    our_slots.append(
        _encode_our_pokemon(our_active, ps, True, energy_in_disc, opp_active, opp_maxdmg,
                            tracker, board)
        if our_active else [0.0] * N_OUR_POKEMON_FEATURES)
    for i in range(N_POKEMON_SLOTS - 1):
        p = ps.bench[i] if (ps.bench and i < len(ps.bench)) else None
        our_slots.append(
            _encode_our_pokemon(p, ps, False, energy_in_disc, opp_active, opp_maxdmg,
                                tracker, board)
            if p else [0.0] * N_OUR_POKEMON_FEATURES)

    # ── Opponent Pokemon slots (6) ─────────────────────────────────────────────
    opp_slots: list[list[float]] = []
    opp_slots.append(
        _encode_opp_pokemon(opp_active, opp_ps, True, energy_in_disc, board, our_active)
        if opp_active else [0.0] * N_OPP_POKEMON_FEATURES)
    for i in range(N_POKEMON_SLOTS - 1):
        p = opp_ps.bench[i] if (opp_ps.bench and i < len(opp_ps.bench)) else None
        opp_slots.append(
            _encode_opp_pokemon(p, opp_ps, False, energy_in_disc, board, our_active)
            if p else [0.0] * N_OPP_POKEMON_FEATURES)

    # ── Zone words: hand, discard, deck, prizes ────────────────────────────────
    hand_counts    = Counter(c.id for c in (ps.hand or []))
    discard_counts = Counter(c.id for c in (ps.discard or []))

    prizes_known = tracker.prizes.prizes_known
    prize_counts = tracker.prizes.prize_counts

    if prizes_known:
        # deck by elimination: full deck − hand − discard − in-play − known prizes
        # TODO: While a Trainer resolves it can temporarily be absent from every zone.
        # Account for obs.select.effect here if exact transient deck counts become
        # strategically important; currently this one-card edge case is accepted.
        deck_counts = (Counter(FULL_DECK) - hand_counts - discard_counts
                       - Counter(_in_play_card_ids(ps)) - prize_counts)
        deck_vec  = _encode_zone(deck_counts, unknown=False)
        prize_vec = _encode_zone(prize_counts, unknown=False)
    else:
        # until the prize tracker resolves, BOTH deck and prizes are unknown
        deck_vec  = _encode_zone(None, unknown=True)
        prize_vec = _encode_zone(None, unknown=True)

    zone_rows = [
        _encode_zone(hand_counts, unknown=False),
        _encode_zone(discard_counts, unknown=False),
        deck_vec,
        prize_vec,
    ]

    # ── Global vector (24) ─────────────────────────────────────────────────────
    our_in_play = []
    if ps.active:
        our_in_play += [p for p in ps.active if p]
    if ps.bench:
        our_in_play += [p for p in ps.bench if p]
    in_play_ids = {p.id for p in our_in_play}

    # ceruledge_KO: effective ceruledge damage (weakness/resist + opp reduction) vs the
    # opponent active's effective HP; real division clipped at 1.0; no opp active -> 1.0
    ceruledge_dmg = 30 + 20 * energy_in_disc
    if opp_active is None:
        ceruledge_ko = 1.0
    else:
        eff_cer = sb.effective_damage(ceruledge_dmg, sb.FIRE, our_active, True,
                                      opp_active, False, board)
        _, eff_opp_hp = sb.effective_hp(opp_active, False, board)
        ceruledge_ko = 1.0 if eff_opp_hp <= 0 else _clip01(eff_cer / eff_opp_hp)

    item_locked = tracker.item_lock_tracked or (
        opp_active is not None and opp_active.id == TYRANITAR)

    turn_order = (0.5 if state.firstPlayer < 0
                  else float(state.firstPlayer != our_idx))
    stadium_ids_in_play = {card.id for card in (state.stadium or []) if card is not None}
    stadium_onehot = [float(cid in stadium_ids_in_play) for cid in STADIUM_IDS]

    global_vec: list[float] = [
        float(Solrock in in_play_ids and Lunatone in in_play_ids),
        _clip01(sum(1 for p in our_in_play if p.id in (Ceruledge_ex, Charcadet)) / 4.0),
        _clip01(energy_in_disc / 16.0),
        ceruledge_ko,
        _clip01(state.turn / 30.0),
        float(item_locked),
        # The engine exposes this exact per-turn rule state directly; unlike effects
        # inferred from logs, it needs no duplicate tracker state.
        float(state.energyAttached),
        float(state.supporterPlayed or tracker.supporter_used),
        float(tracker.lunar_used),
        turn_order,
        _clip01(len(ps.prize or []) / 6.0),
        _clip01(len(ps.hand or []) / 15.0),
        _clip01(len(ps.discard or []) / 46.0),
        _clip01(ps.deckCount / 46.0),
        _clip01(len(opp_ps.prize or []) / 6.0),
        _clip01(opp_ps.handCount / 15.0),
        _clip01(len(opp_ps.discard or []) / 46.0),
        _clip01(opp_ps.deckCount / 46.0),
    ] + stadium_onehot

    return (
        torch.tensor(our_slots, dtype=torch.float32),   # (9, 19)
        torch.tensor(opp_slots, dtype=torch.float32),   # (9, 75)
        torch.tensor(zone_rows, dtype=torch.float32),   # (4, 16)
        torch.tensor(global_vec, dtype=torch.float32),  # (24,)
    )
