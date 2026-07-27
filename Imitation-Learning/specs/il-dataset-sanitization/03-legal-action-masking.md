# Legal-Action Masking

## Purpose
Flag every step where the acting player had no real decision to make (only
one legal option), so downstream IL training can skip those steps without
losing surrounding game context.

## Behavior
For each step in an episode's `steps` list (a 2-element list, one entry per
player slot):

- For each player-slot entry within the step, look at
  `observation.select.option`. This is the legal-action list for that
  player at that step (confirmed via inspection — e.g. step 10 in
  `85828069.json` has 9 entries in `option`, step 1 has 2).
- If `option` is `None`/absent, or the player isn't the acting player for
  this step, `usable` is not meaningful for that slot — leave it out (see
  edge cases below).
- If `len(option) == 1`, set `usable = false` on that player-slot entry.
  Otherwise set `usable = true`.
- Add this `usable` key directly inside each player-slot's
  `observation.select` dict (sibling to `option`), so it travels with the
  data it was computed from:
  ```json
  "select": {
    "...": "...",
    "option": [{"type": 1}, {"type": 2}],
    "usable": true
  }
  ```

### Edge cases
- `select` is `null` for a given player-slot (no decision pending for that
  player this step, e.g. it's the opponent's turn): leave `select` as `null`,
  do not add `usable`.
- `option` present but empty (`[]`): treat as `usable = false` (no legal
  action at all is at least as unusable as exactly one).

## Data
- Input: a single episode dict (post-exclusion-checks, from
  `02-episode-sanitization.md`), specifically each step's per-player
  `observation.select.option`.
- Output: the same episode dict, mutated in place to add `usable` booleans
  inside each non-null `select` object.
- This is a pure in-memory transform — no separate file written; the result
  feeds directly into the final write in `02-episode-sanitization.md`.

## Interfaces / seams
- Called by `02-episode-sanitization.md` on every episode that survives
  exclusion checks, before that episode is written to
  `sanitized/<day>/<episode_id>.json`.
- Aggregate counts (steps masked `usable=false` vs kept `usable=true`, per
  episode and per day) are reported to `04-drop-report.md`.

## Out of scope
- Any change to `action`, `current`, `logs`, or other step fields — only
  `select.usable` is added.
- Deriving legal actions via engine replay — not needed, since `option` is
  already present in the raw data.

## Open questions
None.
