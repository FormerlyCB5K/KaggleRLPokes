# Ceruledge-RL Specifications

This directory contains the current implementation plan and completed design contracts
for the Ceruledge policy.

## Active

- [`09-opponent-pool.md`](09-opponent-pool.md) — **overview/index** for the per-episode
  sampled multi-agent opponent pool. Current phase. Broken into five independently
  buildable parts, each with validation steps and success conditions:
  - [`09a-registry-and-loading.md`](09a-registry-and-loading.md) — registry, collision-safe
    loader, deck resolution
  - [`09b-side-aware-dispatch.md`](09b-side-aware-dispatch.md) — opponent-parameterized
    episode, side-correct decks, `--opponent` via registry
  - [`09c-pool-sampling-cli.md`](09c-pool-sampling-cli.md) — weighted per-episode sampling +
    `--opponent-pool` CLI
  - [`09d-startup-validation-and-deploy.md`](09d-startup-validation-and-deploy.md) —
    fail-fast pool validation + copy-all-folders deploy
  - [`09e-per-opponent-metrics.md`](09e-per-opponent-metrics.md) — per-opponent winrate
    logging + plots
- [`04-training-plan.md`](04-training-plan.md) — the training decisions accompanying the
  generalized encoder that motivate the pool; `09` is its concrete implementation
  contract.

## Completed

Completed specifications remain authoritative descriptions of implemented behavior and
live under [`completed/`](completed/):

- [`01-prize-tracker.md`](completed/01-prize-tracker.md)
- [`02-observation-encoding.md`](completed/02-observation-encoding.md)
- [`03-attack-ability-tagging.md`](completed/03-attack-ability-tagging.md)
- [`05-new-attack-tags-full-audit.md`](completed/05-new-attack-tags-full-audit.md)
- [`06-effect-baking.md`](completed/06-effect-baking.md)
- [`07-effect-baking-audit.md`](completed/07-effect-baking-audit.md)

For a reader-oriented description of the full current model rather than an implementation
plan, start with [`../MODEL-ARCHITECTURE.md`](../MODEL-ARCHITECTURE.md).

## Historical or deferred

Superseded, incomplete, or currently irrelevant proposals are retained under
[`../old/specs/`](../old/specs/) and are not active implementation contracts.
