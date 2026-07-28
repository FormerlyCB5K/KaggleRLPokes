from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from engine_native_policy.il.cache import build_cache
from helpers import sample_deck, sample_observation


def observation_json(
    player: int,
    *,
    max_count: int,
    usable: bool = True,
) -> dict:
    observation = asdict(sample_observation(max_count=max_count))
    observation["current"]["yourIndex"] = player
    observation["select"]["usable"] = usable
    return observation


def sample_episode(seed: int = 0) -> dict:
    decks = [
        sample_deck(),
        [601 + seed] * 56 + [200, 400, 500, 600],
    ]
    first = [
        {
            "action": decks[player],
            "observation": observation_json(player, max_count=1),
        }
        for player in range(2)
    ]
    second = [
        {
            "action": [0],
            "observation": observation_json(player, max_count=2),
        }
        for player in range(2)
    ]
    third = [
        {
            "action": [0, 1],
            "observation": observation_json(
                player, max_count=1, usable=False
            ),
        }
        for player in range(2)
    ]
    fourth = [
        {"action": [0], "observation": None}
        for _ in range(2)
    ]
    return {
        "info": {},
        "rewards": [0, 1],
        "statuses": ["DONE", "DONE"],
        "steps": [first, second, third, fourth],
    }


def write_sanitized_corpus(
    root: Path,
    *,
    days: tuple[str, ...] = ("7-12",),
    episodes_per_day: int = 4,
) -> Path:
    for day_index, day in enumerate(days):
        day_dir = root / day
        day_dir.mkdir(parents=True)
        for episode_index in range(episodes_per_day):
            episode = sample_episode(day_index * 100 + episode_index)
            path = day_dir / f"{episode_index:08d}.json"
            path.write_text(json.dumps(episode), encoding="utf-8")
        report = {
            "day": day,
            "total_episodes_seen": episodes_per_day,
            "excluded": [],
            "episodes_written": episodes_per_day,
            "steps_total": episodes_per_day * 8,
            "steps_usable": episodes_per_day * 6,
            "steps_masked": episodes_per_day * 2,
            "source_archive": f"fixture/{day}.zip",
        }
        (day_dir / "report.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
    return root


def build_test_cache(root: Path, *, workers: int = 1) -> tuple[Path, Path]:
    source = write_sanitized_corpus(root / "sanitized")
    output = root / "cache"
    artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    build_cache(
        sanitized_root=source,
        output_root=output,
        days=("7-12",),
        validation_fraction=0.25,
        seed=20260728,
        target_shard_rows=3,
        workers=workers,
        tables_path=artifacts / "frozen_tables.pt",
        artifact_manifest_path=artifacts / "installed-manifest.json",
    )
    return source, output
