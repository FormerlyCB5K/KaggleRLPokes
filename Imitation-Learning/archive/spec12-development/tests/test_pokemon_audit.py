"""Focused validation for Spec-12b05 Pokemon audit artifacts."""
from __future__ import annotations

import json
import unittest

import build_pokemon_audit as audit


class PokemonBatchOneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch, cls.issues = audit.build_batch()

    def test_exact_batch_coverage(self):
        self.assertEqual([], self.issues)
        self.assertEqual(20, self.batch["summary"]["cards"])
        self.assertEqual(34, self.batch["summary"]["effects"])
        self.assertEqual(20, len(set(self.batch["card_ids"])))
        self.assertEqual("complete", self.batch["status"])

    def test_every_effect_has_evidence_and_semantics(self):
        effect_ids = []
        for card in self.batch["cards"]:
            for effect in card["effects"]:
                effect_ids.append(effect["effect_id"])
                self.assertTrue(effect["text"] or effect["printed_damage"])
                self.assertTrue(effect["engine"]["source_path"])
                self.assertTrue(effect["program"])
                self.assertIn(effect["verdict"], {
                    "engine_baked", "generic_exact", "override_static", "override_dynamic", "ordinary_field",
                })
                self.assertEqual("passed", effect["validation"]["status"])
        self.assertEqual(len(effect_ids), len(set(effect_ids)))

    def test_dynamic_queue_is_unique_and_owned_by_b08(self):
        keys = [item["formula_key"] for item in self.batch["formula_queue"]]
        self.assertEqual(5, len(keys))
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(item["owner"] == "B08" for item in self.batch["formula_queue"]))

    def test_kangaskhan_uses_the_approved_coin_tail_policy(self):
        attack = next(
            effect
            for card in self.batch["cards"]
            for effect in card["effects"]
            if effect["effect_id"] == "card:756:attack:0"
        )
        self.assertEqual(350, attack["damage_profile"]["credible_max"])
        self.assertEqual([200, 250, 300, 350], [
            item["damage"] for item in attack["program"]["practical_enumeration"]
        ])
        self.assertEqual(0.0625, attack["program"]["omitted_tail"]["probability"])

    def test_recorded_engine_attack_evidence_is_complete(self):
        evidence = json.loads(audit.RECORDED_EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(12, evidence["coverage"]["targets_with_sample"])
        self.assertTrue(all(count >= 3 for count in evidence["coverage"]["sample_counts"].values()))
        self.assertTrue(evidence["checks"]["alakazam_live_formula_passes"])


class PokemonBatchTwoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch, cls.issues = audit.build_batch("pokemon-02")
        ledger = json.loads(audit.HUMAN_REVIEW.read_text(encoding="utf-8"))
        cls.order_review_pending = next(
            item for item in ledger["records"] if item["id"] == "HR-B05-003"
        )["status"] != "resolved"
        cls.effects = {
            effect["effect_id"]: effect
            for card in cls.batch["cards"]
            for effect in card["effects"]
        }

    def test_exact_batch_coverage(self):
        self.assertEqual(2 if self.order_review_pending else 0, len(self.issues))
        self.assertEqual(
            "draft_pending_validation" if self.order_review_pending else "complete",
            self.batch["status"],
        )
        self.assertEqual(20, self.batch["summary"]["cards"])
        self.assertEqual(38, self.batch["summary"]["effects"])
        self.assertEqual(38, len(self.effects))
        self.assertEqual({
            "engine_baked": 1,
            "generic_exact": 3,
            "ordinary_field": 10,
            "override_dynamic": 5,
            "override_static": 19,
        }, self.batch["summary"]["verdicts"])

    def test_every_effect_has_source_semantics_and_passed_validation(self):
        for effect in self.effects.values():
            self.assertTrue(effect["text"] or effect["printed_damage"])
            self.assertTrue(effect["engine"]["source_path"])
            self.assertTrue(effect["program"])
            if self.order_review_pending and effect["effect_id"] in {
                "card:132:ability:0", "card:133:ability:0",
            }:
                self.assertEqual("failed", effect["validation"]["status"])
                self.assertEqual("draft", effect["audit_status"])
            else:
                self.assertEqual("passed", effect["validation"]["status"])
                self.assertEqual("complete", effect["audit_status"])

    def test_dynamic_queue_is_complete_unique_and_owned_by_b08(self):
        queue = self.batch["formula_queue"]
        keys = [item["formula_key"] for item in queue]
        self.assertEqual(5, len(keys))
        self.assertEqual(5, len(set(keys)))
        self.assertTrue(all(item["owner"] == "B08" for item in queue))
        self.assertTrue(all(item["required_inputs"] for item in queue))

    def test_dynamic_damage_profiles_preserve_exact_bounds(self):
        rocket_rush = self.effects["card:401:attack:0"]["damage_profile"]
        self.assertEqual("30 * own_team_rocket_pokemon_in_play", rocket_rush["live_formula"])
        self.assertEqual(180, rocket_rush["credible_max"])
        self.assertEqual(180, rocket_rush["theoretical_max"])

        erasure_ball = self.effects["card:431:attack:0"]["damage_profile"]
        self.assertEqual(280, erasure_ball["credible_max"])
        self.assertEqual(280, erasure_ball["theoretical_max"])

        froslass = self.effects["card:861:attack:0"]["damage_profile"]
        self.assertEqual("50 * opponent_hand_count", froslass["live_formula"])
        self.assertIsNone(froslass["credible_max"])
        self.assertEqual(2900, froslass["theoretical_max"])

    def test_counter_and_rule_programs_keep_non_obvious_boundaries(self):
        dusclops = self.effects["card:132:ability:0"]
        self.assertEqual("damage_counters", dusclops["damage_profile"]["damage_kind"])
        self.assertEqual(
            ["knock_out", "place_damage_counters"],
            [node["operation"]["kind"] for node in dusclops["program"]["nodes"]],
        )
        tera = self.effects["card:117:tera:0"]["program"]["nodes"][0]["operation"]
        self.assertEqual("either_player", tera["parameters"]["attacker_controller"])
        self.assertTrue(tera["parameters"]["effects_are_not_prevented"])
        self.assertEqual("engine_baked", self.effects["card:342:ability:0"]["verdict"])

    def test_full_recorded_scan_and_sparse_source_fallbacks_are_explicit(self):
        path = audit.OUTPUT / "pokemon-02-recorded-engine-evidence.json"
        evidence = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(evidence["checks"]["full_dataset_scan_complete"])
        self.assertFalse(evidence["checks"]["all_targets_have_multiple_samples"])
        self.assertEqual(15018, evidence["members_read"])
        self.assertEqual(16, evidence["coverage"]["targets"])
        self.assertEqual(12, evidence["coverage"]["targets_with_sample"])
        self.assertEqual(1, evidence["coverage"]["sample_counts"]["card:861:attack:1"])
        for effect_id in {
            "card:1071:attack:0", "card:131:attack:0",
            "card:133:attack:0", "card:434:attack:0",
        }:
            self.assertEqual(0, evidence["coverage"]["sample_counts"][effect_id])
            checks = self.effects[effect_id]["validation"]["checks"]
            self.assertTrue(checks["no_recorded_execution_with_exact_source_fallback"])

    def test_no_new_approximation_was_added(self):
        approximations = json.loads(
            (audit.PART_B / "approved-approximations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, len(approximations["approximations"]))
        self.assertEqual("HR-B05-002", approximations["approximations"][0]["human_review_id"])
        self.assertTrue(all(
            "HR-B05-002" not in effect["human_review_ids"]
            for effect in self.effects.values()
        ))


class PokemonBatchThreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch, cls.issues = audit.build_batch("pokemon-03")
        cls.effects = {
            effect["effect_id"]: effect
            for card in cls.batch["cards"]
            for effect in card["effects"]
        }

    def test_exact_batch_coverage_and_verdicts(self):
        self.assertEqual([], self.issues)
        self.assertEqual("complete", self.batch["status"])
        self.assertEqual(20, self.batch["summary"]["cards"])
        self.assertEqual(34, self.batch["summary"]["effects"])
        self.assertEqual(34, len(self.effects))
        self.assertEqual({
            "engine_baked": 1,
            "generic_exact": 2,
            "ordinary_field": 9,
            "override_dynamic": 12,
            "override_static": 10,
        }, self.batch["summary"]["verdicts"])

    def test_every_effect_is_complete_and_validated(self):
        for effect in self.effects.values():
            self.assertTrue(effect["text"] or effect["printed_damage"])
            self.assertTrue(effect["engine"]["source_path"])
            self.assertTrue(effect["program"])
            self.assertEqual("passed", effect["validation"]["status"])
            self.assertEqual("complete", effect["audit_status"])

    def test_formula_queue_is_unique_complete_and_owned_by_b08(self):
        queue = self.batch["formula_queue"]
        keys = [item["formula_key"] for item in queue]
        self.assertEqual(12, len(keys))
        self.assertEqual(12, len(set(keys)))
        self.assertTrue(all(item["owner"] == "B08" for item in queue))
        self.assertTrue(all(item["required_inputs"] for item in queue))

    def test_dynamic_bounds_and_coin_values(self):
        psychic = self.effects["card:245:attack:1"]["damage_profile"]
        self.assertEqual("10 + 50 * energy_attached_to_opponent_active", psychic["live_formula"])
        self.assertIsNone(psychic["theoretical_max"])
        self.assertIn("Energy units", psychic["unknown_reason"])
        self.assertEqual(100, self.effects["card:93:attack:0"]["damage_profile"]["credible_max"])
        self.assertEqual(160, self.effects["card:93:attack:0"]["damage_profile"]["theoretical_max"])
        self.assertEqual(200, self.effects["card:169:attack:1"]["damage_profile"]["credible_max"])
        self.assertEqual(230, self.effects["card:849:attack:0"]["damage_profile"]["theoretical_max"])
        self.assertEqual(20.0, self.effects["card:92:attack:0"]["damage_profile"]["expected_value"])
        self.assertEqual(30.0, self.effects["card:164:attack:1"]["damage_profile"]["expected_value"])

    def test_counter_conservation_and_festival_continuation_are_explicit(self):
        strange = self.effects["card:245:attack:0"]["program"]
        repeat = strange["nodes"][1]
        self.assertTrue(repeat["parameters"]["total_damage_counters_conserved"])
        self.assertEqual("damage_counter_relocation", self.effects["card:245:attack:0"]["damage_profile"]["damage_kind"])
        festival = self.effects["card:93:ability:0"]
        self.assertEqual(1245, festival["program"]["condition"]["arguments"][1]["value"])
        modifier = festival["program"]["then"]["nodes"][0]["operation"]
        self.assertEqual(2, modifier["value"]["value"])
        self.assertIn("replacement", modifier["parameters"]["continuation"])

    def test_recorded_scan_and_sparse_fallbacks_are_exact(self):
        path = audit.OUTPUT / "pokemon-03-recorded-engine-evidence.json"
        evidence = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(evidence["checks"]["full_dataset_scan_complete"])
        self.assertEqual(15018, evidence["members_read"])
        self.assertEqual(18, evidence["coverage"]["targets"])
        self.assertEqual(17, evidence["coverage"]["targets_with_sample"])
        self.assertEqual(1, evidence["coverage"]["sample_counts"]["card:65:attack:1"])
        self.assertEqual(0, evidence["coverage"]["sample_counts"]["card:247:attack:0"])
        self.assertTrue(self.effects["card:65:attack:1"]["validation"]["checks"]["sparse_recorded_sample_with_exact_source_fallback"])
        self.assertTrue(self.effects["card:247:attack:0"]["validation"]["checks"]["no_recorded_execution_with_exact_source_fallback"])

    def test_no_new_approximation_or_pending_review(self):
        approximations = json.loads(
            (audit.PART_B / "approved-approximations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["HR-B05-002"], [
            item["human_review_id"] for item in approximations["approximations"]
        ])
        ledger = json.loads(audit.HUMAN_REVIEW.read_text(encoding="utf-8"))
        self.assertFalse(any(item["status"] == "pending" for item in ledger["records"]))


class PokemonLateBatchAndClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batches = {}
        cls.effects = {}
        for batch_id in ("pokemon-04", "pokemon-05", "pokemon-06"):
            batch, issues = audit.build_batch(batch_id)
            cls.batches[batch_id] = batch
            cls.effects[batch_id] = {
                effect["effect_id"]: effect
                for card in batch["cards"]
                for effect in card["effects"]
            }
            if issues:
                raise AssertionError(f"{batch_id} issues: {issues}")

    def test_late_batch_counts_verdicts_and_formula_ownership(self):
        expected = {
            "pokemon-04": (20, 34, 11, {"generic_exact": 6, "ordinary_field": 8, "override_dynamic": 11, "override_static": 9}),
            "pokemon-05": (20, 39, 10, {"generic_exact": 4, "ordinary_field": 11, "override_dynamic": 10, "override_static": 14}),
            "pokemon-06": (15, 26, 8, {"generic_exact": 4, "ordinary_field": 7, "override_dynamic": 8, "override_static": 7}),
        }
        for batch_id, (cards, effects, formulas, verdicts) in expected.items():
            batch = self.batches[batch_id]
            self.assertEqual("complete", batch["status"])
            self.assertEqual(cards, batch["summary"]["cards"])
            self.assertEqual(effects, batch["summary"]["effects"])
            self.assertEqual(verdicts, batch["summary"]["verdicts"])
            keys = [item["formula_key"] for item in batch["formula_queue"]]
            self.assertEqual(formulas, len(keys))
            self.assertEqual(len(keys), len(set(keys)))
            self.assertTrue(all(item["owner"] == "B08" for item in batch["formula_queue"]))
            self.assertTrue(all(item["required_inputs"] for item in batch["formula_queue"]))

    def test_every_late_effect_is_complete_and_source_validated(self):
        for effects in self.effects.values():
            for effect in effects.values():
                self.assertTrue(effect["text"] or effect["printed_damage"])
                self.assertTrue(effect["engine"]["source_path"])
                self.assertTrue(effect["program"])
                self.assertEqual("passed", effect["validation"]["status"])
                self.assertEqual("complete", effect["audit_status"])

    def test_late_dynamic_boundaries_are_lossless(self):
        fourth = self.effects["pokemon-04"]
        self.assertEqual(220, fourth["card:272:attack:0"]["damage_profile"]["credible_max"])
        self.assertEqual(340, fourth["card:272:attack:0"]["damage_profile"]["theoretical_max"])
        self.assertEqual(540, fourth["card:306:attack:0"]["damage_profile"]["theoretical_max"])

        fifth = self.effects["pokemon-05"]
        self.assertEqual(300, fifth["card:141:attack:0"]["damage_profile"]["theoretical_max"])
        self.assertEqual(240, fifth["card:303:attack:0"]["damage_profile"]["credible_max"])
        self.assertEqual("multi_target_attack_damage", fifth["card:108:attack:1"]["damage_profile"]["damage_kind"])

        sixth = self.effects["pokemon-06"]
        self.assertEqual(20, sixth["card:333:attack:0"]["damage_profile"]["expected_value"])
        wild_growth = sixth["card:710:ability:0"]["program"]["nodes"][0]["operation"]
        self.assertTrue(wild_growth["parameters"]["nonstacking"])
        self.assertEqual(2, wild_growth["value"]["value"])
        self.assertEqual("self_damage_counters", sixth["card:834:ability:0"]["damage_profile"]["damage_kind"])
        self.assertIn("HR-B05-001", sixth["card:834:ability:0"]["human_review_ids"])

    def test_late_recorded_scans_and_exact_fallbacks(self):
        expected = {
            "pokemon-04": (19, 14, {"card:73:attack:0": 2, "card:432:attack:0": 0}),
            "pokemon-05": (20, 15, {"card:108:attack:1": 1, "card:63:attack:0": 0}),
            "pokemon-06": (14, 8, {"card:333:attack:0": 2, "card:42:attack:0": 0}),
        }
        for batch_id, (targets, with_sample, spot_counts) in expected.items():
            evidence = json.loads(
                (audit.OUTPUT / f"{batch_id}-recorded-engine-evidence.json").read_text(encoding="utf-8")
            )
            self.assertTrue(evidence["checks"]["full_dataset_scan_complete"])
            self.assertEqual(15018, evidence["members_read"])
            self.assertEqual(targets, evidence["coverage"]["targets"])
            self.assertEqual(with_sample, evidence["coverage"]["targets_with_sample"])
            for effect_id, count in spot_counts.items():
                self.assertEqual(count, evidence["coverage"]["sample_counts"][effect_id])
                checks = self.effects[batch_id][effect_id]["validation"]["checks"]
                key = (
                    "sparse_recorded_sample_with_exact_source_fallback"
                    if count else "no_recorded_execution_with_exact_source_fallback"
                )
                self.assertTrue(checks[key])

    def test_global_pokemon_union_is_exact_unique_and_closed(self):
        worklist = json.loads(audit.WORKLIST.read_text(encoding="utf-8"))
        manifest = json.loads(audit.BATCHES.read_text(encoding="utf-8"))
        expected_cards = {
            card["card_id"] for card in worklist["cards"] if card["card_class"] == "pokemon"
        }
        expected_effects = {
            effect["effect_id"]
            for card in worklist["cards"] if card["card_class"] == "pokemon"
            for effect in card["effects"]
        }
        batch_ids = [item["batch_id"] for item in manifest["batches"] if item["batch_id"].startswith("pokemon-")]
        built = [audit.build_batch(batch_id)[0] for batch_id in batch_ids]
        actual_cards = [card_id for batch in built for card_id in batch["card_ids"]]
        actual_effects = [
            effect["effect_id"] for batch in built for card in batch["cards"] for effect in card["effects"]
        ]
        formula_keys = [item["formula_key"] for batch in built for item in batch["formula_queue"]]
        self.assertEqual(115, len(expected_cards))
        self.assertEqual(205, len(expected_effects))
        self.assertEqual(expected_cards, set(actual_cards))
        self.assertEqual(expected_effects, set(actual_effects))
        self.assertEqual(len(actual_cards), len(set(actual_cards)))
        self.assertEqual(len(actual_effects), len(set(actual_effects)))
        self.assertEqual(51, len(formula_keys))
        self.assertEqual(len(formula_keys), len(set(formula_keys)))
        self.assertTrue(all(batch["status"] == "complete" for batch in built))

    def test_pokemon_closure_has_no_new_approximation_or_pending_review(self):
        approximations = json.loads(
            (audit.PART_B / "approved-approximations.json").read_text(encoding="utf-8")
        )
        self.assertEqual(["HR-B05-002"], [
            item["human_review_id"] for item in approximations["approximations"]
        ])
        ledger = json.loads(audit.HUMAN_REVIEW.read_text(encoding="utf-8"))
        self.assertFalse(any(item["status"] == "pending" for item in ledger["records"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
