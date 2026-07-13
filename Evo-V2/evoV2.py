"""
evoV2.py — Evolutionary optimizer for the Clefable MCTS agent.

MegaLucarioBaseline agent authored by prod1gy on Kaggle.
Source: https://www.kaggle.com/code/prod1gy/elo-1150-rule-based-agent-matchup-tests

This is the self-contained Evo-V2/ version. Lucario-Baseline/ is expected
to live inside Evo-V2/ so the whole directory can be transferred as a unit.

Algorithm (paper spec)
----------------------
- Population of POPULATION_SIZE candidates (W_* weight vectors from Clefable-Agent).
- Generation 0: all candidates are Gaussian perturbations of the weights in weights.py.
- Fitness: GAMES_VS_CHAMP + GAMES_VS_BASE games per candidate:
    * vs current generation champion (Clefable), weighted 1x
    * vs MegaLucarioBaseline, weighted 2x
  fitness = (1/3)*champ_wr + (2/3)*lucario_wr
- Elites: top ELITE_COUNT candidates survive unchanged.
- New candidates: tournament selection → uniform crossover → Gaussian mutation.
- Sigma decays linearly from SIGMA_INIT to SIGMA_FINAL across N_GENERATIONS.
- All games run in parallel via ProcessPoolExecutor.

Usage
-----
    python evoV2.py                         # fresh run
    python evoV2.py --resume                # continue from latest checkpoint
    python evoV2.py --generations 20        # run 20 generations
    python evoV2.py --population 10         # 10 candidates per gen
    python evoV2.py --workers 30            # parallelism
    python evoV2.py --games 50             # total evaluation games per candidate

Output
------
    <output-dir>/gen_<N>_weights.json   — champion weights after each gen
    <output-dir>/history.json           — full history of fitness + weights
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import os
import random
import re
import sys
import time

# ── Configuration ──────────────────────────────────────────────────────────────
POPULATION_SIZE  = 8      # candidates per generation
N_GENERATIONS    = 20
GAMES_VS_CHAMP   = 25     # games vs current Clefable generation champion (weight 1x)
GAMES_VS_BASE    = 25     # games vs MegaLucarioBaseline (weight 2x)
# fitness = (1/3)*champ_wr + (2/3)*lucario_wr
ELITE_COUNT      = 2      # top candidates that survive unchanged
DROP_COUNT       = 2      # bottom candidates removed from gene pool each generation
TOURNAMENT_K     = 3      # tournament selection pool size
EVAL_BUDGET_S    = 0.5    # s/turn for Clefable MCTS during evaluation

SIGMA_INIT  = 0.30        # relative Gaussian σ at generation 0
SIGMA_FINAL = 0.05        # relative σ at final generation
MAX_WORKERS = 20

_HERE        = os.path.dirname(os.path.abspath(__file__))
# Self-contained layout: Evo-V2/evoV2.py, Evo-V2/Clefable-Agent/, Evo-V2/Lucario-Baseline/
# PROJECT_ROOT is one level up from Evo-V2 (for cg_download)
PROJECT_ROOT = os.path.dirname(_HERE)
AGENT_DIR    = os.path.join(_HERE, "Clefable-Agent")
OUTPUT_DIR   = os.path.join(_HERE, "evo_output_v2")
_LUCARIO_BASELINE_PATH = os.path.join(_HERE, "Lucario-Baseline", "mega_lucario_baseline.py")


# ── Checkpoint helpers ─────────────────────────────────────────────────────────

def _find_latest_checkpoint() -> tuple[int, dict[str, float]] | None:
    if not os.path.exists(OUTPUT_DIR):
        return None
    best_gen, best_path = -1, None
    for fname in os.listdir(OUTPUT_DIR):
        m = re.match(r"gen_(\d+)_weights\.json", fname)
        if m:
            g = int(m.group(1))
            if g > best_gen:
                best_gen, best_path = g, os.path.join(OUTPUT_DIR, fname)
    if best_path is None:
        return None
    with open(best_path) as f:
        data = json.load(f)
    return best_gen, data["weights"]


def _load_history() -> list[dict]:
    path = os.path.join(OUTPUT_DIR, "history.json")
    return json.load(open(path)) if os.path.exists(path) else []


# ── Weight loading ─────────────────────────────────────────────────────────────

def _load_weights_from_module() -> dict[str, float]:
    """Read all W_* constants from Clefable-Agent/weights.py."""
    spec = importlib.util.spec_from_file_location(
        "_evo_weights_src", os.path.join(AGENT_DIR, "weights.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {name: float(getattr(mod, name)) for name in dir(mod) if name.startswith("W_")}


# ── Mutation and crossover ─────────────────────────────────────────────────────

def _mutate(weights: dict[str, float], sigma: float, rng: random.Random) -> dict[str, float]:
    result = {}
    for k, v in weights.items():
        scale = abs(v) if v != 0.0 else 0.1
        result[k] = v + rng.gauss(0.0, sigma * scale)
    return result


def _crossover(p1: dict[str, float], p2: dict[str, float], rng: random.Random) -> dict[str, float]:
    """Uniform crossover: each weight drawn independently from one parent."""
    return {k: (p1[k] if rng.random() < 0.5 else p2[k]) for k in p1}


def _tournament_select(population: list[dict], fitnesses: list[float], k: int, rng: random.Random) -> dict:
    """Return the best-fitness individual from a random sample of k candidates."""
    k = min(k, len(population))
    indices = rng.sample(range(len(population)), k)
    return population[max(indices, key=lambda i: fitnesses[i])]


# ── Agent loading + cg wiring (per-worker) ────────────────────────────────────

def _load_agent_module(module_name: str, agent_dir: str):
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(agent_dir, "main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _wire_cg(project_root: str) -> None:
    if "cg" in sys.modules and "cg.api" in sys.modules:
        return
    for key in list(sys.modules.keys()):
        if key in {"cg_download", "cg"} or key.startswith(("cg_download.", "cg.")):
            del sys.modules[key]
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    import cg_download
    import cg_download.api
    import cg_download.game
    import cg_download.sim
    import cg_download.utils
    sys.modules["cg"]       = cg_download
    sys.modules["cg.api"]   = cg_download.api
    sys.modules["cg.game"]  = cg_download.game
    sys.modules["cg.sim"]   = cg_download.sim
    sys.modules["cg.utils"] = cg_download.utils


# ── Game runners ───────────────────────────────────────────────────────────────

def _run_game_vs_champ(
    cand_weights:    dict[str, float],
    champ_weights:   dict[str, float],
    cand_is_p0:      bool,
    budget_s:        float,
    project_root:    str,
    agent_dir:       str,
) -> float:
    """Clefable candidate vs Clefable champion. Returns 1.0 if candidate wins."""
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    _wire_cg(project_root)
    from cg_download.game import battle_finish, battle_select, battle_start

    os.chdir(agent_dir)
    sys.path.insert(0, agent_dir)

    cand_mod  = _load_agent_module("_evo_cand",  agent_dir)
    champ_mod = _load_agent_module("_evo_champ", agent_dir)

    for k, v in cand_weights.items():
        setattr(cand_mod, k, v)
    for k, v in champ_weights.items():
        setattr(champ_mod, k, v)

    for mod in (cand_mod, champ_mod):
        mod._BUDGET_NORMAL = budget_s
        mod._BUDGET_CRUNCH = budget_s
        mod._BUDGET_FINAL  = budget_s
        mod._game_start    = None

    if cand_is_p0:
        p0_mod, p1_mod = cand_mod, champ_mod
        cand_index = 0
    else:
        p0_mod, p1_mod = champ_mod, cand_mod
        cand_index = 1

    obs, start = battle_start(cand_mod.MY_DECK, champ_mod.MY_DECK)
    if start.errorPlayer >= 0:
        raise RuntimeError(f"Deck error player={start.errorPlayer} type={start.errorType}")

    while True:
        result = obs.get("current", {}).get("result", -1)
        if result >= 0:
            break
        yi  = obs.get("current", {}).get("yourIndex", 0)
        mod = p0_mod if yi == 0 else p1_mod
        action = mod.MY_DECK if obs.get("select") is None else mod.agent(obs)
        obs = battle_select(action)

    battle_finish()
    return 1.0 if obs.get("current", {}).get("result", -1) == cand_index else 0.0


def _run_game_vs_lucario(
    cand_weights:    dict[str, float],
    cand_is_p0:      bool,
    budget_s:        float,
    project_root:    str,
    agent_dir:       str,
    lucario_path:    str,
) -> float:
    """Clefable candidate vs MegaLucarioBaseline. Returns 1.0 if candidate wins."""
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    _wire_cg(project_root)
    from cg_download.game import battle_finish, battle_select, battle_start
    import importlib.util as _ilu

    os.chdir(agent_dir)
    sys.path.insert(0, agent_dir)

    cand_mod = _load_agent_module("_evo_cand_luc", agent_dir)
    for k, v in cand_weights.items():
        setattr(cand_mod, k, v)
    cand_mod._BUDGET_NORMAL = budget_s
    cand_mod._BUDGET_CRUNCH = budget_s
    cand_mod._BUDGET_FINAL  = budget_s
    cand_mod._game_start    = None

    spec = _ilu.spec_from_file_location("_mega_lucario_base", lucario_path)
    base_mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(base_mod)
    lucario_agent = base_mod.agent
    lucario_deck  = base_mod.DECK

    if cand_is_p0:
        obs, start = battle_start(cand_mod.MY_DECK, lucario_deck)
        cand_index = 0
    else:
        obs, start = battle_start(lucario_deck, cand_mod.MY_DECK)
        cand_index = 1

    if start.errorPlayer >= 0:
        raise RuntimeError(f"Deck error player={start.errorPlayer} type={start.errorType}")

    while True:
        result = obs.get("current", {}).get("result", -1)
        if result >= 0:
            break
        yi = obs.get("current", {}).get("yourIndex", 0)
        is_cand = (yi == cand_index)
        if obs.get("select") is None:
            action = cand_mod.MY_DECK if is_cand else lucario_deck
        else:
            action = cand_mod.agent(obs) if is_cand else lucario_agent(obs)
        obs = battle_select(action)

    battle_finish()
    return 1.0 if obs.get("current", {}).get("result", -1) == cand_index else 0.0


# ── Fitness evaluation ─────────────────────────────────────────────────────────

def _submit_fitness_games(
    executor:      concurrent.futures.ProcessPoolExecutor,
    cand_weights:  dict[str, float],
    champ_weights: dict[str, float],
) -> tuple[list, list]:
    """Submit all evaluation games. Returns (champ_futures, lucario_futures)."""
    champ_futs = [
        executor.submit(
            _run_game_vs_champ, cand_weights, champ_weights,
            g % 2 == 0, EVAL_BUDGET_S, PROJECT_ROOT, AGENT_DIR,
        )
        for g in range(GAMES_VS_CHAMP)
    ]
    lucario_futs = [
        executor.submit(
            _run_game_vs_lucario, cand_weights,
            g % 2 == 0, EVAL_BUDGET_S, PROJECT_ROOT, AGENT_DIR, _LUCARIO_BASELINE_PATH,
        )
        for g in range(GAMES_VS_BASE)
    ]
    return champ_futs, lucario_futs


def _collect_fitness(champ_futs: list, lucario_futs: list, label: str) -> tuple[float, float, float]:
    """Collect results; return (fitness, champ_wr, lucario_wr)."""
    champ_wins = champ_errs = 0
    for fut in concurrent.futures.as_completed(champ_futs):
        try:
            champ_wins += fut.result()
        except Exception as e:
            print(f"    [{label}] champ-game error: {e}")
            champ_errs += 1

    lucario_wins = lucario_errs = 0
    for fut in concurrent.futures.as_completed(lucario_futs):
        try:
            lucario_wins += fut.result()
        except Exception as e:
            print(f"    [{label}] lucario-game error: {e}")
            lucario_errs += 1

    valid_c = GAMES_VS_CHAMP - champ_errs
    valid_l = GAMES_VS_BASE  - lucario_errs
    champ_wr   = champ_wins   / valid_c if valid_c > 0 else 0.0
    lucario_wr = lucario_wins / valid_l if valid_l > 0 else 0.0
    fitness = (1/3) * champ_wr + (2/3) * lucario_wr
    return fitness, champ_wr, lucario_wr


# ── Main evolutionary loop ────────────────────────────────────────────────────

def run_evolution(n_generations: int = N_GENERATIONS, resume: bool = False) -> dict[str, float]:
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    start_gen = 0
    if resume:
        ckpt = _find_latest_checkpoint()
        if ckpt is None:
            print("No checkpoint found — starting fresh.")
            champ_weights = _load_weights_from_module()
        else:
            start_gen, champ_weights = ckpt
            start_gen += 1
            print(f"Resuming from gen {start_gen - 1} checkpoint.")
    else:
        champ_weights = _load_weights_from_module()

    history = _load_history() if resume else []
    rng = random.Random()
    end_gen = start_gen + n_generations

    print(f"{'Resuming' if resume else 'Starting'} evoV2 (Clefable): {POPULATION_SIZE} candidates, "
          f"{n_generations} generations (gen {start_gen}–{end_gen - 1})")
    print(f"Fitness: {GAMES_VS_CHAMP}g vs Clefable champ (1x) + {GAMES_VS_BASE}g vs Lucario (2x)")
    print(f"Elites: {ELITE_COUNT}, drop: {DROP_COUNT}, tournament k={TOURNAMENT_K}")
    print(f"σ: {SIGMA_INIT:.2f} → {SIGMA_FINAL:.2f}, workers: {MAX_WORKERS}\n")

    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for gen in range(start_gen, end_gen):
            run_progress = (gen - start_gen) / max(n_generations - 1, 1)
            sigma = SIGMA_INIT + run_progress * (SIGMA_FINAL - SIGMA_INIT)
            t0 = time.time()

            # Build population
            if gen == start_gen:
                population = [champ_weights] + [
                    _mutate(champ_weights, sigma, rng)
                    for _ in range(POPULATION_SIZE - 1)
                ]
            else:
                ranked_prev = sorted(range(len(prev_pop)),
                                     key=lambda i: prev_fitnesses[i], reverse=True)
                elites   = [prev_pop[i] for i in ranked_prev[:ELITE_COUNT]]
                children = []
                while len(children) < POPULATION_SIZE - ELITE_COUNT:
                    p1 = _tournament_select(prev_pop, prev_fitnesses, TOURNAMENT_K, rng)
                    p2 = _tournament_select(prev_pop, prev_fitnesses, TOURNAMENT_K, rng)
                    child = _mutate(_crossover(p1, p2, rng), sigma, rng)
                    children.append(child)
                population = elites + children

            # Submit all fitness evaluations in parallel
            all_futs = [
                _submit_fitness_games(executor, cand_w, champ_weights)
                for cand_w in population
            ]

            # Collect results
            fitnesses = []
            for ci, (cf, lf) in enumerate(all_futs):
                fitness, cwr, lwr = _collect_fitness(cf, lf, label=f"gen{gen}c{ci}")
                fitnesses.append(fitness)
                print(f"  gen {gen:2d} | cand {ci} | σ={sigma:.3f} | "
                      f"vs_champ={cwr:.3f} vs_lucario={lwr:.3f} fit={fitness:.3f}")

            ranked        = sorted(range(POPULATION_SIZE), key=lambda i: fitnesses[i], reverse=True)
            best_idx      = ranked[0]
            best_fit      = fitnesses[best_idx]
            champ_weights = population[best_idx]
            # Trim gene pool: survivors are all but the bottom DROP_COUNT
            survivor_idx   = ranked[:POPULATION_SIZE - DROP_COUNT]
            prev_pop       = [population[i] for i in survivor_idx]
            prev_fitnesses = [fitnesses[i]   for i in survivor_idx]
            dropped_idx    = ranked[POPULATION_SIZE - DROP_COUNT:]

            elapsed = time.time() - t0
            print(f"  → gen {gen}: champion=cand{best_idx} fitness={best_fit:.3f} | "
                  f"dropped cand{sorted(dropped_idx)}  ({elapsed:.0f}s)\n")

            out_path = os.path.join(OUTPUT_DIR, f"gen_{gen:02d}_weights.json")
            with open(out_path, "w") as f:
                json.dump({"generation": gen, "fitness": best_fit,
                           "weights": champ_weights}, f, indent=2)

            history.append({
                "generation": gen,
                "sigma": sigma,
                "fitnesses": fitnesses,
                "best_candidate": best_idx,
                "best_fitness": best_fit,
            })

    with open(os.path.join(OUTPUT_DIR, "history.json"), "w") as f:
        json.dump(history, f, indent=2)

    print(f"Evolution complete. Champion weights → {OUTPUT_DIR}/")
    return champ_weights


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="evoV2 — Clefable evolutionary optimizer (self-contained)")
    parser.add_argument("--generations", type=int, default=N_GENERATIONS)
    parser.add_argument("--population",  type=int, default=POPULATION_SIZE)
    parser.add_argument("--workers",     type=int, default=MAX_WORKERS)
    parser.add_argument("--elite",       type=int, default=ELITE_COUNT)
    parser.add_argument("--drop",        type=int, default=DROP_COUNT,
                        help="Bottom N candidates removed from gene pool each generation")
    parser.add_argument("--sigma-init",  type=float, default=SIGMA_INIT)
    parser.add_argument("--sigma-final", type=float, default=SIGMA_FINAL)
    parser.add_argument("--budget",      type=float, default=EVAL_BUDGET_S)
    parser.add_argument("--games",       type=int, default=GAMES_VS_CHAMP + GAMES_VS_BASE,
                        help=f"Total evaluation games per candidate (split evenly, default: {GAMES_VS_CHAMP + GAMES_VS_BASE})")
    parser.add_argument("--output-dir",  type=str, default=OUTPUT_DIR)
    parser.add_argument("--resume",      action="store_true")
    args = parser.parse_args()

    POPULATION_SIZE        = args.population
    MAX_WORKERS            = args.workers
    ELITE_COUNT            = args.elite
    DROP_COUNT             = args.drop
    SIGMA_INIT             = args.sigma_init
    SIGMA_FINAL            = args.sigma_final
    EVAL_BUDGET_S          = args.budget
    OUTPUT_DIR             = args.output_dir
    GAMES_VS_CHAMP         = args.games // 2
    GAMES_VS_BASE          = args.games // 2
    _LUCARIO_BASELINE_PATH = os.path.join(_HERE, "Lucario-Baseline", "mega_lucario_baseline.py")

    run_evolution(n_generations=args.generations, resume=args.resume)
