"""
parallel_collect.py — Parallel episode collection for the Ceruledge PPO trainer.

Actor/learner split (validated in the Phase-1 concurrency gate):
  * The learner (train.py) stays single-process and owns the PPO update on the GPU.
  * A persistent spawn ProcessPoolExecutor of CPU-only actors runs whole episodes.
  * Each update the learner broadcasts a fresh CPU state_dict (version-tagged;
    workers reload only when the version changes) and collects one episode per task.

Why spawn + this exact setup (see Phase-1 findings):
  * spawn, NOT fork — the native cg engine + torch don't survive fork cleanly.
  * Each worker imports the engine locally (via `import train`), so every worker
    process gets its own GameInitialize(). The parent may also have initialized the
    engine (train.py imports it at module top); that coexists fine with spawn.
  * OMP/OpenBLAS/MKL threads MUST be pinned to 1 in the workers, else they
    oversubscribe cores and crash with OpenBLAS OOM at high worker counts.
    torch.set_num_threads(1) alone is not enough — the BLAS thread pools read
    their env vars at import. We set the env in the PARENT before the pool spawns
    so children inherit it before importing torch.
  * CUDA is hidden from the workers so 10 torch imports don't each grab a GPU
    context; the learner's own CUDA context (already created) is unaffected by the
    env change.
"""
from __future__ import annotations

import io
import os
import sys
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

# ── worker-side state (one dict per worker process) ────────────────────────────
_W: dict = {}


def _worker_init(rl_dir: str, parent_dir: str, cfg: dict):
    """Runs once per worker. Imports the engine + trainer locally and syncs the
    exploration / reward-shaping knobs that collect_episode reads from train's
    module globals, so worker rollouts match the learner's configuration."""
    import torch
    torch.set_num_threads(1)
    if rl_dir not in sys.path:
        sys.path.insert(0, rl_dir)
    if parent_dir not in sys.path:
        sys.path.insert(1, parent_dir)
    sys.argv = ["train.py", "--no-wandb"]         # train.py parses argv at import
    import train
    from opponents import resolve_opponent
    train.USE_EPSILON_GREEDY      = cfg["use_epsilon_greedy"]
    train.USE_STOCHASTIC_SAMPLING = cfg["use_stochastic_sampling"]
    train.PRIZE_REWARD            = cfg["prize_reward"]
    train.DAMAGE_REWARD           = cfg["damage_reward"]
    _W["collect"] = train.collect_episode
    _W["Policy"]  = train.CeruledgePolicy
    _W["resolve"] = resolve_opponent
    _W["opps"]    = {}                             # name -> resolved opponent (cached)
    _W["policy"]  = None; _W["pv"] = None          # current policy + its version
    _W["self"]    = None; _W["sv"] = None          # frozen self-play opponent + version


def _load_policy(state_bytes: bytes):
    import torch
    m = _W["Policy"]()
    m.load_state_dict(torch.load(io.BytesIO(state_bytes), weights_only=True))
    m.eval()
    return m


def _worker_episode(task):
    (ep, our_side, go_first, opp_name, epsilon,
     pv, state_bytes, sv, self_bytes) = task
    if pv != _W["pv"]:
        _W["policy"] = _load_policy(state_bytes); _W["pv"] = pv
    opp = _W["opps"].get(opp_name)
    if opp is None:
        opp = _W["resolve"](opp_name); _W["opps"][opp_name] = opp
    opp_model = None
    if opp["kind"] == "self":
        if sv != _W["sv"]:
            _W["self"] = _load_policy(self_bytes); _W["sv"] = sv
        opp_model = _W["self"]
    steps, reward = _W["collect"](
        _W["policy"], epsilon, our_side, go_first, opp, opp_model)
    return (opp_name, steps, reward)


def _dumps_state(model) -> bytes:
    import torch
    sd = {k: v.detach().cpu() for k, v in model.state_dict().items()}
    buf = io.BytesIO()
    torch.save(sd, buf)
    return buf.getvalue()


# ── parent-side collector ──────────────────────────────────────────────────────
class ParallelCollector:
    """Persistent spawn pool of CPU actors. One instance per training run."""

    _THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                   "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")

    def __init__(self, n_workers: int, rl_dir: str, parent_dir: str, cfg: dict):
        # Pin BLAS/OMP threads and hide CUDA for the *children* by setting the env
        # in this (parent) process before the pool spawns — children inherit it.
        # The parent's own torch is already initialized, so these do not change the
        # learner's thread count or its existing CUDA context.
        for v in self._THREAD_ENV:
            os.environ.setdefault(v, "1")
        os.environ["CUDA_VISIBLE_DEVICES"] = ""    # CPU-only actors

        ctx = mp.get_context("spawn")
        self.ex = ProcessPoolExecutor(
            max_workers=n_workers, mp_context=ctx,
            initializer=_worker_init, initargs=(rl_dir, parent_dir, cfg))
        self.n_workers = n_workers
        self._ver = 0
        # Force workers to spawn + run their initializer now, so import/engine-init
        # errors surface here (not mid-training) and don't skew the first update.
        list(self.ex.map(int, range(n_workers)))

    def collect(self, model, episode_opponents, epsilon, self_model=None):
        """Broadcast fresh weights and run one episode per opponent in the list.
        Returns [(opp_name, steps, reward), ...] in the same order as the input
        (identical shape to train.py's sequential `results`)."""
        self._ver += 1
        state_bytes = _dumps_state(model)
        if self_model is not None:
            sv, self_bytes = self._ver, _dumps_state(self_model)
        else:
            sv, self_bytes = -1, None
        tasks = [
            (ep, ep % 2, (ep // 2) % 2 == 0, opp_name, epsilon,
             self._ver, state_bytes, sv, self_bytes)
            for ep, opp_name in enumerate(episode_opponents)
        ]
        return list(self.ex.map(_worker_episode, tasks))

    def close(self):
        self.ex.shutdown(wait=True)
