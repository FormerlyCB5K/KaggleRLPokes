"""Spec 16a: deck-agnostic action classification.

Turns `obs.select.option` into (a) a Stage 1 verb, for MAIN-context decisions, and (b) a
list of Stage 2 candidates -- for *any* deck, using only `cg_download.api`'s own
`OptionType`/`AreaType`/`SelectContext` vocabulary. No card ID is ever hardcoded here.

Candidate shape is a function of `option.type`, never of `SelectContext` -- see spec 16a's
"Behavior" section for why this one resolver covers every `SelectContext` the engine
defines (48+ as of this session), not just the handful `Ceruledge-RL/actions.py`
special-cased.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)  # cg_download
sys.path.insert(0, _IL_ROOT)    # observation

from cg_download.api import AreaType, Observation, Option, OptionType  # noqa: E402
from observation.types import BOARD_ROLES, N_ATTACK_ROWS, ZONE_ROLES  # noqa: E402

# `SelectType.MAIN`'s own docstring in cg_download/api.py lists exactly these 8
# OptionTypes as MAIN-context choices.
VERBS = (
    OptionType.PLAY, OptionType.ATTACH, OptionType.EVOLVE, OptionType.ABILITY,
    OptionType.DISCARD, OptionType.RETREAT, OptionType.ATTACK, OptionType.END,
)
VERB_INDEX = {v: i for i, v in enumerate(VERBS)}
N_VERBS = len(VERBS)  # 8


def build_action_map(obs: Observation) -> dict[OptionType, list[int]]:
    """MAIN-context only: group legal option indices by verb. No `_CARD_TO_ACTION`
    lookup, no per-card branching -- compare to `Ceruledge-RL/actions.py`'s 19-action
    hardcoded version."""
    action_map: dict[OptionType, list[int]] = {}
    for i, o in enumerate(obs.select.option):
        if o.type in VERB_INDEX:
            action_map.setdefault(o.type, []).append(i)
    return action_map


@dataclass(frozen=True)
class BoardRef:
    """A resolved board position, in the same role vocabulary `packing.py`/`encoder.py`
    use. `slot` is the position within that role's word list (always 0 for *_active)."""
    role: str  # "our_active" | "our_bench" | "opponent_active" | "opponent_bench"
    slot: int


@dataclass(frozen=True)
class Candidate:
    """Enough structure for the model (16b) to build an embedding -- this module only
    resolves *which* card/board-slot/attack-slot/literal each candidate refers to.
    `zone_role` names which of `GameState`'s zone-card arrays `card_id` should be looked
    up in (16b's `layout.find_zone_word_index`) -- `None` when the card lives somewhere
    `GameState` doesn't model at all (e.g. the opponent's hand/deck, per spec 15's own
    documented limitation), in which case the model falls back to a zero embedding.
    `occurrence` disambiguates duplicate copies of the same `card_id` within one zone
    (e.g. two Fire Energy in hand): it's how many same-`card_id` items precede this one
    in the zone's raw (pre-sort) order, which -- since `build_zone_array`'s sort is
    stable -- is exactly the same index among the sorted zone words too."""
    option_index: int
    card_id: int | None = None
    zone_role: str | None = None
    occurrence: int = 0
    board_ref: BoardRef | None = None
    attack_slot: int | None = None
    literal: float | None = None
    target: "Candidate | None" = None  # compound ATTACH/EVOLVE: the target half


def _zone_role_for(area: AreaType | None, is_ours: bool) -> str | None:
    if area == AreaType.HAND:
        role = "our_hand" if is_ours else None  # opponent hand unmodeled (spec 15)
    elif area == AreaType.DISCARD:
        role = "our_discard" if is_ours else "opponent_discard"
    elif area == AreaType.DECK:
        role = "our_deck" if is_ours else None  # opponent deck unmodeled
    elif area == AreaType.PRIZE:
        role = "our_prizes" if is_ours else None  # opponent prizes unmodeled
    else:
        role = None  # STADIUM/LOOKING: not one of GameState's persistent zone arrays
    assert role is None or role in ZONE_ROLES, f"unrecognized zone role: {role!r}"
    return role


def _occurrence_before(container, index: int | None, card_id: int | None) -> int:
    """How many items with the same `card_id` appear before `index` in `container`
    (a raw, pre-sort engine list) -- see `Candidate.occurrence`'s docstring."""
    if index is None or card_id is None:
        return 0
    return sum(1 for c in container[:index] if getattr(c, "id", None) == card_id)


def _bench_position(bench, index: int | None) -> int:
    """Position among non-None bench pokes -- matches `live_adapter._board_states`'s own
    ordering exactly (it only appends entries for occupied slots), since `option.index`
    is a raw index into the engine's own bench list (which may have empty-slot gaps)."""
    if index is None:
        return 0
    bench = bench or ()
    return sum(1 for p in bench[:index] if p is not None)


def _resolve_board_ref(
    obs: Observation, our_idx: int, area: AreaType | None, index: int | None,
    player_idx: int | None,
) -> BoardRef | None:
    if area not in (AreaType.ACTIVE, AreaType.BENCH):
        return None
    side = our_idx if player_idx is None else player_idx
    is_ours = side == our_idx
    ps = obs.current.players[side]
    if area == AreaType.ACTIVE:
        role = "our_active" if is_ours else "opponent_active"
        ref = BoardRef(role=role, slot=0)
    else:
        role = "our_bench" if is_ours else "opponent_bench"
        ref = BoardRef(role=role, slot=_bench_position(ps.bench, index))
    assert ref.role in BOARD_ROLES, f"unrecognized board role: {ref.role!r}"
    return ref


def _resolve_card_id(
    obs: Observation, our_idx: int, area: AreaType | None, index: int | None,
    player_idx: int | None,
) -> tuple[int | None, int]:
    """Returns (card_id, occurrence) -- occurrence per `Candidate.occurrence`'s docstring,
    computed against whichever raw container the card was actually found in."""
    if index is None:
        return None, 0
    if area == AreaType.STADIUM:
        st = obs.current.stadium or ()
        card_id = st[index].id if index < len(st) else None
        return card_id, _occurrence_before(st, index, card_id)
    if area == AreaType.LOOKING:
        looking = obs.current.looking or ()
        card = looking[index] if index < len(looking) else None
        card_id = card.id if card is not None else None
        return card_id, _occurrence_before([c for c in looking if c is not None], index, card_id)
    if area == AreaType.DECK:
        deck = obs.select.deck or ()
        card_id = deck[index].id if index < len(deck) else None
        return card_id, _occurrence_before(deck, index, card_id)
    if area is None:
        return None, 0
    side = our_idx if player_idx is None else player_idx
    ps = obs.current.players[side]
    if area == AreaType.HAND:
        h = ps.hand or ()
        card_id = h[index].id if index < len(h) else None
        return card_id, _occurrence_before(h, index, card_id)
    if area == AreaType.DISCARD:
        d = ps.discard or ()
        card_id = d[index].id if index < len(d) else None
        return card_id, _occurrence_before(d, index, card_id)
    if area == AreaType.PRIZE:
        pr = ps.prize or ()
        card = pr[index] if index < len(pr) else None
        card_id = card.id if card is not None else None
        return card_id, _occurrence_before([c for c in pr if c is not None], index, card_id)
    # ACTIVE/BENCH/ENERGY/TOOL/PRE_EVOLUTION/PLAYER: not a plain card reference here --
    # ACTIVE/BENCH resolve via _resolve_board_ref instead; the rest are rare edge cases
    # left unresolved (candidate falls back to a zero embedding in 16b) per this spec's
    # explicitly deprioritized precision.
    return None, 0


def _resolve_pokemon_object(
    obs: Observation, our_idx: int, area: AreaType | None, index: int | None,
    player_idx: int | None,
):
    """For TOOL_CARD/ENERGY_CARD/ENERGY: area/index/playerIndex locate the *Pokemon*, not
    the card directly -- toolIndex/energyIndex then index into its attachments."""
    if index is None or area not in (AreaType.ACTIVE, AreaType.BENCH):
        return None
    side = our_idx if player_idx is None else player_idx
    ps = obs.current.players[side]
    if area == AreaType.ACTIVE:
        active = ps.active or ()
        return active[index] if index < len(active) else None
    bench = ps.bench or ()
    return bench[index] if index < len(bench) else None


def _find_in_own_zones(obs: Observation, our_idx: int, card_id: int | None) -> tuple[str | None, int]:
    """Best-effort resolution for candidates that carry only a bare `card_id` with no
    `area` telling us where it lives (currently just SKILL). Tries our own always-fully-
    observed zones in a fixed order; returns (None, 0) if not found in any of them --
    still a real, documented limitation (the card may live somewhere GameState doesn't
    model, e.g. the opponent's hand), but strictly better than never trying at all."""
    if card_id is None:
        return None, 0
    ps = obs.current.players[our_idx]
    for role, container in (("our_hand", ps.hand or ()), ("our_discard", ps.discard or ())):
        for idx, c in enumerate(container):
            if c.id == card_id:
                return role, _occurrence_before(container, idx, card_id)
    return None, 0


def _classify_one(obs: Observation, our_idx: int, i: int, o: Option) -> Candidate:
    t = o.type
    if t == OptionType.NUMBER:
        return Candidate(option_index=i, literal=float(o.number) if o.number is not None else 0.0)
    if t in (OptionType.YES, OptionType.NO):
        return Candidate(option_index=i, literal=1.0 if t == OptionType.YES else 0.0)
    if t == OptionType.SPECIAL_CONDITION:
        val = float(o.specialConditionType) if o.specialConditionType is not None else 0.0
        return Candidate(option_index=i, literal=val)
    if t == OptionType.ATTACK:
        return Candidate(option_index=i)  # attack_slot assigned in classify_candidates
    if t == OptionType.PLAY:
        # PLAY's wire format carries only `index` -- no `area`/`playerIndex` (confirmed
        # against real engine data and cg_download.api's own OptionType docstring:
        # "index (int): Index within the hand"). It is NOT one of the area/index/
        # playerIndex-documented option types (CARD/DISCARD/etc.) and must never be
        # routed through _resolve_card_id, which short-circuits to None the instant
        # area is None -- that silently made every PLAY candidate unresolvable.
        hand = obs.current.players[our_idx].hand or ()
        card_id = hand[o.index].id if o.index is not None and o.index < len(hand) else None
        occurrence = _occurrence_before(hand, o.index, card_id)
        return Candidate(option_index=i, card_id=card_id, zone_role="our_hand", occurrence=occurrence)
    if t in (OptionType.TOOL_CARD, OptionType.ENERGY_CARD, OptionType.ENERGY):
        poke = _resolve_pokemon_object(obs, our_idx, o.area, o.index, o.playerIndex)
        card_id = None
        if poke is not None:
            if t == OptionType.TOOL_CARD and poke.tools and o.toolIndex is not None \
                    and o.toolIndex < len(poke.tools):
                card_id = poke.tools[o.toolIndex].id
            elif t == OptionType.ENERGY_CARD and poke.energyCards and o.energyIndex is not None \
                    and o.energyIndex < len(poke.energyCards):
                card_id = poke.energyCards[o.energyIndex].id
            # ENERGY (positional, per-unit -- no single card identity): no card_id, but
            # the owning Pokemon (board_ref) is still real signal, not nothing.
        board_ref = _resolve_board_ref(obs, our_idx, o.area, o.index, o.playerIndex)
        return Candidate(option_index=i, card_id=card_id, board_ref=board_ref)
    if t == OptionType.SKILL:
        zone_role, occurrence = _find_in_own_zones(obs, our_idx, o.cardId)
        return Candidate(option_index=i, card_id=o.cardId, zone_role=zone_role, occurrence=occurrence)
    if t in (OptionType.DISCARD, OptionType.RETREAT, OptionType.ABILITY, OptionType.CARD):
        card_id, occurrence = _resolve_card_id(obs, our_idx, o.area, o.index, o.playerIndex)
        board_ref = _resolve_board_ref(obs, our_idx, o.area, o.index, o.playerIndex)
        side = our_idx if o.playerIndex is None else o.playerIndex
        zone_role = _zone_role_for(o.area, side == our_idx)
        return Candidate(
            option_index=i, card_id=card_id, zone_role=zone_role, occurrence=occurrence,
            board_ref=board_ref,
        )
    if t in (OptionType.ATTACH, OptionType.EVOLVE):
        card_id, occurrence = _resolve_card_id(obs, our_idx, o.area, o.index, o.playerIndex)
        zone_role = _zone_role_for(o.area, True)  # card side is always ours (hand)
        # Target is always the acting player's own board -- ATTACH/EVOLVE only ever
        # target your own Pokemon.
        target_ref = _resolve_board_ref(obs, our_idx, o.inPlayArea, o.inPlayIndex, our_idx)
        return Candidate(
            option_index=i, card_id=card_id, zone_role=zone_role, occurrence=occurrence,
            target=Candidate(option_index=i, board_ref=target_ref),
        )
    return Candidate(option_index=i)  # END and anything unrecognized: no data needed


# card_id -> observed attackId values, ascending -- see _attack_slot's docstring.
_ATTACK_ID_ORDER: dict[int, list[int]] = {}


def _attack_slot(card_id: int | None, attack_id: int | None, sibling_ids: list[int]) -> int:
    """`Option.attackId` is NOT a 0/1 slot value on the wire (real values look like 153,
    154 -- confirmed against real engine data) -- mapping it to spec 11a's cheapest-first
    attack row requires knowing the card's OTHER attack(s). Whenever multiple attackIds
    are seen together for one card_id (this decision has >1 legal ATTACK option), their
    relative ascending order is learned and cached, then reused for future decisions
    where only one of that card's attacks happens to be legal. Self-improves as more
    games are seen, with no per-card hardcoding; falls back to slot 0 the first time a
    card_id's attack is ever seen in isolation, since no better information exists yet."""
    if card_id is None or attack_id is None:
        return 0
    known = _ATTACK_ID_ORDER.setdefault(card_id, [])
    for aid in sibling_ids:
        if aid not in known:
            known.append(aid)
    if attack_id not in known:
        known.append(attack_id)
    known.sort()
    return min(known.index(attack_id), N_ATTACK_ROWS - 1)


def classify_candidates(
    obs: Observation, our_idx: int, option_indices: list[int],
) -> list[Candidate]:
    opts = obs.select.option
    out = [_classify_one(obs, our_idx, i, opts[i]) for i in option_indices]

    attack_positions = [pos for pos, i in enumerate(option_indices) if opts[i].type == OptionType.ATTACK]
    if attack_positions:
        active = obs.current.players[our_idx].active
        acting_card_id = active[0].id if active and active[0] is not None else None
        sibling_ids = [
            opts[option_indices[pos]].attackId for pos in attack_positions
            if opts[option_indices[pos]].attackId is not None
        ]
        for pos in attack_positions:
            i = option_indices[pos]
            slot = _attack_slot(acting_card_id, opts[i].attackId, sibling_ids)
            out[pos] = Candidate(option_index=i, attack_slot=slot)
    return out
