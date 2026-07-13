"""
opponents.py — Opponent registry, collision-safe module loading, deck resolution.

Spec: specs/09a-registry-and-loading.md (part 1 of specs/09-opponent-pool.md).

Registry paths resolve relative to _parent (the directory holding Ceruledge-RL/),
matching train.py's original rules-agent loader. Casing is checked component by
component even on Windows, so a mis-cased path fails here instead of on the
case-sensitive Linux cluster.

    python opponents.py        # self-test (spec 09a validation steps)
"""
from __future__ import annotations

import importlib.util
import os
import sys

_here   = os.path.dirname(os.path.abspath(__file__))
_parent = os.path.dirname(_here)
sys.path.insert(0, _here)    # Ceruledge-RL first — local imports win
if _parent not in sys.path:
    sys.path.insert(1, _parent)  # parent for cg_download (agent modules import it)

# ── Registry ───────────────────────────────────────────────────────────────────
# name -> policy source + deck source. Hardcoded by design (spec 09): adding an
# opponent means editing this dict. deck is a CSV path, "inline:<ATTR>" (module
# attribute), or "FULL_DECK" (our own Ceruledge deck from features.py).

OPPONENTS: dict[str, dict[str, str]] = {
    "ceruledge_rules": {"module": "Ceruledge-Agent/main.py",                   "deck": "Ceruledge-Agent/deck.csv"},
    "clefable":        {"module": "Clefable-Agent/main.py",                    "deck": "Clefable-Agent/deck.csv"},
    "alakazam":        {"module": "Alakazam-Agent/main.py",                    "deck": "Alakazam-Agent/Deck.csv"},  # capital D
    "lucario":         {"module": "Lucario-Baseline/mega_lucario_baseline.py", "deck": "inline:DECK"},
    "random":          {"callable": "random_agent",                            "deck": "FULL_DECK"},
    "self":            {"model": "frozen_snapshot",                            "deck": "FULL_DECK"},
}

_module_cache: dict[str, object] = {}


def _assert_exact_case(rel_path: str) -> str:
    """Resolve rel_path under _parent, verifying each component's exact casing.

    Windows opens mis-cased paths happily; the Linux cluster does not. Walking
    os.listdir per component makes the casing trap fail identically on both.
    Returns the absolute path.
    """
    cur = _parent
    for comp in rel_path.split("/"):
        entries = os.listdir(cur) if os.path.isdir(cur) else []
        if comp not in entries:
            match = next((e for e in entries if e.lower() == comp.lower()), None)
            hint = (f" A file named {match!r} exists there — casing must match "
                    f"exactly (case-sensitive on the Linux cluster)." if match else "")
            raise RuntimeError(
                f"Opponent path component {comp!r} not found in {cur!r}.{hint}\n"
                f"  _parent resolved to: {_parent!r}\n"
                f"  Expected layout: <parent>/Ceruledge-RL/train.py and "
                f"<parent>/{rel_path} (case-sensitive on Linux).\n"
                f"  Copy the agent folder (module + deck file) next to "
                f"Ceruledge-RL/ on this machine."
            )
        cur = os.path.join(cur, comp)
    return cur


def load_module(name: str):
    """Import an opponent's module file under a unique module name, cached.

    Never imports under "main" — three agents share that filename, and
    importlib.import_module("main") would return the first one loaded for all
    of them. The agent's own directory goes on sys.path first so its local
    imports (e.g. Clefable's heuristic_score/weights) resolve.
    """
    if name in _module_cache:
        return _module_cache[name]
    entry = OPPONENTS[name]
    rel = entry.get("module")
    if rel is None:
        raise ValueError(f"Opponent {name!r} has no module source (kind: "
                         f"{'random' if 'callable' in entry else 'self'})")
    abs_path  = _assert_exact_case(rel)
    agent_dir = os.path.dirname(abs_path)
    if agent_dir not in sys.path:
        sys.path.insert(0, agent_dir)

    unique_name = f"opp_{name}"
    spec = importlib.util.spec_from_file_location(unique_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[unique_name] = module  # so the agent's own imports see itself
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[unique_name]   # don't cache a half-initialized module
        raise
    _module_cache[name] = module
    return module


def load_deck(name: str) -> list[int]:
    """Return the opponent's 60-card deck as list[int], whatever its source."""
    entry = OPPONENTS[name]
    src = entry["deck"]
    if src == "FULL_DECK":
        from features import FULL_DECK
        return list(FULL_DECK)
    if src.startswith("inline:"):
        attr = src.split(":", 1)[1]
        module = load_module(name)
        deck = getattr(module, attr, None)
        if deck is None:
            raise RuntimeError(
                f"Opponent {name!r}: module {entry['module']!r} has no "
                f"attribute {attr!r} (registry says deck = {src!r})")
        return [int(c) for c in deck]
    abs_path = _assert_exact_case(src)
    with open(abs_path) as f:
        return [int(l) for l in f.read().splitlines() if l.strip()]


def resolve_opponent(name: str) -> dict:
    """Resolve a registry name to what an episode needs.

    Returns {"name", "kind": "file"|"random"|"self", "policy", "deck"}.
    policy is the module's `agent` for file agents, random_agent for "random",
    and None for "self" (the frozen snapshot is created in the training loop).
    """
    entry = OPPONENTS.get(name)
    if entry is None:
        raise KeyError(f"Unknown opponent {name!r}; valid: {sorted(OPPONENTS)}")
    deck = load_deck(name)
    if "module" in entry:
        module = load_module(name)
        agent_fn = getattr(module, "agent", None)
        if not callable(agent_fn):
            raise RuntimeError(f"Opponent {name!r}: {entry['module']!r} exposes "
                               f"no callable `agent`")
        return {"name": name, "kind": "file", "policy": agent_fn, "deck": deck}
    if entry.get("callable") == "random_agent":
        from random_agent import random_agent
        return {"name": name, "kind": "random", "policy": random_agent, "deck": deck}
    return {"name": name, "kind": "self", "policy": None, "deck": deck}


# ── Startup validation (spec 09d) ──────────────────────────────────────────────

def validate_opponents(names) -> dict[str, dict]:
    """Fail-fast validation of the whole active opponent set, before episode 0.

    Resolves every member — importing its module (which warms the loader cache)
    and its deck, with the casing-aware diagnostics of _assert_exact_case — and
    sanity-checks deck length. Any failure aborts with the offending member
    named. Returns {name: resolved} so the caller reuses the resolution.
    """
    resolved: dict[str, dict] = {}
    for name in names:
        opp = resolve_opponent(name)
        n_cards = len(opp["deck"])
        if not (40 <= n_cards <= 60):
            raise RuntimeError(
                f"Opponent {name!r}: implausible deck length {n_cards} "
                f"(sane range 40-60) from source "
                f"{OPPONENTS[name]['deck']!r} — truncated or corrupt file?")
        resolved[name] = opp
        print(f"[opponent-pool] {name}: OK (kind={opp['kind']}, "
              f"deck={n_cards} cards)", flush=True)
    return resolved


# ── Pool spec parsing (spec 09c) ───────────────────────────────────────────────

def parse_pool_spec(spec: str) -> dict[str, float]:
    """Parse a --opponent-pool value: comma-separated name[:weight].

    Weights are relative floats (default 1.0, need not sum to 1). Raises
    ValueError on an empty spec, empty entry (trailing comma), unknown name,
    duplicate name, or missing/non-positive/non-finite weight.
    """
    if not spec or not spec.strip():
        raise ValueError("empty --opponent-pool spec")
    pool: dict[str, float] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            raise ValueError(
                f"empty entry in --opponent-pool spec {spec!r} (trailing comma?)")
        name, sep, w = item.partition(":")
        name = name.strip()
        if name not in OPPONENTS:
            raise ValueError(
                f"unknown opponent {name!r}; valid: {sorted(OPPONENTS)}")
        if name in pool:
            raise ValueError(f"duplicate opponent {name!r} in pool spec")
        if sep:
            try:
                weight = float(w)
            except ValueError:
                raise ValueError(f"bad weight {w!r} in {item!r}") from None
        else:
            weight = 1.0
        if not (0.0 < weight < float("inf")):   # also rejects NaN
            raise ValueError(f"weight must be positive and finite in {item!r}")
        pool[name] = weight
    return pool


# ── Self-test (spec 09a validation steps) ──────────────────────────────────────

if __name__ == "__main__":
    from features import FULL_DECK

    # 1. Simultaneous load without collision (three files all named main.py)
    mods = {n: load_module(n) for n in ("ceruledge_rules", "clefable", "alakazam")}
    assert len({id(m) for m in mods.values()}) == 3, "modules not distinct"
    for n, m in mods.items():
        assert callable(getattr(m, "agent", None)), f"{n}: no callable agent"
        assert sys.modules.get("main") is not m, f"{n} cached under 'main'"
        assert sys.modules.get(f"opp_{n}") is m
    print("1. simultaneous load: OK (3 distinct modules, none under 'main')")

    # 2. Deck resolution — exact counts observed in the repo (all 60)
    for n in OPPONENTS:
        deck = load_deck(n)
        assert isinstance(deck, list) and deck, f"{n}: empty deck"
        assert all(isinstance(c, int) for c in deck), f"{n}: non-int entries"
        assert len(deck) == 60, f"{n}: expected 60 cards, got {len(deck)}"
    assert load_deck("random") == list(FULL_DECK)
    assert load_deck("self")   == list(FULL_DECK)
    # Agents that read their own CSV at import must agree with the registry —
    # guards the CWD-relative deck.csv trap (main.py was made __file__-relative).
    assert list(mods["clefable"].MY_DECK) == load_deck("clefable"), \
        "clefable module loaded a different deck.csv than the registry resolves"
    assert list(mods["alakazam"].MY_DECK) == load_deck("alakazam"), \
        "alakazam module loaded a different Deck.csv than the registry resolves"
    print("2. deck resolution: OK (all 6 opponents, 60 cards each)")

    # 3. Casing trap — wrong-cased Alakazam deck path must raise with a hint
    try:
        _assert_exact_case("Alakazam-Agent/deck.csv")   # actual file is Deck.csv
    except RuntimeError as e:
        assert "casing" in str(e), f"casing error lacks casing hint: {e}"
        print("3. casing trap: OK (wrong case raises with hint)")
    else:
        raise AssertionError("wrong-cased path did not raise")

    # 4. Idempotent caching — second load returns the same object
    assert load_module("clefable") is mods["clefable"]
    r1, r2 = resolve_opponent("lucario"), resolve_opponent("lucario")
    assert r1["policy"] is r2["policy"]
    print("4. idempotent caching: OK")

    print("\nopponents.py self-test passed.")
