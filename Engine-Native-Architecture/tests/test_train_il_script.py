from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT / "scripts" / "train_il.py"


def _load_script():
    name = "test_engine_native_train_il_script"
    spec = importlib.util.spec_from_file_location(name, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _fake_training(config) -> dict:
    output = config.output_dir
    output.mkdir(parents=True, exist_ok=True)
    history = [
        {
            "kind": "baseline",
            "epoch": -1,
            "global_step": 0,
            "validation": {
                "loss": 2.01,
                "nll": 2.0,
                "value_mse": 1.0,
                "single_top1_accuracy": 0.2,
            },
        },
        {
            "kind": "epoch",
            "epoch": 0,
            "global_step": 4,
            "train": {"nll": 1.0, "count": 8},
            "validation": {
                "loss": 0.805,
                "nll": 0.8,
                "value_mse": 0.5,
                "single_top1_accuracy": 0.7,
            },
        },
    ]
    (output / "history.json").write_text(json.dumps(history), encoding="utf-8")
    return {
        "status": "finished",
        "epochs_completed": 1,
        "global_step": 4,
        "best_validation_loss": 0.805,
        "best_validation_nll": 0.8,
        "early_stopped": False,
        "best_checkpoint": str(output / "checkpoint.best.pt"),
        "latest_checkpoint": str(output / "checkpoint.latest.pt"),
        "output_dir": str(output),
    }


def test_combined_config_records_switches_summaries_and_no_evaluation(
    tmp_path: Path, monkeypatch
) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "run_training", _fake_training)
    output = tmp_path / "output"
    config_log = tmp_path / "config" / "run.json"

    status = script.main(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(output),
            "--config-log",
            str(config_log),
            "--model-name",
            "Fixture Model",
            "--model-description",
            "Description with spaces",
            "--epochs",
            "1",
            "--evaluate",
            "false",
        ]
    )

    assert status == 0
    record = json.loads(config_log.read_text(encoding="utf-8"))
    assert record["state"] == "finished"
    assert record["model"] == {
        "name": "Fixture Model",
        "description": "Description with spaces",
    }
    assert record["switches"]["epochs"] == 1
    assert record["switches"]["value_loss_weight"] == 0.01
    assert record["switches"]["evaluate"] is False
    assert record["reward_shaping"] == {
        "enabled": False,
        "value_target": "terminal_outcome",
        "win": 1.0,
        "draw": 0.0,
        "loss": -1.0,
        "discount": 1.0,
        "value_activation": "tanh",
    }
    assert record["tree_search"] == {
        "enabled": False,
        "simulations": 800,
        "max_depth": 32,
        "c_puct": 1.5,
        "dirichlet_alpha": 0.3,
        "dirichlet_epsilon": 0.25,
        "temperature": 1.0,
        "per_decision_seconds": None,
        "game_budget_seconds": None,
        "seed": 20260730,
        "mode": "disabled",
        "boundary_policy": "conservative_public_information",
        "multi_select": "policy_resolved_macro_action",
    }
    assert record["training"]["best_validation_loss"] == 0.805
    assert record["training"]["last_epoch"]["metrics"]["nll"] == 1.0
    assert record["validation"]["best"]["metrics"]["nll"] == 0.8
    assert record["evaluation"] == script.NO_EVALUATION
    assert record["runtime"]["total_seconds"] >= 0


def test_combined_config_records_evaluation_results(
    tmp_path: Path, monkeypatch
) -> None:
    script = _load_script()
    monkeypatch.setattr(script, "run_training", _fake_training)
    monkeypatch.setattr(
        script,
        "_run_evaluation",
        lambda args, output_dir: {
            "status": "completed",
            "runtime_seconds": 1.25,
            "settings": {
                "requested_games": args.evaluation_games,
                "checkpoint": {"path": "checkpoint.best.pt"},
            },
            "results": {
                "completed_games": args.evaluation_games,
                "summary": {"Fixture Model": {"overall": {"wins": 60}}},
            },
        },
    )
    config_log = tmp_path / "config" / "run.json"

    status = script.main(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(tmp_path / "output"),
            "--config-log",
            str(config_log),
            "--model-name",
            "Fixture Model",
            "--evaluate",
            "true",
            "--evaluation-games",
            "100",
        ]
    )

    assert status == 0
    record = json.loads(config_log.read_text(encoding="utf-8"))
    assert record["evaluation"]["status"] == "completed"
    assert record["evaluation"]["settings"]["requested_games"] == 100
    assert record["evaluation"]["results"]["completed_games"] == 100
    assert record["runtime"]["evaluation_seconds"] == 1.25


def test_pending_run_allows_audited_evaluation_switch_update(tmp_path: Path) -> None:
    script = _load_script()
    config_log = tmp_path / "config" / "run.json"
    old_deck = tmp_path / "old-deck.csv"
    new_deck = tmp_path / "new-deck.csv"
    old_args = script.parse_args(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(tmp_path / "output"),
            "--config-log",
            str(config_log),
            "--evaluate",
            "true",
            "--evaluation-own-deck",
            str(old_deck),
        ]
    )
    script._write_json_atomic(
        config_log,
        script._new_record(old_args, config_log.resolve()),
    )

    new_args = script.parse_args(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(tmp_path / "output"),
            "--config-log",
            str(config_log),
            "--evaluate",
            "true",
            "--evaluation-own-deck",
            str(new_deck),
        ]
    )
    record = script._load_or_create_record(new_args, config_log.resolve())

    assert record["switches"]["evaluation_own_deck"] == str(new_deck.resolve())
    assert record["evaluation"] == {
        "status": "pending_training_completion",
        "requested_games": 100,
    }
    assert record["switch_updates"] == [
        {
            "changed_at_utc": record["switch_updates"][0]["changed_at_utc"],
            "scope": "post_training_evaluation",
            "changes": {
                "evaluation_own_deck": {
                    "recorded": str(old_deck.resolve()),
                    "requested": str(new_deck.resolve()),
                }
            },
        }
    ]


def test_training_switch_mismatch_reports_the_differences(tmp_path: Path) -> None:
    script = _load_script()
    config_log = tmp_path / "config" / "run.json"
    original = script.parse_args(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(tmp_path / "output"),
            "--config-log",
            str(config_log),
            "--learning-rate",
            "1e-4",
        ]
    )
    script._write_json_atomic(
        config_log,
        script._new_record(original, config_log.resolve()),
    )
    changed = script.parse_args(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(tmp_path / "output"),
            "--config-log",
            str(config_log),
            "--learning-rate",
            "2e-4",
        ]
    )

    with pytest.raises(RuntimeError, match='"learning_rate"'):
        script._load_or_create_record(changed, config_log.resolve())


def test_completed_evaluation_is_archived_before_reevaluation(tmp_path: Path) -> None:
    script = _load_script()
    config_log = tmp_path / "config" / "run.json"
    original = script.parse_args(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(tmp_path / "output"),
            "--config-log",
            str(config_log),
            "--evaluate",
            "true",
            "--evaluation-games",
            "10",
        ]
    )
    record = script._new_record(original, config_log.resolve())
    prior_evaluation = {
        "status": "completed",
        "results": {"completed_games": 10},
    }
    record["evaluation"] = prior_evaluation
    script._write_json_atomic(config_log, record)
    changed = script.parse_args(
        [
            "--dataset-root",
            str(tmp_path / "dataset"),
            "--out-dir",
            str(tmp_path / "output"),
            "--config-log",
            str(config_log),
            "--evaluate",
            "true",
            "--evaluation-games",
            "20",
        ]
    )

    updated = script._load_or_create_record(changed, config_log.resolve())

    assert updated["switches"]["evaluation_games"] == 20
    assert updated["evaluation"] == {
        "status": "pending_training_completion",
        "requested_games": 20,
    }
    assert updated["evaluation_history"] == [
        {
            "archived_at_utc": updated["evaluation_history"][0][
                "archived_at_utc"
            ],
            "switches": {
                key: record["switches"].get(key)
                for key in sorted(script.EVALUATION_SWITCHES)
            },
            "evaluation": prior_evaluation,
        }
    ]


def test_reevaluation_uses_a_distinct_detailed_log(tmp_path: Path) -> None:
    script = _load_script()
    evaluation_dir = tmp_path / "evaluation"
    evaluation_dir.mkdir()

    assert script._next_evaluation_log_path(evaluation_dir) == (
        evaluation_dir / "results.json"
    )
    (evaluation_dir / "results.json").write_text("{}", encoding="utf-8")

    next_log = script._next_evaluation_log_path(evaluation_dir)
    assert next_log.parent == evaluation_dir
    assert next_log.name.startswith("results-")
    assert next_log.suffix == ".json"
