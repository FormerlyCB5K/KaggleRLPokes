"""Focused acceptance tests for the Spec-12 Part-C registry package."""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

import build_dynamic_formula_registry as dynamic
import build_meta_card_registry as registry_builder


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class MetaCardRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.artifacts, cls.validation = registry_builder.build_all()
        cls.registry = json.loads(cls.artifacts[registry_builder.REGISTRY.name].decode("utf-8"))
        cls.formulas = json.loads(cls.artifacts[registry_builder.FORMULAS.name].decode("utf-8"))
        cls.ids = json.loads(cls.artifacts[registry_builder.CARD_IDS.name].decode("utf-8"))
        cls.overrides = json.loads(cls.artifacts[registry_builder.OVERRIDES.name].decode("utf-8"))

    def test_c0_frozen_versions_hashes_and_closed_inputs(self):
        self.assertEqual("passed", self.validation["status"])
        self.assertTrue(self.validation["checks"]["c0_b09_input_is_closed"])
        self.assertTrue(self.validation["checks"]["c0_schema_versions_frozen"])
        self.assertRegex(self.registry["source_catalog_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(self.registry["source_audit_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual("1.32.0", self.registry["engine_version_or_hash"]["module_version"])

    def test_c1_exact_card_class_effect_and_verdict_coverage(self):
        self.assertEqual(232, self.registry["counts"]["cards"])
        self.assertEqual(314, self.registry["counts"]["effects"])
        self.assertEqual(115, len(self.ids["pokemon"]))
        self.assertEqual(99, len(self.ids["trainer"]))
        self.assertEqual(18, len(self.ids["energy"]))
        verdicts = [effect["verdict"] for card in self.registry["cards"].values() for effect in [*card["attacks"], *card["abilities"], *card["effects"]]]
        self.assertEqual({"engine_baked": 10, "generic_exact": 23, "ordinary_field": 54, "override_dynamic": 79, "override_static": 148}, dict(sorted(__import__("collections").Counter(verdicts).items())))

    def test_c1_all_effects_preserve_program_source_order_and_audit_payload(self):
        handoff = registry_builder.load_json(registry_builder.PART_C_INPUT)
        source_effects = {effect["effect_id"]: effect for card in handoff["cards"] for effect in card["effects"]}
        registry_effects = {effect["effect_id"]: effect for card in self.registry["cards"].values() for effect in [*card["attacks"], *card["abilities"], *card["effects"]]}
        self.assertEqual(set(source_effects), set(registry_effects))
        for effect_id, effect in registry_effects.items():
            self.assertEqual(source_effects[effect_id]["program"], effect["program"])
            self.assertEqual(source_effects[effect_id]["verdict"], effect["verdict"])
        self.assertTrue(self.validation["checks"]["c1_source_order_and_no_truncation"])

    def test_c2_numeric_ids_json_python_parity_and_roundtrip(self):
        numeric_keys = [int(card_id) for card_id in self.registry["cards"]]
        self.assertEqual(sorted(numeric_keys), numeric_keys)
        self.assertEqual(set(self.ids["all"]), set(self.ids["pokemon"]) | set(self.ids["trainer"]) | set(self.ids["energy"]))
        self.assertFalse(set(self.ids["pokemon"]) & set(self.ids["trainer"]))
        generated_path = registry_builder.OUTPUT / registry_builder.CARD_IDS_PY.name
        card_ids_module = load_module("generated_meta_card_ids", generated_path)
        self.assertEqual(tuple(self.ids["all"]), card_ids_module.ALL_CARD_IDS)
        self.assertEqual({int(key): value for key, value in self.ids["index_by_card_id"].items()}, card_ids_module.CARD_ID_TO_INDEX)

    def test_c2_override_view_is_exact_derived_subset_and_no_more(self):
        self.assertEqual(201, self.overrides["counts"]["cards"])
        self.assertEqual(237, self.overrides["counts"]["override_effects"])
        for card_id, card in self.registry["cards"].items():
            special = card["integration_notes"]["override_effect_ids"]
            self.assertEqual(bool(special), card_id in self.overrides["cards"])
            if special:
                self.assertEqual(special, self.overrides["cards"][card_id]["override_effect_ids"])
        self.assertEqual(31, len(self.registry["cards"]) - len(self.overrides["cards"]))

    def test_c2_formula_registry_reverse_indexes_and_card_calculations(self):
        self.assertEqual(79, len(self.formulas["formulas"]))
        self.assertEqual(79, len(self.formulas["reverse_index"]))
        self.assertTrue(all(item["formula_schema_version"] == "1.0.0" for item in self.formulas["formulas"].values()))
        calculations = [(card_id, calc) for card_id, card in self.registry["cards"].items() for calc in card["calculations"]]
        self.assertEqual(79, len(calculations))
        for card_id, calculation in calculations:
            key = calculation["formula_key"]
            self.assertIn(int(card_id), self.formulas["reverse_index"][key]["card_ids"])
            self.assertIn(calculation["effect_id"], self.formulas["reverse_index"][key]["effect_ids"])

    def test_c3_every_serialized_formula_scenario_passes(self):
        count = 0
        for key, formula in self.formulas["formulas"].items():
            for scenario in formula["scenarios"]:
                count += 1
                self.assertEqual(scenario["expected_raw_output"], dynamic.evaluate_formula(key, scenario["inputs"]), scenario["scenario_id"])
        self.assertEqual(237, count)

    def test_c3_concrete_alakazam_and_delegation_boundaries(self):
        alakazam = self.registry["cards"]["743"]
        powerful_hand = next(effect for effect in alakazam["attacks"] if effect["effect_id"] == "card:743:attack:0")
        self.assertEqual("override_dynamic", powerful_hand["verdict"])
        self.assertEqual("{P}", powerful_hand["printed_cost"])
        self.assertIsNone(powerful_hand["printed_damage"])
        self.assertNotIn("pending", (powerful_hand["damage_profile"]["unknown_reason"] or "").casefold())
        self.assertEqual("pokemon_01_alakazam_powerful_hand", powerful_hand["formula_key"])
        self.assertEqual(240, dynamic.evaluate_formula(powerful_hand["formula_key"], {"own_hand_count": 12}))
        for card in self.registry["cards"].values():
            for effect_id in card["integration_notes"]["engine_baked_effect_ids"] + card["integration_notes"]["ordinary_delegated_effect_ids"]:
                self.assertNotIn(effect_id, [item for item in card["integration_notes"]["override_effect_ids"] if item not in card["integration_notes"]["engine_baked_effect_ids"]])

    def test_c4_python_loader_and_unseen_fallback_clean_room_usage(self):
        loader = load_module("generated_meta_registry", registry_builder.OUTPUT / registry_builder.LOADER.name)
        self.assertTrue(loader.is_meta_card(743))
        self.assertEqual("Alakazam", loader.get_card(743)["identity"]["name"])
        self.assertTrue(loader.formulas_for_card(743))
        fallback = loader.unseen_fallback_contract(999999)
        self.assertIn("generalized text/effect parser", fallback["policy"])
        with self.assertRaises(ValueError):
            loader.unseen_fallback_contract(743)

    def test_c4_schema_provenance_readme_and_scope_are_complete(self):
        schema = json.loads(self.artifacts[registry_builder.SCHEMA.name].decode("utf-8"))
        provenance = json.loads(self.artifacts[registry_builder.PROVENANCE.name].decode("utf-8"))
        readme = self.artifacts[registry_builder.README.name].decode("utf-8")
        self.assertEqual(registry_builder.REGISTRY_SCHEMA_VERSION, schema["registry_schema_version"])
        self.assertEqual(9, len(provenance["frozen_inputs"]))
        self.assertEqual(0, provenance["human_review"]["unresolved"])
        self.assertIn("`registry.json` is the canonical", readme)
        self.assertIn("Missing dynamic state remains explicit unknown", readme)
        self.assertIn("Create a new specification", readme)
        self.assertNotIn("tensor_shape", self.registry)

    def test_c5_all_artifacts_parse_and_regenerate_byte_identically(self):
        second, second_validation = registry_builder.build_all()
        self.assertEqual("passed", second_validation["status"])
        self.assertEqual(self.artifacts, second)
        self.assertEqual(11, len(self.artifacts))
        for name, data in self.artifacts.items():
            self.assertEqual(data, (registry_builder.OUTPUT / name).read_bytes(), name)
            if name.endswith(".json"):
                json.loads(data.decode("utf-8"))
        manifest = json.loads(self.artifacts[registry_builder.MANIFEST.name].decode("utf-8"))
        self.assertEqual("complete", manifest["status"])
        self.assertEqual(10, len(manifest["artifacts"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
