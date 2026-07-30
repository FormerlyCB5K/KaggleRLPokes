from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import torch

from engine_native_policy import (
    EngineNativeNet,
    FrozenTables,
    ModelConfig,
    SearchConfig,
)


PROJECT = Path(__file__).resolve().parents[1]
BUILDER_PATH = PROJECT / "scripts" / "build_checkpoint_agent.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "test_build_checkpoint_agent", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_state_dict_accepts_trainer_checkpoint_shapes() -> None:
    builder = _load_builder()
    state = {"weight": torch.ones(2)}

    assert builder.extract_state_dict({"state_dict": state}) == (state, "state_dict")
    assert builder.extract_state_dict({"model_state_dict": state}) == (
        state,
        "model_state_dict",
    )
    assert builder.extract_state_dict(state) == (state, "bare_state_dict")
    assert builder.extract_model_config({"state_dict": state}) == ModelConfig()
    assert builder.extract_search_config({"state_dict": state}) == SearchConfig(
        enabled=False
    )


def test_build_agent_emits_strict_serving_bundle(tmp_path: Path) -> None:
    builder = _load_builder()
    tables_path = PROJECT / "artifacts" / "frozen_tables.pt"
    tables = FrozenTables.load(tables_path)
    network = EngineNativeNet(tables=tables)

    checkpoint = tmp_path / "checkpoint.best.pt"
    torch.save({"state_dict": network.state_dict()}, checkpoint)
    deck_path = tmp_path / "deck.csv"
    deck_path.write_text("".join(f"{card_id}\n" for card_id in range(1, 61)))
    output = tmp_path / "generated-agent"

    manifest = builder.build_agent(
        checkpoint=checkpoint,
        deck_path=deck_path,
        output_dir=output,
        tables_path=tables_path,
        agent_name="fixture-agent",
    )

    assert manifest["schema_version"] == "engine-native-agent-v1"
    assert manifest["source_checkpoint"]["state_field"] == "state_dict"
    assert manifest["model"]["parameter_count"] == 2_370_259
    assert manifest["model"]["config"]["value_activation"] == "identity"
    assert manifest["model"]["search"]["enabled"] is False
    assert (output / "main.py").is_file()
    assert (output / "deck.csv").is_file()
    assert (output / "model.pt").is_file()
    assert (output / "frozen_tables.pt").is_file()
    assert (output / "agent-manifest.json").is_file()
    assert (output / "engine_native_policy" / "policy.py").is_file()
    assert (output / "engine_native_policy" / "mcts.py").is_file()
    assert (output / "engine_native_policy" / "engine_search.py").is_file()

    serving = torch.load(output / "model.pt", map_location="cpu", weights_only=True)
    reloaded = EngineNativeNet(
        config=ModelConfig(**serving["model_config"]), tables=tables
    )
    reloaded.load_state_dict(serving["state_dict"], strict=True)
    assert serving["search_config"]["enabled"] is False


def test_build_agent_preserves_tanh_value_activation(tmp_path: Path) -> None:
    builder = _load_builder()
    tables_path = PROJECT / "artifacts" / "frozen_tables.pt"
    tables = FrozenTables.load(tables_path)
    config = ModelConfig(value_activation="tanh")
    network = EngineNativeNet(config=config, tables=tables)
    checkpoint = tmp_path / "checkpoint.best.pt"
    torch.save(
        {
            "state_dict": network.state_dict(),
            "model_config": vars(config),
        },
        checkpoint,
    )
    deck_path = tmp_path / "deck.csv"
    deck_path.write_text("".join(f"{card_id}\n" for card_id in range(1, 61)))
    output = tmp_path / "generated-agent"

    manifest = builder.build_agent(
        checkpoint=checkpoint,
        deck_path=deck_path,
        output_dir=output,
        tables_path=tables_path,
    )

    assert manifest["model"]["config"]["value_activation"] == "tanh"
    serving = torch.load(output / "model.pt", map_location="cpu", weights_only=True)
    assert serving["model_config"]["value_activation"] == "tanh"


def test_build_agent_rejects_search_with_unbounded_value(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    tables_path = PROJECT / "artifacts" / "frozen_tables.pt"
    tables = FrozenTables.load(tables_path)
    network = EngineNativeNet(tables=tables)
    checkpoint = tmp_path / "checkpoint.best.pt"
    torch.save({"state_dict": network.state_dict()}, checkpoint)
    deck_path = tmp_path / "deck.csv"
    deck_path.write_text("".join(f"{card_id}\n" for card_id in range(1, 61)))
    with pytest.raises(RuntimeError, match="tanh-bounded"):
        builder.build_agent(
            checkpoint=checkpoint,
            deck_path=deck_path,
            output_dir=tmp_path / "generated-agent",
            tables_path=tables_path,
            search_config=SearchConfig(enabled=True),
        )


def test_build_agent_preserves_checkpoint_search_config(tmp_path: Path) -> None:
    builder = _load_builder()
    tables_path = PROJECT / "artifacts" / "frozen_tables.pt"
    tables = FrozenTables.load(tables_path)
    model_config = ModelConfig(value_activation="tanh")
    search_config = SearchConfig(
        enabled=True,
        simulations=17,
        max_depth=5,
        c_puct=2.0,
        per_decision_seconds=0.25,
    )
    network = EngineNativeNet(config=model_config, tables=tables)
    checkpoint = tmp_path / "checkpoint.best.pt"
    torch.save(
        {
            "state_dict": network.state_dict(),
            "model_config": vars(model_config),
            "search_config": search_config.as_dict(),
        },
        checkpoint,
    )
    deck_path = tmp_path / "deck.csv"
    deck_path.write_text("".join(f"{card_id}\n" for card_id in range(1, 61)))
    output = tmp_path / "generated-agent"

    manifest = builder.build_agent(
        checkpoint=checkpoint,
        deck_path=deck_path,
        output_dir=output,
        tables_path=tables_path,
    )

    assert manifest["model"]["search"] == search_config.as_dict()
    serving = torch.load(output / "model.pt", map_location="cpu", weights_only=True)
    assert serving["search_config"] == search_config.as_dict()
