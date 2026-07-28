"""Deterministic inventory, splitting, tensor sharding, and cache verification."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import random
import socket
import subprocess
import time
import uuid
from collections import Counter, defaultdict, deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from cg_download.api import Observation
from cg_download.utils import to_dataclass

from ..featurize import featurize
from ..flat import FIELD_OFFSETS, FLAT_DIM, encode
from ..spec import FEATURIZER_VERSION, MAX_OPTIONS, MAX_TOKENS
from ..tables import FrozenTables
from .replay import (
    DECLARED_SKIP_REASONS,
    ReplayContractError,
    iter_episode_decisions,
    validate_skip_counts,
)
from .targets import TargetContractError, build_target


SCHEMA_NAME = "engine-native-il-v1"
SPLIT_SCHEMA_VERSION = 1
DEFAULT_DAYS = ("7-12", "7-13", "7-14", "7-23", "7-24", "7-25")
DEFAULT_SEED = 20260728
DEFAULT_VALIDATION_FRACTION = 0.10
DEFAULT_TARGET_SHARD_ROWS = 8192

SHARD_DTYPES: dict[str, torch.dtype] = {
    "features": torch.float32,
    "is_multi": torch.bool,
    "single_target": torch.int64,
    "multi_target": torch.bool,
    "n_options": torch.uint8,
    "min_count": torch.uint8,
    "max_count": torch.uint8,
    "origin": torch.int32,
}
SHARD_WIDTHS: dict[str, tuple[int, ...]] = {
    "features": (FLAT_DIM,),
    "is_multi": (),
    "single_target": (),
    "multi_target": (MAX_OPTIONS,),
    "n_options": (),
    "min_count": (),
    "max_count": (),
    "origin": (3,),
}


class CacheContractError(RuntimeError):
    """The cache, source inventory, or artifact set is inconsistent."""


@dataclass(frozen=True)
class SourceEpisode:
    day: str
    filename: str
    path: str
    size: int

    @property
    def key(self) -> str:
        return f"{self.day}/{self.filename}"


@dataclass
class EpisodeRows:
    key: str
    episode_index: int
    arrays: dict[str, np.ndarray]
    skip_counts: dict[str, int]
    histograms: dict[str, dict[int, int]]
    single_count: int
    multi_count: int
    entity_overflow_count: int

    @property
    def n_rows(self) -> int:
        return int(self.arrays["features"].shape[0])


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def validate_artifact_manifest(path: str | Path) -> str:
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema") != "engine-native-reference-artifacts-v1":
        raise CacheContractError(f"unsupported artifact manifest: {manifest_path}")
    root = manifest_path.parent
    for item in payload.get("files", []):
        artifact = root / item["path"]
        if not artifact.is_file():
            raise CacheContractError(f"missing reference artifact: {artifact}")
        if artifact.stat().st_size != item["size"]:
            raise CacheContractError(f"artifact size mismatch: {artifact}")
        actual = sha256_file(artifact)
        if actual != item["sha256"]:
            raise CacheContractError(f"artifact SHA-256 mismatch: {artifact}")
    return sha256_file(manifest_path)


def validate_tables_against_manifest(
    tables_path: str | Path, manifest_path: str | Path
) -> None:
    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    matches = [
        item
        for item in payload.get("files", [])
        if item.get("path") == "frozen_tables.pt"
    ]
    if len(matches) != 1:
        raise CacheContractError(
            "artifact manifest must contain exactly one frozen_tables.pt"
        )
    expected = matches[0]
    tables = Path(tables_path)
    if not tables.is_file():
        raise CacheContractError(f"missing frozen tables: {tables}")
    if tables.stat().st_size != expected["size"]:
        raise CacheContractError("frozen table size does not match artifact manifest")
    if sha256_file(tables) != expected["sha256"]:
        raise CacheContractError("frozen table SHA-256 does not match artifact manifest")
    FrozenTables.load(tables)


def inventory_source(
    sanitized_root: str | Path,
    days: tuple[str, ...] | list[str],
    *,
    max_episodes: int | None = None,
) -> tuple[list[SourceEpisode], dict[str, Any], int]:
    root = Path(sanitized_root).resolve()
    episodes: list[SourceEpisode] = []
    reports: dict[str, Any] = {}
    full_count = 0

    for day in days:
        day_dir = root / day
        if not day_dir.is_dir():
            raise CacheContractError(f"missing sanitized day directory: {day_dir}")
        report_path = day_dir / "report.json"
        if not report_path.is_file():
            raise CacheContractError(f"missing sanitization report: {report_path}")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        files = sorted(
            path
            for path in day_dir.glob("*.json")
            if path.name != "report.json" and path.is_file()
        )
        if not files:
            raise CacheContractError(f"sanitized day contains no episodes: {day_dir}")
        reported = report.get("episodes_written")
        if reported is not None and int(reported) != len(files):
            raise CacheContractError(
                f"{day}: report says {reported} episodes, discovered {len(files)}"
            )
        reports[day] = {
            "path": str(report_path),
            "sha256": sha256_file(report_path),
            "episodes_written": len(files),
            "total_episodes_seen": report.get("total_episodes_seen"),
            "steps_total": report.get("steps_total"),
            "steps_usable": report.get("steps_usable"),
            "steps_masked": report.get("steps_masked"),
            "excluded_count": len(report.get("excluded") or []),
            "source_archive": report.get("source_archive"),
        }
        full_count += len(files)
        episodes.extend(
            SourceEpisode(
                day=day,
                filename=path.name,
                path=str(path),
                size=path.stat().st_size,
            )
            for path in files
        )

    episodes.sort(key=lambda item: item.key)
    if max_episodes is not None:
        if max_episodes <= 0:
            raise CacheContractError("max_episodes must be positive")
        episodes = episodes[:max_episodes]
    if not episodes:
        raise CacheContractError("source inventory is empty")
    return episodes, reports, full_count


def source_inventory_hash(episodes: list[SourceEpisode]) -> str:
    return _canonical_hash(
        [[item.day, item.filename, item.size] for item in episodes]
    )


def make_split(
    episodes: list[SourceEpisode],
    *,
    source_hash: str,
    seed: int,
    validation_fraction: float,
) -> dict[str, Any]:
    if not 0.0 < validation_fraction < 1.0:
        raise CacheContractError("validation_fraction must be between zero and one")
    keys = [item.key for item in episodes]
    shuffled = list(keys)
    random.Random(seed).shuffle(shuffled)
    n_validation = max(1, round(validation_fraction * len(shuffled)))
    validation = sorted(shuffled[:n_validation])
    training = sorted(shuffled[n_validation:])
    if not training:
        raise CacheContractError("split leaves no training episodes")
    logical = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "seed": seed,
        "validation_fraction": validation_fraction,
        "source_inventory_hash": source_hash,
        "train": training,
        "validation": validation,
    }
    logical["split_hash"] = _canonical_hash(logical)
    return logical


def _empty_arrays() -> dict[str, np.ndarray]:
    return {
        "features": np.empty((0, FLAT_DIM), dtype=np.float32),
        "is_multi": np.empty((0,), dtype=np.bool_),
        "single_target": np.empty((0,), dtype=np.int64),
        "multi_target": np.empty((0, MAX_OPTIONS), dtype=np.bool_),
        "n_options": np.empty((0,), dtype=np.uint8),
        "min_count": np.empty((0,), dtype=np.uint8),
        "max_count": np.empty((0,), dtype=np.uint8),
        "origin": np.empty((0, 3), dtype=np.int32),
    }


def _process_episode(job: tuple[SourceEpisode, int]) -> EpisodeRows:
    source, episode_index = job
    try:
        with Path(source.path).open("rb") as handle:
            episode = json.load(handle)
        if not isinstance(episode, dict):
            raise ReplayContractError("episode root must be an object")

        skip_counts: Counter[str] = Counter(
            {reason: 0 for reason in DECLARED_SKIP_REASONS}
        )
        columns: dict[str, list[Any]] = {key: [] for key in SHARD_DTYPES}
        histograms = {
            "n_options": Counter(),
            "min_count": Counter(),
            "max_count": Counter(),
            "selected_count": Counter(),
        }
        single_count = 0
        multi_count = 0
        entity_overflow_count = 0

        for decision in iter_episode_decisions(
            episode, skip_counts=skip_counts
        ):
            observation = to_dataclass(decision.observation_json, Observation)
            frame = featurize(observation, decision.deck)
            entity_overflow_count += int(frame.n_entities > MAX_TOKENS)
            flat = encode(frame)
            target = build_target(decision.action, observation.select, flat)

            columns["features"].append(flat)
            columns["is_multi"].append(target.is_multi)
            columns["single_target"].append(target.single_target)
            columns["multi_target"].append(target.multi_target)
            columns["n_options"].append(target.n_options)
            columns["min_count"].append(target.min_count)
            columns["max_count"].append(target.max_count)
            columns["origin"].append(
                [episode_index, decision.player, decision.response_step]
            )
            single_count += int(not target.is_multi)
            multi_count += int(target.is_multi)
            histograms["n_options"][target.n_options] += 1
            histograms["min_count"][target.min_count] += 1
            histograms["max_count"][target.max_count] += 1
            histograms["selected_count"][target.selected_count] += 1

        validate_skip_counts(skip_counts)
        if not columns["features"]:
            arrays = _empty_arrays()
        else:
            arrays = {
                "features": np.stack(columns["features"]).astype(
                    np.float32, copy=False
                ),
                "is_multi": np.asarray(columns["is_multi"], dtype=np.bool_),
                "single_target": np.asarray(
                    columns["single_target"], dtype=np.int64
                ),
                "multi_target": np.stack(columns["multi_target"]).astype(
                    np.bool_, copy=False
                ),
                "n_options": np.asarray(columns["n_options"], dtype=np.uint8),
                "min_count": np.asarray(columns["min_count"], dtype=np.uint8),
                "max_count": np.asarray(columns["max_count"], dtype=np.uint8),
                "origin": np.asarray(columns["origin"], dtype=np.int32),
            }
        return EpisodeRows(
            key=source.key,
            episode_index=episode_index,
            arrays=arrays,
            skip_counts=dict(skip_counts),
            histograms={
                name: dict(counter) for name, counter in histograms.items()
            },
            single_count=single_count,
            multi_count=multi_count,
            entity_overflow_count=entity_overflow_count,
        )
    except (ReplayContractError, TargetContractError, OSError, ValueError) as exc:
        raise CacheContractError(f"{source.key}: {exc}") from exc


def _process_jobs(
    jobs: list[tuple[SourceEpisode, int]], workers: int
):
    """Yield ordered worker results with bounded in-flight episode payloads."""

    if workers == 1:
        yield from map(_process_episode, jobs)
        return
    with ProcessPoolExecutor(max_workers=workers) as executor:
        pending = deque()
        job_iter = iter(jobs)
        for _ in range(min(len(jobs), workers * 2)):
            pending.append(executor.submit(_process_episode, next(job_iter)))
        while pending:
            future = pending.popleft()
            yield future.result()
            try:
                job = next(job_iter)
            except StopIteration:
                continue
            pending.append(executor.submit(_process_episode, job))


def validate_shard_payload(payload: Any, *, expected_rows: int | None = None) -> int:
    if not isinstance(payload, dict) or set(payload) != set(SHARD_DTYPES):
        raise CacheContractError(
            f"shard keys must be exactly {sorted(SHARD_DTYPES)}"
        )
    rows: int | None = None
    for name, dtype in SHARD_DTYPES.items():
        value = payload[name]
        if not isinstance(value, torch.Tensor):
            raise CacheContractError(f"{name} is not a tensor")
        if value.dtype != dtype:
            raise CacheContractError(
                f"{name}: expected {dtype}, got {value.dtype}"
            )
        if rows is None:
            rows = int(value.shape[0])
        if int(value.shape[0]) != rows:
            raise CacheContractError(f"{name}: row-count mismatch")
        if tuple(value.shape[1:]) != SHARD_WIDTHS[name]:
            raise CacheContractError(
                f"{name}: expected trailing shape {SHARD_WIDTHS[name]}, "
                f"got {tuple(value.shape[1:])}"
            )
    assert rows is not None
    if expected_rows is not None and rows != expected_rows:
        raise CacheContractError(
            f"shard expected {expected_rows} rows, contains {rows}"
        )
    features = payload["features"]
    n_options = payload["n_options"].to(torch.int64)
    minimum = payload["min_count"].to(torch.int64)
    maximum = payload["max_count"].to(torch.int64)
    is_multi = payload["is_multi"]
    if not bool(((n_options >= 2) & (n_options <= MAX_OPTIONS)).all()):
        raise CacheContractError("shard contains invalid n_options")
    if not bool(((minimum >= 0) & (minimum <= maximum) & (maximum <= n_options)).all()):
        raise CacheContractError("shard contains invalid cardinality bounds")
    if not torch.equal(is_multi, maximum > 1):
        raise CacheContractError("is_multi disagrees with max_count")

    n_start, _ = FIELD_OFFSETS["n_options"]
    mask_start, mask_end = FIELD_OFFSETS["opt_mask"]
    encoded_n = features[:, n_start].to(torch.int64)
    encoded_mask_count = features[:, mask_start:mask_end].sum(dim=1).to(torch.int64)
    if not torch.equal(encoded_n, n_options) or not torch.equal(
        encoded_mask_count, n_options
    ):
        raise CacheContractError("cached feature option counts disagree with targets")

    single = ~is_multi
    if bool(single.any()):
        single_target = payload["single_target"][single]
        if not bool(
            ((single_target >= 0) & (single_target < n_options[single])).all()
        ):
            raise CacheContractError("shard contains an invalid single target")
        if bool(payload["multi_target"][single].any()):
            raise CacheContractError("single rows must have empty multi targets")
    if bool(is_multi.any()):
        if not bool((payload["single_target"][is_multi] == -100).all()):
            raise CacheContractError("multi rows must use single_target=-100")
        selected_count = payload["multi_target"][is_multi].sum(dim=1).to(torch.int64)
        if not bool(
            (
                (selected_count >= minimum[is_multi])
                & (selected_count <= maximum[is_multi])
            ).all()
        ):
            raise CacheContractError("multi target violates cardinality bounds")
        option_positions = torch.arange(MAX_OPTIONS).unsqueeze(0)
        padded_selected = payload["multi_target"][is_multi] & (
            option_positions >= n_options[is_multi].unsqueeze(1)
        )
        if bool(padded_selected.any()):
            raise CacheContractError("multi target selects a padded option")
    return rows


class _ShardWriter:
    def __init__(self, root: Path, split: str, target_rows: int) -> None:
        self.root = root
        self.split = split
        self.target_rows = target_rows
        self.directory = root / split
        self.directory.mkdir(parents=True, exist_ok=True)
        self.parts: dict[str, list[np.ndarray]] = {
            key: [] for key in SHARD_DTYPES
        }
        self.rows = 0
        self.index = 0
        self.metadata: list[dict[str, Any]] = []

    def add_episode(self, episode: EpisodeRows) -> None:
        if episode.n_rows == 0:
            return
        for key in self.parts:
            self.parts[key].append(episode.arrays[key])
        self.rows += episode.n_rows
        if self.rows >= self.target_rows:
            self.flush()

    def flush(self) -> None:
        if self.rows == 0:
            return
        payload = {
            key: torch.from_numpy(np.concatenate(values, axis=0))
            for key, values in self.parts.items()
        }
        validate_shard_payload(payload, expected_rows=self.rows)
        name = f"shard-{self.index:06d}.pt"
        final_path = self.directory / name
        temporary = self.directory / f".{name}.{uuid.uuid4().hex}.tmp"
        torch.save(payload, temporary)
        digest = sha256_file(temporary)
        size = temporary.stat().st_size
        os.replace(temporary, final_path)
        self.metadata.append(
            {
                "path": f"{self.split}/{name}",
                "rows": self.rows,
                "bytes": size,
                "sha256": digest,
            }
        )
        self.parts = {key: [] for key in SHARD_DTYPES}
        self.rows = 0
        self.index += 1


def _repository_state(repository_root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "-c", f"safe.directory={repository_root.as_posix()}", "rev-parse", "HEAD"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "-c", f"safe.directory={repository_root.as_posix()}", "status", "--porcelain"],
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return {"revision": revision, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"revision": None, "dirty": None}


def _merge_histogram(
    destination: Counter[int], source: dict[int, int]
) -> None:
    destination.update({int(key): int(value) for key, value in source.items()})


def _manifest_identity(
    *,
    source_hash: str,
    days: tuple[str, ...],
    seed: int,
    validation_fraction: float,
    target_shard_rows: int,
    max_episodes: int | None,
    artifact_manifest_hash: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_NAME,
        "source_inventory_hash": source_hash,
        "days": list(days),
        "seed": seed,
        "validation_fraction": validation_fraction,
        "target_shard_rows": target_shard_rows,
        "max_episodes": max_episodes,
        "featurizer_version": FEATURIZER_VERSION,
        "artifact_manifest_hash": artifact_manifest_hash,
    }


def verify_cache(root: str | Path, *, verify_hashes: bool = True) -> dict[str, Any]:
    cache_root = Path(root)
    manifest_path = cache_root / "manifest.json"
    if not manifest_path.is_file():
        raise CacheContractError(f"cache has no complete manifest: {cache_root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA_NAME:
        raise CacheContractError(f"unsupported cache schema: {manifest.get('schema')}")

    split_path = cache_root / "split.json"
    episode_path = cache_root / "episode-table.json"
    if sha256_file(split_path) != manifest["files"]["split_sha256"]:
        raise CacheContractError("split.json hash mismatch")
    if sha256_file(episode_path) != manifest["files"]["episode_table_sha256"]:
        raise CacheContractError("episode-table.json hash mismatch")

    split = json.loads(split_path.read_text(encoding="utf-8"))
    split_without_hash = dict(split)
    recorded_split_hash = split_without_hash.pop("split_hash", None)
    if recorded_split_hash != _canonical_hash(split_without_hash):
        raise CacheContractError("split logical hash mismatch")
    if recorded_split_hash != manifest["split"]["split_hash"]:
        raise CacheContractError("manifest/split hash disagreement")
    train_keys = set(split["train"])
    validation_keys = set(split["validation"])
    if train_keys & validation_keys:
        raise CacheContractError("train and validation episodes overlap")

    episode_table = json.loads(episode_path.read_text(encoding="utf-8"))
    episode_keys: list[str] = []
    for expected_index, item in enumerate(episode_table):
        if item.get("index") != expected_index:
            raise CacheContractError("episode table indices are not contiguous")
        episode_keys.append(f"{item['day']}/{item['filename']}")
    if train_keys | validation_keys != set(episode_keys):
        raise CacheContractError("split assignments do not match the episode table")

    total_rows = 0
    for shard in manifest["shards"]:
        path = cache_root / shard["path"]
        if not path.is_file() or path.stat().st_size != shard["bytes"]:
            raise CacheContractError(f"missing or size-mismatched shard: {path}")
        if verify_hashes and sha256_file(path) != shard["sha256"]:
            raise CacheContractError(f"shard SHA-256 mismatch: {path}")
        payload = torch.load(
            path, map_location="cpu", weights_only=True, mmap=True
        )
        total_rows += validate_shard_payload(
            payload, expected_rows=shard["rows"]
        )
        expected_keys = (
            train_keys if shard["path"].startswith("train/") else validation_keys
        )
        origins = payload["origin"]
        episode_indices = origins[:, 0].to(torch.int64)
        if not bool(
            ((episode_indices >= 0) & (episode_indices < len(episode_keys))).all()
        ):
            raise CacheContractError(f"invalid episode origin in {path}")
        if not bool(((origins[:, 1] == 0) | (origins[:, 1] == 1)).all()):
            raise CacheContractError(f"invalid player origin in {path}")
        if not bool((origins[:, 2] >= 1).all()):
            raise CacheContractError(f"invalid response-step origin in {path}")
        if any(
            episode_keys[index] not in expected_keys
            for index in episode_indices.unique().tolist()
        ):
            raise CacheContractError(f"shard mixes train/validation episodes: {path}")
    if total_rows != manifest["totals"]["examples"]:
        raise CacheContractError(
            f"manifest has {manifest['totals']['examples']} examples, shards have {total_rows}"
        )
    return manifest


def build_cache(
    *,
    sanitized_root: str | Path,
    output_root: str | Path,
    days: tuple[str, ...] = DEFAULT_DAYS,
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION,
    seed: int = DEFAULT_SEED,
    target_shard_rows: int = DEFAULT_TARGET_SHARD_ROWS,
    workers: int = 1,
    max_episodes: int | None = None,
    tables_path: str | Path,
    artifact_manifest_path: str | Path,
) -> dict[str, Any]:
    """Build or exactly reuse one immutable engine-native IL cache."""

    started = datetime.now(timezone.utc)
    started_clock = time.perf_counter()
    output = Path(output_root).resolve()
    source_root = Path(sanitized_root).resolve()
    if (
        output == source_root
        or output in source_root.parents
        or source_root in output.parents
    ):
        raise CacheContractError(
            "cache output and sanitized source directories must not overlap"
        )
    if target_shard_rows <= 0:
        raise CacheContractError("target_shard_rows must be positive")
    if workers <= 0:
        raise CacheContractError("workers must be positive")

    artifact_manifest_hash = validate_artifact_manifest(artifact_manifest_path)
    validate_tables_against_manifest(tables_path, artifact_manifest_path)
    episodes, report_summaries, full_inventory_count = inventory_source(
        source_root, days, max_episodes=max_episodes
    )
    inventory_hash = source_inventory_hash(episodes)
    identity = _manifest_identity(
        source_hash=inventory_hash,
        days=days,
        seed=seed,
        validation_fraction=validation_fraction,
        target_shard_rows=target_shard_rows,
        max_episodes=max_episodes,
        artifact_manifest_hash=artifact_manifest_hash,
    )

    if (output / "manifest.json").is_file():
        existing = verify_cache(output)
        if existing.get("identity") != identity:
            raise CacheContractError(
                f"existing cache identity differs; choose a new output: {output}"
            )
        return existing
    if output.exists() and not output.is_dir():
        raise CacheContractError(f"output path is not a directory: {output}")
    if output.exists() and any(output.iterdir()):
        raise CacheContractError(
            f"output is non-empty but not exactly reusable; choose a new output: {output}"
        )
    output.mkdir(parents=True, exist_ok=True)

    split = make_split(
        episodes,
        source_hash=inventory_hash,
        seed=seed,
        validation_fraction=validation_fraction,
    )
    _write_json_atomic(output / "split.json", split)
    episode_table = [
        {"index": index, "day": item.day, "filename": item.filename}
        for index, item in enumerate(episodes)
    ]
    _write_json_atomic(output / "episode-table.json", episode_table)

    validation_keys = set(split["validation"])
    train_writer = _ShardWriter(output, "train", target_shard_rows)
    validation_writer = _ShardWriter(output, "validation", target_shard_rows)
    totals_by_split = {
        "train": Counter(),
        "validation": Counter(),
    }
    examples_by_day: dict[str, Counter[str]] = defaultdict(Counter)
    skips_by_day: dict[str, Counter[str]] = {
        day: Counter({reason: 0 for reason in DECLARED_SKIP_REASONS})
        for day in days
    }
    histograms = {
        "n_options": Counter(),
        "min_count": Counter(),
        "max_count": Counter(),
        "selected_count": Counter(),
    }
    entity_overflow_count = 0

    jobs = [(item, index) for index, item in enumerate(episodes)]
    for source, result in zip(episodes, _process_jobs(jobs, workers)):
        if result.key != source.key:
            raise CacheContractError(
                f"worker result order mismatch: {source.key} != {result.key}"
            )
        split_name = (
            "validation" if source.key in validation_keys else "train"
        )
        writer = (
            validation_writer if split_name == "validation" else train_writer
        )
        writer.add_episode(result)
        totals_by_split[split_name]["examples"] += result.n_rows
        totals_by_split[split_name]["games"] += 1
        totals_by_split[split_name]["single"] += result.single_count
        totals_by_split[split_name]["multi"] += result.multi_count
        examples_by_day[source.day][split_name] += result.n_rows
        examples_by_day[source.day][f"{split_name}_games"] += 1
        examples_by_day[source.day]["single"] += result.single_count
        examples_by_day[source.day]["multi"] += result.multi_count
        skips_by_day[source.day].update(result.skip_counts)
        for name, values in result.histograms.items():
            _merge_histogram(histograms[name], values)
        entity_overflow_count += result.entity_overflow_count

    train_writer.flush()
    validation_writer.flush()
    shards = train_writer.metadata + validation_writer.metadata
    total_examples = sum(item["rows"] for item in shards)
    if total_examples != sum(
        totals_by_split[name]["examples"] for name in ("train", "validation")
    ):
        raise CacheContractError("shard rows disagree with accumulated totals")
    if not train_writer.metadata or not validation_writer.metadata:
        raise CacheContractError("both train and validation must contain examples")
    if (
        totals_by_split["train"]["single"] == 0
        or totals_by_split["validation"]["single"] == 0
        or totals_by_split["train"]["multi"] == 0
        or totals_by_split["validation"]["multi"] == 0
    ):
        raise CacheContractError(
            "both splits must contain nonzero single- and multi-select examples"
        )

    repository_root = Path(__file__).resolve().parents[4]
    finished = datetime.now(timezone.utc)
    elapsed = time.perf_counter() - started_clock
    manifest = {
        "schema": SCHEMA_NAME,
        "schema_version": 1,
        "identity": identity,
        "tensor_schema": {
            name: {
                "dtype": str(SHARD_DTYPES[name]).removeprefix("torch."),
                "trailing_shape": list(SHARD_WIDTHS[name]),
            }
            for name in SHARD_DTYPES
        },
        "flat_dim": FLAT_DIM,
        "repository": _repository_state(repository_root),
        "featurizer_version": FEATURIZER_VERSION,
        "frozen_table_manifest_hash": artifact_manifest_hash,
        "source": {
            "sanitized_root": str(source_root),
            "days": list(days),
            "inventory_hash": inventory_hash,
            "games_in_build": len(episodes),
            "games_discovered_before_limit": full_inventory_count,
            "max_episodes": max_episodes,
            "reports": report_summaries,
        },
        "split": {
            "seed": seed,
            "validation_fraction": validation_fraction,
            "split_hash": split["split_hash"],
        },
        "totals": {
            "games": len(episodes),
            "examples": total_examples,
            "single": sum(
                totals_by_split[name]["single"]
                for name in ("train", "validation")
            ),
            "multi": sum(
                totals_by_split[name]["multi"]
                for name in ("train", "validation")
            ),
            "by_split": {
                name: dict(totals_by_split[name])
                for name in ("train", "validation")
            },
            "by_day": {
                day: dict(examples_by_day[day]) for day in days
            },
        },
        "histograms": {
            name: {
                str(key): value for key, value in sorted(counter.items())
            }
            for name, counter in histograms.items()
        },
        "skip_counts_by_day": {
            day: {
                reason: skips_by_day[day][reason]
                for reason in DECLARED_SKIP_REASONS
            }
            for day in days
        },
        "diagnostics": {
            "entity_overflow_count": entity_overflow_count,
        },
        "target_shard_rows": target_shard_rows,
        "shards": shards,
        "files": {
            "split_sha256": sha256_file(output / "split.json"),
            "episode_table_sha256": sha256_file(
                output / "episode-table.json"
            ),
        },
        "build": {
            "started_utc": started.isoformat(),
            "finished_utc": finished.isoformat(),
            "elapsed_seconds": elapsed,
            "examples_per_second": total_examples / elapsed if elapsed else None,
            "host": socket.gethostname(),
            "platform": platform.platform(),
            "workers": workers,
        },
    }
    _write_json_atomic(output / "manifest.json", manifest)
    return manifest
