"""Spec 16a tests: verb classification + candidate resolution against real recorded
ladder games (genuinely diverse, non-Ceruledge decks -- same data spec 15's replay test
uses)."""
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

from cg_download.api import OptionType, SelectContext
from policy import action_space as asp
from policy import data as data_mod

_DATA_DIR = os.path.join(_IL_ROOT, "Top-ladder-data", "7-12")
_ZIP_PATH = os.path.join(_DATA_DIR, "pokemon-tcg-ai-battle-episodes-2026-07-12.zip")

pytestmark = pytest.mark.skipif(not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present")


def _sample_decisions(n_episodes=5, max_steps=200):
    """Uses `data.iter_paired_decisions` -- the single source of the off-by-one pairing
    fix (`steps[i][player].action` responds to `steps[i-1][player].observation`, not the
    same step's own observation) -- rather than a second, independently-maintained copy
    of that loop, so a future fix to the real pairing logic can't silently regress here
    without this test catching it."""
    from cg_download.api import Observation
    from cg_download.utils import to_dataclass

    z = zipfile.ZipFile(_ZIP_PATH)
    names = sorted(z.namelist())[:n_episodes]
    decisions = []
    for name in names:
        data = json.loads(z.read(name))
        steps = data["steps"][:max_steps]
        for our_idx, action, obs_json in data_mod.iter_paired_decisions(steps):
            obs = to_dataclass(obs_json, Observation)
            if obs.current is None:
                continue
            decisions.append((obs, our_idx, action))
    return decisions


def test_verb_vocabulary_is_8():
    assert asp.N_VERBS == 8
    assert len(set(asp.VERBS)) == 8


def test_recorded_action_always_classifiable_on_real_data():
    decisions = _sample_decisions()
    assert decisions, "expected at least one real decision to check"

    main_checked = 0
    sub_checked = 0
    unresolved_card_ids = 0
    total_card_candidates = 0

    for obs, our_idx, action in decisions:
        ctx = obs.select.context
        chosen = action[0]

        if ctx == SelectContext.MAIN:
            action_map = asp.build_action_map(obs)
            chosen_type = obs.select.option[chosen].type
            assert chosen_type in asp.VERB_INDEX, f"chosen MAIN option type {chosen_type} not a verb"
            assert chosen in action_map[chosen_type], "chosen option missing from its own verb bucket"
            candidates = asp.classify_candidates(obs, our_idx, action_map[chosen_type])
            assert any(c.option_index == chosen for c in candidates)
            main_checked += 1
        else:
            all_indices = list(range(len(obs.select.option)))
            candidates = asp.classify_candidates(obs, our_idx, all_indices)
            assert len(candidates) == len(obs.select.option)
            # Only action[0] is checkable against this single recorded observation: for
            # multi-count selections (minCount/maxCount > 1) each subsequent pick is made
            # against a live, updated option list the recorded JSON doesn't capture (only
            # one `observation` snapshot per step-entry) -- see spec 16c's note on this.
            assert any(c.option_index == chosen for c in candidates)
            sub_checked += 1

        for c in candidates:
            if obs.select.option[c.option_index].type in (
                OptionType.CARD, OptionType.PLAY, OptionType.ATTACH, OptionType.EVOLVE,
            ):
                total_card_candidates += 1
                if c.card_id is None and c.board_ref is None and c.target is None:
                    unresolved_card_ids += 1

    assert main_checked > 0
    assert sub_checked > 0
    # Most CARD-shaped candidates should resolve to *something* (card_id or board_ref);
    # a nonzero miss rate is expected (rare AreaTypes deliberately left unresolved per
    # spec 16a), but it shouldn't be the majority.
    if total_card_candidates:
        assert unresolved_card_ids / total_card_candidates < 0.5
