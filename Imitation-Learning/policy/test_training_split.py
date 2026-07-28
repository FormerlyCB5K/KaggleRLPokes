"""Integrity tests for the persistent global game split."""
from __future__ import annotations

import json
import os
import pickle
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _IL_ROOT)

from cg_download.api import OptionType
from observation.encoder import Word
from observation.types import TOTAL_WORDS
from policy import action_space as asp
from policy import data as data_mod
from policy import training_split


def _example(episode_name: str, turn: int) -> data_mod.Example:
    words = (
        [Word("pad", None, None, None, True)] * (TOTAL_WORDS - 2)
        + [
            Word("global", None, None, {"turn_number": turn}, False),
            Word("pool", None, None, None, False),
        ]
    )
    return data_mod.Example(
        words=words,
        option_type=OptionType.YES,
        verb_index=None,
        candidates=[
            asp.Candidate(0, OptionType.YES, literal=1.0),
            asp.Candidate(1, OptionType.NO, literal=0.0),
        ],
        label_index=turn % 2,
        episode_name=episode_name,
    )


def _fake_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    for day in ("7-12", "7-13"):
        examples = []
        for game_index in range(5):
            # Deliberately reuse filenames across days: the global key must include day.
            episode_name = f"episode-{game_index}.json"
            examples.extend([
                _example(episode_name, game_index * 2),
                _example(episode_name, game_index * 2 + 1),
            ])
        examples_path, manifest_path = data_mod.cache_file_paths(
            str(cache_dir), "sanitized", day,
        )
        os.makedirs(os.path.dirname(examples_path), exist_ok=True)
        with open(examples_path, "wb") as handle:
            pickle.dump(examples, handle)
        manifest = data_mod.build_manifest(
            source_label="sanitized",
            day=day,
            max_episodes_per_zip=None,
            max_steps=300,
            source_fingerprint={"kind": "test", "day": day},
            n_examples=len(examples),
        )
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(manifest, handle)
    return cache_dir


def test_global_random_split_is_exact_persistent_and_leak_free(tmp_path):
    cache_dir = _fake_cache(tmp_path)
    split_path = tmp_path / "run" / "game-split.json"

    split = training_split.prepare_or_load_game_split(
        split_path=str(split_path),
        cache_dir=str(cache_dir),
        source="sanitized",
        val_frac=0.2,
        seed=17,
        max_episodes_per_zip=None,
        max_steps=300,
    )

    assert split["total_games"] == 10
    assert split["training_games"] == 8
    assert split["validation_game_count"] == 2
    assert split["total_positions"] == 20
    assert split["training_positions"] == 16
    assert split["validation_positions"] == 4
    assert sum(day["validation_games"] for day in split["source_days"]) == 2

    validation_keys = training_split.validation_key_set(split)
    observed_validation_keys = set()
    for entry in split["source_days"]:
        shard = training_split.load_validation_shard(
            str(split_path), split, entry["source"], entry["day"],
        )
        observed_validation_keys.update(
            training_split.game_key(
                entry["source"], entry["day"], example.episode_name,
            )
            for example in shard
        )
    assert observed_validation_keys == validation_keys

    reloaded = training_split.prepare_or_load_game_split(
        split_path=str(split_path),
        cache_dir=str(cache_dir),
        source="sanitized",
        val_frac=0.2,
        seed=17,
        max_episodes_per_zip=None,
        max_steps=300,
    )
    assert reloaded == split


def test_existing_split_rejects_changed_seed_or_cache_inventory(tmp_path):
    cache_dir = _fake_cache(tmp_path)
    split_path = tmp_path / "run" / "game-split.json"
    kwargs = dict(
        split_path=str(split_path),
        cache_dir=str(cache_dir),
        source="sanitized",
        val_frac=0.2,
        seed=17,
        max_episodes_per_zip=None,
        max_steps=300,
    )
    training_split.prepare_or_load_game_split(**kwargs)

    with pytest.raises(RuntimeError, match="seed"):
        training_split.prepare_or_load_game_split(**{**kwargs, "seed": 18})

    _examples_path, manifest_path = data_mod.cache_file_paths(
        str(cache_dir), "sanitized", "7-12",
    )
    with open(manifest_path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    manifest["n_examples"] += 1
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle)

    with pytest.raises(RuntimeError, match="cache_inventory_hash"):
        training_split.prepare_or_load_game_split(**kwargs)
