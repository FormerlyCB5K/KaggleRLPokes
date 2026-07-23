"""Focused tests for Spec-12b intake/crosswalk tooling."""
from __future__ import annotations

import json
import unittest

import build_part_b_inputs as tool
import build_part_b_schema as schema_tool


class CommentStripTests(unittest.TestCase):
    def test_comments_are_removed_and_lines_preserved(self):
        source = 'CreateCard(1, "//"); // CreateCard(2)\n/* CreateCard(3)\n */ CreateCard(4);\n'
        stripped = tool.strip_cpp_comments(source)
        self.assertIn("CreateCard(1", stripped)
        self.assertNotIn("CreateCard(2", stripped)
        self.assertNotIn("CreateCard(3", stripped)
        self.assertIn("CreateCard(4", stripped)
        self.assertEqual(source.count("\n"), stripped.count("\n"))

    def test_unterminated_block_comment_fails(self):
        with self.assertRaises(ValueError):
            tool.strip_cpp_comments("/* never closed")


class SourceUniverseTests(unittest.TestCase):
    def test_active_source_universe(self):
        locations = tool.source_card_locations()
        self.assertEqual(1267, len(locations))
        self.assertEqual(set(range(1, 1268)), set(locations))
        self.assertEqual(1556, tool.source_attack_count())

    def test_crosswalk_is_complete(self):
        rows, issues, summary = tool.build_crosswalk()
        self.assertEqual(232, len(rows))
        self.assertEqual(0, summary["unresolved"])
        self.assertEqual([], issues)
        self.assertEqual({"energy": 18, "pokemon": 115, "trainer": 99}, summary["class_counts"])

    def test_source_blocks_reconcile_with_source_universe(self):
        blocks = tool.source_card_blocks()
        self.assertEqual(set(range(1, 1268)), set(blocks))
        self.assertEqual(1556, sum(
            segment["kind"] == "attack"
            for block in blocks.values()
            for segment in block["segments"]
        ))


class WorklistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards, cls.effects, cls.summary, cls.issues = tool.build_worklist()

    def test_worklist_has_exact_card_and_class_coverage(self):
        catalog = json.loads(tool.CATALOG.read_text(encoding="utf-8"))
        expected_ids = {int(card["card_id"]) for card in catalog["cards"]}
        actual_ids = {card["card_id"] for card in self.cards}
        self.assertEqual(expected_ids, actual_ids)
        self.assertEqual(232, len(self.cards))
        self.assertEqual(
            {"energy": 18, "pokemon": 115, "trainer": 99},
            self.summary["cards_by_class"],
        )
        self.assertEqual([], self.issues)

    def test_every_effect_is_unique_and_owned_once(self):
        effect_ids = [effect["effect_id"] for effect in self.effects]
        dossier_ids = [
            effect["effect_id"]
            for card in self.cards
            for effect in card["effects"]
        ]
        self.assertEqual(len(effect_ids), len(set(effect_ids)))
        self.assertEqual(effect_ids, dossier_ids)
        self.assertEqual(len(self.effects), self.summary["effects"])

    def test_batches_are_complete_class_specific_and_bounded(self):
        manifest = tool.build_batches(self.cards)
        self.assertEqual(12, manifest["batch_count"])
        batched_ids = []
        card_class = {card["card_id"]: card["card_class"] for card in self.cards}
        for batch in manifest["batches"]:
            self.assertLessEqual(len(batch["card_ids"]), 20)
            self.assertTrue(batch["card_ids"])
            self.assertTrue(all(
                card_class[card_id] == batch["card_class"]
                for card_id in batch["card_ids"]
            ))
            batched_ids.extend(batch["card_ids"])
        self.assertEqual(len(batched_ids), len(set(batched_ids)))
        self.assertEqual(set(card_class), set(batched_ids))


class MechanicInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = schema_tool.build_mechanic_inventory()

    def test_inventory_covers_every_atomic_effect(self):
        summary = self.inventory["summary"]
        self.assertEqual(314, summary["effect_rows"])
        signature_ids = [
            effect_id
            for signature in self.inventory["engine_signature_inventory"]
            for effect_id in signature["effect_ids"]
        ]
        self.assertEqual(314, len(signature_ids))
        self.assertEqual(314, len(set(signature_ids)))

    def test_original_encoder_coverage_is_frozen(self):
        coverage = self.inventory["original_encoder"]["meta_coverage"]
        self.assertEqual(201, coverage["parsed_effects"])
        self.assertEqual(71, coverage["parsed_effects_with_nonzero_generic_tags"])
        self.assertEqual(76, coverage["nonempty_parsed_effects_with_all_zero_generic_tags"])
        self.assertEqual(109, coverage["no_general_parser"])
        self.assertEqual(4, coverage["not_applicable"])

    def test_every_engine_method_has_a_structural_role(self):
        self.assertEqual([], self.inventory["summary"]["unclassified_engine_methods"])

    def test_every_effect_has_a_schema_family_home(self):
        worklist, issues = schema_tool.build_family_worklist()
        self.assertEqual([], issues)
        self.assertEqual(314, worklist["summary"]["effects"])
        self.assertEqual(314, worklist["summary"]["mapped"])
        self.assertEqual(0, worklist["summary"]["unmapped"])

    def test_schema_categories_are_unique(self):
        for values in (
            schema_tool.PROGRAM_NODE_KINDS,
            schema_tool.OPERATION_KINDS,
            schema_tool.EXPRESSION_KINDS,
            schema_tool.OBSERVABILITY_KINDS,
            schema_tool.SCHEMA_FAMILIES,
        ):
            self.assertEqual(len(values), len(set(values)))

    def test_real_program_examples_and_nearby_negatives(self):
        report = schema_tool.build_schema_validation_report()
        self.assertTrue(all(report["checks"].values()))

    def test_observation_matrix_has_fast_and_honest_paths(self):
        matrix = schema_tool.build_observation_matrix()
        classes = {item["observability"] for item in matrix["inputs"]}
        self.assertIn("observation_direct", classes)
        self.assertIn("observation_derived", classes)
        self.assertIn("public_history", classes)
        self.assertIn("hidden_information", classes)
        self.assertIn("stochastic", classes)
        self.assertTrue(any("Never simulate" in rule for rule in matrix["runtime_policy"]))
        self.assertTrue(all(schema_tool.probe_recorded_observation()["checks"].values()))

    def test_only_approved_lossiness_exception_is_registered(self):
        register = schema_tool.build_approved_approximations()
        self.assertEqual(1, len(register["approximations"]))
        self.assertEqual("HR-B05-002", register["approximations"][0]["human_review_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
