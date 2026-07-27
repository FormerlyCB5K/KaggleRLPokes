"""Build a per-day cache of extracted `policy.data.Example`s.

`policy/train.py`'s interleaved multi-epoch training loop revisits every day-chunk
once per outer epoch (standard ML "epoch" meaning: one full pass over the whole
dataset, repeated). Extracting live on every revisit would re-run
`PrizeTracker`/`GameStateTracker`/`build_observation`/`classify_candidates` against
raw JSON once per epoch per chunk -- multiplying the ~1 episode/sec extraction cost
by `--epochs`. This script extracts each day exactly once and pickles the result to
`<cache-dir>/<source_label>/<day>.pkl` (+ a sibling `<day>.manifest.json` recording
what produced it, checked by `policy.data.manifest_matches` before a training run
trusts a cache hit), so `train.py --cache-dir ...` just loads pre-built chunks.

Per-episode extraction is independent across episodes -- the same embarrassingly
parallel shape as `build_sanitized_top_ladder_dataset.py`'s per-episode JSON work,
which measured a 6.7x speedup from parallelizing across a `ProcessPoolExecutor`
(22m18s -> 3m19s for one day, 5,050 episodes). This script uses the identical
pattern: a per-worker-process handle opened once via a pool initializer, results
collected via `pool.map`, written atomically (temp file + `os.replace`).

IMPORTANT if your repo lives inside a cloud-synced folder (OneDrive/Dropbox/etc.):
cache files can be several GB per day. Point --cache-dir outside the synced tree
if that applies -- see build_sanitized_top_ladder_dataset.py's own module docstring
for the OneDrive-sync-contention story this generalizes from.

Run from the repository root, for example:

    python Imitation-Learning/build_example_cache.py \
        --source sanitized --sanitized-dir Imitation-Learning/Top-ladder-data/sanitized \
        --max-episodes-per-zip all --max-steps 300 --workers 8
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor
from functools import partial

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = _HERE
sys.path.insert(0, _IL_ROOT)

from policy import data as data_mod  # noqa: E402

DEFAULT_RAW_DIR = os.path.join(_IL_ROOT, "Top-ladder-data")
DEFAULT_SANITIZED_DIR = os.path.join(_IL_ROOT, "Top-ladder-data", "sanitized")
# Sibling of Top-ladder-data/sanitized/, same convention.
DEFAULT_CACHE_DIR = os.path.join(_IL_ROOT, "Top-ladder-data", "example-cache")
DEFAULT_WORKERS = max(1, min(16, (os.cpu_count() or 4) - 2))


def _write_atomic_bytes(path: str, content: bytes) -> None:
    # Temp file in the same directory so os.replace is a same-volume rename.
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "xb") as handle:
        handle.write(content)
    os.replace(temp_path, path)


def _write_atomic_pickle(path: str, value) -> None:
    """Stream a pickle to the sibling temp file before replacing the target.

    ``pickle.dumps`` would create a second multi-GB in-memory copy of a full
    day's examples, defeating the day-sized memory bound this pipeline exists to
    provide.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp_path, "xb") as handle:
        pickle.dump(value, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temp_path, path)


# ---- Raw-archive worker pool (per-worker zip handle, opened once) ------------------
_worker_zip: zipfile.ZipFile | None = None


def _init_raw_worker(archive_path: str) -> None:
    global _worker_zip
    _worker_zip = zipfile.ZipFile(archive_path)


def _process_raw_episode(member_filename: str, *, max_steps: int) -> list:
    assert _worker_zip is not None
    try:
        data = json.loads(_worker_zip.read(member_filename))
        return data_mod._safe_episode_examples(
            data, member_filename, _worker_zip.filename, max_steps
        )
    except Exception as exc:
        print(
            f"WARNING: skipping episode {member_filename!r} in "
            f"{_worker_zip.filename}: {exc}",
            file=sys.stderr,
        )
        return []


# ---- Sanitized-dir worker (no shared handle needed -- each episode is its own file)
def _process_sanitized_episode(file_path: str, *, day_dir: str, max_steps: int) -> list:
    try:
        with open(file_path, "rb") as handle:
            data = json.load(handle)
        return data_mod._safe_episode_examples(
            data, os.path.basename(file_path), day_dir, max_steps
        )
    except Exception as exc:
        print(
            f"WARNING: skipping episode {os.path.basename(file_path)!r} "
            f"in {day_dir}: {exc}",
            file=sys.stderr,
        )
        return []


def build_day_cache(
    source_label: str, day: str, source_root: str, cache_dir: str,
    *, max_episodes_per_zip: int | None, max_steps: int, workers: int, force: bool,
) -> dict:
    """Builds/refreshes `<cache_dir>/<source_label>/<day>.pkl` + `.manifest.json`
    for one `(source_label, day)` pair. Idempotent: if an existing manifest already
    matches the requested params/fingerprint/schema, skips (unless `force`)."""
    day_source_dir = os.path.join(source_root, day)

    if source_label == "raw":
        zips = sorted(
            f for f in os.listdir(day_source_dir) if f.endswith(".zip")
        ) if os.path.isdir(day_source_dir) else []
        if not zips:
            raise FileNotFoundError(f"no raw archive found for {day} under {day_source_dir!r}")
        archive_paths = [os.path.join(day_source_dir, filename) for filename in zips]
        fingerprint = data_mod._raw_day_fingerprint(day_source_dir)
    else:
        if not os.path.isdir(day_source_dir):
            raise FileNotFoundError(f"no sanitized directory found for {day} under {day_source_dir!r}")
        archive_paths = []
        fingerprint = data_mod._sanitized_dir_fingerprint(day_source_dir)

    examples_path, manifest_path = data_mod.cache_file_paths(cache_dir, source_label, day)

    if not force and os.path.isfile(manifest_path) and os.path.isfile(examples_path):
        with open(manifest_path) as handle:
            existing_manifest = json.load(handle)
        ok, _ = data_mod.manifest_matches(
            existing_manifest, max_episodes_per_zip=max_episodes_per_zip,
            max_steps=max_steps, source_fingerprint=fingerprint,
            source_label=source_label, day=day,
        )
        if ok:
            print(f"{source_label}/{day}: up to date, skipping")
            return {"status": "skipped", "source_label": source_label, "day": day}

    t0 = time.time()
    results: list[list] = []
    episode_count = 0
    if source_label == "raw":
        for archive_path in archive_paths:
            names = data_mod._episode_names(archive_path, max_episodes_per_zip)
            episode_count += len(names)
            with ProcessPoolExecutor(
                max_workers=workers, initializer=_init_raw_worker, initargs=(archive_path,),
            ) as pool:
                results.extend(
                    pool.map(
                        partial(_process_raw_episode, max_steps=max_steps),
                        names,
                        chunksize=8,
                    )
                )
    else:
        names = sorted(
            f for f in os.listdir(day_source_dir) if f.endswith(".json") and f != "report.json"
        )
        if max_episodes_per_zip is not None:
            names = names[:max_episodes_per_zip]
        episode_count = len(names)
        file_paths = [os.path.join(day_source_dir, n) for n in names]
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = list(
                pool.map(
                    partial(_process_sanitized_episode, day_dir=day_source_dir, max_steps=max_steps),
                    file_paths, chunksize=8,
                )
            )

    all_examples = [ex for episode_examples in results for ex in episode_examples]
    del results
    elapsed = time.time() - t0

    manifest = data_mod.build_manifest(
        source_label=source_label, day=day, max_episodes_per_zip=max_episodes_per_zip,
        max_steps=max_steps, source_fingerprint=fingerprint, n_examples=len(all_examples),
    )
    _write_atomic_pickle(examples_path, all_examples)
    _write_atomic_bytes(manifest_path, json.dumps(manifest, indent=2).encode("utf-8"))

    print(
        f"{source_label}/{day}: episodes={episode_count} "
        f"examples={len(all_examples)} elapsed={elapsed:.1f}s"
    )
    return {
        "status": "built", "source_label": source_label, "day": day,
        "n_episodes": episode_count, "n_examples": len(all_examples), "elapsed_s": elapsed,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("raw", "sanitized", "both"), default="sanitized")
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    parser.add_argument("--sanitized-dir", default=DEFAULT_SANITIZED_DIR)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument(
        "--max-episodes-per-zip", type=data_mod.parse_episode_limit, default=None,
        help="cap episodes per day; default None (uncapped) -- this script's whole "
             "purpose is enabling full-dataset training, unlike train.py's own "
             "small default of 20. Use 'all' explicitly for an uncapped run",
    )
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument(
        "--days", default=None,
        help="comma-separated day filter (e.g. 7-12,7-14); default: every day found "
             "for --source under --raw-dir/--sanitized-dir",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--force", action="store_true",
        help="rebuild even if an existing cache already matches the requested params",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root_by_label = {"raw": args.raw_dir, "sanitized": args.sanitized_dir}
    if args.workers < 1:
        raise ValueError(f"workers must be >= 1, got {args.workers}")
    if args.max_steps < 1:
        raise ValueError(f"max_steps must be >= 1, got {args.max_steps}")

    available_pairs = data_mod.list_source_day_pairs(
        raw_dir=args.raw_dir, sanitized_dir=args.sanitized_dir, source=args.source,
    )
    if args.days:
        requested_days = {d.strip() for d in args.days.split(",") if d.strip()}
        selected_pairs = [pair for pair in available_pairs if pair[1] in requested_days]
        missing_days = sorted(
            requested_days - {day for _label, day in selected_pairs}
        )
        if missing_days:
            print(
                "requested day(s) not found in selected source(s): "
                + ", ".join(missing_days),
                file=sys.stderr,
            )
            return 1
    else:
        selected_pairs = available_pairs

    if not selected_pairs:
        print("no source/day pairs found", file=sys.stderr)
        return 1

    built = skipped = failed = 0
    for label, day in selected_pairs:
        try:
            report = build_day_cache(
                label, day, root_by_label[label], args.cache_dir,
                max_episodes_per_zip=args.max_episodes_per_zip, max_steps=args.max_steps,
                workers=args.workers, force=args.force,
            )
        except FileNotFoundError as exc:
            print(f"{label}/{day}: SKIPPED ({exc})", file=sys.stderr)
            failed += 1
            continue
        if report["status"] == "skipped":
            skipped += 1
        else:
            built += 1

    print(f"done: {built} built, {skipped} up-to-date, {failed} missing/failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
