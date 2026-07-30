"""Joint expert-policy and terminal-outcome imitation objectives."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import torch
import torch.nn.functional as F

from ..model import PolicyOutput


@dataclass(frozen=True)
class LossBreakdown:
    loss: torch.Tensor
    policy_loss: torch.Tensor
    value_loss: torch.Tensor
    single_loss_sum: torch.Tensor
    multi_loss_sum: torch.Tensor
    value_loss_sum: torch.Tensor
    single_count: int
    multi_count: int
    value_count: int


def supervised_loss(
    output: PolicyOutput,
    batch: dict[str, torch.Tensor],
    option_mask: torch.Tensor,
    *,
    value_loss_weight: float = 0.01,
) -> LossBreakdown:
    """Average policy NLL plus weighted terminal-outcome MSE per decision."""

    device = output.logits.device
    if not math.isfinite(value_loss_weight) or value_loss_weight < 0:
        raise ValueError("value_loss_weight must be finite and nonnegative")
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
    if output.value.shape != (count,):
        raise ValueError("model value-head shape disagrees with batch size")
    value_target = batch["value_target"].to(
        device=device, dtype=output.value.dtype
    )
    if value_target.shape != (count,):
        raise ValueError("value_target shape disagrees with batch size")
    if not bool(torch.isfinite(value_target).all()):
        raise ValueError("value_target must be finite")
    if not bool(
        (
            (value_target == -1.0)
            | (value_target == 0.0)
            | (value_target == 1.0)
        ).all()
    ):
        raise ValueError("value_target must contain only -1, 0, or 1")

    policy_loss = (single_sum + multi_sum) / count
    value_losses = F.mse_loss(output.value, value_target, reduction="none")
    value_sum = value_losses.sum()
    value_loss = value_sum / count
    return LossBreakdown(
        loss=policy_loss + value_loss_weight * value_loss,
        policy_loss=policy_loss,
        value_loss=value_loss,
        single_loss_sum=single_sum,
        multi_loss_sum=multi_sum,
        value_loss_sum=value_sum,
        single_count=int(single_rows.sum().item()),
        multi_count=int(multi_rows.sum().item()),
        value_count=count,
    )


def supervised_nll(
    output: PolicyOutput,
    batch: dict[str, torch.Tensor],
    option_mask: torch.Tensor,
    *,
    value_loss_weight: float = 0.01,
) -> LossBreakdown:
    """Compatibility alias for the joint supervised objective."""

    return supervised_loss(
        output,
        batch,
        option_mask,
        value_loss_weight=value_loss_weight,
    )


def batch_metrics(
    output: PolicyOutput,
    batch: dict[str, torch.Tensor],
    decoded: dict[str, torch.Tensor],
    *,
    value_loss_weight: float = 0.01,
) -> dict[str, Any]:
    """Return additive metrics for later aggregation across validation batches."""

    option_mask = decoded["opt_mask"].to(torch.bool)
    breakdown = supervised_loss(
        output,
        batch,
        option_mask,
        value_loss_weight=value_loss_weight,
    )
    is_multi = batch["is_multi"].to(
        device=output.logits.device, dtype=torch.bool
    )
    single = ~is_multi
    result: dict[str, Any] = {
        "single_count": breakdown.single_count,
        "multi_count": breakdown.multi_count,
        "single_nll_sum": float(breakdown.single_loss_sum.detach().cpu()),
        "multi_nll_sum": float(breakdown.multi_loss_sum.detach().cpu()),
        "value_mse_sum": float(breakdown.value_loss_sum.detach().cpu()),
        "value_mae_sum": 0.0,
        "value_prediction_sum": 0.0,
        "value_target_sum": 0.0,
        "value_count": breakdown.value_count,
        "value_decisive_count": 0,
        "value_sign_correct": 0,
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
    values = output.value.detach()
    value_targets = batch["value_target"].to(
        device=values.device, dtype=values.dtype
    )
    result["value_mae_sum"] = float(
        (values - value_targets).abs().sum().cpu()
    )
    result["value_prediction_sum"] = float(values.sum().cpu())
    result["value_target_sum"] = float(value_targets.sum().cpu())
    decisive = value_targets != 0
    result["value_decisive_count"] = int(decisive.sum().item())
    if bool(decisive.any()):
        result["value_sign_correct"] = int(
            (
                torch.sign(values[decisive])
                == torch.sign(value_targets[decisive])
            ).sum().item()
        )

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

    if bool(is_multi.any()):
        live = option_mask[is_multi]
        include_logits = output.incl[is_multi]
        targets = batch["multi_target"].to(
            device=include_logits.device, dtype=torch.bool
        )[is_multi] & live
        minimum = batch["min_count"].to(
            device=include_logits.device, dtype=torch.int64
        )[is_multi]
        maximum = batch["max_count"].to(
            device=include_logits.device, dtype=torch.int64
        )[is_multi]

        # This is the batched equivalent of actions.select_options:
        # threshold include probabilities at 0.5, prune highest-probability
        # selections to maxCount, or add highest-probability live options to
        # minCount. Stable sorting preserves the serving tie-break by index.
        probabilities = torch.sigmoid(include_logits)
        chosen = (include_logits >= 0) & live
        chosen_count = chosen.sum(dim=1)
        rank_slots = torch.arange(
            include_logits.shape[1], device=include_logits.device
        ).expand_as(include_logits)

        chosen_order = torch.argsort(
            probabilities.masked_fill(~chosen, -float("inf")),
            dim=1,
            descending=True,
            stable=True,
        )
        chosen_rank = torch.empty_like(chosen_order)
        chosen_rank.scatter_(1, chosen_order, rank_slots)
        pruned = chosen & (chosen_rank < maximum.unsqueeze(1))

        remaining = live & ~chosen
        remaining_order = torch.argsort(
            probabilities.masked_fill(~remaining, -float("inf")),
            dim=1,
            descending=True,
            stable=True,
        )
        remaining_rank = torch.empty_like(remaining_order)
        remaining_rank.scatter_(1, remaining_order, rank_slots)
        needed = (minimum - chosen_count).clamp(min=0)
        expanded = chosen | (remaining & (remaining_rank < needed.unsqueeze(1)))

        predicted = torch.where(
            (chosen_count > maximum).unsqueeze(1),
            pruned,
            torch.where(
                (chosen_count < minimum).unsqueeze(1), expanded, chosen
            ),
        )
        predicted &= live
        predicted_count = predicted.sum(dim=1)
        expected_count = targets.sum(dim=1)
        exact = (predicted == targets).all(dim=1)
        true_positive = (predicted & targets).sum()
        false_positive = (predicted & ~targets & live).sum()
        false_negative = (~predicted & targets).sum()

        result["multi_exact_correct"] = int(exact.sum().item())
        result["multi_selected_count_correct"] = int(
            (predicted_count == expected_count).sum().item()
        )
        result["multi_cardinality_valid"] = int(
            (
                (predicted_count >= minimum)
                & (predicted_count <= maximum)
            ).sum().item()
        )
        result["multi_true_positive"] = int(true_positive.item())
        result["multi_false_positive"] = int(false_positive.item())
        result["multi_false_negative"] = int(false_negative.item())
    return result
