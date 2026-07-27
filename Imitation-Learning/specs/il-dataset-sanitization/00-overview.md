# Sanitized Top-Ladder IL Dataset — Overview

## What this is
A pipeline that pulls the past 14 days (2026-07-12 through 2026-07-25) of daily
"PTCG AI Battle Challenge" episode datasets from Kaggle, drops broken episodes,
and flags every position where the acting player had only one legal action —
producing a replacement for the current imitation-learning training corpus.

## Scope (v1)
- Fetch the 11 missing daily zips (7-15 through 7-25) via the Kaggle API into
  `Imitation-Learning/Top-ladder-data/<day>/`, alongside the 3 already present
  (7-12, 7-13, 7-14).
- Parse every per-episode JSON in each day's zip.
- Exclude episodes that are malformed/truncated, or where either player's
  status isn't `DONE`.
- For every remaining episode, add a per-step `usable` boolean mask: `false`
  when the acting player's `observation.select.option` list has length 1,
  `true` otherwise. Steps are never deleted.
- Write surviving episodes as individual **compact** JSON files (no
  indentation/key-sorting — this data is machine-read only) under
  `<output-root>/<day>/<episode_id>.json`, same shape as source plus the
  mask. `<output-root>` defaults to `Imitation-Learning/Top-ladder-data/sanitized`
  (repo-relative, portable) — see Key decisions for a machine-specific gotcha.
- Emit a per-day drop-report: excluded episode IDs + reason, and step-mask
  counts (kept vs. masked-out).

## Explicitly out of scope
- Fixing the known PrizeTracker bug (corrupts prize/deck counts) — tracked
  separately, not touched here.
- Converting sanitized episodes into packed training tensors — that's the
  existing `Imitation-Learning/policy/data.py` / `packing.py` pipeline,
  run as a later, separate step against this dataset's output.
- Any filtering by game length or player rating — top-ladder games are
  assumed good quality; only crashes/disconnects/malformed data are dropped.

## Success criteria
- All 14 days (7-12 through 7-25) have a `sanitized/<day>/` folder populated.
- Every surviving episode JSON has one `usable: bool` field added per step
  entry (per acting player), and is otherwise byte-identical in structure to
  the source episode.
- A drop-report exists per day (or one combined report) listing every
  excluded episode ID with its exclusion reason, and aggregate step-mask
  counts.
- Re-running the pipeline on an already-sanitized day is idempotent (same
  output, no duplicate downloads).

## Components
- `01-data-fetching.md` — downloading the 11 missing daily datasets via Kaggle API
- `02-episode-sanitization.md` — parsing raw episodes and applying exclusion rules
- `03-legal-action-masking.md` — computing the per-step `usable` mask
- `04-drop-report.md` — manifest format for excluded episodes and mask stats

## Key decisions
- This dataset **replaces** the current IL training data going forward.
- Legal-action counts are read directly from each step's
  `observation.select.option` array — no engine replay needed to derive them.
- Steps are never physically removed; a boolean mask flag is added instead,
  since each step already carries a full state snapshot (`observation.current`)
  and later steps may still need full context.
- Output is filtered raw JSON, not pre-packed tensors — encoding/packing
  stays a separate downstream step.
- No length or rating-based filtering — only DONE-status and malformed-JSON
  exclusions apply.
- Output JSON is written compact (no `indent`, no `sort_keys`). An initial
  test run with `indent=2, sort_keys=True` produced files 2.68x larger than
  the raw source (3.94MB → 10.58MB for the same episode) and was
  correspondingly slower to encode, for no benefit on a machine-only dataset.
- Sanitized output defaults to a repo-relative path (`Top-ladder-data/sanitized`)
  for portability (e.g. an unmodified run on a cluster). On the original dev
  machine the repo happens to live under a OneDrive-synced Desktop folder;
  writing ~5,000 multi-megabyte files/day there caused severe slowdowns from
  OneDrive's sync filter driver intercepting every write. That's a
  machine-specific gotcha, not something to bake into the default — pass
  `--output-root` pointing outside any cloud-synced folder if you hit it.
- Per-day uncompressed size is ~21GB (per the Kaggle manifest), so 14 days of
  full per-episode copies is ~294GB — this must fit on disk wherever
  `--output-root` points; verify free space before running the full range.
- Per-episode work (parse + mask + dump) is CPU-bound (~260ms/episode in
  profiling — json parse/dump dominate; I/O is ~17ms) and independent across
  episodes, so it's parallelized with a `ProcessPoolExecutor` (`--workers`,
  default `min(16, cpu_count - 2)`). Measured 6.7x speedup on one day
  (5,050 episodes): 22m18s single-process → 3m19s parallelized, same output.
- Sample results across the 3 locally-sanitized days (7-12/13/14, 15,018
  episodes seen): episode-level exclusion is negligible (42 `non_done_status`,
  0 `malformed_json` — 0.28% of episodes), while step-level masking is
  substantial (547,670 of 4,397,340 decision points, 12.5%, were
  single-legal-option). The two exclusion mechanisms operate at very
  different scales; masking is the consequential one.
- Raw data is never modified or deleted by this pipeline — exclusion means a
  bad episode is simply not written to `<output-root>`, and masking adds a
  boolean flag rather than removing steps. `Top-ladder-data/<day>/*.zip`
  stays untouched as the ground truth.
- `Imitation-Learning/policy/data.py` now reads either the raw zips or this
  sanitized dataset (or both — see `iter_all_examples`'s `source` param and
  `train.py --source/--raw-dir/--sanitized-dir`), and `iter_paired_decisions`
  skips any step where `select.usable is False`. Raw episodes have no
  `usable` key, so reading raw zips directly is unaffected — the mask only
  takes effect when reading from `<output-root>`.

## Open questions
- None outstanding. (PrizeTracker bug interaction explicitly deferred to a
  separate task; not a gap in this spec.)
