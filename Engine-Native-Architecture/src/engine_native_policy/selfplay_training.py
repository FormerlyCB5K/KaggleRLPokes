"""Replay-window training for AlphaZero self-play shards."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from .flat import FLAT_DIM, decode_batch
from .mcts import SearchConfig
from .model import EngineNativeNet, ModelConfig
from .selfplay import SELFPLAY_SCHEMA, sha256_file
from .spec import MAX_OPTIONS
from .tables import FrozenTables


@dataclass(frozen=True)
class SelfPlayTrainingConfig:
    replay_root: Path
    output_dir: Path
    initial_checkpoint: Path
    tables_path: Path
    replay_window_games: int = 500_000
    validation_fraction: float = 0.10
    epochs: int = 1
    batch_size: int = 256
    num_workers: int = 4
    learning_rate: float = 1e-3
    l2_weight: float = 1e-4
    gradient_clip: float = 1.0
    seed: int = 20260730
    device: str = "auto"

    def validate(self) -> None:
        if self.replay_window_games < 2:
            raise ValueError("replay_window_games must be at least 2")
        if not 0 < self.validation_fraction < 1:
            raise ValueError("validation_fraction must be in (0, 1)")
        if self.epochs < 1 or self.batch_size < 1:
            raise ValueError("epochs and batch_size must be positive")
        if self.num_workers < 0:
            raise ValueError("num_workers must be nonnegative")
        if not math.isfinite(self.learning_rate) or self.learning_rate <= 0:
            raise ValueError("learning_rate must be finite and positive")
        if not math.isfinite(self.l2_weight) or self.l2_weight < 0:
            raise ValueError("l2_weight must be finite and nonnegative")
        if not math.isfinite(self.gradient_clip) or self.gradient_clip < 0:
            raise ValueError("gradient_clip must be finite and nonnegative")
        if self.device not in ("auto", "cpu", "cuda"):
            raise ValueError("device must be auto, cpu, or cuda")


def _split_games(
    games: list[dict[str, Any]],
    validation_fraction: float,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(games) < 2:
        raise RuntimeError("self-play training requires at least two games")
    ordered = sorted(
        games,
        key=lambda item: hashlib.sha256(
            f"{seed}:{int(item['game'])}".encode()
        ).hexdigest(),
    )
    validation_count = min(
        len(games) - 1,
        max(1, round(len(games) * validation_fraction)),
    )
    validation_ids = {
        int(item["game"]) for item in ordered[:validation_count]
    }
    train = [
        item for item in games if int(item["game"]) not in validation_ids
    ]
    validation = [
        item for item in games if int(item["game"]) in validation_ids
    ]
    return train, validation


def _validate_shard(payload: Mapping[str, torch.Tensor], rows: int) -> None:
    shapes = {
        "features": (rows, FLAT_DIM),
        "visit_target": (rows, MAX_OPTIONS),
        "policy_target_valid": (rows,),
        "value_target": (rows,),
        "player": (rows,),
        "root_value": (rows,),
        "simulations": (rows,),
        "search_seconds": (rows,),
        "max_depth_reached": (rows,),
    }
    for name, shape in shapes.items():
        value = payload.get(name)
        if not isinstance(value, torch.Tensor) or tuple(value.shape) != shape:
            raise RuntimeError(
                f"invalid self-play shard field {name}: "
                f"expected {shape}, got {getattr(value, 'shape', None)}"
            )
    targets = payload["visit_target"]
    valid = payload["policy_target_valid"]
    if bool(valid.any()):
        sums = targets[valid].sum(dim=1)
        if not torch.allclose(sums, torch.ones_like(sums), atol=1e-5):
            raise RuntimeError("valid root-visit targets must sum to one")
    if bool((targets[~valid] != 0).any()):
        raise RuntimeError("omitted policy targets must be all zero")
    values = payload["value_target"]
    if not bool(torch.isin(values, torch.tensor([-1.0, 0.0, 1.0])).all()):
        raise RuntimeError("self-play value targets must be -1, 0, or 1")


class SelfPlayDataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(
        self,
        root: str | Path,
        games: list[dict[str, Any]],
        *,
        verify_hashes: bool = True,
        max_open_shards: int = 2,
    ) -> None:
        self.root = Path(root)
        self.games = games
        self.verify_hashes = verify_hashes
        self.max_open_shards = max_open_shards
        self.offsets = [0]
        for game in games:
            self.offsets.append(
                self.offsets[-1] + int(game["examples"])
            )
        self._cache: OrderedDict[int, Mapping[str, torch.Tensor]] = (
            OrderedDict()
        )
        self._verified: set[int] = set()

    def __len__(self) -> int:
        return self.offsets[-1]

    def _locate(self, index: int) -> tuple[int, int]:
        if index < 0:
            index += len(self)
        if not 0 <= index < len(self):
            raise IndexError(index)
        import bisect

        shard = bisect.bisect_right(self.offsets, index) - 1
        return shard, index - self.offsets[shard]

    def _load(self, shard: int) -> Mapping[str, torch.Tensor]:
        if shard in self._cache:
            payload = self._cache.pop(shard)
            self._cache[shard] = payload
            return payload
        metadata = self.games[shard]
        path = self.root / metadata["shard"]
        if not path.is_file() or path.stat().st_size != int(metadata["bytes"]):
            raise RuntimeError(f"missing or size-mismatched shard: {path}")
        if self.verify_hashes and shard not in self._verified:
            if sha256_file(path) != metadata["sha256"]:
                raise RuntimeError(f"self-play shard hash mismatch: {path}")
            self._verified.add(shard)
        payload = torch.load(
            path, map_location="cpu", weights_only=True, mmap=True
        )
        _validate_shard(payload, int(metadata["examples"]))
        self._cache[shard] = payload
        while len(self._cache) > self.max_open_shards:
            self._cache.popitem(last=False)
        return payload

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        shard, row = self._locate(index)
        return {
            name: value[row] for name, value in self._load(shard).items()
        }


def alpha_zero_loss(
    model: nn.Module,
    output: Any,
    batch: Mapping[str, torch.Tensor],
    *,
    l2_weight: float,
) -> tuple[torch.Tensor, dict[str, torch.Tensor | int]]:
    valid = batch["policy_target_valid"].to(torch.bool)
    if bool(valid.any()):
        log_policy = torch.log_softmax(output.logits[valid].float(), dim=1)
        policy_per_row = -(
            batch["visit_target"][valid].float() * log_policy
        ).sum(dim=1)
        policy_loss = policy_per_row.mean()
        policy_sum = policy_per_row.sum()
        policy_count = int(valid.sum())
    else:
        policy_loss = output.value.sum() * 0
        policy_sum = policy_loss.detach()
        policy_count = 0
    value_error = (
        output.value.float() - batch["value_target"].float()
    ).square()
    value_loss = value_error.mean()
    l2 = torch.zeros((), device=output.value.device)
    if l2_weight:
        l2 = l2_weight * sum(
            parameter.float().square().sum()
            for parameter in model.parameters()
        )
    return policy_loss + value_loss + l2, {
        "policy_sum": policy_sum.detach(),
        "policy_count": policy_count,
        "value_sum": value_error.sum().detach(),
        "value_count": value_error.numel(),
        "l2": l2.detach(),
    }


def _checkpoint_parts(
    path: Path,
) -> tuple[Mapping[str, torch.Tensor], ModelConfig, SearchConfig]:
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, Mapping):
        raise RuntimeError("initial checkpoint must be an object")
    state = payload.get("state_dict", payload.get("model_state_dict"))
    if not isinstance(state, Mapping):
        raise RuntimeError("initial checkpoint has no state dict")
    raw_model = payload.get("model_config")
    raw_search = payload.get("search_config")
    if not isinstance(raw_model, Mapping):
        raise RuntimeError("initial checkpoint has no model_config")
    if not isinstance(raw_search, Mapping):
        raise RuntimeError("initial checkpoint has no search_config")
    model_config = ModelConfig(**dict(raw_model))
    search_config = SearchConfig(**dict(raw_search))
    if model_config.value_activation != "tanh":
        raise RuntimeError("self-play training requires tanh value activation")
    if not search_config.enabled:
        raise RuntimeError("self-play training requires search-enabled metadata")
    return state, model_config, search_config


def _device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return torch.device(requested)


def _metrics(
    totals: Mapping[str, float | int],
) -> dict[str, float | int]:
    policy_count = int(totals["policy_count"])
    value_count = int(totals["value_count"])
    policy = (
        float(totals["policy_sum"]) / policy_count
        if policy_count
        else 0.0
    )
    value = float(totals["value_sum"]) / value_count
    return {
        "loss_without_l2": policy + value,
        "policy_cross_entropy": policy,
        "value_mse": value,
        "policy_examples": policy_count,
        "value_examples": value_count,
    }


def _run_epoch(
    model: EngineNativeNet,
    loader: DataLoader,
    *,
    device: torch.device,
    l2_weight: float,
    optimizer: torch.optim.Optimizer | None,
    gradient_clip: float,
) -> dict[str, float | int]:
    training = optimizer is not None
    model.train(training)
    totals: dict[str, float | int] = {
        "policy_sum": 0.0,
        "policy_count": 0,
        "value_sum": 0.0,
        "value_count": 0,
        "l2_sum": 0.0,
        "batches": 0,
    }
    context = torch.enable_grad if training else torch.no_grad
    with context():
        for batch in loader:
            device_batch = {
                name: value.to(device, non_blocking=device.type == "cuda")
                for name, value in batch.items()
            }
            decoded = decode_batch(device_batch["features"])
            if training:
                optimizer.zero_grad(set_to_none=True)
            output = model(decoded)
            loss, parts = alpha_zero_loss(
                model, output, device_batch, l2_weight=l2_weight
            )
            if training:
                loss.backward()
                if gradient_clip:
                    torch.nn.utils.clip_grad_norm_(
                        model.parameters(), gradient_clip
                    )
                optimizer.step()
            totals["policy_sum"] += float(parts["policy_sum"].cpu())
            totals["policy_count"] += int(parts["policy_count"])
            totals["value_sum"] += float(parts["value_sum"].cpu())
            totals["value_count"] += int(parts["value_count"])
            totals["l2_sum"] += float(parts["l2"].cpu())
            totals["batches"] += 1
    result = _metrics(totals)
    l2 = float(totals["l2_sum"]) / max(1, int(totals["batches"]))
    result["l2_penalty"] = l2
    result["loss"] = float(result["loss_without_l2"]) + l2
    return result


def train_selfplay(config: SelfPlayTrainingConfig) -> dict[str, Any]:
    config.validate()
    random.seed(config.seed)
    np.random.seed(config.seed % (2**32))
    torch.manual_seed(config.seed)
    device = _device(config.device)
    manifest = json.loads(
        (config.replay_root / "manifest.json").read_text(encoding="utf-8")
    )
    if manifest.get("schema") != SELFPLAY_SCHEMA:
        raise RuntimeError("unsupported self-play replay schema")
    games = list(manifest["games"])[-config.replay_window_games :]
    train_games, validation_games = _split_games(
        games, config.validation_fraction, config.seed
    )
    train_dataset = SelfPlayDataset(config.replay_root, train_games)
    validation_dataset = SelfPlayDataset(
        config.replay_root, validation_games
    )
    if not len(train_dataset) or not len(validation_dataset):
        raise RuntimeError("self-play train and validation splits must be nonempty")
    generator = torch.Generator().manual_seed(config.seed)
    train_loader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=config.num_workers,
        generator=generator,
        pin_memory=device.type == "cuda",
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        num_workers=config.num_workers,
        pin_memory=device.type == "cuda",
    )
    state, model_config, search_config = _checkpoint_parts(
        config.initial_checkpoint
    )
    tables = FrozenTables.load(config.tables_path)
    model = EngineNativeNet(model_config, tables).to(device)
    model.load_state_dict(state, strict=True)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=config.learning_rate
    )
    history: list[dict[str, Any]] = []
    for epoch in range(config.epochs):
        training = _run_epoch(
            model,
            train_loader,
            device=device,
            l2_weight=config.l2_weight,
            optimizer=optimizer,
            gradient_clip=config.gradient_clip,
        )
        validation = _run_epoch(
            model,
            validation_loader,
            device=device,
            l2_weight=config.l2_weight,
            optimizer=None,
            gradient_clip=0,
        )
        history.append(
            {
                "epoch": epoch,
                "training": training,
                "validation": validation,
            }
        )
        print(
            f"[self-play epoch {epoch + 1}/{config.epochs}] "
            f"train_policy={training['policy_cross_entropy']:.6f} "
            f"train_value={training['value_mse']:.6f} "
            f"validation_policy={validation['policy_cross_entropy']:.6f} "
            f"validation_value={validation['value_mse']:.6f}",
            flush=True,
        )
    output = config.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "checkpoint_version": 3,
        "training_stage": "alpha_zero_selfplay",
        "state_dict": {
            name: value.detach().cpu()
            for name, value in model.state_dict().items()
        },
        "model_config": asdict(model_config),
        "search_config": search_config.as_dict(),
        "source_checkpoint_sha256": sha256_file(
            config.initial_checkpoint
        ),
        "replay_manifest_sha256": sha256_file(
            config.replay_root / "manifest.json"
        ),
        "replay_window": {
            "games": [int(item["game"]) for item in games],
            "train_games": [int(item["game"]) for item in train_games],
            "validation_games": [
                int(item["game"]) for item in validation_games
            ],
        },
        "history": history,
    }
    temporary = output / f".checkpoint.latest.pt.{uuid.uuid4().hex}.tmp"
    torch.save(checkpoint, temporary)
    os.replace(temporary, output / "checkpoint.latest.pt")
    summary = {
        "schema_version": "engine-native-selfplay-training-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            **asdict(config),
            "replay_root": str(config.replay_root.resolve()),
            "output_dir": str(output),
            "initial_checkpoint": str(config.initial_checkpoint.resolve()),
            "tables_path": str(config.tables_path.resolve()),
        },
        "network": {
            "model_config": asdict(model_config),
            "parameter_count": model.parameter_count(),
        },
        "tree_search": search_config.as_dict(),
        "checkpoint_update": {
            "policy": "latest_network",
            "promotion_gate": False,
        },
        "reward_shaping": {
            "enabled": False,
            "value_target": "terminal_outcome",
            "policy_target": "root_visit_distribution",
            "policy_loss_weight": 1.0,
            "value_loss_weight": 1.0,
            "l2_weight": config.l2_weight,
        },
        "replay_window": checkpoint["replay_window"],
        "training": history[-1]["training"],
        "validation": history[-1]["validation"],
        "history": history,
    }
    config_path = output / "config.json"
    temporary_json = output / f".config.json.{uuid.uuid4().hex}.tmp"
    temporary_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_json, config_path)
    return summary
