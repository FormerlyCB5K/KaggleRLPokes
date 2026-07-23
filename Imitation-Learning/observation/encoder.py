"""Top-level spec 13a assembly: 174 words from a `GameState`.

Wires together `zones.py` (deck/hand/discard/prizes), `static_template.py`/
`trainer_energy_static.py` (identity), and `live_state.py` (per-Pokemon board fields) into
the fixed-length word list spec 13a locks. Board-position role embeddings (our-active/
our-bench/opponent-active/opponent-bench) reuse the mechanism already established in spec
11/SVN v2 -- this module just tags each board word with its role; the embedding table
itself is model code, out of scope here.

`GameState` is this module's own adapter boundary: whoever wires a live engine connection
constructs one of these from `ToJson.h`'s `Current`/`PokemonJson` output. No such adapter
exists yet -- this module and its test construct `GameState` directly.

**`attack_damage`/`attack_hits_opponent`/`attacks_survivable` are real, not placeholders**
(see `board_context.py`): every board Pokemon is converted to a `stat_bakes.BoardPokemon`
once per call, bundled into one `GameBoardContext`, and `DAMAGE`-tag magnitudes are folded
through `stat_bakes.effective_damage` (Weakness x2 / Resistance -30 / `damage_dealt_delta`
/ `damage_taken_delta` bakes) against the relevant reference target(s). `attack_damage`/
`attack_hits_opponent` reference the opposing *active* specifically (only legal target
barring `SNIPE` reach, mirrors `Ceruledge-RL/features.py`'s `opp_active`); `attacks_survivable`
is genuinely pairwise -- each opposing Pokemon's own max damage is computed *against this
specific board slot* (spec 11's locked "max across the whole opposing board" reference,
now respecting target-restricted bonuses like Maximum Belt correctly differing per slot).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from . import live_state
from .board_context import (
    GameBoardContext,
    effective_weakness_for,
    raw_attack_damage_for,
    raw_pokemon_to_board_pokemon,
)
from .live_state import RawPokemon
from .pokemon_tag_catalog import DAMAGE_CAP
from .stat_bakes import BoardPokemon
from .static_template import PokemonStatic, build_pokemon_static
from .trainer_energy_static import TrainerEnergyStatic, build_trainer_energy_static
from .types import (
    BOARD_CAPACITY,
    DECK_CAPACITY,
    DISCARD_CAPACITY,
    GLOBAL_CAPACITY,
    HAND_CAPACITY,
    MAX_BENCH,
    POOL_CAPACITY,
    PRIZE_CAPACITY,
    STADIUM_CAPACITY,
    TOTAL_WORDS,
    WR_TYPES,
    WR_TYPE_INDEX,
)
from .zones import ZoneArray, build_any_static, build_zone_array

# The only two stadiums in `stat_bakes.BAKES` that suppress Tools/Abilities.
_JAMMING_TOWER_ID = 1246
_TEAM_ROCKET_WATCHTOWER_ID = 1256

BoardRole = Literal["our_active", "our_bench", "opponent_active", "opponent_bench"]
WordKind = Literal["zone_card", "board_pokemon", "stadium", "global", "pool", "pad"]


@dataclass(frozen=True)
class BoardPokemonState:
    """One board position's worth of input: a Pokemon (or empty) plus its role."""
    role: BoardRole
    raw: RawPokemon | None  # None -> PAD, this position is empty


@dataclass(frozen=True)
class GameState:
    our_deck: list[int]
    our_hand: list[int]
    our_discard: list[int]
    our_prizes_known: list[int]
    our_prizes_hidden_count: int
    opponent_discard: list[int]
    board: list[BoardPokemonState]  # up to BOARD_CAPACITY entries; missing ones are PAD
    stadium_card_id: int | None = None
    turn_number: int = 0
    supporter_played: bool = False  # this turn -- sourced from the engine's own
    # State.supporterPlayed (live_adapter.py), not re-derived from card identity


@dataclass(frozen=True)
class Word:
    kind: WordKind
    role: str | None
    static: PokemonStatic | TrainerEnergyStatic | None
    live: dict | None
    attention_masked: bool  # PAD -> True; everything else (including UNK) -> False


def _pad_word(kind: WordKind = "pad") -> Word:
    return Word(kind=kind, role=None, static=None, live=None, attention_masked=True)


def _zone_words(zone: ZoneArray, kind: WordKind, role: str) -> list[Word]:
    return [
        Word(
            kind="pad" if slot.kind == "PAD" else kind,
            role=None if slot.kind == "PAD" else role,
            static=slot.static,
            live=None,
            attention_masked=slot.attention_masked,
        )
        for slot in zone.slots
    ]


def _weakness_type(static: PokemonStatic) -> str | None:
    for name, value in zip(WR_TYPES, static.weakness_onehot):
        if value == 1.0:
            return name
    return None


def _overwrite_weakness(static: PokemonStatic, bp: BoardPokemon, is_ours: bool, ctx: GameBoardContext) -> PokemonStatic:
    """Spec 11's already-locked, previously-unwired requirement: a board word's own
    `weakness_onehot` gets overwritten in place when an on-field aura (e.g. Lillie's
    Clefairy ex) changes it live. Zone words never call this -- they keep the pure printed
    value, per spec 11's own scope note."""
    live_weakness = effective_weakness_for(bp, is_ours, ctx, _weakness_type(static))
    if live_weakness == _weakness_type(static):
        return static
    new_onehot = [0.0] * len(WR_TYPES)
    if live_weakness is not None:
        new_onehot[WR_TYPE_INDEX[live_weakness]] = 1.0
    return replace(static, weakness_onehot=new_onehot)


def _board_word(
    entry: BoardPokemonState,
    is_ours: bool,
    opposing_entries: list[BoardPokemonState],
    ctx: GameBoardContext,
) -> Word:
    if entry.raw is None:
        return _pad_word()
    static = build_pokemon_static(entry.raw.card_id)
    bp = raw_pokemon_to_board_pokemon(entry.raw)
    static = _overwrite_weakness(static, bp, is_ours, ctx)

    opposing_active = next((o for o in opposing_entries if o.raw is not None and o.raw.is_active), None)
    opposing_active_static = build_pokemon_static(opposing_active.raw.card_id) if opposing_active else None
    opposing_active_bp = raw_pokemon_to_board_pokemon(opposing_active.raw) if opposing_active else None

    raw_damage_vs_active = raw_attack_damage_for(static, bp, is_ours, opposing_active_static, opposing_active_bp, ctx)
    attack_damage = [min(v / DAMAGE_CAP, 1.0) for v in raw_damage_vs_active]

    opposing_board_max_damage = []
    for opp in opposing_entries:
        if opp.raw is None:
            continue
        opp_static = build_pokemon_static(opp.raw.card_id)
        opp_bp = raw_pokemon_to_board_pokemon(opp.raw)
        opp_raw_damage = raw_attack_damage_for(opp_static, opp_bp, not is_ours, static, bp, ctx)
        opposing_board_max_damage.append(max(opp_raw_damage, default=0))

    live = {
        "hp_curr": live_state.hp_curr(entry.raw),
        "attached_energy_counts": live_state.attached_energy_counts(entry.raw),
        "special_energy_id": live_state.special_energy_id(entry.raw),
        "evolved_from": live_state.evolved_from(entry.raw),
        "new_in_play": live_state.new_in_play(entry.raw),
        "special_conditions": live_state.special_conditions_multihot(entry.raw),
        "attacks_survivable": live_state.attacks_survivable(entry.raw.hp, opposing_board_max_damage),
        "attack_damage": attack_damage,
        "attack_hits_opponent": (
            live_state.attack_hits_opponent(int(max(raw_damage_vs_active, default=0)), opposing_active.raw.hp)
            if opposing_active is not None else 0.0
        ),
    }
    return Word(kind="board_pokemon", role=entry.role, static=static, live=live, attention_masked=False)


def build_observation(state: GameState) -> list[Word]:
    words: list[Word] = []

    deck = build_zone_array(state.our_deck, DECK_CAPACITY)
    words += _zone_words(deck, "zone_card", "our_deck")

    prizes = build_zone_array(state.our_prizes_known, PRIZE_CAPACITY, state.our_prizes_hidden_count)
    words += _zone_words(prizes, "zone_card", "our_prizes")

    hand = build_zone_array(state.our_hand, HAND_CAPACITY)
    words += _zone_words(hand, "zone_card", "our_hand")

    our_discard = build_zone_array(state.our_discard, DISCARD_CAPACITY)
    words += _zone_words(our_discard, "zone_card", "our_discard")

    opp_discard = build_zone_array(state.opponent_discard, DISCARD_CAPACITY)
    words += _zone_words(opp_discard, "zone_card", "opponent_discard")

    board_by_role: dict[BoardRole, list[BoardPokemonState]] = {
        "our_active": [], "our_bench": [], "opponent_active": [], "opponent_bench": [],
    }
    for entry in state.board:
        board_by_role[entry.role].append(entry)

    our_entries = board_by_role["our_active"] + board_by_role["our_bench"]
    opponent_entries = board_by_role["opponent_active"] + board_by_role["opponent_bench"]

    ctx = GameBoardContext(
        our_side=tuple(raw_pokemon_to_board_pokemon(e.raw) for e in our_entries if e.raw is not None),
        opponent_side=tuple(raw_pokemon_to_board_pokemon(e.raw) for e in opponent_entries if e.raw is not None),
        stadium_card_id=state.stadium_card_id,
        tools_suppressed=state.stadium_card_id == _JAMMING_TOWER_ID,
        abilities_suppressed_types=("Colorless",) if state.stadium_card_id == _TEAM_ROCKET_WATCHTOWER_ID else (),
    )

    board_words: list[Word] = []
    for entry in our_entries:
        board_words.append(_board_word(entry, True, opponent_entries, ctx))
    board_words += [_pad_word() for _ in range(1 + MAX_BENCH - len(our_entries))]
    for entry in opponent_entries:
        board_words.append(_board_word(entry, False, our_entries, ctx))
    board_words += [_pad_word() for _ in range(1 + MAX_BENCH - len(opponent_entries))]
    assert len(board_words) == BOARD_CAPACITY
    words += board_words

    if state.stadium_card_id is None:
        words.append(_pad_word())
    else:
        words.append(Word(
            kind="stadium", role=None,
            static=build_any_static(state.stadium_card_id),
            live=None, attention_masked=False,
        ))
    assert STADIUM_CAPACITY == 1

    words.append(Word(
        kind="global", role=None, static=None,
        live={"turn_number": state.turn_number, "supporter_played": state.supporter_played},
        attention_masked=False,
    ))
    assert GLOBAL_CAPACITY == 1

    words.append(Word(kind="pool", role=None, static=None, live=None, attention_masked=False))
    assert POOL_CAPACITY == 1

    assert len(words) == TOTAL_WORDS, f"expected {TOTAL_WORDS} words, got {len(words)}"
    return words
