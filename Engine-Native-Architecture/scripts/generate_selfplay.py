#!/usr/bin/env python3
"""Generate AlphaZero root-visit/value examples from latest-network self-play."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


ARCHITECTURE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ARCHITECTURE_ROOT.parent
SOURCE_ROOT = ARCHITECTURE_ROOT / "src"
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(SOURCE_ROOT))

from engine_native_policy.mcts import SearchConfig  # noqa: E402
from engine_native_policy.selfplay import (  # noqa: E402
    append_selfplay_game,
    play_selfplay_game,
)
from engine_native_policy.tables import FrozenTables  # noqa: E402


DEFAULT_TABLES = ARCHITECTURE_ROOT / "artifacts" / "frozen_tables.pt"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _read_deck(path: Path) -> list[int]:
    try:
        deck = [
            int(line.strip())
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except ValueError as exc:
        raise RuntimeError("deck contains a non-integer line") from exc
    if len(deck) != 60:
        raise RuntimeError(f"deck must contain 60 cards, found {len(deck)}")
    return deck


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--tables", type=Path, default=DEFAULT_TABLES)
    parser.add_argument("--games", type=int, required=True)
    parser.add_argument("--start-game", type=int, default=None)
    parser.add_argument("--max-actions", type=int, default=20_000)
    parser.add_argument(
        "--device", choices=("cpu", "cuda"), default="cpu"
    )
    parser.add_argument("--model-name", default="Engine Native Self-Play")
    parser.add_argument("--model-description", default="")
    parser.add_argument("--config-log", type=Path, default=None)
    parser.add_argument("--mcts-simulations", type=int, default=800)
    parser.add_argument("--mcts-max-depth", type=int, default=32)
    parser.add_argument("--mcts-c-puct", type=float, default=1.5)
    parser.add_argument("--mcts-dirichlet-alpha", type=float, default=0.3)
    parser.add_argument("--mcts-dirichlet-epsilon", type=float, default=0.25)
    parser.add_argument("--mcts-temperature", type=float, default=1.0)
    parser.add_argument("--mcts-per-decision-seconds", type=float, default=None)
    parser.add_argument("--mcts-game-budget-seconds", type=float, default=None)
    parser.add_argument("--mcts-seed", type=int, default=20260730)
    args = parser.parse_args(argv)
    if args.games < 1:
        parser.error("--games must be positive")
    if args.start_game is not None and args.start_game < 1:
        parser.error("--start-game must be positive")
    if args.max_actions < 1:
        parser.error("--max-actions must be positive")
    if not args.model_name.strip():
        parser.error("--model-name cannot be empty")
    if args.device == "cuda":
        import torch

        if not torch.cuda.is_available():
            parser.error("--device cuda requested but CUDA is unavailable")
    try:
        SearchConfig(
            enabled=True,
            simulations=args.mcts_simulations,
            max_depth=args.mcts_max_depth,
            c_puct=args.mcts_c_puct,
            dirichlet_alpha=args.mcts_dirichlet_alpha,
            dirichlet_epsilon=args.mcts_dirichlet_epsilon,
            temperature=args.mcts_temperature,
            per_decision_seconds=args.mcts_per_decision_seconds,
            game_budget_seconds=args.mcts_game_budget_seconds,
            seed=args.mcts_seed,
        ).validate()
    except ValueError as exc:
        parser.error(str(exc))
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    config_log = (
        args.config_log.expanduser().resolve()
        if args.config_log is not None
        else output_dir / "config" / "generation.json"
    )
    checkpoint = args.checkpoint.expanduser().resolve()
    deck_path = args.deck.expanduser().resolve()
    tables_path = args.tables.expanduser().resolve()
    for label, path in (
        ("checkpoint", checkpoint),
        ("deck", deck_path),
        ("tables", tables_path),
    ):
        if not path.is_file():
            raise RuntimeError(f"{label} does not exist: {path}")
    deck = _read_deck(deck_path)
    tables = FrozenTables.load(tables_path)
    if tables.provisional:
        raise RuntimeError("self-play refuses provisional frozen tables")
    search_config = SearchConfig(
        enabled=True,
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
    manifest_path = output_dir / "manifest.json"
    existing_games = 0
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing_games = len(manifest.get("games", []))
    first_game = args.start_game or existing_games + 1
    record = {
        "schema_version": "engine-native-selfplay-run-v1",
        "state": "running",
        "model": {
            "name": args.model_name,
            "description": args.model_description,
        },
        "checkpoint_update": {
            "policy": "latest_network_pinned_per_game",
            "promotion_gate": False,
            "checkpoint_path": str(checkpoint),
        },
        "reward_shaping": {
            "enabled": False,
            "value_target": "terminal_outcome",
            "win": 1.0,
            "draw": 0.0,
            "loss": -1.0,
            "discount": 1.0,
            "value_activation": "tanh",
        },
        "tree_search": {
            **search_config.as_dict(),
            "mode": "alpha_zero_mcts",
            "boundary_policy": "conservative_public_information",
            "multi_select": "policy_resolved_macro_action",
        },
        "data": {
            "deck": str(deck_path),
            "tables": str(tables_path),
            "output_dir": str(output_dir),
            "requested_games": args.games,
            "first_game": first_game,
            "max_actions": args.max_actions,
            "multi_select_policy_targets": "omitted",
        },
        "device": args.device,
        "started_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "runtime_seconds": 0.0,
        "games": [],
        "result_counts": {"side_0": 0, "side_1": 0, "draw": 0},
    }
    _json_atomic(config_log, record)
    started = time.perf_counter()
    try:
        for offset in range(args.games):
            game_index = first_game + offset
            payload, summary = play_selfplay_game(
                game_index=game_index,
                checkpoint=checkpoint,
                deck=deck,
                tables=tables,
                search_config=search_config,
                device=args.device,
                max_actions=args.max_actions,
            )
            game = append_selfplay_game(
                output_dir,
                payload,
                summary,
                search_config=search_config,
                checkpoint=checkpoint,
            )
            record["games"].append(
                {
                    "game": game.game,
                    "result": game.result,
                    "examples": game.examples,
                    "policy_examples": game.policy_examples,
                    "checkpoint_sha256": game.checkpoint_sha256,
                    "runtime_seconds": game.elapsed_seconds,
                }
            )
            outcome = ("side_0", "side_1", "draw")[game.result]
            record["result_counts"][outcome] += 1
            record["runtime_seconds"] = time.perf_counter() - started
            record["updated_at_utc"] = _utc_now()
            _json_atomic(config_log, record)
            print(
                f"[{offset + 1}/{args.games}] game={game.game} "
                f"result={outcome} examples={game.examples} "
                f"policy_examples={game.policy_examples} "
                f"seconds={game.elapsed_seconds:.2f}",
                flush=True,
            )
    except BaseException as exc:
        record["state"] = "failed"
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["runtime_seconds"] = time.perf_counter() - started
        record["updated_at_utc"] = _utc_now()
        _json_atomic(config_log, record)
        raise
    record["state"] = "finished"
    record["runtime_seconds"] = time.perf_counter() - started
    record["updated_at_utc"] = _utc_now()
    record["summary"] = {
        "completed_games": len(record["games"]),
        "examples": sum(item["examples"] for item in record["games"]),
        "policy_examples": sum(
            item["policy_examples"] for item in record["games"]
        ),
    }
    _json_atomic(config_log, record)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
