"""Acceptance tests for spec 15's live engine adapter (`live_adapter.build_game_state`).

Constructs `cg_download.api.Observation` fixtures directly (same style as
`Ceruledge-RL/test_features.py`'s `mk_card`/`mk_poke`/`mk_player`/`mk_obs`) and asserts the
resulting `GameState` matches expectations, then confirms `encoder.build_observation` runs
end-to-end against it.

Run from `Imitation-Learning/`: python -m pytest observation/test_live_adapter.py -v
"""
from __future__ import annotations

import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_CERULEDGE_RL = os.path.join(_REPO_ROOT, "Ceruledge-RL")
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _CERULEDGE_RL)

import pytest
from cg_download.api import Card, Log, LogType, Observation, PlayerState, Pokemon, State
from features import FULL_DECK, GameStateTracker
from prize_check import PrizeTracker

from .encoder import build_observation
from .live_adapter import build_game_state
from .types import TOTAL_WORDS

_serial = iter(range(1000, 999_999))


def mk_card(cid: int, player: int = 0) -> Card:
    return Card(id=cid, serial=next(_serial), playerIndex=player)


def mk_poke(cid: int, hp: int, max_hp: int, energy=(), tools=(), pre_evolution=(),
            appeared: bool = False, player: int = 0) -> Pokemon:
    return Pokemon(
        id=cid, serial=next(_serial), hp=hp, maxHp=max_hp, appearThisTurn=appeared,
        energies=[], energyCards=[mk_card(e, player) for e in energy],
        tools=[mk_card(t, player) for t in tools],
        preEvolution=[mk_card(p, player) for p in pre_evolution],
    )


def mk_player(active=None, bench=(), hand=(), discard=(), deck_count=40, prize_count=6,
              hand_count=None, player: int = 0, **conds) -> PlayerState:
    hand_cards = [mk_card(c, player) for c in hand]
    return PlayerState(
        active=[active] if active is not None else [], bench=list(bench), benchMax=8,
        deckCount=deck_count, discard=[mk_card(c, player) for c in discard],
        prize=[None] * prize_count,
        handCount=hand_count if hand_count is not None else len(hand_cards),
        hand=hand_cards if player == 0 else None,
        poisoned=conds.get("poisoned", False), burned=conds.get("burned", False),
        asleep=conds.get("asleep", False), paralyzed=conds.get("paralyzed", False),
        confused=conds.get("confused", False),
    )


def mk_obs(our_ps, opp_ps, turn=1, first_player=0, logs=(), stadium_id=None) -> Observation:
    state = State(
        turn=turn, turnActionCount=0, yourIndex=0, firstPlayer=first_player,
        supporterPlayed=False, stadiumPlayed=False, energyAttached=False, retreated=False,
        result=-1, stadium=[mk_card(stadium_id)] if stadium_id is not None else [],
        looking=None, players=[our_ps, opp_ps],
    )
    return Observation(select=None, logs=list(logs), current=state, search_begin_input=None)


def mk_evolve_log(serial: int, player: int) -> Log:
    return Log(type=LogType.EVOLVE, playerIndex=player, serial=serial)


def _trackers():
    return PrizeTracker(), GameStateTracker(), GameStateTracker()


# ── Board construction ──────────────────────────────────────────────────────────────

def test_active_and_bench_are_mapped_with_correct_roles():
    our_active = mk_poke(743, 100, 140, energy=[1, 1], player=0)
    our_bench = mk_poke(190, 300, 300, tools=[1174], player=0)
    opp_active = mk_poke(121, 200, 320, player=1)
    our = mk_player(active=our_active, bench=[our_bench], hand=[906], player=0)
    opp = mk_player(active=opp_active, player=1)
    obs = mk_obs(our, opp)

    state = build_game_state(obs, 0, *_trackers())
    roles = {(w.role, w.raw.card_id) for w in state.board}
    assert roles == {
        ("our_active", 743), ("our_bench", 190), ("opponent_active", 121),
    }
    our_active_word = next(w for w in state.board if w.role == "our_active")
    assert our_active_word.raw.hp == 100 and our_active_word.raw.max_hp == 140
    assert our_active_word.raw.energy_cards == (1, 1)
    assert our_active_word.raw.is_active is True

    our_bench_word = next(w for w in state.board if w.role == "our_bench")
    assert our_bench_word.raw.tool_card_id == 1174
    assert our_bench_word.raw.is_active is False


def test_empty_active_slot_is_omitted_not_padded_with_none_poke():
    # ps.active == [None] happens when the card is face-down; must not be treated as
    # a real Pokemon, and must not appear in `state.board` at all (encoder pads it).
    our = mk_player(active=None, player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp)

    state = build_game_state(obs, 0, *_trackers())
    assert not any(w.role == "our_active" for w in state.board)


def test_multiple_tools_uses_first_only():
    poke = mk_poke(743, 100, 140, tools=[1174, 999], player=0)
    our = mk_player(active=poke, player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp)

    state = build_game_state(obs, 0, *_trackers())
    active = next(w for w in state.board if w.role == "our_active")
    assert active.raw.tool_card_id == 1174


def test_is_basic_derived_from_empty_pre_evolution():
    basic = mk_poke(743, 100, 140, player=0)
    evolved = mk_poke(190, 300, 300, pre_evolution=[121], player=0)
    our = mk_player(active=basic, bench=[evolved], player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp)

    state = build_game_state(obs, 0, *_trackers())
    assert next(w for w in state.board if w.role == "our_active").raw.is_basic is True
    assert next(w for w in state.board if w.role == "our_bench").raw.is_basic is False
    assert next(w for w in state.board if w.role == "our_bench").raw.pre_evolution_ids == (121,)


# ── new_in_play: appearThisTurn vs. per-side evolution tracking ─────────────────────

def test_new_in_play_via_appear_this_turn():
    poke = mk_poke(743, 100, 140, appeared=True, player=0)
    our = mk_player(active=poke, player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp)

    state = build_game_state(obs, 0, *_trackers())
    assert next(w for w in state.board if w.role == "our_active").raw.new_in_play is True


def test_new_in_play_via_our_evolve_log():
    poke = mk_poke(743, 100, 140, player=0)
    our = mk_player(active=poke, player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp, logs=[mk_evolve_log(poke.serial, player=0)])

    state = build_game_state(obs, 0, *_trackers())
    assert next(w for w in state.board if w.role == "our_active").raw.new_in_play is True


def test_opponent_new_in_play_needs_its_own_tracker_perspective():
    """The whole reason `build_game_state` takes a *second* GameStateTracker: an EVOLVE
    log for the opponent's Pokemon is playerIndex=1, which `our_tracker` (filtered to
    playerIndex==our_idx==0) will never record. Only `opponent_tracker.update(obs, 1)`
    picks it up."""
    opp_poke = mk_poke(121, 200, 320, player=1)
    our = mk_player(active=mk_poke(743, 100, 140, player=0), player=0)
    opp = mk_player(active=opp_poke, player=1)
    obs = mk_obs(our, opp, logs=[mk_evolve_log(opp_poke.serial, player=1)])

    prize_tracker, our_tracker, opponent_tracker = _trackers()
    state = build_game_state(obs, 0, prize_tracker, our_tracker, opponent_tracker)

    opp_word = next(w for w in state.board if w.role == "opponent_active")
    assert opp_word.raw.new_in_play is True
    # confirm it's really coming from the opponent-perspective tracker, not a fluke
    assert opp_poke.serial in opponent_tracker.evolved_serials
    assert opp_poke.serial not in our_tracker.evolved_serials


# ── Special conditions: active-only ──────────────────────────────────────────────────

def test_special_conditions_only_apply_to_active():
    poke_active = mk_poke(743, 100, 140, player=0)
    poke_bench = mk_poke(190, 300, 300, player=0)
    our = mk_player(active=poke_active, bench=[poke_bench], player=0,
                    poisoned=True, asleep=True)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp)

    state = build_game_state(obs, 0, *_trackers())
    active = next(w for w in state.board if w.role == "our_active")
    bench = next(w for w in state.board if w.role == "our_bench")
    assert set(active.raw.special_conditions) == {"Poisoned", "Asleep"}
    assert bench.raw.special_conditions == ()


# ── Zones: hand/discard/stadium/turn always resolvable without prize resolution ─────

def test_hand_discard_stadium_turn_are_direct_regardless_of_prize_state():
    our = mk_player(active=mk_poke(743, 100, 140, player=0), hand=[1, 2, 3],
                     discard=[4], player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), discard=[5], player=1)
    obs = mk_obs(our, opp, turn=7, stadium_id=1266)

    state = build_game_state(obs, 0, *_trackers())
    assert sorted(state.our_hand) == [1, 2, 3]
    assert state.our_discard == [4]
    assert state.opponent_discard == [5]
    assert state.stadium_card_id == 1266
    assert state.turn_number == 7


# ── Deck/prizes: unresolved vs. resolved ─────────────────────────────────────────────

def test_deck_and_prizes_unresolved_before_first_search():
    our = mk_player(active=mk_poke(743, 100, 140, player=0), player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp)

    state = build_game_state(obs, 0, *_trackers())
    assert state.our_deck == []
    assert state.our_prizes_known == []
    assert state.our_prizes_hidden_count == 6


def test_deck_by_elimination_once_prizes_resolved():
    active = mk_poke(FULL_DECK[0], 100, 140, player=0)
    our = mk_player(active=active, hand=[FULL_DECK[1]], discard=[FULL_DECK[2]], player=0)
    opp = mk_player(active=mk_poke(121, 200, 320, player=1), player=1)
    obs = mk_obs(our, opp)

    prize_tracker, our_tracker, opponent_tracker = _trackers()
    # White-box: drive the tracker straight to "resolved" rather than re-deriving
    # PrizeTracker's own already-tested deck-search resolution mechanism here. Every
    # already-accounted-for serial must be pre-registered as known -- otherwise the
    # `build_game_state` call below (which runs `prize_tracker.update()`) sees them as
    # "newly revealed outside prizes" and spuriously decrements their prize count.
    accounted = Counter([active.id] + [c.id for c in our.hand] + [c.id for c in our.discard])
    prize_tracker.prizes_known = True
    prize_tracker.prize_counts = Counter(FULL_DECK[3:9])
    prize_tracker.known_serials = {active.serial} | {c.serial for c in our.hand} | {
        c.serial for c in our.discard
    }

    state = build_game_state(obs, 0, prize_tracker, our_tracker, opponent_tracker)

    expected_prizes = sorted(FULL_DECK[3:9])
    assert sorted(state.our_prizes_known) == expected_prizes
    assert state.our_prizes_hidden_count == 0

    expected_deck = Counter(FULL_DECK) - accounted - Counter(FULL_DECK[3:9])
    assert Counter(state.our_deck) == expected_deck


# ── Guardrails ────────────────────────────────────────────────────────────────────

def test_no_current_raises():
    obs = Observation(select=None, logs=[], current=None, search_begin_input=None)
    with pytest.raises(ValueError):
        build_game_state(obs, 0, *_trackers())


# ── End-to-end: adapter output actually drives the real encoder ─────────────────────

def test_build_observation_runs_end_to_end_on_adapter_output():
    our_active = mk_poke(743, 100, 140, energy=[1, 1], player=0)
    our_bench = mk_poke(190, 300, 300, tools=[1174], player=0)
    opp_active = mk_poke(121, 200, 320, player=1)
    our = mk_player(active=our_active, bench=[our_bench], hand=[906, 1097], player=0)
    opp = mk_player(active=opp_active, discard=[1266], player=1)
    obs = mk_obs(our, opp, turn=4, stadium_id=1266)

    state = build_game_state(obs, 0, *_trackers())
    words = build_observation(state)
    assert len(words) == TOTAL_WORDS == 174
