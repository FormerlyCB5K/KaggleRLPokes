#!/usr/bin/env python3
"""Train the latest policy/value checkpoint from an MCTS replay window."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence


ARCHITECTURE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ARCHITECTURE_ROOT.parent
SOURCE_ROOT = ARCHITECTURE_ROOT / "src"
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))

from engine_native_policy.selfplay_training import (  # noqa: E402
    SelfPlayTrainingConfig,
    train_selfplay,
)


DEFAULT_TABLES = ARCHITECTURE_ROOT / "artifacts" / "frozen_tables.pt"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-root", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--initial-checkpoint", type=Path, required=True)
    parser.add_argument("--tables", type=Path, default=DEFAULT_TABLES)
    parser.add_argument("--replay-window-games", type=int, default=500_000)
    parser.add_argument("--validation-fraction", type=float, default=0.10)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--l2-weight", type=float, default=1e-4)
    parser.add_argument("--gradient-clip", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260730)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda"), default="auto"
    )
    args = parser.parse_args(argv)
    try:
        SelfPlayTrainingConfig(
            replay_root=args.replay_root,
            output_dir=args.out_dir,
            initial_checkpoint=args.initial_checkpoint,
            tables_path=args.tables,
            replay_window_games=args.replay_window_games,
            validation_fraction=args.validation_fraction,
            epochs=args.epochs,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
            learning_rate=args.learning_rate,
            l2_weight=args.l2_weight,
            gradient_clip=args.gradient_clip,
            seed=args.seed,
            device=args.device,
        ).validate()
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = train_selfplay(
        SelfPlayTrainingConfig(
            replay_root=args.replay_root,
            output_dir=args.out_dir,
            initial_checkpoint=args.initial_checkpoint,
            tables_path=args.tables,
            replay_window_games=args.replay_window_games,
            validation_fraction=args.validation_fraction,
            epochs=args.epochs,
            batch_size=args.batch_size,
            num_workers=args.num_workers,
            learning_rate=args.learning_rate,
            l2_weight=args.l2_weight,
            gradient_clip=args.gradient_clip,
            seed=args.seed,
            device=args.device,
        )
    )
    print(f"Latest checkpoint: {(args.out_dir / 'checkpoint.latest.pt').resolve()}")
    print(
        "Validation: "
        f"policy={summary['validation']['policy_cross_entropy']:.6f}, "
        f"value={summary['validation']['value_mse']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
