#!/usr/bin/env python
"""Build the immutable six-day engine-native imitation cache."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve()
ENGINE_ROOT = SCRIPT.parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parent
DEFAULT_CACHE_ROOT = (
    REPOSITORY_ROOT
    / "Imitation-Learning"
    / "Top-ladder-data"
    / "engine-native-cache-test-six-days"
)
sys.path.insert(0, str(ENGINE_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT))

from engine_native_policy.il.cache import (  # noqa: E402
    DEFAULT_DAYS,
    DEFAULT_SEED,
    DEFAULT_TARGET_SHARD_ROWS,
    DEFAULT_VALIDATION_FRACTION,
    build_cache,
)


def _days(value: str) -> tuple[str, ...]:
    parsed = tuple(item.strip() for item in value.split(",") if item.strip())
    if not parsed:
        raise argparse.ArgumentTypeError("at least one day is required")
    if len(parsed) != len(set(parsed)):
        raise argparse.ArgumentTypeError("days must be unique")
    return parsed


def parse_args() -> argparse.Namespace:
    default_source = (
        REPOSITORY_ROOT
        / "Imitation-Learning"
        / "Top-ladder-data"
        / "sanitized"
    )
    artifacts = ENGINE_ROOT / "artifacts"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitized-root", type=Path, default=default_source)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--days", type=_days, default=DEFAULT_DAYS)
    parser.add_argument(
        "--validation-fraction",
        type=float,
        default=DEFAULT_VALIDATION_FRACTION,
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--target-shard-rows",
        type=int,
        default=DEFAULT_TARGET_SHARD_ROWS,
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, min(16, (os.cpu_count() or 4) - 2)),
    )
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=None,
        help="Developer smoke limit only; always recorded in the manifest.",
    )
    parser.add_argument("--tables", type=Path, default=artifacts / "frozen_tables.pt")
    parser.add_argument(
        "--artifact-manifest",
        type=Path,
        default=artifacts / "installed-manifest.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if (
        args.max_episodes is not None
        and args.output_root.resolve() == DEFAULT_CACHE_ROOT.resolve()
    ):
        raise SystemExit(
            "--max-episodes is developer-only and requires a non-default output root"
        )
    manifest = build_cache(
        sanitized_root=args.sanitized_root,
        output_root=args.output_root,
        days=args.days,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
        target_shard_rows=args.target_shard_rows,
        workers=args.workers,
        max_episodes=args.max_episodes,
        tables_path=args.tables,
        artifact_manifest_path=args.artifact_manifest,
    )
    print(
        json.dumps(
            {
                "dataset_root": str(args.output_root.resolve()),
                "examples": manifest["totals"]["examples"],
                "games": manifest["totals"]["games"],
                "single": manifest["totals"]["single"],
                "multi": manifest["totals"]["multi"],
                "shards": len(manifest["shards"]),
                "elapsed_seconds": manifest["build"]["elapsed_seconds"],
                "examples_per_second": manifest["build"]["examples_per_second"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
