"""Test-only helper: bounds a live `train.collect_episode()` call so a pathological
policy/opponent pairing can't hang a test suite indefinitely (independent-audit finding,
2026-07-22 — `collect_episode` itself uses an unbounded `while True` with no turn/time
guard). Does not modify `collect_episode` or any production training path: the bound is
applied entirely from the caller's side, via a daemon thread and a temporary
`battle_select` monkeypatch (the same spying technique `test_dispatch.py` already uses)
purely to count selections for a useful timeout message.

120s per episode is a judgment call, not a measured bound: ordinary games (e.g. the
Archaludon smoke) finish in ~1s, so 120s is generous headroom for legitimate variance
while still catching a genuine stall well within a bounded test run. Adjust `timeout_s`
per call if a specific opponent pairing is known to need more.
"""
from __future__ import annotations

import threading
import time


class EpisodeTimeout(AssertionError):
    pass


def bounded_collect_episode(train_module, *args, timeout_s: float = 120.0, context: str = "", **kwargs):
    """Runs `train_module.collect_episode(*args, **kwargs)` on a daemon thread. Raises
    `EpisodeTimeout` (naming `context` and how many `battle_select` calls happened before
    the deadline) if it doesn't finish in time; otherwise returns its normal result, or
    re-raises whatever exception it raised."""
    real_select = train_module.battle_select
    selection_count = {"n": 0}

    def counting_select(selected):
        selection_count["n"] += 1
        return real_select(selected)

    train_module.battle_select = counting_select
    outcome: dict = {}

    def run():
        try:
            outcome["value"] = train_module.collect_episode(*args, **kwargs)
        except BaseException as exc:  # surface the real exception, don't swallow it
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    start = time.monotonic()
    thread.start()
    thread.join(timeout_s)
    train_module.battle_select = real_select

    if thread.is_alive():
        elapsed = time.monotonic() - start
        raise EpisodeTimeout(
            f"{context}: collect_episode did not finish within {timeout_s:.0f}s "
            f"(elapsed {elapsed:.0f}s, {selection_count['n']} battle_select calls made "
            f"before the deadline) -- likely a stalled/looping live game, not a normal "
            f"legal-action failure"
        )
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]
