from __future__ import annotations

import csv
import json
import sys
import zipfile
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_top_rated_winner_dataset import (  # noqa: E402
    PreparationError,
    prepare_episode,
    process_day,
    select_manifest_rows,
)


def _entry(action):
    return {
        "action": action,
        "observation": {
            "current": {"yourIndex": 0},
            "select": {"option": [{"number": 0}, {"number": 1}]},
        },
    }


def _episode(episode_id: int, rewards, *, statuses=None):
    deck0 = list(range(60))
    deck1 = list(range(100, 160))
    return {
        "info": {"EpisodeId": episode_id, "TeamNames": ["a", "b"]},
        "rewards": rewards,
        "statuses": statuses or ["DONE", "DONE"],
        "steps": [
            [_entry(deck0), _entry(deck1)],
            [_entry([0]), _entry([1])],
            [_entry([1]), _entry([0])],
        ],
    }


def _selection(episode_id: int, rank: int = 1):
    return {
        "episode_id": episode_id,
        "selection_rank": rank,
        "avg_score": 900.0,
        "min_score": 850.0,
        "sum_score": 1800.0,
    }


def test_select_manifest_rows_uses_ceil_and_deterministic_ties() -> None:
    rows = [
        {
            "episode_id": episode_id,
            "min_score": score,
            "avg_score": average,
            "sum_score": average * 2,
        }
        for episode_id, score, average in (
            (4, 8.0, 9.0),
            (3, 8.0, 10.0),
            (2, 7.0, 20.0),
            (1, 6.0, 30.0),
        )
    ]
    selected = select_manifest_rows(
        rows, fraction=0.26, score_column="min_score"
    )
    assert [item["episode_id"] for item in selected] == [3, 4]
    assert [item["selection_rank"] for item in selected] == [1, 2]


def test_winner_filter_preserves_both_decks_and_blanks_loser_actions() -> None:
    episode = _episode(1, [1, -1])
    prepared, result = prepare_episode(
        json.dumps(episode).encode(),
        selection=_selection(1),
        score_column="min_score",
    )
    assert prepared is not None
    assert result["outcome"] == "decisive"
    assert result["supervised_players"] == [0]
    assert len(prepared["steps"][0][1]["action"]) == 60
    assert prepared["steps"][1][1]["action"] == []
    assert prepared["steps"][2][1]["action"] == []
    assert prepared["steps"][1][0]["action"] == [0]
    assert prepared["dataset_selection"]["supervised_players"] == [0]
    assert prepared["steps"][0][0]["observation"]["select"]["usable"] is True


def test_all_perspectives_preserves_both_players_actions() -> None:
    episode = _episode(1, [1, -1])
    prepared, result = prepare_episode(
        json.dumps(episode).encode(),
        selection=_selection(1),
        score_column="min_score",
        perspective_mode="all",
    )
    assert prepared is not None
    assert result["outcome"] == "decisive"
    assert result["supervised_players"] == [0, 1]
    assert result["filtered_actions"] == 0
    assert prepared["steps"][1][0]["action"] == [0]
    assert prepared["steps"][1][1]["action"] == [1]
    assert prepared["dataset_selection"] == {
        "schema": "top-rated-all-perspectives-replays-v1",
        "score_column": "min_score",
        "perspective_mode": "all",
        "selection_rank": 1,
        "avg_score": 900.0,
        "min_score": 850.0,
        "sum_score": 1800.0,
        "outcome": "decisive",
        "supervised_players": [0, 1],
    }


def test_draw_keeps_both_perspectives_and_non_numeric_result_is_excluded() -> None:
    draw, draw_result = prepare_episode(
        json.dumps(_episode(1, [0, 0])).encode(),
        selection=_selection(1),
        score_column="min_score",
    )
    assert draw is not None
    assert draw_result["outcome"] == "draw"
    assert draw_result["filtered_actions"] == 0

    missing, missing_result = prepare_episode(
        json.dumps(_episode(2, [None, None])).encode(),
        selection=_selection(2),
        score_column="min_score",
    )
    assert missing is None
    assert missing_result["reason"] == "non_numeric_result"


def test_process_day_writes_ranked_report_and_atomic_day(tmp_path) -> None:
    data_root = tmp_path / "raw"
    day_dir = data_root / "7-23"
    day_dir.mkdir(parents=True)
    archive = day_dir / "episodes.zip"
    rows = []
    with zipfile.ZipFile(archive, "w") as bundle:
        for episode_id in range(1, 11):
            rows.append(
                {
                    "episode_id": episode_id,
                    "create_time": "",
                    "avg_score": 1000 + episode_id,
                    "min_score": 900 + episode_id,
                    "sum_score": 2000 + episode_id,
                    "agent_count": 2,
                    "size_bytes": 1,
                }
            )
            statuses = ["ACTIVE", "DONE"] if episode_id == 10 else ["DONE", "DONE"]
            bundle.writestr(
                f"{episode_id}.json",
                json.dumps(_episode(episode_id, [1, -1], statuses=statuses)),
            )
        fieldnames = list(rows[0])
        manifest = []
        class _Sink:
            def write(self, value):
                manifest.append(value)
        writer = csv.DictWriter(_Sink(), fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        bundle.writestr("manifest.csv", "".join(manifest))

    output = tmp_path / "selected"
    report = process_day(
        day="7-23",
        data_root=data_root,
        output_root=output,
        fraction=0.20,
        workers=1,
    )
    assert report["selection"]["selected_episodes"] == 2
    assert report["episodes_written"] == 1
    assert report["excluded"][0]["episode_id"] == 10
    assert report["excluded"][0]["reason"] == "non_done_status"
    assert (output / "7-23" / "9.json").is_file()
    assert not (output / "7-23" / "10.json").exists()
    persisted = json.loads((output / "7-23" / "report.json").read_text())
    assert persisted["schema"] == "top-rated-winner-replays-v1"

    reused = process_day(
        day="7-23",
        data_root=data_root,
        output_root=output,
        fraction=0.20,
        workers=1,
        reuse_existing=True,
    )
    assert reused == report

    with pytest.raises(PreparationError, match="does not exactly match"):
        process_day(
            day="7-23",
            data_root=data_root,
            output_root=output,
            fraction=0.30,
            workers=1,
            reuse_existing=True,
        )
