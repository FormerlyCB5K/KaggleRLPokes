from __future__ import annotations

import pytest
import torch

from engine_native_policy.actions import select_options
from engine_native_policy.il.losses import batch_metrics, supervised_loss
from engine_native_policy.model import PolicyOutput


def _output(
    logits: torch.Tensor,
    incl: torch.Tensor,
    value: torch.Tensor | None = None,
) -> PolicyOutput:
    batch = logits.shape[0]
    if value is None:
        value = torch.zeros(batch)
    return PolicyOutput(
        logits=logits,
        incl=incl,
        value=value,
        value_fog=value.detach(),
    )


def test_mixed_loss_matches_categorical_plus_live_joint_bernoulli() -> None:
    logits = torch.tensor(
        [[2.0, 0.0, -float("inf"), -float("inf")], [0.0, 0.0, -float("inf"), -float("inf")]],
        requires_grad=True,
    )
    incl = torch.tensor(
        [[9.0, 9.0, 9.0, 9.0], [1.0, -1.0, 100.0, -100.0]],
        requires_grad=True,
    )
    batch = {
        "is_multi": torch.tensor([False, True]),
        "single_target": torch.tensor([0, -100]),
        "multi_target": torch.tensor(
            [[False, False, False, False], [True, False, False, False]]
        ),
        "n_options": torch.tensor([2, 2], dtype=torch.uint8),
        "value_target": torch.tensor([0.0, 0.0]),
    }
    mask = torch.tensor(
        [[True, True, False, False], [True, True, False, False]]
    )
    result = supervised_loss(_output(logits, incl), batch, mask)
    expected_single = torch.nn.functional.cross_entropy(
        logits[:1], torch.tensor([0])
    )
    expected_multi = torch.nn.functional.binary_cross_entropy_with_logits(
        incl[1, :2], torch.tensor([1.0, 0.0]), reduction="sum"
    )
    assert float(result.loss.detach()) == pytest.approx(
        float(((expected_single + expected_multi) / 2).detach())
    )
    result.loss.backward()
    assert logits.grad is not None
    assert incl.grad is not None
    assert torch.count_nonzero(incl.grad[0]) == 0
    assert torch.count_nonzero(logits.grad[1]) == 0
    assert torch.count_nonzero(incl.grad[1, 2:]) == 0


def test_single_only_does_not_train_include_head() -> None:
    logits = torch.zeros((1, 3), requires_grad=True)
    incl = torch.zeros((1, 3), requires_grad=True)
    batch = {
        "is_multi": torch.tensor([False]),
        "single_target": torch.tensor([1]),
        "multi_target": torch.zeros((1, 3), dtype=torch.bool),
        "n_options": torch.tensor([3], dtype=torch.uint8),
        "value_target": torch.tensor([0.0]),
    }
    result = supervised_loss(
        _output(logits, incl),
        batch,
        torch.ones((1, 3), dtype=torch.bool),
    )
    result.loss.backward()
    assert logits.grad is not None
    assert incl.grad is None


def test_padded_single_target_is_rejected() -> None:
    output = _output(torch.zeros((1, 3)), torch.zeros((1, 3)))
    batch = {
        "is_multi": torch.tensor([False]),
        "single_target": torch.tensor([2]),
        "multi_target": torch.zeros((1, 3), dtype=torch.bool),
        "n_options": torch.tensor([2], dtype=torch.uint8),
        "value_target": torch.tensor([0.0]),
    }
    with pytest.raises(ValueError, match="padded"):
        supervised_loss(
            output,
            batch,
            torch.tensor([[True, True, False]]),
        )


def test_batched_multi_metrics_match_serving_projection() -> None:
    include_logits = torch.tensor(
        [
            [0.1, 0.2, -0.1, -0.2],
            [-10.0, -10.0, -10.0, -10.0],
            [0.4, 0.3, 0.2, -0.1],
        ]
    )
    expected_sets = [
        select_options(torch.zeros(4), include_logits[row], 4, minimum, maximum)
        for row, (minimum, maximum) in enumerate(((1, 2), (2, 3), (1, 2)))
    ]
    targets = torch.zeros((3, 4), dtype=torch.bool)
    for row, selected in enumerate(expected_sets):
        targets[row, selected] = True
    batch = {
        "is_multi": torch.ones(3, dtype=torch.bool),
        "single_target": torch.full((3,), -100),
        "multi_target": targets,
        "n_options": torch.full((3,), 4, dtype=torch.uint8),
        "min_count": torch.tensor([1, 2, 1], dtype=torch.uint8),
        "max_count": torch.tensor([2, 3, 2], dtype=torch.uint8),
        "value_target": torch.tensor([1.0, -1.0, 0.0]),
    }
    output = _output(torch.zeros((3, 4)), include_logits)
    metrics = batch_metrics(
        output,
        batch,
        {
            "opt_mask": torch.ones((3, 4), dtype=torch.bool),
            "opt_type": torch.zeros((3, 4), dtype=torch.int64),
        },
    )
    assert metrics["multi_exact_correct"] == 3
    assert metrics["multi_selected_count_correct"] == 3
    assert metrics["multi_cardinality_valid"] == 3
    assert metrics["value_mse_sum"] == pytest.approx(2.0)
    assert metrics["value_mae_sum"] == pytest.approx(2.0)
    assert metrics["value_decisive_count"] == 2
    assert metrics["value_sign_correct"] == 0


def test_joint_loss_adds_weighted_value_mse_and_trains_value_head() -> None:
    logits = torch.tensor([[1.0, 0.0], [0.0, 1.0]], requires_grad=True)
    incl = torch.zeros((2, 2), requires_grad=True)
    values = torch.tensor([0.25, -0.5], requires_grad=True)
    batch = {
        "is_multi": torch.tensor([False, False]),
        "single_target": torch.tensor([0, 1]),
        "multi_target": torch.zeros((2, 2), dtype=torch.bool),
        "n_options": torch.tensor([2, 2], dtype=torch.uint8),
        "value_target": torch.tensor([1.0, -1.0]),
    }
    result = supervised_loss(
        _output(logits, incl, values),
        batch,
        torch.ones((2, 2), dtype=torch.bool),
        value_loss_weight=0.5,
    )
    expected_value_mse = ((0.25 - 1.0) ** 2 + (-0.5 + 1.0) ** 2) / 2
    assert float(result.value_loss.detach()) == pytest.approx(expected_value_mse)
    assert float(result.loss.detach()) == pytest.approx(
        float(result.policy_loss.detach()) + 0.5 * expected_value_mse
    )
    result.loss.backward()
    assert values.grad is not None
    assert torch.count_nonzero(values.grad) == 2


def test_default_loss_uses_alphago_zero_supervised_value_weight() -> None:
    logits = torch.tensor([[0.0, 0.0]])
    incl = torch.zeros((1, 2))
    batch = {
        "is_multi": torch.tensor([False]),
        "single_target": torch.tensor([0]),
        "multi_target": torch.zeros((1, 2), dtype=torch.bool),
        "n_options": torch.tensor([2], dtype=torch.uint8),
        "value_target": torch.tensor([1.0]),
    }
    result = supervised_loss(
        _output(logits, incl, torch.tensor([0.0])),
        batch,
        torch.ones((1, 2), dtype=torch.bool),
    )
    assert float(result.value_loss.detach()) == pytest.approx(1.0)
    assert float(result.loss.detach()) == pytest.approx(
        float(result.policy_loss.detach()) + 0.01
    )
