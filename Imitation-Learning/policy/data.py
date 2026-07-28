"""Spec 16c: extract supervised (observation, verb, candidates, label) examples from
recorded ladder games -- either raw `Top-ladder-data/*/*.zip` archives, or a sanitized
dataset produced by `build_sanitized_top_ladder_dataset.py` (loose per-episode `*.json`
files under `<sanitized_root>/<day>/`, `report.json` excluded). `iter_all_examples`'s
`source` argument ("raw" / "sanitized" / "both") selects which to read.

Off-by-one alignment (confirmed by direct inspection, not documented anywhere):
`steps[i][player].action` responds to `steps[i-1][player].observation`, not the same
step's own observation -- see `Ceruledge-RL/specs/16c-imitation-learning.md`.

The sanitized dataset adds a `select.usable` boolean (false where the acting player
had exactly one legal option). `iter_paired_decisions` skips those -- see
`Imitation-Learning/specs/il-dataset-sanitization/`. Raw episodes have no `usable`
key, so this has no effect when reading directly from a raw zip.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pickle
import sys
import zipfile
from dataclasses import dataclass

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, os.path.join(_REPO_ROOT, "Ceruledge-RL"))
sys.path.insert(0, _IL_ROOT)

from cg_download.api import Observation, OptionType, SelectContext  # noqa: E402
from cg_download.utils import to_dataclass  # noqa: E402
from features import GameStateTracker  # noqa: E402
from observation.encoder import Word, build_observation  # noqa: E402
from observation.live_adapter import build_game_state  # noqa: E402
from prize_check import PrizeTracker  # noqa: E402

from . import action_space as asp  # noqa: E402


@dataclass
class Example:
    words: list[Word]
    option_type: OptionType
    verb_index: int | None  # set only for MAIN-context examples; index into asp.VERBS
    candidates: list[asp.Candidate]
    label_index: int  # index into `candidates`
    effect_card_id: int | None = None  # obs.select.effect.id, for scoring.condition_on_effect
    episode_name: str = ""  # for episode-level train/val splitting, never per-step


def _episode_names(zip_path: str, limit: int | None) -> list[str]:
    names = sorted(zipfile.ZipFile(zip_path).namelist())
    return names if limit is None else names[:limit]


def submitted_decks_from_steps(steps: list, n_players: int = 2) -> dict[int, list[int]]:
    """Extract each player's authoritative 60-card submission from a replay.

    Deck submission is stored as an action before ordinary option-index actions begin.
    Search the full episode rather than relying on a hardcoded step number, and fail if
    a player is missing or presents conflicting 60-card submissions.
    """
    decks: dict[int, list[int]] = {}
    for step in steps:
        for player_idx, entry in enumerate(step):
            action = entry.get("action") or []
            if len(action) != 60 or any(not isinstance(cid, int) for cid in action):
                continue
            deck = list(action)
            prior = decks.get(player_idx)
            if prior is not None and prior != deck:
                raise RuntimeError(
                    f"replay contains conflicting submitted decks for player {player_idx}"
                )
            decks[player_idx] = deck
        if len(decks) == n_players:
            break
    missing = sorted(set(range(n_players)) - set(decks))
    if missing:
        raise RuntimeError(
            "replay is missing an authoritative 60-card submission for player(s) "
            + ", ".join(map(str, missing))
        )
    return decks


def _iter_paired_entries(steps: list):
    """Yield every raw `(player, response action, preceding observation)` pairing."""
    for i in range(1, len(steps)):
        for player_idx in range(len(steps[i])):
            action = steps[i][player_idx].get("action") or []
            obs_json = steps[i - 1][player_idx].get("observation") or {}
            yield player_idx, action, obs_json


def iter_paired_decisions(steps: list):
    """Yields `(player_idx, action, prev_observation_json)` for every step-entry with a
    non-empty action and a selectable, usable previous observation.

    Centralizes the off-by-one fix confirmed by direct inspection (not documented
    anywhere in the recorded data's own schema): `steps[i][player].action` responds to
    `steps[i-1][player].observation`, not the same step's own observation. This is the
    single source of that fix -- both `extract_examples` below and any test that needs
    the same (obs, action) pairing must call this rather than re-implementing the -1
    offset, so a future edit can't fix the logic here while a separately-copied test
    loop keeps silently exercising the old, wrong pairing.

    Also the single source of the `select.usable` check: the sanitized dataset (see
    `Imitation-Learning/specs/il-dataset-sanitization/`) marks `usable=false` on any
    decision where the acting player had exactly one legal option -- no real choice to
    imitate. Raw episodes have no `usable` key, so `.get("usable", True)` is a no-op
    there and this function's behavior on raw zips is unchanged.
    """
    for player_idx, action, obs_json in _iter_paired_entries(steps):
        select = obs_json.get("select")
        if not action or not select:
            continue
        if select.get("usable", True) is False:
            continue
        yield player_idx, action, obs_json


def iter_tracker_observations(steps: list):
    """Yield every distinct off-by-one-paired observation, including observations
    excluded from imitation-learning supervision.

    Stateful observation trackers must see forced choices (``usable=false``) even
    though those choices are not useful labels. Replay files also repeat the
    non-acting player's last observation across multiple steps, so adjacent equal
    observations are collapsed to avoid applying the same delta logs more than once.
    """
    player_count = max((len(step) for step in steps), default=0)
    last_observations: list[dict | None] = [None] * player_count
    for player_idx, action, obs_json in _iter_paired_entries(steps):
        if not obs_json or obs_json == last_observations[player_idx]:
            continue
        last_observations[player_idx] = obs_json
        yield player_idx, action, obs_json


def _examples_from_episode(data: dict, name: str, max_steps: int):
    """Shared core: one `PrizeTracker` + `GameStateTracker` pair per (episode, player)
    -- same lifecycle `test_live_adapter_replay.py` already established. Trackers
    advance on every distinct observation, including forced choices excluded from
    training, so delta logs cannot be lost between emitted examples. Used by both
    `extract_examples` (raw zip) and `extract_examples_from_dir` (sanitized dir)."""
    all_steps = data["steps"]
    decks = submitted_decks_from_steps(all_steps)
    steps = all_steps[:max_steps]
    trackers = {
        i: (
            PrizeTracker(decks[i]),
            GameStateTracker(decks[i]),
            GameStateTracker(decks[1 - i]),
        )
        for i in (0, 1)
    }

    for our_idx, action, obs_json in iter_tracker_observations(steps):
        obs = to_dataclass(obs_json, Observation)
        if obs.current is None:
            continue

        prize_tracker, our_tracker, opp_tracker = trackers[our_idx]
        state = build_game_state(obs, our_idx, prize_tracker, our_tracker, opp_tracker)

        select = obs_json.get("select")
        if not action or not select or select.get("usable", True) is False:
            continue

        chosen = action[0]
        opts = obs.select.option
        if chosen >= len(opts):
            continue  # deck-phase / other action-space quirk, see spec 16c

        example = _build_example(obs, our_idx, chosen)
        if example is None:
            continue

        example.words = build_observation(state)
        example.episode_name = name
        yield example


def _safe_episode_examples(data: dict, name: str, source_label: str, max_steps: int) -> list:
    """Fully materializes one episode's examples, isolating it from the rest of the
    dataset: a handful of recorded episodes trip PrizeTracker/live-adapter invariant
    checks (e.g. inferred-vs-engine-reported prize count mismatches) that don't
    reflect a bug in the *extraction* itself, just an inconsistency in that one
    replay. Without this, a single bad episode raises out of the middle of
    `list(iter_all_examples(...))` and discards every example already extracted from
    the whole run -- not just that episode. Skips are logged so they stay visible
    rather than silently vanishing."""
    try:
        return list(_examples_from_episode(data, name, max_steps))
    except Exception as exc:
        print(f"WARNING: skipping episode {name!r} in {source_label}: {exc}", file=sys.stderr)
        return []


def extract_examples(zip_path: str, max_episodes: int | None = None, max_steps: int = 300):
    """Yields `Example`s across every episode in one raw Kaggle archive zip."""
    z = zipfile.ZipFile(zip_path)
    for name in _episode_names(zip_path, max_episodes):
        data = json.loads(z.read(name))
        yield from _safe_episode_examples(data, name, zip_path, max_steps)


def extract_examples_from_dir(day_dir: str, max_episodes: int | None = None, max_steps: int = 300):
    """Yields `Example`s across every loose per-episode `*.json` in one sanitized day
    directory (`<sanitized_root>/<day>/`, as produced by
    `build_sanitized_top_ladder_dataset.py`). `report.json` is not an episode and is
    excluded."""
    names = sorted(
        f for f in os.listdir(day_dir) if f.endswith(".json") and f != "report.json"
    )
    if max_episodes is not None:
        names = names[:max_episodes]
    for name in names:
        with open(os.path.join(day_dir, name), "rb") as handle:
            data = json.load(handle)
        yield from _safe_episode_examples(data, name, day_dir, max_steps)


def _build_example(obs: Observation, our_idx: int, chosen: int) -> Example | None:
    opts = obs.select.option
    chosen_type = opts[chosen].type
    effect_card_id = obs.select.effect.id if obs.select.effect is not None else None

    if obs.select.context == SelectContext.MAIN:
        action_map = asp.build_action_map(obs)
        if chosen_type not in action_map or chosen not in action_map[chosen_type]:
            return None  # edge case not covered by the 8-verb MAIN vocabulary
        verb_option_indices = action_map[chosen_type]
        candidates = asp.classify_candidates(obs, our_idx, verb_option_indices)
        label_index = verb_option_indices.index(chosen)
        return Example(
            words=[], option_type=chosen_type, verb_index=asp.VERB_INDEX[chosen_type],
            candidates=candidates, label_index=label_index, effect_card_id=effect_card_id,
        )

    all_indices = list(range(len(opts)))
    candidates = asp.classify_candidates(obs, our_idx, all_indices)
    return Example(
        words=[], option_type=chosen_type, verb_index=None,
        candidates=candidates, label_index=chosen, effect_card_id=effect_card_id,
    )


def _iter_raw_tree(root: str, max_episodes_per_zip: int | None, max_steps: int):
    """Yields `Example`s from every `*.zip` found under `root` (`os.walk`)."""
    for r, _dirs, files in os.walk(root):
        for fname in sorted(files):
            if fname.endswith(".zip"):
                yield from extract_examples(os.path.join(r, fname), max_episodes_per_zip, max_steps)


def _iter_sanitized_tree(root: str, max_episodes_per_zip: int | None, max_steps: int):
    """Yields `Example`s from every directory under `root` (`os.walk`) that contains
    loose per-episode `*.json` (`report.json` excluded)."""
    for r, _dirs, files in os.walk(root):
        if any(f.endswith(".json") and f != "report.json" for f in files):
            yield from extract_examples_from_dir(r, max_episodes_per_zip, max_steps)


def iter_all_examples(
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
    max_episodes_per_zip: int | None = None,
    max_steps: int = 300,
    source: str = "sanitized",
):
    """Extracts examples from raw archives, a sanitized dataset, or both.

    `source` selects which of `raw_dir` / `sanitized_dir` to read:
    - `"raw"`: every `*.zip` under `raw_dir` (e.g. `Top-ladder-data/7-12/*.zip`).
    - `"sanitized"`: every loose per-episode `*.json` under `sanitized_dir`
      (e.g. `<sanitized_root>/7-12/*.json`), respecting the `usable` mask via
      `iter_paired_decisions`. This is the default -- prefer the filtered dataset
      once it exists.
    - `"both"`: reads both. Note this double-counts any day present in both
      directories, since the sanitized set is a filtered copy of the same
      episodes -- only use `"both"` when the two directories cover
      non-overlapping days (e.g. sanitized days plus raw-only days not yet
      run through the sanitizer).
    """
    if source not in ("raw", "sanitized", "both"):
        raise ValueError(f"source must be 'raw', 'sanitized', or 'both', got {source!r}")

    if source in ("raw", "both"):
        if not raw_dir:
            raise ValueError("raw_dir is required when source is 'raw' or 'both'")
        yield from _iter_raw_tree(raw_dir, max_episodes_per_zip, max_steps)

    if source in ("sanitized", "both"):
        if not sanitized_dir:
            raise ValueError("sanitized_dir is required when source is 'sanitized' or 'both'")
        yield from _iter_sanitized_tree(sanitized_dir, max_episodes_per_zip, max_steps)


# ---- Day chunking ------------------------------------------------------------------
# Bounds peak memory to one day-chunk's examples at a time, instead of
# `iter_all_examples` materializing the whole dataset into one list. Profiling this
# session found ~23.4KB retained per Example, ~16GB for one full day (~5,035
# episodes) -- fine one (or a few) days at a time, not for many days loaded at once.


def parse_episode_limit(value: str | int | None) -> int | None:
    """Parse a CLI/API episode limit.

    Positive integers retain the existing capped behavior. ``"all"``/``"none"``
    and ``None`` mean uncapped. Both the cache builder and trainer use this one
    parser so a full cache (whose manifest records ``None``) can be requested
    exactly at training time instead of failing the staleness check against the
    trainer's historical default of 20.
    """
    if value is None:
        return None
    if isinstance(value, int):
        parsed = value
    else:
        text = str(value).strip().lower()
        if text in {"all", "none"}:
            return None
        try:
            parsed = int(text)
        except ValueError as exc:
            raise ValueError(
                f"episode limit must be a positive integer or 'all', got {value!r}"
            ) from exc
    if parsed < 1:
        raise ValueError(f"episode limit must be >= 1 or 'all', got {value!r}")
    return parsed


def _group_days(days: list[str], days_per_chunk: int) -> list[list[str]]:
    """Groups an already-sorted list of day names into consecutive groups of
    `days_per_chunk` (the last group may be shorter). Pure, no I/O."""
    if not isinstance(days_per_chunk, int) or days_per_chunk < 1:
        raise ValueError(f"days_per_chunk must be an int >= 1, got {days_per_chunk!r}")
    return [days[i:i + days_per_chunk] for i in range(0, len(days), days_per_chunk)]


def _immediate_subdirs(path: str | None) -> list[str]:
    """Sorted immediate subdirectory names of `path`, or `[]` if path is falsy or
    missing."""
    if not path or not os.path.isdir(path):
        return []
    return sorted(name for name in os.listdir(path) if os.path.isdir(os.path.join(path, name)))


def _source_labels(source: str) -> tuple[str, ...]:
    if source not in ("raw", "sanitized", "both"):
        raise ValueError(f"source must be 'raw', 'sanitized', or 'both', got {source!r}")
    return tuple(label for label in ("raw", "sanitized") if source in (label, "both"))


def _days_for_source_label(root: str | None, source_label: str) -> list[str]:
    """Return only real day directories for one source.

    Content-based discovery deliberately avoids treating infrastructure folders
    such as ``Top-ladder-data/sanitized`` or ``example-cache`` as raw days.
    """
    days: list[str] = []
    for name in _immediate_subdirs(root):
        day_dir = os.path.join(root, name)
        files = os.listdir(day_dir)
        if source_label == "raw":
            usable = any(filename.endswith(".zip") for filename in files)
        else:
            usable = any(
                filename.endswith(".json") and filename != "report.json"
                for filename in files
            )
        if usable:
            days.append(name)
    return days


def list_source_day_pairs(
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
    source: str = "sanitized",
) -> list[tuple[str, str]]:
    """Canonical sorted ``(source_label, day)`` discovery.

    Keeping the source label attached to the day is what makes ``source="both"``
    work for non-overlapping inputs instead of incorrectly requiring every day to
    exist in both trees.
    """
    roots = {"raw": raw_dir, "sanitized": sanitized_dir}
    pairs = [
        (label, day)
        for label in _source_labels(source)
        for day in _days_for_source_label(roots[label], label)
    ]
    return sorted(pairs, key=lambda pair: (pair[1], pair[0]))


def list_days(
    raw_dir: str | None = None, sanitized_dir: str | None = None, source: str = "sanitized",
) -> list[str]:
    """Sorted union of actual source days, with infrastructure directories excluded."""
    return sorted(
        {day for _label, day in list_source_day_pairs(raw_dir, sanitized_dir, source)}
    )


def iter_examples_by_day_chunk(
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
    max_episodes_per_zip: int | None = None,
    max_steps: int = 300,
    source: str = "sanitized",
    days_per_chunk: int = 1,
):
    """Day-chunked counterpart to `iter_all_examples`. Day boundaries are the
    immediate subdirectories of `raw_dir` / `sanitized_dir` -- see `list_days`.
    `source` selects which root(s) to read, with the same "raw" / "sanitized" /
    "both" semantics as `iter_all_examples`, INCLUDING the same accepted "both"
    double-counting on days present in both roots (a day present in only one root
    just contributes from that one root; this function does not change that
    existing, documented behavior).

    `days_per_chunk` (>=1) groups that many consecutive sorted day-names into one
    chunk before yielding -- e.g. `days_per_chunk=2` over days [7-12, 7-13, 7-14]
    yields chunks for [7-12,7-13] then [7-14].

    Yields `(chunk_label, examples)` once per chunk, where `chunk_label` is the
    chunk's day names joined with "+" (e.g. "7-12" or "7-12+7-13") and `examples`
    is a fully-materialized `list[Example]` for just that chunk -- nothing from one
    chunk is retained once the caller moves on to the next. A chunk with no
    matching data yields an empty list rather than being silently dropped, so
    callers can distinguish "this chunk had nothing" from "no days at all"."""
    if source not in ("raw", "sanitized", "both"):
        raise ValueError(f"source must be 'raw', 'sanitized', or 'both', got {source!r}")
    if not isinstance(days_per_chunk, int) or days_per_chunk < 1:
        raise ValueError(f"days_per_chunk must be an int >= 1, got {days_per_chunk!r}")
    if source in ("raw", "both") and not raw_dir:
        raise ValueError("raw_dir is required when source is 'raw' or 'both'")
    if source in ("sanitized", "both") and not sanitized_dir:
        raise ValueError("sanitized_dir is required when source is 'sanitized' or 'both'")

    source_pairs = set(list_source_day_pairs(raw_dir, sanitized_dir, source))
    all_days = sorted({day for _label, day in source_pairs})

    for group in _group_days(all_days, days_per_chunk):
        chunk_label = "+".join(group)
        chunk_examples: list[Example] = []
        for day in group:
            if ("raw", day) in source_pairs:
                day_dir = os.path.join(raw_dir, day)
                chunk_examples.extend(
                    _iter_raw_tree(day_dir, max_episodes_per_zip, max_steps)
                )
            if ("sanitized", day) in source_pairs:
                day_dir = os.path.join(sanitized_dir, day)
                chunk_examples.extend(
                    _iter_sanitized_tree(day_dir, max_episodes_per_zip, max_steps)
                )
        yield chunk_label, chunk_examples


# ---- Example cache -------------------------------------------------------------
# `build_example_cache.py` extracts each day exactly once (in parallel across
# episodes) and pickles the resulting Examples to `<cache_dir>/<source_label>/
# <day>.pkl` + a sibling `.manifest.json`. `iter_cached_examples_by_day_chunk`
# below is what `train.py` uses to load those chunks quickly on every outer epoch
# of an interleaved multi-epoch run, instead of paying live extraction's
# PrizeTracker/GameStateTracker/build_observation/classify_candidates cost again
# each time a chunk is revisited.

SCHEMA_VERSION = 1
"""Bump whenever `Example`/`Word`/`PokemonStatic`/`TrainerEnergyStatic`/`Candidate`
shapes change. A pickled cache built under an older schema must never be silently
loaded under a newer one -- `manifest_matches` checks this first, always, even when
no source directory is available to re-check a content fingerprint against."""


def _zip_fingerprint(zip_path: str) -> dict:
    """Cheap (stat-only, no content read) fingerprint of one raw day's archive."""
    st = os.stat(zip_path)
    return {"kind": "zip", "size": st.st_size, "mtime_ns": st.st_mtime_ns}


def _raw_day_fingerprint(day_dir: str) -> dict:
    """Cheap fingerprint of every zip in one raw day directory."""
    archives = []
    for filename in sorted(f for f in os.listdir(day_dir) if f.endswith(".zip")):
        archives.append({"name": filename, **_zip_fingerprint(os.path.join(day_dir, filename))})
    return {"kind": "raw_day", "archives": archives}


def _sanitized_dir_fingerprint(day_dir: str) -> dict:
    """Cheap metadata digest for one sanitized day; episode content is not read."""
    entries = []
    for filename in sorted(
        f for f in os.listdir(day_dir) if f.endswith(".json") and f != "report.json"
    ):
        st = os.stat(os.path.join(day_dir, filename))
        entries.append((filename, st.st_size, st.st_mtime_ns))
    digest = hashlib.sha1(repr(entries).encode("utf-8")).hexdigest()
    return {"kind": "dir", "file_count": len(entries), "digest": digest}


def _resolve_source_fingerprint(source_label: str, root: str | None, day: str) -> dict | None:
    """`None` when `root` isn't available (best-effort staleness check, skipped) or
    the day's source path doesn't exist under it."""
    if not root:
        return None
    day_dir = os.path.join(root, day)
    if source_label == "raw":
        if not os.path.isdir(day_dir):
            return None
        zips = sorted(f for f in os.listdir(day_dir) if f.endswith(".zip"))
        return _raw_day_fingerprint(day_dir) if zips else None
    if not os.path.isdir(day_dir):
        return None
    return _sanitized_dir_fingerprint(day_dir)


def cache_file_paths(cache_dir: str, source_label: str, day: str) -> tuple[str, str]:
    """`(examples_path, manifest_path)` for one `(source_label, day)` cache entry:
    `<cache_dir>/<source_label>/<day>.pkl` and `<day>.manifest.json`."""
    base = os.path.join(cache_dir, source_label, day)
    return base + ".pkl", base + ".manifest.json"


def build_manifest(
    *, source_label: str, day: str, max_episodes_per_zip: int | None, max_steps: int,
    source_fingerprint: dict, n_examples: int,
) -> dict:
    """The dict written to `<day>.manifest.json` alongside `<day>.pkl` -- everything
    needed to later decide whether that cache is still trustworthy (see
    `manifest_matches`)."""
    return {
        "schema_version": SCHEMA_VERSION,
        "source_label": source_label,
        "day": day,
        "max_episodes_per_zip": max_episodes_per_zip,
        "max_steps": max_steps,
        "source_fingerprint": source_fingerprint,
        "n_examples": n_examples,
        "built_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def manifest_matches(
    manifest: dict, *, max_episodes_per_zip: int | None, max_steps: int,
    source_fingerprint: dict | None, source_label: str | None = None,
    day: str | None = None,
) -> tuple[bool, str]:
    """Compares a loaded manifest against the parameters/fingerprint a caller is
    about to trust it under. Returns `(True, "")` on match, `(False, reason)` on
    the first mismatch found -- `reason` names exactly what differs.
    `schema_version` is checked first and always (a schema mismatch means the
    pickled objects may not even be the shape current code expects), regardless of
    whether `source_fingerprint` is supplied. If `source_fingerprint` is `None`
    (caller didn't supply the raw/sanitized dir to re-check against), the
    fingerprint comparison is skipped -- best-effort staleness checking, not a hard
    requirement, so a cache stays usable on a machine that only has the cache and
    not the multi-GB source data."""
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return False, (
            f"schema_version: cached={manifest.get('schema_version')!r}, current={SCHEMA_VERSION!r}"
        )
    if source_label is not None and manifest.get("source_label") != source_label:
        return False, (
            f"source_label: cached={manifest.get('source_label')!r}, "
            f"requested={source_label!r}"
        )
    if day is not None and manifest.get("day") != day:
        return False, f"day: cached={manifest.get('day')!r}, requested={day!r}"
    if manifest.get("max_episodes_per_zip") != max_episodes_per_zip:
        return False, (
            f"max_episodes_per_zip: cached={manifest.get('max_episodes_per_zip')!r}, "
            f"requested={max_episodes_per_zip!r}"
        )
    if manifest.get("max_steps") != max_steps:
        return False, f"max_steps: cached={manifest.get('max_steps')!r}, requested={max_steps!r}"
    if source_fingerprint is not None and manifest.get("source_fingerprint") != source_fingerprint:
        return False, (
            f"source_fingerprint: cached={manifest.get('source_fingerprint')!r}, "
            f"current={source_fingerprint!r}"
        )
    return True, ""


def _cached_entry_pairs(cache_dir: str, source: str) -> set[tuple[str, str]]:
    """Discover cache entries from either sibling file.

    Including manifest-only and pickle-only entries lets the strict validation
    below report the missing counterpart rather than silently hiding an
    interrupted build from the inventory.
    """
    pairs: set[tuple[str, str]] = set()
    for label in _source_labels(source):
        label_dir = os.path.join(cache_dir, label)
        if not os.path.isdir(label_dir):
            continue
        for filename in os.listdir(label_dir):
            if filename.endswith(".pkl"):
                pairs.add((label, filename[:-len(".pkl")]))
            elif filename.endswith(".manifest.json"):
                pairs.add((label, filename[:-len(".manifest.json")]))
    return pairs


def resolve_cached_source_day_pairs(
    cache_dir: str,
    source: str = "sanitized",
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
) -> list[tuple[str, str]]:
    """Resolve and validate the source/day inventory a cached run must consume.

    When a live source root exists, it is authoritative: every discovered source
    day must have both cache siblings. If a root is unavailable, cache-only mode
    uses the entries declared under that source label. This permits copying just
    the cache to a training machine while preventing a partial cache from silently
    reducing a run whenever the source dataset is present for comparison.
    """
    labels = _source_labels(source)
    roots = {"raw": raw_dir, "sanitized": sanitized_dir}
    cached_pairs = _cached_entry_pairs(cache_dir, source)
    required_pairs: set[tuple[str, str]] = set()

    for label in labels:
        root = roots[label]
        if root and os.path.isdir(root):
            label_pairs = {
                (label, day) for day in _days_for_source_label(root, label)
            }
        else:
            label_pairs = {pair for pair in cached_pairs if pair[0] == label}
        if not label_pairs:
            location = root if root and os.path.isdir(root) else os.path.join(cache_dir, label)
            raise RuntimeError(
                f"no {label} source/cache days found under {location!r} "
                f"for source={source!r}"
            )
        required_pairs.update(label_pairs)

    for label, day in sorted(required_pairs):
        examples_path, manifest_path = cache_file_paths(cache_dir, label, day)
        if not os.path.isfile(examples_path):
            raise RuntimeError(
                f"missing cache pickle for {label}/{day} at {examples_path!r}; "
                "run build_example_cache.py first"
            )
        if not os.path.isfile(manifest_path):
            raise RuntimeError(
                f"missing cache manifest for {label}/{day} at {manifest_path!r}; "
                "run build_example_cache.py first"
            )

    return sorted(required_pairs, key=lambda pair: (pair[1], pair[0]))


def load_cached_source_day(
    cache_dir: str,
    source_label: str,
    day: str,
    *,
    max_episodes_per_zip: int | None,
    max_steps: int,
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
) -> tuple[list[Example], dict]:
    """Load and strictly validate one cached source/day entry.

    This is the common primitive for day-chunk iteration and the IL trainer's
    resumable mini-epochs. Returning the manifest lets callers bind generated
    split/checkpoint artifacts to the exact cache inventory they came from.
    """
    if source_label not in ("raw", "sanitized"):
        raise ValueError(f"unknown source label: {source_label!r}")
    examples_path, manifest_path = cache_file_paths(cache_dir, source_label, day)
    if not os.path.isfile(examples_path) or not os.path.isfile(manifest_path):
        raise RuntimeError(
            f"incomplete cache for {source_label}/{day}; run build_example_cache.py first"
        )

    with open(manifest_path) as handle:
        manifest = json.load(handle)
    root = raw_dir if source_label == "raw" else sanitized_dir
    source_fingerprint = _resolve_source_fingerprint(source_label, root, day)
    ok, reason = manifest_matches(
        manifest,
        max_episodes_per_zip=max_episodes_per_zip,
        max_steps=max_steps,
        source_fingerprint=source_fingerprint,
        source_label=source_label,
        day=day,
    )
    if not ok:
        raise RuntimeError(
            f"stale cache for {source_label}/{day}: {reason}; "
            "rerun build_example_cache.py"
        )

    with open(examples_path, "rb") as handle:
        examples = pickle.load(handle)
    if not isinstance(examples, list):
        raise RuntimeError(
            f"invalid cache payload for {source_label}/{day}: expected list, "
            f"got {type(examples).__name__}"
        )
    expected_count = manifest.get("n_examples")
    if expected_count != len(examples):
        raise RuntimeError(
            f"invalid cache payload for {source_label}/{day}: "
            f"manifest n_examples={expected_count!r}, loaded={len(examples)}"
        )
    return examples, manifest


def iter_cached_source_days(
    cache_dir: str,
    source: str = "sanitized",
    max_episodes_per_zip: int | None = None,
    max_steps: int = 300,
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
):
    """Yield ``(source_label, day, examples, manifest)`` one cache file at a time."""
    pairs = resolve_cached_source_day_pairs(
        cache_dir, source, raw_dir=raw_dir, sanitized_dir=sanitized_dir,
    )
    for label, day in pairs:
        examples, manifest = load_cached_source_day(
            cache_dir, label, day,
            max_episodes_per_zip=max_episodes_per_zip,
            max_steps=max_steps,
            raw_dir=raw_dir,
            sanitized_dir=sanitized_dir,
        )
        yield label, day, examples, manifest


def iter_cached_examples_by_day_chunk(
    cache_dir: str,
    source: str = "sanitized",
    days_per_chunk: int = 1,
    max_episodes_per_zip: int | None = None,
    max_steps: int = 300,
    raw_dir: str | None = None,
    sanitized_dir: str | None = None,
):
    """Fast counterpart to `iter_examples_by_day_chunk`: loads pre-built per-day
    caches (`build_example_cache.py`) instead of extracting live.

    When a source root is available it defines the required day set, so a partial
    cache fails loudly. When a source root is unavailable, the corresponding
    cache inventory defines the set (cache-only cluster operation). Cache day
    granularity is always one day, independent of `days_per_chunk`.

    Yields `(chunk_label, examples)` per `days_per_chunk`-sized group of cached
    days, examples freshly unpickled each call (nothing retained between chunks).

    Raises `RuntimeError` if a needed `(source_label, day)` has no cache file at
    all (day not yet cached -- run `build_example_cache.py`), or if a cache file's
    manifest doesn't match this call's `max_episodes_per_zip` / `max_steps` /
    schema version, or (when `raw_dir`/`sanitized_dir` given) its
    `source_fingerprint` no longer matches the live source data (stale cache --
    rerun `build_example_cache.py`, optionally with `--force`)."""
    _source_labels(source)
    if not isinstance(days_per_chunk, int) or days_per_chunk < 1:
        raise ValueError(f"days_per_chunk must be an int >= 1, got {days_per_chunk!r}")

    required_pairs = set(
        resolve_cached_source_day_pairs(
            cache_dir, source, raw_dir=raw_dir, sanitized_dir=sanitized_dir
        )
    )
    all_days = sorted({day for _label, day in required_pairs})
    source_labels = _source_labels(source)
    root_by_label = {"raw": raw_dir, "sanitized": sanitized_dir}

    for group in _group_days(all_days, days_per_chunk):
        chunk_label = "+".join(group)
        chunk_examples: list[Example] = []
        for day in group:
            for label in source_labels:
                if (label, day) not in required_pairs:
                    continue
                day_examples, _manifest = load_cached_source_day(
                    cache_dir, label, day,
                    max_episodes_per_zip=max_episodes_per_zip,
                    max_steps=max_steps,
                    raw_dir=root_by_label["raw"],
                    sanitized_dir=root_by_label["sanitized"],
                )
                chunk_examples.extend(day_examples)

        yield chunk_label, chunk_examples
