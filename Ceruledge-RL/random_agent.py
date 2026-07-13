"""
random_agent.py — Ceruledge deck agent that plays uniformly random legal actions.
Used as the opponent in experiment 1.
"""
import random
from cg_download.api import Observation, to_observation_class
from features import FULL_DECK


def random_agent(obs_dict: dict) -> list[int]:
    obs = to_observation_class(obs_dict)

    if obs.select is None:
        return FULL_DECK

    opts    = obs.select.option
    n_opts  = len(opts)
    min_cnt = max(obs.select.minCount, 1)
    max_cnt = min(obs.select.maxCount, n_opts)
    count   = random.randint(min_cnt, max_cnt) if max_cnt >= min_cnt else min_cnt

    return random.sample(range(n_opts), min(count, n_opts))
