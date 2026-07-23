"""Focused validation for the Spec-12b09 closure artifacts."""
from __future__ import annotations

import csv
import io
import json
import unittest

import build_dynamic_formula_registry as dynamic
import build_part_b_closure as closure


class PartBClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts, cls.validation = closure.build_all()
        cls.ledger = json.loads(cls.artifacts[closure.repo_path(closure.LEDGER)].decode("utf-8"))
        cls.diff = json.loads(cls.artifacts[closure.repo_path(closure.SEMANTIC_DIFF)].decode("utf-8"))
        cls.handoff = json.loads(cls.artifacts[closure.repo_path(closure.HANDOFF)].decode("utf-8"))

    def test_exact_card_effect_and_verdict_counts(self):
        self.assertEqual("passed", self.validation["status"])
        self.assertEqual(232, self.ledger["counts"]["cards"])
        self.assertEqual({"energy": 18, "pokemon": 115, "trainer": 99}, self.ledger["counts"]["card_classes"])
        self.assertEqual(314, self.ledger["counts"]["effects"])
        self.assertEqual({"engine_baked": 10, "generic_exact": 23, "ordinary_field": 54, "override_dynamic": 79, "override_static": 148}, self.ledger["counts"]["verdicts"])

    def test_catalog_worklist_ledger_and_handoff_sets_are_equal(self):
        self.assertTrue(self.validation["checks"]["card_sets_equal_catalog_worklist_crosswalk_ledger_handoff"])
        self.assertTrue(self.validation["checks"]["effect_sets_equal_worklist_ledger_handoff"])
        self.assertEqual(232, len({card["card_id"] for card in self.handoff["cards"]}))
        self.assertEqual(314, len({effect["effect_id"] for card in self.handoff["cards"] for effect in card["effects"]}))

    def test_semantic_diff_is_complete_and_human_readable(self):
        self.assertEqual(314, self.diff["summary"]["effect_rows"])
        self.assertEqual(237, self.diff["summary"]["changed"])
        self.assertEqual(77, self.diff["summary"]["unchanged_or_delegated"])
        self.assertTrue(all(item["change_explanation"] for item in self.diff["effects"]))
        rows = list(csv.DictReader(io.StringIO(self.artifacts[closure.repo_path(closure.SEMANTIC_DIFF_CSV)].decode("utf-8-sig"))))
        self.assertEqual(314, len(rows))
        self.assertEqual({str(item["effect_id"]) for item in self.diff["effects"]}, {row["effect_id"] for row in rows})

    def test_dynamic_formulas_join_and_serialized_scenarios_reexecute(self):
        self.assertTrue(self.validation["checks"]["formula_keys_close_exact_queue"])
        self.assertTrue(self.validation["checks"]["dynamic_effects_equal_formula_effects"])
        dynamic_effects = [effect for card in self.handoff["cards"] for effect in card["effects"] if effect["verdict"] == "override_dynamic"]
        self.assertEqual(79, len(dynamic_effects))
        for effect in dynamic_effects:
            self.assertIsNotNone(effect["formula"])
            for scenario in effect["formula"]["scenarios"]:
                self.assertEqual(scenario["expected_raw_output"], dynamic.evaluate_formula(effect["formula"]["formula_key"], scenario["inputs"]))

    def test_every_effect_has_passed_engine_evidence(self):
        self.assertTrue(self.validation["checks"]["all_engine_evidence_linked"])
        effects = [effect for card in self.ledger["cards"] for effect in card.get("effects", [])]
        tera = [effect for effect in effects if ":tera:" in effect["effect_id"]]
        self.assertEqual(4, len(tera))
        self.assertTrue(all(effect["engine"]["source_path"] and effect["engine"]["source_line_start"] for effect in tera))
        self.assertTrue(all(effect["validation"]["status"] == "passed" for effect in effects))

    def test_human_reviews_and_approximation_reconcile(self):
        self.assertTrue(self.validation["checks"]["human_reviews_all_resolved"])
        self.assertTrue(self.validation["checks"]["human_review_triggers_reconcile"])
        self.assertEqual(9, self.validation["counts"]["human_reviews"])
        self.assertEqual([], self.validation["review_reconciliation"]["pending_ids"])
        approximations = closure.load_json(closure.APPROXIMATIONS)["approximations"]
        self.assertEqual(["HR-B05-002"], [item["human_review_id"] for item in approximations])

    def test_clean_room_handoff_has_every_required_override_input(self):
        self.assertEqual("ready_for_part_c", self.handoff["status"])
        self.assertEqual(0, self.handoff["human_review"]["unresolved"])
        self.assertEqual(79, self.handoff["counts"]["embedded_dynamic_formulas"])
        self.assertTrue(self.validation["checks"]["handoff_clean_room_fields_complete"])
        for card in self.handoff["cards"]:
            for effect in card["effects"]:
                if effect["verdict"] == "override_dynamic":
                    self.assertTrue(all(item["name"] and item["source"] and item["missing_policy"] for item in effect["formula"]["inputs"]))

    def test_artifacts_are_utf8_parseable_and_byte_deterministic(self):
        second, second_validation = closure.build_all()
        self.assertEqual("passed", second_validation["status"])
        self.assertEqual(self.artifacts, second)
        self.assertEqual(8, len(self.artifacts))
        for relative, data in self.artifacts.items():
            self.assertEqual(data, (closure.REPO_ROOT / relative).read_bytes(), relative)
            if relative.endswith(".json"):
                json.loads(data.decode("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
