# 09c — Pool Sampling & CLI

Part 3 of [`09-opponent-pool.md`](09-opponent-pool.md). Depends on `09b`. Adds weighted
per-episode sampling and the CLI to drive it.

## Purpose

Turn the opponent-parameterized `collect_episode` from `09b` into a real pool: sample one
opponent per episode from a weighted, CLI-specified active set.

## Behavior

### CLI

- Retain `--opponent <registry-name>` (any registry member; `rules` alias) for
  single-opponent runs (from `09b`).
- Add `--opponent-pool` taking a comma-separated list of `name[:weight]`:

  ```
  --opponent-pool clefable:2,lucario:1,self:1,random:0.5,ceruledge_rules:1
  ```

  - Weight optional; defaults to `1.0`. Weights are relative (need not sum to 1).
  - Every `name` must be a key of `OPPONENTS`; an unknown name is a startup error
    (full validation of the members is `09d`, but parse/lookup errors surface here).
  - `--opponent` and `--opponent-pool` are **mutually exclusive**; supplying both, or a
    malformed spec (empty, bad number, trailing comma), is a clear argparse-level error.

### Sampling

- **Per-episode**: for each of the `EPISODES_PER_UPDATE` (128 on cluster) episodes in a
  rollout, draw one opponent name proportional to weight (e.g.
  `random.choices(names, weights)`).
- The drawn opponent's policy + deck (resolved once at startup, cached) are passed into
  `collect_episode`. Weighting up an opponent means it is **played more often**; the
  reward is unchanged.
- Self-play snapshot refresh (`SELF_PLAY_UPDATE_EVERY`) still applies whenever `self` is
  in the active set; if `self` is absent, no snapshot is maintained.

### Determinism note

Sampling uses the process RNG; the project already treats engine RNG as uncontrolled, so
no new seeding guarantees are promised. (`Date.now`/global-seed constraints are not
relevant here — plain `random`.)

## Data

No persisted data. Reads the resolved registry (from `09a`), writes per-episode opponent
tags consumed by `09e` metrics.

## Interfaces / seams

- Consumes `09a` (resolution) and `09b` (opponent-parameterized episode).
- Emits, per episode, the opponent name alongside its result — the hook `09e` buckets on.

## Validation steps

1. **CLI parse tests.** Unit-test the parser: `clefable:2,lucario` →
   `{clefable:2.0, lucario:1.0}`; unknown name → error; both `--opponent` and
   `--opponent-pool` → error; malformed (`clefable:`, `clefable:x`, empty) → error.
2. **Empirical distribution.** Sample a large N (e.g. 10k draws) from
   `clefable:3,lucario:1` and assert observed frequencies ≈ 0.75 / 0.25 within a small
   tolerance.
3. **Short mixed run.** Run ~1 update with a 3+ member pool and confirm it completes,
   that more than one distinct opponent was actually played (log the per-update opponent
   counts), and that `self` refresh still fires on schedule when included.
4. **Single-opponent unchanged.** `--opponent clefable`-style single runs (via `09b`)
   still behave identically; pool mode is additive.

## Success conditions

- The parser accepts valid specs, rejects malformed/conflicting ones with clear messages.
- Over many draws, empirical opponent frequency matches the configured weights within
  tolerance.
- A short multi-member pooled run completes and demonstrably plays multiple opponents in
  one rollout.

## Out of scope

- Fail-fast validation of member availability before episode 0 (`09d`).
- Per-opponent metrics/plots (`09e`).
- Non-uniform *scheduling* beyond static weights (curriculum is out of scope for 09).
