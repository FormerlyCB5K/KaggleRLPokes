"""Spec 15's validation-plan item: run the adapter + encoder against real recorded
engine output, not just hand-built fixtures.

`Imitation-Learning/Top-ladder-data/*.zip` holds actual Kaggle episode replays. Each
step's `observation` field is the exact JSON the engine hands the bot -- the same shape
`cg_download.utils.to_dataclass` already converts into real `cg_download.api.Observation`
instances (this is the project's own existing JSON<->dataclass bridge, not something new
built for this test). Feeding that through `build_game_state` + `build_observation` is the
strongest available correctness signal short of a live game, and stresses real messy data
(arbitrary decks, arbitrary card ids, mid-evolution states, empty boards) that hand-built
fixtures don't cover.

Important scope note: this replay data is **not** Ceruledge-piloted. Each tracker must
therefore receive that player's authoritative submitted 60-card list from the replay's
initial deck-submission action. This test exercises the generalized prize/deck path in
addition to board/zone construction and end-to-end encoder execution.

Skips entirely if the data directory isn't present (e.g. a checkout without the large
replay archives).
"""
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

_DATA_DIR = os.path.join(_REPO_ROOT, "Imitation-Learning", "Top-ladder-data", "7-12")
_ZIP_PATH = os.path.join(_DATA_DIR, "pokemon-tcg-ai-battle-episodes-2026-07-12.zip")

pytestmark = pytest.mark.skipif(
    not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present in this checkout"
)

EPISODES_TO_SAMPLE = 8
MAX_STEPS_PER_EPISODE = 200  # covers every step of a typical full episode


def _sample_episode_jsons():
    from cg_download.utils import to_dataclass  # noqa: E402
    from cg_download.api import Observation  # noqa: E402
    from policy.data import submitted_decks_from_steps  # noqa: E402

    z = zipfile.ZipFile(_ZIP_PATH)
    names = sorted(z.namelist())[:EPISODES_TO_SAMPLE]
    episodes = []
    for name in names:
        data = json.loads(z.read(name))
        all_steps = data["steps"]
        decks = submitted_decks_from_steps(all_steps)
        steps = all_steps[:MAX_STEPS_PER_EPISODE]
        episodes.append((
            decks,
            [
                [to_dataclass(entry.get("observation", {}), Observation) for entry in step]
                for step in steps
            ],
        ))
    return episodes


def test_adapter_and_encoder_run_end_to_end_on_real_episodes():
    from .encoder import build_observation
    from .live_adapter import build_game_state
    from .types import TOTAL_WORDS
    from features import GameStateTracker
    from prize_check import PrizeTracker

    episodes = _sample_episode_jsons()
    assert episodes, "expected at least one sampled episode"

    checked_states = 0
    resolved_perspectives = 0
    for decks, episode in episodes:
        # One tracker triple per (episode, perspective) pair, reused across steps --
        # mirrors `train.py`'s one-tracker-per-episode lifecycle so evolved-serial and
        # prize bookkeeping accumulate correctly across the game.
        trackers = {
            our_idx: (
                PrizeTracker(decks[our_idx]),
                GameStateTracker(decks[our_idx]),
                GameStateTracker(decks[1 - our_idx]),
            )
            for our_idx in (0, 1)
        }
        for step in episode:
            for our_idx, obs in enumerate(step):
                if obs is None or obs.current is None:
                    continue
                prize_tracker, our_tracker, opponent_tracker = trackers[our_idx]

                state = build_game_state(obs, our_idx, prize_tracker, our_tracker, opponent_tracker)

                # Direct passthrough invariant: every board word's raw fields must
                # exactly match the source Pokemon this adapter is supposed to be a
                # faithful mapping of, not a derived/lossy summary.
                ps = obs.current.players[our_idx]
                opp_ps = obs.current.players[1 - our_idx]
                by_role = {}
                for side_ps, active_role, bench_role in (
                    (ps, "our_active", "our_bench"),
                    (opp_ps, "opponent_active", "opponent_bench"),
                ):
                    live_pokes = []
                    if side_ps.active and side_ps.active[0] is not None:
                        live_pokes.append((active_role, side_ps.active[0]))
                    for p in (side_ps.bench or ()):
                        if p is not None:
                            live_pokes.append((bench_role, p))
                    by_role.setdefault(active_role, []).extend(
                        p for role, p in live_pokes if role == active_role
                    )
                    by_role.setdefault(bench_role, []).extend(
                        p for role, p in live_pokes if role == bench_role
                    )

                for entry in state.board:
                    matches = [p for p in by_role.get(entry.role, ()) if p.id == entry.raw.card_id
                               and p.hp == entry.raw.hp and p.maxHp == entry.raw.max_hp]
                    assert matches, (
                        f"board entry {entry.role}/{entry.raw.card_id} has no matching "
                        f"source Pokemon with identical id/hp/maxHp"
                    )

                words = build_observation(state)
                assert len(words) == TOTAL_WORDS == 174
                checked_states += 1

        for prize_tracker, _our_tracker, _opponent_tracker in trackers.values():
            if prize_tracker.prizes_known:
                assert sum(prize_tracker.prize_counts.values()) <= 6
                resolved_perspectives += 1

    assert checked_states > 0, "no real (obs.current is not None) states were found to check"
    assert resolved_perspectives > 0, "sampled replays never exercised a full-deck reveal"
