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


@pytest.mark.skipif(not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present")
def test_pack_words_matches_content_widths_on_real_data():
    from cg_download.api import Observation
    from cg_download.utils import to_dataclass
    from features import GameStateTracker
    from prize_check import PrizeTracker

    z = zipfile.ZipFile(_ZIP_PATH)
    name = sorted(z.namelist())[0]
    data = json.loads(z.read(name))
    steps = data["steps"][:50]

    trackers = {i: (PrizeTracker(), GameStateTracker(), GameStateTracker()) for i in (0, 1)}
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
