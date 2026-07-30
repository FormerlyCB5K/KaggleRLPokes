"""Folder-agent entry point for a bundled engine-native policy checkpoint."""

from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _wire_engine_imports() -> None:
    """Support both the local ``cg_download`` and Kaggle ``cg`` package names."""
    try:
        import cg_download.api  # noqa: F401
        return
    except ModuleNotFoundError:
        pass

    import cg
    import cg.api
    import cg.game
    import cg.sim
    import cg.utils

    sys.modules.setdefault("cg_download", cg)
    sys.modules.setdefault("cg_download.api", cg.api)
    sys.modules.setdefault("cg_download.game", cg.game)
    sys.modules.setdefault("cg_download.sim", cg.sim)
    sys.modules.setdefault("cg_download.utils", cg.utils)


_wire_engine_imports()

import torch
from cg_download.api import to_observation_class

from engine_native_policy import (
    EngineNativeNet,
    EngineNativePolicy,
    FrozenTables,
    ModelConfig,
)


def _read_deck() -> list[int]:
    deck = [
        int(line.strip())
        for line in (ROOT / "deck.csv").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(deck) != 60:
        raise RuntimeError(f"deck.csv must contain 60 cards, found {len(deck)}")
    return deck


MY_DECK = _read_deck()
_POLICY: EngineNativePolicy | None = None


def _device() -> torch.device:
    requested = os.environ.get("ENGINE_NATIVE_DEVICE", "cpu").strip().lower()
    if requested == "auto":
        requested = "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "ENGINE_NATIVE_DEVICE=cuda was requested but CUDA is unavailable"
        )
    if requested not in {"cpu", "cuda"}:
        raise RuntimeError(
            "ENGINE_NATIVE_DEVICE must be one of: cpu, cuda, auto"
        )
    return torch.device(requested)


def _load_policy() -> EngineNativePolicy:
    tables = FrozenTables.load(ROOT / "frozen_tables.pt")
    payload = torch.load(ROOT / "model.pt", map_location="cpu", weights_only=True)
    if payload.get("format") != "engine-native-agent-v1":
        raise RuntimeError("model.pt is not an engine-native-agent-v1 payload")
    network = EngineNativeNet(
        config=ModelConfig(**payload.get("model_config", {})),
        tables=tables,
    )
    network.load_state_dict(payload["state_dict"], strict=True)
    return EngineNativePolicy(network, MY_DECK, device=_device())


def agent(obs_dict: dict) -> list[int]:
    """Return the deck initially, then choose among the engine's legal options."""
    global _POLICY
    observation = to_observation_class(obs_dict)
    if observation.select is None:
        _POLICY = None
        return list(MY_DECK)
    if _POLICY is None:
        _POLICY = _load_policy()
    return _POLICY.choose(observation)
