"""Persistent random game split and reusable fixed-validation shards for IL."""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import random
import uuid
from collections import Counter

from . import data as data_mod

SPLIT_SCHEMA_VERSION = 1
VALIDATION_SHARD_SCHEMA_VERSION = 1

GameKey = tuple[str, str, str]  # source label, day, episode filename


def game_key(source_label: str, day: str, episode_name: str) -> GameKey:
    if not episode_name:
        raise RuntimeError(f"cached example in {source_label}/{day} has no episode_name")
    return source_label, day, episode_name


def _canonical_hash(value) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json_atomic(path: str, value) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
    os.replace(temp, path)


def _write_pickle_atomic(path: str, value) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(temp, "xb") as handle:
        pickle.dump(value, handle, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(temp, path)


def validation_shard_path(
    split_path: str, source_label: str, day: str,
) -> str:
    stem = os.path.splitext(os.path.abspath(split_path))[0]
    return os.path.join(stem + ".validation", source_label, f"{day}.pkl")


def cache_inventory(
    *,
    cache_dir: str,
    source: str,
    max_episodes_per_zip: int | None,
    max_steps: int,
    raw_dir: str | None,
    sanitized_dir: str | None,
) -> tuple[list[tuple[str, str]], list[dict], str]:
    pairs = data_mod.resolve_cached_source_day_pairs(
        cache_dir, source, raw_dir=raw_dir, sanitized_dir=sanitized_dir,
    )
    inventory = []
    for label, day in pairs:
        _examples_path, manifest_path = data_mod.cache_file_paths(
            cache_dir, label, day,
        )
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = json.load(handle)
        root = raw_dir if label == "raw" else sanitized_dir
        fingerprint = data_mod._resolve_source_fingerprint(label, root, day)
        ok, reason = data_mod.manifest_matches(
            manifest,
            max_episodes_per_zip=max_episodes_per_zip,
            max_steps=max_steps,
            source_fingerprint=fingerprint,
            source_label=label,
            day=day,
        )
        if not ok:
            raise RuntimeError(
                f"stale cache for {label}/{day}: {reason}; "
                "rerun build_example_cache.py"
            )
        inventory.append({
            "source": label,
            "day": day,
            "schema_version": manifest["schema_version"],
            "max_episodes_per_zip": manifest["max_episodes_per_zip"],
            "max_steps": manifest["max_steps"],
            "source_fingerprint": manifest["source_fingerprint"],
            "n_examples": manifest["n_examples"],
        })
    return pairs, inventory, _canonical_hash(inventory)


def _validate_existing_split(
    split: dict,
    *,
    seed: int,
    val_frac: float,
    inventory_hash: str,
) -> None:
    expected = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "seed": seed,
        "val_frac": val_frac,
        "cache_inventory_hash": inventory_hash,
    }
    for key, value in expected.items():
        if split.get(key) != value:
            raise RuntimeError(
                f"existing game split mismatch for {key}: "
                f"saved={split.get(key)!r}, requested={value!r}; "
                "use a new --split-path or --rebuild-split"
            )
    validation_games = split.get("validation_games")
    if not isinstance(validation_games, list):
        raise RuntimeError("existing game split has no validation_games list")
    expected_hash = _canonical_hash(validation_games)
    if split.get("split_hash") != expected_hash:
        raise RuntimeError(
            "existing game split hash does not match its validation game list"
        )


def _load_all_game_counts(
    *,
    cache_dir: str,
    pairs: list[tuple[str, str]],
    max_episodes_per_zip: int | None,
    max_steps: int,
    raw_dir: str | None,
    sanitized_dir: str | None,
) -> tuple[dict[GameKey, int], dict[tuple[str, str], dict]]:
    game_counts: dict[GameKey, int] = {}
    day_totals: dict[tuple[str, str], dict] = {}
    for label, day in pairs:
        examples, _manifest = data_mod.load_cached_source_day(
            cache_dir, label, day,
            max_episodes_per_zip=max_episodes_per_zip,
            max_steps=max_steps,
            raw_dir=raw_dir,
            sanitized_dir=sanitized_dir,
        )
        counts = Counter(
            game_key(label, day, example.episode_name) for example in examples
        )
        overlap = set(game_counts).intersection(counts)
        if overlap:
            raise RuntimeError(f"duplicate global game key(s): {sorted(overlap)[:3]}")
        game_counts.update(counts)
        day_totals[(label, day)] = {
            "games": len(counts),
            "positions": len(examples),
        }
        del examples
    return game_counts, day_totals


def _build_validation_shards(
    *,
    split_path: str,
    split_hash: str,
    validation_keys: set[GameKey],
    cache_dir: str,
    pairs: list[tuple[str, str]],
    max_episodes_per_zip: int | None,
    max_steps: int,
    raw_dir: str | None,
    sanitized_dir: str | None,
) -> tuple[int, dict[tuple[str, str], int]]:
    total_positions = 0
    positions_by_day = {}
    for label, day in pairs:
        examples, _manifest = data_mod.load_cached_source_day(
            cache_dir, label, day,
            max_episodes_per_zip=max_episodes_per_zip,
            max_steps=max_steps,
            raw_dir=raw_dir,
            sanitized_dir=sanitized_dir,
        )
        validation_examples = [
            example for example in examples
            if game_key(label, day, example.episode_name) in validation_keys
        ]
        path = validation_shard_path(split_path, label, day)
        _write_pickle_atomic(path, {
            "schema_version": VALIDATION_SHARD_SCHEMA_VERSION,
            "split_hash": split_hash,
            "source": label,
            "day": day,
            "n_examples": len(validation_examples),
            "examples": validation_examples,
        })
        positions_by_day[(label, day)] = len(validation_examples)
        total_positions += len(validation_examples)
        del examples, validation_examples
    return total_positions, positions_by_day


def prepare_or_load_game_split(
    *,
    split_path: str,
    cache_dir: str,
    source: str,
    val_frac: float,
    seed: int,
    max_episodes_per_zip: int | None,
    max_steps: int,
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
    rebuild: bool = False,
) -> dict:
    """Create or validate a fixed random episode split and validation shards."""
    if not 0.0 < val_frac < 1.0:
        raise ValueError(f"val_frac must be between 0 and 1, got {val_frac}")
    pairs, inventory, inventory_hash = cache_inventory(
        cache_dir=cache_dir,
        source=source,
        max_episodes_per_zip=max_episodes_per_zip,
        max_steps=max_steps,
        raw_dir=raw_dir,
        sanitized_dir=sanitized_dir,
    )

    if os.path.isfile(split_path) and not rebuild:
        with open(split_path, encoding="utf-8") as handle:
            split = json.load(handle)
        _validate_existing_split(
            split, seed=seed, val_frac=val_frac,
            inventory_hash=inventory_hash,
        )
        for entry in split["source_days"]:
            shard_path = validation_shard_path(
                split_path, entry["source"], entry["day"],
            )
            if not os.path.isfile(shard_path):
                raise RuntimeError(
                    f"validation shard missing at {shard_path!r}; "
                    "rerun with --rebuild-split"
                )
        return split

    game_counts, day_totals = _load_all_game_counts(
        cache_dir=cache_dir,
        pairs=pairs,
        max_episodes_per_zip=max_episodes_per_zip,
        max_steps=max_steps,
        raw_dir=raw_dir,
        sanitized_dir=sanitized_dir,
    )
    all_games = sorted(game_counts)
    if len(all_games) < 2:
        raise RuntimeError("at least two games are required for a train/validation split")
    shuffled_games = list(all_games)
    random.Random(seed).shuffle(shuffled_games)
    n_validation_games = min(
        len(all_games) - 1, max(1, round(len(all_games) * val_frac)),
    )
    validation_keys = set(shuffled_games[:n_validation_games])
    validation_games = [
        {"source": label, "day": day, "episode": episode}
        for label, day, episode in sorted(validation_keys)
    ]
    split_hash = _canonical_hash(validation_games)

    validation_positions, val_positions_by_day = _build_validation_shards(
        split_path=split_path,
        split_hash=split_hash,
        validation_keys=validation_keys,
        cache_dir=cache_dir,
        pairs=pairs,
        max_episodes_per_zip=max_episodes_per_zip,
        max_steps=max_steps,
        raw_dir=raw_dir,
        sanitized_dir=sanitized_dir,
    )
    total_positions = sum(game_counts.values())
    source_days = []
    for label, day in pairs:
        day_validation_games = sum(
            1 for key in validation_keys if key[:2] == (label, day)
        )
        totals = day_totals[(label, day)]
        source_days.append({
            "source": label,
            "day": day,
            "total_games": totals["games"],
            "training_games": totals["games"] - day_validation_games,
            "validation_games": day_validation_games,
            "total_positions": totals["positions"],
            "training_positions": (
                totals["positions"] - val_positions_by_day[(label, day)]
            ),
            "validation_positions": val_positions_by_day[(label, day)],
        })

    split = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "seed": seed,
        "val_frac": val_frac,
        "cache_inventory_hash": inventory_hash,
        "cache_inventory": inventory,
        "split_hash": split_hash,
        "total_games": len(all_games),
        "training_games": len(all_games) - n_validation_games,
        "validation_game_count": n_validation_games,
        "total_positions": total_positions,
        "training_positions": total_positions - validation_positions,
        "validation_positions": validation_positions,
        "source_days": source_days,
        "validation_games": validation_games,
    }
    _write_json_atomic(split_path, split)
    return split


def validation_key_set(split: dict) -> set[GameKey]:
    return {
        (entry["source"], entry["day"], entry["episode"])
        for entry in split["validation_games"]
    }


def load_validation_shard(
    split_path: str, split: dict, source_label: str, day: str,
) -> list[data_mod.Example]:
    path = validation_shard_path(split_path, source_label, day)
    with open(path, "rb") as handle:
        payload = pickle.load(handle)
    expected = {
        "schema_version": VALIDATION_SHARD_SCHEMA_VERSION,
        "split_hash": split["split_hash"],
        "source": source_label,
        "day": day,
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise RuntimeError(
                f"validation shard {path!r} mismatch for {key}: "
                f"saved={payload.get(key)!r}, expected={value!r}"
            )
    examples = payload.get("examples")
    if not isinstance(examples, list) or payload.get("n_examples") != len(examples):
        raise RuntimeError(f"invalid validation shard payload at {path!r}")
    return examples
