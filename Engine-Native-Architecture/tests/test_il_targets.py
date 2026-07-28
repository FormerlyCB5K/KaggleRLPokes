from __future__ import annotations

import numpy as np
import pytest

from engine_native_policy import encode, featurize
from engine_native_policy.il.targets import TargetContractError, build_target

from helpers import sample_deck, sample_observation


def _inputs(max_count: int = 2):
    observation = sample_observation(max_count=max_count)
    flat = encode(featurize(observation, sample_deck()))
    return observation.select, flat


def test_one_selected_option_under_multi_prompt_remains_multi() -> None:
    select, flat = _inputs(max_count=2)
    target = build_target([1], select, flat)
    assert target.is_multi
    assert target.single_target == -100
    assert np.flatnonzero(target.multi_target).tolist() == [1]


def test_multi_target_preserves_every_selected_index() -> None:
    select, flat = _inputs(max_count=3)
    target = build_target([3, 1], select, flat)
    assert np.flatnonzero(target.multi_target).tolist() == [1, 3]
    assert target.selected_count == 2


@pytest.mark.parametrize(
    ("action", "message"),
    [
        ([1, 1], "unique"),
        ([99], "not all live"),
        ([], "violates"),
        ([0, 1, 2], "violates"),
    ],
)
def test_invalid_multi_targets_fail_loudly(action, message) -> None:
    select, flat = _inputs(max_count=2)
    with pytest.raises(TargetContractError, match=message):
        build_target(action, select, flat)


def test_source_encoded_option_disagreement_fails() -> None:
    select, flat = _inputs(max_count=1)
    flat = flat.copy()
    flat[1918] = 4
    with pytest.raises(TargetContractError, match="disagreement"):
        build_target([0], select, flat)
