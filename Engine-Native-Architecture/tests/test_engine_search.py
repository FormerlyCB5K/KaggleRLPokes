from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import torch
from cg_download.api import Log, LogType, Option, OptionType, SelectContext

from engine_native_policy.engine_search import NativeSearchBackend
from engine_native_policy.model import PolicyOutput
from engine_native_policy.vocab import EFFECT_TAGS

from helpers import sample_deck, sample_observation


class FakeSearchApi:
    def __init__(self, root, children=None) -> None:
        self.root = root
        self.children = children or {}
        self.begin_kwargs = None
        self.step_calls = []
        self.end_calls = 0

    def search_begin(self, observation, **kwargs):
        self.begin_kwargs = kwargs
        return self.root

    def search_step(self, search_id, action):
        self.step_calls.append((search_id, tuple(action)))
        return self.children[(search_id, tuple(action))]

    def search_end(self):
        self.end_calls += 1


class FakePolicy:
    def __init__(self) -> None:
        self.deck = tuple(sample_deck())
        stat = torch.zeros((1300, 79))
        stat[100, 0] = 1
        card = SimpleNamespace(
            STAT=stat,
            ATK=torch.zeros((1300, 2, 130)),
            ABL=torch.zeros((1300, 130)),
            PLAY=torch.zeros((1300, 130)),
            ATTACK_SLOT=torch.zeros(1600, dtype=torch.int64),
        )
        self.network = SimpleNamespace(card=card)
        self.infer_calls = []

    def infer(self, observation):
        self.infer_calls.append(observation)
        options = observation.select.option
        n = len(options)
        opt_type = np.asarray([int(option.type) for option in options])
        opt_card = np.zeros(n, dtype=np.int64)
        opt_attack = np.zeros(n, dtype=np.int64)
        for index, option in enumerate(options):
            if option.type == OptionType.ATTACK:
                opt_card[index] = 100
                opt_attack[index] = int(option.attackId or 0)
            elif option.type == OptionType.PLAY:
                opt_card[index] = 301
        frame = SimpleNamespace(
            n_options=n,
            opt_type=opt_type,
            opt_card=opt_card,
            opt_attack=opt_attack,
        )
        logits = torch.arange(n, dtype=torch.float32).unsqueeze(0)
        incl = torch.linspace(-1, 1, n).unsqueeze(0)
        value = torch.tensor([0.25])
        return frame, PolicyOutput(
            logits=logits,
            incl=incl,
            value=value,
            value_fog=value,
        )


def _state(search_id, observation):
    return SimpleNamespace(searchId=search_id, observation=observation)


def test_begin_uses_manual_coin_and_length_correct_hidden_placeholders() -> None:
    observation = sample_observation()
    root = _state(1, observation)
    api = FakeSearchApi(root)
    backend = NativeSearchBackend(FakePolicy(), search_api=api)
    assert backend.start(observation) is root
    assert api.begin_kwargs["manual_coin"] is True
    assert len(api.begin_kwargs["your_deck"]) == 48
    assert len(api.begin_kwargs["your_prize"]) == 6
    assert len(api.begin_kwargs["opponent_deck"]) == 49
    assert len(api.begin_kwargs["opponent_prize"]) == 5
    assert len(api.begin_kwargs["opponent_hand"]) == 6
    assert api.begin_kwargs["opponent_active"] == []
    backend.finish()
    assert api.end_calls == 1


def test_single_and_multi_prompts_use_policy_and_macro_action() -> None:
    single_observation = sample_observation()
    single = _state(1, single_observation)
    policy = FakePolicy()
    backend = NativeSearchBackend(
        policy, search_api=FakeSearchApi(single)
    )
    backend.start(single_observation)
    evaluation = backend.evaluate(single)
    assert len(evaluation.actions) == len(single_observation.select.option)
    assert sum(item.prior for item in evaluation.actions) == pytest.approx(1.0)
    backend.finish()

    multi_observation = sample_observation(max_count=2)
    multi_observation.select.minCount = 1
    multi = _state(2, multi_observation)
    backend = NativeSearchBackend(
        policy, search_api=FakeSearchApi(multi)
    )
    backend.start(multi_observation)
    evaluation = backend.evaluate(multi)
    assert len(evaluation.actions) == 1
    assert evaluation.actions[0].prior == 1.0
    assert 1 <= len(evaluation.actions[0].action) <= 2
    backend.finish()


def test_end_turn_and_hidden_effect_stop_before_native_transition() -> None:
    end_observation = sample_observation(
        options=[Option(type=OptionType.END)]
    )
    end_state = _state(1, end_observation)
    api = FakeSearchApi(end_state)
    backend = NativeSearchBackend(FakePolicy(), search_api=api)
    backend.start(end_observation)
    result = backend.step(end_state, (0,))
    assert result.leaf is not None
    assert result.leaf.value == pytest.approx(0.25)
    assert api.step_calls == []
    backend.finish()

    draw_observation = sample_observation(
        options=[Option(type=OptionType.PLAY, index=1)]
    )
    draw_state = _state(2, draw_observation)
    policy = FakePolicy()
    draw_column = 20 + EFFECT_TAGS.index("draw")
    policy.network.card.PLAY[301, draw_column] = 1
    api = FakeSearchApi(draw_state)
    backend = NativeSearchBackend(policy, search_api=api)
    backend.start(draw_observation)
    result = backend.step(draw_state, (0,))
    assert result.leaf is not None
    assert api.step_calls == []
    backend.finish()


def test_terminal_child_is_exact_and_hidden_child_falls_back_to_parent() -> None:
    observation = sample_observation(
        options=[Option(type=OptionType.NUMBER, number=1)]
    )
    root = _state(1, observation)
    terminal_observation = deepcopy(observation)
    terminal_observation.current.result = 0
    terminal = _state(2, terminal_observation)
    api = FakeSearchApi(root, {(1, (0,)): terminal})
    backend = NativeSearchBackend(FakePolicy(), search_api=api)
    backend.start(observation)
    result = backend.step(root, (0,))
    assert result.leaf is not None
    assert result.leaf.proven_terminal is True
    assert result.leaf.value == 1.0
    backend.finish()

    hidden_observation = deepcopy(observation)
    hidden_observation.logs = [Log(type=LogType.DRAW, playerIndex=0)]
    hidden = _state(3, hidden_observation)
    api = FakeSearchApi(root, {(1, (0,)): hidden})
    policy = FakePolicy()
    backend = NativeSearchBackend(policy, search_api=api)
    backend.start(observation)
    result = backend.step(root, (0,))
    assert result.leaf is not None
    assert result.leaf.proven_terminal is False
    assert result.leaf.value == pytest.approx(0.25)
    assert len(policy.infer_calls) == 1
    backend.finish()


def test_manual_coin_prompt_is_evaluated_but_not_traversed() -> None:
    observation = sample_observation(
        options=[Option(type=OptionType.NUMBER, number=1)]
    )
    root = _state(1, observation)
    coin_observation = deepcopy(observation)
    coin_observation.select.context = SelectContext.COIN_HEAD
    coin_observation.select.option = [
        Option(type=OptionType.YES),
        Option(type=OptionType.NO),
    ]
    coin = _state(2, coin_observation)
    api = FakeSearchApi(root, {(1, (0,)): coin})
    policy = FakePolicy()
    backend = NativeSearchBackend(policy, search_api=api)
    backend.start(observation)
    result = backend.step(root, (0,))
    assert result.leaf is not None
    assert result.leaf.value == pytest.approx(0.25)
    assert len(policy.infer_calls) == 2
    backend.finish()
