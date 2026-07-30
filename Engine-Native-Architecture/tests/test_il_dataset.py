from __future__ import annotations

import torch

from engine_native_policy.il.dataset import (
    ShardBatchSampler,
    ShardDataset,
    make_dataloader,
)

from il_helpers import build_test_cache


def test_dataset_dtypes_shapes_and_last_partial_batch(tmp_path) -> None:
    _, output = build_test_cache(tmp_path)
    loader, _ = make_dataloader(
        output,
        "validation",
        batch_size=3,
        num_workers=0,
        seed=123,
        verify_hashes=True,
    )
    batches = list(loader)
    assert [batch["features"].shape[0] for batch in batches] == [3, 3]
    first = batches[0]
    assert first["features"].shape == (3, 2239)
    assert first["features"].dtype == torch.float32
    assert first["is_multi"].dtype == torch.bool
    assert first["single_target"].dtype == torch.int64
    assert first["multi_target"].shape == (3, 64)
    assert first["value_target"].shape == (3,)
    assert first["value_target"].dtype == torch.float32
    assert first["origin"].shape == (3, 3)


def test_train_sampler_is_seeded_and_validation_order_is_fixed(tmp_path) -> None:
    _, output = build_test_cache(tmp_path)
    train = ShardDataset(output, "train", verify_hashes=False)
    left = ShardBatchSampler(
        train, batch_size=4, shuffle=True, seed=99
    )
    right = ShardBatchSampler(
        train, batch_size=4, shuffle=True, seed=99
    )
    assert list(left) == list(right)
    left.set_epoch(1)
    assert list(left) != list(right)

    validation = ShardDataset(output, "validation", verify_hashes=False)
    fixed = ShardBatchSampler(
        validation, batch_size=4, shuffle=False, seed=1
    )
    fixed.set_epoch(10)
    assert list(fixed) == [list(range(4)), list(range(4, len(validation)))]


def test_train_sampler_resumes_without_yielding_prior_batches(tmp_path) -> None:
    _, output = build_test_cache(tmp_path)
    train = ShardDataset(output, "train", verify_hashes=False)
    sampler = ShardBatchSampler(
        train, batch_size=2, shuffle=True, seed=99
    )
    complete = list(sampler)
    sampler.set_start_batch(2)
    assert len(sampler) == len(complete) - 2
    assert list(sampler) == complete[2:]
    sampler.set_epoch(1)
    assert sampler.start_batch == 0


def test_mixed_batch_contains_single_and_multi_rows(tmp_path) -> None:
    _, output = build_test_cache(tmp_path)
    loader, _ = make_dataloader(
        output,
        "validation",
        batch_size=4,
        num_workers=0,
        seed=123,
        verify_hashes=False,
    )
    batch = next(iter(loader))
    assert set(batch["is_multi"].tolist()) == {False, True}
