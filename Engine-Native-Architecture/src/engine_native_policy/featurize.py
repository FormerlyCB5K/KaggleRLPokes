"""Pure featurization from ``cg_download.api.Observation``."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np
from cg_download.api import AreaType

from .features import FeatureFrame
from .spec import (
    ACTION_CAP,
    ATTACK_VOCAB_SIZE,
    CARD_VOCAB_SIZE,
    DAMAGE_COUNTER_CAP,
    DECK_COUNT_CAP,
    DISCARD_COUNT_CAP,
    ENERGY_COUNT_CAP,
    EVOLUTION_DEPTH_CAP,
    HAND_COUNT_CAP,
    HP_CAP,
    LIVE_NUMERIC_WIDTH,
    MATCH_WIDTH,
    OPT_ENTITY_NONE,
    OPTION_NUMERIC_CAP,
    OPTION_NUMERIC_WIDTH,
    PRIZE_COUNT_CAP,
    REMAINING_ENERGY_CAP,
    Role,
    TOOL_COUNT_CAP,
    TURN_CAP,
    OptionKind,
)

_ZERO_NUM = np.zeros(LIVE_NUMERIC_WIDTH, dtype=np.float32)
_SPECIAL_ENERGY_IDS = frozenset(range(9, 21))


def _enum_name(value: Any) -> str:
    if isinstance(value, int):
        try:
            value = AreaType(value)
        except ValueError:
            pass
    name = getattr(value, "name", None)
    if name is not None:
        return str(name)
    return str(value).rsplit(".", 1)[-1].upper()


def _card_id(card: Any | None) -> int:
    return int(getattr(card, "id", 0) or 0) % CARD_VOCAB_SIZE


def _attack_id(value: Any | None) -> int:
    return int(value or 0) % ATTACK_VOCAB_SIZE


def _safe_index(values: Sequence[Any] | None, index: Any | None) -> Any | None:
    if values is None or index is None:
        return None
    i = int(index)
    if i < 0 or i >= len(values):
        return None
    return values[i]


def _area_cards(
    current: Any,
    select: Any,
    owner: int,
    area_name: str,
) -> Sequence[Any] | None:
    players = current.players
    player = players[owner]
    if area_name == "DECK":
        return select.deck
    if area_name == "HAND":
        return player.hand
    if area_name == "DISCARD":
        return player.discard
    if area_name == "ACTIVE":
        return player.active
    if area_name == "BENCH":
        return player.bench
    if area_name == "PRIZE":
        return player.prize
    if area_name == "LOOKING":
        return current.looking
    if area_name == "STADIUM":
        return current.stadium
    return None


def _card_at(
    current: Any,
    select: Any,
    owner: int,
    area: Any | None,
    index: Any | None,
) -> Any | None:
    if area is None:
        return None
    return _safe_index(_area_cards(current, select, owner, _enum_name(area)), index)


def _live_numerics(
    pokemon: Any,
    *,
    is_mine: bool,
    is_active: bool,
    player: Any,
) -> np.ndarray:
    hp = float(getattr(pokemon, "hp", 0) or 0)
    max_hp = float(getattr(pokemon, "maxHp", 0) or 0)
    energies = list(getattr(pokemon, "energies", None) or [])
    tools = list(getattr(pokemon, "tools", None) or [])
    pre_evolution = list(getattr(pokemon, "preEvolution", None) or [])

    typed = np.zeros(12, dtype=np.float32)
    for energy in energies:
        idx = int(energy)
        if 0 <= idx < len(typed):
            typed[idx] += 1.0 / ENERGY_COUNT_CAP

    values = np.asarray(
        [
            float(is_mine),
            float(is_active),
            hp / max_hp if max_hp else 0.0,
            hp / HP_CAP,
            max_hp / HP_CAP,
            (max_hp - hp) / HP_CAP,
            len(energies) / ENERGY_COUNT_CAP,
            len(tools) / TOOL_COUNT_CAP,
            len(pre_evolution) / EVOLUTION_DEPTH_CAP,
            float(bool(getattr(pokemon, "appearThisTurn", False))),
            float(is_active and bool(getattr(player, "poisoned", False))),
            float(is_active and bool(getattr(player, "burned", False))),
            float(is_active and bool(getattr(player, "asleep", False))),
            float(is_active and bool(getattr(player, "paralyzed", False))),
            float(is_active and bool(getattr(player, "confused", False))),
            *typed.tolist(),
        ],
        dtype=np.float32,
    )
    assert values.shape == (LIVE_NUMERIC_WIDTH,)
    return values


def _first_tool_id(pokemon: Any) -> int:
    tools = list(getattr(pokemon, "tools", None) or [])
    return _card_id(tools[0]) if tools else 0


def _first_special_energy_id(pokemon: Any) -> int:
    for card in list(getattr(pokemon, "energyCards", None) or []):
        if int(getattr(card, "id", 0) or 0) in _SPECIAL_ENERGY_IDS:
            return _card_id(card)
    return 0


def _extend_pokemon(
    card_ids: list[int],
    roles: list[int],
    numerics: list[np.ndarray],
    tool_ids: list[int],
    senergy_ids: list[int],
    ent_map: dict[tuple[int, str, int], int],
    pokemon: Any | None,
    *,
    owner: int,
    area_name: str,
    area_index: int,
    role: Role,
    is_mine: bool,
    is_active: bool,
    player: Any,
) -> None:
    if pokemon is None:
        return
    ent_map[(owner, area_name, area_index)] = len(card_ids)
    card_ids.append(_card_id(pokemon))
    roles.append(int(role))
    numerics.append(
        _live_numerics(
            pokemon, is_mine=is_mine, is_active=is_active, player=player
        )
    )
    tool_ids.append(_first_tool_id(pokemon))
    senergy_ids.append(_first_special_energy_id(pokemon))


def _visible_in_play_ids(current: Any, owner: int) -> Iterable[int]:
    player = current.players[owner]
    for pokemon in [*(player.active or []), *(player.bench or [])]:
        if pokemon is None:
            continue
        yield _card_id(pokemon)
        for card in getattr(pokemon, "preEvolution", None) or []:
            yield _card_id(card)
        for card in getattr(pokemon, "energyCards", None) or []:
            yield _card_id(card)
        for card in getattr(pokemon, "tools", None) or []:
            yield _card_id(card)
    for stadium in current.stadium or []:
        if int(getattr(stadium, "playerIndex", owner)) == owner:
            yield _card_id(stadium)


def _deck_features(current: Any, my: int, deck: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    deck_ids = np.asarray(
        [int(card_id) % CARD_VOCAB_SIZE for card_id in deck], dtype=np.int64
    )
    deck_total = Counter(int(card_id) % CARD_VOCAB_SIZE for card_id in deck)
    player = current.players[my]
    hand_count = Counter(_card_id(card) for card in (player.hand or []))
    discard_count = Counter(_card_id(card) for card in (player.discard or []))
    play_count = Counter(_visible_in_play_ids(current, my))

    zone = np.zeros((len(deck_ids), 4), dtype=np.float32)
    for i, card_id in enumerate(deck_ids.tolist()):
        hand = hand_count[card_id]
        discard = discard_count[card_id]
        in_play = play_count[card_id]
        unknown = max(0, deck_total[card_id] - hand - discard - in_play)
        zone[i] = np.asarray(
            [hand / 4.0, discard / 4.0, in_play / 4.0, unknown / 4.0],
            dtype=np.float32,
        )
    return deck_ids, zone


def _resolve_option(
    option: Any,
    current: Any,
    select: Any,
    my: int,
) -> tuple[int, int, int]:
    kind = OptionKind(int(option.type))
    mine = current.players[my]

    if kind == OptionKind.PLAY:
        return _card_id(_safe_index(mine.hand, option.index)), 0, 0
    if kind in (OptionKind.ATTACH, OptionKind.EVOLVE):
        owner = int(option.playerIndex) if option.playerIndex is not None else my
        source = _card_at(current, select, owner, option.area, option.index)
        target = _card_at(
            current, select, my, option.inPlayArea, option.inPlayIndex
        )
        return _card_id(source), _card_id(target), 0
    if kind in (
        OptionKind.CARD,
        OptionKind.TOOL_CARD,
        OptionKind.ENERGY_CARD,
        OptionKind.ENERGY,
        OptionKind.ABILITY,
        OptionKind.DISCARD,
    ):
        owner = int(option.playerIndex) if option.playerIndex is not None else my
        return _card_id(
            _card_at(current, select, owner, option.area, option.index)
        ), 0, 0
    if kind == OptionKind.RETREAT:
        return _card_id(_safe_index(mine.active, 0)), 0, 0
    if kind == OptionKind.ATTACK:
        return (
            _card_id(_safe_index(mine.active, 0)),
            0,
            _attack_id(option.attackId),
        )
    if kind == OptionKind.SKILL:
        return int(option.cardId or 0) % CARD_VOCAB_SIZE, 0, 0
    return 0, 0, 0


def _option_entity(
    option: Any,
    current: Any,
    my: int,
    ent_map: dict[tuple[int, str, int], int],
) -> int:
    kind = OptionKind(int(option.type))
    if kind in (OptionKind.ATTACH, OptionKind.EVOLVE):
        if option.inPlayArea is None or option.inPlayIndex is None:
            return OPT_ENTITY_NONE
        return ent_map.get(
            (my, _enum_name(option.inPlayArea), int(option.inPlayIndex)),
            OPT_ENTITY_NONE,
        )
    if kind in (
        OptionKind.CARD,
        OptionKind.TOOL_CARD,
        OptionKind.ENERGY_CARD,
        OptionKind.ENERGY,
        OptionKind.ABILITY,
        OptionKind.DISCARD,
    ):
        if option.area is None or option.index is None:
            return OPT_ENTITY_NONE
        area_name = _enum_name(option.area)
        if area_name not in ("ACTIVE", "BENCH"):
            return OPT_ENTITY_NONE
        owner = int(option.playerIndex) if option.playerIndex is not None else my
        return ent_map.get((owner, area_name, int(option.index)), OPT_ENTITY_NONE)
    if kind in (OptionKind.RETREAT, OptionKind.ATTACK):
        return ent_map.get((my, "ACTIVE", 0), OPT_ENTITY_NONE)
    return OPT_ENTITY_NONE


def _global_features(current: Any, select: Any, my: int) -> np.ndarray:
    opponent = 1 - my
    mine = current.players[my]
    theirs = current.players[opponent]
    values = np.asarray(
        [
            float(current.turn) / TURN_CAP,
            float(current.turnActionCount) / ACTION_CAP,
            float(current.firstPlayer == my),
            float(current.supporterPlayed),
            float(current.stadiumPlayed),
            float(current.energyAttached),
            float(current.retreated),
            len(mine.prize or []) / PRIZE_COUNT_CAP,
            len(theirs.prize or []) / PRIZE_COUNT_CAP,
            float(mine.deckCount) / DECK_COUNT_CAP,
            float(theirs.deckCount) / DECK_COUNT_CAP,
            float(mine.handCount) / HAND_COUNT_CAP,
            float(theirs.handCount) / HAND_COUNT_CAP,
            len(mine.discard or []) / DISCARD_COUNT_CAP,
            len(theirs.discard or []) / DISCARD_COUNT_CAP,
            float(select.remainDamageCounter) / DAMAGE_COUNTER_CAP,
            float(select.remainEnergyCost) / REMAINING_ENERGY_CAP,
            float(bool(current.stadium)),
        ],
        dtype=np.float32,
    )
    assert values.shape == (MATCH_WIDTH,)
    return values


def featurize(observation: Any, deck: Sequence[int]) -> FeatureFrame:
    """Create one feature frame from the acting player's masked engine observation."""

    current = observation.current
    select = observation.select
    if current is None or select is None:
        raise ValueError("a decision observation with current state and select data is required")
    my = int(current.yourIndex)
    opponent = 1 - my
    mine = current.players[my]
    theirs = current.players[opponent]

    card_ids: list[int] = []
    roles: list[int] = []
    numerics: list[np.ndarray] = []
    tool_ids: list[int] = []
    senergy_ids: list[int] = []
    ent_map: dict[tuple[int, str, int], int] = {}

    for index, pokemon in enumerate(mine.active or []):
        _extend_pokemon(
            card_ids,
            roles,
            numerics,
            tool_ids,
            senergy_ids,
            ent_map,
            pokemon,
            owner=my,
            area_name="ACTIVE",
            area_index=index,
            role=Role.MY_ACTIVE,
            is_mine=True,
            is_active=True,
            player=mine,
        )
    for index, pokemon in enumerate(mine.bench or []):
        _extend_pokemon(
            card_ids,
            roles,
            numerics,
            tool_ids,
            senergy_ids,
            ent_map,
            pokemon,
            owner=my,
            area_name="BENCH",
            area_index=index,
            role=Role.MY_BENCH,
            is_mine=True,
            is_active=False,
            player=mine,
        )
    for index, pokemon in enumerate(theirs.active or []):
        _extend_pokemon(
            card_ids,
            roles,
            numerics,
            tool_ids,
            senergy_ids,
            ent_map,
            pokemon,
            owner=opponent,
            area_name="ACTIVE",
            area_index=index,
            role=Role.OPP_ACTIVE,
            is_mine=False,
            is_active=True,
            player=theirs,
        )
    for index, pokemon in enumerate(theirs.bench or []):
        _extend_pokemon(
            card_ids,
            roles,
            numerics,
            tool_ids,
            senergy_ids,
            ent_map,
            pokemon,
            owner=opponent,
            area_name="BENCH",
            area_index=index,
            role=Role.OPP_BENCH,
            is_mine=False,
            is_active=False,
            player=theirs,
        )

    for card in mine.hand or []:
        card_ids.append(_card_id(card))
        roles.append(int(Role.MY_HAND))
        numerics.append(_ZERO_NUM.copy())
        tool_ids.append(0)
        senergy_ids.append(0)

    for stadium in current.stadium or []:
        card_ids.append(_card_id(stadium))
        roles.append(int(Role.STADIUM))
        numerics.append(_ZERO_NUM.copy())
        tool_ids.append(0)
        senergy_ids.append(0)

    deck_ids, deck_zone = _deck_features(current, my, deck)

    opt_type: list[int] = []
    opt_card: list[int] = []
    opt_tgt: list[int] = []
    opt_attack: list[int] = []
    opt_ent: list[int] = []
    opt_num: list[list[float]] = []
    for option in select.option or []:
        primary, target, attack = _resolve_option(option, current, select, my)
        opt_type.append(int(option.type))
        opt_card.append(primary)
        opt_tgt.append(target)
        opt_attack.append(attack)
        opt_ent.append(_option_entity(option, current, my, ent_map))
        opt_num.append(
            [
                float(option.number or 0) / OPTION_NUMERIC_CAP,
                float(option.count or 0) / OPTION_NUMERIC_CAP,
                float(select.minCount) / OPTION_NUMERIC_CAP,
                float(select.maxCount) / OPTION_NUMERIC_CAP,
            ]
        )

    tok_num = (
        np.stack(numerics).astype(np.float32, copy=False)
        if numerics
        else np.empty((0, LIVE_NUMERIC_WIDTH), dtype=np.float32)
    )
    option_num = (
        np.asarray(opt_num, dtype=np.float32)
        if opt_num
        else np.empty((0, OPTION_NUMERIC_WIDTH), dtype=np.float32)
    )
    return FeatureFrame(
        tok_card_id=np.asarray(card_ids, dtype=np.int64),
        tok_role=np.asarray(roles, dtype=np.int64),
        tok_num=tok_num,
        tok_tool_id=np.asarray(tool_ids, dtype=np.int64),
        tok_senergy_id=np.asarray(senergy_ids, dtype=np.int64),
        deck_ids=deck_ids,
        deck_zone=deck_zone,
        glob=_global_features(current, select, my),
        opt_type=np.asarray(opt_type, dtype=np.int64),
        opt_card=np.asarray(opt_card, dtype=np.int64),
        opt_tgt=np.asarray(opt_tgt, dtype=np.int64),
        opt_attack=np.asarray(opt_attack, dtype=np.int64),
        opt_ent=np.asarray(opt_ent, dtype=np.int64),
        opt_num=option_num,
    )
