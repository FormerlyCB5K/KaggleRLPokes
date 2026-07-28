#!/usr/bin/env python
"""Train the engine-native policy from an immutable tensor cache."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve()
ENGINE_ROOT = SCRIPT.parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parent
sys.path.insert(0, str(ENGINE_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT))

from engine_native_policy.il.trainer import (  # noqa: E402
    TIME_LIMIT_EXIT_CODE,
    TrainingConfig,
    run_training,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "Imitation-Learning"
            / "Top-ladder-data"
            / "engine-native-cache-test-six-days"
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=(
            REPOSITORY_ROOT
            / "Imitation-Learning"
            / "engine-native-training"
            / "test-six-days"
            / "seed-20260728"
        ),
    )
    parser.add_argument(
        "--tables",
        type=Path,
        default=ENGINE_ROOT / "artifacts" / "frozen_tables.pt",
    )
    parser.add_argument(
        "--initial-checkpoint",
        type=Path,
        default=None,
        help="Optional compatible warm-start checkpoint; omitted for the clean baseline.",
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda"), default="auto"
    )
    parser.add_argument(
        "--precision",
        choices=("auto", "fp32", "fp16", "bf16"),
        default="auto",
        help="auto selects bf16 on supported CUDA devices, otherwise fp16.",
    )
    parser.add_argument("--gradient-clip", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260728)
    parser.add_argument("--early-stopping-patience", type=int, default=2)
    parser.add_argument("--early-stopping-min-delta", type=float, default=1e-4)
    parser.add_argument("--checkpoint-every-steps", type=int, default=1000)
    parser.add_argument("--log-every-steps", type=int, default=100)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume checkpoint.latest.pt when it exists; otherwise start fresh.",
    )
    parser.add_argument(
        "--skip-cache-hash-verification",
        action="store_true",
        help=(
            "Skip re-hashing shard bytes. Structural/cache-identity checks still run; "
            "use only after the acceptance smoke verified every hash."
        ),
    )
    parser.add_argument(
        "--max-runtime-minutes",
        type=float,
        default=None,
        help="Stop safely with exit code 75 after this many minutes so SLURM can resume.",
    )
    parser.add_argument(
        "--max-optimizer-steps",
        type=int,
        default=None,
        help="Developer/test limit for this invocation; the resume checkpoint remains valid.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = TrainingConfig(
        dataset_root=args.dataset_root,
        output_dir=args.out_dir,
        tables_path=args.tables,
        initial_checkpoint=args.initial_checkpoint,
        epochs=args.epochs,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        learning_rate=args.learning_rate,
        device=args.device,
        precision=args.precision,
        gradient_clip=args.gradient_clip,
        seed=args.seed,
        early_stopping_patience=args.early_stopping_patience,
        early_stopping_min_delta=args.early_stopping_min_delta,
        checkpoint_every_steps=args.checkpoint_every_steps,
        log_every_steps=args.log_every_steps,
        verify_cache_hashes=not args.skip_cache_hash_verification,
        resume=args.resume,
        max_runtime_seconds=(
            args.max_runtime_minutes * 60.0
            if args.max_runtime_minutes is not None
            else None
        ),
        max_optimizer_steps=args.max_optimizer_steps,
    )
    result = run_training(config)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return (
        TIME_LIMIT_EXIT_CODE
        if result["status"] == "needs_resume"
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
