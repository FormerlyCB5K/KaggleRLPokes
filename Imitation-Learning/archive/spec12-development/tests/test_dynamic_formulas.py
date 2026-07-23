"""Focused validation for the Spec-12b08 dynamic-formula registry."""
from __future__ import annotations

import json
import unittest

import build_dynamic_formula_registry as formulas


class DynamicFormulaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry, cls.validation = formulas.build_registry()
        cls.by_key = {item["formula_key"]: item for item in cls.registry["formulas"]}

    def test_queue_closes_exactly_79_unique_keys(self):
        self.assertEqual("complete", self.registry["status"])
        self.assertEqual("passed", self.validation["status"])
        self.assertEqual(79, self.registry["queue_count"])
        self.assertEqual(79, self.registry["formula_count"])
        self.assertEqual(79, len(self.by_key))
        self.assertTrue(self.validation["checks"]["queue_keys_equal_completed_keys"])
        self.assertTrue(self.validation["checks"]["queue_keys_unique"])

    def test_all_237_scenarios_reexecute_identically(self):
        self.assertEqual(237, self.validation["counts"]["scenarios"])
        for formula in self.registry["formulas"]:
            self.assertEqual(3, len(formula["scenarios"]))
            for scenario in formula["scenarios"]:
                self.assertEqual(
                    scenario["expected_raw_output"],
                    formulas.evaluate_formula(formula["formula_key"], scenario["inputs"]),
                    scenario["scenario_id"],
                )

    def test_serialized_scenarios_reexecute_identically(self):
        serialized = json.loads(formulas.OUTPUT.read_text(encoding="utf-8"))
        for formula in serialized["formulas"]:
            for scenario in formula["scenarios"]:
                self.assertEqual(
                    scenario["expected_raw_output"],
                    formulas.evaluate_formula(formula["formula_key"], scenario["inputs"]),
                    scenario["scenario_id"],
                )

    def test_scenario_coverage_includes_applicable_case_families(self):
        for formula in self.registry["formulas"]:
            coverage = {tag for scenario in formula["scenarios"] for tag in scenario["coverage"]}
            self.assertTrue({"negative", "positive", "boundary"}.issubset(coverage))
            expected = set(formulas._coverage_tags(formula["algorithm"]["shared_handler"], 2))
            self.assertTrue(expected.issubset(coverage))

    def test_missing_inputs_raise_instead_of_being_imputed(self):
        with self.assertRaises(formulas.MissingFormulaInput):
            formulas.evaluate_formula("pokemon_01_alakazam_powerful_hand", {})
        self.assertTrue(all(
            input_spec["missing_policy"] == "explicit_unknown_no_imputation"
            for formula in self.registry["formulas"]
            for input_spec in formula["inputs"]
        ))

    def test_card_specific_arithmetic_and_filters(self):
        self.assertEqual(240, formulas.evaluate_formula("pokemon_01_alakazam_powerful_hand", {"own_hand_count": 12}))
        self.assertEqual(120, formulas.evaluate_formula("pokemon_01_articuno_dark_frost", {"attached_energy_card_names": ["Team Rocket's Energy"]}))
        self.assertEqual(50, formulas.evaluate_formula("pokemon_03_cynthias_spiritomb_raging_curse", {"own_bench_exact_card_ids_or_cynthia_flags": [True, False, True], "own_bench_damage_counter_counts": [2, 9, 3]}))
        self.assertEqual(150, formulas.evaluate_formula("pokemon_05_teal_mask_ogerpon_myriad_leaf_shower", {"both_active_attached_energy_unit_counts": [1, 3]}))

    def test_threshold_damage_and_exact_card_id_gates(self):
        self.assertFalse(formulas.evaluate_formula("pokemon_02_team_rockets_mewtwo_power_saver", {"own_in_play_card_ids_or_team_rocket_flags": [True, True, True]}))
        self.assertTrue(formulas.evaluate_formula("pokemon_02_team_rockets_mewtwo_power_saver", {"own_in_play_card_ids_or_team_rocket_flags": [True] * 4}))
        self.assertEqual(70, formulas.evaluate_formula("pokemon_04_solrock_cosmic_beam", {"own_bench_exact_card_ids": [675]}))
        self.assertEqual(120, formulas.evaluate_formula("pokemon_06_mega_sharpedo_hungry_jaws", {"source_current_hp": 310, "source_effective_max_hp": 310}))
        self.assertEqual(270, formulas.evaluate_formula("pokemon_06_mega_sharpedo_hungry_jaws", {"source_current_hp": 300, "source_effective_max_hp": 310}))

    def test_copy_attacks_preserve_card_specific_source_gate(self):
        programs = [{"attack_id": "a", "raw_damage": 80}]
        blocked = formulas.evaluate_formula("pokemon_02_team_rockets_mimikyu_gemstone_mimicry", {"opponent_active_exact_card_id": 1, "opponent_active_is_tera": False, "chosen_attack_ordinal": 0, "referenced_attack_program": programs})
        allowed = formulas.evaluate_formula("pokemon_02_team_rockets_mimikyu_gemstone_mimicry", {"opponent_active_exact_card_id": 1, "opponent_active_is_tera": True, "chosen_attack_ordinal": 0, "referenced_attack_program": programs})
        self.assertFalse(blocked["legal"])
        self.assertTrue(allowed["legal"])

    def test_evolution_and_assignment_option_sets(self):
        candy = formulas.evaluate_formula("trainer_01_rare_candy_eligible_evolutions", {"own_in_play_exact_card_ids": [1], "own_hand_exact_card_ids": [3], "turn_number": 2, "pokemon_entered_play_this_turn": [False], "evolution_relations": {3: 2, 2: 1}})
        self.assertEqual([[1, 3]], candy)
        crispin = formulas.evaluate_formula("trainer_02_crispin_energy_assignment", {"basic_energy_cards_and_types_in_deck": [{"id": "p", "type": "psychic"}, {"id": "d", "type": "darkness"}], "own_pokemon_targets": ["active"], "owner_choices": []})
        self.assertIn({"hand": None, "attach": None, "target": None}, crispin)
        self.assertIn({"hand": "p", "attach": None, "target": None}, crispin)
        self.assertIn({"hand": "p", "attach": "d", "target": "active"}, crispin)

    def test_area_zero_order_and_special_energy_boundaries(self):
        area = formulas.evaluate_formula("trainer_05_area_zero_bench_capacity", {"stadium_in_play": False, "each_player_tera_presence": [True, True], "each_bench_occupied_count": [8, 7], "stadium_owner": 1, "stadium_leave_event": True})
        self.assertEqual([5, 5], area["capacities"])
        self.assertEqual([3, 2], area["discard_counts"])
        self.assertEqual([1, 0], area["resolution_order"])
        rocket = formulas.evaluate_formula("energy_01_team_rocket_energy_payment", {"holder_team_rocket_flag": True, "requested_attack_cost_types": {}, "other_attached_energy": {}})
        self.assertEqual(3, len(rocket["allocations"]))
        legacy = formulas.evaluate_formula("energy_01_legacy_energy_prize_reduction", {"holder_ko_cause": "opponent_attack_damage", "legacy_energy_effect_already_used_by_owner": False})
        self.assertEqual({"prize_reduction": 1, "mark_used": True}, legacy)

    def test_exact_kangaskhan_formula_and_only_approved_practical_tail(self):
        self.assertEqual(400, formulas.evaluate_formula("pokemon_01_mega_kangaskhan_coin_until_tails", {"coin_sequence": 4}))
        approximation_records = [item for item in self.registry["formulas"] if item["approximation"]]
        self.assertEqual(["pokemon_01_mega_kangaskhan_coin_until_tails"], [item["formula_key"] for item in approximation_records])
        self.assertEqual("HR-B05-002", approximation_records[0]["approximation"]["human_review_id"])

    def test_no_placeholder_bounds_or_pending_review(self):
        for item in self.registry["formulas"]:
            reason = item["output"]["unknown_reason"] or ""
            self.assertNotIn("pending", reason.casefold())
            self.assertEqual("none_raw_units", item["algorithm"]["saturation"])
        ledger = json.loads(formulas.HUMAN_REVIEW.read_text(encoding="utf-8"))
        self.assertFalse(any(item["status"] == "pending" for item in ledger["records"]))

    def test_registry_has_engine_trace_for_every_formula(self):
        for item in self.registry["formulas"]:
            evidence = item["engine_evidence"]
            self.assertRegex(evidence["chain_sha256"], r"^[0-9a-f]{64}$")
            self.assertIn(":", evidence["card_source"])
            self.assertTrue(evidence["canonical_batch"].endswith(".json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
