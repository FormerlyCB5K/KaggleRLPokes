# 09 — Opponent Pool (Overview)

## What this is

Replace the single-opponent switch (`--opponent random|rules|self`) with a **per-episode
sampled pool of opponents**, each playing its own native deck, so the Ceruledge policy
trains against diverse decks, decision flows, and skill levels. This is the training-side
realization of the pool sketched in [`04-training-plan.md`](04-training-plan.md).

Our side is **always the Ceruledge deck** (`FULL_DECK`); only the opponent slot varies.

Because this is a large change, it is split into five independently buildable and
testable parts. Each part below is its own spec file with concrete validation steps and
success conditions. Build them in order; each is a working, verifiable increment.

## Build order & parts

1. [`09a-registry-and-loading.md`](09a-registry-and-loading.md) — the hardcoded
   `OPPONENTS` registry, the collision-safe multi-agent module loader, and deck
   resolution (CSV / inline / `FULL_DECK`). Pure plumbing; no training-loop changes.
2. [`09b-side-aware-dispatch.md`](09b-side-aware-dispatch.md) — parameterize
   `collect_episode` by a single opponent spec, place decks side-correctly in
   `battle_start`, and route the existing `--opponent` flag through the registry. Still
   one opponent per run.
3. [`09c-pool-sampling-cli.md`](09c-pool-sampling-cli.md) — weighted per-episode
   sampling and the `--opponent-pool name:weight,...` CLI (mutually exclusive with
   `--opponent`).
4. [`09d-startup-validation-and-deploy.md`](09d-startup-validation-and-deploy.md) —
   fail-fast validation of the whole active pool before episode 0, plus the
   copy-all-agent-folders cluster deploy update.
5. [`09e-per-opponent-metrics.md`](09e-per-opponent-metrics.md) — per-opponent winrate
   to console/wandb and per-opponent winrate-vs-iteration matplotlib curves.

Dependencies: `09a → 09b → 09c`; `09d` depends on `09a`; `09e` depends on `09c`.

## Scope (v1)

- Per-episode sampled opponent pool; our side always Ceruledge, opponents on native decks.
- Hardcoded `OPPONENTS` registry in `train.py`. Seed members: `ceruledge_rules`,
  `clefable`, `alakazam`, `lucario`, `random`, `self`.

  **Amendment (2026-07-22, independent audit finding):** the registry has since grown to 8
  named members. `archaludon` was added and is documented by
  [`10-archaludon-opponent.md`](10-archaludon-opponent.md). `garchomp` was also added
  (`garchomp-baseline/`) but has no corresponding spec addendum — its provenance and
  intended registry status are unresearched here; flagged as a candidate for a future,
  separately-scoped audit rather than backfilled from this note.
- CLI-driven pool with inline weights; `--opponent` retained and extended to accept any
  registry name (`rules` kept as alias for `ceruledge_rules`).
- Fail-fast startup validation of the active pool; deploy copies all pooled folders.
- Per-opponent metrics and plots. Reward function unchanged.

## Explicitly out of scope

- Reward shaping, PPO hyperparameters, or training-loop mechanics (weighting is by play
  frequency only).
- Curriculum / league scheduling beyond static weighted per-episode sampling.
- External/downloaded Kaggle agents (registry is extensible; none added here).
- Config-file-driven registry (hardcoded dict only for now).

## Success criteria (whole feature)

- A run with `--opponent-pool clefable:2,lucario:1,self:1,random:0.5,ceruledge_rules:1`
  completes end-to-end on the cluster, opponents playing their own decks, and produces
  per-opponent winrate curves.
- A pool that references an un-deployed agent folder fails at startup, not mid-run.
- Every existing single-opponent capability (`--opponent random|rules|self`) still works.

## Shared reference — the registry

A module-level `dict` in `train.py` maps an opponent **name** to its policy source and
deck source. No external config; adding an opponent means editing this dict.

```python
OPPONENTS = {
    "ceruledge_rules": {"module": "Ceruledge-Agent/main.py",                 "deck": "Ceruledge-Agent/deck.csv"},
    "clefable":        {"module": "Clefable-Agent/main.py",                   "deck": "Clefable-Agent/deck.csv"},
    "alakazam":        {"module": "Alakazam-Agent/main.py",                   "deck": "Alakazam-Agent/Deck.csv"},  # capital D
    "lucario":         {"module": "Lucario-Baseline/mega_lucario_baseline.py","deck": "inline:DECK"},
    "random":          {"callable": "random_agent",                          "deck": "FULL_DECK"},
    "self":            {"model": "frozen_snapshot",                          "deck": "FULL_DECK"},
}
```

Paths resolve relative to `_parent` (the directory holding `Ceruledge-RL/`), matching the
existing rules-agent loader. **Casing is significant on the Linux cluster** — Alakazam's
deck file is `Deck.csv`. Exact field names are at the author's discretion; this shape is
the contract the parts share.

## Key decisions (from the design interview)

- Our side fixed to Ceruledge; opponents on native decks (diversity is the whole point).
- Hardcoded registry, not a config file. Extensible for future/external agents later.
- Per-episode sampling (rollout batch is 128 on the cluster).
- `random` and `self` are pool members; `self` kept slim and on the current 23-word flow.
- Weighting an opponent = playing it more often; the reward function does not change.
- Fail-fast on any missing/broken pool member before training starts.
- `--opponent` accepts any registry name (design interview 2026-07-12); per-opponent
  winrate histories persist in the checkpoint (required, backward-compatible load).

## Open questions

- None.
