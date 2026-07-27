"""Spec 16b: tensor packing tests -- fixed widths, and a real-data smoke check reusing
the same recorded episode data spec 15's replay test validates against."""
from __future__ import annotations

import json
import os
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _IL_ROOT)

import pytest

from observation.encoder import build_observation
from observation.live_adapter import build_game_state
from observation.types import TOTAL_WORDS
from policy import data as data_mod
from policy import packing

_DATA_DIR = os.path.join(_IL_ROOT, "Top-ladder-data", "7-12")
_ZIP_PATH = os.path.join(_DATA_DIR, "pokemon-tcg-ai-battle-episodes-2026-07-12.zip")


def test_pad_pool_have_no_content():
    from observation.encoder import Word
    assert packing.pack_word(Word(kind="pad", role=None, static=None, live=None, attention_masked=True)) == []
    assert packing.pack_word(Word(kind="pool", role=None, static=None, live=None, attention_masked=False)) == []


def test_role_index_covers_every_role():
    for name in packing.ZONE_ROLE_NAMES + packing.BOARD_ROLE_NAMES:
        assert 0 <= packing.role_index(name) < packing.N_ROLES
    assert 0 <= packing.role_index(None) < packing.N_ROLES
    # every role gets a distinct index
    all_names = packing.ZONE_ROLE_NAMES + packing.BOARD_ROLE_NAMES + (None,)
    assert len({packing.role_index(n) for n in all_names}) == len(all_names)


def test_global_content_order_and_normalization():
    """Global-word catch-up (observation_known_errors #3): exact field order and
    normalization for all 12 scalars, including clipping at each zone's own capacity
    constant rather than Ceruledge's magic numbers."""
    from observation.encoder import Word
    from observation.types import DECK_CAPACITY, DISCARD_CAPACITY, HAND_CAPACITY, PRIZE_CAPACITY

    live = {
        "turn_number": 25,
        "supporter_played": True,
        "our_prize_count": 3,
        "opponent_prize_count": 6,
        "our_deck_count": DECK_CAPACITY,
        "opponent_deck_count": 10,
        "our_discard_count": 20,
        "opponent_discard_count": DISCARD_CAPACITY * 2,  # exercises the clip at 1.0
        "opponent_hand_count": HAND_CAPACITY,
        "item_locked": True,
        "energy_attached_this_turn": False,
        "turn_order": 1.0,
    }
    word = Word(kind="global", role=None, static=None, live=live, attention_masked=False)
    vec = packing.pack_word(word)

    assert len(vec) == packing.GLOBAL_WIDTH == 12
    assert vec == [
        25 / 50,
        1.0,
        3 / PRIZE_CAPACITY,
        1.0,
        1.0,
        10 / DECK_CAPACITY,
        20 / DISCARD_CAPACITY,
        1.0,
        1.0,
        1.0,
        0.0,
        1.0,
    ]


def test_global_content_defaults_to_zero_when_live_is_none():
    from observation.encoder import Word
    word = Word(kind="global", role=None, static=None, live=None, attention_masked=False)
    assert packing.pack_word(word) == [0.0] * packing.GLOBAL_WIDTH


@pytest.mark.skipif(not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present")
def test_pack_words_matches_content_widths_on_real_data():
    from cg_download.api import Observation
    from cg_download.utils import to_dataclass
    from features import GameStateTracker
    from prize_check import PrizeTracker

    z = zipfile.ZipFile(_ZIP_PATH)
    name = sorted(z.namelist())[0]
    data = json.loads(z.read(name))
    all_steps = data["steps"]
    decks = data_mod.submitted_decks_from_steps(all_steps)
    steps = all_steps[:50]

    trackers = {
        i: (
            PrizeTracker(decks[i]),
            GameStateTracker(decks[i]),
            GameStateTracker(decks[1 - i]),
        )
        for i in (0, 1)
    }
    checked = 0
    for step in steps:
        for our_idx, entry in enumerate(step):
            obs = to_dataclass(entry.get("observation", {}), Observation)
            if obs.current is None:
                continue
            prize_tracker, our_tracker, opp_tracker = trackers[our_idx]
            state = build_game_state(obs, our_idx, prize_tracker, our_tracker, opp_tracker)
            words = build_observation(state)
            assert len(words) == TOTAL_WORDS

            packed = packing.pack_words(words)
            assert len(packed) == TOTAL_WORDS
            for kind, role, vec, masked in packed:
                assert len(vec) == packing.CONTENT_WIDTHS[kind], (kind, len(vec))
                assert all(isinstance(v, float) for v in vec)
                if role is not None:
                    assert role in packing.ROLE_INDEX
            checked += 1

    assert checked > 0, "no real observations found to check"
