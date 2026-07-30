from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from engine_native_policy.mcts import (
    ActionPrior,
    LeafValue,
    NeuralMCTS,
    PositionEvaluation,
    SearchConfig,
    StepResult,
)


class FakeBackend:
    def __init__(self, evaluations, transitions) -> None:
        self.evaluations = evaluations
        self.transitions = transitions
        self.finish_calls = 0
        self.steps: list[tuple[str, tuple[int, ...]]] = []

    def start(self, root_observation):
        return root_observation

    def evaluate(self, state):
        return self.evaluations[state]

    def step(self, state, action):
        self.steps.append((state, action))
        return self.transitions[(state, action)]

    def finish(self) -> None:
        self.finish_calls += 1


def _evaluation(player, value, *priors) -> PositionEvaluation:
    return PositionEvaluation(
        player=player,
        value=value,
        actions=tuple(
            ActionPrior((index,), prior)
            for index, prior in enumerate(priors)
        ),
    )


def test_search_uses_leaf_values_and_returns_normalized_visits() -> None:
    backend = FakeBackend(
        {"root": _evaluation(0, 0.0, 0.5, 0.5)},
        {
            ("root", (0,)): StepResult(leaf=LeafValue(0, -0.75)),
            ("root", (1,)): StepResult(leaf=LeafValue(0, 0.75)),
        },
    )
    result = NeuralMCTS(
        backend,
        SearchConfig(enabled=True, simulations=40, c_puct=1.0),
    ).search("root", training=False)

    assert result.action == (1,)
    assert result.visit_counts[1] > result.visit_counts[0]
    assert sum(result.visit_counts) == 40
    assert sum(result.visit_policy) == pytest.approx(1.0)
    assert result.immediate_terminal_win is False
    assert backend.finish_calls == 1


def test_value_is_negated_only_when_the_acting_player_changes() -> None:
    evaluations = {
        "root": _evaluation(0, 0.0, 0.5, 0.5),
        "opponent_good": _evaluation(1, 0.8, 1.0),
        "opponent_bad": _evaluation(1, -0.2, 1.0),
    }
    transitions = {
        ("root", (0,)): StepResult(child="opponent_good"),
        ("root", (1,)): StepResult(child="opponent_bad"),
        ("opponent_good", (0,)): StepResult(
            leaf=LeafValue(1, 0.8)
        ),
        ("opponent_bad", (0,)): StepResult(
            leaf=LeafValue(1, -0.2)
        ),
    }
    result = NeuralMCTS(
        FakeBackend(evaluations, transitions),
        SearchConfig(enabled=True, simulations=30, c_puct=1.0),
    ).search("root", training=False)
    assert result.action == (1,)


def test_immediate_terminal_win_overrides_a_tiny_prior() -> None:
    backend = FakeBackend(
        {"root": _evaluation(0, 0.0, 0.999, 0.001)},
        {
            ("root", (0,)): StepResult(
                leaf=LeafValue(0, 0.2, proven_terminal=False)
            ),
            ("root", (1,)): StepResult(
                leaf=LeafValue(0, 1.0, proven_terminal=True)
            ),
        },
    )
    result = NeuralMCTS(
        backend,
        SearchConfig(enabled=True, simulations=1),
    ).search("root", training=False)
    assert result.action == (1,)
    assert result.immediate_terminal_win is True
    assert result.stop_reason == "immediate_terminal_win"
    assert result.simulations_completed == 0


def test_root_noise_is_seeded_and_never_changes_the_action_set() -> None:
    config = SearchConfig(
        enabled=True,
        simulations=10,
        dirichlet_alpha=0.3,
        dirichlet_epsilon=0.25,
        temperature=1.0,
        seed=7,
    )

    def run():
        backend = FakeBackend(
            {"root": _evaluation(0, 0.0, 0.6, 0.3, 0.1)},
            {
                ("root", (0,)): StepResult(leaf=LeafValue(0, 0.0)),
                ("root", (1,)): StepResult(leaf=LeafValue(0, 0.0)),
                ("root", (2,)): StepResult(leaf=LeafValue(0, 0.0)),
            },
        )
        return NeuralMCTS(
            backend, config, rng=np.random.default_rng(7)
        ).search("root", training=True)

    left = run()
    right = run()
    assert left.actions == right.actions == ((0,), (1,), (2,))
    assert left.visit_counts == right.visit_counts
    assert left.action == right.action


@pytest.mark.parametrize(
    "config,match",
    (
        (SearchConfig(simulations=0), "simulations"),
        (SearchConfig(max_depth=0), "max_depth"),
        (SearchConfig(c_puct=-1), "c_puct"),
        (SearchConfig(dirichlet_alpha=0), "dirichlet_alpha"),
        (SearchConfig(dirichlet_epsilon=2), "dirichlet_epsilon"),
        (SearchConfig(temperature=-1), "temperature"),
        (
            replace(SearchConfig(), per_decision_seconds=0),
            "per_decision_seconds",
        ),
        (
            replace(SearchConfig(), game_budget_seconds=0),
            "game_budget_seconds",
        ),
    ),
)
def test_invalid_search_config_is_rejected(config, match) -> None:
    with pytest.raises(ValueError, match=match):
        config.validate()
