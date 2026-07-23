"""Spec 16c: extract supervised (observation, verb, candidates, label) examples from
`Imitation-Learning/Top-ladder-data/*/*.zip` -- real recorded ladder games, genuinely
diverse (non-Ceruledge) decks, with real chosen actions.

Off-by-one alignment (confirmed by direct inspection, not documented anywhere):
`steps[i][player].action` responds to `steps[i-1][player].observation`, not the same
step's own observation -- see `Ceruledge-RL/specs/16c-imitation-learning.md`.
"""
from __future__ import annotations

import json
import os
import sys
import zipfile
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "Ceruledge-RL"))
sys.path.insert(0, _IL_ROOT)

from cg_download.api import Observation, OptionType, SelectContext  # noqa: E402
from cg_download.utils import to_dataclass  # noqa: E402
from features import GameStateTracker  # noqa: E402
from observation.encoder import Word, build_observation  # noqa: E402
from observation.live_adapter import build_game_state  # noqa: E402
from prize_check import PrizeTracker  # noqa: E402

from . import action_space as asp  # noqa: E402


@dataclass
class Example:
    words: list[Word]
    option_type: OptionType
    verb_index: int | None  # set only for MAIN-context examples; index into asp.VERBS
    candidates: list[asp.Candidate]
    label_index: int  # index into `candidates`
    effect_card_id: int | None = None  # obs.select.effect.id, for scoring.condition_on_effect
    episode_name: str = ""  # for episode-level train/val splitting, never per-step


def _episode_names(zip_path: str, limit: int | None) -> list[str]:
    names = sorted(zipfile.ZipFile(zip_path).namelist())
    return names if limit is None else names[:limit]


def iter_paired_decisions(steps: list):
    """Yields `(player_idx, action, prev_observation_json)` for every step-entry with a
    non-empty action and a selectable previous observation.

    Centralizes the off-by-one fix confirmed by direct inspection (not documented
    anywhere in the recorded data's own schema): `steps[i][player].action` responds to
    `steps[i-1][player].observation`, not the same step's own observation. This is the
    single source of that fix -- both `extract_examples` below and any test that needs
    the same (obs, action) pairing must call this rather than re-implementing the -1
    offset, so a future edit can't fix the logic here while a separately-copied test
    loop keeps silently exercising the old, wrong pairing.
    """
    for i in range(1, len(steps)):
        for player_idx in range(len(steps[i])):
            action = steps[i][player_idx].get("action") or []
            obs_json = steps[i - 1][player_idx].get("observation") or {}
            if not action or not obs_json.get("select"):
                continue
            yield player_idx, action, obs_json


def extract_examples(zip_path: str, max_episodes: int | None = None, max_steps: int = 300):
    """Yields `Example`s across every episode in one zip. One `PrizeTracker` +
    `GameStateTracker` pair per (episode, player) -- same lifecycle
    `test_live_adapter_replay.py` already established."""
    z = zipfile.ZipFile(zip_path)
    for name in _episode_names(zip_path, max_episodes):
        data = json.loads(z.read(name))
        steps = data["steps"][:max_steps]
        trackers = {i: (PrizeTracker(), GameStateTracker(), GameStateTracker()) for i in (0, 1)}

        for our_idx, action, obs_json in iter_paired_decisions(steps):
            obs = to_dataclass(obs_json, Observation)
            if obs.current is None:
                continue

            chosen = action[0]
            opts = obs.select.option
            if chosen >= len(opts):
                continue  # deck-phase / other action-space quirk, see spec 16c

            example = _build_example(obs, our_idx, chosen)
            if example is None:
                continue

            prize_tracker, our_tracker, opp_tracker = trackers[our_idx]
            state = build_game_state(obs, our_idx, prize_tracker, our_tracker, opp_tracker)
            example.words = build_observation(state)
            example.episode_name = name
            yield example


def _build_example(obs: Observation, our_idx: int, chosen: int) -> Example | None:
    opts = obs.select.option
    chosen_type = opts[chosen].type
    effect_card_id = obs.select.effect.id if obs.select.effect is not None else None

    if obs.select.context == SelectContext.MAIN:
        action_map = asp.build_action_map(obs)
        if chosen_type not in action_map or chosen not in action_map[chosen_type]:
            return None  # edge case not covered by the 8-verb MAIN vocabulary
        verb_option_indices = action_map[chosen_type]
        candidates = asp.classify_candidates(obs, our_idx, verb_option_indices)
        label_index = verb_option_indices.index(chosen)
        return Example(
            words=[], option_type=chosen_type, verb_index=asp.VERB_INDEX[chosen_type],
            candidates=candidates, label_index=label_index, effect_card_id=effect_card_id,
        )

    all_indices = list(range(len(opts)))
    candidates = asp.classify_candidates(obs, our_idx, all_indices)
    return Example(
        words=[], option_type=chosen_type, verb_index=None,
        candidates=candidates, label_index=chosen, effect_card_id=effect_card_id,
    )


def iter_all_examples(data_dir: str, max_episodes_per_zip: int | None = None, max_steps: int = 300):
    """Walks every `*.zip` directly under `data_dir` (non-recursive per-subdir zips, e.g.
    `Top-ladder-data/7-12/*.zip`, `7-13/*.zip`, ...)."""
    for root, _dirs, files in os.walk(data_dir):
        for fname in sorted(files):
            if fname.endswith(".zip"):
                yield from extract_examples(
                    os.path.join(root, fname), max_episodes_per_zip, max_steps
                )
