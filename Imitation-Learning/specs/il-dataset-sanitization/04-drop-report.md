# Drop Report

## Purpose
Give visibility into what sanitization removed or masked, so data quality is
auditable rather than silently changing the training distribution.

## Behavior
Produce one report file per day (simplest to generate alongside that day's
output), plus values that can trivially be summed across days for a
combined view. No separate combined-file generation is required — a
consumer can concatenate the per-day reports.

Each per-day report records:
- `day`: the date string (e.g. `2026-07-14`).
- `total_episodes_seen`: count of JSON entries found in the source zip.
- `excluded`: list of `{episode_id, reason}` for every excluded episode,
  where `reason` is one of `malformed_json` or `non_done_status` (with the
  actual `statuses` value included for the latter).
- `episodes_written`: count of episodes written to `sanitized/<day>/`.
- `steps_total`: total step-player entries with a non-null `select` across
  all written episodes for the day.
- `steps_usable`: count of those with `usable = true`.
- `steps_masked`: count of those with `usable = false`.

## Data
- Output path: `<output-root>/<day>/report.json` (default `<output-root>` is
  `Imitation-Learning/Top-ladder-data/sanitized` — see `00-overview.md`).
- Example:
  ```json
  {
    "day": "2026-07-14",
    "total_episodes_seen": 5516,
    "excluded": [
      {"episode_id": 85829001, "reason": "non_done_status", "statuses": ["DONE", "ERROR"]},
      {"episode_id": 85829044, "reason": "malformed_json"}
    ],
    "episodes_written": 5498,
    "steps_total": 612340,
    "steps_usable": 401220,
    "steps_masked": 211120
  }
  ```

## Interfaces / seams
- Written by the same process as `02-episode-sanitization.md`
  (exclusions) and `03-legal-action-masking.md` (mask counts) — both feed
  their events/counts into this report as sanitization runs, rather than a
  separate pass re-reading output files.

## Out of scope
- Any dashboard, visualization, or cross-day aggregation tooling — just the
  raw per-day JSON report.

## Open questions
None.
