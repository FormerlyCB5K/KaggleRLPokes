"""Independent reference verifier for a top-ladder inventory run.

Unlike analyze_top_ladder_cards.py, this script ignores visualization data and finds
root actions that are exactly 60 positive integers. It recomputes all catalog frequency
aggregates and checks deterministic first/middle/last plus seeded sample episodes.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import analyze_top_ladder_cards as primary


_ROOT_DECK_RE = re.compile(
    rb'"action"\s*:\s*'
    rb'(\[\s*\d+(?:\s*,\s*\d+){59}\s*\])'
)
_EPISODE_ID_RE = re.compile(rb'"EpisodeId"\s*:\s*(\d+)')


def root_decks(raw: bytes) -> tuple[tuple[int, ...], tuple[int, ...]]:
    matches = _ROOT_DECK_RE.findall(raw)
    decks = [tuple(json.loads(match)) for match in matches]
    if len(decks) != 2:
        raise AssertionError(f"expected exactly two root 60-ID actions, found {len(decks)}")
    for deck in decks:
        if len(deck) != 60 or any(type(card_id) is not int or card_id <= 0 for card_id in deck):
            raise AssertionError("reference extractor found an invalid deck")
    return decks[0], decks[1]


def expected_samples(names: list[str]) -> set[str]:
    if not names:
        return set()
    indices = {0, len(names) // 2, len(names) - 1}
    rng = random.Random(120712)
    indices.update(rng.sample(range(len(names)), min(10, len(names))))
    return {names[index] for index in indices}


def verify(archives: list[Path], output_dir: Path) -> dict:
    catalog = json.loads((output_dir / "top_ladder_card_catalog.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    artifact_cards = {int(card["card_id"]): card for card in catalog["cards"]}

    games: defaultdict[int, set[int]] = defaultdict(set)
    decks_with: Counter[int] = Counter()
    copies: Counter[int] = Counter()
    minimum: dict[int, int] = {}
    maximum: dict[int, int] = {}

    checked_samples: list[str] = []
    seen_episodes: dict[int, tuple[tuple[int, ...], tuple[int, ...]]] = {}
    json_members = 0
    duplicate_episodes = 0
    for archive in sorted(archives, key=lambda path: path.as_posix()):
        with zipfile.ZipFile(archive) as bundle:
            names = sorted(name for name in bundle.namelist() if name.lower().endswith(".json"))
            json_members += len(names)
            sample_names = expected_samples(names)
            for name in names:
                raw = bundle.read(name)
                decks = root_decks(raw)
                episode_match = _EPISODE_ID_RE.search(raw[: min(len(raw), 250_000)])
                if not episode_match:
                    raise AssertionError(f"reference verifier requires EpisodeId: {name}")
                episode_id = int(episode_match.group(1))
                prior = seen_episodes.get(episode_id)
                if prior is not None:
                    if prior != decks:
                        raise AssertionError(f"episode-ID content collision: {episode_id}")
                    duplicate_episodes += 1
                    continue
                seen_episodes[episode_id] = decks
                for deck in decks:
                    counts = Counter(deck)
                    for card_id, count in counts.items():
                        games[card_id].add(episode_id)
                        decks_with[card_id] += 1
                        copies[card_id] += count
                        minimum[card_id] = min(minimum.get(card_id, count), count)
                        maximum[card_id] = max(maximum.get(card_id, count), count)
                if name in sample_names:
                    visual = primary.extract_episode(
                        raw,
                        archive_path=archive.as_posix(),
                        member_name=name,
                        date=primary.dataset_date(archive),
                    ).decks
                    if visual != decks:
                        raise AssertionError(f"sample deck mismatch: {archive.name}:{name}")
                    checked_samples.append(f"{archive.name}:{name}")

    reference_ids = set(copies)
    if reference_ids != set(artifact_cards):
        raise AssertionError(
            f"card-ID union mismatch: missing={sorted(reference_ids - set(artifact_cards))}, "
            f"extra={sorted(set(artifact_cards) - reference_ids)}"
        )
    for card_id in sorted(reference_ids):
        card = artifact_cards[card_id]
        expected = {
            "games_with_card": len(games[card_id]),
            "decks_with_card": decks_with[card_id],
            "total_copies": copies[card_id],
            "min_copies_in_containing_deck": minimum[card_id],
            "max_copies_in_containing_deck": maximum[card_id],
        }
        actual = {key: card[key] for key in expected}
        if actual != expected:
            raise AssertionError(f"aggregate mismatch for card {card_id}: {actual} != {expected}")

    summary = manifest["summary"]
    unique_episode_count = len(seen_episodes)
    if summary["unique_episodes"] != unique_episode_count:
        raise AssertionError("manifest unique episode count differs from reference")
    if summary["deck_instances"] != 2 * unique_episode_count:
        raise AssertionError("manifest deck count differs from reference")
    if summary["submitted_card_copies"] != 120 * unique_episode_count:
        raise AssertionError("manifest submitted-card total differs from reference")

    class_sets = {}
    for card_class in ("pokemon", "trainer", "energy"):
        class_sets[card_class] = set(json.loads(
            (output_dir / f"{card_class}_ids.json").read_text(encoding="utf-8")
        ))
    if any(class_sets[left] & class_sets[right]
           for left, right in (("pokemon", "trainer"), ("pokemon", "energy"), ("trainer", "energy"))):
        raise AssertionError("stratified ID lists overlap")
    if set().union(*class_sets.values()) != reference_ids:
        raise AssertionError("stratified ID-list union differs from reference card union")

    return {
        "archives_checked": len(archives),
        "json_members": json_members,
        "unique_episodes": unique_episode_count,
        "duplicate_episodes": duplicate_episodes,
        "deck_instances": 2 * unique_episode_count,
        "submitted_card_copies": 120 * unique_episode_count,
        "unique_card_ids": len(reference_ids),
        "sample_members_checked": sorted(checked_samples),
        "per_card_aggregates_checked": len(reference_ids),
        "stratified_lists_disjoint_and_complete": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = verify([archive.resolve() for archive in args.archive], args.output_dir.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
