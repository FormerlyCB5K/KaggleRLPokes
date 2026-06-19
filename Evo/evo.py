"""
evo.py — Evolutionary weight tuner for the Clefable MCTS agent.

Strategy
--------
- Population of POPULATION_SIZE candidates per generation.
  * Candidate 0 is the current reference (no mutation).
  * Candidates 1–(N-1) are Gaussian-mutated copies of the reference.
- Each candidate plays GAMES_PER_CAND games against the reference
  (alternating who is player 0 to remove first-player bias).
- Best candidate (highest win rate) becomes the new reference next generation.
- Mutation σ decays linearly from SIGMA_INIT to SIGMA_FINAL over all generations.
- All games run in parallel via ProcessPoolExecutor (up to MAX_WORKERS cores).

Usage
-----
    python evo.py                  # full run
    python evo.py --generations 3  # quick test

Output
------
    evo_output/gen_<N>_weights.json   — best weights after each generation
    evo_output/history.json           — win rates + weights per generation
"""

import argparse
import concurrent.futures
import importlib.util
import json
import os
import random
import sys
import time

# ── Configuration ──────────────────────────────────────────────────────────────
POPULATION_SIZE  = 5     # total candidates (1 reference + 4 mutations)
N_GENERATIONS    = 10
GAMES_PER_CAND   = 10    # games each candidate plays vs reference
EVAL_BUDGET_S    = 0.5   # s/turn during evaluation (fast mode)
MAX_WORKERS      = 20    # CPU cores to use

SIGMA_INIT  = 0.40   # relative σ at generation 0
SIGMA_FINAL = 0.05   # relative σ at generation N_GENERATIONS - 1

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_DIR    = os.path.join(PROJECT_ROOT, "Clefable-Agent")
OUTPUT_DIR   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evo_output")


# ── Weight extraction ──────────────────────────────────────────────────────────

def _load_weights_from_module() -> dict[str, float]:
    """Read all W_* constants from weights.py (not HEURISTIC_NORM)."""
    spec = importlib.util.spec_from_file_location(
        "_evo_weights_src", os.path.join(AGENT_DIR, "weights.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {
        name: float(getattr(mod, name))
        for name in dir(mod)
        if name.startswith("W_")
    }


# ── Mutation ───────────────────────────────────────────────────────────────────

def _sigma_for_gen(gen: int) -> float:
    """Linear decay from SIGMA_INIT (gen 0) to SIGMA_FINAL (gen N-1)."""
    if N_GENERATIONS <= 1:
        return SIGMA_INIT
    t = gen / (N_GENERATIONS - 1)
    return SIGMA_INIT + t * (SIGMA_FINAL - SIGMA_INIT)


def _mutate(weights: dict[str, float], sigma: float, rng: random.Random) -> dict[str, float]:
    """Apply Gaussian noise scaled relative to each weight's magnitude."""
    result = {}
    for k, v in weights.items():
        scale = abs(v) if v != 0.0 else 0.1
        result[k] = v + rng.gauss(0.0, sigma * scale)
    return result


# ── Per-game worker ────────────────────────────────────────────────────────────

def _load_agent_module(module_name: str, agent_dir: str):
    """Load main.py as a fresh module with the given name."""
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(agent_dir, "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _wire_cg(project_root: str) -> None:
    """Register cg_download as the 'cg' package if not already done."""
    if "cg" in sys.modules:
        return
    sys.path.insert(0, project_root)
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


def _run_single_game(
    cand_weights: dict[str, float],
    ref_weights:  dict[str, float],
    cand_is_p0:   bool,
    budget_s:     float,
    project_root: str,
    agent_dir:    str,
) -> float:
    """
    Run one game between the candidate and the reference agent.

    Returns 1.0 if the candidate wins, 0.0 if the reference wins or it's a draw.
    This function runs in a worker process (fresh Python interpreter each time).
    """
    _wire_cg(project_root)
    from cg_download.game import battle_finish, battle_select, battle_start

    os.chdir(agent_dir)
    sys.path.insert(0, agent_dir)

    cand_mod = _load_agent_module("_evo_cand", agent_dir)
    ref_mod  = _load_agent_module("_evo_ref",  agent_dir)

    # Patch weight constants into each module
    for k, v in cand_weights.items():
        setattr(cand_mod, k, v)
    for k, v in ref_weights.items():
        setattr(ref_mod, k, v)

    # Override time budgets for fast evaluation
    for mod in (cand_mod, ref_mod):
        mod._BUDGET_NORMAL = budget_s
        mod._BUDGET_CRUNCH = budget_s
        mod._BUDGET_FINAL  = budget_s
        mod._game_start    = None

    # Assign player slots
    if cand_is_p0:
        p0_mod, p1_mod = cand_mod, ref_mod
        cand_index = 0
    else:
        p0_mod, p1_mod = ref_mod, cand_mod
        cand_index = 1

    obs, start_data = battle_start(cand_mod.MY_DECK, ref_mod.MY_DECK)
    if start_data.errorPlayer >= 0:
        raise RuntimeError(
            f"Deck error: player={start_data.errorPlayer} "
            f"type={start_data.errorType}"
        )

    while True:
        result = obs.get("current", {}).get("result", -1)
        if result >= 0:
            break

        sel        = obs.get("select")
        your_index = obs.get("current", {}).get("yourIndex", 0)
        acting_mod = p0_mod if your_index == 0 else p1_mod

        if sel is None:
            action = acting_mod.MY_DECK
        else:
            action = acting_mod.agent(obs)

        obs = battle_select(action)

    battle_finish()

    final_result = obs.get("current", {}).get("result", -1)
    return 1.0 if final_result == cand_index else 0.0


# ── Evaluation of one candidate ───────────────────────────────────────────────

def _submit_candidate_games(
    executor:      concurrent.futures.ProcessPoolExecutor,
    cand_weights:  dict[str, float],
    ref_weights:   dict[str, float],
    cand_idx:      int,
    n_games:       int,
    budget_s:      float,
) -> list[concurrent.futures.Future]:
    """Submit n_games futures for one candidate, alternating first-player."""
    futures = []
    for g in range(n_games):
        cand_is_p0 = (g % 2 == 0)
        fut = executor.submit(
            _run_single_game,
            cand_weights,
            ref_weights,
            cand_is_p0,
            budget_s,
            PROJECT_ROOT,
            AGENT_DIR,
        )
        futures.append(fut)
    return futures


# ── Main evolutionary loop ────────────────────────────────────────────────────

def run_evolution(n_generations: int = N_GENERATIONS) -> dict[str, float]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    ref_weights = _load_weights_from_module()
    history: list[dict] = []
    rng = random.Random()

    print(f"Starting evolution: {POPULATION_SIZE} candidates, "
          f"{n_generations} generations, {GAMES_PER_CAND} games/candidate")
    print(f"σ schedule: {SIGMA_INIT:.2f} → {SIGMA_FINAL:.2f}")
    print(f"Parallel workers: {MAX_WORKERS}\n")

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for gen in range(n_generations):
            sigma = _sigma_for_gen(gen)
            t_gen_start = time.time()

            # Build population: [reference, mutation1, ..., mutationN-1]
            mutations = [ref_weights] + [
                _mutate(ref_weights, sigma, rng)
                for _ in range(POPULATION_SIZE - 1)
            ]

            # Submit all games in parallel
            all_futures: list[list[concurrent.futures.Future]] = []
            for cand_idx, cand_w in enumerate(mutations):
                # Reference always plays itself (win rate = baseline ~50%)
                # so we measure the mutants against the same reference.
                futs = _submit_candidate_games(
                    executor, cand_w, ref_weights, cand_idx,
                    GAMES_PER_CAND, EVAL_BUDGET_S
                )
                all_futures.append(futs)

            # Collect results
            win_rates = []
            for cand_idx, futs in enumerate(all_futures):
                wins   = 0
                errors = 0
                for fut in concurrent.futures.as_completed(futs):
                    try:
                        wins += fut.result()
                    except Exception as e:
                        print(f"  [gen {gen}][cand {cand_idx}] game error: {e}")
                        errors += 1
                valid_games = GAMES_PER_CAND - errors
                wr = wins / valid_games if valid_games > 0 else 0.0
                win_rates.append(wr)
                print(f"  gen {gen:2d} | cand {cand_idx} | σ={sigma:.3f} | "
                      f"wins={int(wins)}/{valid_games} | wr={wr:.3f}"
                      + (" [reference]" if cand_idx == 0 else ""))

            # Select best candidate (highest win rate)
            best_idx = max(range(POPULATION_SIZE), key=lambda i: win_rates[i])
            best_wr  = win_rates[best_idx]
            best_w   = mutations[best_idx]

            t_gen = time.time() - t_gen_start
            print(f"  → gen {gen}: best cand={best_idx} wr={best_wr:.3f}  "
                  f"({t_gen:.0f}s)\n")

            # Update reference
            ref_weights = best_w

            # Save
            out_path = os.path.join(OUTPUT_DIR, f"gen_{gen:02d}_weights.json")
            with open(out_path, "w") as f:
                json.dump({"generation": gen, "win_rate": best_wr,
                           "weights": best_w}, f, indent=2)

            history.append({
                "generation": gen,
                "sigma": sigma,
                "win_rates": win_rates,
                "best_candidate": best_idx,
                "best_win_rate": best_wr,
            })

    # Save history
    history_path = os.path.join(OUTPUT_DIR, "history.json")
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)

    print(f"Evolution complete. Best weights saved to {OUTPUT_DIR}/")
    return ref_weights


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evolutionary weight tuner")
    parser.add_argument("--generations", type=int, default=N_GENERATIONS,
                        help=f"Number of generations (default: {N_GENERATIONS})")
    parser.add_argument("--budget", type=float, default=EVAL_BUDGET_S,
                        help=f"Turn budget in seconds (default: {EVAL_BUDGET_S})")
    args = parser.parse_args()

    EVAL_BUDGET_S = args.budget
    run_evolution(n_generations=args.generations)
