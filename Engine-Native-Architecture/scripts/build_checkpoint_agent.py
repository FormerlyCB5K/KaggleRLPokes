"""Build a folder agent from an engine-native model checkpoint and deck CSV.

Example:

    python Engine-Native-Architecture/scripts/build_checkpoint_agent.py \
        --checkpoint checkpoint.best.pt \
        --deck Ceruledge-Agent/deck.csv \
        --output-dir Imitation-Learning/checkpoint-agents/my-agent

The checkpoint must be trusted: PyTorch checkpoint files can execute code while
being loaded. Both trainer formats (``state_dict`` in the best checkpoint and
``model_state_dict`` in the latest checkpoint) and a bare state dict are
accepted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


ARCHITECTURE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ARCHITECTURE_ROOT.parent
SOURCE_ROOT = ARCHITECTURE_ROOT / "src"
RUNTIME_MAIN = ARCHITECTURE_ROOT / "agent_runtime" / "main.py"
DEFAULT_TABLES = ARCHITECTURE_ROOT / "artifacts" / "frozen_tables.pt"
RUNTIME_MODULES = (
    "__init__.py",
    "actions.py",
    "features.py",
    "featurize.py",
    "flat.py",
    "engine_search.py",
    "mcts.py",
    "model.py",
    "policy.py",
    "spec.py",
    "tables.py",
    "vocab.py",
)

sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))

from engine_native_policy import (  # noqa: E402
    EngineNativeNet,
    FrozenTables,
    ModelConfig,
    SearchConfig,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_deck(path: Path) -> list[int]:
    try:
        deck = [
            int(line.strip())
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except ValueError as exc:
        raise RuntimeError(f"{path}: deck contains a non-integer line") from exc
    if len(deck) != 60:
        raise RuntimeError(f"{path}: expected 60 cards, found {len(deck)}")
    return deck


def _is_tensor_state_dict(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(isinstance(name, str) for name in value)
        and all(isinstance(tensor, torch.Tensor) for tensor in value.values())
    )


def extract_state_dict(payload: Any) -> tuple[Mapping[str, torch.Tensor], str]:
    """Return the model state and the checkpoint field it came from."""
    if isinstance(payload, Mapping):
        for key in ("state_dict", "model_state_dict"):
            value = payload.get(key)
            if _is_tensor_state_dict(value):
                return value, key
        if _is_tensor_state_dict(payload):
            return payload, "bare_state_dict"
    raise RuntimeError(
        "checkpoint contains neither state_dict nor model_state_dict "
        "and is not a bare tensor state dict"
    )


def extract_model_config(payload: Any) -> ModelConfig:
    """Recover model behavior metadata, defaulting old checkpoints to legacy parity."""

    if not isinstance(payload, Mapping) or payload.get("model_config") is None:
        return ModelConfig()
    raw = payload["model_config"]
    if not isinstance(raw, Mapping):
        raise RuntimeError("checkpoint model_config must be an object")
    try:
        return ModelConfig(**dict(raw))
    except TypeError as exc:
        raise RuntimeError(f"checkpoint model_config is invalid: {exc}") from exc


def extract_search_config(payload: Any) -> SearchConfig:
    """Recover search behavior, explicitly disabled for old/IL checkpoints."""

    if not isinstance(payload, Mapping) or payload.get("search_config") is None:
        return SearchConfig(enabled=False)
    raw = payload["search_config"]
    if not isinstance(raw, Mapping):
        raise RuntimeError("checkpoint search_config must be an object")
    try:
        config = SearchConfig(**dict(raw))
        config.validate()
        return config
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"checkpoint search_config is invalid: {exc}") from exc


def _cpu_state_dict(
    state: Mapping[str, torch.Tensor],
) -> dict[str, torch.Tensor]:
    return {
        name: tensor.detach().to(device="cpu").contiguous()
        for name, tensor in state.items()
    }


def _copy_runtime_package(destination: Path) -> list[str]:
    source_package = SOURCE_ROOT / "engine_native_policy"
    destination.mkdir(parents=True)
    copied: list[str] = []
    for filename in RUNTIME_MODULES:
        source = source_package / filename
        if not source.is_file():
            raise RuntimeError(f"required runtime source is missing: {source}")
        shutil.copy2(source, destination / filename)
        copied.append(filename)
    return copied


def _readme(agent_name: str) -> str:
    return f"""# {agent_name}

This folder is an engine-native checkpoint agent built by
`Engine-Native-Architecture/scripts/build_checkpoint_agent.py`.

Required runtime dependencies:

- Python 3.10 or newer;
- PyTorch;
- NumPy; and
- the competition engine exposed as either `cg_download` or `cg`.

Run it against another repository agent from the repository root:

```powershell
.venv\\Scripts\\python.exe evaluate_agents.py `
  "<this-agent-folder>" `
  sample-archaludon `
  100
```

CPU inference is the default. Set `ENGINE_NATIVE_DEVICE=auto` or
`ENGINE_NATIVE_DEVICE=cuda` to enable CUDA inference when available.
"""


def build_agent(
    *,
    checkpoint: Path,
    deck_path: Path,
    output_dir: Path,
    tables_path: Path = DEFAULT_TABLES,
    agent_name: str | None = None,
    search_config: SearchConfig | None = None,
) -> dict[str, Any]:
    checkpoint = checkpoint.expanduser().resolve()
    deck_path = deck_path.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    tables_path = tables_path.expanduser().resolve()

    for label, path in (
        ("checkpoint", checkpoint),
        ("deck", deck_path),
        ("frozen tables", tables_path),
        ("runtime main", RUNTIME_MAIN),
    ):
        if not path.is_file():
            raise RuntimeError(f"{label} file does not exist: {path}")
    if output_dir.exists():
        raise RuntimeError(
            f"output directory already exists; choose a new path: {output_dir}"
        )

    deck = _read_deck(deck_path)
    tables = FrozenTables.load(tables_path)
    if tables.provisional:
        raise RuntimeError("refusing to build a gameplay agent with provisional tables")

    # This intentionally loads only a trusted user/model checkpoint.
    payload = torch.load(checkpoint, map_location="cpu", weights_only=False)
    state, checkpoint_field = extract_state_dict(payload)
    model_config = extract_model_config(payload)
    resolved_search = search_config or extract_search_config(payload)
    resolved_search.validate()
    if resolved_search.enabled and model_config.value_activation != "tanh":
        raise RuntimeError(
            "tree-search agents require a tanh-bounded value checkpoint"
        )
    serving_state = _cpu_state_dict(state)

    network = EngineNativeNet(config=model_config, tables=tables)
    network.load_state_dict(serving_state, strict=True)
    parameter_count = network.parameter_count()

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = output_dir.parent / (
        f".{output_dir.name}.building-{uuid.uuid4().hex}"
    )
    staging.mkdir()
    try:
        shutil.copy2(RUNTIME_MAIN, staging / "main.py")
        (staging / "deck.csv").write_text(
            "".join(f"{card_id}\n" for card_id in deck),
            encoding="utf-8",
            newline="\n",
        )
        shutil.copy2(tables_path, staging / "frozen_tables.pt")
        runtime_modules = _copy_runtime_package(
            staging / "engine_native_policy"
        )
        torch.save(
            {
                "format": "engine-native-agent-v1",
                "state_dict": serving_state,
                "model_config": vars(model_config),
                "search_config": resolved_search.as_dict(),
            },
            staging / "model.pt",
        )

        resolved_name = agent_name or output_dir.name
        (staging / "README.md").write_text(
            _readme(resolved_name), encoding="utf-8", newline="\n"
        )
        manifest = {
            "schema_version": "engine-native-agent-v1",
            "agent_name": resolved_name,
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_checkpoint": {
                "filename": checkpoint.name,
                "sha256": _sha256(checkpoint),
                "state_field": checkpoint_field,
            },
            "files": {
                "model.pt": {
                    "sha256": _sha256(staging / "model.pt"),
                    "bytes": (staging / "model.pt").stat().st_size,
                },
                "frozen_tables.pt": {
                    "sha256": _sha256(staging / "frozen_tables.pt"),
                    "bytes": (staging / "frozen_tables.pt").stat().st_size,
                },
                "deck.csv": {
                    "sha256": _sha256(staging / "deck.csv"),
                    "cards": len(deck),
                },
            },
            "model": {
                "parameter_count": parameter_count,
                "config": vars(model_config),
                "search": resolved_search.as_dict(),
                "runtime_modules": list(runtime_modules),
            },
        }
        (staging / "agent-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(staging, output_dir)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return manifest


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        required=True,
        help="Trusted checkpoint.best.pt, checkpoint.latest.pt, or bare state dict.",
    )
    parser.add_argument(
        "--deck",
        type=Path,
        required=True,
        help="Deck CSV containing exactly 60 integer card IDs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New agent folder to create; it must not already exist.",
    )
    parser.add_argument(
        "--tables",
        type=Path,
        default=DEFAULT_TABLES,
        help="Frozen tables artifact (defaults to the installed real tables).",
    )
    parser.add_argument(
        "--name",
        help="Display name recorded in the generated manifest/README.",
    )
    parser.add_argument(
        "--tree-search",
        choices=("true", "false"),
        default=None,
        help="Override checkpoint search behavior; omitted preserves metadata.",
    )
    parser.add_argument("--mcts-simulations", type=int, default=800)
    parser.add_argument("--mcts-max-depth", type=int, default=32)
    parser.add_argument("--mcts-c-puct", type=float, default=1.5)
    parser.add_argument("--mcts-dirichlet-alpha", type=float, default=0.3)
    parser.add_argument("--mcts-dirichlet-epsilon", type=float, default=0.25)
    parser.add_argument("--mcts-temperature", type=float, default=1.0)
    parser.add_argument("--mcts-per-decision-seconds", type=float, default=None)
    parser.add_argument("--mcts-game-budget-seconds", type=float, default=None)
    parser.add_argument("--mcts-seed", type=int, default=20260730)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    search_config = (
        None
        if args.tree_search is None
        else SearchConfig(
            enabled=args.tree_search == "true",
            simulations=args.mcts_simulations,
            max_depth=args.mcts_max_depth,
            c_puct=args.mcts_c_puct,
            dirichlet_alpha=args.mcts_dirichlet_alpha,
            dirichlet_epsilon=args.mcts_dirichlet_epsilon,
            temperature=args.mcts_temperature,
            per_decision_seconds=args.mcts_per_decision_seconds,
            game_budget_seconds=args.mcts_game_budget_seconds,
            seed=args.mcts_seed,
        )
    )
    manifest = build_agent(
        checkpoint=args.checkpoint,
        deck_path=args.deck,
        output_dir=args.output_dir,
        tables_path=args.tables,
        agent_name=args.name,
        search_config=search_config,
    )
    print(f"Created agent: {args.output_dir.resolve()}")
    print(
        "Checkpoint: "
        f"{manifest['source_checkpoint']['filename']} "
        f"({manifest['source_checkpoint']['state_field']})"
    )
    print(f"Parameters: {manifest['model']['parameter_count']:,}")
    print(
        "Model SHA-256: "
        f"{manifest['files']['model.pt']['sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
