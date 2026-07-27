# Data Fetching

## Purpose
Get all 14 daily episode datasets (2026-07-12 through 2026-07-25) present
locally under `Imitation-Learning/Top-ladder-data/<day>/` before sanitization
runs. Days 7-12, 7-13, 7-14 already exist; 7-15 through 7-25 (11 days) must be
downloaded.

## Behavior
- Iterate the date range `2026-07-12` .. `2026-07-25` inclusive.
- Each day maps to a Kaggle dataset slug
  `kaggle/pokemon-tcg-ai-battle-episodes-<YYYY-MM-DD>` (per the manifest at
  `pokemon-tcg-ai-battle-episodes-index`).
- For each day, if
  `Imitation-Learning/Top-ladder-data/<M-D>/pokemon-tcg-ai-battle-episodes-<YYYY-MM-DD>.zip`
  does not already exist, download it via the `kaggle` **Python package's**
  API directly (`kaggle.api.dataset_download_files(slug, path=..., unzip=False)`
  after `kaggle.api.authenticate()`) — not by shelling out to the `kaggle` CLI
  executable. Initial testing found `subprocess.run(["kaggle", ...])` hit a
  `ModuleNotFoundError` inside the spawned process even though `import kaggle`
  worked fine in the same interpreter and the identical command worked fine
  typed directly into a shell — some PATH/shebang resolution difference
  between an interactive shell and a Python-spawned subprocess. Calling the
  API in-process avoids that class of problem. Requires `pip install kaggle`
  in whatever environment runs this script, and Kaggle API credentials
  configured (`~/.kaggle/kaggle.json`, or `KAGGLE_USERNAME`/`KAGGLE_KEY`).
- Do not unzip during fetch — sanitization reads directly from the zip
  (see `02-episode-sanitization.md`).
- Skip (no-op, no re-download) any day whose zip is already present, so the
  fetch step is safe to re-run.

## Data
- Input: none (pulls from Kaggle).
- Output: `Imitation-Learning/Top-ladder-data/<M-D>/pokemon-tcg-ai-battle-episodes-<YYYY-MM-DD>.zip`
  for each of the 14 days, matching the existing naming convention seen in
  `7-12/`, `7-13/`, `7-14/`.

## Interfaces / seams
- Downstream: `02-episode-sanitization.md` reads these zip paths as input.

## Out of scope
- Handling missing/invalid Kaggle credentials (assumed pre-configured).
- Retrying partial/corrupt downloads beyond a basic re-download-if-missing
  check — if a zip is corrupt, that surfaces as a malformed-episode exclusion
  in sanitization (see `02-episode-sanitization.md`), not handled here.

## Open questions
None.
