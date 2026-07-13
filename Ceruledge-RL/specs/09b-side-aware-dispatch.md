# 09b — Side-Aware Dispatch (Single Opponent via Registry)

Part 2 of [`09-opponent-pool.md`](09-opponent-pool.md). Depends on `09a`. Still one
opponent per run — this part makes `collect_episode` opponent-parameterized and
deck-correct, and routes the existing `--opponent` flag through the registry. No pool
sampling yet.

## Purpose

Make an episode play against **any** registry opponent on **its own deck**, with the
opponent deck on the correct side. This is the riskiest mechanical change (deck/side
placement, dispatch), isolated here so it can be verified against each opponent
individually before sampling is added.

## Behavior

### Parameterize `collect_episode`

`collect_episode` gains the sampled opponent for that episode: its name, resolved policy
(from `09a`), and resolved deck. The frozen self-play snapshot is still passed in as
today for the `self` opponent.

### Side-aware `battle_start`

`our_side = ep % 2` alternates per episode and `battle_start(deck_for_side0,
deck_for_side1)` maps positionally. Place our deck on our side and the opponent deck on
the other:

```python
if our_side == 0:
    obs_dict, start_data = battle_start(FULL_DECK, opp_deck)
else:
    obs_dict, start_data = battle_start(opp_deck, FULL_DECK)
```

For `random` and `self`, `opp_deck` is `FULL_DECK`, so behavior matches today.

### Dispatch in the opponent branch

Keep the `IS_FIRST` handling exactly as today. In the opponent's decision branch,
dispatch by opponent kind:

- **file agent** → `policy(obs_dict)` (the module's `agent`), inside the existing
  try/except that falls back to a random legal move on a per-move error, plus the
  existing `IndexError` guard around `battle_select`.
- **random** → `random_agent(obs_dict)`.
- **self** → `_self_play_action(obs, 1 - our_side, opp_model, opp_tracker)` (frozen
  snapshot; no Step recorded for the opponent side; runs on the current 23-word flow).

### Route `--opponent` through the registry

`--opponent` now accepts **any registry name** (`ceruledge_rules`, `clefable`,
`alakazam`, `lucario`, `random`, `self`) and selects that single member for every
episode. `rules` is kept as a legacy alias for `ceruledge_rules`. Behavior is identical
to today for `random`/`self`; `rules` goes through the new loader/deck path but plays
the same Ceruledge deck it always did. An unknown name is an argparse-level error
listing the valid names.

## Data

No new persisted data. Uses `09a` resolvers plus the engine's `battle_start` /
`battle_select`.

## Interfaces / seams

- Consumes `09a` (policy + deck resolution).
- Unchanged: `features.py`, `model.py`, `actions.py`, reward shaping, PPO update.
- Produces the opponent-parameterized `collect_episode` that `09c` samples into.

## Validation steps

1. **Each opponent individually.** For each of `ceruledge_rules`, `clefable`, `alakazam`,
   `lucario`, `random`, `self`, run a short collection (a handful of episodes, e.g.
   `--opponent <name>` or a temporary direct call) and confirm every game runs to a
   terminal result with no crash.
2. **Opponent really plays its own deck.** Log or assert the opponent side's revealed
   card ids over an episode are a subset of that opponent's registry deck and are
   **not** a subset of `FULL_DECK` for the non-Ceruledge agents (proves the deck was
   actually swapped, not silently left as Ceruledge).
3. **Side alternation is correct.** Across episodes with `our_side` = 0 and = 1, assert
   our recorded Steps always come from our side and our deck is always `FULL_DECK`
   regardless of side (guards a transposed `battle_start` argument).
4. **Backward compatibility.** `--opponent random`, `--opponent self`, `--opponent rules`
   each produce the same episode flow as before this part (rules now via registry but
   same deck). A 2-update PPO run completes clean (matches the existing smoke bar).
5. **Robustness.** Confirm the per-move try/except and the `battle_select` `IndexError`
   guard still catch a bad opponent move (e.g. force one) without crashing the run.
6. **Foreign cards through feature extraction.** During an episode vs a non-Ceruledge
   opponent, assert `extract_features` runs without error while opponent cards outside
   `FULL_DECK` are in play (verified feasible: `opponent_tags.py` encodes any
   `CardRegistry` card via the override → keyword → zeros fallback; this step just
   guards a regression).

## Success conditions

- A full game runs to completion against **every** seed opponent, each on its own deck.
- Non-Ceruledge opponents demonstrably play non-Ceruledge cards; our side is always
  `FULL_DECK` on whichever side we occupy.
- All three legacy `--opponent` modes behave as before; a 2-update run is clean.

## Out of scope

- Sampling multiple opponents within one run (that is `09c`).
- Startup pool validation and metrics (`09d`, `09e`).
