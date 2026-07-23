"""Build the reviewed Spec-12b07 Energy audit batch."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
WORKLIST = PART_B / "audit-worklist.json"
BATCHES = PART_B / "audit-batch-manifest.json"
HUMAN_REVIEW = PART_B / "human-review-ledger.json"
OUTPUT = PART_B / "energy-audit"
EVIDENCE = OUTPUT / "energy-01-recorded-attachment-evidence.json"
SCHEMA_VERSION = 1

BASIC_TYPES = {1: "grass", 2: "fire", 3: "water", 4: "lightning", 5: "psychic", 6: "fighting", 7: "darkness", 8: "metal"}


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def expr(kind: str, **fields) -> dict:
    return {"kind": kind, **fields}


def operation(kind: str, target: object = None, value: object = None, **parameters) -> dict:
    return {"kind": "operation", "operation": {"kind": kind, "target": target, "value": value, "parameters": parameters}}


def sequence(*nodes: dict) -> dict:
    return {"kind": "sequence", "nodes": list(nodes)}


def conditional(condition: object, then: dict, otherwise: dict | None = None) -> dict:
    return {"kind": "conditional", "condition": condition, "then": then, "else": otherwise}


def profile(default_types: list[str], default_count: int, *, formula: object | None = None, inputs: list[str] | None = None) -> dict:
    return {
        "default_provided_types": default_types,
        "default_energy_count": default_count,
        "live_formula": formula or {"types": default_types, "count": default_count},
        "required_inputs": inputs or [],
    }


def effect_semantics() -> dict[int, dict]:
    return {
        19: {
            "verdict": "override_static",
            "energy_profile": profile(["psychic"], 1),
            "activation": {"event": "attach_from_hand", "requirements": ["holder_is_psychic_pokemon"]},
            "program": sequence(operation("provide_energy", "holder", 1, types=["psychic"]), operation("move_cards", "chosen_basic_psychic_pokemon_cards", "chosen_count_0_to_min(2,open_bench_slots)", source="own_deck", destination="own_bench"), operation("shuffle_cards", "own_deck")),
            "observability": ["hidden_information", "observation_direct"],
            "change_from_current": "the current encoder omits Psychic provision and the hand-attach-to-Psychic trigger that benches up to two Basic Psychic Pokémon and shuffles",
            "formula_key": None, "formula_inputs": [], "formula_question": None, "human_review_ids": [],
        },
        13: {
            "verdict": "override_static",
            "energy_profile": profile(["colorless"], 1),
            "activation": {"event": "attach_from_hand"},
            "program": sequence(operation("provide_energy", "holder", 1, types=["colorless"]), operation("move_cards", "own_deck_top", 4, source="own_deck", destination="own_hand", mode="draw")),
            "observability": ["hidden_information"],
            "change_from_current": "the current encoder omits Colorless provision and the attach-from-hand draw-four trigger",
            "formula_key": None, "formula_inputs": [], "formula_question": None, "human_review_ids": [],
        },
        18: {
            "verdict": "override_static",
            "energy_profile": profile(["grass"], 1),
            "activation": {"event": "energy_continuous", "duration": "while_attached"},
            "program": sequence(operation("provide_energy", "holder", 1, types=["grass"]), conditional(expr("read", path="holder_is_grass_pokemon"), sequence(operation("modify_stat", "holder", 20, stat="max_hp", mode="add")))),
            "observability": ["observation_direct", "observation_derived"],
            "change_from_current": "the current encoder omits Grass provision and the Grass-holder-only +20 effective maximum HP",
            "formula_key": None, "formula_inputs": [], "formula_question": None, "human_review_ids": [],
        },
        11: {
            "verdict": "override_static",
            "energy_profile": profile(["colorless"], 1),
            "activation": {"event": "energy_continuous", "duration": "while_attached"},
            "program": sequence(operation("provide_energy", "holder", 1, types=["colorless"]), operation("modify_effect_rule", "holder", None, rule="prevent_effects_of_opponent_pokemon_attacks", damage_is_not_prevented=True, existing_effects_are_not_removed=True)),
            "observability": ["observation_direct"],
            "change_from_current": "the current encoder omits Colorless provision and damage-excluding prevention of future opposing attack effects without removing existing effects",
            "formula_key": None, "formula_inputs": [], "formula_question": None, "human_review_ids": [],
        },
        14: {
            "verdict": "override_static",
            "energy_profile": profile(["colorless"], 1),
            "activation": {"event": "holder_damaged_by_opponent_attack_while_active", "even_if_holder_knocked_out": True},
            "program": sequence(operation("provide_energy", "holder", 1, types=["colorless"]), operation("place_damage_counters", "attacking_pokemon", 2)),
            "observability": ["public_history"],
            "change_from_current": "the current encoder omits Colorless provision, the Active-holder damage trigger including KO, and exact two-counter retaliation",
            "formula_key": None, "formula_inputs": [], "formula_question": None, "human_review_ids": ["HR-B05-001"],
        },
        15: {
            "verdict": "override_dynamic",
            "energy_profile": profile(["psychic", "darkness"], 2, formula={"types": "any chosen combination of psychic/darkness", "count": 2}, inputs=["energy_payment_type_allocation"]),
            "activation": {"event": "energy_continuous_and_attachment_legality", "duration": "while_attached"},
            "program": sequence(operation("modify_attachment_rule", "this_energy", None, allowed_holder="team_rocket_pokemon", discard_if_illegally_attached=True), operation("provide_energy", "holder", 2, types=["psychic", "darkness"], allocation="any_combination_per_payment")),
            "observability": ["observation_direct", "observation_derived"],
            "change_from_current": "the current encoder omits the Team Rocket-only attachment rule, refresh-time illegal-holder discard, and two units in any Psychic/Darkness combination",
            "runtime_engine_refs": ["Imitation-Learning/ptcg_engine/ptcgProgram 22/State.h:1313", "Imitation-Learning/ptcg_engine/ptcgProgram 22/EffectProc.h:1168"],
            "formula_key": "energy_01_team_rocket_energy_payment", "formula_inputs": ["holder_team_rocket_flag", "requested_attack_cost_types", "other_attached_energy"], "formula_question": "all legal allocations of exactly 2 units across Psychic and Darkness for payment", "human_review_ids": [],
        },
        20: {
            "verdict": "override_static",
            "energy_profile": profile(["fighting"], 1),
            "activation": {"event": "energy_continuous", "duration": "while_attached"},
            "program": sequence(operation("provide_energy", "holder", 1, types=["fighting"]), conditional(expr("read", path="holder_is_fighting_pokemon"), sequence(operation("modify_effect_rule", "holder", None, rule="prevent_effects_of_opponent_pokemon_attacks", damage_is_not_prevented=True, existing_effects_are_not_removed=True)))),
            "observability": ["observation_direct", "observation_derived"],
            "change_from_current": "the current encoder omits Fighting provision and Fighting-holder-only prevention of future opposing attack effects while preserving damage/existing effects",
            "formula_key": None, "formula_inputs": [], "formula_question": None, "human_review_ids": [],
        },
        17: {
            "verdict": "override_dynamic",
            "energy_profile": profile(["colorless"], 1, formula={"types": ["colorless"], "count": "3 if holder is Stage 1 or Stage 2 else 1"}, inputs=["holder_evolution_stage"]),
            "activation": {"event": "energy_continuous_and_owner_turn_end", "duration": "while_attached_until_owner_turn_end"},
            "program": sequence(conditional(expr("read", path="holder_is_evolution_pokemon"), sequence(operation("provide_energy", "holder", 3, types=["colorless"])), sequence(operation("provide_energy", "holder", 1, types=["colorless"]))), operation("move_cards", "this_energy", 1, source="own_pokemon_attachment", destination="own_discard", timing="end_of_owners_turn")),
            "observability": ["observation_direct", "public_history"],
            "change_from_current": "the current encoder omits 1-versus-3 Colorless provision by holder stage and mandatory owner-turn-end discard",
            "runtime_engine_refs": ["Imitation-Learning/ptcg_engine/ptcgProgram 22/State.h:1095"],
            "formula_key": "energy_01_ignition_energy_provision", "formula_inputs": ["holder_evolution_stage", "turn_owner"], "formula_question": "provide 3 Colorless on Stage 1/2 else 1, then discard at owner's turn end", "human_review_ids": [],
        },
        16: {
            "verdict": "override_dynamic",
            "energy_profile": profile(["colorless"], 1, formula={"types": "all if holder Basic else colorless", "count": 1}, inputs=["holder_evolution_stage"]),
            "activation": {"event": "energy_continuous", "duration": "while_attached"},
            "program": conditional(expr("read", path="holder_is_basic_pokemon"), sequence(operation("provide_energy", "holder", 1, types=["all"], simultaneous_count_cap=1)), sequence(operation("provide_energy", "holder", 1, types=["colorless"]))),
            "observability": ["observation_direct", "observation_derived"],
            "change_from_current": "the current encoder omits Basic-holder every-type provision with a one-unit cap versus Colorless-only provision otherwise",
            "runtime_engine_refs": ["Imitation-Learning/ptcg_engine/ptcgProgram 22/State.h:1088"],
            "formula_key": "energy_01_prism_energy_provision", "formula_inputs": ["holder_evolution_stage", "requested_attack_cost_types", "other_attached_energy"], "formula_question": "one unit of any single needed type if holder Basic, else one Colorless", "human_review_ids": [],
        },
        12: {
            "verdict": "override_dynamic",
            "energy_profile": profile(["all"], 1, formula={"types": "all", "count": 1}, inputs=[]),
            "activation": {"event": "energy_continuous_and_holder_ko_by_opponent_attack_damage", "frequency": "once_per_game_per_owner_across_legacy_energy"},
            "program": sequence(operation("provide_energy", "holder", 1, types=["all"], simultaneous_count_cap=1), operation("modify_prize_rule", "opponent", -1, trigger="holder_ko_by_opponent_attack_damage", frequency="once_per_game_per_owner")),
            "observability": ["observation_direct", "public_history"],
            "change_from_current": "the current encoder omits one-unit every-type provision and once-per-game -1 Prize on opponent-attack-damage KO",
            "formula_key": "energy_01_legacy_energy_prize_reduction", "formula_inputs": ["holder_ko_cause", "legacy_energy_effect_already_used_by_owner"], "formula_question": "reduce prizes taken by 1 iff eligible KO and owner's Legacy effect unused, then mark used", "human_review_ids": [],
        },
    }


def build_batch() -> tuple[dict, list[dict]]:
    worklist = json.loads(WORKLIST.read_text(encoding="utf-8"))
    manifest = json.loads(BATCHES.read_text(encoding="utf-8"))
    batch = next(item for item in manifest["batches"] if item["batch_id"] == "energy-01")
    cards = {card["card_id"]: card for card in worklist["cards"]}
    semantics = effect_semantics()
    review = {item["id"]: item for item in json.loads(HUMAN_REVIEW.read_text(encoding="utf-8"))["records"]}
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8")) if EVIDENCE.exists() else None
    issues: list[dict] = []
    expected_special = {card_id for card_id in batch["card_ids"] if cards[card_id]["effects"]}
    if set(semantics) != expected_special:
        issues.append({"code": "semantic_card_key_mismatch", "missing": sorted(expected_special - set(semantics)), "extra": sorted(set(semantics) - expected_special)})
    audited_cards = []
    formula_queue = []
    verdicts = Counter()
    for card_id in batch["card_ids"]:
        source = cards[card_id]
        attachment_id = f"card:{card_id}:energy_attachment"
        card_checks = {
            "exact_card_source_present": bool(source["engine_card_source"]["path"]),
            "energy_definition_shape": "basicEnergy" in source["engine_card_source"]["method_calls"] if card_id in BASIC_TYPES else "specialEnergy" in source["engine_card_source"]["method_calls"],
        }
        card_refs = [f"{source['engine_card_source']['path']}:{source['engine_card_source']['line_start']}"]
        if evidence:
            count = len(evidence["samples"][attachment_id])
            card_checks["recorded_attachment_coverage_accounted"] = count == evidence["coverage"]["sample_counts"][attachment_id] and evidence["checks"]["full_dataset_scan_complete"]
            card_checks["recorded_attachment_or_exact_source_fallback"] = True
            card_refs.append(f"{EVIDENCE.name}#samples/{attachment_id} ({count} distinct recorded attachments)")
        if card_id in BASIC_TYPES:
            verdicts["ordinary_field"] += 1
            passed = all(card_checks.values()) and not source["effects"]
            if not passed:
                issues.append({"code": "basic_energy_validation_failed", "card_id": card_id, "checks": card_checks})
            audited_cards.append({
                "card_id": card_id, "card_name": source["card_name"], "subtype": source["subtype"], "frequency": source["frequency"],
                "verdict": "ordinary_field", "energy_profile": profile([BASIC_TYPES[card_id]], 1), "additional_effects": [],
                "engine_card_source": source["engine_card_source"], "effects": [],
                "change_from_current": "delegated exact Basic Energy type/count; no additional semantics exist",
                "validation": {"status": "passed" if passed else "failed", "checks": card_checks, "refs": card_refs}, "audit_status": "complete" if passed else "draft",
            })
            continue
        sem = semantics[card_id]
        effect = source["effects"][0]
        effect_checks = {
            **card_checks,
            "exact_effect_chain_present": len(effect["engine"].get("chain_sha256", "")) == 64,
            "exact_text_present": bool(effect["text"]),
            "program_present": bool(sem["program"]),
            "human_reviews_resolved": all(review[item]["status"] == "resolved" for item in sem["human_review_ids"]),
        }
        passed = all(effect_checks.values())
        if not passed:
            issues.append({"code": "special_energy_validation_failed", "effect_id": effect["effect_id"], "checks": effect_checks})
        verdicts[sem["verdict"]] += 1
        record = {
            "effect_id": effect["effect_id"], "kind": effect["kind"], "text": effect["text"], "engine": effect["engine"], "current_encoder": effect["current_encoder"],
            **sem, "validation": {"status": "passed" if passed else "failed", "checks": effect_checks, "refs": [*card_refs, f"{effect['engine']['source_path']}:{effect['engine']['source_line_start']}"]},
            "audit_status": "complete" if passed else "draft",
        }
        if sem["formula_key"]:
            formula_queue.append({"formula_key": sem["formula_key"], "effect_id": effect["effect_id"], "owner": "B08", "required_inputs": sem["formula_inputs"], "question": sem["formula_question"], "status": "queued"})
        audited_cards.append({
            "card_id": card_id, "card_name": source["card_name"], "subtype": source["subtype"], "frequency": source["frequency"], "verdict": sem["verdict"],
            "energy_profile": sem["energy_profile"], "engine_card_source": source["engine_card_source"], "effects": [record],
            "validation": {"status": "passed" if passed else "failed", "checks": card_checks, "refs": card_refs}, "audit_status": "complete" if passed else "draft",
        })
    complete = not issues and len(audited_cards) == 18 and all(card["audit_status"] == "complete" for card in audited_cards)
    result = {
        "schema_version": SCHEMA_VERSION, "batch_id": "energy-01", "status": "complete" if complete else "draft_pending_validation",
        "card_ids": batch["card_ids"], "cards": audited_cards, "formula_queue": formula_queue,
        "summary": {"cards": len(audited_cards), "effects": sum(len(card["effects"]) for card in audited_cards), "subtypes": dict(sorted(Counter(card["subtype"] for card in audited_cards).items())), "verdicts": dict(sorted(verdicts.items())), "formula_queue": len(formula_queue), "issues": len(issues)},
    }
    return result, issues


def main() -> int:
    batch, issues = build_batch()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "energy-01-draft.json").write_bytes(json_bytes(batch))
    if batch["status"] == "complete":
        (OUTPUT / "energy-01.json").write_bytes(json_bytes(batch))
    (OUTPUT / "energy-01-issues.json").write_bytes(json_bytes({"schema_version": SCHEMA_VERSION, "issues": issues}))
    print(json.dumps(batch["summary"], indent=2, sort_keys=True))
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
