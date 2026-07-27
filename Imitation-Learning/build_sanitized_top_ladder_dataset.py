"""Build the sanitized top-ladder IL dataset.

Reads each day's raw Kaggle episode archive under Top-ladder-data/<day>/,
drops episodes that are malformed or where either player's status isn't
DONE, adds a per-step `usable` legal-action mask (false where the acting
player had exactly one legal option that step), and writes surviving
episodes plus a per-day drop report to <output-root>/<day>/.

Output is compact JSON (no indent, no key sorting) — this dataset is
machine-read only, and pretty-printing the large nested per-step arrays
roughly triples both write time and on-disk size for no benefit.

The default output root is repo-relative (Top-ladder-data/sanitized), for
portability across machines (e.g. a cluster). IMPORTANT if your repo lives
inside a cloud-synced folder (OneDrive/Dropbox/etc.) as it did during initial
development on Windows: writing ~5,000 multi-megabyte files/day into an
actively-synced folder gets every write intercepted by the sync client's
filter driver and queued for upload, which dominated wall-clock time far
more than JSON encoding did. Pass --output-root pointing outside the synced
tree in that case.

Per-episode work (json.loads + mask + json.dumps) is CPU-bound and
independent across episodes — profiling showed ~260ms/episode of pure
Python JSON parse/dump time versus ~17ms of I/O, so this is parallelized
across worker processes (see --workers) rather than run single-threaded.

Run from the repository root, for example:

    python Imitation-Learning/build_sanitized_top_ladder_dataset.py \
        --start-date 2026-07-12 --end-date 2026-07-25
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"
# Repo-relative by default for portability (e.g. running unmodified on a
# cluster). Override with --output-root if the repo sits inside a
# cloud-synced folder (OneDrive/Dropbox/etc.) — see module docstring.
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "sanitized"
DEFAULT_WORKERS = max(1, min(16, (os.cpu_count() or 4) - 2))

REQUIRED_EPISODE_KEYS = ("info", "rewards", "statuses", "steps")
DONE_STATUSES = ["DONE", "DONE"]


def _repo_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def iter_dates(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def day_dir_name(date: dt.date) -> str:
    return f"{date.month}-{date.day}"


def find_archive(data_root: Path, date: dt.date) -> Path | None:
    day_dir = data_root / day_dir_name(date)
    if not day_dir.is_dir():
        return None
    matches = sorted(p for p in day_dir.glob("*.zip") if date.isoformat() in p.name)
    return matches[0] if matches else None


def sanitize_member(raw: bytes) -> tuple[dict | None, dict | None]:
    """Parse and validate one episode. Returns (episode, exclusion) — exactly
    one of the two is not None."""
    try:
        episode = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, {"reason": "malformed_json"}

    if not isinstance(episode, dict) or any(
        key not in episode for key in REQUIRED_EPISODE_KEYS
    ):
        return None, {"reason": "malformed_json"}

    statuses = episode.get("statuses")
    if statuses != DONE_STATUSES:
        return None, {"reason": "non_done_status", "statuses": statuses}

    return episode, None


def mask_episode(episode: dict) -> tuple[int, int, int]:
    """Add select.usable in place for every non-null select with an option
    list. Returns (steps_total, steps_usable, steps_masked)."""
    steps_total = 0
    steps_usable = 0
    steps_masked = 0
    for step in episode.get("steps") or []:
        if not isinstance(step, list):
            continue
        for player_entry in step:
            if not isinstance(player_entry, dict):
                continue
            observation = player_entry.get("observation")
            if not isinstance(observation, dict):
                continue
            select = observation.get("select")
            if not isinstance(select, dict):
                continue
            steps_total += 1
            option = select.get("option")
            if option is None:
                continue
            usable = len(option) != 1
            select["usable"] = usable
            if usable:
                steps_usable += 1
            else:
                steps_masked += 1
    return steps_total, steps_usable, steps_masked


def _json_bytes(value: object) -> bytes:
    # Compact, unsorted: this dataset is machine-read only. Pretty-printing the
    # large nested per-step arrays (indent=2 + sort_keys) roughly tripled both
    # write time and on-disk size in testing, for no downstream benefit.
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _write_atomic(path: Path, content: bytes) -> None:
    # Write the temp file in the destination directory (not a system temp dir)
    # so os.replace is a same-volume rename rather than a cross-device copy.
    temp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with temp_path.open("xb") as handle:
        handle.write(content)
    os.replace(temp_path, path)


# Per-worker-process global: each worker opens the archive once (in
# _init_worker) and reuses that handle for every member it's assigned,
# instead of reopening the zip's central directory per episode.
_worker_zip: zipfile.ZipFile | None = None


def _init_worker(archive_path: str) -> None:
    global _worker_zip
    _worker_zip = zipfile.ZipFile(archive_path)


def _process_member(member_filename: str, *, day_output_dir: str) -> dict:
    assert _worker_zip is not None
    episode_id = Path(member_filename).stem
    try:
        raw = _worker_zip.read(member_filename)
    except (KeyError, RuntimeError, zipfile.BadZipFile):
        return {"episode_id": episode_id, "reason": "malformed_json"}

    episode, exclusion = sanitize_member(raw)
    if episode is None:
        return {"episode_id": episode_id, **exclusion}

    steps_total, steps_usable, steps_masked = mask_episode(episode)
    _write_atomic(Path(day_output_dir) / f"{episode_id}.json", _json_bytes(episode))
    return {
        "episode_id": episode_id,
        "written": True,
        "steps_total": steps_total,
        "steps_usable": steps_usable,
        "steps_masked": steps_masked,
    }


def process_day(
    date: dt.date, data_root: Path, output_root: Path, *, workers: int = DEFAULT_WORKERS
) -> dict:
    archive = find_archive(data_root, date)
    if archive is None:
        raise FileNotFoundError(f"no source archive found for {date.isoformat()}")

    day_output_dir = output_root / day_dir_name(date)
    if day_output_dir.exists():
        shutil.rmtree(day_output_dir)
    day_output_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as bundle:
        member_names = sorted(
            m.filename
            for m in bundle.infolist()
            if not m.is_dir() and m.filename.lower().endswith(".json")
        )

    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker, initargs=(str(archive),)
    ) as pool:
        results = list(
            pool.map(
                partial(_process_member, day_output_dir=str(day_output_dir)),
                member_names,
                chunksize=8,
            )
        )

    excluded = [r for r in results if not r.get("written")]
    written = [r for r in results if r.get("written")]

    report = {
        "day": date.isoformat(),
        "total_episodes_seen": len(member_names),
        "excluded": sorted(excluded, key=lambda e: str(e["episode_id"])),
        "episodes_written": len(written),
        "steps_total": sum(r["steps_total"] for r in written),
        "steps_usable": sum(r["steps_usable"] for r in written),
        "steps_masked": sum(r["steps_masked"] for r in written),
        "source_archive": _repo_path(archive),
    }
    _write_atomic(day_output_dir / "report.json", _json_bytes(report))
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.end_date < args.start_date:
        raise SystemExit("--end-date must not be before --start-date")

    data_root = args.data_root.resolve()
    output_root = args.output_root.resolve()

    missing_days: list[str] = []
    for date in iter_dates(args.start_date, args.end_date):
        try:
            report = process_day(date, data_root, output_root, workers=args.workers)
        except FileNotFoundError as exc:
            print(f"{date.isoformat()}: SKIPPED ({exc})", file=sys.stderr)
            missing_days.append(date.isoformat())
            continue
        print(
            f"{report['day']}: seen={report['total_episodes_seen']} "
            f"written={report['episodes_written']} "
            f"excluded={len(report['excluded'])} "
            f"steps_usable={report['steps_usable']} "
            f"steps_masked={report['steps_masked']}"
        )

    if missing_days:
        print(f"missing source archives for: {missing_days}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
