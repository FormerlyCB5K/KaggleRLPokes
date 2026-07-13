"""
Canonical live smoke test for the Ceruledge-RL policy/encoder (spec 02 Verification).

Plays full games (policy vs random) through the real engine — mirror plus a foreign
(Clefable) opponent deck. At every decision of ours it runs extract_features + a model
forward and asserts: correct shapes (9x19, 9x75, 4x16, 24), all feature values in
[0, 1], no NaNs/infs anywhere. Engine errors are reported with full selection context.

Run from project root: python smoke_test_encoder.py
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

import cg_download, cg_download.api, cg_download.game, cg_download.sim, cg_download.utils
sys.modules.setdefault("cg",       cg_download)
sys.modules.setdefault("cg.api",   cg_download.api)
sys.modules.setdefault("cg.game",  cg_download.game)
sys.modules.setdefault("cg.sim",   cg_download.sim)
sys.modules.setdefault("cg.utils", cg_download.utils)

from cg_download.game import battle_start, battle_finish, battle_select
from cg_download.api import LogType, OptionType, to_observation_class, SelectContext

# Ceruledge-RL modules must shadow any same-named root modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "Ceruledge-RL"))

import torch

from features import FULL_DECK, GameStateTracker, extract_features
from model import CeruledgePolicy
from actions import select_action
from random_agent import random_agent
from train import _setup_active, _setup_bench, _answer_yes_no

N_GAMES   = 5
MAX_STEPS = 500

# A non-mirror opponent deck so the opponent encoder sees foreign cards
# (types, rules, tag tiers it never meets in the Ceruledge mirror).
_CLEFABLE_DECK_CSV = os.path.join(os.path.dirname(__file__),
                                  "Clefable-Agent", "deck.csv")


def _load_deck(path: str) -> list[int]:
    with open(path, encoding="utf-8") as fh:
        return [int(line.strip()) for line in fh if line.strip()]


def assert_encoder_output(our_p, opp_p, zones, glob, where: str):
    assert our_p.shape == (9, 19), f"{where}: our_pokemon {tuple(our_p.shape)}"
    assert opp_p.shape == (9, 75), f"{where}: opp_pokemon {tuple(opp_p.shape)}"
    assert zones.shape == (4, 16), f"{where}: zones {tuple(zones.shape)}"
    assert glob.shape == (24,),    f"{where}: global {tuple(glob.shape)}"
    for name, t in (("our", our_p), ("opp", opp_p), ("zones", zones), ("glob", glob)):
        assert torch.isfinite(t).all(), f"{where}: non-finite in {name}"
        assert float(t.min()) >= 0.0 and float(t.max()) <= 1.0, (
            f"{where}: {name} outside [0,1] (min={float(t.min()):.4f}, "
            f"max={float(t.max()):.4f})")


def assert_live_evolution_flags(obs, our_idx: int, our_p, tracker, where: str) -> int:
    """Every friendly EVOLVE log must mark that exact board word as new in play."""
    ps = obs.current.players[our_idx]
    slots = [ps.active[0] if ps.active else None]
    slots.extend((ps.bench or [])[:8])
    slots.extend([None] * (9 - len(slots)))

    checked = 0
    for log in (obs.logs or []):
        if log.type != LogType.EVOLVE or log.playerIndex != our_idx:
            continue
        assert log.serial is not None, f"{where}: EVOLVE log has no evolved serial"
        assert log.serial in tracker.evolved_serials, (
            f"{where}: evolved serial {log.serial} missing from tracker")
        matching = [i for i, poke in enumerate(slots)
                    if poke is not None and poke.serial == log.serial]
        assert len(matching) == 1, (
            f"{where}: evolved serial {log.serial} maps to board slots {matching}")
        slot = matching[0]
        assert our_p[slot, 8] == 1.0, (
            f"{where}: evolved slot {slot} did not set new_in_play")
        checked += 1
    return checked


def run_game(game_num: int, model: CeruledgePolicy, our_side: int, go_first: bool,
             opp_deck: list[int] | None = None) -> tuple[int, int]:
    decks = [FULL_DECK, FULL_DECK]
    if opp_deck is not None:
        decks[1 - our_side] = opp_deck
    obs_dict, start = battle_start(decks[0], decks[1])
    if obs_dict is None:
        print("  [!] battle_start returned None")
        return 0, 0

    tracker = GameStateTracker()
    step = 0
    n_checked = 0
    n_evolution_checked = 0

    while True:
        obs    = to_observation_class(obs_dict)
        result = obs.current.result if obs.current else -1
        if result >= 0:
            who = "policy" if result == our_side else ("draw" if result == 2 else "random")
            print(f"  Game {game_num}: {step} steps, {n_checked} encoder checks, "
                  f"{n_evolution_checked} evolution checks, winner={who}")
            break
        if step >= MAX_STEPS:
            print(f"  Game {game_num} hit step cap ({MAX_STEPS}), {n_checked} checks")
            break

        your_idx = obs.current.yourIndex
        ctx      = obs.select.context if obs.select else None

        if your_idx == our_side:
            if ctx == SelectContext.IS_FIRST:
                action = _answer_yes_no(obs, yes=go_first)
            elif ctx == SelectContext.SETUP_ACTIVE_POKEMON:
                action = _setup_active(obs)
            elif ctx == SelectContext.SETUP_BENCH_POKEMON:
                action = _setup_bench(obs)
            else:
                # encoder + model forward under assertion (tracker's obs-id guard
                # keeps the follow-up select_action from double-processing logs)
                our_p, opp_p, zones, glob = extract_features(obs, our_side, tracker)
                where = f"game {game_num} step {step} ctx={ctx}"
                assert_encoder_output(our_p, opp_p, zones, glob, where)
                n_evolution_checked += assert_live_evolution_flags(
                    obs, our_side, our_p, tracker, where)
                with torch.no_grad():
                    words, pooled, logits, value = model(
                        our_p.unsqueeze(0), opp_p.unsqueeze(0),
                        zones.unsqueeze(0), glob.unsqueeze(0))
                assert words.shape == (1, 23, 64), words.shape
                assert torch.isfinite(words).all() and torch.isfinite(logits).all()
                n_checked += 1

                # Exercise the evolution tracker whenever the engine offers a legal
                # evolve. Other decisions continue through the real policy path.
                evolve_i = next((i for i, opt in enumerate(obs.select.option)
                                 if opt.type == OptionType.EVOLVE), None)
                if evolve_i is not None:
                    action = [evolve_i]
                else:
                    action, _ = select_action(
                        obs, our_side, model, tracker, greedy=True)
                if not action:
                    action = [0]
        else:
            if ctx == SelectContext.IS_FIRST:
                action = _answer_yes_no(obs, yes=not go_first)
            else:
                action = random_agent(obs_dict)

        if not isinstance(action, list) or not action:
            raise RuntimeError(f"game {game_num} step {step}: bad action {action!r}")

        try:
            obs_dict = battle_select(action)
        except Exception as exc:
            sel = obs.select
            raise RuntimeError(
                f"battle_select failed at game {game_num} step {step}: action={action}, "
                f"context={ctx}, minCount={sel.minCount}, maxCount={sel.maxCount}, "
                f"n_opts={len(sel.option)}, "
                f"effect={sel.effect.id if sel.effect else None}") from exc
        step += 1

    battle_finish()
    return n_checked, n_evolution_checked


if __name__ == "__main__":
    print(f"Encoder smoke test: policy vs random ({N_GAMES} games)\n")
    model = CeruledgePolicy()
    model.eval()

    clefable = _load_deck(_CLEFABLE_DECK_CSV)
    # first N_GAMES: mirror; then N_GAMES vs the Clefable deck (foreign opponent cards)
    schedule = [(i, None) for i in range(1, N_GAMES + 1)] + \
               [(i, clefable) for i in range(N_GAMES + 1, 2 * N_GAMES + 1)]

    total_checks = 0
    total_evolution_checks = 0
    failed = False
    for i, opp_deck in schedule:
        our_side = i % 2
        go_first = (i // 2) % 2 == 0
        label = "mirror" if opp_deck is None else "vs Clefable deck"
        try:
            print(f"Game {i} ({label}):")
            checks, evolution_checks = run_game(
                i, model, our_side, go_first, opp_deck)
            total_checks += checks
            total_evolution_checks += evolution_checks
        except AssertionError:
            failed = True
            print(f"  [ENCODER ASSERTION FAILED] game {i}")
            traceback.print_exc()
            battle_finish()
        except Exception:
            failed = True
            print(f"  [FATAL] game {i}")
            traceback.print_exc()
            battle_finish()

    if failed:
        print(f"\nsmoke_test_encoder FAILED")
        sys.exit(1)
    if total_evolution_checks == 0:
        print("\nsmoke_test_encoder FAILED: no live evolution was exercised")
        sys.exit(1)
    print(f"\nsmoke_test_encoder PASSED ({total_checks} encoder checks across "
          f"{len(schedule)} games; {total_evolution_checks} live evolution checks)")
