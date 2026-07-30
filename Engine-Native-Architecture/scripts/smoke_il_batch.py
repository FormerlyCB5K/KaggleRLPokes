#!/usr/bin/env python
"""Verify cached batches with one real-model forward/backward optimizer step."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch


SCRIPT = Path(__file__).resolve()
ENGINE_ROOT = SCRIPT.parents[1]
REPOSITORY_ROOT = ENGINE_ROOT.parent
sys.path.insert(0, str(ENGINE_ROOT / "src"))
sys.path.insert(0, str(REPOSITORY_ROOT))

from engine_native_policy import (  # noqa: E402
    EngineNativeNet,
    FrozenTables,
    ModelConfig,
    decode_batch,
)
from engine_native_policy.il.cache import DEFAULT_SEED, verify_cache  # noqa: E402
from engine_native_policy.il.dataset import make_dataloader  # noqa: E402
from engine_native_policy.il.losses import batch_metrics, supervised_loss  # noqa: E402


def parse_args() -> argparse.Namespace:
    default_dataset = (
        REPOSITORY_ROOT
        / "Imitation-Learning"
        / "Top-ladder-data"
        / "engine-native-cache-test-six-days"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=default_dataset)
    parser.add_argument(
        "--tables",
        type=Path,
        default=ENGINE_ROOT / "artifacts" / "frozen_tables.pt",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Optional compatible checkpoint to initialize before the smoke step.",
    )
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda"), default="auto"
    )
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument(
        "--skip-full-hash-verification",
        action="store_true",
        help="Developer-only shortcut; the cluster acceptance smoke must not use it.",
    )
    return parser.parse_args()


def _device(name: str) -> torch.device:
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda requested but CUDA is unavailable")
    return torch.device(name)


def _to_device(
    tensors: dict[str, torch.Tensor], device: torch.device
) -> dict[str, torch.Tensor]:
    return {
        name: value.to(device, non_blocking=device.type == "cuda")
        for name, value in tensors.items()
    }


def main() -> int:
    args = parse_args()
    device = _device(args.device)
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
    manifest = verify_cache(
        args.dataset_root,
        verify_hashes=not args.skip_full_hash_verification,
    )
    train_loader, train_sampler = make_dataloader(
        args.dataset_root,
        "train",
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        seed=args.seed,
        device=device,
        verify_hashes=False,
    )
    validation_loader, validation_sampler = make_dataloader(
        args.dataset_root,
        "validation",
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        seed=args.seed,
        device=device,
        verify_hashes=False,
    )

    train_sampler.set_epoch(0)
    first_indices = next(iter(train_sampler))
    train_sampler.set_epoch(0)
    if first_indices != next(iter(train_sampler)):
        raise RuntimeError("seeded training sampler is not deterministic")
    if list(iter(validation_sampler)) != list(iter(validation_sampler)):
        raise RuntimeError("validation sampler is not deterministic")

    tables = FrozenTables.load(args.tables)
    network = EngineNativeNet(
        config=ModelConfig(value_activation="tanh"),
        tables=tables,
    ).to(device)
    if args.checkpoint is not None:
        checkpoint = torch.load(
            args.checkpoint, map_location="cpu", weights_only=True
        )
        state = checkpoint.get("state_dict", checkpoint)
        network.load_state_dict(state, strict=True)
    optimizer = torch.optim.Adam(network.parameters(), lr=args.learning_rate)

    train_batch = _to_device(next(iter(train_loader)), device)
    decoded = _to_device(decode_batch(train_batch["features"]), device)
    if not torch.equal(
        decoded["opt_mask"].sum(dim=1),
        train_batch["n_options"].to(torch.int64),
    ):
        raise RuntimeError("train option-mask counts disagree with cache")
    network.train()
    optimizer.zero_grad(set_to_none=True)
    train_output = network(decoded)
    train_loss = supervised_loss(
        train_output, train_batch, decoded["opt_mask"]
    )
    if not bool(torch.isfinite(train_loss.loss)):
        raise RuntimeError("training smoke loss is not finite")
    train_loss.loss.backward()
    gradients = [
        parameter.grad
        for parameter in network.parameters()
        if parameter.grad is not None
    ]
    if not gradients or not all(
        bool(torch.isfinite(gradient).all()) for gradient in gradients
    ):
        raise RuntimeError("training smoke produced missing or non-finite gradients")
    optimizer.step()

    validation_batch = _to_device(next(iter(validation_loader)), device)
    validation_decoded = _to_device(
        decode_batch(validation_batch["features"]), device
    )
    if not torch.equal(
        validation_decoded["opt_mask"].sum(dim=1),
        validation_batch["n_options"].to(torch.int64),
    ):
        raise RuntimeError("validation option-mask counts disagree with cache")
    network.eval()
    with torch.inference_mode():
        validation_output = network(validation_decoded)
        validation_loss = supervised_loss(
            validation_output,
            validation_batch,
            validation_decoded["opt_mask"],
        )
        metrics = batch_metrics(
            validation_output, validation_batch, validation_decoded
        )

    print(
        json.dumps(
            {
                "dataset_examples": manifest["totals"]["examples"],
                "device": str(device),
                "train_batch": int(train_batch["features"].shape[0]),
                "train_loss": float(train_loss.loss.detach().cpu()),
                "validation_batch": int(
                    validation_batch["features"].shape[0]
                ),
                "validation_loss": float(
                    validation_loss.loss.detach().cpu()
                ),
                "finite_gradient_tensors": len(gradients),
                "validation_metrics": metrics,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
