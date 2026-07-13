"""
effect_bake_probe.py — Spec-07 Phase-0 engine-behavior probe.

Question the probe answers: does the observed `Pokemon.maxHp` already include effect
HP (Tools, and — if ever observed — ability/stadium auras)? That determines whether an
`hp_delta` bake would double-count (spec 06 § Double-counting rule).

Method: play random-vs-random games with a deck stuffed with an HP Tool (Hero's Cape,
+100 HP) on cheap Basics. Every observation, for every in-play Pokemon, compare the
observed maxHp to the card's printed HP (card_data) and note attached tools.

Also flags any Pokemon whose observed maxHp exceeds its printed HP with NO tool attached
— that would be an ability/stadium HP aura baked into maxHp (the one case we cannot
force in random play, caught opportunistically here).

Retreat / damage-reduction / weakness-resistance need no probe: the live `Pokemon`
dataclass has no retreatCost/damage-reduction field, and weak/resist come from static
card_data — so baking those cannot double-count against the observation.

Run from repo root:
.venv\\Scripts\\python.exe Ceruledge-RL\\old\\audits\\effect-baking\\effect_bake_probe.py
"""
import os
import sys

_ARCHIVE = os.path.dirname(os.path.abspath(__file__))
_RL = os.path.dirname(os.path.dirname(os.path.dirname(_ARCHIVE)))
sys.path.insert(0, os.path.dirname(_RL))
sys.path.insert(0, _RL)

import cg_download, cg_download.api, cg_download.game, cg_download.sim, cg_download.utils
sys.modules.setdefault("cg", cg_download)
sys.modules.setdefault("cg.api", cg_download.api)
sys.modules.setdefault("cg.game", cg_download.game)
sys.modules.setdefault("cg.sim", cg_download.sim)
sys.modules.setdefault("cg.utils", cg_download.utils)

from cg_download.game import battle_start, battle_finish, battle_select
from cg_download.api import to_observation_class

import card_data as cd
from random_agent import random_agent

# The engine enforces deck legality (4-copy limit, 1 ACE SPEC), and the only generic HP
# Tool (Hero's Cape) is ACE SPEC, so a stuffed HP-tool probe deck is rejected and random
# agents won't reliably attach a single copy. Instead we run a KNOWN-LEGAL real deck
# (deck (2).csv — a Mega Abomasnow deck that runs the Maximum Belt Tool and evolving
# Pokemon) on both sides. This validates the harness and captures the aura signal
# (maxHp > printed with no tool) on real cards over many games.
_REPO = os.path.dirname(_RL)
_DECK_CSV = os.path.join(_REPO, "Decks", "Deck-Builder", "deck (2).csv")


def _load_deck(path):
    with open(path, encoding="utf-8") as fh:
        return [int(x.strip()) for x in fh if x.strip()]


PROBE_DECK = _load_deck(_DECK_CSV)
assert len(PROBE_DECK) == 60, len(PROBE_DECK)

# Second, targeted HP-tool deck: 4 Cynthia's Gible (Basic, 70 HP) + 4 Cynthia's Power
# Weight (+70 HP, non-ACE) + Fighting Energy. Legal (≤4 of each, energy unlimited).
CYNTHIA_GIBLE = 379
CYNTHIA_POWER_WEIGHT = 1173
FIGHTING_ENERGY = 6
HP_TOOL_DECK = [CYNTHIA_GIBLE] * 4 + [CYNTHIA_POWER_WEIGHT] * 4 + [FIGHTING_ENERGY] * 52
assert len(HP_TOOL_DECK) == 60

N_GAMES = 60
MAX_STEPS = 400


def _pokes(ps):
    out = []
    if ps.active:
        out += [p for p in ps.active if p is not None]
    if ps.bench:
        out += [p for p in ps.bench if p is not None]
    return out


def _run(deck, label):
    reg = cd.CardRegistry.load()
    tool_obs = []          # (card_id, printed_hp, observed_maxHp, n_tools)
    aura_flags = []        # tool-free maxHp > printed
    n_tool_attachments = 0

    for g in range(N_GAMES):
        obs_dict, start = battle_start(deck, deck)
        if obs_dict is None:
            print(f"  game {g}: battle_start returned None (deck rejected?)")
            continue
        step = 0
        while True:
            obs = to_observation_class(obs_dict)
            if (obs.current is None) or obs.current.result >= 0 or step >= MAX_STEPS:
                break
            for ps in obs.current.players:
                for p in _pokes(ps):
                    printed = reg.get(p.id).max_hp or 0
                    obs_max = p.maxHp or 0
                    n_tools = len(p.tools or [])
                    if n_tools:
                        tool_obs.append((p.id, printed, obs_max, n_tools))
                        n_tool_attachments += 1
                    elif printed and obs_max > printed:
                        aura_flags.append((p.id, printed, obs_max))
            try:
                obs_dict = battle_select(random_agent(obs_dict))
            except Exception:
                break
            step += 1
        battle_finish()

    print(f"\n=== {label}: {N_GAMES} games ===")
    print(f"tool-attachment observations: {n_tool_attachments}")
    if tool_obs:
        matches = sum(1 for _, pr, mx, _ in tool_obs if mx == pr)
        exceeds = sum(1 for _, pr, mx, _ in tool_obs if mx > pr)
        print(f"  tool-carrying Pokemon, maxHp == printed: {matches}")
        print(f"  tool-carrying Pokemon, maxHp >  printed: {exceeds}  (tool HP baked into maxHp)")
        for row in tool_obs[:6]:
            print(f"    sample: card={row[0]} printed={row[1]} obs_maxHp={row[2]} n_tools={row[3]}")
    else:
        print("  (no tool ever attached in random play — inconclusive for tools)")
    print(f"tool-free maxHp>printed (ability/stadium aura baked into maxHp?): {len(aura_flags)}")
    for row in aura_flags[:6]:
        print(f"    sample: card={row[0]} printed={row[1]} obs_maxHp={row[2]}")


if __name__ == "__main__":
    _run(PROBE_DECK, "Probe A — real deck(2) (damage Tool + evolutions)")
    _run(HP_TOOL_DECK, "Probe B — Cynthia's Power Weight (+70 HP Tool)")
