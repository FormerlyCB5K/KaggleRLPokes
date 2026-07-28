from __future__ import annotations

import pytest
import torch

from engine_native_policy.il.losses import supervised_nll
from engine_native_policy.model import PolicyOutput


def _output(logits: torch.Tensor, incl: torch.Tensor) -> PolicyOutput:
    batch = logits.shape[0]
    return PolicyOutput(
        logits=logits,
        incl=incl,
        value=torch.zeros(batch),
        value_fog=torch.zeros(batch),
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
    }
    mask = torch.tensor(
        [[True, True, False, False], [True, True, False, False]]
    )
    result = supervised_nll(_output(logits, incl), batch, mask)
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
    }
    result = supervised_nll(
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
    }
    with pytest.raises(ValueError, match="padded"):
        supervised_nll(
            output,
            batch,
            torch.tensor([[True, True, False]]),
        )
