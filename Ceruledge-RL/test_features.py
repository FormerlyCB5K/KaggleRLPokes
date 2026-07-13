"""
test_features.py — Unit tests for the generalized encoder (spec 02 Verification).

Hand-computed expected vectors on constructed game states: early game (prizes
unknown), resolved prizes (deck by elimination), tag tiers (override / keyword /
zeros), status-afflicted active, empty slots, item-lock tracking, Tyranitar check.

Run from the repo root (needs cg_download importable + the card CSV):
    .venv/Scripts/python.exe Ceruledge-RL/test_features.py
"""
from __future__ import annotations

import math
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root: cg_download
sys.path.insert(0, _HERE)                    # Ceruledge-RL first: its features.py wins

from cg_download.api import (
    Card, Log, LogType, Observation, PlayerState, Pokemon, State,
)
import features as ft
from features import (
    Ceruledge_ex, Charcadet, Fire_Energy, Fighting_Energy, GameStateTracker,
    extract_features, opp_active_max_damage,
)

BUDEW = 235
TYRANITAR = 290
_serial = iter(range(1000, 9999))


def mk_card(cid: int, player: int = 0) -> Card:
    return Card(id=cid, serial=next(_serial), playerIndex=player)


def mk_poke(cid: int, hp: int, max_hp: int, energy: list[int] = (),
            appeared: bool = False, player: int = 0, tools: list[int] = ()) -> Pokemon:
    return Pokemon(id=cid, serial=next(_serial), hp=hp, maxHp=max_hp,
                   appearThisTurn=appeared, energies=[],
                   energyCards=[mk_card(e, player) for e in energy],
                   tools=[mk_card(t, player) for t in tools], preEvolution=[])


def mk_player(active=None, bench=(), hand=(), discard=(), deck_count=40,
              prize_count=6, hand_count=None, player: int = 0,
              **conds) -> PlayerState:
    hand_cards = [mk_card(c, player) for c in hand]
    return PlayerState(
        active=[active] if active is not None else [],
        bench=list(bench), benchMax=8, deckCount=deck_count,
        discard=[mk_card(c, player) for c in discard],
        prize=[None] * prize_count,
        handCount=hand_count if hand_count is not None else len(hand_cards),
        hand=hand_cards if player == 0 else None,
        poisoned=conds.get("poisoned", False), burned=conds.get("burned", False),
        asleep=conds.get("asleep", False), paralyzed=conds.get("paralyzed", False),
        confused=conds.get("confused", False),
    )


def mk_obs(our_ps, opp_ps, turn=1, first_player=0, logs=(),
           energy_attached=False, supporter_played=False, stadium_id=None) -> Observation:
    state = State(turn=turn, turnActionCount=0, yourIndex=0,
                  firstPlayer=first_player, supporterPlayed=supporter_played,
                  stadiumPlayed=False, energyAttached=energy_attached,
                  retreated=False, result=-1,
                  stadium=[mk_card(stadium_id)] if stadium_id is not None else [],
                  looking=None, players=[our_ps, opp_ps])
    return Observation(select=None, logs=list(logs), current=state,
                       search_begin_input=None)


def check_ranges(tensors):
    for t in tensors:
        assert torch_finite(t), "non-finite values"
        assert float(t.min()) >= 0.0 and float(t.max()) <= 1.0, \
            f"values outside [0,1]: min={t.min()}, max={t.max()}"


def torch_finite(t) -> bool:
    return bool((t == t).all()) and bool(t.abs().max() != float("inf"))


# ── Test A: early game, prizes unknown, hand-computed vectors ───────────────────

def test_early_game():
    our = mk_player(
        active=mk_poke(Charcadet, 80, 80, energy=[Fire_Energy]),
        hand=[Fire_Energy, Fire_Energy, Ceruledge_ex],
        deck_count=40, player=0)
    opp = mk_player(active=mk_poke(BUDEW, 30, 30, player=1),
                    deck_count=41, hand_count=5, player=1)
    obs = mk_obs(our, opp, turn=1, first_player=0)

    tracker = GameStateTracker()
    our_p, opp_p, zones, glob = extract_features(obs, 0, tracker)

    assert our_p.shape == (9, 19) and opp_p.shape == (9, 75)
    assert zones.shape == (4, 16) and glob.shape == (24,)
    check_ranges([our_p, opp_p, zones, glob])

    # our active (Charcadet, 1 fire, vs Budew max damage 10)
    a = our_p[0].tolist()
    expect = [80 / 270,   # hp_max
              1.0,        # hp_curr / own max
              1.0,        # is_ceruledge_line
              0.0, 1.0, 0.0, 0.0, 0.0,   # one-hot: Charcadet
              0.0,        # new_in_play
              0.5, 0.0,   # 1 fire / 2, 0 fighting
              1.0,        # survivable: min(80 // 10, 4)/4 = 1.0
              0.0,        # Charcadet attack damage 0
              1.0,        # hits_opponent: damage 0 -> "can never KO" -> 1.0
              0.0, 0.0, 0.0, 0.0, 0.0]   # no conditions
    assert all(abs(x - y) < 1e-6 for x, y in zip(a, expect)), (a, expect)

    # empty bench slots -> all zeros
    assert our_p[1:].abs().sum() == 0.0
    assert opp_p[1:].abs().sum() == 0.0

    # opp active (Budew: Grass, weak to Fire, 30 HP, free 10-damage attack,
    # override item_lock)
    o = opp_p[0].tolist()
    assert abs(o[0] - 30 / 340) < 1e-6 and o[1] == 1.0  # hp
    assert o[2:5] == [1.0, 0.0, 0.0]                   # rule: plain
    assert o[5] == 0.0 and o[6] == 0.0                 # no tool, retreat 0
    assert o[7] == 1.0 and sum(o[7:17]) == 1.0         # type: Grass
    assert o[17] == 1.0 and o[18] == 0.0               # weak to fire only
    assert o[19] == 0.0 and o[20] == 0.0               # no resistance
    # attacks_survivable_vs_ceruledge: Budew is fire-weak, so Ceruledge's 30 doubles to
    # 60 → min(30 // 60, 4)/4 = 0.0 (effect-aware weakness, spec 06)
    assert o[21] == 0.0
    assert o[22] == 0.0                                # no energy
    assert o[23:28] == [0.0] * 5                       # no conditions
    atk1 = o[28:46]
    assert atk1[0] == 0.0                              # free attack
    assert abs(atk1[1] - 10 / 270) < 1e-6              # 10 damage
    assert atk1[5] == 1.0                              # item_lock (override tier)
    assert o[46:64] == [0.0] * 18                      # single attack
    assert o[64:75] == [0.0] * 11                      # no ability

    # zones: hand has 2 Fire (of 7) + 1 Ceruledge (of 4); deck+prizes unknown
    hand = zones[0].tolist()
    assert abs(hand[ft.CARD_IDX[Fire_Energy]] - 2 / 7) < 1e-6
    assert abs(hand[ft.CARD_IDX[Ceruledge_ex]] - 1 / 4) < 1e-6
    assert hand[15] == 0.0
    assert zones[1].tolist() == [0.0] * 15 + [0.0]     # empty discard, known
    assert zones[2].tolist() == [0.0] * 15 + [1.0]     # deck unknown
    assert zones[3].tolist() == [0.0] * 15 + [1.0]     # prizes unknown

    # global
    g = glob.tolist()
    assert g[0] == 0.0                                 # no sol+lun
    assert g[1] == 0.25                                # 1 ceruledge-line / 4
    assert g[2] == 0.0                                 # no discard energy
    assert g[3] == 1.0                                 # 30 dmg vs 30 HP -> KO
    assert abs(g[4] - 1 / 30) < 1e-6                   # turn 1
    assert g[5] == 0.0                                 # not item locked
    assert g[6] == 0.0 and g[7] == 0.0 and g[8] == 0.0
    assert g[9] == 0.0                                 # we went first
    assert g[10] == 1.0                                # 6 prizes
    assert abs(g[11] - 3 / 15) < 1e-6                  # 3 cards in hand
    assert abs(g[13] - 40 / 46) < 1e-6
    print("  test_early_game PASSED")


# ── Test B: prizes resolved -> deck by elimination ──────────────────────────────

def test_prizes_resolved():
    our = mk_player(
        active=mk_poke(Charcadet, 80, 80),
        hand=[Fire_Energy], discard=[Fighting_Energy, Fighting_Energy],
        deck_count=39, player=0)
    opp = mk_player(active=mk_poke(BUDEW, 30, 30, player=1),
                    hand_count=4, player=1)
    obs = mk_obs(our, opp, turn=4)

    tracker = GameStateTracker()
    tracker.prizes.prizes_known = True
    tracker.prizes.prize_counts = Counter({Ceruledge_ex: 1, Fire_Energy: 2,
                                           Fighting_Energy: 3})
    # keep PrizeTracker.update from decrementing on these unseen serials
    tracker.prizes.known_serials = set(range(0, 100000))

    _, _, zones, glob = extract_features(obs, 0, tracker)

    prize = zones[3].tolist()
    assert prize[15] == 0.0
    assert abs(prize[ft.CARD_IDX[Ceruledge_ex]] - 1 / 4) < 1e-6
    assert abs(prize[ft.CARD_IDX[Fighting_Energy]] - 3 / 13) < 1e-6

    # deck = full − hand(1 fire) − discard(2 fighting) − in-play(1 charcadet)
    #        − prizes(1 ceruledge, 2 fire, 3 fighting)
    deck = zones[2].tolist()
    assert deck[15] == 0.0
    assert abs(deck[ft.CARD_IDX[Ceruledge_ex]] - 3 / 4) < 1e-6       # 4-0-0-1
    assert abs(deck[ft.CARD_IDX[Charcadet]] - 3 / 4) < 1e-6          # 4-1 in play
    assert abs(deck[ft.CARD_IDX[Fire_Energy]] - 4 / 7) < 1e-6        # 7-1-2
    assert abs(deck[ft.CARD_IDX[Fighting_Energy]] - 8 / 13) < 1e-6   # 13-2-3
    assert abs(glob[2] - 2 / 16) < 1e-6                              # discard energy
    print("  test_prizes_resolved PASSED")


# ── Test C: item lock — Budew attack tracked, Tyranitar live check ──────────────

def test_item_lock():
    our = mk_player(active=mk_poke(Charcadet, 80, 80), player=0)
    opp = mk_player(active=mk_poke(BUDEW, 30, 30, player=1),
                    hand_count=4, player=1)

    tracker = GameStateTracker()
    atk_log = Log(type=LogType.ATTACK, playerIndex=1, cardId=BUDEW,
                  serial=1, attackId=0)
    obs = mk_obs(our, opp, turn=2, logs=[atk_log])
    _, _, _, glob = extract_features(obs, 0, tracker)
    assert glob[5] == 1.0, "Budew attack must set item_locked"

    # persists on a later obs within our turn
    obs2 = mk_obs(our, opp, turn=2)
    _, _, _, glob = extract_features(obs2, 0, tracker)
    assert glob[5] == 1.0

    # cleared at the end of OUR turn
    end_log = Log(type=LogType.TURN_END, playerIndex=0)
    obs3 = mk_obs(our, opp, turn=3, logs=[end_log])
    _, _, _, glob = extract_features(obs3, 0, tracker)
    assert glob[5] == 0.0, "must clear at end of our turn"

    # Tyranitar active -> continuous lock, no tracking
    opp_tt = mk_player(active=mk_poke(TYRANITAR, 190, 190, player=1),
                       hand_count=4, player=1)
    obs4 = mk_obs(our, opp_tt, turn=3)
    _, _, _, glob = extract_features(obs4, 0, GameStateTracker())
    assert glob[5] == 1.0, "Tyranitar active must set item_locked"
    print("  test_item_lock PASSED")


# ── Test D: status conditions + no-opponent-active edge ─────────────────────────

def test_status_and_no_opp_active():
    our = mk_player(active=mk_poke(Ceruledge_ex, 100, 270, energy=[Fire_Energy]),
                    discard=[Fire_Energy] * 3,
                    asleep=True, burned=True, player=0)
    opp = mk_player(active=None, hand_count=4, player=1)   # mid-KO replacement
    obs = mk_obs(our, opp, turn=9)

    our_p, opp_p, _, glob = extract_features(obs, 0, GameStateTracker())
    a = our_p[0].tolist()
    # order: Asleep, Paralyzed, Burned, Poisoned, Confused
    assert a[14:19] == [1.0, 0.0, 1.0, 0.0, 0.0], a[14:19]
    # Ceruledge with 3 discard energy: damage 30+60=90
    assert abs(a[12] - 90 / 270) < 1e-6
    # no opp active -> treated as 0 HP: hits_opponent 0, survivable 1 (max dmg 0)
    assert a[13] == 0.0 and a[11] == 1.0
    # ceruledge_KO stays 1.0; opp slots all zero
    assert glob[3] == 1.0
    assert opp_p.abs().sum() == 0.0
    print("  test_status_and_no_opp_active PASSED")


# ── Test E: keyword tier + evolved-this-turn flag ────────────────────────────────

def test_keyword_tier_and_new_in_play():
    # Tyranitar has no attack override -> tier 2 keywords (Cracking Stomp: deckout)
    our_active = mk_poke(Ceruledge_ex, 270, 270, appeared=True)
    our = mk_player(active=our_active, player=0)
    opp = mk_player(active=mk_poke(TYRANITAR, 190, 190,
                                   energy=[Fire_Energy] * 2, player=1),
                    hand_count=4, player=1)

    tracker = GameStateTracker()
    ev_log = Log(type=LogType.EVOLVE, playerIndex=0, cardId=Ceruledge_ex,
                 serial=our_active.serial)
    obs = mk_obs(our, opp, turn=5, logs=[ev_log])
    our_p, opp_p, _, _ = extract_features(obs, 0, tracker)

    assert our_p[0][8] == 1.0                          # new_in_play (evolved)
    o = opp_p[0].tolist()
    atk1 = o[28:46]
    assert atk1[11] == 1.0                             # deckout via keywords
    assert abs(atk1[1] - 150 / 270) < 1e-6             # printed 150
    assert abs(o[22] - 2 / 5) < 1e-6                   # 2 energy attached
    # our survivable vs Tyranitar (max 150): min(270 // 150, 4)/4 = 0.25
    assert our_p[0][11] == 0.25
    print("  test_keyword_tier_and_new_in_play PASSED")


def test_reviewed_overrides_and_dynamic_damage():
    # Static tag corrections and new attack-tag dimensions.
    atk, _, md = ft.ot.card_tag_vectors(879)  # Hop's Trevenant
    schema = ft.ot.attack_block_schema()
    assert dict(zip(schema, atk[18:36]))["retreat_lock"] == 1.0
    assert md == 180
    atk, _, _ = ft.ot.card_tag_vectors(304)   # Hop's Snorlax
    assert dict(zip(schema, atk[:18]))["recoil"] == 1.0
    assert ft.ot.card_tags(304).attack_raws[0]["recoil"] == 80
    atk, _, _ = ft.ot.card_tag_vectors(743)   # Alakazam
    assert dict(zip(schema, atk[:18]))["counter_snipe"] == 0.0
    atk, _, md = ft.ot.card_tag_vectors(293)  # N's Zoroark aggregate threats
    z1, z2 = dict(zip(schema, atk[:18])), dict(zip(schema, atk[18:36]))
    assert z1["cooldown"] == 1.0 and z1["recoil"] == 0.0
    assert z2["snipe"] == 0.9 and z2["discard_energy"] == 0.4 and md == 290
    _, ability, _ = ft.ot.card_tag_vectors(386)
    assert ability == [0.0] * 11              # phantom immunity override removed

    # Board-dependent threat formulas.
    alakazam = mk_poke(743, 150, 150, player=1)
    opp = mk_player(active=alakazam, hand_count=7, player=1)
    assert opp_active_max_damage(alakazam, opp, mk_player(player=0)) == 140

    archaludon = mk_poke(190, 80, 330, player=1)
    opp = mk_player(active=archaludon, player=1)
    assert opp_active_max_damage(archaludon, opp, mk_player(player=0)) == 330

    gible = mk_poke(379, 70, 70, player=1)
    roserade = mk_poke(342, 130, 130, player=1)
    opp = mk_player(active=gible, bench=[roserade], player=1)
    assert opp_active_max_damage(gible, opp, mk_player(player=0)) == 50

    voltorb = mk_poke(265, 60, 60, player=1)
    bellibolt = mk_poke(269, 280, 280,
                        energy=[Fire_Energy] * 3, player=1)
    opp = mk_player(active=voltorb, bench=[bellibolt], player=1)
    assert opp_active_max_damage(voltorb, opp, mk_player(player=0)) == 80

    # Okidogi's reviewed 230 HP is used even if static/live source says 130.
    our = mk_player(active=mk_poke(Charcadet, 80, 80), player=0)
    opp = mk_player(active=mk_poke(116, 130, 130, player=1), player=1)
    _, opp_p, _, _ = extract_features(mk_obs(our, opp), 0, GameStateTracker())
    assert abs(float(opp_p[0][0]) - 230 / 340) < 1e-6
    assert abs(float(opp_p[0][1]) - 130 / 230) < 1e-6

    # Palafin recoil is live: 40 damage taken = 4 counters = 40 recoil HP.
    palafin = mk_poke(51, 110, 150, player=1)
    opp = mk_player(active=palafin, player=1)
    _, opp_p, _, _ = extract_features(mk_obs(our, opp), 0, GameStateTracker())
    recoil_idx = 28 + ft.ot.attack_block_schema().index("recoil")
    assert abs(float(opp_p[0][recoil_idx]) - 40 / 70) < 1e-6
    print("  test_reviewed_overrides_and_dynamic_damage PASSED")


# ── Test G: effect baking end-to-end (spec 06/07) ───────────────────────────────

def test_effect_bakes():
    # opp dim indices
    HP_MAX, HP_CURR, RETREAT = 0, 1, 6
    SURV_VS_CER = 21

    # (1) damage-reduction ability (Mudsdale 383, -30 taken). With 2 fire in our discard,
    # ceruledge_dmg = 70; effective = 70 - 30 = 40 vs Mudsdale 150 HP → min(150//40,4)/4.
    our = mk_player(active=mk_poke(Ceruledge_ex, 270, 270, energy=[Fire_Energy]),
                    discard=[Fire_Energy, Fire_Energy], player=0)
    muds = mk_poke(383, 150, 150, player=1)
    opp = mk_player(active=muds, hand_count=4, player=1)
    _, opp_p, _, glob = extract_features(mk_obs(our, opp), 0, GameStateTracker())
    assert opp_p[0][SURV_VS_CER] == 0.75, opp_p[0][SURV_VS_CER].item()   # 150 // 40 = 3
    # ceruledge_KO reflects the reduced 40 damage: 40 / 150
    assert abs(float(glob[3]) - 40 / 150) < 1e-6, glob[3].item()

    # sanity: same board WITHOUT the reduction ability would be 150 // 70 = 2 → 0.5
    plain = mk_poke(796, 150, 150, player=1)   # Charcadet: no bake, {R} type (not fire-weak-relevant)
    opp2 = mk_player(active=plain, hand_count=4, player=1)
    _, opp_p2, _, _ = extract_features(mk_obs(our, opp2), 0, GameStateTracker())
    assert opp_p2[0][SURV_VS_CER] == 0.5, opp_p2[0][SURV_VS_CER].item()

    # (2) stadium HP aura (Lively Stadium 1251, +30 to Basics both sides): Budew 30 → 60.
    our3 = mk_player(active=mk_poke(Charcadet, 80, 80), player=0)
    opp3 = mk_player(active=mk_poke(BUDEW, 30, 30, player=1), hand_count=4, player=1)
    _, opp_p3, _, _ = extract_features(mk_obs(our3, opp3, stadium_id=1251),
                                      0, GameStateTracker())
    assert abs(float(opp_p3[0][HP_MAX]) - 60 / 340) < 1e-6, opp_p3[0][HP_MAX].item()

    # (3) retreat tool (Air Balloon 1174, -2): opp active with printed retreat reduced.
    reg = ft.cd.CardRegistry.load()
    r_id = next(cid for cid, s in reg.stats.items()
                if s.stage and s.retreat >= 2 and s.max_hp and not (get_ov(cid)))
    base_ret = reg.get(r_id).retreat
    opp4 = mk_player(active=mk_poke(r_id, reg.get(r_id).max_hp, reg.get(r_id).max_hp,
                                    player=1, tools=[1174]), hand_count=4, player=1)
    our4 = mk_player(active=mk_poke(Charcadet, 80, 80), player=0)
    _, opp_p4, _, _ = extract_features(mk_obs(our4, opp4), 0, GameStateTracker())
    assert abs(float(opp_p4[0][RETREAT]) - max(0, base_ret - 2) / 4) < 1e-6, opp_p4[0][RETREAT].item()

    # (4) opponent attack-cost feature changes dynamically; damage remains present.
    ATTACK0_COST, ATTACK0_DAMAGE = 28, 29
    ursa = mk_player(active=mk_poke(44, 260, 260, player=1), prize_count=6, player=1)
    ours_prizes_taken3 = mk_player(active=mk_poke(Charcadet, 80, 80),
                                   prize_count=3, player=0)
    _, up, _, _ = extract_features(mk_obs(ours_prizes_taken3, ursa), 0,
                                   GameStateTracker())
    assert abs(float(up[0][ATTACK0_COST]) - 2 / 5) < 1e-6  # Blood Moon 5 - 3
    assert float(up[0][ATTACK0_DAMAGE]) > 0                 # never gated to zero

    # Watchtower suppresses Bloodmoon Ursaluna's Colorless Ability: printed cost 5.
    _, up_watch, _, _ = extract_features(mk_obs(ours_prizes_taken3, ursa,
                                                 stadium_id=1256),
                                         0, GameStateTracker())
    assert float(up_watch[0][ATTACK0_COST]) == 1.0

    # Counter Gain: opponent has more prizes remaining, so attached holder costs 1 less.
    counter_opp = mk_player(active=mk_poke(796, 70, 70, player=1, tools=[1168]),
                            prize_count=5, player=1)
    counter_us = mk_player(active=mk_poke(Charcadet, 80, 80), prize_count=3, player=0)
    _, cp, _, _ = extract_features(mk_obs(counter_us, counter_opp), 0,
                                   GameStateTracker())
    printed = ft.cd.CardRegistry.load().get(796).attacks[0].total_cost
    assert abs(float(cp[0][ATTACK0_COST]) - max(0, printed - 1) / 5) < 1e-6

    print("  test_effect_bakes PASSED")


def test_stadium_global_onehot():
    our = mk_player(active=mk_poke(Charcadet, 80, 80), player=0)
    opp = mk_player(active=mk_poke(BUDEW, 30, 30, player=1),
                    hand_count=5, player=1)

    for expected_idx, stadium_id in enumerate(ft.STADIUM_IDS):
        _, _, _, glob = extract_features(
            mk_obs(our, opp, stadium_id=stadium_id), 0, GameStateTracker())
        expected = [0.0] * 6
        expected[expected_idx] = 1.0
        assert glob[18:].tolist() == expected, (stadium_id, glob[18:].tolist())

    # Stadiums outside the selected six do not set any stadium feature.
    _, _, _, glob = extract_features(
        mk_obs(our, opp, stadium_id=1251), 0, GameStateTracker())
    assert glob[18:].tolist() == [0.0] * 6

    print("  test_stadium_global_onehot PASSED")


def test_engine_energy_attached_flag():
    """The engine-owned per-turn flag is the sole source for global dim 6."""
    our = mk_player(active=mk_poke(Charcadet, 80, 80))
    opp = mk_player(active=mk_poke(BUDEW, 30, 30, player=1), player=1)

    _, _, _, before = extract_features(
        mk_obs(our, opp, energy_attached=False), 0, GameStateTracker())
    _, _, _, after = extract_features(
        mk_obs(our, opp, energy_attached=True), 0, GameStateTracker())

    assert before[6] == 0.0
    assert after[6] == 1.0
    print("  test_engine_energy_attached_flag PASSED")


def get_ov(cid):
    from attack_overrides import get_override
    return get_override(cid)


if __name__ == "__main__":
    test_early_game()
    test_prizes_resolved()
    test_item_lock()
    test_status_and_no_opp_active()
    test_keyword_tier_and_new_in_play()
    test_reviewed_overrides_and_dynamic_damage()
    test_effect_bakes()
    test_stadium_global_onehot()
    test_engine_energy_attached_flag()
    print("test_features ALL PASSED")
