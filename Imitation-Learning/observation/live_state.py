"""Spec 11's Pokemon live-state fields: hp_curr, attached_energy_counts, special_energy_id,
tool_template, evolved_from, new_in_play, special conditions, and the three hits-ratio
threat features.

Input shape mirrors what the engine actually serializes (`ToJson.h`'s `PokemonJson`,
confirmed during spec 14's audit): `hp`/`maxHp` already effect-resolved, `energyCards`/
`tools`/`preEvolution` as exact card-ID lists. This module trusts that shape rather than
re-deriving HP/energy/tool/evolution tracking itself -- spec 14 established there is
nothing to re-derive for HP, and the engine already hands us exact identity for the rest.

`attacks_survivable`/`attack_damage`/`attack_hits_opponent` need real per-attack damage
numbers, which live in spec 11a's tag block -- still a zero-stub (see `static_template.py`).
The hits-ratio *mechanism* below is real and locked (spec 11's "Base field schema"); it's
parameterized by a `max_damage` callback so it's correct and testable independently of the
tag-block transcription.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import card_data
from .types import (
    ENERGY_BUCKET_INDEX,
    ENERGY_BUCKETS,
    PRISM_ENERGY_NAME,
    SPECIAL_CONDITIONS,
    SPECIAL_ENERGY_FIXED_BUCKET,
    SPECIAL_ENERGY_ID_INDEX,
    SPECIAL_ENERGY_IDS,
)

ENERGY_NORM = 5.0


@dataclass(frozen=True)
class RawPokemon:
    """Mirrors `ToJson.h::PokemonJson`'s fields, plus the handful of extras (is_active,
    is_basic for the host, special conditions) needed elsewhere in this module that the
    engine exposes through other parts of the observation, not this struct itself."""
    card_id: int
    hp: int
    max_hp: int
    energy_cards: tuple[int, ...] = ()
    tool_card_id: int | None = None
    pre_evolution_ids: tuple[int, ...] = ()
    is_basic: bool = False  # of the *current* top-of-stack form, for Prism Energy's bucket
    is_active: bool = False
    new_in_play: bool = False
    special_conditions: tuple[str, ...] = ()  # subset of types.SPECIAL_CONDITIONS, active only


def hp_curr(raw: RawPokemon) -> float:
    """Both `hp`/`maxHp` are already fully effect-resolved by the engine (spec 14) --
    nothing to bake, just normalize."""
    if raw.max_hp <= 0:
        return 0.0
    return min(raw.hp / raw.max_hp, 1.0)


def _energy_bucket(card_id: int, is_basic_host: bool) -> str | None:
    """Which `attached_energy_counts` bucket a single attached Energy card falls into.
    Basic Energy cards fall through to their own printed type (via card_data); Special
    Energy cards use the locked name-based mapping, with Prism Energy's live conditional
    (Rainbow while the host is a Basic, Colorless once evolved) as the one exception."""
    static = card_data.get_card_static(card_id)
    if static is None:
        return None
    if static.name == PRISM_ENERGY_NAME:
        return "Rainbow" if is_basic_host else "Colorless"
    if static.name in SPECIAL_ENERGY_FIXED_BUCKET:
        return SPECIAL_ENERGY_FIXED_BUCKET[static.name]
    # Ordinary Basic Energy: its own printed type is the bucket.
    return static.type_name


def attached_energy_counts(raw: RawPokemon) -> list[float]:
    counts = [0.0] * len(ENERGY_BUCKETS)
    for card_id in raw.energy_cards:
        bucket = _energy_bucket(card_id, raw.is_basic)
        if bucket is None or bucket not in ENERGY_BUCKET_INDEX:
            continue  # unrecognized Energy card -- not silently wrong, just uncounted; see open items
        counts[ENERGY_BUCKET_INDEX[bucket]] += 1.0
    return [min(c / ENERGY_NORM, 1.0) for c in counts]


def special_energy_id(raw: RawPokemon) -> list[float]:
    """Presence-based, multi-hot (spec 14's open item -- multiple different Special Energy
    IDs attached at once each get their own dim lit, not just the first found)."""
    vec = [0.0] * len(SPECIAL_ENERGY_IDS)
    for card_id in raw.energy_cards:
        static = card_data.get_card_static(card_id)
        if static is not None and static.name in SPECIAL_ENERGY_ID_INDEX:
            vec[SPECIAL_ENERGY_ID_INDEX[static.name]] = 1.0
    return vec


def new_in_play(raw: RawPokemon) -> float:
    return 1.0 if raw.new_in_play else 0.0


def special_conditions_multihot(raw: RawPokemon) -> list[float]:
    return [1.0 if c in raw.special_conditions else 0.0 for c in SPECIAL_CONDITIONS]


def evolved_from(raw: RawPokemon, max_depth: int = 3) -> list[int]:
    """Bounded list of prior-stage card IDs, padded with 0 (no card-index 0 exists in the
    shared vocabulary, so 0 doubles as "no entry" here -- callers embedding this should
    treat 0 as absent, not as card_id 0)."""
    ids = list(raw.pre_evolution_ids[:max_depth])
    return ids + [0] * (max_depth - len(ids))


# ---------------------------------------------------------------------------
# Hits-ratio threat features (spec 11's shared convention, `attacks_survivable` locked
# 2026-07-16: max damage across the ENTIRE opposing board, not just the current active)
# ---------------------------------------------------------------------------

HITS_CLIP = 4


def hits_ratio(numerator: int, denominator: int) -> float:
    """`min(numerator // denominator, 4) / 4`; denominator 0 -> the clip max, 1.0."""
    if denominator <= 0:
        return 1.0
    return min(numerator // denominator, HITS_CLIP) / HITS_CLIP


def attacks_survivable(effective_hp: int, opposing_board_max_damage: list[int]) -> float:
    """Reference attacker = the single highest damage value across every Pokemon on the
    opposing board (spec 11, locked 2026-07-16) -- not just the current active."""
    worst = max(opposing_board_max_damage, default=0)
    return hits_ratio(effective_hp, worst)


def attack_hits_opponent(effective_own_damage: int, opponent_effective_hp: int) -> float:
    return hits_ratio(opponent_effective_hp, effective_own_damage)
