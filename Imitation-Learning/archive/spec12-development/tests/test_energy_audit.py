"""Focused validation for Spec-12b07 Energy audit artifacts."""
from __future__ import annotations

import json
import unittest

import build_energy_audit as audit


class EnergyAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch, cls.issues = audit.build_batch()
        cls.cards = {card["card_id"]: card for card in cls.batch["cards"]}
        cls.effects = {
            effect["effect_id"]: effect
            for card in cls.batch["cards"]
            for effect in card["effects"]
        }

    def test_exact_batch_counts_subtypes_and_verdicts(self):
        self.assertEqual([], self.issues)
        self.assertEqual("complete", self.batch["status"])
        self.assertEqual(18, self.batch["summary"]["cards"])
        self.assertEqual(10, self.batch["summary"]["effects"])
        self.assertEqual({"Basic Energy": 8, "Special Energy": 10}, self.batch["summary"]["subtypes"])
        self.assertEqual({"ordinary_field": 8, "override_dynamic": 4, "override_static": 6}, self.batch["summary"]["verdicts"])

    def test_global_id_and_effect_sets_equal_worklist(self):
        worklist = json.loads(audit.WORKLIST.read_text(encoding="utf-8"))
        expected_cards = {
            card["card_id"] for card in worklist["cards"] if card["card_class"] == "energy"
        }
        expected_effects = {
            effect["effect_id"]
            for card in worklist["cards"] if card["card_class"] == "energy"
            for effect in card["effects"]
        }
        self.assertEqual(expected_cards, set(self.batch["card_ids"]))
        self.assertEqual(expected_effects, set(self.effects))
        self.assertEqual(18, len(set(self.batch["card_ids"])))
        self.assertEqual(10, len(self.effects))

    def test_basic_energy_types_are_exact_and_have_no_extra_effects(self):
        for card_id, energy_type in audit.BASIC_TYPES.items():
            card = self.cards[card_id]
            self.assertEqual("ordinary_field", card["verdict"])
            self.assertEqual([energy_type], card["energy_profile"]["default_provided_types"])
            self.assertEqual(1, card["energy_profile"]["default_energy_count"])
            self.assertEqual([], card["effects"])
            self.assertIn("basicEnergy", card["engine_card_source"]["method_calls"])
            self.assertEqual("passed", card["validation"]["status"])

    def test_all_attachments_have_three_recorded_samples(self):
        evidence = json.loads(audit.EVIDENCE.read_text(encoding="utf-8"))
        self.assertTrue(evidence["checks"]["full_dataset_scan_complete"])
        self.assertTrue(evidence["checks"]["all_targets_have_multiple_samples"])
        self.assertEqual(15018, evidence["members_read"])
        self.assertEqual(18, evidence["coverage"]["targets"])
        self.assertEqual(18, evidence["coverage"]["targets_with_sample"])
        self.assertTrue(all(count == 3 for count in evidence["coverage"]["sample_counts"].values()))

    def test_dynamic_formula_keys_are_unique_and_owned_by_b08(self):
        queue = self.batch["formula_queue"]
        keys = [item["formula_key"] for item in queue]
        self.assertEqual(4, len(keys))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual({
            "energy_01_team_rocket_energy_payment",
            "energy_01_ignition_energy_provision",
            "energy_01_prism_energy_provision",
            "energy_01_legacy_energy_prize_reduction",
        }, set(keys))
        self.assertTrue(all(item["owner"] == "B08" for item in queue))
        self.assertTrue(all(item["required_inputs"] for item in queue))

    def test_special_energy_type_count_and_trigger_boundaries(self):
        team_rocket = self.effects["card:15:energy_effect:0"]
        self.assertEqual(2, team_rocket["energy_profile"]["default_energy_count"])
        self.assertEqual(["psychic", "darkness"], team_rocket["energy_profile"]["default_provided_types"])
        self.assertTrue(team_rocket["program"]["nodes"][0]["operation"]["parameters"]["discard_if_illegally_attached"])
        self.assertTrue(any(ref.endswith("State.h:1313") for ref in team_rocket["runtime_engine_refs"]))

        ignition = self.effects["card:17:energy_effect:0"]
        self.assertEqual("conditional", ignition["program"]["nodes"][0]["kind"])
        self.assertEqual(3, ignition["program"]["nodes"][0]["then"]["nodes"][0]["operation"]["value"])
        self.assertEqual("end_of_owners_turn", ignition["program"]["nodes"][1]["operation"]["parameters"]["timing"])

        prism = self.effects["card:16:energy_effect:0"]
        self.assertEqual(1, prism["energy_profile"]["default_energy_count"])
        self.assertEqual("conditional", prism["program"]["kind"])
        self.assertEqual(1, prism["program"]["then"]["nodes"][0]["operation"]["parameters"]["simultaneous_count_cap"])

        legacy = self.effects["card:12:energy_effect:0"]
        prize = legacy["program"]["nodes"][1]["operation"]
        self.assertEqual(-1, prize["value"])
        self.assertEqual("once_per_game_per_owner", prize["parameters"]["frequency"])

    def test_protection_and_counter_units_remain_distinct(self):
        mist = self.effects["card:11:energy_effect:0"]["program"]["nodes"][1]["operation"]
        self.assertTrue(mist["parameters"]["damage_is_not_prevented"])
        self.assertTrue(mist["parameters"]["existing_effects_are_not_removed"])

        rock = self.effects["card:20:energy_effect:0"]["program"]["nodes"][1]
        self.assertEqual("holder_is_fighting_pokemon", rock["condition"]["path"])

        spiky = self.effects["card:14:energy_effect:0"]
        self.assertIn("HR-B05-001", spiky["human_review_ids"])
        self.assertEqual(2, spiky["program"]["nodes"][1]["operation"]["value"])
        self.assertTrue(spiky["activation"]["even_if_holder_knocked_out"])

    def test_only_approved_approximation_and_no_pending_review(self):
        approximations = json.loads(
            (audit.PART_B / "approved-approximations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["HR-B05-002"], [item["human_review_id"] for item in approximations["approximations"]])
        ledger = json.loads(audit.HUMAN_REVIEW.read_text(encoding="utf-8"))
        self.assertFalse(any(item["status"] == "pending" for item in ledger["records"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
