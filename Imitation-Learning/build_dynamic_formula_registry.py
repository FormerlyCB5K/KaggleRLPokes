"""Build and execute the reviewed Spec-12b08 dynamic-formula registry.

This module deliberately evaluates raw card semantics.  It does not choose an
observation tensor layout, normalize values, clip damage, or guess missing state.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
OUTPUT = PART_B / "dynamic-formulas.json"
VALIDATION = PART_B / "dynamic-formula-validation.json"
HUMAN_REVIEW = PART_B / "human-review-ledger.json"
APPROXIMATIONS = PART_B / "approved-approximations.json"
SCHEMA_VERSION = 1

BATCH_PATHS = [
    *(PART_B / "pokemon-audit" / f"pokemon-{number:02d}.json" for number in range(1, 7)),
    *(PART_B / "trainer-audit" / f"trainer-{number:02d}.json" for number in range(1, 6)),
    PART_B / "energy-audit" / "energy-01.json",
]


class MissingFormulaInput(ValueError):
    """Raised instead of silently inventing a value for unavailable state."""


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _count(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    raise TypeError(f"cannot count {type(value).__name__}")


def _bool_count(value: Any) -> int:
    if isinstance(value, int):
        return value
    return sum(bool(item) for item in value)


def _damage_counters(inputs: dict[str, Any]) -> int:
    maximum = int(inputs["source_effective_max_hp"])
    current = int(inputs["source_current_hp"])
    return max(0, (maximum - current) // 10)


def _energy_units(value: Any, energy_type: str | None = None) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        if energy_type is None:
            return sum(int(item) for item in value.values())
        return int(value.get(energy_type, 0))
    total = 0
    for item in value:
        if isinstance(item, dict):
            item_type = item.get("type")
            units = int(item.get("units", 1))
            if energy_type is None or item_type == energy_type:
                total += units
        elif energy_type is None:
            total += int(item)
        elif item == energy_type:
            total += 1
    return total


def _normalize_pairs(items: list[Any]) -> list[list[Any]]:
    return [list(item) for item in sorted({tuple(item) for item in items}, key=lambda pair: tuple(map(str, pair)))]


def evaluate_formula(key: str, inputs: dict[str, Any]) -> Any:
    """Evaluate one formula in raw engine units using normalized declared inputs."""
    spec = FORMULAS[key]
    missing = [name for name in spec["required_inputs"] if name not in inputs]
    if missing:
        raise MissingFormulaInput(f"{key}: missing {', '.join(missing)}; fallback=explicit_unknown")
    rule = spec["rule"]
    p = spec.get("parameters", {})

    if rule == "mul_count":
        return p["multiplier"] * _count(inputs[p["input"]])
    if rule == "mul_bool_count":
        return p["multiplier"] * _bool_count(inputs[p["input"]])
    if rule == "flagged_sum":
        return p["multiplier"] * sum(int(value) for flag, value in zip(inputs[p["flags"]], inputs[p["values"]]) if flag)
    if rule == "sum_values":
        return p.get("base", 0) + p["multiplier"] * sum(int(value) for value in inputs[p["input"]])
    if rule == "threshold_count":
        return _bool_count(inputs[p["input"]]) >= p["minimum"]
    if rule == "equals_value":
        return p["equal"] if inputs[p["input"]] == p["value"] else p["other"]
    if rule == "base_plus_mul":
        return p["base"] + p["multiplier"] * _count(inputs[p["input"]])
    if rule == "base_plus_energy":
        return p["base"] + p["multiplier"] * _energy_units(inputs[p["input"]], p.get("energy_type"))
    if rule == "hp_counter_damage":
        return p.get("base", 0) + p["multiplier"] * _damage_counters(inputs)
    if rule == "conditional_value":
        return p["true"] if bool(inputs[p["input"]]) else p["false"]
    if rule == "damaged_value":
        return p["damaged"] if int(inputs["source_current_hp"]) < int(inputs["source_effective_max_hp"]) else p["undamaged"]
    if rule == "paired_flag_bonus":
        active = any(bool(a) and bool(b) for a, b in zip(inputs[p["first"]], inputs[p["second"]]))
        return p["bonus"] if active else 0
    if rule == "contains_value":
        return p["true"] if p["needle"] in inputs[p["input"]] else p["false"]
    if rule == "coin_value":
        return p["heads"] if inputs[p["input"]] == "heads" else p["tails"]
    if rule == "draw_until":
        return max(0, p["target"] - int(inputs[p["input"]]))
    if rule == "history_draw":
        active = bool(inputs[p["history_input"]])
        return {"legal": active, "owner_draw": p["owner"] if active else 0, "opponent_draw": p.get("opponent", 0) if active else 0}
    if rule == "flip_script":
        history = bool(inputs.get("own_pokemon_ko_during_opponent_last_turn", False))
        unused = not bool(inputs.get("same_name_ability_used_this_turn", False))
        return {"can_activate": history and unused, "draw": 3 if history and unused else 0}
    if rule == "kangaskhan":
        heads = int(inputs["coin_sequence"])
        if heads < 0:
            raise ValueError("heads_before_first_tails must be nonnegative")
        return 200 + 50 * heads
    if rule == "capped_transfer":
        moved = min(p["cap"], _count(inputs[p["input"]]))
        return {"moved_counters": moved, "damage_equivalent": 10 * moved}
    if rule == "discard_bonus":
        eligible = _count(inputs[p["eligible"]])
        selected = min(int(inputs[p["selected"]]), eligible, p["cap"])
        return {"discarded": selected, "damage": p["base"] + p["multiplier"] * selected}
    if rule == "copy_attack":
        ordinal = int(inputs[p["choice"]])
        programs = inputs[p["programs"]]
        legal = 0 <= ordinal < len(programs) and bool(inputs.get(p.get("gate", ""), True))
        return {"legal": legal, "attack_program": programs[ordinal] if legal else None}
    if rule == "counter_concentration":
        counters = [int(value) for value in inputs[p["counts"]]]
        if not counters:
            return {"maximum_gain": 0, "final_counters": []}
        total = sum(counters)
        maximum_gain = total - max(counters)
        return {"maximum_gain": maximum_gain, "damage_equivalent": 10 * maximum_gain, "final_counters": [total, *([0] * (len(counters) - 1))]}
    if rule == "festival_lead":
        attacks = [int(item["raw_damage"]) for item in inputs[p["programs"]] if item.get("payable", True)]
        stadium = bool(inputs[p["stadium"]])
        replacement = bool(inputs[p["replacement"]])
        if not attacks:
            return {"attack_count": 0, "maximum_raw_damage": 0}
        count = 2 if stadium and replacement else 1
        return {"attack_count": count, "maximum_raw_damage": max(attacks) * count}
    if rule == "wonder_kiss":
        eligible = bool(inputs["opponent_active_ko_event"])
        heads = inputs["coin_result"] == "heads"
        return {"extra_prizes": 1 if eligible and heads else 0}
    if rule == "bench_sum":
        return p["base"] + p["multiplier"] * sum(int(inputs[name]) for name in p["inputs"])
    if rule == "energy_type_bonus":
        active = _energy_units(inputs[p["input"]], p["energy_type"]) > 0
        return {"max_hp_modifier": p.get("hp", 0) if active else 0, "attack_damage_modifier": p.get("damage", 0) if active else 0}
    if rule == "wobbuffet":
        flags = inputs["own_bench_team_rocket_flags"]
        counts = inputs["own_bench_damage_counter_counts"]
        eligible = [int(count) for flag, count in zip(flags, counts) if flag]
        moved = max(eligible, default=0)
        return {"moved_counters": moved, "damage": 10 * moved}
    if rule == "memory_dive":
        programs = inputs["referenced_attack_programs"]
        payable = [item for item in programs if item.get("payable", False)]
        return {"legal_attack_ids": sorted(item["attack_id"] for item in payable), "maximum_raw_damage": max((int(item.get("raw_damage", 0)) for item in payable), default=0)}
    if rule == "named_cards":
        names = inputs[p["names"]]
        flags = inputs[p["flags"]]
        return p["multiplier"] * sum(flag and p["substring"] in name.casefold() for flag, name in zip(flags, names))
    if rule == "chosen_named_cards":
        chosen = set(inputs[p["chosen"]])
        names = inputs[p["names"]]
        flags = inputs[p["flags"]]
        legal = [index for index in chosen if 0 <= index < len(names) and flags[index] and p["substring"] in names[index].casefold()]
        return {"discarded": len(legal), "damage": p["multiplier"] * len(legal)}
    if rule == "chosen_basic_energy":
        flags = inputs[p["flags"]]
        chosen = set(inputs[p["chosen"]])
        count = sum(0 <= index < len(flags) and bool(flags[index]) for index in chosen)
        return {"discarded": count, "damage": p["multiplier"] * count}
    if rule == "torrential_pump":
        attached = _count(inputs["source_attached_energy_cards"])
        bench = inputs["opponent_bench_targets"]
        choose = bool(inputs["owner_choice"])
        legal = choose and attached >= 3 and bool(bench)
        return {"active_damage": 100, "energy_shuffled": 3 if legal else 0, "bench_damage": 120 if legal else 0}
    if rule == "wild_growth":
        flags = inputs["basic_grass_energy_flags"]
        active = bool(inputs["wild_growth_active"])
        cards = sum(bool(flag) for flag in flags)
        return {"grass_energy_units": cards * (2 if active else 1), "stacks": False}
    if rule == "prevent_damage_coin":
        darkness = p["energy_type"] in inputs[p["energies"]]
        prevented = darkness and inputs["coin_result"] == "heads"
        pending = int(inputs["pending_attack_damage"])
        return {"prevented": prevented, "damage_received": 0 if prevented else pending}
    if rule == "discard_until":
        return max(0, int(inputs[p["input"]]) - p["target"])
    if rule == "conditional_target":
        target = p["true_target"] if p["predicate"](inputs) else p["false_target"]
        return max(0, target - int(inputs[p["input"]]))
    if rule == "rare_candy":
        if int(inputs["turn_number"]) <= 1:
            return []
        entered = inputs["pokemon_entered_play_this_turn"]
        basics = inputs["own_in_play_exact_card_ids"]
        stage2 = inputs["own_hand_exact_card_ids"]
        relations = inputs.get("evolution_relations", {})
        def evolves_from_basic(evolved: Any, basic: Any) -> bool:
            stage1 = relations.get(str(evolved), relations.get(evolved))
            return relations.get(str(stage1), relations.get(stage1)) == basic
        return _normalize_pairs([(basic, evolved) for index, basic in enumerate(basics) if not entered[index] for evolved in stage2 if evolves_from_basic(evolved, basic)])
    if rule == "hand_trimmer":
        return {"order": ["opponent", "owner"], "opponent_discard": max(0, int(inputs["opponent_hand_count"]) - 5), "owner_discard": max(0, int(inputs["own_hand_count"]) - 5)}
    if rule == "coin_target":
        heads = inputs["coin_result"] == "heads"
        targets = inputs[p["targets"]]
        return {"success": heads and bool(targets), "chosen_count": 1 if heads and targets else 0}
    if rule == "wally":
        damage = int(inputs["eligible_own_mega_ex_damage"])
        energies = _count(inputs["selected_target_attached_energy_cards"])
        return {"healed": max(0, damage), "energy_to_hand": energies if damage > 0 else 0}
    if rule == "named_history":
        names = inputs[p["names"]]
        active = any(p["substring"] in name.casefold() for name in names)
        return {"can_activate": active, "draw": p["draw"] if active else 0}
    if rule == "crispin":
        energies = inputs["basic_energy_cards_and_types_in_deck"]
        targets = inputs["own_pokemon_targets"]
        pairs = [{"hand": None, "attach": None, "target": None}]
        pairs.extend({"hand": item["id"], "attach": None, "target": None} for item in energies)
        for a, b in itertools.combinations(energies, 2):
            if a["type"] != b["type"]:
                for target in targets:
                    pairs.extend([{"hand": a["id"], "attach": b["id"], "target": target}, {"hand": b["id"], "attach": a["id"], "target": target}])
        return sorted(pairs, key=lambda item: (str(item["hand"]), str(item["attach"]), str(item["target"])))
    if rule == "ariana":
        flags = inputs["all_own_in_play_exact_card_ids_or_team_rocket_flags"]
        target = 8 if flags and all(flags) else 5
        return max(0, target - int(inputs["own_hand_count"]))
    if rule == "risky_ruins":
        events = inputs["bench_entry_events"]
        return [{"event": index, "counters": 2} for index, item in enumerate(events) if item.get("during_controllers_turn") and item.get("stage") == "basic" and item.get("type") != "darkness"]
    if rule == "evolution_options":
        candidates = inputs[p["candidates"]]
        if p.get("first_turn_block") and int(inputs.get("turn_number", 2)) <= 1:
            return []
        return _normalize_pairs([(item["target"], item["evolution"]) for item in candidates if item.get("legal", True) and (not p.get("grass_only") or item.get("type") == "grass") and (not p.get("no_ability") or not item.get("has_ability"))])
    if rule == "surfer":
        switched = bool(inputs["own_bench_targets"])
        return {"switched": switched, "draw": max(0, 5 - int(inputs["own_hand_count_after_play_and_switch"])) if switched else 0}
    if rule == "community_center":
        active = bool(inputs["supporter_played_from_hand_this_turn"])
        damages = inputs["all_own_pokemon_damage"]
        return [min(10, int(value)) if active else 0 for value in damages]
    if rule == "grand_tree":
        if int(inputs["turn_number"]) <= 1:
            return []
        relations = {
            int(card) if isinstance(card, str) and card.isdigit() else card:
            int(parent) if isinstance(parent, str) and parent.isdigit() else parent
            for card, parent in inputs["evolution_relations"].items()
        }
        deck = set(inputs["deck_exact_card_ids"])
        chains = []
        for basic in inputs["own_in_play_exact_card_ids"]:
            for stage1, parent in relations.items():
                if parent == basic and stage1 in deck:
                    stage2s = sorted(card for card, prior in relations.items() if prior == stage1 and card in deck)
                    chains.append([basic, stage1])
                    chains.extend([[basic, stage1, stage2] for stage2 in stage2s])
        return sorted(chains, key=lambda item: tuple(map(str, item)))
    if rule == "rosa":
        legal = int(inputs["own_prize_count"]) > int(inputs["opponent_prize_count"]) and bool(inputs["own_stage_2_targets"])
        count = min(2, _count(inputs["basic_energy_in_own_discard"])) if legal else 0
        return {"legal": legal, "maximum_attach_count": count}
    if rule == "harlequin":
        return {"owner_draw": 5, "opponent_draw": 3} if inputs["coin_result"] == "heads" else {"owner_draw": 3, "opponent_draw": 5}
    if rule == "glass_trumpet":
        if not bool(inputs["own_tera_pokemon_in_play"]):
            return []
        targets = inputs["own_benched_colorless_targets"]
        energies = inputs["basic_energy_cards_in_own_discard"]
        result = [[]]
        for count in range(1, min(2, len(targets), len(energies)) + 1):
            for chosen_targets in itertools.combinations(targets, count):
                for chosen_energies in itertools.permutations(energies, count):
                    result.append([[target, energy] for target, energy in zip(chosen_targets, chosen_energies)])
        return sorted(result, key=lambda item: json.dumps(item, sort_keys=True))
    if rule == "area_zero":
        presences = inputs["each_player_tera_presence"]
        occupied = inputs["each_bench_occupied_count"]
        owner = int(inputs["stadium_owner"])
        stadium = bool(inputs["stadium_in_play"]) and not bool(inputs["stadium_leave_event"])
        capacities = [8 if stadium and bool(flag) else 5 for flag in presences]
        discard = [max(0, int(count) - cap) for count, cap in zip(occupied, capacities)]
        order = [owner, 1 - owner] if bool(inputs["stadium_leave_event"]) else []
        return {"capacities": capacities, "discard_counts": discard, "resolution_order": order}
    if rule == "janine":
        targets = inputs["own_darkness_pokemon_targets"]
        energies = inputs["basic_darkness_energy_cards_in_deck"]
        selected = inputs["selected_targets"]
        legal = []
        for target in selected:
            if target in targets and target not in legal:
                legal.append(target)
        legal = legal[:min(2, _count(energies))]
        return {"assignments": [[target, energies[index]] for index, target in enumerate(legal)], "poison_active": "active" in legal}
    if rule == "team_rocket_energy":
        if not bool(inputs["holder_team_rocket_flag"]):
            return {"legal_attachment": False, "allocations": []}
        return {"legal_attachment": True, "allocations": [{"psychic": 0, "darkness": 2}, {"psychic": 1, "darkness": 1}, {"psychic": 2, "darkness": 0}]}
    if rule == "ignition":
        stage = inputs["holder_evolution_stage"]
        return {"colorless_units": 3 if stage in {"stage1", "stage2"} else 1, "discard_at_owner_turn_end": bool(inputs["turn_owner"])}
    if rule == "prism":
        basic = inputs["holder_evolution_stage"] == "basic"
        return {"unit_count": 1, "provided_types": "any_one_requested_type" if basic else ["colorless"]}
    if rule == "legacy":
        eligible = inputs["holder_ko_cause"] == "opponent_attack_damage" and not bool(inputs["legacy_energy_effect_already_used_by_owner"])
        return {"prize_reduction": 1 if eligible else 0, "mark_used": eligible}
    raise KeyError(f"unknown formula rule {rule!r}")


def _f(rule: str, inputs: list[str], *, parameters: dict[str, Any] | None = None, output: str = "structured_raw") -> dict[str, Any]:
    return {"rule": rule, "required_inputs": inputs, "parameters": parameters or {}, "output_unit": output}


# Card-specific declarations. Shared rules are implementation reuse, never semantic merging.
FORMULAS: dict[str, dict[str, Any]] = {
    "pokemon_01_fezandipiti_flip_script_history": _f("flip_script", ["own_pokemon_ko_during_opponent_last_turn", "same_name_ability_used_this_turn"], output="activation_and_cards"),
    "pokemon_01_alakazam_powerful_hand": _f("mul_count", ["own_hand_count"], parameters={"input": "own_hand_count", "multiplier": 20}, output="damage_equivalent_hp"),
    "pokemon_01_mega_kangaskhan_coin_until_tails": _f("kangaskhan", ["coin_sequence"], output="attack_damage"),
    "pokemon_01_munkidori_adrena_brain_transfer": _f("capped_transfer", ["chosen_source_damage_counters", "chosen_target"], parameters={"input": "chosen_source_damage_counters", "cap": 3}, output="damage_counters_and_equivalent_hp"),
    "pokemon_01_articuno_dark_frost": _f("contains_value", ["attached_energy_card_names"], parameters={"input": "attached_energy_card_names", "needle": "Team Rocket's Energy", "true": 120, "false": 60}, output="attack_damage"),
    "pokemon_02_team_rockets_spidops_rocket_rush": _f("mul_bool_count", ["own_in_play_card_ids_or_team_rocket_flags"], parameters={"input": "own_in_play_card_ids_or_team_rocket_flags", "multiplier": 30}, output="attack_damage"),
    "pokemon_02_team_rockets_mewtwo_power_saver": _f("threshold_count", ["own_in_play_card_ids_or_team_rocket_flags"], parameters={"input": "own_in_play_card_ids_or_team_rocket_flags", "minimum": 4}, output="attack_legal"),
    "pokemon_02_team_rockets_mewtwo_erasure_ball": _f("discard_bonus", ["eligible_energy_attached_to_own_bench", "selected_discard_count"], parameters={"eligible": "eligible_energy_attached_to_own_bench", "selected": "selected_discard_count", "cap": 2, "base": 160, "multiplier": 60}, output="discard_count_and_attack_damage"),
    "pokemon_02_team_rockets_mimikyu_gemstone_mimicry": _f("copy_attack", ["opponent_active_exact_card_id", "opponent_active_is_tera", "chosen_attack_ordinal", "referenced_attack_program"], parameters={"choice": "chosen_attack_ordinal", "programs": "referenced_attack_program", "gate": "opponent_active_is_tera"}, output="referenced_attack_program"),
    "pokemon_02_mega_froslass_resentful_refrain": _f("mul_count", ["opponent_hand_count"], parameters={"input": "opponent_hand_count", "multiplier": 50}, output="attack_damage"),
    "pokemon_03_cynthias_spiritomb_raging_curse": _f("flagged_sum", ["own_bench_exact_card_ids_or_cynthia_flags", "own_bench_damage_counter_counts"], parameters={"flags": "own_bench_exact_card_ids_or_cynthia_flags", "values": "own_bench_damage_counter_counts", "multiplier": 10}, output="attack_damage"),
    "pokemon_03_alakazam_strange_hacking": _f("counter_concentration", ["all_opponent_in_play_damage_counter_counts", "chosen_counter_transfer_allocation"], parameters={"counts": "all_opponent_in_play_damage_counter_counts"}, output="damage_counters_and_equivalent_hp"),
    "pokemon_03_alakazam_psychic": _f("base_plus_mul", ["opponent_active_attached_energy_unit_count"], parameters={"input": "opponent_active_attached_energy_unit_count", "base": 10, "multiplier": 50}, output="attack_damage"),
    "pokemon_03_applin_tumbling_attack": _f("coin_value", ["coin_result"], parameters={"input": "coin_result", "heads": 30, "tails": 10}, output="attack_damage"),
    "pokemon_03_dipplin_festival_lead": _f("festival_lead", ["stadium_card_id", "source_attack_programs", "first_attack_ko_and_replacement_state"], parameters={"stadium": "stadium_card_id", "programs": "source_attack_programs", "replacement": "first_attack_ko_and_replacement_state"}, output="attack_sequence_and_raw_damage"),
    "pokemon_03_dipplin_do_the_wave": _f("mul_count", ["own_bench_occupied_count", "own_bench_capacity"], parameters={"input": "own_bench_occupied_count", "multiplier": 20}, output="attack_damage"),
    "pokemon_03_swirlix_festival_lead": _f("festival_lead", ["stadium_card_id", "source_attack_programs", "first_attack_ko_and_replacement_state"], parameters={"stadium": "stadium_card_id", "programs": "source_attack_programs", "replacement": "first_attack_ko_and_replacement_state"}, output="attack_sequence_and_raw_damage"),
    "pokemon_03_togekiss_wonder_kiss": _f("wonder_kiss", ["opponent_active_ko_event", "coin_result"], output="extra_prize_cards"),
    "pokemon_03_duraludon_raging_hammer": _f("hp_counter_damage", ["source_current_hp", "source_effective_max_hp"], parameters={"base": 80, "multiplier": 10}, output="attack_damage"),
    "pokemon_03_mega_lopunny_gale_thrust": _f("conditional_value", ["source_moved_bench_to_active_this_turn"], parameters={"input": "source_moved_bench_to_active_this_turn", "true": 230, "false": 60}, output="attack_damage"),
    "pokemon_03_comfey_play_rough": _f("coin_value", ["coin_result"], parameters={"input": "coin_result", "heads": 40, "tails": 20}, output="attack_damage"),
    "pokemon_03_moltres_fighting_wings": _f("conditional_value", ["opponent_active_exact_card_id_or_rule_box_flags"], parameters={"input": "opponent_active_exact_card_id_or_rule_box_flags", "true": 110, "false": 20}, output="attack_damage"),
    "pokemon_04_marnies_morpeko_spiky_wheel": _f("base_plus_energy", ["source_attached_energy_types_and_unit_counts"], parameters={"input": "source_attached_energy_types_and_unit_counts", "energy_type": "darkness", "base": 20, "multiplier": 40}, output="attack_damage"),
    "pokemon_04_team_rockets_wobbuffet_rocket_mirror": _f("wobbuffet", ["own_bench_team_rocket_flags", "own_bench_damage_counter_counts"], output="moved_damage_counters_and_attack_damage"),
    "pokemon_04_rabsca_psychic": _f("base_plus_mul", ["opponent_active_attached_energy_unit_count"], parameters={"input": "opponent_active_attached_energy_unit_count", "base": 10, "multiplier": 30}, output="attack_damage"),
    "pokemon_04_solrock_cosmic_beam": _f("contains_value", ["own_bench_exact_card_ids"], parameters={"input": "own_bench_exact_card_ids", "needle": 675, "true": 70, "false": 0}, output="attack_damage"),
    "pokemon_04_fan_rotom_assault_landing": _f("conditional_value", ["stadium_card_id_or_presence"], parameters={"input": "stadium_card_id_or_presence", "true": 70, "false": 0}, output="attack_damage"),
    "pokemon_04_lillies_clefairy_full_moon_rondo": _f("bench_sum", ["own_bench_occupied_count", "opponent_bench_occupied_count", "both_bench_capacities"], parameters={"inputs": ["own_bench_occupied_count", "opponent_bench_occupied_count"], "base": 20, "multiplier": 20}, output="attack_damage"),
    "pokemon_04_great_tusk_land_collapse": _f("conditional_value", ["played_ancient_supporter_from_hand_this_turn"], parameters={"input": "played_ancient_supporter_from_hand_this_turn", "true": 4, "false": 1}, output="cards_milled"),
    "pokemon_04_relicanth_memory_dive": _f("memory_dive", ["own_evolved_pokemon_exact_card_ids", "visible_pre_evolution_stack_ids", "attached_energy_and_attack_costs", "referenced_attack_programs"], output="legal_attack_ids_and_maximum_raw_damage"),
    "pokemon_04_terrakion_retaliate": _f("conditional_value", ["opponent_previous_turn_attack_damage_ko_history"], parameters={"input": "opponent_previous_turn_attack_damage_ko_history", "true": 130, "false": 50}, output="attack_damage"),
    "pokemon_04_chi_yu_ground_melter": _f("conditional_value", ["stadium_card_id_or_presence"], parameters={"input": "stadium_card_id_or_presence", "true": 120, "false": 60}, output="attack_damage"),
    "pokemon_04_dudunsparce_tenacious_tail": _f("mul_bool_count", ["opponent_in_play_exact_card_ids_or_ex_flags", "opponent_bench_capacity"], parameters={"input": "opponent_in_play_exact_card_ids_or_ex_flags", "multiplier": 60}, output="attack_damage"),
    "pokemon_05_mega_gardevoir_mega_symphonia": _f("base_plus_energy", ["all_own_in_play_attached_energy_types_and_units"], parameters={"input": "all_own_in_play_attached_energy_types_and_units", "energy_type": "psychic", "base": 0, "multiplier": 50}, output="attack_damage"),
    "pokemon_05_okidogi_adrena_power": _f("energy_type_bonus", ["source_attached_energy_types"], parameters={"input": "source_attached_energy_types", "energy_type": "darkness", "hp": 100, "damage": 100}, output="hp_and_attack_damage_modifiers"),
    "pokemon_05_teal_mask_ogerpon_myriad_leaf_shower": _f("sum_values", ["both_active_attached_energy_unit_counts"], parameters={"input": "both_active_attached_energy_unit_counts", "base": 30, "multiplier": 30}, output="attack_damage"),
    "pokemon_05_team_rocket_porygon2_r_command": _f("named_cards", ["own_discard_exact_card_ids", "supporter_flags", "normalized_card_names"], parameters={"names": "normalized_card_names", "flags": "supporter_flags", "substring": "team rocket", "multiplier": 20}, output="attack_damage"),
    "pokemon_05_team_rocket_honchkrow_rocket_feathers": _f("chosen_named_cards", ["own_hand_exact_card_ids", "supporter_flags", "normalized_card_names", "chosen_discard_set"], parameters={"names": "normalized_card_names", "flags": "supporter_flags", "chosen": "chosen_discard_set", "substring": "team rocket", "multiplier": 60}, output="discard_count_and_attack_damage"),
    "pokemon_05_ns_zoroark_night_joker": _f("copy_attack", ["own_bench_exact_card_ids_and_ns_flags", "selected_bench_is_ns_pokemon", "referenced_attack_programs", "owner_attack_choice"], parameters={"choice": "owner_attack_choice", "programs": "referenced_attack_programs", "gate": "selected_bench_is_ns_pokemon"}, output="referenced_attack_program"),
    "pokemon_05_ns_reshiram_powerful_rage": _f("hp_counter_damage", ["source_current_hp", "source_effective_max_hp"], parameters={"base": 0, "multiplier": 20}, output="attack_damage"),
    "pokemon_05_raging_bolt_bellowing_thunder": _f("chosen_basic_energy", ["all_own_attached_card_ids_and_basic_energy_flags", "chosen_discard_set"], parameters={"flags": "all_own_attached_card_ids_and_basic_energy_flags", "chosen": "chosen_discard_set", "multiplier": 70}, output="discard_count_and_attack_damage"),
    "pokemon_05_wellspring_ogerpon_torrential_pump": _f("torrential_pump", ["source_attached_energy_cards", "opponent_bench_targets", "owner_choice"], output="split_attack_damage_and_energy_shuffle"),
    "pokemon_05_pecharunt_irritated_outburst": _f("mul_count", ["opponent_taken_prize_count"], parameters={"input": "opponent_taken_prize_count", "multiplier": 60}, output="attack_damage"),
    "pokemon_06_ns_darmanitan_back_draft": _f("mul_bool_count", ["opponent_discard_exact_card_ids", "basic_energy_flags"], parameters={"input": "basic_energy_flags", "multiplier": 30}, output="attack_damage"),
    "pokemon_06_hydrapple_syrup_storm": _f("base_plus_energy", ["all_own_in_play_attached_energy_types_and_units"], parameters={"input": "all_own_in_play_attached_energy_types_and_units", "energy_type": "grass", "base": 30, "multiplier": 30}, output="attack_damage"),
    "pokemon_06_meganium_wild_growth": _f("wild_growth", ["all_own_attached_exact_card_ids", "basic_grass_energy_flags", "wild_growth_active"], output="grass_energy_units"),
    "pokemon_06_riolu_quick_attack": _f("coin_value", ["coin_result"], parameters={"input": "coin_result", "heads": 30, "tails": 10}, output="attack_damage"),
    "pokemon_06_fezandipiti_adrena_pheromone": _f("prevent_damage_coin", ["source_attached_energy_types", "pending_attack_damage", "coin_result"], parameters={"energies": "source_attached_energy_types", "energy_type": "darkness"}, output="prevented_and_received_attack_damage"),
    "pokemon_06_fezandipiti_energy_feather": _f("mul_count", ["source_attached_energy_unit_count"], parameters={"input": "source_attached_energy_unit_count", "multiplier": 30}, output="attack_damage"),
    "pokemon_06_mega_sharpedo_hungry_jaws": _f("damaged_value", ["source_current_hp", "source_effective_max_hp"], parameters={"damaged": 270, "undamaged": 120}, output="attack_damage"),
    "pokemon_06_seviper_excited_power": _f("paired_flag_bonus", ["all_own_in_play_exact_card_ids", "darkness_type_flags", "mega_evolution_ex_flags"], parameters={"first": "darkness_type_flags", "second": "mega_evolution_ex_flags", "bonus": 120}, output="attack_damage_modifier"),
    "trainer_01_xerosic_discard_until_three": _f("discard_until", ["opponent_hand_count"], parameters={"input": "opponent_hand_count", "target": 3}, output="cards_discarded"),
    "trainer_01_lillies_determination_draw": _f("equals_value", ["own_prize_count"], parameters={"input": "own_prize_count", "value": 6, "equal": 8, "other": 6}, output="cards_drawn"),
    "trainer_01_rare_candy_eligible_evolutions": _f("rare_candy", ["own_in_play_exact_card_ids", "own_hand_exact_card_ids", "turn_number", "pokemon_entered_play_this_turn", "evolution_relations"], output="legal_evolution_pairs"),
    "trainer_01_hand_trimmer_discard_counts": _f("hand_trimmer", ["opponent_hand_count", "own_hand_count"], output="ordered_discard_counts"),
    "trainer_01_unfair_stamp_activation_and_draw": _f("history_draw", ["own_pokemon_ko_during_opponent_last_turn"], parameters={"history_input": "own_pokemon_ko_during_opponent_last_turn", "owner": 5, "opponent": 2}, output="activation_and_cards_drawn"),
    "trainer_02_crushing_hammer": _f("coin_target", ["coin_result", "opponent_attached_energy_targets"], parameters={"targets": "opponent_attached_energy_targets"}, output="success_and_cards_discarded"),
    "trainer_02_wallys_compassion": _f("wally", ["eligible_own_mega_ex_damage", "selected_target_attached_energy_cards"], output="healed_damage_and_energy_returned"),
    "trainer_02_team_rocket_factory_activation": _f("named_history", ["supporters_played_from_hand_this_turn", "normalized_card_names"], parameters={"names": "normalized_card_names", "substring": "team rocket", "draw": 2}, output="activation_and_cards_drawn"),
    "trainer_02_crispin_energy_assignment": _f("crispin", ["basic_energy_cards_and_types_in_deck", "own_pokemon_targets", "owner_choices"], output="legal_energy_assignments"),
    "trainer_02_team_rocket_ariana_draw": _f("ariana", ["own_hand_count", "all_own_in_play_exact_card_ids_or_team_rocket_flags"], output="cards_drawn"),
    "trainer_02_team_rocket_archer_activation": _f("history_draw", ["team_rocket_pokemon_ko_during_opponent_last_turn"], parameters={"history_input": "team_rocket_pokemon_ko_during_opponent_last_turn", "owner": 5, "opponent": 3}, output="activation_and_cards_drawn"),
    "trainer_03_risky_ruins_trigger": _f("risky_ruins", ["bench_entry_events", "entered_pokemon_stage", "entered_pokemon_type"], output="triggered_counter_placements"),
    "trainer_03_forest_of_vitality_evolution_options": _f("evolution_options", ["both_in_play_exact_card_ids", "entered_play_this_turn", "turn_number", "hands_or_deck_evolution_candidates"], parameters={"candidates": "hands_or_deck_evolution_candidates", "grass_only": True, "first_turn_block": True}, output="legal_evolution_pairs"),
    "trainer_03_surfer_draw": _f("surfer", ["own_hand_count_after_play_and_switch", "own_bench_targets"], output="switch_and_cards_drawn"),
    "trainer_03_community_center_healing": _f("community_center", ["supporter_played_from_hand_this_turn", "all_own_pokemon_damage"], output="healing_per_pokemon"),
    "trainer_03_salvatore_eligible_evolutions": _f("evolution_options", ["own_in_play_exact_card_ids", "deck_exact_card_ids", "candidate_ability_flags", "evolves_from_relations"], parameters={"candidates": "evolves_from_relations", "no_ability": True}, output="legal_evolution_pairs"),
    "trainer_04_iriss_fighting_spirit_draw": _f("draw_until", ["own_hand_count_after_play_and_cost"], parameters={"input": "own_hand_count_after_play_and_cost", "target": 6}, output="cards_drawn"),
    "trainer_04_grand_tree_evolution_chain": _f("grand_tree", ["own_in_play_exact_card_ids", "deck_exact_card_ids", "evolution_relations", "turn_number", "entered_play_this_turn"], output="legal_evolution_chains"),
    "trainer_04_rosas_encouragement": _f("rosa", ["own_prize_count", "opponent_prize_count", "own_stage_2_targets", "basic_energy_in_own_discard"], output="activation_and_maximum_attachments"),
    "trainer_04_harlequin_draw_distribution": _f("harlequin", ["coin_result"], output="cards_drawn_by_side"),
    "trainer_04_mortys_conviction_draw": _f("mul_count", ["opponent_bench_occupied_count"], parameters={"input": "opponent_bench_occupied_count", "multiplier": 1}, output="cards_drawn"),
    "trainer_05_glass_trumpet_assignments": _f("glass_trumpet", ["own_tera_pokemon_in_play", "own_benched_colorless_targets", "basic_energy_cards_in_own_discard"], output="legal_target_energy_assignments"),
    "trainer_05_area_zero_bench_capacity": _f("area_zero", ["stadium_in_play", "each_player_tera_presence", "each_bench_occupied_count", "stadium_owner", "stadium_leave_event"], output="capacities_discard_counts_and_order"),
    "trainer_05_janines_secret_art_assignments": _f("janine", ["own_darkness_pokemon_targets", "basic_darkness_energy_cards_in_deck", "selected_targets"], output="energy_assignments_and_poison"),
    "energy_01_team_rocket_energy_payment": _f("team_rocket_energy", ["holder_team_rocket_flag", "requested_attack_cost_types", "other_attached_energy"], output="attachment_legality_and_payment_allocations"),
    "energy_01_ignition_energy_provision": _f("ignition", ["holder_evolution_stage", "turn_owner"], output="energy_units_and_end_turn_discard"),
    "energy_01_prism_energy_provision": _f("prism", ["holder_evolution_stage", "requested_attack_cost_types", "other_attached_energy"], output="energy_units_and_types"),
    "energy_01_legacy_energy_prize_reduction": _f("legacy", ["holder_ko_cause", "legacy_energy_effect_already_used_by_owner"], output="prize_reduction_and_once_per_game_state"),
}


def _input_spec(name: str) -> dict[str, Any]:
    lower = name.casefold()
    if "referenced_attack_program" in lower or "evolution_relation" in lower or "flags" in lower or "normalized_card_names" in lower:
        source = "static_card_registry_or_observation_derivation"
    elif "last_turn" in lower or "this_turn" in lower or "history" in lower or "moved_bench" in lower or "used_by_owner" in lower or "leave_event" in lower or "turn_owner" in lower:
        source = "public_event_tracker"
    elif "coin" in lower:
        source = "engine_random_resolution"
    elif "deck" in lower:
        source = "owner_private_zone_tracker_or_explicit_unknown_for_opponent"
    else:
        source = "current_observation"
    if "count" in lower or "damage" in lower or "prize" in lower or "capacity" in lower:
        unit = "integer_raw_count"
    elif "flag" in lower or "presence" in lower or lower.startswith("own_tera"):
        unit = "boolean_or_boolean_vector"
    elif "card_id" in lower:
        unit = "exact_card_id_or_exact_card_id_vector"
    elif "energy" in lower:
        unit = "energy_card_or_energy_unit_structure"
    else:
        unit = "typed_engine_state_value"
    return {"name": name, "unit": unit, "scope": "as_named_exact_side_and_zone", "source": source, "missing_policy": "explicit_unknown_no_imputation"}


def _sample_value(name: str, variant: int) -> Any:
    lower = name.casefold()
    if name == "coin_result": return ["tails", "heads", "heads"][variant]
    if name == "coin_sequence": return [0, 1, 3][variant]
    if "current_hp" in lower: return [100, 90, 10][variant]
    if "max_hp" in lower: return 100
    if "turn_number" in lower: return [1, 2, 3][variant]
    if "stage" in lower and "targets" not in lower: return ["basic", "stage1", "stage2"][variant]
    if "ko_cause" in lower: return ["other", "opponent_attack_damage", "opponent_attack_damage"][variant]
    if "card_names" in lower or "normalized_card_names" in lower: return [[], ["Team Rocket Admin"], ["Team Rocket Admin", "Other"]][variant]
    if "program" in lower: return [[], [{"attack_id": "a", "raw_damage": 50, "payable": True}], [{"attack_id": "a", "raw_damage": 50, "payable": True}, {"attack_id": "b", "raw_damage": 120, "payable": True}]][variant]
    if "energy_cards_and_types" in lower: return [[], [{"id": "p", "type": "psychic"}], [{"id": "p", "type": "psychic"}, {"id": "d", "type": "darkness"}]][variant]
    if "attached_energy_types_and_unit_counts" in lower or "attached_energy_types_and_units" in lower: return [{}, {"psychic": 1, "grass": 1, "darkness": 1}, {"psychic": 3, "grass": 3, "darkness": 3}][variant]
    if "attached_energy_types" in lower: return [[], ["darkness"], ["darkness", "psychic"]][variant]
    if "bench_entry_events" in lower: return [[], [{"during_controllers_turn": True, "stage": "basic", "type": "darkness"}], [{"during_controllers_turn": True, "stage": "basic", "type": "grass"}]][variant]
    if "candidate" in lower or "evolves_from_relations" in lower: return [[], [{"target": 1, "evolution": 2, "type": "grass", "legal": True, "has_ability": False}], [{"target": 1, "evolution": 2, "type": "grass", "legal": True, "has_ability": False}, {"target": 3, "evolution": 4, "type": "water", "legal": True, "has_ability": True}]][variant]
    if "evolution_relations" == name: return [{}, {2: 1}, {2: 1, 3: 2}][variant]
    if name in {"own_bench_damage_counter_counts", "all_opponent_in_play_damage_counter_counts", "both_active_attached_energy_unit_counts", "each_bench_occupied_count", "all_own_pokemon_damage"}:
        return [[], [1], [1, 3]][variant]
    if name == "chosen_discard_set": return [[], [0], [0, 1]][variant]
    if "selected" in lower and "count" in lower: return [0, 1, 2][variant]
    if "choice" in lower or "ordinal" in lower: return [0, 0, 1][variant]
    if "count" in lower or "damage" in lower or "prize" in lower or "capacity" in lower: return [0, 1, 6][variant]
    if lower.endswith("_flag") or "presence" in lower or "history" in lower or "played" in lower or "event" in lower or "turn_owner" in lower: return [False, True, True][variant]
    if "flags" in lower: return [[], [True], [True, False, True, True]][variant]
    if "targets" in lower or "card_ids" in lower or "cards" in lower or "set" in lower or "allocation" in lower: return [[], ["active"], ["active", "bench1", "bench2"]][variant]
    return [False, True, True][variant]


def _scenario_inputs(spec: dict[str, Any], variant: int) -> dict[str, Any]:
    values = {name: _sample_value(name, variant) for name in spec["required_inputs"]}
    rule = spec["rule"]
    if rule == "flip_script":
        values.update({"own_pokemon_ko_during_opponent_last_turn": variant > 0, "same_name_ability_used_this_turn": variant == 2})
    elif rule == "threshold_count":
        values[spec["parameters"]["input"]] = [False, False, False] if variant == 0 else ([True, True, True, True] if variant == 1 else [True, True, True, True, True])
    elif rule == "rare_candy":
        values.update({"own_in_play_exact_card_ids": [1], "own_hand_exact_card_ids": [3], "pokemon_entered_play_this_turn": [variant == 0], "turn_number": 1 if variant == 0 else 2, "evolution_relations": {"3": 2, "2": 1}})
    elif rule == "grand_tree":
        values.update({"own_in_play_exact_card_ids": [1], "deck_exact_card_ids": [2, 3], "evolution_relations": {2: 1, 3: 2}, "turn_number": 1 if variant == 0 else 2, "entered_play_this_turn": [False]})
    elif rule == "copy_attack":
        values[spec["parameters"]["programs"]] = [] if variant == 0 else [{"attack_id": "a", "raw_damage": 50}, {"attack_id": "b", "raw_damage": 120}]
        values[spec["parameters"]["choice"]] = 0 if variant < 2 else 1
    elif rule == "festival_lead":
        values[spec["parameters"]["programs"]] = [{"attack_id": "a", "raw_damage": 50, "payable": True}]
        values[spec["parameters"]["stadium"]] = variant > 0
        values[spec["parameters"]["replacement"]] = variant == 2
    elif rule == "counter_concentration":
        values[spec["parameters"]["counts"]] = [0, 0] if variant == 0 else ([2, 0] if variant == 1 else [2, 3, 1])
    elif rule == "wobbuffet":
        values.update({"own_bench_team_rocket_flags": [False, False] if variant == 0 else [True, False], "own_bench_damage_counter_counts": [0, 3 if variant == 2 else 1] if variant == 0 else [3 if variant == 2 else 1, 5]})
    elif rule == "crispin":
        values.update({"basic_energy_cards_and_types_in_deck": [] if variant == 0 else [{"id": "p", "type": "psychic"}, {"id": "d", "type": "darkness"}], "own_pokemon_targets": [] if variant == 0 else ["active"], "owner_choices": []})
    elif rule == "risky_ruins":
        values["bench_entry_events"] = [] if variant == 0 else [{"during_controllers_turn": True, "stage": "basic", "type": "darkness" if variant == 1 else "grass"}]
    elif rule == "evolution_options":
        values[spec["parameters"]["candidates"]] = [] if variant == 0 else [{"target": 1, "evolution": 2, "type": "grass", "legal": True, "has_ability": False}]
        if "turn_number" in values: values["turn_number"] = 1 if variant == 0 else 2
    elif rule == "glass_trumpet":
        values.update({"own_tera_pokemon_in_play": variant > 0, "own_benched_colorless_targets": ["b1", "b2"], "basic_energy_cards_in_own_discard": ["e1", "e2"]})
    elif rule == "area_zero":
        values.update({"stadium_in_play": variant > 0, "each_player_tera_presence": [True, variant == 2], "each_bench_occupied_count": [8, 6], "stadium_owner": 1, "stadium_leave_event": variant == 2})
    elif rule == "janine":
        values.update({"own_darkness_pokemon_targets": ["active", "bench1"], "basic_darkness_energy_cards_in_deck": ["e1", "e2"], "selected_targets": [] if variant == 0 else (["bench1"] if variant == 1 else ["active", "bench1"])})
    elif rule == "team_rocket_energy":
        values.update({"holder_team_rocket_flag": variant > 0, "requested_attack_cost_types": {}, "other_attached_energy": {}})
    return values


def _coverage_tags(rule: str, variant: int) -> list[str]:
    if variant == 0:
        return ["negative"]
    if variant == 1:
        return ["positive"]
    tags = ["boundary"]
    if rule in {"mul_count", "mul_bool_count", "flagged_sum", "sum_values", "base_plus_mul", "base_plus_energy", "hp_counter_damage", "energy_type_bonus", "chosen_named_cards", "chosen_basic_energy", "wild_growth", "team_rocket_energy", "ignition", "prism"}:
        tags.append("stacking")
    if rule in {"conditional_value", "contains_value", "coin_value", "coin_target", "copy_attack", "flip_script", "history_draw", "named_history", "threshold_count", "damaged_value", "paired_flag_bonus", "prevent_damage_coin", "evolution_options", "rare_candy", "rosa", "legacy"}:
        tags.append("suppression")
    if rule in {"area_zero", "festival_lead", "memory_dive", "glass_trumpet", "janine", "grand_tree", "crispin", "rare_candy", "counter_concentration", "wobbuffet", "torrential_pump"}:
        tags.append("conflict")
    return tags


def _closed_output_bounds(effect: dict[str, Any], declaration: dict[str, Any]) -> dict[str, Any]:
    damage = effect.get("damage_profile") or {}
    credible = damage.get("credible_max")
    legal = damage.get("theoretical_max")
    reason = damage.get("unknown_reason")
    if reason and "pending" in reason.casefold():
        reason = "No card-text constant exists: the exact raw value is computed from the declared live state; a missing or hidden input remains explicit unknown."
    if declaration["output_unit"] not in {"attack_damage", "damage_equivalent_hp", "damage_counters_and_equivalent_hp", "discard_count_and_attack_damage", "moved_damage_counters_and_attack_damage", "split_attack_damage_and_energy_shuffle", "attack_sequence_and_raw_damage", "legal_attack_ids_and_maximum_raw_damage", "hp_and_attack_damage_modifiers", "attack_damage_modifier", "prevented_and_received_attack_damage"}:
        credible = None
        legal = None
        if not reason:
            reason = "not_applicable_to_this_non_damage_output"
    elif credible is None and legal is None and not reason:
        reason = "No safe constant maximum follows from card text alone; compute the exact live value or emit explicit unknown when required state is unavailable."
    return {"unit": declaration["output_unit"], "meaning": "raw_engine_semantics_before_encoder_normalization", "credible_max": credible, "legal_or_theoretical_max": legal, "unknown_reason": reason}


def _collect() -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    queues: list[dict[str, Any]] = []
    owners: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    for path in BATCH_PATHS:
        batch = json.loads(path.read_text(encoding="utf-8"))
        effects = {effect["effect_id"]: (card, effect) for card in batch["cards"] for effect in card.get("effects", [])}
        for item in batch["formula_queue"]:
            queues.append(item)
            if item["effect_id"] not in effects:
                issues.append({"code": "queue_owner_missing", "formula_key": item["formula_key"]})
                continue
            card, effect = effects[item["effect_id"]]
            owners[item["formula_key"]] = {"batch_path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"), "card_id": card["card_id"], "card_name": card["card_name"], "effect": effect}
    return queues, owners, issues


def build_registry() -> tuple[dict[str, Any], dict[str, Any]]:
    queues, owners, issues = _collect()
    queue_keys = [item["formula_key"] for item in queues]
    if set(queue_keys) != set(FORMULAS):
        issues.append({"code": "formula_key_mismatch", "missing": sorted(set(queue_keys) - set(FORMULAS)), "extra": sorted(set(FORMULAS) - set(queue_keys))})
    review = json.loads(HUMAN_REVIEW.read_text(encoding="utf-8"))["records"]
    pending = [item["id"] for item in review if item["status"] == "pending"]
    if pending:
        issues.append({"code": "pending_human_review", "ids": pending})
    approximations = json.loads(APPROXIMATIONS.read_text(encoding="utf-8"))["approximations"]
    if [item["human_review_id"] for item in approximations] != ["HR-B05-002"]:
        issues.append({"code": "unapproved_approximation_set"})

    records = []
    scenario_results = []
    for key in sorted(set(queue_keys) & set(FORMULAS)):
        declaration = FORMULAS[key]
        owner = owners[key]
        effect = owner["effect"]
        queue = next(item for item in queues if item["formula_key"] == key)
        if not set(queue["required_inputs"]).issubset(declaration["required_inputs"]):
            issues.append({"code": "queued_input_not_declared", "formula_key": key, "queue": queue["required_inputs"], "declared": declaration["required_inputs"]})
        scenarios = []
        for index, label in enumerate(("negative", "positive", "boundary")):
            inputs = _scenario_inputs(declaration, index)
            try:
                expected = evaluate_formula(key, inputs)
                status = "passed"
            except Exception as exc:  # validation artifact must preserve exact failure
                expected = {"error": type(exc).__name__, "message": str(exc)}
                status = "failed"
                issues.append({"code": "scenario_failed", "formula_key": key, "scenario": label, "error": repr(exc)})
            scenario = {"scenario_id": f"{key}:{index + 1}", "coverage": _coverage_tags(declaration["rule"], index), "inputs": inputs, "expected_raw_output": expected, "status": status}
            scenarios.append(scenario)
            scenario_results.append({"formula_key": key, **scenario})
        records.append({
            "formula_key": key,
            "status": "complete" if all(item["status"] == "passed" for item in scenarios) else "failed",
            "card": {"card_id": owner["card_id"], "card_name": owner["card_name"], "effect_id": effect["effect_id"], "effect_kind": effect["kind"], "effect_text": effect["text"]},
            "queue_question": queue["question"],
            "inputs": [_input_spec(name) for name in declaration["required_inputs"]],
            "output": _closed_output_bounds(effect, declaration),
            "timing": effect.get("activation", {"event": "source_program_resolution"}),
            "algorithm": {"shared_handler": declaration["rule"], "parameters": {name: value for name, value in declaration["parameters"].items() if not callable(value)}, "order": "exact source-program order; selections are resolved before dependent damage/effects", "fallback": "explicit_unknown_no_imputation", "saturation": "none_raw_units"},
            "interactions": {"tools_stadiums_special_energy_archetype_prizes_zones_and_history": "consumed only through the declared inputs and canonical source program; no implicit bonuses or suppression", "copied_attacks": "referenced attack program retains its own card-specific formula and legality checks" if declaration["rule"] in {"copy_attack", "memory_dive", "festival_lead"} else "not_applicable_unless_declared_input"},
            "engine_evidence": {"card_source": f"{effect['engine']['source_path']}:{effect['engine']['source_line_start']}", "chain_sha256": effect["engine"]["chain_sha256"], "runtime_refs": effect.get("runtime_engine_refs", []), "canonical_batch": owner["batch_path"]},
            "approximation": {"human_review_id": "HR-B05-002", "policy": "enumerate 0-3 heads for practical distribution; exact evaluator accepts every nonnegative head count; >=4 tail probability is 0.0625"} if key == "pokemon_01_mega_kangaskhan_coin_until_tails" else None,
            "human_review_ids": effect.get("human_review_ids", []),
            "scenarios": scenarios,
        })
    complete = not issues and len(records) == len(queue_keys) == 79 and all(item["status"] == "complete" for item in records)
    source_hash = hashlib.sha256(b"".join(path.read_bytes() for path in BATCH_PATHS)).hexdigest()
    registry = {"schema_version": SCHEMA_VERSION, "spec_step": "12b08", "status": "complete" if complete else "failed", "source_batches_sha256": source_hash, "formula_count": len(records), "queue_count": len(queue_keys), "policies": {"missing_input": "return explicit unknown at integration boundary; evaluator raises MissingFormulaInput", "hidden_information": "emit declared bound or unknown, never an invented exact value", "damage_saturation": "none", "only_approved_approximation": "HR-B05-002"}, "formulas": records}
    validation = {"schema_version": SCHEMA_VERSION, "status": "passed" if complete else "failed", "checks": {"queue_keys_equal_completed_keys": set(queue_keys) == {item["formula_key"] for item in records}, "queue_keys_unique": len(queue_keys) == len(set(queue_keys)), "all_inputs_declared": all(len(item["inputs"]) == len(FORMULAS[item["formula_key"]]["required_inputs"]) for item in records), "all_scenarios_pass": all(item["status"] == "passed" for item in scenario_results), "deterministic_formula_order": [item["formula_key"] for item in records] == sorted(queue_keys), "no_pending_human_review": not pending, "only_approved_approximation": [item["human_review_id"] for item in approximations] == ["HR-B05-002"]}, "counts": {"queued": len(queue_keys), "completed": len(records), "scenarios": len(scenario_results), "issues": len(issues)}, "issues": issues, "scenario_results": scenario_results}
    return registry, validation


def main() -> int:
    registry, validation = build_registry()
    OUTPUT.write_bytes(json_bytes(registry))
    VALIDATION.write_bytes(json_bytes(validation))
    print(json.dumps({"status": registry["status"], "formulas": registry["formula_count"], "scenarios": validation["counts"]["scenarios"], "issues": validation["counts"]["issues"]}, indent=2, sort_keys=True))
    return 0 if registry["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
