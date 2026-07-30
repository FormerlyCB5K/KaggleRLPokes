from __future__ import annotations

import pytest
import torch

from engine_native_policy.actions import select_options
from engine_native_policy.model import EngineNativeNet
from engine_native_policy.mcts import SearchConfig
from engine_native_policy.policy import EngineNativePolicy

from helpers import sample_deck, sample_observation


def test_single_select_uses_policy_argmax() -> None:
    logits = torch.tensor([0.1, 2.0, 1.0])
    incl = torch.tensor([10.0, -10.0, 10.0])
    assert select_options(logits, incl, 3, 1, 1) == [1]


def test_multi_select_uses_include_threshold_and_bounds() -> None:
    logits = torch.tensor([100.0, 0.0, 0.0, 0.0])
    incl = torch.tensor([0.1, 0.2, -0.1, -0.2])
    assert select_options(logits, incl, 4, 1, 2) == [0, 1]
    assert select_options(logits, torch.full((4,), -10.0), 4, 2, 3) == [0, 1]


def test_multi_select_ties_resolve_by_index() -> None:
    zeros = torch.zeros(4)
    assert select_options(zeros, zeros, 4, 1, 2) == [0, 1]


def test_serving_rejects_provisional_tables_without_explicit_test_override() -> None:
    net = EngineNativeNet()
    with pytest.raises(ValueError, match="provisional"):
        EngineNativePolicy(net, sample_deck())


def test_serving_wrapper_returns_engine_option_indices() -> None:
    torch.manual_seed(3)
    policy = EngineNativePolicy(
        EngineNativeNet(),
        sample_deck(),
        allow_provisional_tables=True,
    )
    choices = policy.choose(sample_observation())
    assert len(choices) == 1
    assert 0 <= choices[0] < 5


def test_search_requires_bounded_value_head() -> None:
    with pytest.raises(ValueError, match="tanh-bounded"):
        EngineNativePolicy(
            EngineNativeNet(),
            sample_deck(),
            allow_provisional_tables=True,
            search_config=SearchConfig(enabled=True),
        )


def test_exhausted_game_budget_falls_back_to_raw_policy() -> None:
    torch.manual_seed(3)
    policy = EngineNativePolicy(
        EngineNativeNet(),
        sample_deck(),
        allow_provisional_tables=True,
    )
    policy.search_config = SearchConfig(
        enabled=True,
        simulations=1,
        game_budget_seconds=1.0,
    )
    policy._search_seconds_used = 1.0
    choices = policy.choose(sample_observation())
    assert len(choices) == 1
    assert 0 <= choices[0] < 5
