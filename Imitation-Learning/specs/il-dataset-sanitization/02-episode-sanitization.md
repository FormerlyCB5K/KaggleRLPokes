# Episode Sanitization

## Purpose
Read each day's zip of per-episode JSON files, drop episodes that are broken
or unusable, and pass everything else through to legal-action masking and
output writing.

## Behavior
For each day in the range, for each `<episode_id>.json` entry inside that
day's zip:

1. **Parse.** Attempt `json.load`. If parsing fails, or any of the required
   top-level keys are missing (`info`, `rewards`, `statuses`, `steps`),
   exclude with reason `malformed_json`.
2. **Status check.** If `statuses != ["DONE", "DONE"]` (either player not
   `DONE` — covers crashes, timeouts, disconnects), exclude with reason
   `non_done_status`, recording the actual `statuses` value.
3. Anything surviving both checks proceeds to legal-action masking
   (`03-legal-action-masking.md`) and is then written compact (no
   indent/sort_keys — see `00-overview.md`) to
   `<output-root>/<day>/<episode_id>.json`, where `<output-root>` defaults
   to `Imitation-Learning/Top-ladder-data/sanitized` (repo-relative;
   override with `--output-root` if the repo lives in a cloud-synced
   folder — see `00-overview.md`).

No other exclusion criteria apply — no minimum step-count / length filter, no
player-rating filter. Short but clean (no crash/DC) games are kept as-is.

## Data
- Input: `Imitation-Learning/Top-ladder-data/<day>/pokemon-tcg-ai-battle-episodes-<date>.zip`,
  read entry-by-entry (no need to fully extract to disk first).
- Each episode JSON shape (confirmed from `7-14/85828069.json`):
  ```
  {
    "configuration": ..., "description": ..., "id": ...,
    "info": {"Agents": [...], "EpisodeId": int, "TeamNames": [...]},
    "module_version": ..., "name": ..., "rewards": [int, int],
    "schema_version": ..., "specification": ..., "statuses": [str, str],
    "steps": [ [ {player0_step}, {player1_step} ], ... ],
    "title": ..., "version": ...
  }
  ```
  Each `{playerN_step}` has `action`, `info`, `observation`
  (`current`, `logs`, `remainingOverageTime`, `search_begin_input`, `select`,
  `step`), `reward`, `status`, `visualize`.
- Output: unmodified copy of the episode dict (plus masks added by step
  03) written to `sanitized/<day>/<episode_id>.json`.
- Exclusion events are handed off to `04-drop-report.md`, not written inline
  into any episode file.

## Interfaces / seams
- Upstream: consumes zips produced/verified present by `01-data-fetching.md`.
- Downstream: passes each surviving episode dict into the masking logic in
  `03-legal-action-masking.md` before final write.
- Every exclusion (with `episode_id`, `day`, `reason`) is reported to
  `04-drop-report.md`.

## Out of scope
- Any semantic validation of game correctness beyond parse + DONE-status
  (e.g. does not re-simulate the game or validate move legality itself).
- Deduplication across days (not required — episode IDs are assumed unique
  across the whole dataset).

## Open questions
None.
