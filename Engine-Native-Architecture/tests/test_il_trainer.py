from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import torch
from torch import nn

from engine_native_policy.il.trainer import TrainingConfig, run_training
from engine_native_policy.model import PolicyOutput
from engine_native_policy.tables import FrozenTables

from il_helpers import build_test_cache


class TinyPolicy(nn.Module):
    """Fast trainer test seam; the real network is covered by the smoke test."""

    def __init__(self) -> None:
        super().__init__()
        self.policy = nn.Parameter(torch.zeros(64))
        self.include = nn.Parameter(torch.zeros(64))

    def forward(self, batch: dict[str, torch.Tensor]) -> PolicyOutput:
        mask = batch["opt_mask"].to(torch.bool)
        rows = mask.shape[0]
        logits = self.policy.unsqueeze(0).expand(rows, -1)
        logits = logits.masked_fill(~mask, float("-inf"))
        include = self.include.unsqueeze(0).expand(rows, -1)
        include = include.masked_fill(~mask, -30.0)
        value = logits.new_zeros(rows)
        return PolicyOutput(
            logits=logits,
            incl=include,
            value=value,
            value_fog=value,
        )


def _factory(_tables: FrozenTables) -> nn.Module:
    return TinyPolicy()


def _config(cache, output) -> TrainingConfig:
    # Test caches live under pytest's temp root; use the installed project table.
    artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    return TrainingConfig(
        dataset_root=cache,
        output_dir=output,
        tables_path=artifacts / "frozen_tables.pt",
        epochs=2,
        batch_size=2,
        num_workers=0,
        learning_rate=1e-2,
        device="cpu",
        precision="fp32",
        early_stopping_patience=0,
        checkpoint_every_steps=1,
        log_every_steps=1000,
        verify_cache_hashes=False,
    )


def test_full_trainer_resume_matches_uninterrupted_run(tmp_path) -> None:
    _, cache = build_test_cache(tmp_path)
    resumed_output = tmp_path / "resumed"
    first = run_training(
        replace(
            _config(cache, resumed_output),
            max_optimizer_steps=1,
        ),
        model_factory=_factory,
    )
    assert first["status"] == "needs_resume"
    assert first["next_batch"] == 1

    resumed = run_training(
        replace(
            _config(cache, resumed_output),
            resume=True,
        ),
        model_factory=_factory,
    )
    assert resumed["status"] == "finished"

    uninterrupted_output = tmp_path / "uninterrupted"
    uninterrupted = run_training(
        _config(cache, uninterrupted_output),
        model_factory=_factory,
    )
    assert uninterrupted["status"] == "finished"

    resumed_state = torch.load(
        resumed_output / "checkpoint.latest.pt",
        map_location="cpu",
        weights_only=False,
    )
    uninterrupted_state = torch.load(
        uninterrupted_output / "checkpoint.latest.pt",
        map_location="cpu",
        weights_only=False,
    )
    for name, expected in uninterrupted_state["model_state_dict"].items():
        assert torch.equal(resumed_state["model_state_dict"][name], expected)
    assert resumed_state["global_step"] == uninterrupted_state["global_step"]
    assert len(resumed_state["history"]) == 3
    assert (resumed_output / "checkpoint.best.pt").is_file()
    assert (resumed_output / "training-summary.json").is_file()


def test_finished_resume_is_a_no_op(tmp_path) -> None:
    _, cache = build_test_cache(tmp_path)
    output = tmp_path / "finished"
    config = replace(_config(cache, output), epochs=1)
    result = run_training(config, model_factory=_factory)
    assert result["status"] == "finished"
    resumed = run_training(
        replace(config, resume=True), model_factory=_factory
    )
    assert resumed["status"] == "finished"
    assert resumed["global_step"] == result["global_step"]
