"""Memory-mapped tensor shards and deterministic shard-aware batching."""

from __future__ import annotations

import bisect
import json
import random
from collections import OrderedDict
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset, Sampler

from .cache import (
    CacheContractError,
    SCHEMA_NAME,
    sha256_file,
    validate_shard_payload,
)


class ShardDataset(Dataset[dict[str, torch.Tensor]]):
    """Global row view over one cache split, with a small mmap shard LRU."""

    def __init__(
        self,
        root: str | Path,
        split: str,
        *,
        verify_hashes: bool = True,
        max_open_shards: int = 2,
    ) -> None:
        if split not in ("train", "validation"):
            raise ValueError("split must be 'train' or 'validation'")
        if max_open_shards <= 0:
            raise ValueError("max_open_shards must be positive")
        self.root = Path(root)
        self.split = split
        self.verify_hashes = verify_hashes
        self.max_open_shards = max_open_shards
        manifest_path = self.root / "manifest.json"
        if not manifest_path.is_file():
            raise CacheContractError(f"missing cache manifest: {manifest_path}")
        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if self.manifest.get("schema") != SCHEMA_NAME:
            raise CacheContractError(
                f"unsupported cache schema: {self.manifest.get('schema')}"
            )
        required_files = {
            "split.json": self.manifest["files"]["split_sha256"],
            "episode-table.json": self.manifest["files"][
                "episode_table_sha256"
            ],
        }
        for filename, expected_hash in required_files.items():
            path = self.root / filename
            if not path.is_file() or sha256_file(path) != expected_hash:
                raise CacheContractError(f"{filename} hash mismatch")
        self.shards = [
            item
            for item in self.manifest["shards"]
            if item["path"].startswith(f"{split}/")
        ]
        if not self.shards:
            raise CacheContractError(f"cache contains no {split} shards")
        self.offsets = [0]
        for shard in self.shards:
            self.offsets.append(self.offsets[-1] + int(shard["rows"]))
        self._cache: OrderedDict[int, dict[str, torch.Tensor]] = OrderedDict()
        self._verified: set[int] = set()

    def __len__(self) -> int:
        return self.offsets[-1]

    @property
    def shard_ranges(self) -> tuple[tuple[int, int], ...]:
        return tuple(zip(self.offsets[:-1], self.offsets[1:]))

    def _load(self, shard_index: int) -> dict[str, torch.Tensor]:
        if shard_index in self._cache:
            payload = self._cache.pop(shard_index)
            self._cache[shard_index] = payload
            return payload

        metadata = self.shards[shard_index]
        path = self.root / metadata["path"]
        if not path.is_file() or path.stat().st_size != metadata["bytes"]:
            raise CacheContractError(f"missing or size-mismatched shard: {path}")
        if self.verify_hashes and shard_index not in self._verified:
            if sha256_file(path) != metadata["sha256"]:
                raise CacheContractError(f"shard SHA-256 mismatch: {path}")
            self._verified.add(shard_index)
        payload = torch.load(
            path, map_location="cpu", weights_only=True, mmap=True
        )
        validate_shard_payload(payload, expected_rows=metadata["rows"])
        self._cache[shard_index] = payload
        while len(self._cache) > self.max_open_shards:
            self._cache.popitem(last=False)
        return payload

    def _locate(self, index: int) -> tuple[int, int]:
        if index < 0:
            index += len(self)
        if index < 0 or index >= len(self):
            raise IndexError(index)
        shard_index = bisect.bisect_right(self.offsets, index) - 1
        return shard_index, index - self.offsets[shard_index]

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        shard_index, row = self._locate(index)
        payload = self._load(shard_index)
        return {name: value[row] for name, value in payload.items()}

    def __getitems__(self, indices: list[int]) -> list[dict[str, torch.Tensor]]:
        if not indices:
            return []
        located = [self._locate(index) for index in indices]
        shard_indices = {item[0] for item in located}
        if len(shard_indices) != 1:
            return [self[index] for index in indices]
        shard_index = located[0][0]
        payload = self._load(shard_index)
        rows = torch.tensor([item[1] for item in located], dtype=torch.int64)
        sliced = {name: value[rows] for name, value in payload.items()}
        return [
            {name: value[row] for name, value in sliced.items()}
            for row in range(len(indices))
        ]


class ShardBatchSampler(Sampler[list[int]]):
    """Shuffle shards and their rows without random mmap thrashing."""

    def __init__(
        self,
        dataset: ShardDataset,
        *,
        batch_size: int,
        shuffle: bool,
        seed: int,
        drop_last: bool = False,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.dataset = dataset
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.seed = seed
        self.drop_last = drop_last
        self.epoch = 0

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __iter__(self) -> Iterator[list[int]]:
        generator = torch.Generator()
        generator.manual_seed(self.seed + self.epoch)
        shard_order = list(range(len(self.dataset.shard_ranges)))
        if self.shuffle:
            shard_order = torch.randperm(
                len(shard_order), generator=generator
            ).tolist()
        for shard_index in shard_order:
            start, end = self.dataset.shard_ranges[shard_index]
            count = end - start
            if self.shuffle:
                rows = torch.randperm(count, generator=generator).tolist()
            else:
                rows = list(range(count))
            for offset in range(0, count, self.batch_size):
                batch = rows[offset : offset + self.batch_size]
                if len(batch) < self.batch_size and self.drop_last:
                    continue
                yield [start + row for row in batch]

    def __len__(self) -> int:
        total = 0
        for start, end in self.dataset.shard_ranges:
            count = end - start
            if self.drop_last:
                total += count // self.batch_size
            else:
                total += (count + self.batch_size - 1) // self.batch_size
        return total


def _seed_worker(worker_id: int) -> None:
    seed = torch.initial_seed() % (2**32)
    np.random.seed(seed)
    random.seed(seed)


def make_dataloader(
    root: str | Path,
    split: str,
    *,
    batch_size: int,
    num_workers: int,
    seed: int,
    device: str | torch.device = "cpu",
    verify_hashes: bool = True,
    drop_last: bool = False,
) -> tuple[DataLoader, ShardBatchSampler]:
    dataset = ShardDataset(
        root, split, verify_hashes=verify_hashes
    )
    sampler = ShardBatchSampler(
        dataset,
        batch_size=batch_size,
        shuffle=split == "train",
        seed=seed,
        drop_last=drop_last,
    )
    generator = torch.Generator()
    generator.manual_seed(seed)
    pin_memory = torch.device(device).type == "cuda"
    loader = DataLoader(
        dataset,
        batch_sampler=sampler,
        num_workers=num_workers,
        pin_memory=pin_memory,
        persistent_workers=num_workers > 0,
        worker_init_fn=_seed_worker,
        generator=generator,
    )
    return loader, sampler
