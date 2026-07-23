# 10 — Archaludon Opponent in the Training Pool

Add the public rule-based Archaludon ex / Cinderace agent (Kaggle notebook, v6,
~74% WR vs a 1300+ Starmie) as a pool opponent. The agent folder already exists at
`sample-archaludon/` (repo root, next to `Ceruledge-RL/`): `main.py` + `deck.csv`
(60 cards), copied verbatim from the notebook. All infrastructure exists from
spec 09 — this is a registry entry plus test bookkeeping.

## Changes

1. **`opponents.py`** — add to `OPPONENTS`:

   ```python
   "archaludon": {"module": "sample-archaludon/main.py", "deck": "sample-archaludon/deck.csv"},
   ```

   Path is all-lowercase; `_assert_exact_case` enforces the exact casing, so it
   deploys unchanged to the case-sensitive Linux cluster.

2. **`opponents.py` self-test (`__main__`)** — the deck loop already iterates
   `OPPONENTS`, so archaludon is covered automatically; update the printed count
   ("all 6 opponents" → 7). No `MY_DECK` cross-check needed: unlike Clefable and
   Alakazam, this agent does not read its CSV at import time (`read_deck_csv()` runs
   only on `obs.select is None`, which training never hits — decks come from the
   registry via `battle_start`).

3. **`test_dispatch.py`** — add `"archaludon"` to `SEED_ORDER` and `NON_CERULEDGE`.

Deploy needs no changes: 09d's copy-all-folders step picks up `sample-archaludon/`
like any other agent folder — just include it when copying to the cluster.

## Validation steps

1. `python opponents.py` — self-test green; archaludon loads as `opp_archaludon`
   (not `main`), deck resolves to 60 ints.
2. `python test_pool.py` — green (iterates `OPPONENTS` dynamically; validates the
   new entry end-to-end including `validate_opponents`).
3. `python test_dispatch.py` — green with archaludon in the seed order.
4. Smoke train: `--opponent-pool archaludon --episodes 20` (or repo-standard smoke
   count) — no crashes, per-opponent metrics (09e) show an `archaludon` row.

## Success conditions

- `resolve_opponent("archaludon")` returns a callable policy and a 60-card deck.
- A pool run mixing archaludon with existing opponents trains without errors and
  logs its winrate separately.

## Out of scope

- Any modification to the agent's logic (kept verbatim; it is a fixed opponent,
  not our submission).
- Reweighting the default pool mix — choose weights per run via `--opponent-pool`.
