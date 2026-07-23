"""Spec 14: effect baking for retreat cost, weakness, attack cost, and flat damage deltas.

HP and resistance are deliberately absent -- spec 14 proved from the engine source that HP
is always already-effective in the observation (no bake needed, ever) and resistance can
never change dynamically in this engine (no bake possible, ever). Only the 12 locked
candidates below exist; anything outside them is out of this pass's scope (see spec 14's
"Explicitly excluded" section) and gets no bake.

This module defines the data (the `BAKES` table) and the predicate/folding functions. It
does not wire to a live game engine -- `BoardPokemon`/`Board` below are a minimal context
shape sufficient to unit-test the folding logic; connecting them to real engine JSON
(`ToJson.h`'s `PokemonJson`/`Current` shape) is implementation work for whoever wires the
live encoder, not decided here.

**Source vs. target.** Every modifier here is evaluated once per *target* Pokemon (the one
whose retreat/weakness/damage is being computed, bound to `Board.holder`). For a
self-scoped effect (Air Balloon, Brave Bangle, ...), the source and target are the same
Pokemon. For a team/board-scoped effect (Latias ex's own-team retreat reduction, Lillie's
Clefairy ex's opponent-side weakness override, ...), the source (whoever prints the
ability/holds the tool) can be a *different* Pokemon from the target. `source_present`
below scans the correct roster for the source based on the modifier's own `scope`, rather
than assuming `Board.holder` is always both.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal

Stat = Literal[
    "retreat_delta", "retreat_set",
    "weakness_set",
    "attack_cost_delta",
    "damage_dealt_delta", "damage_taken_delta",
]
Scope = Literal["self", "own_team", "opponent_side", "all", "all_active"]


@dataclass(frozen=True)
class BoardPokemon:
    card_id: int
    name: str
    types: tuple[str, ...] = ()
    is_active: bool = False
    is_basic: bool = False
    has_rule_box: bool = False
    is_tera: bool = False
    energy_types_attached: tuple[str, ...] = ()
    attached_tool_id: int | None = None


@dataclass(frozen=True)
class Board:
    """Context for computing one target Pokemon's effective stats. `own_side`/
    `opponent_side` are relative to `holder` (the target), and include `holder` itself
    where applicable -- callers should put `holder` in whichever roster matches its own
    side. `attacker` is only meaningful for damage_dealt/damage_taken folding."""
    holder: BoardPokemon
    attacker: BoardPokemon | None
    own_side: tuple[BoardPokemon, ...]
    opponent_side: tuple[BoardPokemon, ...]
    stadium_card_id: int | None = None
    tools_suppressed: bool = False  # Jamming Tower in play
    abilities_suppressed_types: tuple[str, ...] = ()  # Team Rocket's Watchtower's scope


Predicate = Callable[["Board"], bool]
PokemonPredicate = Callable[[BoardPokemon], bool]


def is_basic(board: Board) -> bool:
    return board.holder.is_basic


def holder_is_type(type_name: str) -> Predicate:
    return lambda board: type_name in board.holder.types


def holder_is_tera(board: Board) -> bool:
    return board.holder.is_tera


def holder_name_prefix(prefix: str) -> Predicate:
    return lambda board: board.holder.name.startswith(prefix)


def attacker_name_prefix(prefix: str) -> Predicate:
    return lambda board: board.attacker is not None and board.attacker.name.startswith(prefix)


def defender_has_rule_box(board: Board) -> bool:
    """The Pokemon *taking* the damage has a rule box -- symmetric counterpart to the old
    registry's attacker-only `attacker_has_rule_box` (spec 14's "New condition predicates
    needed" note). For a damage_dealt_delta bake, the "defender" is the attack's target,
    i.e. `board.holder` from the perspective of whoever is about to be hit."""
    return board.holder.has_rule_box


def attacker_has_energy_type(type_name: str) -> Predicate:
    return lambda board: (
        board.attacker is not None and type_name in board.attacker.energy_types_attached
    )


def own_side_has(predicate: PokemonPredicate) -> Predicate:
    return lambda board: any(predicate(p) for p in board.own_side)


def is_mega_ex_of_type(type_name: str) -> PokemonPredicate:
    return lambda p: p.has_rule_box and type_name in p.types  # "Mega ex" folded into has_rule_box + type here


def _and(*predicates: Predicate) -> Predicate:
    return lambda board: all(p(board) for p in predicates)


def always(board: Board) -> bool:
    """No further activation gate beyond the source being present and unsuppressed."""
    return True


@dataclass(frozen=True)
class Modifier:
    stat: Stat
    value: float | str  # str only for weakness_set (a type name); numeric otherwise
    scope: Scope
    condition: Predicate
    ordering: Literal["pre_wr", "post_wr"] = "pre_wr"  # only meaningful for damage stats
    target_restriction: Predicate | None = None  # gates whether this applies to a given attack
    source_requirement: PokemonPredicate = lambda p: True  # checked against the CANDIDATE source


@dataclass(frozen=True)
class Bake:
    card_id: int
    name: str
    kind: Literal["tool", "stadium", "ability"]
    mods: tuple[Modifier, ...] = field(default_factory=tuple)


def _is_source(bake: Bake, candidate: BoardPokemon) -> bool:
    if bake.kind == "ability":
        return candidate.card_id == bake.card_id
    if bake.kind == "tool":
        return candidate.attached_tool_id == bake.card_id
    raise AssertionError(f"_is_source only applies to tool/ability bakes, got {bake.kind!r}")


def source_present(bake: Bake, mod: Modifier) -> Predicate:
    """Is `bake`'s card actually the effect source for this target, scanning whichever
    roster `mod.scope` implies rather than assuming the target IS the source? Suppression
    (Jamming Tower / Team Rocket's Watchtower) is checked against the *candidate source*
    Pokemon, not the target -- a suppressed source is no source at all, regardless of who
    it would have affected."""
    def check(board: Board) -> bool:
        if bake.kind == "stadium":
            return board.stadium_card_id == bake.card_id

        def matches(p: BoardPokemon) -> bool:
            if not _is_source(bake, p):
                return False
            if bake.kind == "tool" and board.tools_suppressed:
                return False
            if bake.kind == "ability" and any(t in board.abilities_suppressed_types for t in p.types):
                return False
            return mod.source_requirement(p)

        if mod.scope == "self":
            return matches(board.holder)
        if mod.scope == "own_team":
            return any(matches(p) for p in board.own_side)
        if mod.scope == "opponent_side":
            return any(matches(p) for p in board.opponent_side)
        if mod.scope in ("all", "all_active"):
            return any(matches(p) for p in (*board.own_side, *board.opponent_side))
        raise AssertionError(f"unknown scope: {mod.scope!r}")
    return check


# Card IDs per Decks/Deck-Builder/EN_Card_Data.csv / meta-card-registry.
BAKES: dict[int, Bake] = {
    1174: Bake(1174, "Air Balloon", "tool", (
        Modifier("retreat_delta", -2, "self", always),
    )),
    1166: Bake(1166, "Gravity Gemstone", "tool", (
        Modifier("retreat_delta", 1, "all_active", always,
                  source_requirement=lambda p: p.is_active),
    )),
    1175: Bake(1175, "Brave Bangle", "tool", (
        Modifier("damage_dealt_delta", 30, "self", always,
                  target_restriction=defender_has_rule_box,
                  source_requirement=lambda p: not p.has_rule_box),
    )),
    1158: Bake(1158, "Maximum Belt", "tool", (
        Modifier("damage_dealt_delta", 50, "self", always, target_restriction=defender_has_rule_box),
    )),
    1266: Bake(1266, "Nighttime Mine", "stadium", (
        Modifier("attack_cost_delta", 1, "all", holder_is_tera),
    )),
    1244: Bake(1244, "Full Metal Lab", "stadium", (
        Modifier("damage_taken_delta", -30, "all", holder_is_type("Metal"), ordering="post_wr"),
    )),
    1253: Bake(1253, "N's Castle", "stadium", (
        Modifier("retreat_set", 0, "all", holder_name_prefix("N's")),
    )),
    184: Bake(184, "Latias ex", "ability", (
        Modifier("retreat_set", 0, "own_team", is_basic),
    )),
    272: Bake(272, "Lillie's Clefairy ex", "ability", (
        Modifier("weakness_set", "Psychic", "opponent_side", holder_is_type("Dragon")),
    )),
    342: Bake(342, "Cynthia's Roserade", "ability", (
        Modifier("damage_dealt_delta", 30, "own_team", attacker_name_prefix("Cynthia's")),
    )),
    116: Bake(116, "Okidogi", "ability", (
        Modifier("damage_dealt_delta", 100, "self", attacker_has_energy_type("Darkness")),
    )),
    829: Bake(829, "Seviper", "ability", (
        Modifier("damage_dealt_delta", 120, "self", own_side_has(is_mega_ex_of_type("Darkness"))),
    )),
}


def active_modifiers(board: Board) -> list[Modifier]:
    """All modifiers from any bake whose source card is actually present, unsuppressed,
    and satisfying its own `source_requirement` for this target (`source_present` handles
    all three) -- *and* whose own activation `condition` holds against the target."""
    result = []
    for bake in BAKES.values():
        for mod in bake.mods:
            if source_present(bake, mod)(board) and mod.condition(board):
                result.append(mod)
    return result


# ---------------------------------------------------------------------------
# Fold functions -- combine `active_modifiers()`'s raw candidates into final effective
# numbers. `active_modifiers()` itself never evaluates `target_restriction` (confirmed
# above: it only checks `source_present` + `condition`), so every function here that needs
# it takes two `Board`s -- one framed with `holder` = whoever we're asking "what's active
# for you", a second framed with `holder` = the actual target, used only to check
# `target_restriction` against that specific Pokemon (e.g. Brave Bangle's "vs a rule-box
# defender" only reads as true when checked against the real opponent, not the attacker).
#
# Generalizes `Ceruledge-RL/stat_bakes.py`'s `effective_damage`/`damage_dealt_bonus`
# (hardcoded to Fire/Fighting only) to all 10 types via the caller's own weakness/
# resistance one-hots, rather than inventing a new formula.
# ---------------------------------------------------------------------------


def damage_dealt_bonus(attacker_board: Board, target_board: Board) -> float:
    """Sum of `damage_dealt_delta` modifiers active for `attacker_board.holder` (the
    attacker), dropping any whose `target_restriction` fails against
    `target_board.holder` (the actual defender). Only `ordering="pre_wr"` mods are summed
    here -- no current bake declares a `damage_dealt_delta` with `ordering="post_wr"`; if
    one is ever added, this needs a second post-multiplier pass, same as
    `damage_taken_adjustment` already supports via its own `ordering` parameter."""
    total = 0.0
    for mod in active_modifiers(attacker_board):
        if mod.stat != "damage_dealt_delta" or mod.ordering != "pre_wr":
            continue
        if mod.target_restriction is not None and not mod.target_restriction(target_board):
            continue
        total += mod.value
    return total


def damage_taken_adjustment(defender_board: Board, ordering: Literal["pre_wr", "post_wr"]) -> float:
    """Sum of `damage_taken_delta` modifiers active for `defender_board.holder` (the
    defender) matching the given `ordering`."""
    return sum(
        mod.value for mod in active_modifiers(defender_board)
        if mod.stat == "damage_taken_delta" and mod.ordering == ordering
    )


def effective_weakness(pokemon_board: Board, static_weakness: str | None) -> str | None:
    """Live weakness type for `pokemon_board.holder`, folding any active `weakness_set`
    override (e.g. Lillie's Clefairy ex) over the printed value. Only one `weakness_set`
    bake exists in `BAKES` today, so there's no real multiple-setter conflict to resolve
    yet -- takes the first match if that ever changes, rather than inventing an ordering
    with no real case to validate it against."""
    sets = [mod.value for mod in active_modifiers(pokemon_board) if mod.stat == "weakness_set"]
    return sets[0] if sets else static_weakness


def effective_damage(
    base_damage: float,
    attacker_type: str | None,
    attacker_board: Board,
    target_board: Board,
    defender_weakness: str | None,
    defender_resistance: str | None,
) -> float:
    """Effective damage `attacker_board.holder` deals to `target_board.holder`: base +
    pre-multiplier damage_dealt/damage_taken deltas, x2 Weakness / -30 Resistance for
    `attacker_type` against the defender's live weakness/resistance, then post-multiplier
    damage_taken deltas (e.g. Full Metal Lab's -30, `ordering="post_wr"`). Mirrors
    `Ceruledge-RL/stat_bakes.py`'s `effective_damage` formula, generalized from
    Fire/Fighting-only to any of the 10 types."""
    d = base_damage
    d += damage_dealt_bonus(attacker_board, target_board)
    d += damage_taken_adjustment(target_board, "pre_wr")
    if attacker_type is not None and attacker_type == defender_weakness:
        d *= 2.0
    if attacker_type is not None and attacker_type == defender_resistance:
        d -= 30.0
    d += damage_taken_adjustment(target_board, "post_wr")
    return max(0.0, d)
