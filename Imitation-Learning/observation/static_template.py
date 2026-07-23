"""Spec 11's Pokemon static template: card-ID identity, base printed fields, and the
attack/ability effect tag block (spec 11a).

**Tag block: real, wired in (Stage 4).** Known meta card IDs (`pokemon_meta_tags.META_TAGS`,
Deliverable A -- transcribed from spec 11a's manual assignment table) take precedence;
anything else falls back to `pokemon_tag_catalog.tag_unseen_pokemon` (Deliverable B, the
regex parser) run against `card_data.get_card_moves`' printed move text. See
`Ceruledge-RL/specs/11a-pokemon-attribute-tag-vocabulary.md` for the design this
implements. Only the first ability is encoded (a second ability is ignored, matching the
old encoding's convention); attacks are taken in printed order, up to 2, zero-padded if the
card has fewer.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import card_data
from ._registry import CARD_ID_TO_INDEX, UNK_CARD_INDEX
from .pokemon_meta_tags import META_TAGS
from .pokemon_tag_catalog import tag_unseen_pokemon
from .types import (
    N_ATTACK_ROWS,
    RULE_STATUS_INDEX,
    RULE_STATUSES,
    TYPE_INDEX,
    TYPES,
    WR_TYPE_INDEX,
    WR_TYPES,
)

# Per-row tag-block widths locked in spec 11a (amended for `energy_cost`, then corrected
# during code transcription: collapsed a redundant presence+magnitude pair per content tag,
# and fixed a stale 48->49 tag-count bug in spec 11a's own Phase 4 section -- was 117/108,
# now 70/61) -- see that spec's "Phase 4" and "Energy cost" sections. Attack rows carry
# `energy_cost` (9 dims); ability rows always leave it at zero.
TAG_BLOCK_WIDTH_ATTACK = 70
TAG_BLOCK_WIDTH_ABILITY = 61
N_ABILITY_ROWS = 1
TAG_BLOCK_WIDTH = TAG_BLOCK_WIDTH_ATTACK * N_ATTACK_ROWS + TAG_BLOCK_WIDTH_ABILITY * N_ABILITY_ROWS


def one_hot(index: int | None, width: int) -> list[float]:
    vec = [0.0] * width
    if index is not None:
        vec[index] = 1.0
    return vec


def build_tag_block(card_id: int) -> list[float]:
    """Known meta card -> Deliverable A's transcribed lookup. Anything else -> Deliverable
    B's regex parser run against the card's own printed move text."""
    zero_attack = [0.0] * TAG_BLOCK_WIDTH_ATTACK
    zero_ability = [0.0] * TAG_BLOCK_WIDTH_ABILITY

    if card_id in META_TAGS:
        rows = META_TAGS[card_id]
        attack0 = rows.get(f"card:{card_id}:attack:0", zero_attack)
        attack1 = rows.get(f"card:{card_id}:attack:1", zero_attack)
        ability0 = rows.get(f"card:{card_id}:ability:0", zero_ability)
        return attack0 + attack1 + ability0

    attacks, abilities = card_data.get_card_moves(card_id)
    attack_vecs = []
    for move in attacks[:N_ATTACK_ROWS]:
        vec, _ = tag_unseen_pokemon(move.text, None, move.cost, move.damage)
        attack_vecs.append(vec)
    while len(attack_vecs) < N_ATTACK_ROWS:
        attack_vecs.append(zero_attack)

    ability_vec = zero_ability
    if abilities:
        _, ab = tag_unseen_pokemon("", abilities[0].text, None, None)
        ability_vec = ab if ab is not None else zero_ability

    result: list[float] = []
    for vec in attack_vecs:
        result.extend(vec)
    result.extend(ability_vec)
    return result


@dataclass(frozen=True)
class PokemonStatic:
    card_id: int | None  # None for a genuinely unknown/UNK card
    card_index: int  # index into the shared card-ID embedding table; UNK_CARD_INDEX if unknown
    hp_max: float  # already normalized, /340
    type_onehot: list[float]  # len(TYPES) == 10
    rule_onehot: list[float]  # len(RULE_STATUSES) == 3
    retreat_cost: float  # already normalized, /4
    weakness_onehot: list[float]  # len(WR_TYPES) == 9, all-zero if none
    resistance_onehot: list[float]  # len(WR_TYPES) == 9, all-zero if none
    tag_block: list[float] = field(default_factory=lambda: [0.0] * TAG_BLOCK_WIDTH)


HP_NORM = 340.0
RETREAT_NORM = 4.0


def build_pokemon_static(card_id: int | None) -> PokemonStatic:
    """Build the static half of a Pokemon word. `card_id=None` -> UNK (all-zero identity,
    all-zero base fields -- an unknown card has no printed data to encode)."""
    if card_id is None:
        return PokemonStatic(
            card_id=None,
            card_index=UNK_CARD_INDEX,
            hp_max=0.0,
            type_onehot=one_hot(None, len(TYPES)),
            rule_onehot=one_hot(RULE_STATUS_INDEX["none"], len(RULE_STATUSES)),
            retreat_cost=0.0,
            weakness_onehot=one_hot(None, len(WR_TYPES)),
            resistance_onehot=one_hot(None, len(WR_TYPES)),
        )

    card_index = CARD_ID_TO_INDEX.get(card_id, UNK_CARD_INDEX)
    static = card_data.get_card_static(card_id)
    if static is None:
        raise ValueError(f"card_id {card_id} not found in EN_Card_Data.csv")

    type_idx = TYPE_INDEX.get(static.type_name) if static.type_name else None
    weak_idx = WR_TYPE_INDEX.get(static.weakness) if static.weakness else None
    resist_idx = WR_TYPE_INDEX.get(static.resistance) if static.resistance else None

    return PokemonStatic(
        card_id=card_id,
        card_index=card_index,
        hp_max=min((static.hp or 0) / HP_NORM, 1.0),
        type_onehot=one_hot(type_idx, len(TYPES)),
        rule_onehot=one_hot(RULE_STATUS_INDEX[static.rule_status], len(RULE_STATUSES)),
        retreat_cost=min((static.retreat_cost or 0) / RETREAT_NORM, 1.0),
        weakness_onehot=one_hot(weak_idx, len(WR_TYPES)),
        resistance_onehot=one_hot(resist_idx, len(WR_TYPES)),
        tag_block=build_tag_block(card_id),
    )
