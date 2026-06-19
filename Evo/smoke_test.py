"""
smoke_test.py — self-play timing benchmark.

Both players use the Clefable MCTS agent.  Prints per-turn MCTS latency and a
summary at the end.

Usage (from project root):
    python smoke_test.py              # full budget (20 s/turn)
    python smoke_test.py --budget 5   # quick mode  ( 5 s/turn)
    python smoke_test.py --budget 2   # fast sanity  ( 2 s/turn)
"""
import os
import sys
import time

# ── CLI ───────────────────────────────────────────────────────────────────────
budget_override: float | None = None
if "--budget" in sys.argv:
    idx = sys.argv.index("--budget")
    budget_override = float(sys.argv[idx + 1])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR    = os.path.join(PROJECT_ROOT, "Clefable-Agent")

# ── 1. Wire cg_download/ as the importable 'cg' package ──────────────────────
sys.path.insert(0, PROJECT_ROOT)
import cg_download
import cg_download.api
import cg_download.game
import cg_download.sim
import cg_download.utils
sys.modules.setdefault("cg",        cg_download)
sys.modules.setdefault("cg.api",    cg_download.api)
sys.modules.setdefault("cg.game",   cg_download.game)
sys.modules.setdefault("cg.sim",    cg_download.sim)
sys.modules.setdefault("cg.utils",  cg_download.utils)

from cg_download.game import battle_finish, battle_select, battle_start

# ── 2. Import agent — deck.csv is resolved relative to AGENT_DIR ─────────────
os.chdir(AGENT_DIR)
sys.path.insert(0, AGENT_DIR)
import main as agent_mod

agent   = agent_mod.agent
MY_DECK = agent_mod.MY_DECK
print(f"Deck loaded: {len(MY_DECK)} cards")

if budget_override is not None:
    agent_mod._BUDGET_NORMAL = budget_override
    agent_mod._BUDGET_CRUNCH = budget_override
    agent_mod._BUDGET_FINAL  = budget_override
    print(f"Budget override: {budget_override}s/turn")
else:
    print(f"Budget: {agent_mod._BUDGET_NORMAL}s normal / "
          f"{agent_mod._BUDGET_CRUNCH}s crunch / "
          f"{agent_mod._BUDGET_FINAL}s final")


# ── 3. Game runner ─────────────────────────────────────────────────────────────
def run_game(game_num: int, verbose: bool = True) -> dict:
    agent_mod._game_start = None   # fresh clock for each game

    obs, start_data = battle_start(MY_DECK, MY_DECK)
    if start_data.errorPlayer >= 0:
        codes = {1: "invalid card ID", 2: "too many copies",
                 3: "no basic Pokémon", 4: "multiple ACE SPEC"}
        raise RuntimeError(
            f"Deck error: player={start_data.errorPlayer} "
            f"type={start_data.errorType} ({codes.get(start_data.errorType, '?')})"
        )

    mcts_times  : list[float] = []
    greedy_times: list[float] = []
    mcts_turn   = 0
    total_steps = 0
    game_t0     = time.time()

    while True:
        result = obs.get("current", {}).get("result", -1)
        if result >= 0:
            break

        sel = obs.get("select")
        if sel is None:
            action = MY_DECK
        else:
            context  = sel.get("context", -1)
            is_main  = (context == 0)   # SelectContext.MAIN == 0
            player   = obs.get("current", {}).get("yourIndex", "?")

            t0      = time.time()
            action  = agent(obs)
            elapsed = time.time() - t0

            if is_main:
                mcts_turn += 1
                mcts_times.append(elapsed)
                if verbose:
                    print(f"  g{game_num} mcts-turn {mcts_turn:3d} "
                          f"p{player}  {elapsed:6.3f}s  action={action}")
            else:
                greedy_times.append(elapsed)

        total_steps += 1
        obs = battle_select(action)

    battle_finish()
    wall = time.time() - game_t0

    return {
        "result":        obs.get("current", {}).get("result", -1),
        "wall_s":        wall,
        "mcts_turns":    len(mcts_times),
        "total_steps":   total_steps,
        "avg_mcts_s":    sum(mcts_times)   / len(mcts_times)   if mcts_times   else 0.0,
        "max_mcts_s":    max(mcts_times,   default=0.0),
        "min_mcts_s":    min(mcts_times,   default=0.0),
        "avg_greedy_s":  sum(greedy_times) / len(greedy_times) if greedy_times else 0.0,
    }


# ── 4. Run ────────────────────────────────────────────────────────────────────
print("\n=== Self-play smoke test ===\n")
try:
    stats = run_game(1, verbose=True)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

w = stats["result"]
print(f"""
{'='*50}
Result:          player {w} wins  (2 = draw)
Wall time:       {stats['wall_s']:.1f}s
MCTS turns:      {stats['mcts_turns']}
Total steps:     {stats['total_steps']}
Avg MCTS/turn:   {stats['avg_mcts_s']:.3f}s
Max MCTS/turn:   {stats['max_mcts_s']:.3f}s
Min MCTS/turn:   {stats['min_mcts_s']:.3f}s
Avg greedy/step: {stats['avg_greedy_s']*1000:.2f}ms
{'='*50}
""")
