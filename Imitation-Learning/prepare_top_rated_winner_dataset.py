#!/usr/bin/env python
"""Prepare a compact, top-rated replay corpus with selectable perspectives.

For each requested daily raw archive, this script:

1. ranks manifest rows by ``min_score`` (the lower-rated player in the game);
2. selects the top ``ceil(fraction * manifest rows)`` games deterministically;
3. applies the existing DONE-status and forced-choice sanitization contract;
4. keeps either the winner's actions or both players' actions;
5. always keeps both perspectives for numeric draws; and
6. excludes malformed, non-DONE, or non-numeric-result episodes.

The complete observations and both submitted decks remain in every written replay.
Only non-selected action labels are blanked, so the existing engine-native cache
builder can consume the output without a second winner-filter implementation.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import shutil
import uuid
import zipfile
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any

from build_sanitized_top_ladder_dataset import (
    _json_bytes,
    _repo_path,
    _write_atomic,
    mask_episode,
    sanitize_member,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPOSITORY_ROOT / "Imitation-Learning" / "Top-ladder-data"
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "top-rated-winner-three-days"
DEFAULT_DAYS = ("7-23", "7-24", "7-25")
DEFAULT_FRACTION = 0.10
DEFAULT_SCORE_COLUMN = "min_score"
DEFAULT_PERSPECTIVE_MODE = "winner"
DEFAULT_WORKERS = max(1, min(16, (os.cpu_count() or 4) - 2))
REPORT_SCHEMAS = {
    "winner": "top-rated-winner-replays-v1",
    "all": "top-rated-all-perspectives-replays-v1",
}
SCORE_COLUMNS = ("min_score", "avg_score")
PERSPECTIVE_MODES = tuple(REPORT_SCHEMAS)


class PreparationError(RuntimeError):
    """The raw inventory or a selected episode violates the data contract."""


def _parse_days(value: str) -> tuple[str, ...]:
    days = tuple(item.strip() for item in value.split(",") if item.strip())
    if not days:
        raise argparse.ArgumentTypeError("at least one day is required")
    if len(days) != len(set(days)):
        raise argparse.ArgumentTypeError("days must be unique")
    for day in days:
        parts = day.split("-")
        if (
            len(parts) != 2
            or not all(part.isdigit() for part in parts)
            or not 1 <= int(parts[0]) <= 12
            or not 1 <= int(parts[1]) <= 31
        ):
            raise argparse.ArgumentTypeError(
                f"invalid day {day!r}; expected M-D such as 7-23"
            )
    return days


def _find_archive(data_root: Path, day: str) -> Path:
    day_dir = data_root / day
    if not day_dir.is_dir():
        raise PreparationError(f"missing raw day directory: {day_dir}")
    matches = sorted(day_dir.glob("*.zip"))
    if len(matches) != 1:
        raise PreparationError(
            f"{day}: expected exactly one raw archive, found {len(matches)}"
        )
    return matches[0]


def _read_manifest(bundle: zipfile.ZipFile, *, day: str) -> list[dict[str, Any]]:
    try:
        manifest_bytes = bundle.read("manifest.csv")
    except KeyError as exc:
        raise PreparationError(f"{day}: archive has no manifest.csv") from exc
    try:
        reader = csv.DictReader(
            io.StringIO(manifest_bytes.decode("utf-8-sig", errors="strict"))
        )
        required = {
            "episode_id",
            "avg_score",
            "min_score",
            "sum_score",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise PreparationError(
                f"{day}: manifest is missing required columns {sorted(required)}"
            )
        rows: list[dict[str, Any]] = []
        seen: set[int] = set()
        for raw in reader:
            episode_id = int(raw["episode_id"])
            if episode_id in seen:
                raise PreparationError(
                    f"{day}: duplicate manifest episode_id {episode_id}"
                )
            seen.add(episode_id)
            scores = {
                "avg_score": float(raw["avg_score"]),
                "min_score": float(raw["min_score"]),
                "sum_score": float(raw["sum_score"]),
            }
            if not all(math.isfinite(value) for value in scores.values()):
                raise PreparationError(
                    f"{day}: episode {episode_id} has a non-finite score"
                )
            rows.append(
                {
                    "episode_id": episode_id,
                    **scores,
                }
            )
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise PreparationError(f"{day}: malformed manifest.csv: {exc}") from exc
    if not rows:
        raise PreparationError(f"{day}: manifest.csv contains no episodes")
    return rows


def select_manifest_rows(
    rows: list[dict[str, Any]],
    *,
    fraction: float,
    score_column: str,
) -> list[dict[str, Any]]:
    """Return a deterministic top fraction, annotated with one-based rank."""

    if not 0.0 < fraction <= 1.0:
        raise PreparationError("fraction must be greater than zero and at most one")
    if score_column not in SCORE_COLUMNS:
        raise PreparationError(
            f"score_column must be one of {', '.join(SCORE_COLUMNS)}"
        )
    secondary = "avg_score" if score_column == "min_score" else "min_score"
    ordered = sorted(
        rows,
        key=lambda row: (
            -float(row[score_column]),
            -float(row[secondary]),
            int(row["episode_id"]),
        ),
    )
    count = math.ceil(fraction * len(ordered))
    return [
        {**row, "selection_rank": index}
        for index, row in enumerate(ordered[:count], start=1)
    ]


def _numeric_rewards(episode: dict[str, Any]) -> tuple[float, float] | None:
    rewards = episode.get("rewards")
    if not isinstance(rewards, list) or len(rewards) != 2:
        return None
    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        for value in rewards
    ):
        return None
    return float(rewards[0]), float(rewards[1])


def _is_deck_submission(action: Any) -> bool:
    return (
        isinstance(action, list)
        and len(action) == 60
        and all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in action
        )
    )


def restrict_episode_to_perspectives(
    episode: dict[str, Any], players: tuple[int, ...]
) -> int:
    """Blank non-selected action labels while preserving submitted decks."""

    allowed = set(players)
    filtered = 0
    for step in episode.get("steps") or []:
        if not isinstance(step, list):
            continue
        for player, entry in enumerate(step):
            if player in allowed or not isinstance(entry, dict):
                continue
            action = entry.get("action")
            if action and not _is_deck_submission(action):
                entry["action"] = []
                filtered += 1
    return filtered


def prepare_episode(
    raw: bytes,
    *,
    selection: dict[str, Any],
    score_column: str,
    perspective_mode: str = DEFAULT_PERSPECTIVE_MODE,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Sanitize and label one selected episode."""

    if perspective_mode not in PERSPECTIVE_MODES:
        raise PreparationError(
            f"perspective_mode must be one of {', '.join(PERSPECTIVE_MODES)}"
        )
    episode, exclusion = sanitize_member(raw)
    if episode is None:
        return None, dict(exclusion or {"reason": "malformed_json"})

    rewards = _numeric_rewards(episode)
    if rewards is None:
        return None, {"reason": "non_numeric_result", "rewards": episode.get("rewards")}
    if rewards[0] == rewards[1]:
        outcome = "draw"
        perspectives = (0, 1)
    else:
        outcome = "decisive"
        winner = 0 if rewards[0] > rewards[1] else 1
        perspectives = (0, 1) if perspective_mode == "all" else (winner,)

    filtered_actions = restrict_episode_to_perspectives(episode, perspectives)
    steps_total, steps_usable, steps_masked = mask_episode(episode)
    episode["dataset_selection"] = {
        "schema": REPORT_SCHEMAS[perspective_mode],
        "score_column": score_column,
        "perspective_mode": perspective_mode,
        "selection_rank": int(selection["selection_rank"]),
        "avg_score": float(selection["avg_score"]),
        "min_score": float(selection["min_score"]),
        "sum_score": float(selection["sum_score"]),
        "outcome": outcome,
        "supervised_players": list(perspectives),
    }
    return episode, {
        "written": True,
        "outcome": outcome,
        "supervised_players": list(perspectives),
        "filtered_actions": filtered_actions,
        "steps_total": steps_total,
        "steps_usable": steps_usable,
        "steps_masked": steps_masked,
    }


_worker_bundle: zipfile.ZipFile | None = None


def _init_worker(archive_path: str) -> None:
    global _worker_bundle
    if _worker_bundle is not None:
        _worker_bundle.close()
    _worker_bundle = zipfile.ZipFile(archive_path)


def _process_selection(
    selection: dict[str, Any],
    *,
    output_dir: str,
    score_column: str,
    perspective_mode: str,
) -> dict[str, Any]:
    assert _worker_bundle is not None
    episode_id = int(selection["episode_id"])
    member = f"{episode_id}.json"
    result = {
        "episode_id": episode_id,
        "selection_rank": int(selection["selection_rank"]),
        "avg_score": float(selection["avg_score"]),
        "min_score": float(selection["min_score"]),
        "sum_score": float(selection["sum_score"]),
    }
    try:
        raw = _worker_bundle.read(member)
    except KeyError:
        return {**result, "reason": "missing_episode_member"}
    except (RuntimeError, zipfile.BadZipFile):
        return {**result, "reason": "malformed_json"}

    episode, disposition = prepare_episode(
        raw,
        selection=selection,
        score_column=score_column,
        perspective_mode=perspective_mode,
    )
    if episode is None:
        return {**result, **disposition}
    info = episode.get("info")
    recorded_id = info.get("EpisodeId") if isinstance(info, dict) else None
    if recorded_id is not None and int(recorded_id) != episode_id:
        return {
            **result,
            "reason": "episode_id_mismatch",
            "recorded_episode_id": recorded_id,
        }
    _write_atomic(
        Path(output_dir) / member,
        _json_bytes(episode),
    )
    return {**result, **disposition}


def _replace_day_directory(
    staging: Path, destination: Path, *, overwrite: bool
) -> None:
    if destination.exists():
        if not overwrite:
            raise PreparationError(
                f"output day already exists: {destination}; pass --overwrite to replace it"
            )
        resolved = destination.resolve()
        parent = destination.parent.resolve()
        if resolved.parent != parent or resolved.name in ("", ".", ".."):
            raise PreparationError(f"unsafe output day path: {resolved}")
        shutil.rmtree(resolved)
    os.replace(staging, destination)


def process_day(
    *,
    day: str,
    data_root: Path,
    output_root: Path,
    fraction: float = DEFAULT_FRACTION,
    score_column: str = DEFAULT_SCORE_COLUMN,
    perspective_mode: str = DEFAULT_PERSPECTIVE_MODE,
    workers: int = DEFAULT_WORKERS,
    overwrite: bool = False,
) -> dict[str, Any]:
    if workers < 1:
        raise PreparationError("workers must be positive")
    if perspective_mode not in PERSPECTIVE_MODES:
        raise PreparationError(
            f"perspective_mode must be one of {', '.join(PERSPECTIVE_MODES)}"
        )
    archive = _find_archive(data_root, day)
    with zipfile.ZipFile(archive) as bundle:
        rows = _read_manifest(bundle, day=day)
    selected = select_manifest_rows(
        rows, fraction=fraction, score_column=score_column
    )

    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / day
    staging = output_root / f".{day}.{uuid.uuid4().hex}.tmp"
    staging.mkdir()
    try:
        if workers == 1:
            _init_worker(str(archive))
            try:
                results = [
                    _process_selection(
                        selection,
                        output_dir=str(staging),
                        score_column=score_column,
                        perspective_mode=perspective_mode,
                    )
                    for selection in selected
                ]
            finally:
                assert _worker_bundle is not None
                _worker_bundle.close()
        else:
            with ProcessPoolExecutor(
                max_workers=workers,
                initializer=_init_worker,
                initargs=(str(archive),),
            ) as pool:
                results = list(
                    pool.map(
                        partial(
                            _process_selection,
                            output_dir=str(staging),
                            score_column=score_column,
                            perspective_mode=perspective_mode,
                        ),
                        selected,
                        chunksize=4,
                    )
                )

        written = [item for item in results if item.get("written")]
        excluded = [item for item in results if not item.get("written")]
        report = {
            "schema": REPORT_SCHEMAS[perspective_mode],
            "day": day,
            "source_archive": _repo_path(archive),
            "selection": {
                "fraction": fraction,
                "rounding": "ceil",
                "score_column": score_column,
                "perspective_mode": perspective_mode,
                "tie_break": [
                    (
                        "avg_score_desc"
                        if score_column == "min_score"
                        else "min_score_desc"
                    ),
                    "episode_id_asc",
                ],
                "manifest_episodes": len(rows),
                "selected_episodes": len(selected),
                "cutoff_score": float(selected[-1][score_column]),
            },
            "total_episodes_seen": len(selected),
            "episodes_written": len(written),
            "excluded": sorted(excluded, key=lambda item: item["selection_rank"]),
            "outcomes": {
                "decisive": sum(item.get("outcome") == "decisive" for item in written),
                "draw": sum(item.get("outcome") == "draw" for item in written),
            },
            "filtered_loser_actions": sum(
                int(item["filtered_actions"]) for item in written
            ),
            "steps_total": sum(int(item["steps_total"]) for item in written),
            "steps_usable": sum(int(item["steps_usable"]) for item in written),
            "steps_masked": sum(int(item["steps_masked"]) for item in written),
            "episodes": sorted(written, key=lambda item: item["selection_rank"]),
        }
        _write_atomic(staging / "report.json", _json_bytes(report))
        _replace_day_directory(staging, destination, overwrite=overwrite)
        return report
    except BaseException:
        if staging.is_dir():
            shutil.rmtree(staging)
        raise


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--days", type=_parse_days, default=DEFAULT_DAYS)
    parser.add_argument("--fraction", type=float, default=DEFAULT_FRACTION)
    parser.add_argument(
        "--score-column",
        choices=SCORE_COLUMNS,
        default=DEFAULT_SCORE_COLUMN,
    )
    parser.add_argument(
        "--perspectives",
        choices=PERSPECTIVE_MODES,
        default=DEFAULT_PERSPECTIVE_MODE,
        help="Use winner actions only, or actions from both players.",
    )
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Atomically replace existing selected day directories.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_root = args.data_root.resolve()
    output_root = args.output_root.resolve()
    if data_root == output_root or output_root in data_root.parents:
        raise SystemExit("output root must not contain or equal the raw data root")
    summaries = []
    for day in args.days:
        report = process_day(
            day=day,
            data_root=data_root,
            output_root=output_root,
            fraction=args.fraction,
            score_column=args.score_column,
            perspective_mode=args.perspectives,
            workers=args.workers,
            overwrite=args.overwrite,
        )
        summaries.append(report)
        print(
            f"{day}: manifest={report['selection']['manifest_episodes']} "
            f"selected={report['selection']['selected_episodes']} "
            f"written={report['episodes_written']} "
            f"decisive={report['outcomes']['decisive']} "
            f"draws={report['outcomes']['draw']} "
            f"excluded={len(report['excluded'])}",
            flush=True,
        )
    print(
        json.dumps(
            {
                "output_root": str(output_root),
                "days": list(args.days),
                "score_column": args.score_column,
                "perspective_mode": args.perspectives,
                "fraction": args.fraction,
                "games_written": sum(item["episodes_written"] for item in summaries),
                "decisive_games": sum(
                    item["outcomes"]["decisive"] for item in summaries
                ),
                "draws": sum(item["outcomes"]["draw"] for item in summaries),
                "excluded": sum(len(item["excluded"]) for item in summaries),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
