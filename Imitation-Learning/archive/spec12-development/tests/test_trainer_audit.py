"""Focused validation for Spec-12b06 Trainer audit artifacts."""
from __future__ import annotations

import json
import unittest

import build_trainer_audit as audit


class TrainerAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batches = {}
        cls.effects = {}
        for number in range(1, 6):
            batch_id = f"trainer-{number:02d}"
            batch, issues = audit.build_batch(batch_id)
            if issues:
                raise AssertionError(f"{batch_id}: {issues}")
            cls.batches[batch_id] = batch
            cls.effects[batch_id] = {
                effect["effect_id"]: effect
                for card in batch["cards"]
                for effect in card["effects"]
            }

    def test_batch_counts_verdicts_and_formula_ownership(self):
        expected = {
            "trainer-01": (20, 5, {"engine_baked": 1, "override_dynamic": 5, "override_static": 14}),
            "trainer-02": (20, 6, {"engine_baked": 1, "override_dynamic": 6, "override_static": 13}),
            "trainer-03": (20, 5, {"engine_baked": 1, "override_dynamic": 5, "override_static": 14}),
            "trainer-04": (20, 5, {"engine_baked": 2, "override_dynamic": 5, "override_static": 13}),
            "trainer-05": (19, 3, {"engine_baked": 3, "override_dynamic": 3, "override_static": 13}),
        }
        for batch_id, (cards, formulas, verdicts) in expected.items():
            batch = self.batches[batch_id]
            self.assertEqual("complete", batch["status"])
            self.assertEqual(cards, batch["summary"]["cards"])
            self.assertEqual(cards, batch["summary"]["effects"])
            self.assertEqual(verdicts, batch["summary"]["verdicts"])
            queue = batch["formula_queue"]
            self.assertEqual(formulas, len(queue))
            self.assertTrue(all(item["owner"] == "B08" for item in queue))
            self.assertTrue(all(item["required_inputs"] for item in queue))

    def test_every_effect_has_exact_source_program_and_evidence(self):
        for batch_id, effects in self.effects.items():
            evidence = json.loads(
                (audit.OUTPUT / f"{batch_id}-recorded-engine-evidence.json").read_text(encoding="utf-8")
            )
            self.assertTrue(evidence["checks"]["full_dataset_scan_complete"])
            self.assertEqual(15018, evidence["members_read"])
            for effect_id, effect in effects.items():
                self.assertTrue(effect["text"])
                self.assertEqual(64, len(effect["engine"]["chain_sha256"]))
                self.assertTrue(effect["program"])
                self.assertEqual("passed", effect["validation"]["status"])
                self.assertEqual("complete", effect["audit_status"])
                self.assertEqual(
                    len(evidence["samples"][effect_id]),
                    evidence["coverage"]["sample_counts"][effect_id],
                )

    def test_global_trainer_union_subtypes_and_formulas_are_exact(self):
        worklist = json.loads(audit.WORKLIST.read_text(encoding="utf-8"))
        expected_cards = {
            card["card_id"] for card in worklist["cards"] if card["card_class"] == "trainer"
        }
        expected_effects = {
            effect["effect_id"]
            for card in worklist["cards"] if card["card_class"] == "trainer"
            for effect in card["effects"]
        }
        actual_cards = [card_id for batch in self.batches.values() for card_id in batch["card_ids"]]
        actual_effects = [effect_id for effects in self.effects.values() for effect_id in effects]
        formula_keys = [item["formula_key"] for batch in self.batches.values() for item in batch["formula_queue"]]
        subtype_counts = {}
        for batch in self.batches.values():
            for card in batch["cards"]:
                subtype_counts[card["subtype"]] = subtype_counts.get(card["subtype"], 0) + 1
        self.assertEqual(99, len(expected_cards))
        self.assertEqual(99, len(expected_effects))
        self.assertEqual(expected_cards, set(actual_cards))
        self.assertEqual(expected_effects, set(actual_effects))
        self.assertEqual(len(actual_cards), len(set(actual_cards)))
        self.assertEqual(len(actual_effects), len(set(actual_effects)))
        self.assertEqual({"Item": 32, "Pokémon Tool": 11, "Stadium": 17, "Supporter": 39}, subtype_counts)
        self.assertEqual(24, len(formula_keys))
        self.assertEqual(len(formula_keys), len(set(formula_keys)))

    def test_recorded_sparse_and_absent_cases_are_honest(self):
        expected = {
            "trainer-04": {"card:1206:trainer_effect:0": 2},
            "trainer-05": {
                "card:1155:trainer_effect:0": 1,
                "card:1158:trainer_effect:0": 1,
                "card:1176:trainer_effect:0": 1,
                "card:1188:trainer_effect:0": 1,
                "card:1195:trainer_effect:0": 0,
                "card:1235:trainer_effect:0": 1,
            },
        }
        for batch_id, counts in expected.items():
            evidence = json.loads(
                (audit.OUTPUT / f"{batch_id}-recorded-engine-evidence.json").read_text(encoding="utf-8")
            )
            for effect_id, count in counts.items():
                self.assertEqual(count, evidence["coverage"]["sample_counts"][effect_id])
                checks = self.effects[batch_id][effect_id]["validation"]["checks"]
                key = "sparse_recorded_sample_with_exact_source_fallback" if count else "no_recorded_execution_with_exact_source_fallback"
                self.assertTrue(checks[key])

    def test_order_suppression_and_card_level_rules_are_explicit(self):
        hand_trimmer = self.effects["trainer-01"]["card:1087:trainer_effect:0"]["program"]["nodes"]
        self.assertEqual(1, hand_trimmer[0]["operation"]["parameters"]["resolution_order"])
        self.assertEqual(2, hand_trimmer[1]["operation"]["parameters"]["resolution_order"])

        neutral_card = next(card for card in self.batches["trainer-02"]["cards"] if card["card_id"] == 1247)
        self.assertIn("cannotToHandOrDeckInTrash", neutral_card["engine_card_source"]["method_calls"])
        neutral_ops = self.effects["trainer-02"]["card:1247:trainer_effect:0"]["program"]["nodes"]
        self.assertEqual("modify_card_movement_rule", neutral_ops[1]["operation"]["kind"])
        self.assertEqual(["hand", "deck"], neutral_ops[1]["operation"]["parameters"]["prohibited_destinations"])

        jamming = self.effects["trainer-02"]["card:1246:trainer_effect:0"]
        self.assertEqual("suppress_card_effects", jamming["program"]["nodes"][0]["operation"]["kind"])
        self.assertEqual("override_static", jamming["verdict"])

        area_zero = self.effects["trainer-05"]["card:1250:trainer_effect:0"]["program"]["nodes"]
        self.assertEqual("stadium_owner_then_opponent", area_zero[2]["operation"]["parameters"]["resolution_order"])

    def test_counter_trigger_evolution_and_coin_boundaries(self):
        battle_cage = self.effects["trainer-01"]["card:1264:trainer_effect:0"]
        self.assertIn("HR-B05-001", battle_cage["human_review_ids"])
        self.assertTrue(battle_cage["program"]["nodes"][0]["operation"]["parameters"]["attack_damage_still_applies"])

        brock = self.effects["trainer-03"]["card:1210:trainer_effect:0"]["program"]["nodes"]
        self.assertEqual("conditional", brock[1]["kind"])
        self.assertEqual("first_selected_card_is_basic", brock[1]["condition"]["path"])

        grand_tree = self.effects["trainer-04"]["card:1249:trainer_effect:0"]["program"]["nodes"]
        self.assertTrue(grand_tree[0]["operation"]["parameters"]["prohibit_first_turn"])
        self.assertEqual("conditional", grand_tree[1]["kind"])

        harlequin = self.effects["trainer-04"]["card:1223:trainer_effect:0"]
        branch = harlequin["program"]["nodes"][2]
        self.assertEqual(0.5, branch["condition"]["probability_heads"])
        self.assertEqual({"owner": 5, "opponent": 3}, harlequin["formula_question"]["heads"])

    def test_only_approved_approximation_and_no_pending_review(self):
        approximations = json.loads(
            (audit.PART_B / "approved-approximations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["HR-B05-002"], [item["human_review_id"] for item in approximations["approximations"]])
        ledger = json.loads(audit.HUMAN_REVIEW.read_text(encoding="utf-8"))
        self.assertFalse(any(item["status"] == "pending" for item in ledger["records"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
