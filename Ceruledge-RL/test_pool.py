"""
test_pool.py — Spec 09c/09d validation (+ 09b robustness step 5).

Covers: pool-spec parsing (accept/reject), empirical sampling distribution,
startup validation happy path, implausible-deck and missing-module failures,
and the per-move error fallback for file agents.

Run from the repo root:
    .venv/Scripts/python.exe Ceruledge-RL/test_pool.py
"""
from __future__ import annotations

import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))   # repo root: cg_download
sys.path.insert(0, _HERE)                    # Ceruledge-RL first

import opponents as O
from opponents import OPPONENTS, parse_pool_spec, resolve_opponent, validate_opponents


def test_parser() -> None:
    assert parse_pool_spec("clefable:2,lucario") == {"clefable": 2.0, "lucario": 1.0}
    assert parse_pool_spec("self") == {"self": 1.0}
    got = parse_pool_spec("clefable:2, lucario : 0.5 ,random")
    assert got == {"clefable": 2.0, "lucario": 0.5, "random": 1.0}
    bad = ["", "   ", "clefable:", "clefable:x", "not_a_member", "clefable:2,",
           ",clefable", "clefable,clefable", "clefable:-1", "clefable:0",
           "clefable:nan", "clefable:inf"]
    for spec in bad:
        try:
            parse_pool_spec(spec)
        except ValueError:
            continue
        raise AssertionError(f"parser accepted malformed spec {spec!r}")
    print("1. pool-spec parser: OK (valid accepted, 12 malformed rejected)")


def test_distribution() -> None:
    pool = parse_pool_spec("clefable:3,lucario:1")
    names, weights = list(pool), [pool[n] for n in pool]
    n = 10_000
    draws = random.choices(names, weights=weights, k=n)
    freq = draws.count("clefable") / n
    assert abs(freq - 0.75) < 0.02, f"clefable freq {freq:.3f} not ~0.75"
    print(f"2. sampling distribution: OK (clefable {freq:.3f} ~ 0.75 over {n} draws)")


def test_validate_happy() -> None:
    active = validate_opponents(list(OPPONENTS))
    assert set(active) == set(OPPONENTS)
    assert all(40 <= len(o["deck"]) <= 60 for o in active.values())
    print("3. startup validation happy path: OK (all 6 members)")


def test_validate_failures() -> None:
    # Implausible deck: registry entry pointing at a truncated CSV
    tmp_dir = os.path.join(_HERE, "out", "tmp_test_pool")
    os.makedirs(tmp_dir, exist_ok=True)
    bad_csv = os.path.join(tmp_dir, "deck.csv")
    with open(bad_csv, "w") as f:
        f.write("1\n2\n3\n")
    O.OPPONENTS["_badlen"] = {"module": "Ceruledge-Agent/main.py",
                              "deck": "Ceruledge-RL/out/tmp_test_pool/deck.csv"}
    try:
        try:
            validate_opponents(["_badlen"])
        except RuntimeError as e:
            assert "implausible deck length 3" in str(e), e
        else:
            raise AssertionError("truncated deck passed validation")
    finally:
        del O.OPPONENTS["_badlen"]
        os.remove(bad_csv)
        os.rmdir(tmp_dir)

    # Missing module folder: diagnostic must name the path and _parent
    O.OPPONENTS["_missing"] = {"module": "Nonexistent-Agent/main.py",
                               "deck": "FULL_DECK"}
    try:
        try:
            validate_opponents(["_missing"])
        except RuntimeError as e:
            msg = str(e)
            assert "Nonexistent-Agent" in msg and "_parent" in msg, msg
        else:
            raise AssertionError("missing module passed validation")
    finally:
        del O.OPPONENTS["_missing"]
    print("4. startup validation failures: OK (bad length + missing folder abort)")


def test_per_move_fallback() -> None:
    """Spec 09b step 5: a file agent that errors on a move must not crash the
    episode — _file_agent_move falls back to a random legal action."""
    sys.argv = ["test_pool.py", "--no-wandb"]
    import train as T

    base = resolve_opponent("clefable")
    real_agent = base["policy"]
    calls = {"n": 0}

    def flaky_agent(obs_dict):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise ValueError("forced test error")
        return real_agent(obs_dict)

    opp = {**base, "policy": flaky_agent}
    model = T.CeruledgePolicy()
    model.eval()
    steps, reward = T.collect_episode(model, 0.0, 0, True, opp)
    assert calls["n"] >= 2, "flaky agent never consulted"
    assert reward in (-1.0, 0.0, 1.0), f"no terminal result (reward={reward})"
    print(f"5. per-move fallback: OK (2 forced errors absorbed, "
          f"game finished, reward={reward:+.0f})")


if __name__ == "__main__":
    test_parser()
    test_distribution()
    test_validate_happy()
    test_validate_failures()
    test_per_move_fallback()
    print("\ntest_pool.py passed.")
