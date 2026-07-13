"""
Clefable MCTS Agent — Pokémon TCG AI Battle Challenge

Architecture:
  Shallow MCTS (max depth 3, measured in OUR main-phase selections) with a
  rules-based greedy rollout (3 further steps) for leaf evaluation.

Key decisions:
  - Tree nodes exist only at OUR SelectContext.MAIN decision points.
    Everything else (sub-selections, opponent turns) is fast-forwarded with
    the same greedy policy used for rollouts.
  - Depth counts only our player's MAIN selections, so depth 3 lets the agent
    see 3-card combos within the same turn (e.g. attach + evolve + Hero's Cape).
  - UCB exploration constant C = 1.5 (above √2 ≈ 1.41 → prefers exploration).
  - Imperfect information: if the game requires an unrecognized SelectContext
    (coin flip resolution, etc.), score immediately with the heuristic instead
    of simulating further.
  - Card draws: when cards are drawn during search, they are unknown. Their
    count is forwarded to the heuristic as `unknown_cards` for a small bonus.
"""

import math
import os
import random
import time

from cg_download.api import (
    AreaType,
    Card,
    Observation,
    OptionType,
    Pokemon,
    SearchState,
    SelectContext,
    all_card_data,
    search_begin,
    search_end,
    search_step,
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

# ── Clefable-deck card ID constants ───────────────────────────────────────────

# Pokémon
Dudunsparce      = 66     # ×4  (Dunsparce's evolution — draw engine, no energy)
Smoochum         = 183    # ×1  (support ability, no energy)
Dunsparce        = 305    # ×4  (bench-setter, no energy)
Clefairy         = 1039   # ×4  (evolves into Mega Clefable ex)
Mega_Clefable_ex = 1040   # ×4  (main attacker)

# Energy
Basic_Psychic_Energy = 5  # ×10

# Trainer — Items
Buddy_Buddy_Poffin = 1086  # ×4
Night_Stretcher    = 1097  # ×2
Energy_Retrieval   = 1118  # ×2
Pokegear_3         = 1122  # ×2
Mega_Signal        = 1145  # ×1
Poke_Pad           = 1152  # ×4
Hero_Cape          = 1159  # ×1

# Trainer — Supporters
Boss_Orders          = 1182  # ×3
Mortys_Conviction    = 1187  # ×4
Lillie_Determination = 1227  # ×4
Dawn                 = 1231  # ×2
Jacinthe             = 1241  # ×4

# Tool cards — all other ATTACH options are energy attaches.
TOOL_CARD_IDS: frozenset[int] = frozenset({Hero_Cape})

# Pokémon that should NEVER receive energy.
# Pruned from MCTS branches entirely; penalised to -500 in the greedy rollout.
NO_ENERGY_POKEMON_IDS: frozenset[int] = frozenset({
    Dudunsparce,  # draw engine only — never needs energy
    Smoochum,     # support only — never needs energy
})
# Dunsparce CAN receive energy (penalised in heuristic, allowed by expand)

# ── MCTS hyperparameters ──────────────────────────────────────────────────────

MAX_DEPTH       = 4    # max OUR main-phase selections before heuristic eval
MCTS_ITERATIONS = 100_000  # hard cap; time budget is the real constraint
UCB_C           = 1.5  # exploration constant
ROLLOUT_STEPS   = 4    # greedy steps in rollout after reaching a leaf

# SelectContexts we recognise as fully deterministic.
# Any other context → imperfect information → score immediately.
_KNOWN_CONTEXTS: set | None = None

def _known_contexts() -> set:
    global _KNOWN_CONTEXTS
    if _KNOWN_CONTEXTS is None:
        _KNOWN_CONTEXTS = {
            SelectContext.MAIN,
            SelectContext.SWITCH,
            SelectContext.TO_ACTIVE,
            SelectContext.SETUP_ACTIVE_POKEMON,
            SelectContext.TO_HAND,
            SelectContext.ATTACH_FROM,
        }
    return _KNOWN_CONTEXTS

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_card(obs: Observation, area: AreaType, index: int, player_index: int):
    ps = obs.current.players[player_index]
    match area:
        case AreaType.DECK:    return obs.select.deck[index]
        case AreaType.HAND:    return ps.hand[index]
        case AreaType.DISCARD: return ps.discard[index]
        case AreaType.ACTIVE:  return ps.active[index]
        case AreaType.BENCH:   return ps.bench[index]
        case AreaType.PRIZE:   return ps.prize[index]
        case AreaType.STADIUM: return obs.current.stadium[index]
        case AreaType.LOOKING: return obs.current.looking[index]
        case _:                return None


def prize_count(pokemon: Pokemon) -> int:
    data = card_table[pokemon.id]
    count = 3 if data.megaEx else 2 if data.ex else 1
    for card in pokemon.energyCards:
        if card.id == 12:  # Legacy Energy reduces prize count
            count -= 1
    return max(0, count)


def _has_tool_attached(pokemon, tool_id: int) -> bool:
    """True if pokemon has the given tool card equipped."""
    for attr in ('tool', 'toolCard'):
        val = getattr(pokemon, attr, None)
        if val is not None and getattr(val, 'id', None) == tool_id:
            return True
    for c in getattr(pokemon, 'energyCards', []):
        if getattr(c, 'id', None) == tool_id:
            return True
    return False


def _weakness_multiplier(pokemon) -> float:
    """2.0 if pokemon is weak to Psychic, else 1.0."""
    data = card_table.get(getattr(pokemon, 'id', -1))
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


def _max_hp(pokemon) -> int:
    """Printed max HP from the card table; falls back to current HP."""
    data = card_table.get(getattr(pokemon, 'id', -1))
    return getattr(data, 'hp', pokemon.hp) if data else pokemon.hp


# ── Heuristic position scorer ─────────────────────────────────────────────────
# Full implementation lives in heuristic_score.py (for iterating weights).
# When submitting, paste the contents of heuristic_score.py here and remove
# the import. Weights are in weights.py; paste those inline too.

_ATTACKER_IDS = frozenset({Clefairy, Mega_Clefable_ex})

# Trainer/item card IDs — used in H15 to detect unplayed cards when attacking.
_TRAINER_IDS = frozenset({
    Buddy_Buddy_Poffin, Night_Stretcher, Energy_Retrieval, Pokegear_3,
    Mega_Signal, Poke_Pad, Hero_Cape, Boss_Orders, Mortys_Conviction,
    Lillie_Determination, Dawn, Jacinthe,
})

# Tunable values — sourced from weights.py; inline here for the final submission.
# Paste the contents of weights.py here before submitting.
HEURISTIC_NORM           = 40.0

W_ATTACKER_1             =  2.0
W_ATTACKER_2             =  1.5
W_ATTACKER_3             =  1.0

W_DUNSPARCE              =  1.0
W_DUNSPARCE_ENERGY       = -1.0

W_MEGA_CLEFABLE_EX       =  2.5
W_DUDUNSPARCE_HAND       =  0.5
W_POKE_PAD_HAND          =  0.3

W_SMOOCHUM_ACTIVE        =  3.0
W_SMOOCHUM_PLAY          =  1.0

W_E_A1_E1                =  2.0
W_E_A1_E2                =  3.0
W_E_A2_E1                =  2.0
W_E_A2_E2                =  1.0
W_E_EXCESS               = -1.0

W_ACTIVE_CLEFABLE_E0     = -5.0
W_ACTIVE_CLEFABLE_E1     =  3.0
W_ACTIVE_CLEFABLE_E2     =  5.0
W_ACTIVE_CLEFABLE_CAPE   =  2.0
W_ACTIVE_CLEFAIRY_CAPE   =  0.5
W_ACTIVE_NONA_CAPE       = -3.0
W_BENCH_CLEFABLE_CAPE    =  1.0
W_BENCH_CLEFAIRY_CAPE    =  0.5
W_BENCH_NONA_CAPE        = -3.0

W_ONE_ENERGY_AWAY        =  1.0
W_BENCH_ATTACKER_READY   =  1.0
W_KO_FLAT                =  7.0
W_KO_PER_PRIZE           =  2.0

W_WASTED_ENERGY          = -1.0
W_BENCH_ENERGY           =  1.0

W_PRIZE_DIFF             = 15.0
W_GAME_POINT             =  5.0
W_DMG_PROGRESS           =  5.0

W_ATTACK_WITH_TRAINERS   = -1.0
W_PSYCHIC_IN_HAND        =  0.5
W_OPP_ENERGY_IN_PLAY     = -1.0
W_NONATT_ACTIVE_LATE     = -10.0
W_ATTACKER_DAMAGE        = -0.2

W_DECK_LOW_PENALTY       =  1.0
W_DECK_CRIT_PENALTY      =  2.0

W_HAND_TIER1             =  0.9
W_HAND_TIER2             =  0.4

W_NIGHT_STRETCHER_LIVE   =  0.5
W_ENERGY_RETRIEVAL_LIVE  =  0.5
W_DAWN_LIVE              =  0.5

W_OPP_BENCH_PENALTY      =  0.5
W_PRIZE_LEAD_MOMENTUM    =  2.0
W_ENGINE_COMPLETE        =  1.0
W_SMALL_HAND_SUPPORTER   =  1.0


def heuristic_score(obs: Observation, our_index: int, unknown_cards: int = 0) -> float:
    """
    Score the current position from our_index's perspective.
    Returns float in [-1.0, 1.0]; positive = we are ahead.
    Raw score is divided by HEURISTIC_NORM before the final clamp.
    """
    state = obs.current
    us    = state.players[our_index]
    them  = state.players[1 - our_index]

    raw = 0.0

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
        raw += w

    # ── H2: Dunsparce bench-setter bonus ──────────────────────────────────────
    raw += W_DUNSPARCE * sum(1 for p in all_our if p.id == Dunsparce)

    # ── H2b: Penalty for energy wasted on Dunsparce ───────────────────────────
    for _p in all_our:
        if _p.id == Dunsparce:
            raw += W_DUNSPARCE_ENERGY * len(_p.energies)

    # ── H4: Mega Clefable ex presence bonus ───────────────────────────────────
    raw += W_MEGA_CLEFABLE_EX * min(sum(1 for p in all_our if p.id == Mega_Clefable_ex), 2)

    # ── H5: Dudunsparce in hand ready to evolve ───────────────────────────────
    dunsparce_in_play   = sum(1 for p in all_our if p.id == Dunsparce)
    dudunsparce_in_hand = sum(1 for c in hand_cards if c.id == Dudunsparce)
    raw += W_DUDUNSPARCE_HAND * min(dudunsparce_in_hand, dunsparce_in_play)

    # ── H6: Poke Pad in hand ──────────────────────────────────────────────────
    raw += W_POKE_PAD_HAND * sum(1 for c in hand_cards if c.id == Poke_Pad)

    # ── H7 & H8: Smoochum early-setup bonuses (stack) ─────────────────────────
    if our_active and our_active.id == Smoochum and total_our_energy < 2:
        if any(p.id in _ATTACKER_IDS and len(p.energies) == 0 for p in us.bench if p):
            raw += W_SMOOCHUM_ACTIVE
    if (any(p.id == Smoochum for p in all_our)
            and total_our_energy < 2
            and psychic_in_hand < 2):
        raw += W_SMOOCHUM_PLAY

    # ── H9: Energy distribution across attackers ──────────────────────────────
    _etable = {(0, 1): W_E_A1_E1, (0, 2): W_E_A1_E2, (1, 1): W_E_A2_E1, (1, 2): W_E_A2_E2}
    for i, att in enumerate(sorted(attackers, key=lambda p: len(p.energies), reverse=True)):
        for ei in range(1, len(att.energies) + 1):
            raw += _etable.get((i, ei), W_E_EXCESS)

    # ── H10: Active/bench Clefable and Hero's Cape scoring ────────────────────
    if our_active:
        e_act  = len(our_active.energies)
        c_act  = _has_tool_attached(our_active, Hero_Cape)
        if our_active.id == Mega_Clefable_ex:
            raw += (W_ACTIVE_CLEFABLE_E0 if e_act == 0
                    else W_ACTIVE_CLEFABLE_E1 if e_act == 1
                    else W_ACTIVE_CLEFABLE_E2)
            if e_act >= 1 and c_act:
                raw += W_ACTIVE_CLEFABLE_CAPE
        elif our_active.id == Clefairy:
            if c_act:
                raw += W_ACTIVE_CLEFAIRY_CAPE
        else:
            if c_act:
                raw += W_ACTIVE_NONA_CAPE

    for p in us.bench:
        if p is None:
            continue
        cape = _has_tool_attached(p, Hero_Cape)
        if p.id == Mega_Clefable_ex:
            if cape and len(p.energies) > 0:
                raw += W_BENCH_CLEFABLE_CAPE
        elif p.id == Clefairy:
            if cape:
                raw += W_BENCH_CLEFAIRY_CAPE
        else:
            if cape:
                raw += W_BENCH_NONA_CAPE

    # ── H11: Attack damage potential ──────────────────────────────────────────
    can_attack    = False
    psychic_for_dmg = 0

    if our_active and our_active.id == Mega_Clefable_ex:
        e_act = len(our_active.energies)
        if e_act >= 2:
            can_attack = True
            psychic_for_dmg = psychic_in_hand
        elif e_act == 1 and psychic_in_hand >= 1:
            can_attack = True
            psychic_for_dmg = psychic_in_hand - 1
            raw += W_ONE_ENERGY_AWAY

    if not can_attack:
        for p in us.bench:
            if p and p.id == Mega_Clefable_ex and len(p.energies) >= 1 and psychic_in_hand >= 1:
                raw += W_BENCH_ATTACKER_READY
                break

    if can_attack and opp_active:
        dmg = int((120 + 40 * min(psychic_for_dmg, 4)) * _weakness_multiplier(opp_active))
        if dmg >= opp_active.hp:
            raw += W_KO_FLAT + W_KO_PER_PRIZE * prize_count(opp_active)
        # H14: combined damage progress toward 2-shot
        existing  = max(0, _max_hp(opp_active) - opp_active.hp)
        combined  = dmg + existing
        if combined > 100:
            raw += (combined // 100) * W_DMG_PROGRESS

    # ── H12: Cannot-attack penalties / bench-energy rewards ───────────────────
    if not can_attack:
        if our_active:
            raw += W_WASTED_ENERGY * len(our_active.energies)
        for p in us.bench:
            if p and p.id in _ATTACKER_IDS:
                raw += W_BENCH_ENERGY * len(p.energies)

    # ── H13: Prize differential ────────────────────────────────────────────────
    raw += W_PRIZE_DIFF * (len(them.prize) - len(us.prize))

    # ── N8: Game point — we need exactly 1 more prize ─────────────────────────
    if len(us.prize) == 1:
        raw += W_GAME_POINT

    # ── H15: Attacking with unused trainers in hand ───────────────────────────
    if can_attack and any(c.id in _TRAINER_IDS for c in hand_cards):
        raw += W_ATTACK_WITH_TRAINERS

    # ── H17: Psychic Energy in hand ───────────────────────────────────────────
    raw += W_PSYCHIC_IN_HAND * psychic_in_hand

    # ── H18: Opponent energy in play ──────────────────────────────────────────
    raw += W_OPP_ENERGY_IN_PLAY * sum(len(p.energies) for p in all_them)

    # ── H19: Non-attacker in active when opponent has 1 prize left ────────────
    if len(them.prize) == 1 and our_active and our_active.id not in _ATTACKER_IDS:
        raw += W_NONATT_ACTIVE_LATE

    # ── H20: Damage on our Clefairy / Mega Clefable ex ────────────────────────
    for p in all_our:
        if p.id in _ATTACKER_IDS:
            raw += W_ATTACKER_DAMAGE * (max(0, _max_hp(p) - p.hp) // 10)

    # ── H21: Deck thinning penalty ────────────────────────────────────────────
    deck_count = getattr(us, 'deckCount', None)
    if deck_count is not None and deck_count < 10:
        penalty = 10 - deck_count
        mult = W_DECK_CRIT_PENALTY if deck_count < 3 else W_DECK_LOW_PENALTY
        raw -= float(penalty) * mult

    # ── H22: Hand-size bonus ──────────────────────────────────────────────────
    _hc = len(hand_cards)
    if _hc <= 10:
        raw += _hc * W_HAND_TIER1
    else:
        raw += 10 * W_HAND_TIER1 + min(_hc - 10, 10) * W_HAND_TIER2

    # ── P2: Recovery cards live ───────────────────────────────────────────────
    if Night_Stretcher in hand_ids and any(c.id in _ATTACKER_IDS for c in discard):
        raw += W_NIGHT_STRETCHER_LIVE
    if Energy_Retrieval in hand_ids and Basic_Psychic_Energy in discard_ids:
        raw += W_ENERGY_RETRIEVAL_LIVE
    if Dawn in hand_ids and sum(1 for c in discard if c.id == Basic_Psychic_Energy) >= 2:
        raw += W_DAWN_LIVE

    # ── P3: Opponent bench size ───────────────────────────────────────────────
    raw -= W_OPP_BENCH_PENALTY * sum(1 for p in them.bench if p is not None)

    # ── P4: Prize lead + attack-ready momentum ────────────────────────────────
    if len(us.prize) < len(them.prize) and our_active and our_active.id == Mega_Clefable_ex:
        e = len(our_active.energies)
        if e >= 2 or (e >= 1 and psychic_in_hand >= 1):
            raw += W_PRIZE_LEAD_MOMENTUM

    # ── P5: Dunsparce + Dudunsparce engine pair in play ───────────────────────
    if (any(p.id == Dunsparce   for p in all_our) and
            any(p.id == Dudunsparce for p in all_our)):
        raw += W_ENGINE_COMPLETE

    # ── N14: Lillie's / Morty's in hand when hand is thin (<4 cards) ─────────
    if (len(hand_cards) < 4 and
            (Lillie_Determination in hand_ids or Mortys_Conviction in hand_ids)):
        raw += W_SMALL_HAND_SUPPORTER

    return max(-1.0, min(1.0, raw / HEURISTIC_NORM))

# ── Greedy action selector ────────────────────────────────────────────────────
# Used for:  (a) opponent turns in search,  (b) sub-selections (non-MAIN),
#            (c) rollout steps.
# Intentionally simple — the MCTS tree handles the important decisions.

def greedy_action(obs: Observation, our_index: int) -> list[int]:
    """
    Assign a quick heuristic score to each option and return the best
    min/max-count selection. Does NOT branch — one choice only.
    """
    state   = obs.current
    select  = obs.select
    context = select.context
    acting  = state.yourIndex  # The player currently making a choice
    ps      = state.players[acting]

    scores: list[float] = []
    for o in select.option:
        score: float = 0.0

        if o.type == OptionType.NUMBER:
            score = float(o.number)

        elif o.type == OptionType.YES:
            score = 1.0

        elif o.type == OptionType.END:
            # In rollout we want to keep playing; attack before ending
            score = -50.0

        elif o.type == OptionType.ATTACK:
            score = 500.0

        elif o.type == OptionType.EVOLVE:
            score = 300.0

        elif o.type == OptionType.ABILITY:
            score = 250.0

        elif o.type == OptionType.PLAY:
            if o.index < len(ps.hand):
                card = ps.hand[o.index]
                data = card_table.get(card.id)
                if data:
                    # Pokémon > Trainer in raw greedy; attack opportunity wins
                    score = 200.0 if getattr(data, "cardType", 1) == 0 else 100.0
                # H16: strongly deprioritise Lillie's Determination when other
                # trainer cards are still in hand (discard should be a last resort).
                if card.id == Lillie_Determination:
                    other_trainers = sum(
                        1 for c in ps.hand
                        if c.id in _TRAINER_IDS and c.id != Lillie_Determination
                    )
                    if other_trainers > 0:
                        score -= 200.0

                # N14: strongly prioritise playing Lillie's or Morty's when hand is thin
                if card.id in (Lillie_Determination, Mortys_Conviction) and len(ps.hand) < 4:
                    score += 200.0

        elif o.type == OptionType.ATTACH:
            if 0 <= o.index < len(ps.hand):
                card = ps.hand[o.index]
                target = get_card(obs, o.inPlayArea, o.inPlayIndex, acting)
                if card.id in TOOL_CARD_IDS:
                    # Hero's Cape: only on Clefairy / Mega Clefable ex — anything else -500
                    if target is not None and target.id == Mega_Clefable_ex:
                        score = 200.0
                    elif target is not None and target.id == Clefairy:
                        score = 100.0
                    else:
                        score = -500.0
                else:
                    # Energy attach
                    if target is not None and target.id in NO_ENERGY_POKEMON_IDS:
                        score = -500.0          # Dudunsparce / Smoochum: never
                    elif target is not None and target.id == Dunsparce:
                        score = 50.0            # Dunsparce: allowed but suboptimal
                    else:
                        score = 150.0
            else:
                score = 50.0

        elif o.type == OptionType.RETREAT:
            score = -50.0

        elif o.type == OptionType.CARD:
            card = get_card(obs, o.area, o.index, o.playerIndex)
            if isinstance(card, Pokemon):
                score = 100.0 + len(card.energies) * 20.0 + card.hp / 20.0
            elif card is not None:
                score = 50.0

        scores.append(score)

    desc = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    count = max(select.minCount, min(select.maxCount, len(desc)))
    return desc[:count]

# ── MCTS data structures ──────────────────────────────────────────────────────

class MCTSChild:
    """Edge in the MCTS tree — stores the action taken and the child node."""
    __slots__ = ("action", "node")

    def __init__(self, action: list[int]) -> None:
        self.action = action          # Option indices selected at the parent node
        self.node: "MCTSNode | None" = None


class MCTSNode:
    """
    Node in the MCTS tree. Always sits at a SelectContext.MAIN decision point
    for our player. Opponent turns and sub-selections are fast-forwarded
    greedily and never become tree nodes.
    """
    __slots__ = (
        "state", "depth", "unknown_cards",
        "visit_count", "total_value",
        "parent", "children", "is_leaf",
    )

    def __init__(
        self,
        state: SearchState,
        depth: int,
        parent: "MCTSNode | None" = None,
        unknown_cards: int = 0,
    ) -> None:
        self.state:         SearchState    = state
        self.depth:         int            = depth
        self.unknown_cards: int            = unknown_cards
        self.visit_count:   int            = 0
        self.total_value:   float          = 0.0
        self.parent:        MCTSNode | None = parent
        self.children:      list[MCTSChild] = []
        self.is_leaf:       bool           = False

    @property
    def q_value(self) -> float:
        return self.total_value / self.visit_count if self.visit_count else 0.0

    def backprop(self, value: float) -> None:
        """Propagate a value up to the root. All nodes are ours → no sign flip."""
        self.visit_count += 1
        self.total_value += value
        if self.parent is not None:
            self.parent.backprop(value)

# ── Fast-forward helper ───────────────────────────────────────────────────────

def _fast_forward(
    state: SearchState,
    our_index: int,
    prev_hand_count: int,
) -> tuple[SearchState, int, bool]:
    """
    After making one of our MAIN selections, greedily resolve all subsequent
    selections (our sub-choices AND opponent turns) until we arrive at our next
    MAIN decision, a terminal state, or an imperfect-information context.

    Returns
    -------
    new_state       : the SearchState at the stopping point
    unknown_drawn   : count of cards our player drew (unknown identity)
    is_imperfect    : True if we stopped because of an unrecognised context
    """
    unknown_drawn = 0
    known         = _known_contexts()

    while True:
        obs  = state.observation
        game = obs.current

        # ── Terminal ─────────────────────────────────────────────────────────
        if game.result >= 0:
            return state, unknown_drawn, False

        context  = obs.select.context
        our_turn = game.yourIndex == our_index

        # ── Draw detection ────────────────────────────────────────────────────
        curr_hand = game.players[our_index].handCount
        if curr_hand > prev_hand_count:
            unknown_drawn    += curr_hand - prev_hand_count
            prev_hand_count   = curr_hand

        # ── Stop: our MAIN turn ───────────────────────────────────────────────
        if our_turn and context == SelectContext.MAIN:
            return state, unknown_drawn, False

        # ── Stop: imperfect information ───────────────────────────────────────
        # (coin flips, unknown contexts — caller will score immediately)
        if context not in known:
            return state, unknown_drawn, True

        # ── Greedy advance ────────────────────────────────────────────────────
        action = greedy_action(obs, our_index)
        state  = search_step(state.searchId, action)


# ── Greedy rollout ────────────────────────────────────────────────────────────

def _greedy_rollout(
    state: SearchState,
    our_index: int,
    steps: int,
) -> float:
    """
    Play out the game greedily for up to `steps` of OUR MAIN-phase selections,
    then score with the heuristic. Returns a float in [-1, 1].
    Used at leaf nodes (depth == MAX_DEPTH) to get a better estimate than
    the raw heuristic applied to the current state.
    """
    unknown_total = 0
    hand_count    = state.observation.current.players[our_index].handCount
    known         = _known_contexts()

    # Guard: cap total iterations to prevent infinite loops in edge cases
    for _ in range(steps * 15):
        obs  = state.observation
        game = obs.current

        # Terminal: exact outcome
        if game.result >= 0:
            if game.result == 2:             return  0.0
            if game.result == our_index:     return  1.0
            return -1.0

        context  = obs.select.context
        our_turn = game.yourIndex == our_index

        # Draw detection
        curr_hand = game.players[our_index].handCount
        if curr_hand > hand_count:
            unknown_total += curr_hand - hand_count
            hand_count     = curr_hand

        # Imperfect info encountered mid-rollout: score the current position
        if context not in known:
            break

        # Decrement step budget only on our MAIN selections
        if our_turn and context == SelectContext.MAIN:
            if steps <= 0:
                break
            steps -= 1

        action = greedy_action(obs, our_index)
        state  = search_step(state.searchId, action)

    return heuristic_score(state.observation, our_index, unknown_total)


# ── MCTS core ─────────────────────────────────────────────────────────────────

def _ucb(parent: MCTSNode, child: MCTSChild) -> float:
    """UCB1 score for a child. Unvisited children return +∞."""
    if child.node is None:
        return float("inf")
    n  = child.node.visit_count
    q  = child.node.q_value
    return q + UCB_C * math.sqrt(math.log(parent.visit_count + 1) / (n + 1))


def _expand(node: MCTSNode, our_index: int) -> None:
    """
    Create one MCTSChild per available MAIN option, pruning energy attachments
    to Dudunsparce/Smoochum. Hero's Cape attaches are pruned to any non-attacker.
    Dunsparce may receive energy (penalised in heuristic, not pruned here).
    """
    obs  = node.state.observation
    ps   = obs.current.players[our_index]
    opts = obs.select.option

    for i, o in enumerate(opts):
        if o.type == OptionType.ATTACH:
            if 0 <= o.index < len(ps.hand):
                card   = ps.hand[o.index]
                target = get_card(obs, o.inPlayArea, o.inPlayIndex, our_index)
                if target is not None:
                    if card.id in TOOL_CARD_IDS:
                        # Hero's Cape: only on Clefairy / Mega Clefable ex
                        if target.id not in _ATTACKER_IDS:
                            continue
                    elif target.id in NO_ENERGY_POKEMON_IDS:
                        # Energy: Dudunsparce and Smoochum are always wrong targets
                        continue
        node.children.append(MCTSChild(action=[i]))


def _evaluate(node: MCTSNode, our_index: int) -> float:
    """Score a leaf node by running a short greedy rollout."""
    return _greedy_rollout(node.state, our_index, ROLLOUT_STEPS)


# ── Game clock ───────────────────────────────────────────────────────────────
# Total game time is 10 minutes (600 s). We use 30 s/turn normally; drop to
# 10 s/turn when less than 60 s remains to preserve endgame moves.

_GAME_BUDGET_S  = 600.0
_BUDGET_NORMAL  = 20.0   # >60 s remaining
_BUDGET_CRUNCH  = 10.0   # ≤60 s remaining
_BUDGET_FINAL   =  3.0   # ≤30 s remaining
_CRUNCH_BELOW_S = 60.0
_FINAL_BELOW_S  = 30.0

_game_start: float | None = None


def _turn_budget() -> float:
    if _game_start is None:
        return _BUDGET_NORMAL
    remaining = max(0.0, _GAME_BUDGET_S - (time.time() - _game_start))
    if remaining <= _FINAL_BELOW_S:
        return _BUDGET_FINAL
    if remaining <= _CRUNCH_BELOW_S:
        return _BUDGET_CRUNCH
    return _BUDGET_NORMAL


def mcts_search(obs_dict: dict, our_index: int, our_deck: list[int]) -> list[int]:
    """
    Run MCTS from the current observation and return the best MAIN-phase action.
    Calls search_begin / search_end internally.
    """
    obs   = to_observation_class(obs_dict)
    game  = obs.current
    us    = game.players[our_index]
    them  = game.players[1 - our_index]

    # Initialise the search tree with randomised deck order to sample draws
    root_search = search_begin(
        obs,
        your_deck       = random.sample(our_deck, us.deckCount),
        your_prize      = random.sample(our_deck, len(us.prize)),
        opponent_deck   = [1] * them.deckCount,           # unknown → placeholder
        opponent_prize  = [1] * len(them.prize),
        opponent_hand   = [1] * them.handCount,
        opponent_active = (
            [None] if them.active and them.active[0] is None else []
        ),
    )

    # Seed the root node with a quick heuristic so UCB has a baseline
    root = MCTSNode(state=root_search, depth=0)
    root.visit_count = 1
    root.total_value = heuristic_score(obs, our_index)
    _expand(root, our_index)

    # ── Main MCTS loop ────────────────────────────────────────────────────────
    deadline = time.time() + _turn_budget()
    for _ in range(MCTS_ITERATIONS):
        if time.time() >= deadline:
            break

        # ── 1. Selection: walk tree by UCB until an unvisited child ───────────
        node = root
        while True:
            if node.is_leaf:
                # Re-evaluate a previously scored leaf to reduce variance
                value = _evaluate(node, our_index)
                node.backprop(value)
                break

            if not node.children:
                # Shouldn't happen at a non-leaf, but safe guard
                break

            best_score = -float("inf")
            best_child: MCTSChild = node.children[0]
            for child in node.children:
                s = _ucb(node, child)
                if s > best_score:
                    best_score = s
                    best_child = child

            if best_child.node is None:
                # ── 2. Expansion ──────────────────────────────────────────────
                # Step into the child by making that MAIN selection
                after_action = search_step(node.state.searchId, best_child.action)
                prev_hand    = node.state.observation.current.players[our_index].handCount

                # Fast-forward: resolve sub-selections / opponent turn greedily
                child_state, unknown_drawn, is_imperfect = _fast_forward(
                    after_action, our_index, prev_hand
                )

                child_game = child_state.observation.current
                is_terminal = child_game.result >= 0
                new_depth   = node.depth + 1

                child_node = MCTSNode(
                    state         = child_state,
                    depth         = new_depth,
                    parent        = node,
                    unknown_cards = node.unknown_cards + unknown_drawn,
                )
                best_child.node = child_node

                # Mark as leaf if: terminal, max depth reached, or imperfect info
                child_node.is_leaf = is_terminal or (new_depth >= MAX_DEPTH) or is_imperfect

                # ── 3. Evaluation ─────────────────────────────────────────────
                if is_terminal:
                    r     = child_game.result
                    value = 0.0 if r == 2 else (1.0 if r == our_index else -1.0)
                elif is_imperfect:
                    # Coin flip / unknown context → score current position directly
                    value = heuristic_score(
                        child_state.observation, our_index, child_node.unknown_cards
                    )
                else:
                    # Normal leaf at max depth → greedy rollout
                    value = _evaluate(child_node, our_index)

                # ── 4. Backpropagation ────────────────────────────────────────
                child_node.visit_count = 1
                child_node.total_value = value
                node.backprop(value)

                # Pre-expand internal nodes for future iterations
                if not child_node.is_leaf:
                    _expand(child_node, our_index)
                break

            else:
                # Descend to the best existing child
                node = best_child.node

    # ── Pick the most-visited root child ──────────────────────────────────────
    visited = [c for c in root.children if c.node is not None]
    if not visited:
        return [0]
    best = max(visited, key=lambda c: c.node.visit_count)
    return best.action


# ── Agent entry point ─────────────────────────────────────────────────────────

def agent(obs_dict: dict) -> list[int]:
    """
    Required entry point. Returns the deck on the first call (obs.select is
    None), then routes all MAIN-context decisions through MCTS and everything
    else through the greedy policy.
    """
    global _game_start
    obs = to_observation_class(obs_dict)

    # First call: return the deck
    if obs.select is None:
        return MY_DECK

    # Start the game clock on the first real decision
    if _game_start is None:
        _game_start = time.time()

    state   = obs.current
    context = obs.select.context
    our_idx = state.yourIndex

    if context == SelectContext.MAIN:
        try:
            return mcts_search(obs_dict, our_idx, MY_DECK)
        finally:
            search_end()

    # All non-MAIN selections (sub-choices, opponent setup, etc.) → greedy
    return greedy_action(obs, our_idx)
