"""Spec 16c: extract supervised (observation, verb, candidates, label) examples from
recorded ladder games -- either raw `Top-ladder-data/*/*.zip` archives, or a sanitized
dataset produced by `build_sanitized_top_ladder_dataset.py` (loose per-episode `*.json`
files under `<sanitized_root>/<day>/`, `report.json` excluded). `iter_all_examples`'s
`source` argument ("raw" / "sanitized" / "both") selects which to read.

Off-by-one alignment (confirmed by direct inspection, not documented anywhere):
`steps[i][player].action` responds to `steps[i-1][player].observation`, not the same
step's own observation -- see `Ceruledge-RL/specs/16c-imitation-learning.md`.

The sanitized dataset adds a `select.usable` boolean (false where the acting player
had exactly one legal option). `iter_paired_decisions` skips those -- see
`Imitation-Learning/specs/il-dataset-sanitization/`. Raw episodes have no `usable`
key, so this has no effect when reading directly from a raw zip.
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


def submitted_decks_from_steps(steps: list, n_players: int = 2) -> dict[int, list[int]]:
    """Extract each player's authoritative 60-card submission from a replay.

    Deck submission is stored as an action before ordinary option-index actions begin.
    Search the full episode rather than relying on a hardcoded step number, and fail if
    a player is missing or presents conflicting 60-card submissions.
    """
    decks: dict[int, list[int]] = {}
    for step in steps:
        for player_idx, entry in enumerate(step):
            action = entry.get("action") or []
            if len(action) != 60 or any(not isinstance(cid, int) for cid in action):
                continue
            deck = list(action)
            prior = decks.get(player_idx)
            if prior is not None and prior != deck:
                raise RuntimeError(
                    f"replay contains conflicting submitted decks for player {player_idx}"
                )
            decks[player_idx] = deck
        if len(decks) == n_players:
            break
    missing = sorted(set(range(n_players)) - set(decks))
    if missing:
        raise RuntimeError(
            "replay is missing an authoritative 60-card submission for player(s) "
            + ", ".join(map(str, missing))
        )
    return decks


def iter_paired_decisions(steps: list):
    """Yields `(player_idx, action, prev_observation_json)` for every step-entry with a
    non-empty action and a selectable, usable previous observation.

    Centralizes the off-by-one fix confirmed by direct inspection (not documented
    anywhere in the recorded data's own schema): `steps[i][player].action` responds to
    `steps[i-1][player].observation`, not the same step's own observation. This is the
    single source of that fix -- both `extract_examples` below and any test that needs
    the same (obs, action) pairing must call this rather than re-implementing the -1
    offset, so a future edit can't fix the logic here while a separately-copied test
    loop keeps silently exercising the old, wrong pairing.

    Also the single source of the `select.usable` check: the sanitized dataset (see
    `Imitation-Learning/specs/il-dataset-sanitization/`) marks `usable=false` on any
    decision where the acting player had exactly one legal option -- no real choice to
    imitate. Raw episodes have no `usable` key, so `.get("usable", True)` is a no-op
    there and this function's behavior on raw zips is unchanged.
    """
    for i in range(1, len(steps)):
        for player_idx in range(len(steps[i])):
            action = steps[i][player_idx].get("action") or []
            obs_json = steps[i - 1][player_idx].get("observation") or {}
            select = obs_json.get("select")
            if not action or not select:
                continue
            if select.get("usable", True) is False:
                continue
            yield player_idx, action, obs_json


def _examples_from_episode(data: dict, name: str, max_steps: int):
    """Shared core: one `PrizeTracker` + `GameStateTracker` pair per (episode, player)
    -- same lifecycle `test_live_adapter_replay.py` already established. Used by both
    `extract_examples` (raw zip) and `extract_examples_from_dir` (sanitized dir)."""
    all_steps = data["steps"]
    decks = submitted_decks_from_steps(all_steps)
    steps = all_steps[:max_steps]
    trackers = {
        i: (
            PrizeTracker(decks[i]),
            GameStateTracker(decks[i]),
            GameStateTracker(decks[1 - i]),
        )
        for i in (0, 1)
    }

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


def extract_examples(zip_path: str, max_episodes: int | None = None, max_steps: int = 300):
    """Yields `Example`s across every episode in one raw Kaggle archive zip."""
    z = zipfile.ZipFile(zip_path)
    for name in _episode_names(zip_path, max_episodes):
        data = json.loads(z.read(name))
        yield from _examples_from_episode(data, name, max_steps)


def extract_examples_from_dir(day_dir: str, max_episodes: int | None = None, max_steps: int = 300):
    """Yields `Example`s across every loose per-episode `*.json` in one sanitized day
    directory (`<sanitized_root>/<day>/`, as produced by
    `build_sanitized_top_ladder_dataset.py`). `report.json` is not an episode and is
    excluded."""
    names = sorted(
        f for f in os.listdir(day_dir) if f.endswith(".json") and f != "report.json"
    )
    if max_episodes is not None:
        names = names[:max_episodes]
    for name in names:
        with open(os.path.join(day_dir, name), "rb") as handle:
            data = json.load(handle)
        yield from _examples_from_episode(data, name, max_steps)


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


def iter_all_examples(
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
    max_episodes_per_zip: int | None = None,
    max_steps: int = 300,
    source: str = "sanitized",
):
    """Extracts examples from raw archives, a sanitized dataset, or both.

    `source` selects which of `raw_dir` / `sanitized_dir` to read:
    - `"raw"`: every `*.zip` under `raw_dir` (e.g. `Top-ladder-data/7-12/*.zip`).
    - `"sanitized"`: every loose per-episode `*.json` under `sanitized_dir`
      (e.g. `<sanitized_root>/7-12/*.json`), respecting the `usable` mask via
      `iter_paired_decisions`. This is the default -- prefer the filtered dataset
      once it exists.
    - `"both"`: reads both. Note this double-counts any day present in both
      directories, since the sanitized set is a filtered copy of the same
      episodes -- only use `"both"` when the two directories cover
      non-overlapping days (e.g. sanitized days plus raw-only days not yet
      run through the sanitizer).
    """
    if source not in ("raw", "sanitized", "both"):
        raise ValueError(f"source must be 'raw', 'sanitized', or 'both', got {source!r}")

    if source in ("raw", "both"):
        if not raw_dir:
            raise ValueError("raw_dir is required when source is 'raw' or 'both'")
        for root, _dirs, files in os.walk(raw_dir):
            for fname in sorted(files):
                if fname.endswith(".zip"):
                    yield from extract_examples(
                        os.path.join(root, fname), max_episodes_per_zip, max_steps
                    )

    if source in ("sanitized", "both"):
        if not sanitized_dir:
            raise ValueError("sanitized_dir is required when source is 'sanitized' or 'both'")
        for root, _dirs, files in os.walk(sanitized_dir):
            if any(f.endswith(".json") and f != "report.json" for f in files):
                yield from extract_examples_from_dir(root, max_episodes_per_zip, max_steps)
