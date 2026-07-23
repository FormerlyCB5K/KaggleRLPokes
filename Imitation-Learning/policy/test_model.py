"""Spec 16b tests: model forward pass + Stage 1/2 scoring against real recorded data."""
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
import torch

from cg_download.api import SelectContext
from observation.encoder import build_observation
from observation.live_adapter import build_game_state
from observation.types import TOTAL_WORDS
from policy import action_space as asp
from policy import data as data_mod
from policy import scoring
from policy.model import D_MODEL, PolicyModel

_DATA_DIR = os.path.join(_IL_ROOT, "Top-ladder-data", "7-12")
_ZIP_PATH = os.path.join(_DATA_DIR, "pokemon-tcg-ai-battle-episodes-2026-07-12.zip")


def _real_decisions(n_episodes=3, max_steps=150):
    """Uses `data.iter_paired_decisions` -- see `test_action_space.py::_sample_decisions`
    for why this shouldn't be a second independent copy of the pairing loop."""
    from cg_download.api import Observation
    from cg_download.utils import to_dataclass
    from features import GameStateTracker
    from prize_check import PrizeTracker

    z = zipfile.ZipFile(_ZIP_PATH)
    names = sorted(z.namelist())[:n_episodes]
    out = []
    for name in names:
        data = json.loads(z.read(name))
        steps = data["steps"][:max_steps]
        trackers = {i: (PrizeTracker(), GameStateTracker(), GameStateTracker()) for i in (0, 1)}
        for our_idx, action, obs_json in data_mod.iter_paired_decisions(steps):
            obs = to_dataclass(obs_json, Observation)
            if obs.current is None:
                continue
            prize_tracker, our_tracker, opp_tracker = trackers[our_idx]
            state = build_game_state(obs, our_idx, prize_tracker, our_tracker, opp_tracker)
            words = build_observation(state)
            out.append((obs, our_idx, action, words))
    return out


def test_forward_pass_shapes_and_no_nans():
    model = PolicyModel()
    model.eval()
    # A minimal synthetic all-PAD/pool/global observation exercises the shapes without
    # needing real data.
    from observation.encoder import Word
    words = (
        [Word(kind="pad", role=None, static=None, live=None, attention_masked=True)] * (TOTAL_WORDS - 2)
        + [Word(kind="global", role=None, static=None, live={"turn_number": 3}, attention_masked=False)]
        + [Word(kind="pool", role=None, static=None, live=None, attention_masked=False)]
    )
    with torch.no_grad():
        word_embeddings, pooled = model.encode(words)
    assert word_embeddings.shape == (TOTAL_WORDS, D_MODEL)
    assert pooled.shape == (D_MODEL,)
    assert not torch.isnan(word_embeddings).any()
    assert not torch.isnan(pooled).any()

    logits = model.stage1_logits(pooled)
    assert logits.shape == (asp.N_VERBS,)
    assert not torch.isnan(logits).any()


def test_stop_token_appends_one_extra_score():
    model = PolicyModel()
    model.eval()
    from observation.encoder import Word
    from cg_download.api import OptionType

    words = (
        [Word(kind="pad", role=None, static=None, live=None, attention_masked=True)] * (TOTAL_WORDS - 2)
        + [Word(kind="global", role=None, static=None, live={"turn_number": 3}, attention_masked=False)]
        + [Word(kind="pool", role=None, static=None, live=None, attention_masked=False)]
    )
    with torch.no_grad():
        word_embeddings, pooled = model.encode(words)
        candidates = [
            asp.Candidate(option_index=0, literal=1.0),
            asp.Candidate(option_index=1, literal=0.0),
        ]
        scores_plain = scoring.score_candidates(
            model, words, word_embeddings, pooled, OptionType.YES, candidates,
        )
        scores_stop = scoring.score_candidates(
            model, words, word_embeddings, pooled, OptionType.YES, candidates, include_stop=True,
        )
    assert scores_plain.shape == (2,)
    assert scores_stop.shape == (3,)
    assert not torch.isnan(scores_stop).any()
    # STOP's score should be model.stop_score(pooled) exactly (no effect-conditioning here).
    assert torch.isclose(scores_stop[-1], model.stop_score(pooled))


@pytest.mark.skipif(not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present")
def test_stage1_and_stage2_on_real_data():
    model = PolicyModel()
    model.eval()
    decisions = _real_decisions()
    assert decisions, "expected at least one real decision"

    main_checked = 0
    sub_checked = 0
    for obs, our_idx, action, words in decisions:
        with torch.no_grad():
            word_embeddings, pooled = model.encode(words)
        assert not torch.isnan(pooled).any()

        ctx = obs.select.context
        if ctx == SelectContext.MAIN:
            action_map = asp.build_action_map(obs)
            if not action_map:
                continue
            logits = model.stage1_logits(pooled)
            assert logits.shape == (asp.N_VERBS,)
            chosen_type = obs.select.option[action[0]].type
            if chosen_type not in action_map:
                continue  # off-by-one/deck-phase edge cases already noted in spec 16c
            candidates = asp.classify_candidates(obs, our_idx, action_map[chosen_type])
            scores = scoring.score_candidates(model, words, word_embeddings, pooled, chosen_type, candidates)
            assert scores.shape == (len(candidates),)
            assert not torch.isnan(scores).any()
            main_checked += 1
        else:
            all_indices = list(range(len(obs.select.option)))
            if action[0] >= len(all_indices):
                continue
            option_type = obs.select.option[action[0]].type
            candidates = asp.classify_candidates(obs, our_idx, all_indices)
            scores = scoring.score_candidates(model, words, word_embeddings, pooled, option_type, candidates)
            assert scores.shape == (len(candidates),)
            assert not torch.isnan(scores).any()
            sub_checked += 1

    assert main_checked > 0
    assert sub_checked > 0
