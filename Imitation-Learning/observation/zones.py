"""Spec 13a: fixed-capacity padded zone arrays, PAD vs UNK, canonical ordering.

A zone (deck/hand/discard/prizes) is a fixed-size array of `ZoneSlot`s. Occupancy varies;
capacity never does. Slots beyond current occupancy are `PAD`. Own unrevealed prizes are
`UNK`. Known cards are sorted by card-ID (deterministic tiebreak on ties) rather than any
gameplay-derived order -- see spec 13a's "Canonical ordering" section for why.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from . import card_data
from .static_template import PokemonStatic, build_pokemon_static
from .trainer_energy_static import TrainerEnergyStatic, build_trainer_energy_static
from .types import PAD, UNK

SlotKind = Literal["PAD", "UNK", "CARD"]


def build_any_static(card_id: int) -> PokemonStatic | TrainerEnergyStatic:
    static = card_data.get_card_static(card_id)
    if static is None:
        raise ValueError(f"card_id {card_id} not found in EN_Card_Data.csv")
    if static.card_class == "pokemon":
        return build_pokemon_static(card_id)
    return build_trainer_energy_static(card_id)


@dataclass(frozen=True)
class ZoneSlot:
    kind: SlotKind
    card_id: int | None
    static: PokemonStatic | TrainerEnergyStatic | None

    @property
    def attention_masked(self) -> bool:
        """PAD is masked out of self-attention and pooling; UNK is not (spec 13a)."""
        return self.kind == "PAD"


def _pad_slot() -> ZoneSlot:
    return ZoneSlot(kind="PAD", card_id=None, static=None)


def _unk_slot() -> ZoneSlot:
    # UNK reuses the same UNK-identity static template spec 11 already defines for an
    # unseen/hidden card -- no separate mechanism needed.
    return ZoneSlot(kind="UNK", card_id=None, static=build_pokemon_static(None))


def _card_slot(card_id: int) -> ZoneSlot:
    return ZoneSlot(kind="CARD", card_id=card_id, static=build_any_static(card_id))


@dataclass(frozen=True)
class ZoneArray:
    slots: tuple[ZoneSlot, ...]
    overflow_count: int  # cards that didn't fit; 0 for every zone except rare edge cases


def build_zone_array(
    known_card_ids: list[int],
    capacity: int,
    hidden_count: int = 0,
) -> ZoneArray:
    """Assemble one zone's fixed-capacity array.

    `known_card_ids` -- card IDs currently in this zone with known identity, in any order
    (this function sorts them canonically). `hidden_count` -- additional cards known to be
    present but with hidden identity (own unrevealed prizes only, per spec 13a); each
    becomes a `UNK` slot. Total occupancy beyond `capacity` becomes `overflow_count` rather
    than being silently dropped (spec 13a's no-silent-loss overflow handling) -- known cards
    take priority over UNK slots when trimming, since a UNK's own identity is irrelevant to
    which slot got cut.
    """
    ordered = sorted(known_card_ids)
    total = len(ordered) + hidden_count
    overflow = max(0, total - capacity)

    kept_known = ordered[: capacity]
    remaining_capacity = capacity - len(kept_known)
    kept_hidden = min(hidden_count, remaining_capacity)

    slots = [_card_slot(cid) for cid in kept_known]
    slots += [_unk_slot() for _ in range(kept_hidden)]
    slots += [_pad_slot() for _ in range(capacity - len(slots))]

    return ZoneArray(slots=tuple(slots), overflow_count=overflow)
