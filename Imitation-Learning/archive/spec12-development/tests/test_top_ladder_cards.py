"""Focused tests for analyze_top_ladder_cards.py."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import analyze_top_ladder_cards as inv


def deck(start: int = 1) -> list[int]:
    return [start + (index % 8) for index in range(inv.DECK_SIZE)]


def episode_bytes(
    left: list | None = None,
    right: list | None = None,
    *,
    episode_id: int = 123,
    root_left: list | None = None,
    root_right: list | None = None,
    extra_root_left: bool = False,
) -> bytes:
    left = deck(1) if left is None else left
    right = deck(20) if right is None else right
    root_left = left if root_left is None else root_left
    root_right = right if root_right is None else root_right
    steps = [
        [
            {"action": [], "visualize": [{"action": [left, right]}]},
            {"action": []},
        ],
        [{"action": root_left}, {"action": root_right}],
    ]
    if extra_root_left:
        steps.append([{"action": root_left}, {"action": []}])
    payload = {
        "id": f"fixture-{episode_id}",
        "info": {"EpisodeId": episode_id},
        "steps": steps,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def extract(raw: bytes) -> inv.EpisodeRecord:
    return inv.extract_episode(
        raw,
        archive_path="fixture.zip",
        member_name="123.json",
        date="2026-07-12",
    )


class ExtractionTests(unittest.TestCase):
    def assert_code(self, code: str, raw: bytes) -> None:
        with self.assertRaises(inv.ExtractionError) as caught:
            extract(raw)
        self.assertEqual(code, caught.exception.code)

    def test_valid_episode_preserves_multiplicity(self):
        result = extract(episode_bytes())
        self.assertEqual(2, len(result.decks))
        self.assertEqual(60, len(result.decks[0]))
        self.assertEqual(8, result.decks[0].count(1))
        self.assertEqual("episode:123", result.episode_key)

    def test_whitespace_in_json_arrays_is_accepted(self):
        spaced = json.dumps(json.loads(episode_bytes())).encode("utf-8")
        result = extract(spaced)
        self.assertEqual(60, len(result.decks[0]))

    def test_invalid_json(self):
        self.assert_code("invalid_json", episode_bytes()[:-1])

    def test_missing_visualization(self):
        raw = episode_bytes().replace(b'"visualize"', b'"not_visualize"')
        self.assert_code("missing_visualize", raw)

    def test_bad_deck_lengths(self):
        self.assert_code("invalid_deck_length", episode_bytes(left=deck()[:-1]))
        self.assert_code("invalid_deck_length", episode_bytes(left=deck() + [1]))

    def test_bad_card_id_types_and_values(self):
        invalid = deck()
        invalid[0] = "1"
        self.assert_code("non_integer_card_id", episode_bytes(left=invalid))
        invalid = deck()
        invalid[0] = True
        self.assert_code("boolean_card_id", episode_bytes(left=invalid))
        invalid = deck()
        invalid[0] = 0
        self.assert_code("non_positive_card_id", episode_bytes(left=invalid))

    def test_redundant_source_mismatch(self):
        self.assert_code(
            "deck_source_mismatch",
            episode_bytes(root_left=list(reversed(deck()))),
        )

    def test_duplicate_root_candidate(self):
        self.assert_code("duplicate_deck_submission", episode_bytes(extra_root_left=True))

    def test_identical_player_decks_require_two_root_actions(self):
        same = deck()
        result = extract(episode_bytes(left=same, right=same))
        self.assertEqual(result.decks[0], result.decks[1])


class AggregationTests(unittest.TestCase):
    def record(self, episode_id: int, left: list[int], right: list[int]) -> inv.EpisodeRecord:
        return inv.EpisodeRecord(
            episode_key=f"episode:{episode_id}",
            episode_id=episode_id,
            fallback_id=None,
            dataset_date="2026-07-12",
            archive_path="fixture.zip",
            member_name=f"{episode_id}.json",
            decks=(tuple(left), tuple(right)),
        )

    def test_game_deck_and_copy_counts_are_distinct(self):
        left = [1] * 4 + [2] * 56
        right = [1] * 2 + [3] * 58
        metadata = {
            1: {"card_id": 1, "card_name": "A", "card_class": "pokemon", "subtype": "Basic Pokémon"},
            2: {"card_id": 2, "card_name": "B", "card_class": "trainer", "subtype": "Item"},
            3: {"card_id": 3, "card_name": "C", "card_class": "energy", "subtype": "Basic Energy"},
        }
        cards, issues, summary = inv.aggregate_cards([self.record(1, left, right)], metadata)
        by_id = {card["card_id"]: card for card in cards}
        self.assertFalse(issues)
        self.assertEqual(1, by_id[1]["games_with_card"])
        self.assertEqual(2, by_id[1]["decks_with_card"])
        self.assertEqual(6, by_id[1]["total_copies"])
        self.assertEqual(2, by_id[1]["min_copies_in_containing_deck"])
        self.assertEqual(4, by_id[1]["max_copies_in_containing_deck"])
        self.assertEqual(120, summary["submitted_card_copies"])

    def test_unknown_card_is_retained_and_reported(self):
        cards, issues, _ = inv.aggregate_cards(
            [self.record(1, [999] * 60, [999] * 60)], {}
        )
        self.assertEqual([999], [card["card_id"] for card in cards])
        self.assertEqual("unresolved", cards[0]["card_class"])
        self.assertEqual("unresolved_card_id", issues[0]["code"])


class DeterminismTests(unittest.TestCase):
    def test_artifacts_are_byte_deterministic(self):
        cards = [{
            "card_id": 1,
            "card_name": "Basic Energy",
            "card_class": "energy",
            "subtype": "Basic Energy",
            "metadata_resolved": True,
            "dataset_dates": ["2026-07-12"],
            "source_archives": ["fixture.zip"],
            "games_with_card": 1,
            "decks_with_card": 1,
            "total_copies": 60,
            "min_copies_in_containing_deck": 60,
            "max_copies_in_containing_deck": 60,
            "first_dataset_date": "2026-07-12",
            "last_dataset_date": "2026-07-12",
            "per_date": {"2026-07-12": {"games_with_card": 1, "decks_with_card": 1, "total_copies": 60}},
        }]
        summary = {
            "unique_episodes": 1,
            "deck_instances": 2,
            "submitted_card_copies": 120,
            "unique_card_ids": 1,
            "cards_by_class": {"energy": 1},
            "cards_by_subtype": {"Basic Energy": 1},
        }
        archive = [{
            "path": "fixture.zip", "dataset_date": "2026-07-12", "size_bytes": 1,
            "sha256": "0" * 64, "zip_members": 1, "json_members": 1,
            "accepted_unique_episodes": 1, "duplicate_episodes": 0,
            "rejected_json_members": 0, "non_json_members": 0,
        }]
        first = inv.build_artifacts(
            cards=cards, issues=[], summary=summary, archive_manifests=archive,
            card_csv=inv.DEFAULT_CARD_CSV, argv=["fixture"],
        )
        second = inv.build_artifacts(
            cards=cards, issues=[], summary=summary, archive_manifests=archive,
            card_csv=inv.DEFAULT_CARD_CSV, argv=["fixture"],
        )
        self.assertEqual(first, second)
        self.assertEqual(
            {name: hashlib.sha256(data).hexdigest() for name, data in first.items()},
            {name: hashlib.sha256(data).hexdigest() for name, data in second.items()},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
