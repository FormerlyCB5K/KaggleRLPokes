"""Behavior-cloning likelihood and distribution-specific metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
import torch.nn.functional as F

from ..actions import select_options
from ..model import PolicyOutput


@dataclass(frozen=True)
class LossBreakdown:
    loss: torch.Tensor
    single_loss_sum: torch.Tensor
    multi_loss_sum: torch.Tensor
    single_count: int
    multi_count: int


def supervised_nll(
    output: PolicyOutput,
    batch: dict[str, torch.Tensor],
    option_mask: torch.Tensor,
) -> LossBreakdown:
    """Average one categorical or joint-Bernoulli NLL per decision."""

    device = output.logits.device
    is_multi = batch["is_multi"].to(device=device, dtype=torch.bool)
    option_mask = option_mask.to(device=device, dtype=torch.bool)
    n_options = batch["n_options"].to(device=device, dtype=torch.int64)
    if not torch.equal(option_mask.sum(dim=1), n_options):
        raise ValueError("decoded option-mask counts disagree with cached n_options")
    if output.logits.shape != option_mask.shape or output.incl.shape != option_mask.shape:
        raise ValueError("model option-head shapes disagree with option mask")

    single_rows = ~is_multi
    multi_rows = is_multi
    zero = output.logits.new_zeros(())

    if bool(single_rows.any()):
        single_targets = batch["single_target"].to(
            device=device, dtype=torch.int64
        )[single_rows]
        live = option_mask[single_rows].gather(
            1, single_targets.unsqueeze(1)
        )
        if not bool(live.all()):
            raise ValueError("single target points to a padded option")
        single_losses = F.cross_entropy(
            output.logits[single_rows], single_targets, reduction="none"
        )
        single_sum = single_losses.sum()
    else:
        single_sum = zero

    if bool(multi_rows.any()):
        targets = batch["multi_target"].to(
            device=device, dtype=output.incl.dtype
        )[multi_rows]
        live_mask = option_mask[multi_rows].to(output.incl.dtype)
        per_option = F.binary_cross_entropy_with_logits(
            output.incl[multi_rows], targets, reduction="none"
        )
        multi_sum = (per_option * live_mask).sum(dim=1).sum()
    else:
        multi_sum = zero

    count = int(is_multi.numel())
    if count == 0:
        raise ValueError("cannot compute a loss for an empty batch")
    return LossBreakdown(
        loss=(single_sum + multi_sum) / count,
        single_loss_sum=single_sum,
        multi_loss_sum=multi_sum,
        single_count=int(single_rows.sum().item()),
        multi_count=int(multi_rows.sum().item()),
    )


def batch_metrics(
    output: PolicyOutput,
    batch: dict[str, torch.Tensor],
    decoded: dict[str, torch.Tensor],
) -> dict[str, Any]:
    """Return additive metrics for later aggregation across validation batches."""

    option_mask = decoded["opt_mask"].to(torch.bool)
    breakdown = supervised_nll(output, batch, option_mask)
    is_multi = batch["is_multi"].to(
        device=output.logits.device, dtype=torch.bool
    )
    single = ~is_multi
    result: dict[str, Any] = {
        "single_count": breakdown.single_count,
        "multi_count": breakdown.multi_count,
        "single_nll_sum": float(breakdown.single_loss_sum.detach().cpu()),
        "multi_nll_sum": float(breakdown.multi_loss_sum.detach().cpu()),
        "single_top1_correct": 0,
        "single_top3_correct": 0,
        "single_top3_count": 0,
        "multi_exact_correct": 0,
        "multi_selected_count_correct": 0,
        "multi_cardinality_valid": 0,
        "multi_true_positive": 0,
        "multi_false_positive": 0,
        "multi_false_negative": 0,
        "single_by_option_type": {},
    }

    if bool(single.any()):
        logits = output.logits[single]
        targets = batch["single_target"].to(
            device=logits.device, dtype=torch.int64
        )[single]
        predictions = logits.argmax(dim=1)
        correct = predictions == targets
        result["single_top1_correct"] = int(correct.sum().item())
        n_options = batch["n_options"].to(
            device=logits.device, dtype=torch.int64
        )[single]
        eligible = n_options >= 3
        if bool(eligible.any()):
            top3 = logits[eligible].topk(3, dim=1).indices
            expected = targets[eligible].unsqueeze(1)
            result["single_top3_correct"] = int(
                (top3 == expected).any(dim=1).sum().item()
            )
            result["single_top3_count"] = int(eligible.sum().item())

        option_types = decoded["opt_type"].to(logits.device)[single]
        selected_types = option_types.gather(1, targets.unsqueeze(1)).squeeze(1)
        by_type: dict[str, dict[str, int]] = {}
        for option_type in selected_types.unique().tolist():
            mask = selected_types == option_type
            by_type[str(int(option_type))] = {
                "count": int(mask.sum().item()),
                "correct": int((correct & mask).sum().item()),
            }
        result["single_by_option_type"] = by_type

    multi_indices = torch.nonzero(is_multi, as_tuple=False).flatten().tolist()
    for row in multi_indices:
        n_options = int(batch["n_options"][row])
        minimum = int(batch["min_count"][row])
        maximum = int(batch["max_count"][row])
        predicted = set(
            select_options(
                output.logits[row],
                output.incl[row],
                n_options,
                minimum,
                maximum,
            )
        )
        expected = set(
            torch.nonzero(
                batch["multi_target"][row, :n_options], as_tuple=False
            )
            .flatten()
            .tolist()
        )
        result["multi_exact_correct"] += int(predicted == expected)
        result["multi_selected_count_correct"] += int(
            len(predicted) == len(expected)
        )
        result["multi_cardinality_valid"] += int(
            minimum <= len(predicted) <= maximum
        )
        result["multi_true_positive"] += len(predicted & expected)
        result["multi_false_positive"] += len(predicted - expected)
        result["multi_false_negative"] += len(expected - predicted)
    return result
