from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
import torch

from engine_native_policy.il.cache import (
    CacheContractError,
    SHARD_DTYPES,
    build_cache,
    verify_cache,
)
from top_ladder_sanitization import mask_episode, sanitize_member

from il_helpers import build_test_cache, sample_episode


def _write_raw_and_sanitized_equivalent(
    root: Path, *, episodes_per_day: int = 4
) -> tuple[Path, Path]:
    day = "7-12"
    raw_root = root / "raw"
    raw_day = raw_root / day
    raw_day.mkdir(parents=True)
    archive = raw_day / "pokemon-tcg-ai-battle-episodes-2026-07-12.zip"

    members: dict[str, bytes] = {}
    accepted: list[tuple[str, dict]] = []
    steps_total = 0
    steps_usable = 0
    steps_masked = 0
    for index in range(episodes_per_day):
        episode = sample_episode(index)
        for step in episode["steps"]:
            for entry in step:
                observation = entry.get("observation")
                if isinstance(observation, dict):
                    select = observation.get("select")
                    if isinstance(select, dict):
                        select.pop("usable", None)
        for entry in episode["steps"][2]:
            select = entry["observation"]["select"]
            select["option"] = select["option"][:1]
        filename = f"{index:08d}.json"
        raw = json.dumps(episode).encode("utf-8")
        members[filename] = raw
        sanitized, exclusion = sanitize_member(raw)
        assert exclusion is None and sanitized is not None
        counts = mask_episode(sanitized)
        steps_total += counts[0]
        steps_usable += counts[1]
        steps_masked += counts[2]
        accepted.append((filename, sanitized))

    non_done = sample_episode(99)
    non_done["statuses"] = ["DONE", "ERROR"]
    members["non-done.json"] = json.dumps(non_done).encode("utf-8")
    members["malformed.json"] = b"{"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for filename, raw in members.items():
            bundle.writestr(filename, raw)

    sanitized_root = root / "sanitized"
    sanitized_day = sanitized_root / day
    sanitized_day.mkdir(parents=True)
    for filename, episode in accepted:
        (sanitized_day / filename).write_text(
            json.dumps(episode), encoding="utf-8"
        )
    report = {
        "day": day,
        "total_episodes_seen": len(members),
        "excluded": [
            {
                "episode_id": "malformed",
                "day": day,
                "reason": "malformed_json",
            },
            {
                "episode_id": "non-done",
                "day": day,
                "reason": "non_done_status",
                "statuses": ["DONE", "ERROR"],
            },
        ],
        "episodes_written": episodes_per_day,
        "steps_total": steps_total,
        "steps_usable": steps_usable,
        "steps_masked": steps_masked,
        "source_archive": str(archive),
    }
    (sanitized_day / "report.json").write_text(
        json.dumps(report), encoding="utf-8"
    )
    return raw_root, sanitized_root


def _split_payload(root: Path, manifest: dict, split: str) -> dict[str, torch.Tensor]:
    payloads = [
        torch.load(
            root / shard["path"],
            map_location="cpu",
            weights_only=True,
        )
        for shard in manifest["shards"]
        if shard["path"].startswith(f"{split}/")
    ]
    return {
        key: torch.cat([payload[key] for payload in payloads], dim=0)
        for key in SHARD_DTYPES
    }


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


def test_raw_zip_mode_matches_loose_sanitized_cache(tmp_path) -> None:
    raw_root, sanitized_root = _write_raw_and_sanitized_equivalent(tmp_path)
    artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    common = {
        "days": ("7-12",),
        "validation_fraction": 0.25,
        "seed": 20260728,
        "target_shard_rows": 3,
        "tables_path": artifacts / "frozen_tables.pt",
        "artifact_manifest_path": artifacts / "installed-manifest.json",
    }
    raw_output = tmp_path / "raw-cache"
    raw_manifest = build_cache(
        sanitized_root=None,
        raw_root=raw_root,
        output_root=raw_output,
        workers=2,
        **common,
    )
    sanitized_output = tmp_path / "sanitized-cache"
    sanitized_manifest = build_cache(
        sanitized_root=sanitized_root,
        output_root=sanitized_output,
        workers=1,
        **common,
    )

    assert raw_manifest["source"]["mode"] == "raw_zip"
    assert raw_manifest["source"]["reports"]["7-12"]["excluded_count"] == 2
    report_path = raw_output / "sanitization-reports" / "7-12.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert {item["reason"] for item in report["excluded"]} == {
        "malformed_json",
        "non_done_status",
    }
    assert not list(raw_root.rglob("*.json"))
    assert json.loads((raw_output / "split.json").read_text())["train"] == json.loads(
        (sanitized_output / "split.json").read_text()
    )["train"]
    assert raw_manifest["totals"] == sanitized_manifest["totals"]
    for split in ("train", "validation"):
        raw_payload = _split_payload(raw_output, raw_manifest, split)
        sanitized_payload = _split_payload(
            sanitized_output, sanitized_manifest, split
        )
        for key in SHARD_DTYPES:
            assert torch.equal(raw_payload[key], sanitized_payload[key]), key
    verify_cache(raw_output)
    report_path.write_text(report_path.read_text() + " ", encoding="utf-8")
    with pytest.raises(
        CacheContractError, match="sanitization report SHA-256 mismatch"
    ):
        verify_cache(raw_output)
