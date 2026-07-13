"""
Smoke test for Ceruledge-RL PrizeTracker (prize_check.py).

Part 1: unit checks on synthetic observations (no sim).
Part 2: full sim games (policy vs random) asserting every step that the
        tracker's prize counts match the actual remaining prizes.

Run from project root: python smoke_test_prize_check.py
"""

import sys
import traceback
import os
from collections import Counter
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

import cg_download, cg_download.api, cg_download.game, cg_download.sim, cg_download.utils
sys.modules.setdefault("cg",       cg_download)
sys.modules.setdefault("cg.api",   cg_download.api)
sys.modules.setdefault("cg.game",  cg_download.game)
sys.modules.setdefault("cg.sim",   cg_download.sim)
sys.modules.setdefault("cg.utils", cg_download.utils)

from cg_download.game import battle_start, battle_finish, battle_select
from cg_download.api import to_observation_class, SelectContext

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Ceruledge-RL"))

from features import FULL_DECK, DECK_CARDS, Ceruledge_ex
from prize_check import PrizeTracker
from random_agent import random_agent

N_GAMES   = 10
MAX_STEPS = 500


# ── Part 1: unit checks on synthetic observations ──────────────────────────────

def _card(cid, serial):
    return NS(id=cid, serial=serial)

def _poke(cid, serial, energies=(), pre=()):
    return NS(id=cid, serial=serial,
              energyCards=list(energies), tools=[], preEvolution=list(pre))

def _obs(hand=(), discard=(), active=(), bench=(), deck=None):
    ps = NS(hand=list(hand), discard=list(discard),
            active=list(active), bench=list(bench), prize=[None] * 6)
    opp = NS(hand=None, discard=[], active=[], bench=[], prize=[None] * 6)
    return NS(current=NS(players=[ps, opp], stadium=[], looking=None),
              select=NS(deck=list(deck) if deck is not None else None, effect=None))

def unit_tests():
    # Deal a deterministic "game": assign serials 0..59 to FULL_DECK in order.
    all_cards = [_card(cid, i) for i, cid in enumerate(FULL_DECK)]
    prizes    = all_cards[:6]            # what we pretend got prized
    hand      = all_cards[6:11]
    disc      = all_cards[11:13]
    active    = [_poke(Ceruledge_ex, all_cards[13].serial,
                       energies=all_cards[14:16],
                       pre=[all_cards[16]])]
    # give the poke stubs real ids from their card slots
    active[0].id = all_cards[13].id
    deck      = all_cards[17:]

    t = PrizeTracker()

    # 1. fresh tracker is unknown
    assert t.vector() == [0]*15 + [1], "fresh tracker should be unknown"

    # 2. update without a deck search stays unknown
    t.update(_obs(hand=hand, discard=disc), our_idx=0)
    assert t.vector() == [0]*15 + [1], "no deck search -> still unknown"

    # 3. elimination on deck search
    t.update(_obs(hand=hand, discard=disc, active=active, deck=deck), our_idx=0)
    v = t.vector()
    assert v[15] == 0, "flag should clear after search"
    expected = Counter(c.id for c in prizes)
    got      = {DECK_CARDS[i]: v[i] for i in range(15) if v[i]}
    assert got == dict(expected), f"elimination wrong: {got} != {dict(expected)}"
    assert sum(v[:15]) == 6

    # 4. pre-evolution card under the active was NOT counted as prized
    pre_id = all_cards[16].id
    assert t.prize_counts[pre_id] == Counter(c.id for c in prizes)[pre_id], \
        "preEvolution card leaked into prize counts"

    # 5. taken prize detected by new serial in hand
    taken = prizes[0]
    t.update(_obs(hand=hand + [taken], discard=disc, active=active), our_idx=0)
    v2 = t.vector()
    assert sum(v2[:15]) == 5, "prize take not detected"
    assert v2[DECK_CARDS.index(taken.id)] == expected[taken.id] - 1

    # 6. re-seeing the same serial doesn't double-decrement
    t.update(_obs(hand=hand + [taken], discard=disc, active=active), our_idx=0)
    assert t.vector() == v2, "double decrement on re-seen serial"

    print("Unit tests: all passed.\n")


# ── Part 2: full sim games ──────────────────────────────────────────────────────

def run_game(game_num: int, our_side: int):
    obs_dict, start = battle_start(FULL_DECK, FULL_DECK)
    if obs_dict is None:
        print("  [!] battle_start returned None")
        return False

    pt       = PrizeTracker()
    step     = 0
    known_at = None
    takes    = 0
    ok       = True

    while True:
        obs    = to_observation_class(obs_dict)
        result = obs.current.result if obs.current else -1

        if result >= 0 or step >= MAX_STEPS:
            break

        your_idx = obs.current.yourIndex
        ctx      = obs.select.context if obs.select else None

        if your_idx == our_side:
            was_known = pt.prizes_known
            pt.update(obs, our_side)
            v  = pt.vector()
            ps = obs.current.players[our_side]

            if not pt.prizes_known:
                if v != [0]*15 + [1]:
                    print(f"  [FAIL] step {step}: unknown-state vector wrong: {v}")
                    ok = False
            else:
                if known_at is None:
                    known_at = step
                    comp = {DECK_CARDS[i]: v[i] for i in range(15) if v[i]}
                    print(f"  prizes known at step {step}: {comp}")
                if any(c < 0 for c in v[:15]):
                    print(f"  [FAIL] step {step}: negative count: {v}")
                    ok = False
                if sum(v[:15]) != len(ps.prize):
                    print(f"  [FAIL] step {step}: sum(counts)={sum(v[:15])} "
                          f"but {len(ps.prize)} prizes remain")
                    ok = False
                if was_known and sum(v[:15]) < 6 and takes < 6 - sum(v[:15]):
                    takes = 6 - sum(v[:15])

        try:
            # Both sides play randomly — random exploration reliably triggers
            # deck searches (Ultra Ball / Poke Pad) and prize takes, which is
            # what the tracker needs to see. The tracker only observes.
            action = random_agent(obs_dict)
        except Exception:
            print(f"  [ERROR] agent crashed at step {step}, context={ctx}")
            traceback.print_exc()
            battle_finish()
            return False

        try:
            obs_dict = battle_select(action)
        except Exception:
            print(f"  [ERROR] battle_select failed at step {step}, action={action}")
            traceback.print_exc()
            battle_finish()
            return False

        step += 1

    battle_finish()
    searched = "yes" if known_at is not None else "NO DECK SEARCH"
    print(f"  Game {game_num}: {step} steps, deck searched: {searched}, "
          f"prize takes detected: {takes}, invariants: {'OK' if ok else 'FAILED'}")
    return ok


if __name__ == "__main__":
    unit_tests()

    print(f"Sim test: {N_GAMES} games (random vs random, tracker observing)\n")
    all_ok = True
    for i in range(1, N_GAMES + 1):
        our_side = i % 2
        print(f"Game {i} (us=player{our_side}):")
        try:
            all_ok &= run_game(i, our_side)
        except Exception:
            print(f"  [FATAL] game {i}")
            traceback.print_exc()
            all_ok = False

    print(f"\n{'ALL PASSED' if all_ok else 'FAILURES DETECTED'}")
    sys.exit(0 if all_ok else 1)
