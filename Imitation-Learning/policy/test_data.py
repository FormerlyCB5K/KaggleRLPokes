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

pytestmark = pytest.mark.skipif(not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present")


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
