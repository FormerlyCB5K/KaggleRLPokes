"""
test_dispatch.py — Spec 09b validation: side-aware dispatch & native decks.

Runs collect_episode() against every registry opponent on both sides, with
spies on train.battle_start / train.battle_select, asserting:

  1. every game runs to a terminal result (reward in {-1, 0, +1})
  2. the opponent's revealed cards are a subset of its registry deck, and
     non-Ceruledge opponents reveal cards outside FULL_DECK (deck really
     swapped, not silently left as Ceruledge)
  3. our deck is FULL_DECK on whichever side we occupy, the opponent deck on
     the other (battle_start argument order)
  4. recorded Steps carry finite tensors (feature extraction survived foreign
     opponent cards — spec 09b validation step 6)

Run from the repo root:
    .venv/Scripts/python.exe Ceruledge-RL/test_dispatch.py
"""
from __future__ import annotations

import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root: cg_download
sys.path.insert(0, _HERE)                    # Ceruledge-RL first

sys.argv = ["test_dispatch.py", "--no-wandb"]  # train.py parses argv at import
import torch

import train as T
from features import FULL_DECK
from opponents import resolve_opponent
from test_support import bounded_collect_episode

FULL_SET = set(FULL_DECK)
SEED_ORDER = ["ceruledge_rules", "clefable", "alakazam", "archaludon", "garchomp", "lucario", "random", "self"]
NON_CERULEDGE = {"clefable", "alakazam", "archaludon", "garchomp", "lucario"}


def _harvest(obs_dict, opp_idx: int, revealed: set[int]) -> None:
    """Accumulate opponent-side card ids visible in a raw obs dict."""
    players = (obs_dict or {}).get("current", {}).get("players") or []
    if opp_idx >= len(players):
        return
    ps = players[opp_idx] or {}
    for c in (ps.get("discard") or []):
        if c and c.get("id") is not None:
            revealed.add(c["id"])
    for zone in ("active", "bench"):
        for p in (ps.get(zone) or []):
            if not p:
                continue
            if p.get("id") is not None:
                revealed.add(p["id"])
            for key in ("energyCards", "tools"):
                for c in (p.get(key) or []):
                    if c and c.get("id") is not None:
                        revealed.add(c["id"])


def run_spied_episode(model, opponent, our_side, go_first, opponent_model=None, context=""):
    captured: dict = {}
    revealed: set[int] = set()
    opp_idx = 1 - our_side
    real_start, real_select = T.battle_start, T.battle_select

    def spy_start(deck0, deck1):
        captured["decks"] = (list(deck0), list(deck1))
        obs = real_start(deck0, deck1)
        _harvest(obs[0] if isinstance(obs, tuple) else obs, opp_idx, revealed)
        return obs

    def spy_select(selected):
        obs_dict = real_select(selected)
        _harvest(obs_dict, opp_idx, revealed)
        return obs_dict

    T.battle_start, T.battle_select = spy_start, spy_select
    try:
        steps, reward = bounded_collect_episode(
            T, model, 0.0, our_side, go_first, opponent, opponent_model, context=context,
        )
    finally:
        T.battle_start, T.battle_select = real_start, real_select
    return steps, reward, captured, revealed


def main() -> None:
    model = T.CeruledgePolicy()
    model.eval()

    for name in SEED_ORDER:
        opp = resolve_opponent(name)
        opponent_model = None
        if opp["kind"] == "self":
            opponent_model = copy.deepcopy(model)
            opponent_model.eval()

        revealed_all: set[int] = set()
        for ep in range(2):                      # once per side
            our_side = ep % 2
            steps, reward, cap, revealed = run_spied_episode(
                model, opp, our_side, ep == 0, opponent_model,
                context=f"{name} side={our_side}",
            )

            d0, d1 = cap["decks"]
            ours, theirs = (d0, d1) if our_side == 0 else (d1, d0)
            assert ours == list(FULL_DECK), \
                f"{name} side={our_side}: our deck is not FULL_DECK"
            assert theirs == list(opp["deck"]), \
                f"{name} side={our_side}: opponent deck mismatch"
            assert reward in (-1.0, 0.0, 1.0), \
                f"{name} side={our_side}: no terminal result (reward={reward})"
            for s in steps:
                for t in (s.our_pokemon, s.opp_pokemon, s.zones, s.glob):
                    assert torch.isfinite(t).all(), \
                        f"{name} side={our_side}: non-finite features"
            revealed_all |= revealed

        unknown = revealed_all - set(opp["deck"])
        assert not unknown, f"{name}: revealed cards outside its deck: {unknown}"
        if name in NON_CERULEDGE:
            assert revealed_all - FULL_SET, \
                f"{name}: revealed no cards outside FULL_DECK — deck swap suspect"

        foreign = len(revealed_all - FULL_SET)
        print(f"{name:16s} OK  (both sides terminal, {len(revealed_all)} opponent "
              f"cards seen, {foreign} outside FULL_DECK)", flush=True)

    print("\ntest_dispatch.py passed.")


if __name__ == "__main__":
    main()
