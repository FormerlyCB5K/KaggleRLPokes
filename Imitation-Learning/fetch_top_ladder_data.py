"""Fetch missing daily top-ladder episode archives from Kaggle.

Downloads any day in [--start-date, --end-date] (inclusive) whose zip archive
is not already present under Top-ladder-data/<month>-<day>/. Days whose
archive already exists are left untouched, so this is safe to re-run.
Assumes Kaggle API credentials are already configured on this machine
(~/.kaggle/kaggle.json, or KAGGLE_USERNAME/KAGGLE_KEY env vars).

Uses the `kaggle` Python package's API directly (`kaggle.api.dataset_download_
files`) rather than shelling out to the `kaggle` CLI executable. Initial
testing shelled out via subprocess to the `kaggle` command and hit a
ModuleNotFoundError inside the spawned process even though `import kaggle`
worked fine in-process and the same CLI command worked fine typed directly
into a shell -- some difference in how the console-script's embedded
interpreter resolved site-packages under a subprocess spawn. Calling the API
directly sidesteps that PATH/shebang resolution entirely (and is one less
moving part to break differently again on the cluster). Run this with
whatever Python has `kaggle` installed (`pip install kaggle`).

Run from the repository root, for example:

    python Imitation-Learning/fetch_top_ladder_data.py \
        --start-date 2026-07-12 --end-date 2026-07-25
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"
DATASET_OWNER = "kaggle"
DATASET_PREFIX = "pokemon-tcg-ai-battle-episodes"


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


def archive_path(data_root: Path, date: dt.date) -> Path:
    return data_root / day_dir_name(date) / f"{DATASET_PREFIX}-{date.isoformat()}.zip"


def fetch_day(date: dt.date, data_root: Path, *, api) -> str:
    target = archive_path(data_root, date)
    if target.is_file():
        return "already_present"

    target.parent.mkdir(parents=True, exist_ok=True)
    slug = f"{DATASET_OWNER}/{DATASET_PREFIX}-{date.isoformat()}"
    try:
        api.dataset_download_files(slug, path=str(target.parent), unzip=False, quiet=False)
    except Exception as exc:
        raise RuntimeError(f"kaggle download failed for {slug}: {exc}") from exc
    if not target.is_file():
        raise RuntimeError(
            f"kaggle download for {slug} reported success but {target} was not created"
        )
    return "downloaded"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--end-date", required=True, type=dt.date.fromisoformat)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.end_date < args.start_date:
        raise SystemExit("--end-date must not be before --start-date")

    import kaggle  # imported here so --help works without kaggle installed

    kaggle.api.authenticate()

    data_root = args.data_root.resolve()
    failures: list[str] = []
    for date in iter_dates(args.start_date, args.end_date):
        try:
            status = fetch_day(date, data_root, api=kaggle.api)
        except RuntimeError as exc:
            print(f"{date.isoformat()}: FAILED ({exc})", file=sys.stderr)
            failures.append(date.isoformat())
            continue
        target = _repo_path(archive_path(data_root, date))
        print(f"{date.isoformat()}: {status} -> {target}")

    if failures:
        print(f"{len(failures)} day(s) failed to fetch: {failures}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
