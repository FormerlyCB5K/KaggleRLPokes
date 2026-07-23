"""Bridges `live_state.RawPokemon` (spec 11's per-Pokemon input shape) and
`static_template.PokemonStatic` (spec 11a's tag block) into `stat_bakes.BoardPokemon`/
`Board` queries, so `encoder.py` can compute real `attack_damage`/`attack_hits_opponent`/
`attacks_survivable` instead of the zero placeholder.

Kept separate from `live_state.py` (which only needs one Pokemon's own fields, no board
context) and from `stat_bakes.py` (which knows nothing about tag blocks or card_data) --
this module is the one place that needs all three together.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import card_data
from .live_state import RawPokemon
from .pokemon_tag_catalog import CONTENT_TAGS, DAMAGE_CAP
from .stat_bakes import Board, BoardPokemon, effective_damage, effective_weakness
from .static_template import PokemonStatic, TAG_BLOCK_WIDTH_ATTACK
from .types import TYPES, WR_TYPES

_DAMAGE_TAG_OFFSET = CONTENT_TAGS.index("DAMAGE")


def raw_pokemon_to_board_pokemon(raw: RawPokemon) -> BoardPokemon:
    """`is_tera` is left at its `BoardPokemon` default (`False`) -- not tracked on
    `RawPokemon` and not needed by any currently-defined `damage_dealt_delta`/
    `damage_taken_delta`/`weakness_set` bake (only `Nighttime Mine`'s `attack_cost_delta`
    checks it, out of this module's scope -- see the wiring plan's "Explicitly out of
    scope")."""
    static = card_data.get_card_static(raw.card_id)
    energy_types = tuple(
        s.type_name
        for card_id in raw.energy_cards
        if (s := card_data.get_card_static(card_id)) is not None and s.type_name
    )
    return BoardPokemon(
        card_id=raw.card_id,
        name=static.name if static else "",
        types=(static.type_name,) if static and static.type_name else (),
        is_active=raw.is_active,
        is_basic=raw.is_basic,
        has_rule_box=bool(static and static.rule_status != "none"),
        energy_types_attached=energy_types,
        attached_tool_id=raw.tool_card_id,
    )


def _onehot_to_type(onehot: list[float], type_names: tuple[str, ...]) -> str | None:
    for name, value in zip(type_names, onehot):
        if value == 1.0:
            return name
    return None


@dataclass(frozen=True)
class GameBoardContext:
    """One full board snapshot's worth of context, built once per `build_observation()`
    call. `our_side`/`opponent_side` are every `BoardPokemon` currently in play on each
    side (active + bench)."""
    our_side: tuple[BoardPokemon, ...]
    opponent_side: tuple[BoardPokemon, ...]
    stadium_card_id: int | None = None
    tools_suppressed: bool = False
    abilities_suppressed_types: tuple[str, ...] = ()

    def board_for(self, holder: BoardPokemon, attacker: BoardPokemon | None, holder_is_ours: bool) -> Board:
        own = self.our_side if holder_is_ours else self.opponent_side
        opponent = self.opponent_side if holder_is_ours else self.our_side
        return Board(
            holder=holder, attacker=attacker, own_side=own, opponent_side=opponent,
            stadium_card_id=self.stadium_card_id, tools_suppressed=self.tools_suppressed,
            abilities_suppressed_types=self.abilities_suppressed_types,
        )


def effective_weakness_for(
    pokemon: BoardPokemon, is_ours: bool, ctx: GameBoardContext, static_weakness: str | None
) -> str | None:
    return effective_weakness(ctx.board_for(pokemon, None, is_ours), static_weakness)


def raw_attack_damage_for(
    attacker_static: PokemonStatic,
    attacker_bp: BoardPokemon,
    attacker_is_ours: bool,
    defender_static: PokemonStatic | None,
    defender_bp: BoardPokemon | None,
    ctx: GameBoardContext,
) -> list[float]:
    """Effective, un-normalized damage for both of `attacker_static`'s attack slots
    against `defender_bp` as the reference target. `[0.0, 0.0]` if there's no defender (no
    opposing active to reference) -- mirrors the old encoder's `hits_opp = 0.0` convention
    for an absent opponent active. Uses the *live* weakness (folding `weakness_set` bakes
    via `effective_weakness_for`, spec 11's already-locked aura-override requirement), not
    just the printed value -- resistance never needs this (spec 14: no bake mechanism
    exists for it)."""
    if defender_static is None or defender_bp is None:
        return [0.0, 0.0]

    attacker_board = ctx.board_for(attacker_bp, attacker_bp, attacker_is_ours)
    target_board = ctx.board_for(defender_bp, attacker_bp, not attacker_is_ours)
    attacker_type = _onehot_to_type(attacker_static.type_onehot, TYPES)
    static_weakness = _onehot_to_type(defender_static.weakness_onehot, WR_TYPES)
    defender_weakness = effective_weakness_for(defender_bp, not attacker_is_ours, ctx, static_weakness)
    defender_resistance = _onehot_to_type(defender_static.resistance_onehot, WR_TYPES)

    result = []
    for slot in range(2):
        offset = slot * TAG_BLOCK_WIDTH_ATTACK + _DAMAGE_TAG_OFFSET
        raw_damage = attacker_static.tag_block[offset] * DAMAGE_CAP
        result.append(effective_damage(
            raw_damage, attacker_type, attacker_board, target_board,
            defender_weakness, defender_resistance,
        ))
    return result


def attack_damage_for(
    attacker_static: PokemonStatic,
    attacker_bp: BoardPokemon,
    attacker_is_ours: bool,
    defender_static: PokemonStatic | None,
    defender_bp: BoardPokemon | None,
    ctx: GameBoardContext,
) -> list[float]:
    """Normalized (`/ DAMAGE_CAP`, clipped to 1.0) version of `raw_attack_damage_for`, for
    the observation's `attack_damage` field."""
    return [min(v / DAMAGE_CAP, 1.0) for v in raw_attack_damage_for(
        attacker_static, attacker_bp, attacker_is_ours, defender_static, defender_bp, ctx,
    )]
