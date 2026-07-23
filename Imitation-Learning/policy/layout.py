"""Maps a board/zone reference (role + slot, or role + card_id) to its absolute position
in spec 13a's 174-word sequence -- mirrors `observation/encoder.py::build_observation`'s
exact word assembly order. Needed so Stage 2 candidate scoring (16b) can look up the right
post-transformer word embedding for a resolved `action_space.Candidate` (16a).
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _IL_ROOT)

from observation.encoder import Word  # noqa: E402
from observation.types import (  # noqa: E402
    BOARD_ROLES,
    DECK_CAPACITY,
    DISCARD_CAPACITY,
    HAND_CAPACITY,
    MAX_BENCH,
    PRIZE_CAPACITY,
    ZONE_ROLES,
)

# Same order `build_observation` assembles words in.
_DECK_START = 0
_PRIZE_START = _DECK_START + DECK_CAPACITY
_HAND_START = _PRIZE_START + PRIZE_CAPACITY
_OUR_DISCARD_START = _HAND_START + HAND_CAPACITY
_OPP_DISCARD_START = _OUR_DISCARD_START + DISCARD_CAPACITY
_BOARD_START = _OPP_DISCARD_START + DISCARD_CAPACITY
_BENCH_SLOTS = 1 + MAX_BENCH  # active + full bench, matches encoder.py's per-side padding
_OUR_ACTIVE = _BOARD_START
_OUR_BENCH_START = _BOARD_START + 1
_OPP_ACTIVE = _BOARD_START + _BENCH_SLOTS
_OPP_BENCH_START = _OPP_ACTIVE + 1
_STADIUM = _BOARD_START + 2 * _BENCH_SLOTS
_GLOBAL = _STADIUM + 1
_POOL = _GLOBAL + 1

# Sourced from observation.types.ZONE_ROLES (single source of truth, shared with
# packing.py/action_space.py) -- each role's (start, capacity) still stated explicitly
# since word order isn't derivable from the vocabulary tuple's own (unrelated) order.
ZONE_STARTS = {
    "our_deck": (_DECK_START, DECK_CAPACITY),
    "our_prizes": (_PRIZE_START, PRIZE_CAPACITY),
    "our_hand": (_HAND_START, HAND_CAPACITY),
    "our_discard": (_OUR_DISCARD_START, DISCARD_CAPACITY),
    "opponent_discard": (_OPP_DISCARD_START, DISCARD_CAPACITY),
}
assert set(ZONE_STARTS) == set(ZONE_ROLES), "ZONE_STARTS drifted from observation.types.ZONE_ROLES"


def board_word_index(role: str, slot: int) -> int:
    """`role` in {our_active, our_bench, opponent_active, opponent_bench} (see
    `observation.types.BOARD_ROLES`). `slot` is always 0 for the two *_active roles
    (bench-position for the two *_bench roles), matching `action_space.BoardRef`."""
    if role not in BOARD_ROLES:
        raise ValueError(f"not a board role: {role!r}")
    if role == "our_active":
        return _OUR_ACTIVE
    if role == "our_bench":
        return _OUR_BENCH_START + slot
    if role == "opponent_active":
        return _OPP_ACTIVE
    return _OPP_BENCH_START + slot


STADIUM_INDEX = _STADIUM
GLOBAL_INDEX = _GLOBAL
POOL_INDEX = _POOL


def find_zone_word_index(
    words: list[Word], role: str, card_id: int | None, occurrence: int = 0,
) -> int | None:
    """Linear scan over a zone's slice of `words` for the `occurrence`-th word whose
    static card_id matches (0 = first). `build_zone_array` assigns zone words by a
    *stable* ascending-card-id sort, so the Nth same-card_id occurrence in the engine's
    raw (pre-sort) zone list -- `action_space.Candidate.occurrence`, computed from that
    same raw order -- lands at the Nth matching word here too. Without `occurrence`,
    duplicate copies of a card (very common: multi-copy Energy/Trainer lines) would all
    resolve to the same first match and become indistinguishable to the scorer."""
    if card_id is None or role not in ZONE_STARTS:
        return None
    start, capacity = ZONE_STARTS[role]
    seen = 0
    for offset in range(capacity):
        w = words[start + offset]
        if w.static is not None and getattr(w.static, "card_id", None) == card_id:
            if seen == occurrence:
                return start + offset
            seen += 1
    return None
