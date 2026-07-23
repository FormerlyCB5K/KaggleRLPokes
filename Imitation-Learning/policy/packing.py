"""Spec 16b: tensor packing -- `observation.encoder.Word` -> flat float content vectors.

Nothing before this module converts `Word` (whose `static`/`live` fields are structured
dataclasses/dicts, not tensors) into anything a model can consume -- spec 15 explicitly
left this out of scope. Widths are computed from the actual dataclass/dict shapes at
import time (via a zero/UNK probe instance) rather than hardcoded, so a future field
addition to the observation package can't silently desync this module's output width.

Per spec 16b: one content vector per `Word.kind` (`zone_card`, `board_pokemon`,
`stadium`, `global`; `pool`/`pad` carry no content -- the model gives them learned
constant embeddings instead). `card_id`/`card_index` (identity fields) are deliberately
excluded -- this project's attribute-only design principle (generalizing to unseen cards)
applies here exactly as it did for the value-network work referenced in memory.
"""
from __future__ import annotations

import os
import sys
from dataclasses import fields

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _IL_ROOT)  # Imitation-Learning root: `observation` as a top-level package

from observation.encoder import Word  # noqa: E402
from observation.static_template import PokemonStatic, build_pokemon_static  # noqa: E402
from observation.trainer_energy_static import (  # noqa: E402
    TrainerEnergyStatic,
    build_trainer_energy_static,
)
from observation.zones import build_any_static  # noqa: E402
from observation.types import (  # noqa: E402
    BOARD_ROLES,
    ENERGY_BUCKETS,
    MAX_BENCH,
    N_ATTACK_ROWS,
    SPECIAL_CONDITIONS,
    SPECIAL_ENERGY_IDS,
    ZONE_ROLES,
)

EVOLVED_FROM_DEPTH = 3  # live_state.evolved_from's default max_depth
CARD_ID_NORM = 2000.0  # evolved_from carries raw card ids, not pre-normalized
TURN_NUMBER_NORM = 50.0

_IDENTITY_FIELDS = {"card_id", "card_index"}


def _flatten(value) -> list[float]:
    if value is None:
        return []
    if isinstance(value, bool):
        return [1.0 if value else 0.0]
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    raise TypeError(f"cannot flatten value of type {type(value)}: {value!r}")


def _flatten_static_content(static) -> list[float]:
    """Flatten every non-identity field of a static dataclass, in declared field order."""
    out: list[float] = []
    for f in fields(static):
        if f.name in _IDENTITY_FIELDS:
            continue
        out.extend(_flatten(getattr(static, f.name)))
    return out


# Probe instances (zero/UNK) fix each vector's width once, from the real dataclass shapes.
_POKEMON_PROBE = _flatten_static_content(build_pokemon_static(None))
_TRAINER_ENERGY_PROBE = _flatten_static_content(build_trainer_energy_static(None))

POKEMON_STATIC_WIDTH = len(_POKEMON_PROBE)
TRAINER_ENERGY_STATIC_WIDTH = len(_TRAINER_ENERGY_PROBE)

# zone_card words can hold either card class -- both halves are always present, only one
# is ever nonzero for a given real slot.
ZONE_CARD_WIDTH = POKEMON_STATIC_WIDTH + TRAINER_ENERGY_STATIC_WIDTH

# board_pokemon live dict: fixed key order, explicit per-key width (values can be
# variable-length lists -- e.g. attack_damage has one entry per printed attack, 0-2 --
# so each key is padded/truncated to its declared width rather than flattened raw).
_BOARD_LIVE_KEY_WIDTHS = (
    ("hp_curr", 1),
    ("attached_energy_counts", len(ENERGY_BUCKETS)),
    ("special_energy_id", len(SPECIAL_ENERGY_IDS)),
    ("evolved_from", EVOLVED_FROM_DEPTH),
    ("new_in_play", 1),
    ("special_conditions", len(SPECIAL_CONDITIONS)),
    ("attacks_survivable", 1),
    ("attack_damage", N_ATTACK_ROWS),
    ("attack_hits_opponent", 1),
)


def _pad_or_truncate(vec: list[float], width: int) -> list[float]:
    if len(vec) >= width:
        return vec[:width]
    return vec + [0.0] * (width - len(vec))


def _board_live_vec(live: dict | None) -> list[float]:
    out: list[float] = []
    for key, width in _BOARD_LIVE_KEY_WIDTHS:
        raw = None if live is None else live.get(key)
        if key == "evolved_from":
            vals = [] if raw is None else [float(v) / CARD_ID_NORM for v in raw]
        else:
            vals = [] if raw is None else _flatten(raw)
        out.extend(_pad_or_truncate(vals, width))
    return out


# Fixed once the module loads -- see test_packing.py for the cross-check that this
# matches encoder.py's actual live-dict keys.
BOARD_LIVE_WIDTH = len(_board_live_vec(None))  # 1+11+10+3+1+5+1+2+1 = 35

BOARD_POKEMON_WIDTH = POKEMON_STATIC_WIDTH + BOARD_LIVE_WIDTH
STADIUM_WIDTH = TRAINER_ENERGY_STATIC_WIDTH


def _global_content(word: Word) -> list[float]:
    turn = 0.0 if word.live is None else float(word.live.get("turn_number", 0))
    supporter_played = 0.0 if word.live is None else float(bool(word.live.get("supporter_played", False)))
    return [min(turn / TURN_NUMBER_NORM, 1.0), supporter_played]


GLOBAL_WIDTH = len(_global_content(Word(kind="global", role=None, static=None, live=None, attention_masked=False)))

CONTENT_WIDTHS = {
    "zone_card": ZONE_CARD_WIDTH,
    "board_pokemon": BOARD_POKEMON_WIDTH,
    "stadium": STADIUM_WIDTH,
    "global": GLOBAL_WIDTH,
    "pool": 0,
    "pad": 0,
}

# Role vocabulary: 4 board roles + 5 zone names + 1 shared "none" row (stadium/global/
# pool/pad, where Word.role is None). Sourced from observation.types (single source of
# truth, shared with layout.py/action_space.py) rather than redeclared here.
ZONE_ROLE_NAMES = ZONE_ROLES
BOARD_ROLE_NAMES = BOARD_ROLES
NONE_ROLE_NAME = "_none"
ROLE_NAMES = ZONE_ROLE_NAMES + BOARD_ROLE_NAMES + (NONE_ROLE_NAME,)
ROLE_INDEX = {name: i for i, name in enumerate(ROLE_NAMES)}
N_ROLES = len(ROLE_NAMES)  # 10


def role_index(role: str | None) -> int:
    return ROLE_INDEX[role if role is not None else NONE_ROLE_NAME]


def _zone_card_content_from_static(static: PokemonStatic | TrainerEnergyStatic | None) -> list[float]:
    pokemon_part = (
        _flatten_static_content(static) if isinstance(static, PokemonStatic)
        else [0.0] * POKEMON_STATIC_WIDTH
    )
    trainer_part = (
        _flatten_static_content(static) if isinstance(static, TrainerEnergyStatic)
        else [0.0] * TRAINER_ENERGY_STATIC_WIDTH
    )
    return pokemon_part + trainer_part


def _zone_card_content(word: Word) -> list[float]:
    return _zone_card_content_from_static(word.static)


def pack_card_content(card_id: int) -> list[float]:
    """Build a `zone_card`-shaped content vector directly from a card_id, independent of
    any `Word`/board position -- used for effect-conditioning (see `model.py`'s
    `encode_card_by_id`/`condition_on_effect`), where the triggering card
    (`obs.select.effect`) may not correspond to any single word in the current
    observation (e.g. it's the Trainer card currently being played, not yet resolved to
    a discard-pile word)."""
    return _zone_card_content_from_static(build_any_static(card_id))


def _board_pokemon_content(word: Word) -> list[float]:
    static = word.static
    pokemon_part = (
        _flatten_static_content(static) if isinstance(static, PokemonStatic)
        else [0.0] * POKEMON_STATIC_WIDTH
    )
    return pokemon_part + _board_live_vec(word.live)


def _stadium_content(word: Word) -> list[float]:
    static = word.static
    if isinstance(static, TrainerEnergyStatic):
        return _flatten_static_content(static)
    return [0.0] * TRAINER_ENERGY_STATIC_WIDTH


def pack_word(word: Word) -> list[float]:
    """One `Word` -> its kind's fixed-width content vector (role is handled separately,
    as a model-side embedding -- see `Ceruledge-RL/specs/16b-model-architecture.md`)."""
    if word.kind == "zone_card":
        return _zone_card_content(word)
    if word.kind == "board_pokemon":
        return _board_pokemon_content(word)
    if word.kind == "stadium":
        return _stadium_content(word)
    if word.kind == "global":
        return _global_content(word)
    return []  # "pool" / "pad": no content, model supplies a learned constant embedding


def pack_words(words: list[Word]) -> list[tuple[str, str | None, list[float], bool]]:
    """Whole-observation convenience wrapper: (kind, role, content_vec, attention_masked)
    per word, in the same order `build_observation` produced them."""
    return [(w.kind, w.role, pack_word(w), w.attention_masked) for w in words]
