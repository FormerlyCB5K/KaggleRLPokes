"""Spec 11b's Trainer/Energy static template: card-ID identity + effect tag block.

**Tag block: real, wired in.** `trainer_energy_meta_tags.META_TAGS` (Deliverable A --
transcribed from the registry's own 109 effect rows) is looked up by known card_id; anything
else falls back to `trainer_energy_tag_catalog.tag_unseen_trainer_energy` (Deliverable B,
the regex parser) run against `card_data.get_trainer_energy_text`.

Trainer/Energy cards have no board-slot analogue and no static/live split of their own
(spec 11b's own scope note) -- they only ever need this one template, used identically
whether the card is sitting in a zone or (for a Tool/Stadium) fused into a Pokemon's live
state via `tool_template`/the Stadium word.

**Width correction (91 -> 54), found while transcribing.** Spec 11b's own Phase 4 section
locked "1 presence bit + 1 magnitude scalar per content tag" (`38x2 + 6 + 1 + 1 + 1 + 6 =
91`) -- but that prose predates this session's Pokemon-side finding (see
`pokemon_meta_tags.py`'s module docstring): across the real assignment data, no
magnitude-bearing tag is ever assigned exactly `0` while present, so the presence bit and
magnitude scalar collapse losslessly into one scalar per tag, exactly the same collapse
already applied to spec 11a's Pokemon tag block (108/117 -> 61/70). Re-verified true here
too across all 109 real rows (checked during transcription -- no row assigns a
magnitude-bearing tag literal `0`; N's Castle's `RETREAT_COST_MOD`, the one row whose true
effect *is* an absolute zero, is represented as boolean presence instead, precisely to
avoid this collision -- see `trainer_energy_meta_tags.py`). Corrected total:
`38 + 6 + 1 + 1 + 1 + 6 = 53`, then `54` after `STAT_DEBUFF` was added as a 20th reused
content tag (see `trainer_energy_tag_catalog.py`'s own module docstring).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import card_data
from ._registry import CARD_ID_TO_INDEX, UNK_CARD_INDEX
from .trainer_energy_meta_tags import META_TAGS
from .trainer_energy_tag_catalog import TAG_BLOCK_WIDTH, tag_unseen_trainer_energy

N_EFFECT_ROWS = 1


def build_tag_block(card_id: int) -> list[float]:
    """Known meta card -> Deliverable A's transcribed lookup. Anything else -> Deliverable
    B's regex parser run against the card's own printed effect text."""
    zero = [0.0] * TAG_BLOCK_WIDTH
    if card_id in META_TAGS:
        rows = META_TAGS[card_id]
        return next(iter(rows.values()), zero)
    text = card_data.get_trainer_energy_text(card_id) or ""
    return tag_unseen_trainer_energy(text)


@dataclass(frozen=True)
class TrainerEnergyStatic:
    card_id: int | None
    card_index: int
    tag_block: list[float] = field(default_factory=lambda: [0.0] * TAG_BLOCK_WIDTH)


def build_trainer_energy_static(card_id: int | None) -> TrainerEnergyStatic:
    if card_id is None:
        return TrainerEnergyStatic(card_id=None, card_index=UNK_CARD_INDEX)
    card_index = CARD_ID_TO_INDEX.get(card_id, UNK_CARD_INDEX)
    return TrainerEnergyStatic(
        card_id=card_id, card_index=card_index, tag_block=build_tag_block(card_id)
    )
