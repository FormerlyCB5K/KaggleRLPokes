"""AlphaZero self-play game generation and replay-buffer shards."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import torch
from cg_download import game as default_game
from cg_download.api import to_observation_class

from .flat import FLAT_DIM, encode
from .mcts import SearchConfig, SearchResult
from .model import EngineNativeNet, ModelConfig
from .policy import EngineNativePolicy
from .spec import MAX_OPTIONS
from .tables import FrozenTables


SELFPLAY_SCHEMA = "engine-native-selfplay-v1"


class GameAPI(Protocol):
    def battle_start(
        self, deck0: list[int], deck1: list[int]
    ) -> tuple[dict, Any]: ...

    def battle_select(self, selection: list[int]) -> dict: ...

    def battle_finish(self) -> None: ...


@dataclass(frozen=True)
class SelfPlayGame:
    game: int
    result: int
    actions: int
    examples: int
    policy_examples: int
    elapsed_seconds: float
    checkpoint_sha256: str
    shard: str


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _torch_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    torch.save(value, temporary)
    os.replace(temporary, path)


def _state_dict(payload: Any) -> Mapping[str, torch.Tensor]:
    if isinstance(payload, Mapping):
        for name in ("state_dict", "model_state_dict"):
            state = payload.get(name)
            if isinstance(state, Mapping):
                return state
        if payload and all(
            isinstance(name, str) and isinstance(value, torch.Tensor)
            for name, value in payload.items()
        ):
            return payload
    raise RuntimeError("checkpoint does not contain a model state dict")


def load_selfplay_network(
    checkpoint: str | Path,
    tables: FrozenTables,
    *,
    device: str | torch.device,
) -> tuple[EngineNativeNet, str]:
    """Load one immutable network snapshot for a complete self-play game."""

    checkpoint = Path(checkpoint).resolve()
    checkpoint_hash = sha256_file(checkpoint)
    payload = torch.load(
        checkpoint, map_location="cpu", weights_only=True
    )
    if sha256_file(checkpoint) != checkpoint_hash:
        raise RuntimeError(
            "latest checkpoint changed while a game snapshot was loading"
        )
    raw_config = (
        payload.get("model_config")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(raw_config, Mapping):
        raise RuntimeError(
            "self-play checkpoint must record its tanh model_config"
        )
    model_config = ModelConfig(**dict(raw_config))
    if model_config.value_activation != "tanh":
        raise RuntimeError("self-play requires a tanh-bounded value checkpoint")
    network = EngineNativeNet(config=model_config, tables=tables)
    network.load_state_dict(_state_dict(payload), strict=True)
    return network.to(device).eval(), checkpoint_hash


def _policy_target(
    result: SearchResult,
    *,
    n_options: int,
    max_count: int,
) -> tuple[np.ndarray, bool]:
    target = np.zeros(MAX_OPTIONS, dtype=np.float32)
    valid = max_count <= 1 and n_options > 1
    if valid:
        for action, probability in zip(
            result.actions, result.visit_policy
        ):
            if len(action) != 1 or not 0 <= action[0] < n_options:
                valid = False
                break
            target[action[0]] = float(probability)
    if not valid or not np.isclose(float(target.sum()), 1.0):
        target.fill(0)
        valid = False
    return target, valid


def play_selfplay_game(
    *,
    game_index: int,
    checkpoint: str | Path,
    deck: Sequence[int],
    tables: FrozenTables,
    search_config: SearchConfig,
    device: str | torch.device = "cpu",
    max_actions: int = 20_000,
    game_api: GameAPI = default_game,
) -> tuple[dict[str, torch.Tensor], dict[str, Any]]:
    """Play one latest-network mirror game and return completed targets."""

    if len(deck) != 60:
        raise ValueError("self-play deck must contain exactly 60 cards")
    if not search_config.enabled:
        raise ValueError("self-play requires tree search to be enabled")
    if max_actions < 1:
        raise ValueError("max_actions must be positive")
    search_config.validate()
    started_at = time.perf_counter()
    network, checkpoint_hash = load_selfplay_network(
        checkpoint, tables, device=device
    )
    policy_configs = (
        replace(
            search_config,
            seed=search_config.seed + 2 * int(game_index),
        ),
        replace(
            search_config,
            seed=search_config.seed + 2 * int(game_index) + 1,
        ),
    )
    policies = (
        EngineNativePolicy(
            network,
            deck,
            device=device,
            search_config=policy_configs[0],
        ),
        EngineNativePolicy(
            network,
            deck,
            device=device,
            search_config=policy_configs[1],
        ),
    )
    features: list[np.ndarray] = []
    visit_targets: list[np.ndarray] = []
    policy_valid: list[bool] = []
    players: list[int] = []
    root_values: list[float] = []
    simulations: list[int] = []
    search_seconds: list[float] = []
    depths: list[int] = []
    observation: dict | None = None
    started = False
    try:
        observation, start_data = game_api.battle_start(
            list(deck), list(deck)
        )
        started = bool(getattr(start_data, "battlePtr", 1))
        error_player = int(getattr(start_data, "errorPlayer", -1))
        if error_player >= 0:
            raise RuntimeError(
                f"engine rejected self-play deck for side {error_player}"
            )
        if observation is None:
            raise RuntimeError("engine returned no initial self-play observation")

        actions = 0
        while True:
            current = observation.get("current") or {}
            result = int(current.get("result", -1))
            if result >= 0:
                break
            if actions >= max_actions:
                raise RuntimeError(
                    f"self-play game exceeded max_actions={max_actions}"
                )
            player = int(current.get("yourIndex", -1))
            if player not in (0, 1):
                raise RuntimeError(f"invalid acting player {player}")
            typed = to_observation_class(observation)
            if typed.select is None:
                raise RuntimeError("self-play received an unexpected deck prompt")
            frame, _ = policies[player].infer(typed)
            search = policies[player].search(typed, training=True)
            target, target_valid = _policy_target(
                search,
                n_options=frame.n_options,
                max_count=int(typed.select.maxCount),
            )
            features.append(encode(frame))
            visit_targets.append(target)
            policy_valid.append(target_valid)
            players.append(player)
            root_values.append(search.root_value)
            simulations.append(search.simulations_completed)
            search_seconds.append(search.elapsed_seconds)
            depths.append(search.max_depth_reached)
            observation = game_api.battle_select(list(search.action))
            actions += 1

        if result not in (0, 1, 2):
            raise RuntimeError(f"engine returned unknown terminal result={result}")
    finally:
        if started:
            game_api.battle_finish()

    value_targets = np.asarray(
        [
            0.0 if result == 2 else (1.0 if player == result else -1.0)
            for player in players
        ],
        dtype=np.float32,
    )
    payload = {
        "features": torch.from_numpy(
            np.stack(features)
            if features
            else np.empty((0, FLAT_DIM), dtype=np.float32)
        ),
        "visit_target": torch.from_numpy(
            np.stack(visit_targets)
            if visit_targets
            else np.empty((0, MAX_OPTIONS), dtype=np.float32)
        ),
        "policy_target_valid": torch.tensor(
            policy_valid, dtype=torch.bool
        ),
        "value_target": torch.from_numpy(value_targets),
        "player": torch.tensor(players, dtype=torch.int8),
        "root_value": torch.tensor(root_values, dtype=torch.float32),
        "simulations": torch.tensor(simulations, dtype=torch.int32),
        "search_seconds": torch.tensor(
            search_seconds, dtype=torch.float32
        ),
        "max_depth_reached": torch.tensor(depths, dtype=torch.int16),
    }
    summary = {
        "game": int(game_index),
        "result": int(result),
        "actions": int(actions),
        "examples": len(features),
        "policy_examples": int(sum(policy_valid)),
        "elapsed_seconds": time.perf_counter() - started_at,
        "checkpoint_sha256": checkpoint_hash,
    }
    return payload, summary


def append_selfplay_game(
    root: str | Path,
    payload: Mapping[str, torch.Tensor],
    summary: Mapping[str, Any],
    *,
    search_config: SearchConfig,
    checkpoint: str | Path,
) -> SelfPlayGame:
    """Atomically append one game shard and refresh its replay manifest."""

    root = Path(root).resolve()
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") != SELFPLAY_SCHEMA:
            raise RuntimeError("self-play manifest schema mismatch")
        if manifest.get("search_config") != search_config.as_dict():
            raise RuntimeError("self-play search configuration changed")
    else:
        manifest = {
            "schema": SELFPLAY_SCHEMA,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "updated_utc": None,
            "checkpoint_policy": "latest_network_pinned_per_game",
            "promotion_gate": False,
            "search_config": search_config.as_dict(),
            "games": [],
            "totals": {
                "games": 0,
                "examples": 0,
                "policy_examples": 0,
            },
        }
    game_index = int(summary["game"])
    if any(int(item["game"]) == game_index for item in manifest["games"]):
        raise RuntimeError(f"self-play game {game_index} already exists")
    relative = f"games/game-{game_index:08d}.pt"
    shard_path = root / relative
    _torch_atomic(shard_path, dict(payload))
    game = SelfPlayGame(
        **{
            **dict(summary),
            "elapsed_seconds": round(
                float(summary["elapsed_seconds"]), 6
            ),
            "shard": relative,
        }
    )
    record = {
        **asdict(game),
        "bytes": shard_path.stat().st_size,
        "sha256": sha256_file(shard_path),
        "checkpoint": str(Path(checkpoint).resolve()),
    }
    manifest["games"].append(record)
    manifest["games"].sort(key=lambda item: int(item["game"]))
    manifest["totals"] = {
        "games": len(manifest["games"]),
        "examples": sum(int(item["examples"]) for item in manifest["games"]),
        "policy_examples": sum(
            int(item["policy_examples"]) for item in manifest["games"]
        ),
    }
    manifest["updated_utc"] = datetime.now(timezone.utc).isoformat()
    _json_atomic(manifest_path, manifest)
    return game
