#!/usr/bin/env python
"""Train, record, and optionally evaluate an engine-native imitation policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


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
from engine_native_policy.model import ModelConfig  # noqa: E402
from engine_native_policy.mcts import SearchConfig  # noqa: E402


NO_EVALUATION = "NO EVALUATION PERFORMED FOR THIS RUN"
EVALUATION_SWITCHES = frozenset(
    {
        "evaluate",
        "evaluation_games",
        "evaluation_opponent_folder",
        "evaluation_opponent_deck",
        "evaluation_own_deck",
        "evaluation_checkpoint",
        "evaluation_max_actions",
    }
)
DEFAULT_DATASET_ROOT = (
    REPOSITORY_ROOT
    / "Imitation-Learning"
    / "Top-ladder-data"
    / "engine-native-cache-test-six-days"
)
DEFAULT_OUTPUT_DIR = (
    REPOSITORY_ROOT
    / "Imitation-Learning"
    / "engine-native-training"
    / "test-six-days"
    / "seed-20260728"
)
DEFAULT_TABLES = ENGINE_ROOT / "artifacts" / "frozen_tables.pt"
DEFAULT_OPPONENT = REPOSITORY_ROOT / "sample-archaludon"
DEFAULT_OWN_DECK = REPOSITORY_ROOT / "Rising-Tide-Fixed-Metal-v15" / "deck.csv"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(
        f"expected true or false, received {value!r}"
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value.expanduser().resolve())
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _training_summaries(output_dir: Path, result: dict[str, Any]) -> dict[str, Any]:
    history_path = output_dir / "history.json"
    history = _read_json(history_path) if history_path.is_file() else []
    baseline = next(
        (
            entry
            for entry in history
            if entry.get("kind") == "baseline"
        ),
        None,
    )
    epochs = [
        entry for entry in history if entry.get("kind") == "epoch"
    ]
    validation_entries = [
        entry
        for entry in history
        if isinstance(entry.get("validation"), dict)
        and entry["validation"].get("nll") is not None
    ]
    best = (
        min(
            validation_entries,
            key=lambda entry: float(
                entry["validation"].get(
                    "loss", entry["validation"]["nll"]
                )
            ),
        )
        if validation_entries
        else None
    )
    last = epochs[-1] if epochs else None
    training = {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "epochs_completed": result.get(
            "epochs_completed", result.get("epoch")
        ),
        "global_step": result.get("global_step"),
        "best_validation_loss": result.get("best_validation_loss"),
        "best_validation_nll": result.get("best_validation_nll"),
        "early_stopped": result.get("early_stopped"),
        "last_epoch": (
            {
                "epoch": last.get("epoch"),
                "global_step": last.get("global_step"),
                "metrics": last.get("train"),
            }
            if last is not None
            else None
        ),
        "best_checkpoint": result.get(
            "best_checkpoint", str(output_dir / "checkpoint.best.pt")
        ),
        "latest_checkpoint": result.get(
            "latest_checkpoint", str(output_dir / "checkpoint.latest.pt")
        ),
    }
    validation = {
        "baseline": baseline.get("validation") if baseline else None,
        "best": (
            {
                "epoch": best.get("epoch"),
                "global_step": best.get("global_step"),
                "metrics": best.get("validation"),
            }
            if best is not None
            else None
        ),
        "last": (
            {
                "epoch": last.get("epoch"),
                "global_step": last.get("global_step"),
                "metrics": last.get("validation"),
            }
            if last is not None
            else None
        ),
    }
    return {"training": training, "validation": validation}


def _resolve_checkpoint(value: str, output_dir: Path) -> Path:
    if value == "best":
        return output_dir / "checkpoint.best.pt"
    if value == "latest":
        return output_dir / "checkpoint.latest.pt"
    return Path(value).expanduser().resolve()


def _copy_agent_with_deck(
    source: Path,
    deck_path: Path,
    destination: Path,
) -> Path:
    source = source.expanduser().resolve()
    if not source.is_dir():
        raise RuntimeError(f"opponent folder does not exist: {source}")
    deck = _read_deck(deck_path)
    shutil.copytree(source, destination)
    matches = [
        path
        for path in destination.iterdir()
        if path.is_file() and path.name.casefold() == "deck.csv"
    ]
    for match in matches:
        match.unlink()
    (destination / "deck.csv").write_text(
        "".join(f"{card_id}\n" for card_id in deck),
        encoding="utf-8",
        newline="\n",
    )
    return destination


def _run_evaluation(
    args: argparse.Namespace,
    *,
    output_dir: Path,
) -> dict[str, Any]:
    checkpoint = _resolve_checkpoint(args.evaluation_checkpoint, output_dir)
    own_deck_path = args.evaluation_own_deck.expanduser().resolve()
    opponent_folder = args.evaluation_opponent_folder.expanduser().resolve()
    tables_path = args.tables.expanduser().resolve()
    for label, path in (
        ("evaluation checkpoint", checkpoint),
        ("evaluation own deck", own_deck_path),
        ("frozen tables", tables_path),
    ):
        if not path.is_file():
            raise RuntimeError(f"{label} does not exist: {path}")
    if not opponent_folder.is_dir():
        raise RuntimeError(
            f"evaluation opponent folder does not exist: {opponent_folder}"
        )

    evaluation_dir = output_dir / "evaluation"
    evaluation_dir.mkdir(parents=True, exist_ok=True)
    detailed_log = evaluation_dir / "results.json"
    started_at = _utc_now()
    timer = time.perf_counter()

    with tempfile.TemporaryDirectory(
        prefix=".evaluation-agent-",
        dir=evaluation_dir,
    ) as temporary:
        temporary_root = Path(temporary)
        trained_agent = temporary_root / "trained-agent"
        sys.path.insert(0, str(ENGINE_ROOT / "scripts"))
        try:
            from build_checkpoint_agent import build_agent
        finally:
            sys.path.pop(0)
        manifest = build_agent(
            checkpoint=checkpoint,
            deck_path=own_deck_path,
            output_dir=trained_agent,
            tables_path=tables_path,
            agent_name=args.model_name,
        )

        if args.evaluation_opponent_deck is not None:
            staged_opponent = _copy_agent_with_deck(
                opponent_folder,
                args.evaluation_opponent_deck.expanduser().resolve(),
                temporary_root / "opponent",
            )
        else:
            staged_opponent = opponent_folder

        opponent_name = opponent_folder.name
        if opponent_name == args.model_name:
            opponent_name = f"{opponent_name} opponent"
        command = [
            sys.executable,
            str(REPOSITORY_ROOT / "evaluate_agents.py"),
            str(trained_agent),
            str(staged_opponent),
            str(args.evaluation_games),
            "--name-a",
            args.model_name,
            "--name-b",
            opponent_name,
            "--output",
            str(detailed_log),
            "--max-actions",
            str(args.evaluation_max_actions),
        ]
        environment = dict(os.environ)
        environment["ENGINE_NATIVE_DEVICE"] = "cpu"
        subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=True,
        )

    payload = _read_json(detailed_log)
    bots = payload.get("bots") or {}
    own_bot = bots.get(args.model_name) or {}
    opponent_bot = bots.get(opponent_name) or {}
    elapsed = time.perf_counter() - timer
    return {
        "status": "completed",
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "runtime_seconds": elapsed,
        "settings": {
            "requested_games": args.evaluation_games,
            "max_actions_per_game": args.evaluation_max_actions,
            "opponent": {
                "name": opponent_name,
                "folder": str(opponent_folder),
                "entrypoint": opponent_bot.get("entrypoint"),
                "deck_source": (
                    str(args.evaluation_opponent_deck.expanduser().resolve())
                    if args.evaluation_opponent_deck is not None
                    else opponent_bot.get("deck_source")
                ),
                "deck": opponent_bot.get("configured_deck"),
            },
            "own_deck_source": str(own_deck_path),
            "own_deck": own_bot.get("configured_deck") or _read_deck(own_deck_path),
            "checkpoint": {
                "path": str(checkpoint.resolve()),
                "sha256": _sha256(checkpoint),
                "state_field": manifest["source_checkpoint"]["state_field"],
            },
        },
        "results": {
            "completed_games": payload.get("completed_games"),
            "summary": payload.get("summary"),
            "games": payload.get("games"),
            "error": payload.get("error"),
            "detailed_log": str(detailed_log.resolve()),
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Human-readable/cache-suffix dataset identifier.",
    )
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tables", type=Path, default=DEFAULT_TABLES)
    parser.add_argument(
        "--initial-checkpoint",
        type=Path,
        default=None,
        help="Optional compatible warm-start checkpoint.",
    )
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--model-width", type=int, default=224)
    parser.add_argument("--model-layers", type=int, default=4)
    parser.add_argument("--model-heads", type=int, default=4)
    parser.add_argument("--model-feedforward-width", type=int, default=448)
    parser.add_argument("--model-static-width", type=int, default=32)
    parser.add_argument("--model-effect-width", type=int, default=48)
    parser.add_argument("--model-registers", type=int, default=4)
    parser.add_argument("--model-dropout", type=float, default=0.0)
    parser.add_argument(
        "--value-loss-weight",
        type=float,
        default=0.01,
        help=(
            "Terminal-outcome MSE coefficient; 0.01 matches AlphaGo Zero's "
            "supervised-learning experiment."
        ),
    )
    parser.add_argument(
        "--tree-search",
        type=_parse_bool,
        default=False,
        metavar="{true,false}",
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
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda"), default="auto"
    )
    parser.add_argument(
        "--precision",
        choices=("auto", "fp32", "fp16", "bf16"),
        default="auto",
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
        help="Resume checkpoint.latest.pt when it exists.",
    )
    parser.add_argument(
        "--skip-cache-hash-verification",
        action="store_true",
    )
    parser.add_argument("--max-runtime-minutes", type=float, default=None)
    parser.add_argument("--max-optimizer-steps", type=int, default=None)
    parser.add_argument(
        "--max-resubmits",
        type=int,
        default=0,
        help="SLURM continuation budget, recorded here for provenance.",
    )

    parser.add_argument("--model-name", default="Engine Native IL")
    parser.add_argument("--model-description", default="")
    parser.add_argument(
        "--config-log",
        type=Path,
        default=None,
        help="Combined run JSON; defaults to <out-dir>/config/run.json.",
    )
    parser.add_argument(
        "--evaluate",
        type=_parse_bool,
        default=False,
        metavar="{true,false}",
    )
    parser.add_argument("--evaluation-games", type=int, default=100)
    parser.add_argument(
        "--evaluation-opponent-folder",
        type=Path,
        default=DEFAULT_OPPONENT,
    )
    parser.add_argument(
        "--evaluation-opponent-deck",
        type=Path,
        default=None,
        help="Optional deck.csv override for the opponent folder.",
    )
    parser.add_argument(
        "--evaluation-own-deck",
        type=Path,
        default=DEFAULT_OWN_DECK,
    )
    parser.add_argument(
        "--evaluation-checkpoint",
        default="best",
        help="'best', 'latest', or an explicit checkpoint path.",
    )
    parser.add_argument("--evaluation-max-actions", type=int, default=20_000)
    args = parser.parse_args(argv)
    if not args.model_name.strip():
        parser.error("--model-name cannot be empty")
    args.dataset_name = args.dataset_name or args.dataset_root.name
    args.run_name = args.run_name or args.model_name
    if args.max_resubmits < 0:
        parser.error("--max-resubmits must be non-negative")
    if (
        not math.isfinite(args.value_loss_weight)
        or args.value_loss_weight < 0
    ):
        parser.error("--value-loss-weight must be finite and non-negative")
    try:
        ModelConfig(
            d_model=args.model_width,
            n_layers=args.model_layers,
            n_heads=args.model_heads,
            d_ff=args.model_feedforward_width,
            d_stat=args.model_static_width,
            d_eff=args.model_effect_width,
            n_registers=args.model_registers,
            dropout=args.model_dropout,
            value_activation="tanh",
        ).validate()
        SearchConfig(
            enabled=args.tree_search,
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
    if args.evaluation_games <= 0:
        parser.error("--evaluation-games must be positive")
    if args.evaluation_max_actions <= 0:
        parser.error("--evaluation-max-actions must be positive")
    return args


def _new_record(args: argparse.Namespace, config_log: Path) -> dict[str, Any]:
    switches = {
        key: _json_value(value)
        for key, value in vars(args).items()
    }
    switches["config_log"] = str(config_log)
    search_config = SearchConfig(
        enabled=args.tree_search,
        simulations=args.mcts_simulations,
        max_depth=args.mcts_max_depth,
        c_puct=args.mcts_c_puct,
        dirichlet_alpha=args.mcts_dirichlet_alpha,
        dirichlet_epsilon=args.mcts_dirichlet_epsilon,
        temperature=args.mcts_temperature,
        per_decision_seconds=args.mcts_per_decision_seconds,
        game_budget_seconds=args.mcts_game_budget_seconds,
        seed=args.mcts_seed,
    ).as_dict()
    return {
        "schema_version": "engine-native-training-run-v1",
        "model": {
            "name": args.model_name,
            "description": args.model_description,
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
            **search_config,
            "mode": (
                "alpha_zero_mcts"
                if args.tree_search
                else "disabled"
            ),
            "boundary_policy": "conservative_public_information",
            "multi_select": "policy_resolved_macro_action",
        },
        "switches": switches,
        "switch_updates": [],
        "created_at_utc": _utc_now(),
        "updated_at_utc": _utc_now(),
        "state": "created",
        "runtime": {
            "training_invocation_seconds": 0.0,
            "evaluation_seconds": 0.0,
            "total_seconds": 0.0,
        },
        "invocations": [],
        "training": None,
        "validation": None,
        "evaluation": (
            {
                "status": "pending_training_completion",
                "requested_games": args.evaluation_games,
            }
            if args.evaluate
            else NO_EVALUATION
        ),
    }


def _load_or_create_record(
    args: argparse.Namespace, config_log: Path
) -> dict[str, Any]:
    expected = _new_record(args, config_log)
    if not config_log.is_file():
        return expected
    existing = _read_json(config_log)
    if existing.get("schema_version") != expected["schema_version"]:
        raise RuntimeError(f"{config_log}: unsupported run-record schema")
    if existing.get("model") != expected["model"]:
        raise RuntimeError(
            f"{config_log}: model name or description does not match this run"
        )
    existing_switches = existing.get("switches")
    expected_switches = expected["switches"]
    if not isinstance(existing_switches, dict):
        raise RuntimeError(f"{config_log}: run record has invalid switches")
    switch_changes = {
        key: {
            "recorded": existing_switches.get(key),
            "requested": expected_switches.get(key),
        }
        for key in sorted(set(existing_switches) | set(expected_switches))
        if existing_switches.get(key) != expected_switches.get(key)
    }
    if not switch_changes:
        return existing

    prior_evaluation = existing.get("evaluation")
    evaluation_completed = (
        isinstance(prior_evaluation, dict)
        and prior_evaluation.get("status") == "completed"
    )
    if set(switch_changes).issubset(EVALUATION_SWITCHES) and not evaluation_completed:
        changed_at = _utc_now()
        existing["switches"] = expected_switches
        updates = existing.setdefault("switch_updates", [])
        if not isinstance(updates, list):
            raise RuntimeError(f"{config_log}: run record has invalid switch_updates")
        updates.append(
            {
                "changed_at_utc": changed_at,
                "scope": "post_training_evaluation",
                "changes": switch_changes,
            }
        )
        existing["evaluation"] = expected["evaluation"]
        existing["updated_at_utc"] = changed_at
        return existing

    raise RuntimeError(
        f"{config_log}: command-line switches do not match this run; "
        "use the recorded switches or a new --run-name. Differences:\n"
        f"{json.dumps(switch_changes, indent=2, sort_keys=True)}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.out_dir.expanduser().resolve()
    config_log = (
        args.config_log.expanduser().resolve()
        if args.config_log is not None
        else output_dir / "config" / "run.json"
    )
    record = _load_or_create_record(args, config_log)
    invocation_started_utc = _utc_now()
    invocation_timer = time.perf_counter()
    invocation = {
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "started_at_utc": invocation_started_utc,
        "finished_at_utc": None,
        "runtime_seconds": None,
        "status": "running",
    }
    record["state"] = "training"
    record["updated_at_utc"] = _utc_now()
    _write_json_atomic(config_log, record)

    search_config = SearchConfig(
        enabled=args.tree_search,
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
    model_config = ModelConfig(
        d_model=args.model_width,
        n_layers=args.model_layers,
        n_heads=args.model_heads,
        d_ff=args.model_feedforward_width,
        d_stat=args.model_static_width,
        d_eff=args.model_effect_width,
        n_registers=args.model_registers,
        dropout=args.model_dropout,
        value_activation="tanh",
    )
    config = TrainingConfig(
        dataset_root=args.dataset_root,
        output_dir=args.out_dir,
        tables_path=args.tables,
        initial_checkpoint=args.initial_checkpoint,
        epochs=args.epochs,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
        learning_rate=args.learning_rate,
        value_loss_weight=args.value_loss_weight,
        model_config=model_config,
        search_config=search_config,
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

    try:
        result = run_training(config)
    except BaseException as exc:
        elapsed = time.perf_counter() - invocation_timer
        invocation.update(
            {
                "finished_at_utc": _utc_now(),
                "runtime_seconds": elapsed,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        record["invocations"].append(invocation)
        record["runtime"]["training_invocation_seconds"] += elapsed
        record["runtime"]["total_seconds"] += elapsed
        record["state"] = "failed"
        record["training"] = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
        }
        record["updated_at_utc"] = _utc_now()
        _write_json_atomic(config_log, record)
        raise

    training_elapsed = time.perf_counter() - invocation_timer
    invocation.update(
        {
            "finished_at_utc": _utc_now(),
            "runtime_seconds": training_elapsed,
            "status": result["status"],
        }
    )
    record["invocations"].append(invocation)
    record["runtime"]["training_invocation_seconds"] += training_elapsed
    record["runtime"]["total_seconds"] += training_elapsed
    summaries = _training_summaries(output_dir, result)
    record.update(summaries)
    record["state"] = result["status"]
    record["updated_at_utc"] = _utc_now()
    _write_json_atomic(config_log, record)

    if result["status"] == "finished" and args.evaluate:
        prior_evaluation = record.get("evaluation")
        if not (
            isinstance(prior_evaluation, dict)
            and prior_evaluation.get("status") == "completed"
        ):
            record["state"] = "evaluating"
            record["evaluation"] = {
                "status": "running",
                "requested_games": args.evaluation_games,
                "started_at_utc": _utc_now(),
            }
            record["updated_at_utc"] = _utc_now()
            _write_json_atomic(config_log, record)
            try:
                evaluation = _run_evaluation(args, output_dir=output_dir)
            except BaseException as exc:
                evaluation_elapsed = time.perf_counter() - invocation_timer - training_elapsed
                record["runtime"]["evaluation_seconds"] += evaluation_elapsed
                record["runtime"]["total_seconds"] += evaluation_elapsed
                record["state"] = "evaluation_failed"
                record["evaluation"] = {
                    "status": "failed",
                    "requested_games": args.evaluation_games,
                    "finished_at_utc": _utc_now(),
                    "runtime_seconds": evaluation_elapsed,
                    "error": f"{type(exc).__name__}: {exc}",
                    "traceback": traceback.format_exc(),
                }
                record["updated_at_utc"] = _utc_now()
                _write_json_atomic(config_log, record)
                raise
            record["evaluation"] = evaluation
            record["runtime"]["evaluation_seconds"] += float(
                evaluation["runtime_seconds"]
            )
            record["runtime"]["total_seconds"] += float(
                evaluation["runtime_seconds"]
            )

    if result["status"] == "finished":
        record["state"] = "finished"
    record["updated_at_utc"] = _utc_now()
    _write_json_atomic(config_log, record)
    print(f"Combined run config: {config_log}", flush=True)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return (
        TIME_LIMIT_EXIT_CODE
        if result["status"] == "needs_resume"
        else 0
    )


if __name__ == "__main__":
    raise SystemExit(main())
