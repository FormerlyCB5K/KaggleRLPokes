"""Unit tests for acting.py's pure-logic pieces -- synthetic Observation fixtures, no
native engine required."""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "Ceruledge-RL"))
sys.path.insert(0, _IL_ROOT)

import torch

from cg_download.api import AreaType, Card, Observation, Option, OptionType, PlayerState, SelectContext, SelectData, SelectType, State
from policy import acting
from policy import action_space as asp

_P_OWNER = 0


def _player_state(hand=(), active=None, bench=()):
    return PlayerState(
        active=[active] if active is not None else [],
        bench=list(bench), benchMax=8, deckCount=0,
        discard=[], prize=[None] * 6, handCount=len(hand), hand=list(hand),
        poisoned=False, burned=False, asleep=False, paralyzed=False, confused=False,
    )


def _state(players, your_idx=0):
    return State(
        turn=1, turnActionCount=0, yourIndex=your_idx, firstPlayer=0,
        supporterPlayed=False, stadiumPlayed=False, energyAttached=False, retreated=False,
        result=-1, stadium=[], looking=None, players=players,
    )


def _obs(options, context=SelectContext.MAIN, state=None, min_count=1, max_count=1):
    select = SelectData(
        type=SelectType.MAIN, context=context, minCount=min_count, maxCount=max_count,
        remainDamageCounter=0, remainEnergyCost=0, option=options,
        deck=None, contextCard=None, effect=None,
    )
    return Observation(select=select, logs=[], current=state)


def test_answer_yes_no_picks_correct_index():
    opts = [Option(type=OptionType.NO), Option(type=OptionType.YES)]
    obs = _obs(opts, context=SelectContext.IS_FIRST)
    assert acting.answer_yes_no(obs, yes=True) == [1]
    assert acting.answer_yes_no(obs, yes=False) == [0]


def test_answer_yes_no_empty_options():
    obs = _obs([], context=SelectContext.IS_FIRST)
    assert acting.answer_yes_no(obs, yes=True) == []


def test_setup_active_heuristic_picks_highest_hp_basic():
    # Charcadet (HP 70) vs Solrock (HP 110) -- both real Basic Pokemon card ids.
    Charcadet, Solrock = 796, 676
    hand = [Card(id=Charcadet, serial=1, playerIndex=_P_OWNER), Card(id=Solrock, serial=2, playerIndex=_P_OWNER)]
    ps = _player_state(hand=hand)
    state = _state([ps, _player_state()])
    opts = [
        Option(type=OptionType.CARD, area=AreaType.HAND, index=0),
        Option(type=OptionType.CARD, area=AreaType.HAND, index=1),
    ]
    obs = _obs(opts, context=SelectContext.SETUP_ACTIVE_POKEMON, state=state)
    assert acting.setup_active_heuristic(obs, our_idx=0) == [1]  # Solrock, higher HP


def test_setup_active_heuristic_falls_back_when_no_basic_found():
    hand = [Card(id=2, serial=1, playerIndex=_P_OWNER)]  # a Basic Energy, not a Pokemon
    ps = _player_state(hand=hand)
    state = _state([ps, _player_state()])
    opts = [Option(type=OptionType.CARD, area=AreaType.HAND, index=0)]
    obs = _obs(opts, context=SelectContext.SETUP_ACTIVE_POKEMON, state=state)
    assert acting.setup_active_heuristic(obs, our_idx=0) == [0]


def test_setup_bench_heuristic_declines_when_optional():
    opts = [Option(type=OptionType.CARD, area=AreaType.HAND, index=0)]
    obs = _obs(opts, context=SelectContext.SETUP_BENCH_POKEMON, min_count=0)
    assert acting.setup_bench_heuristic(obs) == []


def test_setup_bench_heuristic_satisfies_forced_minimum():
    opts = [Option(type=OptionType.CARD, area=AreaType.HAND, index=0)]
    obs = _obs(opts, context=SelectContext.SETUP_BENCH_POKEMON, min_count=1)
    assert acting.setup_bench_heuristic(obs) == [0]


def test_random_legal_selection_respects_min_max_no_duplicates():
    opts = [Option(type=OptionType.CARD, area=AreaType.HAND, index=i) for i in range(5)]
    obs = _obs(opts, min_count=2, max_count=4)
    for _ in range(50):
        result = acting.random_legal_selection(obs)
        assert 2 <= len(result) <= 4
        assert len(set(result)) == len(result)
        assert all(0 <= i < 5 for i in result)


def test_random_legal_selection_empty_options():
    obs = _obs([])
    assert acting.random_legal_selection(obs) == []


def test_act_main_masks_illegal_verbs():
    # Only END is legal here -- mask should be -inf everywhere except END's slot.
    opts = [Option(type=OptionType.END)]
    ps = _player_state()
    state_obj = _state([ps, _player_state()])
    obs = _obs(opts, context=SelectContext.MAIN, state=state_obj)

    from policy.model import PolicyModel
    from observation.encoder import GameState

    model = PolicyModel()
    model.eval()
    game_state = GameState(
        our_deck=[], our_hand=[], our_discard=[], our_prizes_known=[], our_prizes_hidden_count=6,
        opponent_discard=[], board=[], stadium_card_id=None, turn_number=1,
    )
    with torch.no_grad():
        result = acting.act_main(model, obs, our_idx=0, game_state=game_state, sample=False)

    end_idx = asp.VERB_INDEX[OptionType.END]
    assert result.mask[end_idx].item() == 0.0
    for i in range(asp.N_VERBS):
        if i != end_idx:
            assert result.mask[i].item() == float("-inf")
    assert result.selected == [0]
    assert result.verb_index == end_idx
    assert result.log_prob is not None and result.value is not None
