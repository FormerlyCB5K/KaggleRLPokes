"""Resumable behavior cloning for the engine-native cached dataset."""

from __future__ import annotations

import contextlib
import json
import math
import os
import random
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn

from ..flat import decode_batch
from ..model import EngineNativeNet, ModelConfig
from ..mcts import SearchConfig
from ..spec import OptionKind
from ..tables import FrozenTables
from .cache import sha256_file, verify_cache
from .dataset import make_dataloader
from .losses import LossBreakdown, batch_metrics, supervised_loss


CHECKPOINT_VERSION = 2
TIME_LIMIT_EXIT_CODE = 75


@dataclass(frozen=True)
class TrainingConfig:
    dataset_root: Path
    output_dir: Path
    tables_path: Path
    initial_checkpoint: Path | None = None
    epochs: int = 3
    batch_size: int = 256
    num_workers: int = 4
    learning_rate: float = 1e-3
    value_loss_weight: float = 0.01
    model_config: ModelConfig = field(
        default_factory=lambda: ModelConfig(value_activation="tanh")
    )
    search_config: SearchConfig = field(
        default_factory=lambda: SearchConfig(enabled=False)
    )
    device: str = "auto"
    precision: str = "auto"
    gradient_clip: float = 1.0
    seed: int = 20260728
    early_stopping_patience: int = 2
    early_stopping_min_delta: float = 1e-4
    checkpoint_every_steps: int = 1000
    log_every_steps: int = 100
    verify_cache_hashes: bool = True
    resume: bool = False
    max_runtime_seconds: float | None = None
    max_optimizer_steps: int | None = None

    def validate(self) -> None:
        if self.epochs < 1:
            raise ValueError("epochs must be positive")
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.num_workers < 0:
            raise ValueError("num_workers must be nonnegative")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")
        if (
            not math.isfinite(self.value_loss_weight)
            or self.value_loss_weight < 0
        ):
            raise ValueError("value_loss_weight must be finite and nonnegative")
        self.model_config.validate()
        if self.model_config.value_activation != "tanh":
            raise ValueError(
                "imitation terminal-outcome training requires tanh value activation"
            )
        self.search_config.validate()
        if self.gradient_clip < 0:
            raise ValueError("gradient_clip must be nonnegative")
        if self.early_stopping_patience < 0:
            raise ValueError("early_stopping_patience must be nonnegative")
        if self.early_stopping_min_delta < 0:
            raise ValueError("early_stopping_min_delta must be nonnegative")
        if self.checkpoint_every_steps < 1:
            raise ValueError("checkpoint_every_steps must be positive")
        if self.log_every_steps < 1:
            raise ValueError("log_every_steps must be positive")
        if self.max_runtime_seconds is not None and self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive when set")
        if self.max_optimizer_steps is not None and self.max_optimizer_steps <= 0:
            raise ValueError("max_optimizer_steps must be positive when set")


def resolve_device(requested: str) -> torch.device:
    if requested not in ("auto", "cpu", "cuda"):
        raise ValueError("device must be auto, cpu, or cuda")
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return torch.device(requested)


def resolve_precision(
    requested: str, device: torch.device
) -> tuple[str, torch.dtype | None]:
    if requested not in ("auto", "fp32", "fp16", "bf16"):
        raise ValueError("precision must be auto, fp32, fp16, or bf16")
    if device.type != "cuda":
        if requested in ("fp16", "bf16"):
            raise ValueError(f"{requested} training requires CUDA")
        return "fp32", None
    if requested == "auto":
        requested = (
            "bf16"
            if torch.cuda.is_bf16_supported()
            else "fp16"
        )
    if requested == "bf16" and not torch.cuda.is_bf16_supported():
        raise RuntimeError("bf16 was requested but the CUDA device does not support it")
    dtype = {
        "fp32": None,
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
    }[requested]
    return requested, dtype


def _autocast(device: torch.device, dtype: torch.dtype | None):
    if dtype is None:
        return contextlib.nullcontext()
    return torch.autocast(device_type=device.type, dtype=dtype)


def _make_scaler(enabled: bool):
    if hasattr(torch, "amp") and hasattr(torch.amp, "GradScaler"):
        try:
            return torch.amp.GradScaler("cuda", enabled=enabled)
        except TypeError:
            return torch.amp.GradScaler(enabled=enabled)
    return torch.cuda.amp.GradScaler(enabled=enabled)


def _json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _torch_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    torch.save(value, temporary)
    os.replace(temporary, path)


def _to_device(
    tensors: Mapping[str, torch.Tensor], device: torch.device
) -> dict[str, torch.Tensor]:
    return {
        name: value.to(device, non_blocking=device.type == "cuda")
        for name, value in tensors.items()
    }


def _fresh_loss_totals() -> dict[str, float | int]:
    return {
        "single_loss_sum": 0.0,
        "multi_loss_sum": 0.0,
        "value_loss_sum": 0.0,
        "single_count": 0,
        "multi_count": 0,
        "value_only_count": 0,
        "value_count": 0,
        "batches": 0,
        "elapsed_seconds": 0.0,
        "peak_cuda_memory_bytes": 0,
    }


def _add_loss(
    totals: dict[str, float | int], breakdown: LossBreakdown
) -> None:
    totals["single_loss_sum"] += float(
        breakdown.single_loss_sum.detach().float().cpu()
    )
    totals["multi_loss_sum"] += float(
        breakdown.multi_loss_sum.detach().float().cpu()
    )
    totals["value_loss_sum"] += float(
        breakdown.value_loss_sum.detach().float().cpu()
    )
    totals["single_count"] += breakdown.single_count
    totals["multi_count"] += breakdown.multi_count
    totals["value_only_count"] += breakdown.value_only_count
    totals["value_count"] += breakdown.value_count
    totals["batches"] += 1


def _loss_summary(
    totals: Mapping[str, float | int], *, value_loss_weight: float
) -> dict[str, float | int]:
    single_count = int(totals["single_count"])
    multi_count = int(totals["multi_count"])
    policy_count = single_count + multi_count
    value_only_count = int(totals["value_only_count"])
    single_sum = float(totals["single_loss_sum"])
    multi_sum = float(totals["multi_loss_sum"])
    value_sum = float(totals["value_loss_sum"])
    value_count = int(totals["value_count"])
    elapsed = float(totals["elapsed_seconds"])
    policy_nll = (
        (single_sum + multi_sum) / policy_count if policy_count else 0.0
    )
    value_mse = value_sum / value_count if value_count else 0.0
    return {
        "examples": value_count,
        "policy_count": policy_count,
        "batches": int(totals["batches"]),
        "loss": policy_nll + value_loss_weight * value_mse,
        "nll": policy_nll,
        "policy_nll": policy_nll,
        "value_mse": value_mse,
        "value_loss_weight": value_loss_weight,
        "single_nll": single_sum / single_count if single_count else 0.0,
        "multi_nll": multi_sum / multi_count if multi_count else 0.0,
        "single_count": single_count,
        "multi_count": multi_count,
        "value_only_count": value_only_count,
        "value_count": value_count,
        "elapsed_seconds": elapsed,
        "examples_per_second": value_count / elapsed if elapsed else 0.0,
        "peak_cuda_memory_bytes": int(totals["peak_cuda_memory_bytes"]),
    }


def _fresh_validation_totals() -> dict[str, Any]:
    return {
        **_fresh_loss_totals(),
        "single_top1_correct": 0,
        "single_top3_correct": 0,
        "single_top3_count": 0,
        "multi_exact_correct": 0,
        "multi_selected_count_correct": 0,
        "multi_cardinality_valid": 0,
        "multi_true_positive": 0,
        "multi_false_positive": 0,
        "multi_false_negative": 0,
        "value_mae_sum": 0.0,
        "value_prediction_sum": 0.0,
        "value_target_sum": 0.0,
        "value_decisive_count": 0,
        "value_sign_correct": 0,
        "single_by_option_type": {},
    }


def _add_validation_metrics(
    totals: dict[str, Any], metrics: Mapping[str, Any]
) -> None:
    for name in (
        "single_count",
        "multi_count",
        "value_only_count",
        "single_nll_sum",
        "multi_nll_sum",
        "single_top1_correct",
        "single_top3_correct",
        "single_top3_count",
        "multi_exact_correct",
        "multi_selected_count_correct",
        "multi_cardinality_valid",
        "multi_true_positive",
        "multi_false_positive",
        "multi_false_negative",
        "value_count",
        "value_mse_sum",
        "value_mae_sum",
        "value_prediction_sum",
        "value_target_sum",
        "value_decisive_count",
        "value_sign_correct",
    ):
        destination = {
            "single_nll_sum": "single_loss_sum",
            "multi_nll_sum": "multi_loss_sum",
            "value_mse_sum": "value_loss_sum",
        }.get(name, name)
        totals[destination] += metrics[name]
    totals["batches"] += 1
    by_type = totals["single_by_option_type"]
    for option_type, values in metrics["single_by_option_type"].items():
        target = by_type.setdefault(option_type, {"count": 0, "correct": 0})
        target["count"] += values["count"]
        target["correct"] += values["correct"]


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _validation_summary(
    totals: Mapping[str, Any], *, value_loss_weight: float
) -> dict[str, Any]:
    summary = _loss_summary(
        totals, value_loss_weight=value_loss_weight
    )
    single_count = int(totals["single_count"])
    multi_count = int(totals["multi_count"])
    true_positive = int(totals["multi_true_positive"])
    false_positive = int(totals["multi_false_positive"])
    false_negative = int(totals["multi_false_negative"])
    precision = _safe_ratio(true_positive, true_positive + false_positive)
    recall = _safe_ratio(true_positive, true_positive + false_negative)
    by_type: dict[str, Any] = {}
    for raw_type, values in sorted(
        totals["single_by_option_type"].items(), key=lambda item: int(item[0])
    ):
        option_id = int(raw_type)
        try:
            option_name = OptionKind(option_id).name
        except ValueError:
            option_name = f"UNKNOWN_{option_id}"
        by_type[option_name] = {
            "id": option_id,
            "count": int(values["count"]),
            "accuracy": _safe_ratio(values["correct"], values["count"]),
        }
    summary.update(
        {
            "single_top1_accuracy": _safe_ratio(
                totals["single_top1_correct"], single_count
            ),
            "single_top3_accuracy": _safe_ratio(
                totals["single_top3_correct"], totals["single_top3_count"]
            ),
            "single_top3_count": int(totals["single_top3_count"]),
            "multi_exact_set_accuracy": _safe_ratio(
                totals["multi_exact_correct"], multi_count
            ),
            "multi_selected_count_accuracy": _safe_ratio(
                totals["multi_selected_count_correct"], multi_count
            ),
            "multi_cardinality_valid_rate": _safe_ratio(
                totals["multi_cardinality_valid"], multi_count
            ),
            "multi_precision": precision,
            "multi_recall": recall,
            "multi_f1": (
                2.0 * precision * recall / (precision + recall)
                if precision + recall
                else 0.0
            ),
            "single_by_option_type": by_type,
            "value_mae": _safe_ratio(
                totals["value_mae_sum"], totals["value_count"]
            ),
            "value_sign_accuracy": _safe_ratio(
                totals["value_sign_correct"],
                totals["value_decisive_count"],
            ),
            "value_decisive_count": int(
                totals["value_decisive_count"]
            ),
            "value_prediction_mean": _safe_ratio(
                totals["value_prediction_sum"], totals["value_count"]
            ),
            "value_target_mean": _safe_ratio(
                totals["value_target_sum"], totals["value_count"]
            ),
        }
    )
    return summary


@torch.inference_mode()
def evaluate(
    model: nn.Module,
    loader,
    *,
    device: torch.device,
    autocast_dtype: torch.dtype | None,
    value_loss_weight: float,
) -> dict[str, Any]:
    was_training = model.training
    model.eval()
    totals = _fresh_validation_totals()
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    started = time.perf_counter()
    for batch in loader:
        device_batch = _to_device(batch, device)
        decoded = decode_batch(device_batch["features"])
        if not torch.equal(
            decoded["opt_mask"].sum(dim=1),
            device_batch["n_options"].to(torch.int64),
        ):
            raise RuntimeError("validation option-mask counts disagree with cache")
        with _autocast(device, autocast_dtype):
            output = model(decoded)
            metrics = batch_metrics(
                output,
                device_batch,
                decoded,
                value_loss_weight=value_loss_weight,
            )
        _add_validation_metrics(totals, metrics)
    totals["elapsed_seconds"] = time.perf_counter() - started
    if device.type == "cuda":
        totals["peak_cuda_memory_bytes"] = torch.cuda.max_memory_allocated(device)
    if was_training:
        model.train()
    return _validation_summary(
        totals, value_loss_weight=value_loss_weight
    )


def _capture_rng() -> dict[str, Any]:
    state: dict[str, Any] = {
        "python": random.getstate(),
        "numpy": np.random.get_state(),
        "torch": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        state["cuda"] = torch.cuda.get_rng_state_all()
    return state


def _restore_rng(state: Mapping[str, Any], device: torch.device) -> None:
    random.setstate(state["python"])
    np.random.set_state(state["numpy"])
    torch.set_rng_state(state["torch"].cpu())
    if device.type == "cuda" and "cuda" in state:
        torch.cuda.set_rng_state_all([item.cpu() for item in state["cuda"]])


def _checkpoint_payload(
    *,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    scaler: Any,
    signature: Mapping[str, Any],
    epoch: int,
    next_batch: int,
    global_step: int,
    epoch_totals: Mapping[str, Any],
    baseline: Mapping[str, Any],
    best_validation_loss: float,
    best_validation_nll: float,
    epochs_without_improvement: int,
    history: list[dict[str, Any]],
    finished: bool,
) -> dict[str, Any]:
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "signature": dict(signature),
        "model_state_dict": model.state_dict(),
        "model_config": (
            asdict(model.config)
            if isinstance(model, EngineNativeNet)
            else None
        ),
        "search_config": dict(signature["search_config"]),
        "optimizer_state_dict": optimizer.state_dict(),
        "scaler_state_dict": scaler.state_dict(),
        "epoch": epoch,
        "next_batch": next_batch,
        "global_step": global_step,
        "epoch_totals": dict(epoch_totals),
        "baseline": dict(baseline),
        "best_validation_loss": best_validation_loss,
        "best_validation_nll": best_validation_nll,
        "epochs_without_improvement": epochs_without_improvement,
        "history": history,
        "finished": finished,
        "rng": _capture_rng(),
    }


def _best_payload(
    *,
    model: nn.Module,
    signature: Mapping[str, Any],
    epoch: int,
    global_step: int,
    validation: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "signature": dict(signature),
        "state_dict": model.state_dict(),
        "model_config": (
            asdict(model.config)
            if isinstance(model, EngineNativeNet)
            else None
        ),
        "search_config": dict(signature["search_config"]),
        "epoch": epoch,
        "global_step": global_step,
        "validation": dict(validation),
    }


def _signature(
    config: TrainingConfig,
    *,
    manifest_hash: str,
    tables_hash: str,
    initial_checkpoint_hash: str | None,
    resolved_precision: str,
) -> dict[str, Any]:
    return {
        "cache_manifest_sha256": manifest_hash,
        "tables_sha256": tables_hash,
        "initial_checkpoint_sha256": initial_checkpoint_hash,
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "learning_rate": config.learning_rate,
        "value_loss_weight": config.value_loss_weight,
        "value_activation": config.model_config.value_activation,
        "model_config": asdict(config.model_config),
        "search_config": config.search_config.as_dict(),
        "precision": resolved_precision,
        "gradient_clip": config.gradient_clip,
        "seed": config.seed,
        "early_stopping_patience": config.early_stopping_patience,
        "early_stopping_min_delta": config.early_stopping_min_delta,
    }


def _load_initial_checkpoint(model: nn.Module, path: Path) -> None:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    state = payload.get("state_dict", payload)
    model.load_state_dict(state, strict=True)


def run_training(
    config: TrainingConfig,
    *,
    model_factory: Callable[[FrozenTables], nn.Module] | None = None,
) -> dict[str, Any]:
    """Run or resume training and return a small terminal-status dictionary."""

    config.validate()
    invocation_started = time.perf_counter()
    deadline = (
        invocation_started + config.max_runtime_seconds
        if config.max_runtime_seconds is not None
        else None
    )
    device = resolve_device(config.device)
    resolved_precision, autocast_dtype = resolve_precision(
        config.precision, device
    )
    if device.type == "cuda":
        torch.set_float32_matmul_precision("high")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    random.seed(config.seed)
    np.random.seed(config.seed % (2**32))
    torch.manual_seed(config.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(config.seed)

    dataset_root = config.dataset_root.resolve()
    output_dir = config.output_dir.resolve()
    tables_path = config.tables_path.resolve()
    initial_checkpoint = (
        config.initial_checkpoint.resolve()
        if config.initial_checkpoint is not None
        else None
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    latest_path = output_dir / "checkpoint.latest.pt"
    best_path = output_dir / "checkpoint.best.pt"
    config_path = output_dir / "config.json"
    history_path = output_dir / "history.json"
    summary_path = output_dir / "training-summary.json"

    manifest = verify_cache(
        dataset_root, verify_hashes=config.verify_cache_hashes
    )
    manifest_hash = sha256_file(dataset_root / "manifest.json")
    tables_hash = sha256_file(tables_path)
    initial_checkpoint_hash = (
        sha256_file(initial_checkpoint)
        if initial_checkpoint is not None
        else None
    )
    signature = _signature(
        config,
        manifest_hash=manifest_hash,
        tables_hash=tables_hash,
        initial_checkpoint_hash=initial_checkpoint_hash,
        resolved_precision=resolved_precision,
    )

    tables = FrozenTables.load(tables_path)
    model = (
        model_factory(tables)
        if model_factory is not None
        else EngineNativeNet(
            config=config.model_config,
            tables=tables,
        )
    ).to(device)
    if initial_checkpoint is not None:
        _load_initial_checkpoint(model, initial_checkpoint)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    scaler = _make_scaler(
        enabled=device.type == "cuda" and resolved_precision == "fp16"
    )

    train_loader, train_sampler = make_dataloader(
        dataset_root,
        "train",
        batch_size=config.batch_size,
        num_workers=config.num_workers,
        seed=config.seed,
        device=device,
        verify_hashes=False,
    )
    validation_loader, validation_sampler = make_dataloader(
        dataset_root,
        "validation",
        batch_size=config.batch_size,
        num_workers=config.num_workers,
        seed=config.seed,
        device=device,
        verify_hashes=False,
    )
    validation_sampler.set_epoch(0)

    epoch = 0
    next_batch = 0
    global_step = 0
    epoch_totals = _fresh_loss_totals()
    baseline: dict[str, Any] | None = None
    best_validation_loss = math.inf
    best_validation_nll = math.inf
    epochs_without_improvement = 0
    history: list[dict[str, Any]] = []
    finished = False

    if latest_path.is_file():
        if not config.resume:
            raise RuntimeError(
                f"{latest_path} already exists; pass resume=True or use a new output directory"
            )
        state = torch.load(latest_path, map_location=device, weights_only=False)
        if state.get("checkpoint_version") != CHECKPOINT_VERSION:
            raise RuntimeError("resume checkpoint version mismatch")
        if state.get("signature") != signature:
            raise RuntimeError(
                "resume checkpoint configuration or cache identity does not match"
            )
        model.load_state_dict(state["model_state_dict"], strict=True)
        optimizer.load_state_dict(state["optimizer_state_dict"])
        scaler.load_state_dict(state["scaler_state_dict"])
        epoch = int(state["epoch"])
        next_batch = int(state["next_batch"])
        global_step = int(state["global_step"])
        epoch_totals = dict(state["epoch_totals"])
        baseline = dict(state["baseline"])
        best_validation_loss = float(state["best_validation_loss"])
        best_validation_nll = float(state["best_validation_nll"])
        epochs_without_improvement = int(state["epochs_without_improvement"])
        history = list(state["history"])
        finished = bool(state["finished"])
        _restore_rng(state["rng"], device)
        print(
            f"Resumed epoch={epoch} next_batch={next_batch} "
            f"global_step={global_step} best_validation_loss="
            f"{best_validation_loss:.6f}",
            flush=True,
        )
    elif config.resume:
        print("No resume checkpoint found; starting a fresh run.", flush=True)

    run_config = {
        **{
            key: str(value) if isinstance(value, Path) else value
            for key, value in asdict(config).items()
        },
        "dataset_root": str(dataset_root),
        "output_dir": str(output_dir),
        "tables_path": str(tables_path),
        "initial_checkpoint": (
            str(initial_checkpoint) if initial_checkpoint is not None else None
        ),
        "resolved_device": str(device),
        "resolved_precision": resolved_precision,
        "cache": {
            "manifest_sha256": manifest_hash,
            "identity": manifest["identity"],
            "totals": manifest["totals"],
            "split": manifest["split"],
        },
        "model_parameters": sum(parameter.numel() for parameter in model.parameters()),
        "model_config": (
            asdict(model.config)
            if isinstance(model, EngineNativeNet)
            else None
        ),
        "search_config": config.search_config.as_dict(),
        "signature": signature,
    }
    if config_path.is_file():
        existing_config = json.loads(config_path.read_text(encoding="utf-8"))
        if existing_config.get("signature") != signature:
            raise RuntimeError("existing config.json does not match this run")
    else:
        run_config["created_utc"] = datetime.now(timezone.utc).isoformat()
        _json_atomic(config_path, run_config)

    if finished:
        return {
            "status": "finished",
            "epoch": epoch,
            "global_step": global_step,
            "best_validation_loss": best_validation_loss,
            "best_validation_nll": best_validation_nll,
            "output_dir": str(output_dir),
        }

    def save_latest(*, finished_value: bool, totals: Mapping[str, Any]) -> None:
        _torch_atomic(
            latest_path,
            _checkpoint_payload(
                model=model,
                optimizer=optimizer,
                scaler=scaler,
                signature=signature,
                epoch=epoch,
                next_batch=next_batch,
                global_step=global_step,
                epoch_totals=totals,
                baseline=baseline or {},
                best_validation_loss=best_validation_loss,
                best_validation_nll=best_validation_nll,
                epochs_without_improvement=epochs_without_improvement,
                history=history,
                finished=finished_value,
            ),
        )
        _json_atomic(history_path, history)

    if baseline is None:
        print(
            f"Evaluating baseline on {len(validation_loader.dataset)} examples...",
            flush=True,
        )
        baseline = evaluate(
            model,
            validation_loader,
            device=device,
            autocast_dtype=autocast_dtype,
            value_loss_weight=config.value_loss_weight,
        )
        history.append(
            {
                "kind": "baseline",
                "epoch": -1,
                "global_step": 0,
                "validation": baseline,
                "recorded_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        best_validation_loss = float(baseline["loss"])
        best_validation_nll = float(baseline["nll"])
        _torch_atomic(
            best_path,
            _best_payload(
                model=model,
                signature=signature,
                epoch=-1,
                global_step=0,
                validation=baseline,
            ),
        )
        save_latest(finished_value=False, totals=epoch_totals)
        print(
            f"[baseline] validation_loss={baseline['loss']:.6f} "
            f"policy_nll={baseline['nll']:.6f} "
            f"value_mse={baseline['value_mse']:.6f} "
            f"single_top1={baseline['single_top1_accuracy']:.4f} "
            f"multi_exact={baseline['multi_exact_set_accuracy']:.4f}",
            flush=True,
        )

    steps_this_invocation = 0
    stopped_reason: str | None = None
    while epoch < config.epochs:
        train_sampler.set_epoch(epoch)
        total_batches = train_sampler.total_batches
        train_sampler.set_start_batch(next_batch)
        if next_batch > total_batches:
            raise RuntimeError(
                f"resume batch {next_batch} exceeds epoch size {total_batches}"
            )
        model.train()
        if device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(device)
        starting_batch = next_batch
        segment_started = time.perf_counter()

        for relative_batch, batch in enumerate(train_loader):
            batch_index = starting_batch + relative_batch
            device_batch = _to_device(batch, device)
            decoded = decode_batch(device_batch["features"])
            if not torch.equal(
                decoded["opt_mask"].sum(dim=1),
                device_batch["n_options"].to(torch.int64),
            ):
                raise RuntimeError("training option-mask counts disagree with cache")

            optimizer.zero_grad(set_to_none=True)
            with _autocast(device, autocast_dtype):
                output = model(decoded)
                breakdown = supervised_loss(
                    output,
                    device_batch,
                    decoded["opt_mask"],
                    value_loss_weight=config.value_loss_weight,
                )
            if not bool(torch.isfinite(breakdown.loss)):
                raise RuntimeError("training loss became non-finite")
            scaler.scale(breakdown.loss).backward()
            if config.gradient_clip > 0:
                scaler.unscale_(optimizer)
                gradient_norm = torch.nn.utils.clip_grad_norm_(
                    model.parameters(), config.gradient_clip
                )
                if not bool(torch.isfinite(gradient_norm)):
                    raise RuntimeError("gradient norm became non-finite")
            scaler.step(optimizer)
            scaler.update()

            _add_loss(epoch_totals, breakdown)
            if device.type == "cuda":
                epoch_totals["peak_cuda_memory_bytes"] = max(
                    int(epoch_totals["peak_cuda_memory_bytes"]),
                    torch.cuda.max_memory_allocated(device),
                )
            global_step += 1
            steps_this_invocation += 1
            next_batch = batch_index + 1

            if global_step % config.log_every_steps == 0:
                elapsed = float(epoch_totals["elapsed_seconds"]) + (
                    time.perf_counter() - segment_started
                )
                progress_totals = dict(epoch_totals)
                progress_totals["elapsed_seconds"] = elapsed
                progress = _loss_summary(
                    progress_totals,
                    value_loss_weight=config.value_loss_weight,
                )
                print(
                    f"[epoch {epoch + 1}/{config.epochs} "
                    f"batch {next_batch}/{total_batches}] "
                    f"step={global_step} loss={progress['loss']:.6f} "
                    f"policy_nll={progress['nll']:.6f} "
                    f"value_mse={progress['value_mse']:.6f} "
                    f"throughput={progress['examples_per_second']:.1f} examples/s",
                    flush=True,
                )

            if global_step % config.checkpoint_every_steps == 0:
                checkpoint_totals = dict(epoch_totals)
                checkpoint_totals["elapsed_seconds"] = float(
                    checkpoint_totals["elapsed_seconds"]
                ) + (time.perf_counter() - segment_started)
                save_latest(finished_value=False, totals=checkpoint_totals)

            if (
                config.max_optimizer_steps is not None
                and steps_this_invocation >= config.max_optimizer_steps
            ):
                stopped_reason = "optimizer_step_limit"
            elif deadline is not None and time.perf_counter() >= deadline:
                stopped_reason = "runtime_limit"
            if stopped_reason is not None:
                epoch_totals["elapsed_seconds"] = float(
                    epoch_totals["elapsed_seconds"]
                ) + (time.perf_counter() - segment_started)
                save_latest(finished_value=False, totals=epoch_totals)
                print(
                    f"Stopping safely for {stopped_reason}; resume from "
                    f"epoch={epoch} batch={next_batch} step={global_step}.",
                    flush=True,
                )
                return {
                    "status": "needs_resume",
                    "reason": stopped_reason,
                    "epoch": epoch,
                    "next_batch": next_batch,
                    "global_step": global_step,
                    "best_validation_loss": best_validation_loss,
                    "best_validation_nll": best_validation_nll,
                    "output_dir": str(output_dir),
                }

        epoch_totals["elapsed_seconds"] = float(
            epoch_totals["elapsed_seconds"]
        ) + (time.perf_counter() - segment_started)
        if next_batch != total_batches:
            raise RuntimeError(
                f"epoch ended at batch {next_batch}, expected {total_batches}"
            )
        train_summary = _loss_summary(
            epoch_totals,
            value_loss_weight=config.value_loss_weight,
        )

        validation = evaluate(
            model,
            validation_loader,
            device=device,
            autocast_dtype=autocast_dtype,
            value_loss_weight=config.value_loss_weight,
        )
        improved = float(validation["loss"]) < (
            best_validation_loss - config.early_stopping_min_delta
        )
        if improved:
            best_validation_loss = float(validation["loss"])
            best_validation_nll = float(validation["nll"])
            epochs_without_improvement = 0
            _torch_atomic(
                best_path,
                _best_payload(
                    model=model,
                    signature=signature,
                    epoch=epoch,
                    global_step=global_step,
                    validation=validation,
                ),
            )
        else:
            epochs_without_improvement += 1

        history.append(
            {
                "kind": "epoch",
                "epoch": epoch,
                "global_step": global_step,
                "train": train_summary,
                "validation": validation,
                "improved": improved,
                "best_validation_loss": best_validation_loss,
                "best_validation_nll": best_validation_nll,
                "epochs_without_improvement": epochs_without_improvement,
                "recorded_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        print(
            f"[epoch {epoch + 1}/{config.epochs}] "
            f"train_loss={train_summary['loss']:.6f} "
            f"validation_loss={validation['loss']:.6f} "
            f"policy_nll={validation['nll']:.6f} "
            f"value_mse={validation['value_mse']:.6f} "
            f"single_top1={validation['single_top1_accuracy']:.4f} "
            f"multi_exact={validation['multi_exact_set_accuracy']:.4f} "
            f"best={best_validation_loss:.6f}",
            flush=True,
        )

        epoch += 1
        next_batch = 0
        epoch_totals = _fresh_loss_totals()
        early_stopped = (
            config.early_stopping_patience > 0
            and epochs_without_improvement >= config.early_stopping_patience
        )
        finished = epoch >= config.epochs or early_stopped
        save_latest(finished_value=finished, totals=epoch_totals)
        if finished:
            break

        if deadline is not None and time.perf_counter() >= deadline:
            return {
                "status": "needs_resume",
                "reason": "runtime_limit",
                "epoch": epoch,
                "next_batch": next_batch,
                "global_step": global_step,
                "best_validation_loss": best_validation_loss,
                "best_validation_nll": best_validation_nll,
                "output_dir": str(output_dir),
            }

    final_summary = {
        "status": "finished",
        "epochs_completed": epoch,
        "global_step": global_step,
        "best_validation_loss": best_validation_loss,
        "best_validation_nll": best_validation_nll,
        "early_stopped": (
            epoch < config.epochs
            and epochs_without_improvement >= config.early_stopping_patience
        ),
        "baseline": baseline,
        "last_epoch": history[-1] if history else None,
        "best_checkpoint": str(best_path),
        "latest_checkpoint": str(latest_path),
        "finished_utc": datetime.now(timezone.utc).isoformat(),
    }
    _json_atomic(summary_path, final_summary)
    return {
        **final_summary,
        "output_dir": str(output_dir),
    }
