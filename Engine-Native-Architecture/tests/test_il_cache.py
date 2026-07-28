from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from engine_native_policy.il.cache import (
    CacheContractError,
    SHARD_DTYPES,
    build_cache,
    verify_cache,
)

from il_helpers import build_test_cache


def test_cache_build_split_manifest_and_exact_reuse(tmp_path) -> None:
    source, output = build_test_cache(tmp_path)
    manifest = verify_cache(output)
    split = json.loads((output / "split.json").read_text())

    assert not set(split["train"]) & set(split["validation"])
    assert len(split["train"]) == 3
    assert len(split["validation"]) == 1
    assert manifest["totals"]["examples"] == 16
    assert manifest["totals"]["single"] == 8
    assert manifest["totals"]["multi"] == 8
    assert set(manifest["skip_counts_by_day"]["7-12"]) == {
        "no_action",
        "no_current",
        "no_select",
        "unusable",
        "fewer_than_two_options",
        "option_overflow",
    }

    first_shard = output / manifest["shards"][0]["path"]
    payload = torch.load(
        first_shard, map_location="cpu", weights_only=True, mmap=True
    )
    assert set(payload) == set(SHARD_DTYPES)
    assert payload["features"].dtype == torch.float32
    assert payload["multi_target"].dtype == torch.bool
    assert payload["origin"].dtype == torch.int32

    project_artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    reused = build_cache(
        sanitized_root=source,
        output_root=output,
        days=("7-12",),
        validation_fraction=0.25,
        seed=20260728,
        target_shard_rows=3,
        workers=1,
        tables_path=project_artifacts / "frozen_tables.pt",
        artifact_manifest_path=project_artifacts / "installed-manifest.json",
    )
    assert reused["build"]["started_utc"] == manifest["build"]["started_utc"]


def test_changed_source_cannot_silently_reuse_cache(tmp_path) -> None:
    source, output = build_test_cache(tmp_path)
    episode = source / "7-12" / "00000000.json"
    episode.write_text(episode.read_text() + " ", encoding="utf-8")
    project_artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    with pytest.raises(CacheContractError, match="identity differs"):
        build_cache(
            sanitized_root=source,
            output_root=output,
            days=("7-12",),
            validation_fraction=0.25,
            seed=20260728,
            target_shard_rows=3,
            workers=1,
            tables_path=project_artifacts / "frozen_tables.pt",
            artifact_manifest_path=project_artifacts / "installed-manifest.json",
        )


def test_corrupt_shard_hash_fails_verification(tmp_path) -> None:
    _, output = build_test_cache(tmp_path)
    manifest = json.loads((output / "manifest.json").read_text())
    shard = output / manifest["shards"][0]["path"]
    with shard.open("ab") as handle:
        handle.write(b"corrupt")
    with pytest.raises(CacheContractError, match="size-mismatched"):
        verify_cache(output)
