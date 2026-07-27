# 09e — Per-Opponent Metrics & Plots

Part 5 of [`09-opponent-pool.md`](09-opponent-pool.md). Depends on `09c` (episodes are
tagged with their opponent). Makes a pooled run interpretable.

## Purpose

Track and surface **win/loss per opponent**, so a pooled run answers "are we beating
Clefable but losing to Lucario?" — which the single aggregate winrate hides. The reward
function and PPO logging are unchanged; this is observation only.

## Behavior

### Bucketing

Each episode already carries its opponent name (`09c`). Per update, bucket episode
results by opponent name into win/loss/(draw) counts and compute a per-opponent winrate.

### Console + wandb

- Log per-opponent winrate each update alongside the existing aggregate, e.g.
  `winrate/clefable`, `winrate/lucario`, `winrate/self`, … (namespaced so wandb groups
  them). Include the per-opponent episode count so low-sample buckets are visible.
- The existing aggregate winrate and `avg_reward = (wins−losses)/total` stay as-is.

### Matplotlib

- Extend the existing figure: add **per-opponent winrate-vs-iteration** curves, one line
  per active opponent, with a legend. Keep the existing reward/aggregate-winrate
  subplots.
- Maintain a per-opponent winrate history list per update (parallel to the existing
  `winrate_history` / `update_nums`) to drive the plot.

### Checkpoint (required)

Persist the per-opponent histories in the existing checkpoint dict alongside
`reward_history` / `winrate_history`, so `--resume` keeps continuous curves. Load with
`ckpt.get("per_opponent_history", {})` (or equivalent default) so checkpoints written
before this part still resume cleanly with empty per-opponent history.

## Data

- In-memory: per-opponent win/loss counters (per update) and winrate history lists.
- Out: console lines, wandb scalars, the plot figure (existing output path). Optionally
  the checkpoint dict.

## Interfaces / seams

- Consumes the per-episode opponent tag from `09c`.
- Writes to the same logging/plotting/checkpoint surfaces already in `train.py`.

## Validation steps

1. **Bucketing reconciles.** After a short pooled run, assert
   `sum(per_opponent_episode_counts) == total_episodes` for each update, and that
   per-opponent (wins+losses+draws) equals that opponent's episode count.
2. **Console/wandb present.** Confirm each active opponent emits a `winrate/<name>` line
   each update, with counts; absent opponents (not in the pool) emit nothing.
3. **Plot correctness.** Generate the figure from a short run and confirm it has one
   winrate curve per active opponent, correctly labeled, plus the retained
   reward/aggregate subplots. Spot-check a point against the logged number.
4. **Single-opponent still fine.** A `--opponent clefable` run shows exactly one
   per-opponent curve equal to the aggregate.
5. **Resume continuity.** Resume a checkpoint and confirm per-opponent curves continue
   rather than restart. Also confirm a pre-09e checkpoint (without the new key) still
   loads and starts fresh per-opponent history without error.

## Success conditions

- Per-opponent winrate appears in console + wandb each update, with visible sample counts.
- The plot shows a correct, legended winrate curve per active opponent alongside the
  existing subplots.
- Buckets reconcile exactly with total episodes; the aggregate winrate is unchanged from
  before this part.

## Out of scope

- Any change to reward shaping or the PPO update.
- Curriculum decisions driven by these metrics (out of scope for 09; the metrics just
  inform the human, who reweights via `--opponent-pool`).
