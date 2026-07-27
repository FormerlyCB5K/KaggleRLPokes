"""Spec 16c tests: example extraction from real recorded ladder games."""
from __future__ import annotations

import itertools
import json
import os
import pickle
import shutil
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _IL_ROOT)

import pytest

import build_example_cache
from observation.types import TOTAL_WORDS
from policy import action_space as asp
from policy import data

_ZIP_PATH = os.path.join(
    _IL_ROOT, "Top-ladder-data", "7-12", "pokemon-tcg-ai-battle-episodes-2026-07-12.zip",
)
_SANITIZED_DAY_DIR = os.path.join(_IL_ROOT, "Top-ladder-data", "sanitized", "7-12")
_PRIZE_GAP_EPISODE = os.path.join(_SANITIZED_DAY_DIR, "85489078.json")


@pytest.mark.skipif(not os.path.isfile(_ZIP_PATH), reason="recorded replay data not present")
def test_extract_examples_well_formed():
    examples = list(itertools.islice(data.extract_examples(_ZIP_PATH, max_episodes=3), 200))
    assert examples, "expected at least one extracted example"

    n_main = 0
    n_sub = 0
    for ex in examples:
        assert len(ex.words) == TOTAL_WORDS
        assert 0 <= ex.label_index < len(ex.candidates)
        if ex.verb_index is not None:
            assert 0 <= ex.verb_index < asp.N_VERBS
            n_main += 1
        else:
            n_sub += 1

    assert n_main > 0
    assert n_sub > 0


@pytest.mark.skipif(
    not os.path.isdir(_SANITIZED_DAY_DIR), reason="sanitized dataset not present locally"
)
def test_extract_examples_from_dir_well_formed():
    examples = list(
        itertools.islice(data.extract_examples_from_dir(_SANITIZED_DAY_DIR, max_episodes=3), 200)
    )
    assert examples, "expected at least one extracted example"
    for ex in examples:
        assert len(ex.words) == TOTAL_WORDS
        assert 0 <= ex.label_index < len(ex.candidates)


def _step(player_count: int, action, select) -> list:
    """One `steps[i]` entry: `player_count` player-slots, only slot 0 populated with
    the given action/select (mirrors real 2-player replay shape)."""
    entries = [{"action": [], "observation": {"select": None}} for _ in range(player_count)]
    entries[0] = {"action": action, "observation": {"select": select}}
    return entries


def test_iter_paired_decisions_skips_usable_false():
    """The sanitized dataset marks `usable=false` on single-legal-option decisions;
    iter_paired_decisions must not yield those. Recall the off-by-one pairing:
    `steps[i].action` responds to `steps[i-1].observation`, so each observation
    under test needs a *following* step supplying the action that responds to it."""
    steps = [
        _step(2, [], None),  # steps[0]: dummy prior obs (no select) for steps[1]'s action
        _step(2, [0], {"option": [{"type": 1}], "usable": False}),  # masked: 1 option
        _step(2, [1], {"option": [{"type": 1}, {"type": 2}], "usable": True}),  # real choice
        _step(2, [1], None),  # steps[3]'s action responds to steps[2]'s (usable) obs
    ]
    decisions = list(data.iter_paired_decisions(steps))
    assert len(decisions) == 1, "the usable=False decision must be skipped"
    _, action, obs_json = decisions[0]
    assert action == [1]
    assert obs_json["select"]["usable"] is True


def test_iter_paired_decisions_defaults_usable_true_when_absent():
    """Raw (unsanitized) episodes have no `usable` key at all -- behavior must be
    unchanged (nothing gets filtered on that basis)."""
    steps = [
        _step(2, [], None),
        _step(2, [1], {"option": [{"type": 1}]}),  # no "usable" key -- raw-zip shape
        _step(2, [1], None),  # action responding to the prior (unmasked-shape) obs
    ]
    decisions = list(data.iter_paired_decisions(steps))
    assert len(decisions) == 1


def test_iter_tracker_observations_keeps_forced_choices_and_deduplicates_repeats():
    """Trackers need forced choices for their delta logs even though IL drops them."""
    forced = {"current": {"turn": 1}, "select": {"usable": False}}
    usable = {"current": {"turn": 2}, "select": {"usable": True}}
    def observation_step(action, observation):
        entries = [{"action": [], "observation": {}} for _ in range(2)]
        entries[0] = {"action": action, "observation": observation}
        return entries

    steps = [
        observation_step([], {}),
        observation_step([], forced),
        observation_step([0], forced),
        observation_step([], usable),
        observation_step([0], {}),
    ]
    observations = list(data.iter_tracker_observations(steps))
    assert [(action, obs) for _, action, obs in observations] == [
        ([0], forced),
        ([0], usable),
    ]


@pytest.mark.skipif(
    not os.path.isfile(_PRIZE_GAP_EPISODE), reason="prize-gap regression replay not present"
)
def test_forced_choice_prize_take_advances_trackers():
    """A forced ACTIVE selection carries the only PRIZE->HAND log in this replay.

    The next trainable decision reports five prizes. If the forced observation is
    filtered before tracker updates, extraction raises with an inferred 6 vs 5
    PrizeTracker mismatch.
    """
    with open(_PRIZE_GAP_EPISODE, "rb") as handle:
        episode = json.load(handle)
    examples = list(data._examples_from_episode(episode, "85489078.json", max_steps=300))
    assert examples


def test_iter_all_examples_rejects_invalid_source():
    with pytest.raises(ValueError):
        list(data.iter_all_examples(source="bogus"))


def test_iter_all_examples_requires_matching_dir_arg():
    with pytest.raises(ValueError):
        list(data.iter_all_examples(source="raw", raw_dir=None))
    with pytest.raises(ValueError):
        list(data.iter_all_examples(source="sanitized", sanitized_dir=None))


def test_parse_episode_limit():
    assert data.parse_episode_limit(None) is None
    assert data.parse_episode_limit("all") is None
    assert data.parse_episode_limit("NONE") is None
    assert data.parse_episode_limit("20") == 20
    assert data.parse_episode_limit(5) == 5
    with pytest.raises(ValueError):
        data.parse_episode_limit("bogus")
    with pytest.raises(ValueError):
        data.parse_episode_limit(0)


def test_group_days():
    days = ["7-12", "7-13", "7-14"]
    assert data._group_days(days, 1) == [["7-12"], ["7-13"], ["7-14"]]
    assert data._group_days(days, 2) == [["7-12", "7-13"], ["7-14"]]
    with pytest.raises(ValueError):
        data._group_days(days, 0)


def test_source_day_discovery_ignores_infrastructure_and_preserves_source(tmp_path):
    raw_root = tmp_path / "raw"
    sanitized_root = tmp_path / "sanitized-root"
    (raw_root / "7-12").mkdir(parents=True)
    (raw_root / "7-12" / "day.zip").write_bytes(b"")
    (raw_root / "sanitized").mkdir()
    (raw_root / "sanitized" / "episode.json").write_text("{}")
    (raw_root / "example-cache").mkdir()
    (sanitized_root / "7-13").mkdir(parents=True)
    (sanitized_root / "7-13" / "episode.json").write_text("{}")
    (sanitized_root / "empty").mkdir()
    (sanitized_root / "empty" / "report.json").write_text("{}")

    assert data.list_source_day_pairs(str(raw_root), None, "raw") == [
        ("raw", "7-12")
    ]
    assert data.list_source_day_pairs(
        str(raw_root), str(sanitized_root), "both"
    ) == [("raw", "7-12"), ("sanitized", "7-13")]
    assert data.list_days(str(raw_root), str(sanitized_root), "both") == [
        "7-12", "7-13"
    ]


@pytest.mark.skipif(
    not os.path.isdir(os.path.dirname(_SANITIZED_DAY_DIR)),
    reason="three-day sanitized fixture not present locally",
)
def test_iter_examples_by_day_chunk_groups_real_days():
    root = os.path.dirname(_SANITIZED_DAY_DIR)
    one_day = list(
        data.iter_examples_by_day_chunk(
            sanitized_dir=root, source="sanitized", days_per_chunk=1,
            max_episodes_per_zip=1, max_steps=20,
        )
    )
    two_day = list(
        data.iter_examples_by_day_chunk(
            sanitized_dir=root, source="sanitized", days_per_chunk=2,
            max_episodes_per_zip=1, max_steps=20,
        )
    )
    assert [label for label, _examples in one_day] == ["7-12", "7-13", "7-14"]
    assert [label for label, _examples in two_day] == ["7-12+7-13", "7-14"]


def _write_cache_entry(
    cache_dir, source_label, day, examples, *,
    fingerprint, max_episodes=1, max_steps=20, manifest_overrides=None,
):
    examples_path, manifest_path = data.cache_file_paths(
        str(cache_dir), source_label, day
    )
    os.makedirs(os.path.dirname(examples_path), exist_ok=True)
    manifest = data.build_manifest(
        source_label=source_label, day=day,
        max_episodes_per_zip=max_episodes, max_steps=max_steps,
        source_fingerprint=fingerprint, n_examples=len(examples),
    )
    manifest.update(manifest_overrides or {})
    with open(examples_path, "wb") as handle:
        pickle.dump(examples, handle)
    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle)
    return examples_path, manifest_path


def test_manifest_matches_all_guard_fields():
    fingerprint = {"kind": "dir", "file_count": 1, "digest": "abc"}
    manifest = data.build_manifest(
        source_label="sanitized", day="7-12",
        max_episodes_per_zip=None, max_steps=300,
        source_fingerprint=fingerprint, n_examples=2,
    )
    assert data.manifest_matches(
        manifest, max_episodes_per_zip=None, max_steps=300,
        source_fingerprint=fingerprint, source_label="sanitized", day="7-12",
    ) == (True, "")

    cases = [
        ({"schema_version": 0}, "schema_version"),
        ({"source_label": "raw"}, "source_label"),
        ({"day": "7-13"}, "day"),
        ({"max_episodes_per_zip": 20}, "max_episodes_per_zip"),
        ({"max_steps": 50}, "max_steps"),
        ({"source_fingerprint": {"different": True}}, "source_fingerprint"),
    ]
    for override, expected_reason in cases:
        candidate = dict(manifest)
        candidate.update(override)
        ok, reason = data.manifest_matches(
            candidate, max_episodes_per_zip=None, max_steps=300,
            source_fingerprint=fingerprint, source_label="sanitized", day="7-12",
        )
        assert not ok
        assert expected_reason in reason

    # A copied cache remains usable on a cache-only machine with no source tree.
    assert data.manifest_matches(
        manifest, max_episodes_per_zip=None, max_steps=300,
        source_fingerprint=None, source_label="sanitized", day="7-12",
    ) == (True, "")


def test_cached_loader_rejects_missing_cache_siblings_and_incomplete_source(tmp_path):
    source_root = tmp_path / "source"
    (source_root / "7-12").mkdir(parents=True)
    (source_root / "7-12" / "episode.json").write_text("{}")
    cache_dir = tmp_path / "cache"

    with pytest.raises(RuntimeError, match="missing cache pickle.*sanitized/7-12"):
        list(
            data.iter_cached_examples_by_day_chunk(
                str(cache_dir), source="sanitized",
                sanitized_dir=str(source_root), max_episodes_per_zip=1,
            )
        )

    examples_path, _manifest_path = data.cache_file_paths(
        str(cache_dir), "sanitized", "7-12"
    )
    os.makedirs(os.path.dirname(examples_path), exist_ok=True)
    with open(examples_path, "wb") as handle:
        pickle.dump([], handle)
    with pytest.raises(RuntimeError, match="missing cache manifest.*sanitized/7-12"):
        list(
            data.iter_cached_examples_by_day_chunk(
                str(cache_dir), source="sanitized",
                sanitized_dir=str(source_root), max_episodes_per_zip=1,
            )
        )


def test_cached_loader_rejects_stale_and_count_mismatched_entries(tmp_path):
    cache_dir = tmp_path / "cache"
    fingerprint = {"kind": "dir", "file_count": 0, "digest": "empty"}
    _write_cache_entry(
        cache_dir, "sanitized", "7-12", [], fingerprint=fingerprint,
        max_episodes=1, max_steps=20,
    )
    with pytest.raises(RuntimeError, match="max_steps"):
        list(
            data.iter_cached_examples_by_day_chunk(
                str(cache_dir), source="sanitized",
                max_episodes_per_zip=1, max_steps=21,
            )
        )

    _write_cache_entry(
        cache_dir, "sanitized", "7-12", [], fingerprint=fingerprint,
        max_episodes=1, max_steps=20, manifest_overrides={"n_examples": 1},
    )
    with pytest.raises(RuntimeError, match="manifest n_examples=1.*loaded=0"):
        list(
            data.iter_cached_examples_by_day_chunk(
                str(cache_dir), source="sanitized",
                max_episodes_per_zip=1, max_steps=20,
            )
        )


def test_cached_loader_supports_nonoverlapping_both_sources(tmp_path):
    raw_root = tmp_path / "raw"
    sanitized_root = tmp_path / "sanitized"
    cache_dir = tmp_path / "cache"
    (raw_root / "7-12").mkdir(parents=True)
    (raw_root / "7-12" / "day.zip").write_bytes(b"raw")
    (sanitized_root / "7-13").mkdir(parents=True)
    (sanitized_root / "7-13" / "episode.json").write_text("{}")

    raw_fingerprint = data._raw_day_fingerprint(str(raw_root / "7-12"))
    sanitized_fingerprint = data._sanitized_dir_fingerprint(
        str(sanitized_root / "7-13")
    )
    _write_cache_entry(
        cache_dir, "raw", "7-12", [], fingerprint=raw_fingerprint,
    )
    _write_cache_entry(
        cache_dir, "sanitized", "7-13", [], fingerprint=sanitized_fingerprint,
    )

    chunks = list(
        data.iter_cached_examples_by_day_chunk(
            str(cache_dir), source="both", days_per_chunk=1,
            max_episodes_per_zip=1, max_steps=20,
            raw_dir=str(raw_root), sanitized_dir=str(sanitized_root),
        )
    )
    assert [label for label, _examples in chunks] == ["7-12", "7-13"]


@pytest.mark.skipif(
    not os.path.isdir(_SANITIZED_DAY_DIR), reason="sanitized dataset not present locally"
)
def test_real_cache_round_trip_and_idempotency(tmp_path):
    source_root = tmp_path / "sanitized"
    copied_day = source_root / "7-12"
    copied_day.mkdir(parents=True)
    episode_name = sorted(
        filename for filename in os.listdir(_SANITIZED_DAY_DIR)
        if filename.endswith(".json") and filename != "report.json"
    )[0]
    shutil.copyfile(
        os.path.join(_SANITIZED_DAY_DIR, episode_name),
        copied_day / episode_name,
    )
    cache_dir = tmp_path / "cache"

    live_examples = list(
        data.extract_examples_from_dir(str(copied_day), max_episodes=1, max_steps=50)
    )
    first = build_example_cache.build_day_cache(
        "sanitized", "7-12", str(source_root), str(cache_dir),
        max_episodes_per_zip=1, max_steps=50, workers=1, force=False,
    )
    second = build_example_cache.build_day_cache(
        "sanitized", "7-12", str(source_root), str(cache_dir),
        max_episodes_per_zip=1, max_steps=50, workers=1, force=False,
    )
    cached_chunks = list(
        data.iter_cached_examples_by_day_chunk(
            str(cache_dir), source="sanitized", days_per_chunk=1,
            max_episodes_per_zip=1, max_steps=50,
            sanitized_dir=str(source_root),
        )
    )
    cached_examples = cached_chunks[0][1]

    assert first["status"] == "built"
    assert second["status"] == "skipped"
    assert len(cached_examples) == len(live_examples)
    assert {ex.episode_name for ex in cached_examples} == {
        ex.episode_name for ex in live_examples
    }
