from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
from torch import nn

from engine_native_policy.flat import FIELD_OFFSETS, FLAT_DIM
from engine_native_policy.mcts import SearchConfig, SearchResult
from engine_native_policy.model import PolicyOutput
from engine_native_policy.model import EngineNativeNet, ModelConfig
from engine_native_policy.selfplay import (
    _policy_target,
    append_selfplay_game,
)
from engine_native_policy.selfplay_training import (
    SelfPlayDataset,
    SelfPlayTrainingConfig,
    _split_games,
    alpha_zero_loss,
    train_selfplay,
)
from engine_native_policy.tables import FrozenTables
from engine_native_policy.spec import MAX_OPTIONS


def _result() -> SearchResult:
    return SearchResult(
        action=(1,),
        actions=((0,), (1,), (2,)),
        visit_counts=(1, 3, 0),
        visit_policy=(0.25, 0.75, 0.0),
        root_value=0.2,
        simulations_completed=4,
        elapsed_seconds=0.01,
        max_depth_reached=2,
        immediate_terminal_win=False,
        stop_reason="simulation_limit",
    )


def _payload(rows: int = 2) -> dict[str, torch.Tensor]:
    target = torch.zeros(rows, MAX_OPTIONS)
    target[:, 0] = 1
    features = torch.zeros(rows, FLAT_DIM)
    mask_start, _ = FIELD_OFFSETS["opt_mask"]
    n_options_start, _ = FIELD_OFFSETS["n_options"]
    features[:, mask_start : mask_start + 2] = 1
    features[:, n_options_start] = 2
    return {
        "features": features,
        "visit_target": target,
        "policy_target_valid": torch.ones(rows, dtype=torch.bool),
        "value_target": torch.tensor([1.0, -1.0])[:rows],
        "player": torch.tensor([0, 1], dtype=torch.int8)[:rows],
        "root_value": torch.zeros(rows),
        "simulations": torch.full((rows,), 4, dtype=torch.int32),
        "search_seconds": torch.full((rows,), 0.01),
        "max_depth_reached": torch.full((rows,), 2, dtype=torch.int16),
    }


def test_root_visits_become_policy_target_for_single_selection() -> None:
    target, valid = _policy_target(_result(), n_options=3, max_count=1)
    assert valid
    assert target[:3].tolist() == pytest.approx([0.25, 0.75, 0.0])
    assert float(target.sum()) == pytest.approx(1.0)


def test_multi_and_forced_choices_are_value_only() -> None:
    multi, multi_valid = _policy_target(
        _result(), n_options=3, max_count=2
    )
    forced, forced_valid = _policy_target(
        SearchResult(
            **{
                **_result().__dict__,
                "actions": ((0,),),
                "visit_counts": (4,),
                "visit_policy": (1.0,),
            }
        ),
        n_options=1,
        max_count=1,
    )
    assert not multi_valid and not forced_valid
    assert not np.any(multi) and not np.any(forced)


def test_replay_manifest_and_dataset_round_trip(tmp_path: Path) -> None:
    config = SearchConfig(enabled=True, simulations=4)
    game = append_selfplay_game(
        tmp_path,
        _payload(),
        {
            "game": 1,
            "result": 0,
            "actions": 2,
            "examples": 2,
            "policy_examples": 2,
            "elapsed_seconds": 0.1,
            "checkpoint_sha256": "a" * 64,
        },
        search_config=config,
        checkpoint=tmp_path / "latest.pt",
    )
    manifest = json.loads(
        (tmp_path / "manifest.json").read_text(encoding="utf-8")
    )
    assert game.game == 1
    assert manifest["checkpoint_policy"] == "latest_network_pinned_per_game"
    assert manifest["promotion_gate"] is False
    assert manifest["totals"] == {
        "games": 1,
        "examples": 2,
        "policy_examples": 2,
    }
    dataset = SelfPlayDataset(tmp_path, manifest["games"])
    assert len(dataset) == 2
    assert dataset[0]["value_target"].item() == 1.0


def test_game_split_is_disjoint_and_deterministic() -> None:
    games = [{"game": value} for value in range(1, 11)]
    first = _split_games(games, 0.2, 7)
    second = _split_games(games, 0.2, 7)
    assert first == second
    assert len(first[0]) == 8
    assert len(first[1]) == 2
    assert {
        item["game"] for item in first[0]
    }.isdisjoint(item["game"] for item in first[1])


class _DummyModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.zeros(()))


def test_alpha_zero_loss_uses_equal_policy_and_value_weights() -> None:
    logits = torch.zeros(2, MAX_OPTIONS, requires_grad=True)
    value = torch.tensor([0.0, 0.5], requires_grad=True)
    output = PolicyOutput(
        logits=logits,
        incl=torch.zeros_like(logits),
        value=value,
        value_fog=value,
    )
    target = torch.zeros(2, MAX_OPTIONS)
    target[0, 0] = 1
    batch = {
        "visit_target": target,
        "policy_target_valid": torch.tensor([True, False]),
        "value_target": torch.tensor([1.0, -1.0]),
    }
    loss, parts = alpha_zero_loss(
        _DummyModel(), output, batch, l2_weight=0
    )
    expected_policy = torch.log(torch.tensor(float(MAX_OPTIONS)))
    expected_value = torch.tensor((1.0 + 2.25) / 2)
    assert loss.item() == pytest.approx(
        (expected_policy + expected_value).item()
    )
    assert parts["policy_count"] == 1
    assert parts["value_count"] == 2
    loss.backward()
    assert torch.all(logits.grad[1] == 0)
    assert value.grad is not None and bool((value.grad != 0).all())


def test_selfplay_training_writes_latest_checkpoint_and_metrics(
    tmp_path: Path,
) -> None:
    project = Path(__file__).resolve().parents[1]
    tables_path = project / "artifacts" / "frozen_tables.pt"
    tables = FrozenTables.load(tables_path)
    initial = tmp_path / "initial.pt"
    model_config = ModelConfig(value_activation="tanh")
    search_config = SearchConfig(enabled=True, simulations=4)
    torch.save(
        {
            "state_dict": EngineNativeNet(
                model_config, tables
            ).state_dict(),
            "model_config": model_config.__dict__,
            "search_config": search_config.as_dict(),
        },
        initial,
    )
    replay = tmp_path / "replay"
    for game_index, result in ((1, 0), (2, 1)):
        append_selfplay_game(
            replay,
            _payload(1),
            {
                "game": game_index,
                "result": result,
                "actions": 1,
                "examples": 1,
                "policy_examples": 1,
                "elapsed_seconds": 0.1,
                "checkpoint_sha256": "a" * 64,
            },
            search_config=search_config,
            checkpoint=initial,
        )
    output = tmp_path / "training"
    summary = train_selfplay(
        SelfPlayTrainingConfig(
            replay_root=replay,
            output_dir=output,
            initial_checkpoint=initial,
            tables_path=tables_path,
            replay_window_games=2,
            validation_fraction=0.5,
            epochs=1,
            batch_size=1,
            num_workers=0,
            learning_rate=1e-5,
            device="cpu",
        )
    )
    assert (output / "checkpoint.latest.pt").is_file()
    assert (output / "config.json").is_file()
    assert summary["checkpoint_update"]["promotion_gate"] is False
    assert summary["training"]["policy_examples"] == 1
    assert summary["validation"]["value_examples"] == 1
