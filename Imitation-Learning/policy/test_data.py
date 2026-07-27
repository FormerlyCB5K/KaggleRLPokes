"""Spec 16c tests: example extraction from real recorded ladder games."""
from __future__ import annotations

import itertools
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _IL_ROOT)

import pytest

from observation.types import TOTAL_WORDS
from policy import action_space as asp
from policy import data

_ZIP_PATH = os.path.join(
    _IL_ROOT, "Top-ladder-data", "7-12", "pokemon-tcg-ai-battle-episodes-2026-07-12.zip",
)
_SANITIZED_DAY_DIR = os.path.join(_IL_ROOT, "Top-ladder-data", "sanitized", "7-12")


@pytest.mark.skipif(not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present")
def test_extract_examples_well_formed():
    examples = list(itertools.islice(data.extract_examples(_ZIP_PATH, max_episodes=3), 200))
    assert examples, "expected at least one extracted example"

    n_main = 0
    n_sub = 0
    for ex in examples:
        assert len(ex.words) == TOTAL_WORDS
        assert 0 <= ex.label_index < len(ex.candidates)
        if ex.verb_index is not None:
            assert 0 <= ex.verb_index < asp.N_VERBS
            n_main += 1
        else:
            n_sub += 1

    assert n_main > 0
    assert n_sub > 0


@pytest.mark.skipif(
    not os.path.isdir(_SANITIZED_DAY_DIR), reason="sanitized dataset not present locally"
)
def test_extract_examples_from_dir_well_formed():
    examples = list(
        itertools.islice(data.extract_examples_from_dir(_SANITIZED_DAY_DIR, max_episodes=3), 200)
    )
    assert examples, "expected at least one extracted example"
    for ex in examples:
        assert len(ex.words) == TOTAL_WORDS
        assert 0 <= ex.label_index < len(ex.candidates)


def _step(player_count: int, action, select) -> list:
    """One `steps[i]` entry: `player_count` player-slots, only slot 0 populated with
    the given action/select (mirrors real 2-player replay shape)."""
    entries = [{"action": [], "observation": {"select": None}} for _ in range(player_count)]
    entries[0] = {"action": action, "observation": {"select": select}}
    return entries


def test_iter_paired_decisions_skips_usable_false():
    """The sanitized dataset marks `usable=false` on single-legal-option decisions;
    iter_paired_decisions must not yield those. Recall the off-by-one pairing:
    `steps[i].action` responds to `steps[i-1].observation`, so each observation
    under test needs a *following* step supplying the action that responds to it."""
    steps = [
        _step(2, [], None),  # steps[0]: dummy prior obs (no select) for steps[1]'s action
        _step(2, [0], {"option": [{"type": 1}], "usable": False}),  # masked: 1 option
        _step(2, [1], {"option": [{"type": 1}, {"type": 2}], "usable": True}),  # real choice
        _step(2, [1], None),  # steps[3]'s action responds to steps[2]'s (usable) obs
    ]
    decisions = list(data.iter_paired_decisions(steps))
    assert len(decisions) == 1, "the usable=False decision must be skipped"
    _, action, obs_json = decisions[0]
    assert action == [1]
    assert obs_json["select"]["usable"] is True


def test_iter_paired_decisions_defaults_usable_true_when_absent():
    """Raw (unsanitized) episodes have no `usable` key at all -- behavior must be
    unchanged (nothing gets filtered on that basis)."""
    steps = [
        _step(2, [], None),
        _step(2, [1], {"option": [{"type": 1}]}),  # no "usable" key -- raw-zip shape
        _step(2, [1], None),  # action responding to the prior (unmasked-shape) obs
    ]
    decisions = list(data.iter_paired_decisions(steps))
    assert len(decisions) == 1


def test_iter_all_examples_rejects_invalid_source():
    with pytest.raises(ValueError):
        list(data.iter_all_examples(source="bogus"))


def test_iter_all_examples_requires_matching_dir_arg():
    with pytest.raises(ValueError):
        list(data.iter_all_examples(source="raw", raw_dir=None))
    with pytest.raises(ValueError):
        list(data.iter_all_examples(source="sanitized", sanitized_dir=None))
