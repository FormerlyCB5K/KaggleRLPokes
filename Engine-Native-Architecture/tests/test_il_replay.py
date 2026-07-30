from __future__ import annotations

from collections import Counter
from copy import deepcopy

import pytest

from engine_native_policy.il.replay import (
    ReplayContractError,
    extract_submitted_decks,
    iter_episode_decisions,
    terminal_outcomes,
)

from il_helpers import sample_episode


def test_decks_are_found_and_actions_pair_with_previous_observation() -> None:
    episode = sample_episode()
    decks = extract_submitted_decks(episode)
    assert len(decks) == 2
    assert all(len(deck) == 60 for deck in decks)

    counts = Counter()
    decisions = list(iter_episode_decisions(episode, skip_counts=counts))
    assert len(decisions) == 4
    assert decisions[0].response_step == 1
    assert decisions[0].observation_json["select"]["maxCount"] == 1
    assert decisions[0].action == (0,)
    assert [decision.value_target for decision in decisions] == [
        -1.0,
        1.0,
        -1.0,
        1.0,
    ]
    assert decisions[2].response_step == 2
    assert decisions[2].observation_json["select"]["maxCount"] == 2
    assert decisions[2].action == (0, 1)
    assert counts["unusable"] == 2


def test_deck_submission_can_appear_at_any_step() -> None:
    episode = sample_episode()
    for player in range(2):
        deck = episode["steps"][0][player]["action"]
        episode["steps"][0][player]["action"] = []
        episode["steps"][3][player]["action"] = deck
    assert all(len(deck) == 60 for deck in extract_submitted_decks(episode))


def test_missing_or_conflicting_deck_is_a_hard_error() -> None:
    missing = sample_episode()
    missing["steps"][0][0]["action"] = []
    with pytest.raises(ReplayContractError, match="no authoritative"):
        extract_submitted_decks(missing)

    conflicting = sample_episode()
    extra = deepcopy(conflicting["steps"][0])
    extra[0]["action"] = [999] * 60
    conflicting["steps"].append(extra)
    with pytest.raises(ReplayContractError, match="conflicting"):
        extract_submitted_decks(conflicting)


def test_option_overflow_is_counted_and_not_emitted() -> None:
    episode = sample_episode()
    prior = episode["steps"][0][0]["observation"]["select"]
    prior["option"] = [deepcopy(prior["option"][0]) for _ in range(65)]
    counts = Counter()
    decisions = list(iter_episode_decisions(episode, skip_counts=counts))
    assert counts["option_overflow"] == 1
    assert len(decisions) == 3


def test_terminal_outcomes_are_acting_perspective_and_draw_safe() -> None:
    episode = sample_episode()
    episode["rewards"] = [8, 3]
    assert terminal_outcomes(episode) == (1.0, -1.0)

    episode["rewards"] = [-2, -2]
    assert terminal_outcomes(episode) == (0.0, 0.0)


@pytest.mark.parametrize(
    "rewards",
    (None, [1], [1, None], [1, float("nan")], [True, False]),
)
def test_invalid_terminal_rewards_are_rejected(rewards) -> None:
    episode = sample_episode()
    episode["rewards"] = rewards
    with pytest.raises(ReplayContractError, match="rewards"):
        terminal_outcomes(episode)
