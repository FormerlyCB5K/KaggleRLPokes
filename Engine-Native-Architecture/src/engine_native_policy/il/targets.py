"""Validated single- and multi-selection labels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from ..flat import FIELD_OFFSETS, FLAT_DIM
from ..spec import MAX_OPTIONS


class TargetContractError(ValueError):
    """A replay label does not match its legal-option list."""


@dataclass(frozen=True)
class DecisionTarget:
    is_multi: bool
    single_target: int
    multi_target: np.ndarray
    n_options: int
    min_count: int
    max_count: int
    selected_count: int


def _integer(value: Any, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TargetContractError(f"{name} must be an integer, got {value!r}")
    return value


def build_target(
    action: tuple[int, ...] | list[int],
    select: Any,
    encoded_features: np.ndarray,
) -> DecisionTarget:
    """Validate one complete recorded action and construct its tensor targets."""

    flat = np.asarray(encoded_features)
    if flat.shape != (FLAT_DIM,) or flat.dtype != np.float32:
        raise TargetContractError(
            f"features must be float32[{FLAT_DIM}], got {flat.dtype}{flat.shape}"
        )

    options = getattr(select, "option", None)
    if not isinstance(options, list):
        raise TargetContractError("select.option must be a list")
    n_options = len(options)
    if not 1 <= n_options <= MAX_OPTIONS:
        raise TargetContractError(f"n_options must be in [1, {MAX_OPTIONS}], got {n_options}")

    selected = tuple(
        _integer(value, name=f"selected[{index}]")
        for index, value in enumerate(action)
    )
    if len(selected) != len(set(selected)):
        raise TargetContractError(f"selected indices must be unique, got {selected}")
    if any(index < 0 or index >= n_options for index in selected):
        raise TargetContractError(
            f"selected indices {selected} are not all live for {n_options} options"
        )

    minimum = _integer(getattr(select, "minCount", None), name="minCount")
    maximum = _integer(getattr(select, "maxCount", None), name="maxCount")
    if minimum < 0 or maximum < minimum or maximum > n_options:
        raise TargetContractError(
            f"invalid selection bounds min={minimum} max={maximum} n={n_options}"
        )

    is_multi = maximum > 1
    if is_multi:
        if not minimum <= len(selected) <= maximum:
            raise TargetContractError(
                f"multi action length {len(selected)} violates [{minimum}, {maximum}]"
            )
    elif len(selected) != 1:
        raise TargetContractError(
            f"single selection requires one selected index, got {selected}"
        )

    n_start, _ = FIELD_OFFSETS["n_options"]
    mask_start, mask_end = FIELD_OFFSETS["opt_mask"]
    encoded_n = int(flat[n_start])
    encoded_mask_count = int(flat[mask_start:mask_end].sum())
    if encoded_n != n_options or encoded_mask_count != n_options:
        raise TargetContractError(
            "source/encoded option disagreement: "
            f"source={n_options} encoded_n={encoded_n} mask={encoded_mask_count}"
        )

    multi_target = np.zeros(MAX_OPTIONS, dtype=np.bool_)
    single_target = -100
    if is_multi:
        multi_target[list(selected)] = True
    else:
        single_target = selected[0]

    return DecisionTarget(
        is_multi=is_multi,
        single_target=single_target,
        multi_target=multi_target,
        n_options=n_options,
        min_count=minimum,
        max_count=maximum,
        selected_count=len(selected),
    )
