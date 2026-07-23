"""Build reviewed Spec-12b06 Trainer audit batches."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
WORKLIST = PART_B / "audit-worklist.json"
BATCHES = PART_B / "audit-batch-manifest.json"
HUMAN_REVIEW = PART_B / "human-review-ledger.json"
OUTPUT = PART_B / "trainer-audit"
SCHEMA_VERSION = 1


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


def semantic(
    program: dict,
    *,
    verdict: str = "override_static",
    activation: dict | None = None,
    observability: list[str] | None = None,
    change: str,
    formula_key: str | None = None,
    formula_inputs: list[str] | None = None,
    formula_question: object | None = None,
    human_review_ids: list[str] | None = None,
) -> dict:
    return {
        "verdict": verdict,
        "activation": activation or {"event": "play_from_hand"},
        "program": program,
        "observability": observability or ["observation_direct"],
        "change_from_current": change,
        "formula_key": formula_key,
        "formula_inputs": formula_inputs or [],
        "formula_question": formula_question,
        "human_review_ids": human_review_ids or [],
    }


def move(target: object, count: object, source: str, destination: str, **params) -> dict:
    return operation("move_cards", target, count, source=source, destination=destination, **params)


def search_hand(target: str, count: object = 1, **params) -> dict:
    return sequence(move(target, count, "own_deck", "own_hand", reveal=True, **params), operation("shuffle_cards", "own_deck"))


def trainer_01() -> dict[int, dict]:
    return {
        1086: semantic(
            sequence(move("chosen_basic_pokemon_cards_with_printed_hp_at_most_70", "chosen_count_0_to_min(2,open_bench_slots)", "own_deck", "own_bench"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits the up-to-two Basic, <=70 HP, open-Bench-slot, deck-to-Bench, and shuffle semantics",
            observability=["hidden_information", "observation_direct"],
        ),
        1182: semantic(
            sequence(operation("switch_active", "one_chosen_opponent_benched_pokemon", 1, side="opponent")),
            change="the current encoder omits the opponent-Bench gust selector",
        ),
        1197: semantic(
            sequence(move("opponent_chosen_hand_cards", "max(0, opponent_hand_count - 3)", "opponent_hand", "opponent_discard", chooser="opponent")),
            verdict="override_dynamic", change="the current encoder omits opponent-selected discard-until-three",
            formula_key="trainer_01_xerosic_discard_until_three", formula_inputs=["opponent_hand_count"], formula_question="max(0, opponent_hand_count - 3)",
            observability=["observation_direct", "hidden_information"],
        ),
        1152: semantic(
            search_hand("chosen_non_rule_box_pokemon_card", "chosen_count_0_to_1"),
            change="the current encoder omits the non-Rule-Box Pokémon filter, reveal, hidden-deck fail-to-find allowance, and shuffle",
            observability=["hidden_information"],
        ),
        1225: semantic(
            sequence(move("chosen_evolution_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_energy_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits the separately capped Evolution-Pokémon and Energy searches, reveal, and shared shuffle",
            observability=["hidden_information"],
        ),
        1097: semantic(
            sequence(move("one_chosen_pokemon_or_basic_energy_card", 1, "own_discard", "own_hand")),
            change="the current encoder omits the exact discard-to-hand Pokémon-or-Basic-Energy union",
        ),
        1227: semantic(
            sequence(move("all_cards_in_own_hand", None, "own_hand", "own_deck"), operation("shuffle_cards", "own_deck"), conditional(expr("compare", operator="equal", left="own_prize_count", right=6), sequence(move("own_deck_top", 8, "own_deck", "own_hand", mode="draw")), sequence(move("own_deck_top", 6, "own_deck", "own_hand", mode="draw")))),
            verdict="override_dynamic", change="the current encoder omits hand replacement and the exact-six-Prizes 8-versus-6 draw branch",
            formula_key="trainer_01_lillies_determination_draw", formula_inputs=["own_prize_count"], formula_question="8 if own_prize_count == 6 else 6",
            observability=["observation_direct", "hidden_information"],
        ),
        1079: semantic(
            sequence(operation("evolve", "one_chosen_own_basic_pokemon", "matching_stage_2_from_hand", skip_stage_1=True, prohibit_first_turn=True, prohibit_if_basic_entered_play_this_turn=True)),
            verdict="override_dynamic", change="the current encoder omits Rare Candy's exact Basic-to-matching-Stage-2 relation and both timing prohibitions",
            formula_key="trainer_01_rare_candy_eligible_evolutions", formula_inputs=["own_in_play_exact_card_ids", "own_hand_exact_card_ids", "turn_number", "pokemon_entered_play_this_turn"], formula_question="all legal Basic/Stage-2 evolution pairs",
            observability=["observation_direct", "hidden_information", "public_history"],
        ),
        1231: semantic(
            sequence(move("chosen_basic_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_stage_1_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_stage_2_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits three independent stage-filtered searches, reveal, and shuffle",
            observability=["hidden_information"],
        ),
        1184: semantic(
            sequence(move("chosen_non_rule_box_pokemon_or_basic_energy_cards", "chosen_count_0_to_3_total", "own_discard", "own_hand", combination="any")),
            change="the current encoder omits the shared up-to-three cap and exact non-Rule-Box-Pokémon/Basic-Energy discard union",
        ),
        1081: semantic(
            sequence(move("one_chosen_special_energy_attached_to_opponent_pokemon", 1, "opponent_in_play_attachment", "opponent_discard")),
            change="the current encoder omits the opponent-side attached Special Energy selector and discard",
        ),
        1129: semantic(
            sequence(move("chosen_pokemon_cards", "chosen_count_0_to_5", "own_discard", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits the up-to-five Pokémon discard-to-deck movement and shuffle",
        ),
        1159: semantic(
            sequence(operation("modify_stat", "tool_holder", 100, stat="max_hp", mode="add")),
            change="the current encoder omits Hero's Cape's +100 effective maximum HP",
            activation={"event": "tool_continuous", "duration": "while_attached"},
        ),
        1122: semantic(
            sequence(operation("inspect_cards", "own_deck_top", 7, visibility="owner_only"), move("chosen_supporter_among_inspected", "chosen_count_0_to_1", "inspected_cards", "own_hand", reveal=True), move("all_other_inspected_cards", None, "inspected_cards", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits top-seven inspection, optional Supporter selection/reveal, and rest-to-deck shuffle",
            observability=["hidden_information"],
        ),
        1266: semantic(
            sequence(operation("modify_attack_cost", "all_tera_pokemon_in_play", 1, energy_type="colorless", scope="both_players")),
            verdict="engine_baked", change="the existing stat bake exactly preserves +1 Colorless attack cost for every Tera Pokémon on both sides",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1147: semantic(
            sequence(operation("heal_damage", "own_active", 80, requirement="at_least_3_attached_energy_units")),
            change="the current encoder omits the damaged-Active and at-least-three-attached-Energy gate for healing 80",
        ),
        1264: semantic(
            sequence(operation("modify_counter_rule", "all_benched_pokemon", None, rule="prevent_damage_counter_placement", source="opponent_pokemon_attack_or_ability", attack_damage_still_applies=True, scope="both_players")),
            change="the current encoder omits the Bench-only, counter-only, opponent-Pokémon attack-or-Ability prevention boundary",
            activation={"event": "stadium_continuous", "duration": "while_in_play"}, human_review_ids=["HR-B05-001"],
        ),
        1123: semantic(
            sequence(operation("switch_active", "one_chosen_own_benched_pokemon", 1, side="own")),
            change="the current encoder omits the own Active/Bench switch selector",
        ),
        1087: semantic(
            sequence(move("opponent_chosen_hand_cards", "max(0, opponent_hand_count - 5)", "opponent_hand", "opponent_discard", chooser="opponent", resolution_order=1), move("own_chosen_hand_cards", "max(0, own_hand_count - 5)", "own_hand", "own_discard", chooser="owner", resolution_order=2)),
            verdict="override_dynamic", change="the current encoder omits both discard-until-five calculations and opponent-first resolution order",
            formula_key="trainer_01_hand_trimmer_discard_counts", formula_inputs=["opponent_hand_count", "own_hand_count"], formula_question={"opponent": "max(0, count-5)", "owner": "max(0, count-5)", "order": "opponent_then_owner"},
            observability=["observation_direct", "hidden_information"],
        ),
        1080: semantic(
            sequence(move("all_cards_in_both_hands", None, "both_hands", "respective_decks"), operation("shuffle_cards", "each_players_deck"), move("own_deck_top", 5, "own_deck", "own_hand", mode="draw"), move("opponent_deck_top", 2, "opponent_deck", "opponent_hand", mode="draw")),
            verdict="override_dynamic", change="the current encoder omits the prior-turn own-Pokémon KO gate and asymmetric 5/2 hand replacement",
            formula_key="trainer_01_unfair_stamp_activation_and_draw", formula_inputs=["own_pokemon_ko_during_opponent_last_turn"], formula_question="legal iff KO history is true; then replace hands with owner 5/opponent 2",
            observability=["public_history", "observation_direct", "hidden_information"],
            activation={"event": "play_from_hand", "requirements": ["own_pokemon_ko_during_opponent_last_turn"]},
        ),
    }


def trainer_02() -> dict[int, dict]:
    return {
        1121: semantic(
            sequence(move("two_chosen_other_hand_cards", 2, "own_hand", "own_discard", role="play_cost"), move("chosen_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits the exact two-other-card hand cost and Pokémon search/reveal/shuffle",
            observability=["hidden_information", "observation_direct"],
        ),
        1259: semantic(
            search_hand("chosen_marnies_pokemon_card", "chosen_count_0_to_1"),
            change="the current encoder omits the once-per-player-turn Stadium search for a Marnie's Pokémon",
            activation={"event": "stadium_manual_activation", "frequency": "once_per_player_turn", "controller": "turn_player"}, observability=["hidden_information", "public_history"],
        ),
        1219: semantic(
            search_hand("chosen_trainer_card", "chosen_count_0_to_1"),
            change="the current encoder omits the Trainer-card deck search, reveal, and shuffle",
            observability=["hidden_information"],
        ),
        1120: semantic(
            conditional(expr("coin_flip", probability_heads=0.5), sequence(move("one_chosen_energy_attached_to_opponent_pokemon", 1, "opponent_in_play_attachment", "opponent_discard"))),
            verdict="override_dynamic", change="the current encoder omits the fair coin and heads-only opposing attached-Energy discard",
            formula_key="trainer_02_crushing_hammer", formula_inputs=["coin_result", "opponent_attached_energy_targets"], formula_question="discard one chosen opposing attached Energy on heads, else no effect", observability=["stochastic", "observation_direct"],
        ),
        1247: semantic(
            sequence(operation("modify_damage_rule", "all_non_rule_box_pokemon", None, rule="prevent_attack_damage", attacker_filter="opponent_pokemon_ex_or_v", scope="both_players", effects_are_not_prevented=True), operation("modify_card_movement_rule", "this_card_while_in_discard", None, prohibited_destinations=["hand", "deck"])),
            change="the current encoder omits both non-Rule-Box damage prevention from opposing Pokémon ex/V and the card-level discard-to-hand/deck prohibition",
            activation={"event": "stadium_continuous", "duration": "while_in_play_for_damage_rule_and_while_in_discard_for_movement_rule"},
        ),
        1229: semantic(
            sequence(operation("heal_damage", "one_chosen_damaged_own_mega_evolution_pokemon_ex", "all", bind_actual_heal="healed_amount"), conditional(expr("compare", operator="greater_than", left="healed_amount", right=0), sequence(move("all_energy_attached_to_same_pokemon", None, "own_in_play_attachment", "own_hand")))),
            verdict="override_dynamic", change="the current encoder omits full healing of one damaged own Mega Evolution Pokémon ex and the heal-success-gated all-Energy return",
            formula_key="trainer_02_wallys_compassion", formula_inputs=["eligible_own_mega_ex_damage", "selected_target_attached_energy_cards"], formula_question="heal target to full; if any damage healed, move all its Energy to hand",
        ),
        1161: semantic(
            sequence(move("one_chosen_energy_attached_to_attacking_pokemon", 1, "opponent_attacking_pokemon_attachment", "one_chosen_opponent_benched_pokemon_attachment", chooser="tool_owner")),
            change="the current encoder omits the Active-tool-holder damaged-by-opponent-attack trigger, even-if-KO persistence, and attacker-to-opponent-Bench Energy movement",
            activation={"event": "tool_holder_damaged_by_opponent_attack_while_active", "even_if_holder_knocked_out": True}, observability=["public_history", "observation_direct"],
        ),
        1213: semantic(
            sequence(move("all_cards_in_both_hands", None, "both_hands", "respective_decks"), operation("shuffle_cards", "each_players_deck"), move("own_deck_top", 4, "own_deck", "own_hand", mode="draw"), move("opponent_deck_top", 4, "opponent_deck", "opponent_hand", mode="draw")),
            change="the current encoder omits symmetric hand replacement with four cards each",
            observability=["observation_direct", "hidden_information"],
        ),
        1257: semantic(
            sequence(move("turn_players_deck_top", 2, "turn_players_deck", "turn_players_hand", mode="draw")),
            verdict="override_dynamic", change="the current encoder omits the once-per-turn Stadium draw gated by a Team Rocket-named Supporter played from hand this turn",
            formula_key="trainer_02_team_rocket_factory_activation", formula_inputs=["supporters_played_from_hand_this_turn", "normalized_card_names"], formula_question="may draw 2 iff a Team Rocket-named Supporter was played from hand this turn",
            activation={"event": "stadium_manual_activation", "frequency": "once_per_player_turn"}, observability=["public_history"],
        ),
        1094: semantic(
            sequence(operation("inspect_cards", "own_deck_top", 7, visibility="owner_only"), move("chosen_grass_pokemon_or_basic_grass_energy_cards", "chosen_count_0_to_2_total", "inspected_cards", "own_hand", reveal=True, combination="any"), move("all_other_inspected_cards", None, "inspected_cards", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits top-seven inspection and the shared up-to-two Grass-Pokémon/Basic-Grass-Energy selection",
            observability=["hidden_information"],
        ),
        1175: semantic(
            sequence(operation("modify_damage_rule", "tool_holder_attacks", 30, rule="add_damage_to_opponent_active_before_weakness_resistance", holder_filter="non_rule_box", defender_filter="pokemon_ex")),
            verdict="engine_baked", change="the existing Tool bake exactly preserves the holder/plain and opposing-Active-ex gates with +30 damage",
            activation={"event": "tool_continuous", "duration": "while_attached"},
        ),
        1198: semantic(
            sequence(move("chosen_basic_energy_cards_of_distinct_types", "chosen_count_0_to_2", "own_deck", "selection_buffer", reveal=True, distinct_energy_types=True), conditional(expr("compare", operator="equal", left="selected_count", right=2), sequence(move("one_selected_energy", 1, "selection_buffer", "own_hand"), move("other_selected_energy", 1, "selection_buffer", "one_chosen_own_pokemon_attachment")), sequence(move("selected_energy_if_any", "selected_count", "selection_buffer", "own_hand"))), operation("shuffle_cards", "own_deck")),
            verdict="override_dynamic", change="the current encoder omits the up-to-two distinct Basic Energy types and the exact one-to-hand/other-to-Pokémon split",
            formula_key="trainer_02_crispin_energy_assignment", formula_inputs=["basic_energy_cards_and_types_in_deck", "own_pokemon_targets", "owner_choices"], formula_question="legal distinct-type selections and hand-versus-attachment assignment",
            observability=["hidden_information", "observation_direct"],
        ),
        1137: semantic(
            sequence(move("chosen_pokemon_tools_attached_to_any_pokemon", "chosen_count_0_to_2", "both_in_play_attachments", "respective_owner_discard")),
            change="the current encoder omits the shared up-to-two Tool selector across both players and owner-correct discard destinations",
        ),
        1246: semantic(
            sequence(operation("suppress_card_effects", "all_attached_pokemon_tools", None, scope="both_players", priority="stadium_suppression")),
            change="the current Stadium bake has no modifiers and therefore omits complete suppression of all attached Pokémon Tool effects",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1134: semantic(
            search_hand("chosen_team_rocket_named_supporter_card", "chosen_count_0_to_1"),
            change="the current encoder omits the combined Supporter and Team Rocket name filters, reveal, and shuffle",
            observability=["hidden_information"],
        ),
        1216: semantic(
            conditional(expr("all", values=["all_own_pokemon_in_play_are_team_rocket", "own_pokemon_in_play_count_at_least_one"]), sequence(move("own_deck_top", "max(0, 8-own_hand_count)", "own_deck", "own_hand", mode="draw_until_8")), sequence(move("own_deck_top", "max(0, 5-own_hand_count)", "own_deck", "own_hand", mode="draw_until_5"))),
            verdict="override_dynamic", change="the current encoder omits draw-until-five versus draw-until-eight based on every own Pokémon being Team Rocket's",
            formula_key="trainer_02_team_rocket_ariana_draw", formula_inputs=["own_hand_count", "all_own_in_play_exact_card_ids_or_team_rocket_flags"], formula_question="max(0, target_hand_size-current_hand), target 8 iff all own Pokémon are Team Rocket's else 5",
        ),
        1217: semantic(
            sequence(move("all_cards_in_both_hands", None, "both_hands", "respective_decks"), operation("shuffle_cards", "each_players_deck"), move("own_deck_top", 5, "own_deck", "own_hand", mode="draw"), move("opponent_deck_top", 3, "opponent_deck", "opponent_hand", mode="draw")),
            verdict="override_dynamic", change="the current encoder omits the prior-turn Team Rocket Pokémon KO gate and asymmetric 5/3 hand replacement",
            formula_key="trainer_02_team_rocket_archer_activation", formula_inputs=["team_rocket_pokemon_ko_during_opponent_last_turn"], formula_question="legal iff Team Rocket Pokémon KO history is true; then owner draws 5 and opponent 3",
            activation={"event": "play_from_hand", "requirements": ["own_team_rocket_pokemon_ko_during_opponent_last_turn"]}, observability=["public_history", "hidden_information"],
        ),
        1218: semantic(
            sequence(operation("switch_active", "one_chosen_own_benched_team_rocket_pokemon", 1, active_filter="team_rocket"), operation("switch_active", "one_chosen_opponent_benched_pokemon", 1, side="opponent", requirement="own_switch_succeeded")),
            change="the current encoder omits both Team Rocket filters, own-switch-first order, and success-gated opponent gust",
        ),
        1220: semantic(
            search_hand("chosen_basic_team_rocket_pokemon_cards", "chosen_count_0_to_3"),
            change="the current encoder omits the up-to-three Basic Team Rocket's Pokémon search and the explicit first-player first-turn permission",
            activation={"event": "play_from_hand", "special_timing": "may_be_played_during_first_turn_when_going_first"}, observability=["hidden_information"],
        ),
        1142: semantic(
            search_hand("chosen_basic_fighting_energy_or_basic_fighting_pokemon_card", "chosen_count_0_to_1"),
            change="the current encoder omits the exact Basic Fighting Energy-or-Basic Fighting Pokémon union, reveal, and shuffle",
            observability=["hidden_information"],
        ),
    }


def trainer_03() -> dict[int, dict]:
    return {
        1192: semantic(
            sequence(move("all_cards_in_own_hand", None, "own_hand", "own_discard"), move("own_deck_top", 5, "own_deck", "own_hand", mode="draw")),
            change="the current encoder omits discard-entire-hand then draw-five and the going-first first-turn permission",
            activation={"event": "play_from_hand", "special_timing": "may_be_played_during_first_turn_when_going_first"}, observability=["hidden_information"],
        ),
        1260: semantic(
            sequence(operation("place_damage_counters", "pokemon_just_benched_by_turn_player", 2, filter="basic_non_darkness_pokemon", scope="both_players")),
            verdict="override_dynamic", change="the current encoder omits the during-own-turn Bench-entry trigger, Basic/non-Darkness filters, and exact two-counter placement",
            formula_key="trainer_03_risky_ruins_trigger", formula_inputs=["bench_entry_events", "entered_pokemon_stage", "entered_pokemon_type"], formula_question="place 2 counters on each Basic non-Darkness Pokémon benched by a player during that player's turn",
            activation={"event": "pokemon_enters_bench_during_its_controllers_turn", "duration": "while_stadium_in_play"}, observability=["public_history", "observation_direct"], human_review_ids=["HR-B05-001"],
        ),
        1210: semantic(
            sequence(move("first_chosen_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), conditional(expr("read", path="first_selected_card_is_basic"), sequence(move("second_chosen_basic_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True))), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits the engine's exact branch: choose one Pokémon, then a second only when the first is Basic, yielding up to two Basic or one Evolution",
            observability=["hidden_information"],
        ),
        1167: semantic(
            sequence(operation("place_damage_counters", "attacking_pokemon", 12), move("this_tool", 1, "tool_holder_attachment", "tool_owner_discard", requirement="counters_were_placed")),
            change="the current encoder omits the Active-holder damaged-by-opponent-attack trigger, even-if-KO persistence, twelve counters on the attacker, and success-gated self-discard",
            activation={"event": "tool_holder_damaged_by_opponent_attack_while_active", "even_if_holder_knocked_out": True}, observability=["public_history"], human_review_ids=["HR-B05-001"],
        ),
        1145: semantic(
            search_hand("chosen_mega_evolution_pokemon_ex_card", "chosen_count_0_to_1"),
            change="the current encoder omits the Mega Evolution Pokémon ex search, reveal, and shuffle",
            observability=["hidden_information"],
        ),
        1173: semantic(
            sequence(operation("modify_stat", "tool_holder", 70, stat="max_hp", mode="add", holder_filter="cynthias_pokemon")),
            change="the current encoder omits the Cynthia's-Pokémon holder gate and +70 effective maximum HP",
            activation={"event": "tool_continuous", "duration": "while_attached"},
        ),
        1261: semantic(
            sequence(operation("modify_evolution_rule", "grass_pokemon_both_sides", None, rule="may_evolve_during_turn_put_into_play", evolution_target_filter="grass", first_turn_still_prohibited=True)),
            verdict="override_dynamic", change="the current encoder omits same-turn Grass-to-Grass evolution permission and retained first-turn prohibition",
            formula_key="trainer_03_forest_of_vitality_evolution_options", formula_inputs=["both_in_play_exact_card_ids", "entered_play_this_turn", "turn_number", "hands_or_deck_evolution_candidates"], formula_question="legal Grass evolution pairs after relaxing only the entered-play-this-turn restriction",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1174: semantic(
            sequence(operation("modify_stat", "tool_holder", -2, stat="retreat_cost", mode="add_floor_zero")),
            verdict="engine_baked", change="the existing Tool bake exactly preserves -2 Retreat Cost with the normal zero floor",
            activation={"event": "tool_continuous", "duration": "while_attached"},
        ),
        1262: semantic(
            sequence(operation("switch_active", "one_chosen_own_benched_water_pokemon", 1, active_filter="water")),
            change="the current encoder omits the once-per-player-turn Water-Active/Water-Bench switch",
            activation={"event": "stadium_manual_activation", "frequency": "once_per_player_turn"},
        ),
        1224: semantic(
            sequence(move("own_deck_top", 3, "own_deck", "own_hand", mode="draw")),
            change="the current encoder omits drawing three cards",
            observability=["hidden_information"],
        ),
        1236: semantic(
            sequence(move("own_deck_top", 3, "own_deck", "own_hand", mode="draw")),
            change="the current encoder omits drawing three cards",
            observability=["hidden_information"],
        ),
        1186: semantic(
            sequence(operation("reveal_cards", "opponent_hand", None, visibility="both_players"), move("owner_chosen_item_cards", "chosen_count_0_to_2", "opponent_revealed_hand", "opponent_discard"), operation("conceal_cards", "remaining_opponent_hand")),
            change="the current encoder omits full opponent-hand reveal and owner-selected up-to-two Item discard",
            observability=["hidden_information"],
        ),
        1203: semantic(
            sequence(operation("switch_active", "one_chosen_own_benched_pokemon", 1, side="own", bind_success="switched"), conditional(expr("read", path="switched"), sequence(move("own_deck_top", "max(0, 5-own_hand_count_after_play_and_switch)", "own_deck", "own_hand", mode="draw_until_5")))),
            verdict="override_dynamic", change="the current encoder omits the own switch and success-gated draw-until-five count",
            formula_key="trainer_03_surfer_draw", formula_inputs=["own_hand_count_after_play_and_switch", "own_bench_targets"], formula_question="if switch succeeds, draw max(0,5-current hand) cards",
        ),
        1242: semantic(
            sequence(operation("heal_damage", "each_own_pokemon", 10, requirement="supporter_played_from_hand_this_turn")),
            verdict="override_dynamic", change="the current encoder omits once-per-turn Supporter-history-gated healing of 10 from every own Pokémon",
            formula_key="trainer_03_community_center_healing", formula_inputs=["supporter_played_from_hand_this_turn", "all_own_pokemon_damage"], formula_question="10 healing capped by current damage for each own Pokémon when activation is legal",
            activation={"event": "stadium_manual_activation", "frequency": "once_per_player_turn"}, observability=["public_history", "observation_direct"],
        ),
        1204: semantic(
            sequence(operation("switch_active", "one_chosen_opponent_benched_basic_pokemon", 1, side="opponent", bind_success="switched"), conditional(expr("read", path="switched"), sequence(operation("apply_special_condition", "new_opponent_active", "confused")))),
            change="the current encoder omits the opponent Basic-Bench gust and Confusion on the new Active",
        ),
        1245: semantic(
            sequence(operation("remove_special_conditions", "each_pokemon_with_any_attached_energy", "all", scope="both_players"), operation("modify_condition_rule", "each_pokemon_with_any_attached_energy", None, rule="cannot_receive_special_conditions", scope="both_players")),
            change="the current encoder omits immediate recovery and continuing Special-Condition immunity for every Pokémon with attached Energy",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1146: semantic(
            sequence(move("one_chosen_basic_psychic_energy", 1, "own_discard", "one_chosen_own_benched_psychic_pokemon_attachment")),
            change="the current encoder omits the Basic Psychic discard source and Psychic Bench target filters",
        ),
        1189: semantic(
            sequence(operation("evolve", "one_chosen_own_pokemon", "chosen_no_ability_card_from_deck_that_evolves_from_target", allow_setup_or_entered_play_this_turn=True), operation("shuffle_cards", "own_deck")),
            verdict="override_dynamic", change="the current encoder omits exact evolves-from matching, no-Ability filter, deck evolution, shuffle, and same-turn/setup timing exception",
            formula_key="trainer_03_salvatore_eligible_evolutions", formula_inputs=["own_in_play_exact_card_ids", "deck_exact_card_ids", "candidate_ability_flags", "evolves_from_relations"], formula_question="all legal target/evolution pairs after bypassing the normal entered-play timing restriction",
            observability=["hidden_information", "observation_direct"],
        ),
        1194: semantic(
            sequence(move("chosen_stadium_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_energy_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits separately capped Stadium and Energy searches, reveal, and shuffle",
            observability=["hidden_information"],
        ),
        1202: semantic(
            sequence(operation("inspect_cards", "own_deck_top", 7, visibility="owner_only"), move("chosen_pokemon_among_inspected", "chosen_count_0_to_1", "inspected_cards", "own_hand", reveal=True), move("chosen_trainer_among_remaining_inspected", "chosen_count_0_to_1", "inspected_cards", "own_hand", reveal=True), move("all_other_inspected_cards", None, "inspected_cards", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits top-seven inspection, independent Pokémon and Trainer selections, reveal, and rest-to-deck shuffle",
            observability=["hidden_information"],
        ),
    }


def trainer_04() -> dict[int, dict]:
    return {
        1185: semantic(
            sequence(operation("inspect_cards", "own_deck_top", 6, visibility="owner_only"), move("two_chosen_inspected_cards", "min(2, inspected_count)", "inspected_cards", "own_hand"), move("all_other_inspected_cards", None, "inspected_cards", "own_discard")),
            change="the current encoder omits top-six inspection, exactly-two-to-hand selection when available, and discard of every remainder",
            observability=["hidden_information"],
        ),
        1244: semantic(
            sequence(operation("modify_damage_rule", "all_metal_pokemon", -30, rule="attack_damage_taken_after_weakness_resistance", attacker="opponent_pokemon", scope="both_players")),
            verdict="engine_baked", change="the existing Stadium bake exactly preserves -30 damage taken by Metal Pokémon from opposing attacks after Weakness/Resistance",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1256: semantic(
            sequence(operation("suppress_abilities", "all_colorless_pokemon_in_play", None, scope="both_players")),
            change="the current Stadium bake has no modifiers and omits complete Ability suppression for Colorless Pokémon on both sides",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1208: semantic(
            sequence(move("one_chosen_other_hand_card", 1, "own_hand", "own_discard", role="play_cost"), move("own_deck_top", "max(0, 6-own_hand_count_after_cost_and_play)", "own_deck", "own_hand", mode="draw_until_6")),
            verdict="override_dynamic", change="the current encoder omits the one-other-card discard cost and exact draw-until-six count",
            formula_key="trainer_04_iriss_fighting_spirit_draw", formula_inputs=["own_hand_count_after_play_and_cost"], formula_question="max(0, 6-current hand count)", observability=["observation_direct", "hidden_information"],
        ),
        1141: semantic(
            sequence(operation("modify_damage_rule", "attacks_used_by_own_fighting_pokemon", 30, rule="add_damage_to_opponent_active_before_weakness_resistance", duration="this_turn")),
            change="the current encoder omits the this-turn Fighting-attacker and opponent-Active gates for +30 damage",
            activation={"event": "play_from_hand", "duration": "this_turn"}, observability=["public_history"],
        ),
        1211: semantic(
            sequence(operation("modify_damage_rule", "attacks_used_by_own_pokemon", 40, rule="add_damage_to_opponent_active_before_weakness_resistance", defender_filter="pokemon_ex", duration="this_turn")),
            change="the current encoder omits the this-turn opposing-Active-Pokémon-ex gate for +40 damage",
            activation={"event": "play_from_hand", "duration": "this_turn"}, observability=["public_history"],
        ),
        1092: semantic(
            sequence(move("three_chosen_other_hand_cards", 3, "own_hand", "own_discard", role="play_cost"), move("chosen_item_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_pokemon_tool_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_supporter_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_stadium_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits the three-other-card cost and four independently capped Trainer-subtype searches",
            observability=["hidden_information", "observation_direct"],
        ),
        1191: semantic(
            {"kind": "choice", "chooser": "owner", "options": [sequence(operation("switch_active", "one_chosen_own_benched_pokemon", 1)), sequence(operation("modify_damage_rule", "attacks_used_by_own_pokemon", 30, rule="add_damage_to_opponent_active_before_weakness_resistance", defender_filter="pokemon_ex_or_v", duration="this_turn"))]},
            change="the current encoder omits the exclusive choice between an own switch and a this-turn +30 modifier against opposing Active Pokémon ex/V",
            observability=["observation_direct", "public_history"],
        ),
        1119: semantic(
            search_hand("chosen_basic_energy_card", "chosen_count_0_to_1"),
            change="the current encoder omits the Basic Energy search, reveal, and shuffle",
            observability=["hidden_information"],
        ),
        1166: semantic(
            sequence(operation("modify_stat", "both_active_pokemon", 1, stat="retreat_cost", mode="add", requirement="tool_holder_is_active")),
            verdict="engine_baked", change="the existing Tool bake exactly preserves source-Active gating and +1 Retreat Cost for both Active Pokémon",
            activation={"event": "tool_continuous", "duration": "while_attached_and_holder_active"},
        ),
        1102: semantic(
            sequence(operation("inspect_cards", "own_deck_bottom", 7, visibility="owner_only"), move("chosen_pokemon_among_inspected", "chosen_count_0_to_1", "inspected_cards", "own_hand", reveal=True), move("all_other_inspected_cards", None, "inspected_cards", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits bottom-seven inspection, optional Pokémon selection/reveal, and rest-to-deck shuffle",
            observability=["hidden_information"],
        ),
        1212: semantic(
            sequence(operation("heal_damage", "own_active", 70, requirement="target_damaged")),
            change="the current encoder omits healing 70 from the damaged own Active",
        ),
        1139: semantic(
            sequence(move("chosen_basic_energy_cards", "chosen_count_0_to_5", "own_discard", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits up-to-five Basic Energy discard-to-deck movement and shuffle",
        ),
        1095: semantic(
            sequence(operation("apply_special_condition", "opponent_active", "burned"), operation("apply_special_condition", "opponent_active", "confused")),
            change="the current encoder omits applying both Burned and Confused to the opponent's Active",
        ),
        1228: semantic(
            sequence(operation("modify_damage_rule", "one_chosen_own_pokemon", None, rule="prevent_attack_damage_and_effects", attacker_filter="opponent_pokemon_ex", duration="opponent_next_turn")),
            change="the current encoder omits the opponent-two-or-fewer-Prizes gate, any-own-Pokémon selector, ex-only attacker filter, and next-turn damage-and-effects prevention",
            activation={"event": "play_from_hand", "requirements": ["opponent_prize_count_at_most_2"]}, observability=["observation_direct", "public_history"],
        ),
        1249: semantic(
            sequence(operation("evolve", "one_chosen_own_basic_pokemon", "chosen_matching_stage_1_from_deck", prohibit_first_turn=True, prohibit_if_basic_entered_play_this_turn=True, bind_success="stage1_evolved"), conditional(expr("read", path="stage1_evolved"), sequence(operation("evolve", "same_pokemon", "chosen_matching_stage_2_from_deck", optional=True))), operation("shuffle_cards", "own_deck")),
            verdict="override_dynamic", change="the current encoder omits once-per-turn deck evolution through matching Stage 1 then optional matching Stage 2, plus normal Basic timing restrictions",
            formula_key="trainer_04_grand_tree_evolution_chain", formula_inputs=["own_in_play_exact_card_ids", "deck_exact_card_ids", "evolution_relations", "turn_number", "entered_play_this_turn"], formula_question="all legal Basic→Stage1→optional Stage2 chains from deck",
            activation={"event": "stadium_manual_activation", "frequency": "once_per_player_turn"}, observability=["hidden_information", "observation_direct", "public_history"],
        ),
        1240: semantic(
            sequence(move("chosen_basic_energy_cards", "chosen_count_0_to_2", "own_discard", "one_chosen_own_stage_2_pokemon_attachment", all_to_same_target=True)),
            verdict="override_dynamic", change="the current encoder omits the more-Prizes-remaining gate and up-to-two Basic Energy discard attachment to one own Stage 2",
            formula_key="trainer_04_rosas_encouragement", formula_inputs=["own_prize_count", "opponent_prize_count", "own_stage_2_targets", "basic_energy_in_own_discard"], formula_question="legal iff own prizes > opponent prizes; attach 0–2 eligible cards to one Stage 2",
        ),
        1223: semantic(
            sequence(move("all_cards_in_both_hands", None, "both_hands", "respective_decks"), operation("shuffle_cards", "each_players_deck"), conditional(expr("coin_flip", probability_heads=0.5), sequence(move("own_deck_top", 5, "own_deck", "own_hand", mode="draw"), move("opponent_deck_top", 3, "opponent_deck", "opponent_hand", mode="draw")), sequence(move("own_deck_top", 3, "own_deck", "own_hand", mode="draw"), move("opponent_deck_top", 5, "opponent_deck", "opponent_hand", mode="draw")))),
            verdict="override_dynamic", change="the current encoder omits both-hand replacement and the exact fair-coin 5/3 versus 3/5 distribution",
            formula_key="trainer_04_harlequin_draw_distribution", formula_inputs=["coin_result"], formula_question={"heads": {"owner": 5, "opponent": 3}, "tails": {"owner": 3, "opponent": 5}, "probability_each": 0.5}, observability=["stochastic", "hidden_information"],
        ),
        1206: semantic(
            sequence(move("all_cards_in_own_hand", None, "own_hand", "own_discard"), move("chosen_pokemon_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_supporter_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), move("chosen_basic_energy_card", "chosen_count_0_to_1", "own_deck", "own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits discarding the entire hand and three independently capped Pokémon/Supporter/Basic-Energy searches",
            observability=["hidden_information"],
        ),
        1187: semantic(
            sequence(move("one_chosen_other_hand_card", 1, "own_hand", "own_discard", role="play_cost"), move("own_deck_top", "opponent_bench_count", "own_deck", "own_hand", mode="draw")),
            verdict="override_dynamic", change="the current encoder omits the one-other-card cost and draw count equal to occupied opponent Bench slots",
            formula_key="trainer_04_mortys_conviction_draw", formula_inputs=["opponent_bench_occupied_count"], formula_question="draw opponent_bench_occupied_count cards after paying cost",
        ),
    }


def trainer_05() -> dict[int, dict]:
    return {
        1205: semantic(
            search_hand("chosen_pokemon_ex_cards", "chosen_count_0_to_3"),
            change="the current encoder omits the up-to-three Pokémon ex search, reveal, and shuffle",
            observability=["hidden_information"],
        ),
        1252: semantic(
            sequence(operation("modify_stat", "all_stage_2_pokemon_in_play", -30, stat="max_hp", mode="add", scope="both_players")),
            verdict="engine_baked", change="the existing Stadium bake exactly preserves -30 effective maximum HP for every Stage 2 Pokémon on both sides",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1238: semantic(
            sequence(move("chosen_fighting_pokemon_or_basic_fighting_energy_cards", "chosen_count_0_to_4_total", "own_discard", "own_hand", combination="any")),
            change="the current encoder omits the shared up-to-four cap and exact Fighting-Pokémon/Basic-Fighting-Energy discard union",
        ),
        1118: semantic(
            sequence(move("chosen_basic_energy_cards", "chosen_count_0_to_2", "own_discard", "own_hand")),
            change="the current encoder omits moving up to two Basic Energy cards from discard to hand",
        ),
        1077: semantic(
            sequence(operation("inspect_cards", "own_deck_top", 4, visibility="owner_only"), move("any_number_of_supporters_among_inspected", "chosen_count_0_to_all_eligible", "inspected_cards", "own_hand", reveal=True), move("all_other_inspected_cards", None, "inspected_cards", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits top-four inspection, any-number Supporter selection/reveal, and rest-to-deck shuffle",
            observability=["hidden_information"],
        ),
        1109: semantic(
            sequence(move("chosen_supporter_cards", "chosen_count_0_to_2", "own_discard", "own_hand")),
            change="the current encoder omits moving up to two Supporters from discard to hand",
        ),
        1113: semantic(
            sequence(move("one_chosen_basic_energy_card", 1, "own_discard", "one_chosen_own_benched_ns_pokemon_attachment")),
            change="the current encoder omits the Basic Energy discard source and Benched N's Pokémon target filters",
        ),
        1253: semantic(
            sequence(operation("modify_stat", "all_ns_pokemon_in_play", 0, stat="retreat_cost", mode="set", scope="both_players")),
            verdict="engine_baked", change="the existing Stadium bake exactly sets Retreat Cost to zero for every N's Pokémon on both sides",
            activation={"event": "stadium_continuous", "duration": "while_in_play"},
        ),
        1116: semantic(
            sequence(operation("move_attachment", "one_chosen_basic_energy_attached_to_own_pokemon", 1, destination="different_own_pokemon")),
            change="the current encoder omits Basic-Energy-only movement between two distinct own Pokémon",
        ),
        1088: semantic(
            sequence(operation("switch_active", "one_chosen_opponent_benched_pokemon", 1, side="opponent", bind_success="opponent_switched"), conditional(expr("read", path="opponent_switched"), sequence(operation("switch_active", "one_chosen_own_benched_pokemon", 1, side="own")))),
            change="the current encoder omits opponent gust first, then success-gated own switch",
        ),
        1098: semantic(
            sequence(operation("select_targets", "chosen_own_benched_colorless_pokemon", "chosen_count_0_to_2"), move("one_chosen_basic_energy_per_selected_target", "one_per_target", "own_discard", "selected_target_attachments", distinct_cards=True)),
            verdict="override_dynamic", change="the current encoder omits the own-Tera-in-play gate, up-to-two Colorless Bench targets, and one distinct Basic Energy discard attachment per target",
            formula_key="trainer_05_glass_trumpet_assignments", formula_inputs=["own_tera_pokemon_in_play", "own_benched_colorless_targets", "basic_energy_cards_in_own_discard"], formula_question="all legal 0–2 target/energy one-to-one assignments",
        ),
        1158: semantic(
            sequence(operation("modify_damage_rule", "tool_holder_attacks", 50, rule="add_damage_to_opponent_active_before_weakness_resistance", defender_filter="pokemon_ex")),
            verdict="engine_baked", change="the existing Tool bake exactly preserves +50 damage against opposing Active Pokémon ex",
            activation={"event": "tool_continuous", "duration": "while_attached"},
        ),
        1250: semantic(
            sequence(operation("modify_bench_capacity", "each_player_with_tera_pokemon_in_play", 8, default_capacity=5), operation("enforce_bench_capacity", "player_losing_last_tera_pokemon", 5, chooser="that_player"), operation("enforce_bench_capacity", "both_players_when_stadium_leaves_play", 5, resolution_order="stadium_owner_then_opponent", chooser="respective_player")),
            verdict="override_dynamic", change="the current encoder omits Tera-gated Bench capacity 8 and both forced discard-to-five transitions with exact stadium-owner-first departure order",
            formula_key="trainer_05_area_zero_bench_capacity", formula_inputs=["stadium_in_play", "each_player_tera_presence", "each_bench_occupied_count", "stadium_owner", "stadium_leave_event"], formula_question="capacity 8 iff Tera present; otherwise enforce 5, with stadium owner resolving first on leave",
            activation={"event": "stadium_continuous_and_leave_play", "duration": "while_in_play_plus_leave_resolution"}, observability=["observation_direct", "public_history"],
        ),
        1156: semantic(
            sequence(move("tool_owners_deck_top", 2, "tool_owners_deck", "tool_owners_hand", mode="draw")),
            change="the current encoder omits the Active-holder damaged-by-opponent-attack trigger, even-if-KO persistence, and draw two",
            activation={"event": "tool_holder_damaged_by_opponent_attack_while_active", "even_if_holder_knocked_out": True}, observability=["public_history", "hidden_information"],
        ),
        1176: semantic(
            sequence(operation("place_damage_counters", "attacking_pokemon", 4)),
            change="the current encoder omits the Darkness-holder/Active/damaged-by-opponent-attack trigger, even-if-KO persistence, and exact four counters on the attacker",
            activation={"event": "tool_holder_damaged_by_opponent_attack_while_active", "holder_filter": "darkness", "even_if_holder_knocked_out": True}, observability=["public_history"], human_review_ids=["HR-B05-001"],
        ),
        1188: semantic(
            sequence(move("two_chosen_cards", 2, "own_deck", "selection_buffer", visibility="owner_only"), operation("shuffle_cards", "own_deck"), move("selected_cards_in_owner_chosen_order", 2, "selection_buffer", "own_deck_top", ordering="owner_chosen")),
            change="the current encoder omits arbitrary two-card deck search, intervening shuffle, and owner-chosen top-deck order",
            observability=["hidden_information"],
        ),
        1195: semantic(
            sequence(operation("select_targets", "chosen_own_darkness_pokemon", "chosen_count_0_to_2"), move("one_basic_darkness_energy_per_selected_target", "one_per_target", "own_deck", "selected_target_attachments", distinct_cards=True, bind_active_attached="active_received_energy"), operation("shuffle_cards", "own_deck"), conditional(expr("read", path="active_received_energy"), sequence(operation("apply_special_condition", "own_active", "poisoned")))),
            verdict="override_dynamic", change="the current encoder omits up-to-two Darkness targets, per-target Basic Darkness deck attachment, shuffle, and Poison only when the Active actually receives Energy",
            formula_key="trainer_05_janines_secret_art_assignments", formula_inputs=["own_darkness_pokemon_targets", "basic_darkness_energy_cards_in_deck", "selected_targets"], formula_question="one distinct Basic Darkness Energy per selected target; poison own Active iff it received one",
            observability=["hidden_information", "observation_direct"],
        ),
        1155: semantic(
            sequence(operation("replace_knock_out", "tool_holder", None, requirement="full_hp_before_opponent_attack_damage_and_would_be_ko", remaining_hp=10), move("this_tool", 1, "tool_holder_attachment", "tool_owner_discard")),
            change="the current encoder omits the full-HP precondition, opponent-attack-damage KO replacement to 10 HP, and mandatory Tool discard",
            activation={"event": "before_tool_holder_ko_from_opponent_attack_damage"}, observability=["public_history", "observation_direct"],
        ),
        1235: semantic(
            sequence(operation("inspect_cards", "own_deck_top", 6, visibility="owner_only"), move("chosen_basic_energy_among_inspected", "chosen_count_0_to_1", "inspected_cards", "one_chosen_own_pokemon_attachment"), move("all_other_inspected_cards", None, "inspected_cards", "own_deck"), operation("shuffle_cards", "own_deck")),
            change="the current encoder omits top-six inspection, optional Basic Energy attachment to any own Pokémon, and rest-to-deck shuffle",
            observability=["hidden_information", "observation_direct"],
        ),
    }


def semantic_entries(batch_id: str) -> dict[int, dict]:
    builders = {"trainer-01": trainer_01, "trainer-02": trainer_02, "trainer-03": trainer_03, "trainer-04": trainer_04, "trainer-05": trainer_05}
    try:
        return builders[batch_id]()
    except KeyError as exc:
        raise ValueError(f"No Trainer semantic builder exists for {batch_id}") from exc


def build_batch(batch_id: str) -> tuple[dict, list[dict]]:
    worklist = json.loads(WORKLIST.read_text(encoding="utf-8"))
    manifest = json.loads(BATCHES.read_text(encoding="utf-8"))
    batch = next(item for item in manifest["batches"] if item["batch_id"] == batch_id)
    cards = {card["card_id"]: card for card in worklist["cards"]}
    semantics = semantic_entries(batch_id)
    review = {item["id"]: item for item in json.loads(HUMAN_REVIEW.read_text(encoding="utf-8"))["records"]}
    evidence_path = OUTPUT / f"{batch_id}-recorded-engine-evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else None
    issues: list[dict] = []
    if set(semantics) != set(batch["card_ids"]):
        issues.append({"code": "semantic_card_key_mismatch", "missing": sorted(set(batch["card_ids"]) - set(semantics)), "extra": sorted(set(semantics) - set(batch["card_ids"]))})
    audited_cards = []
    formula_queue = []
    for card_id in batch["card_ids"]:
        source = cards[card_id]
        effect = source["effects"][0]
        sem = semantics.get(card_id)
        if sem is None:
            continue
        methods = effect["engine"].get("method_calls", [])
        checks = {
            "exact_source_chain_present": len(effect["engine"].get("chain_sha256", "")) == 64,
            "exact_text_and_handler_present": bool(effect["text"] and effect["engine"].get("source_path")),
            "trainer_handler_shape": bool(methods and methods[0] in {"playSkill", "toolSkill", "stadiumSkill", "stadiumActivateSkillOnceTurn"} and "textEn" in methods),
            "program_present": bool(sem["program"]),
            "human_reviews_resolved": all(review[item]["status"] == "resolved" for item in sem["human_review_ids"]),
        }
        refs = [f"{effect['engine']['source_path']}:{effect['engine']['source_line_start']}"]
        effect_id = effect["effect_id"]
        if evidence and effect_id in evidence["samples"]:
            count = len(evidence["samples"][effect_id])
            checks["recorded_engine_coverage_accounted"] = count == evidence["coverage"]["sample_counts"][effect_id] and evidence["checks"]["full_dataset_scan_complete"]
            if count >= 3:
                checks["recorded_engine_samples"] = True
            elif count:
                checks["sparse_recorded_sample_with_exact_source_fallback"] = True
            else:
                checks["no_recorded_execution_with_exact_source_fallback"] = True
            refs.append(f"{evidence_path.name}#samples/{effect_id} ({count} distinct recorded executions)")
        passed = all(checks.values())
        if not passed:
            issues.append({"code": "effect_validation_failed", "effect_id": effect_id, "checks": checks})
        record = {
            "effect_id": effect_id,
            "kind": effect["kind"],
            "text": effect["text"],
            "engine": effect["engine"],
            "current_encoder": effect["current_encoder"],
            **sem,
            "validation": {"status": "passed" if passed else "failed", "checks": checks, "refs": refs},
            "audit_status": "complete" if passed else "draft",
        }
        if sem["formula_key"]:
            formula_queue.append({"formula_key": sem["formula_key"], "effect_id": effect_id, "owner": "B08", "required_inputs": sem["formula_inputs"], "question": sem["formula_question"], "status": "queued"})
        audited_cards.append({
            "card_id": card_id,
            "card_name": source["card_name"],
            "subtype": source["subtype"],
            "frequency": source["frequency"],
            "engine_card_source": source["engine_card_source"],
            "effects": [record],
            "audit_status": "complete" if passed else "draft",
        })
    complete = not issues and len(audited_cards) == len(batch["card_ids"]) and all(card["audit_status"] == "complete" for card in audited_cards)
    verdicts = Counter(card["effects"][0]["verdict"] for card in audited_cards)
    result = {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "status": "complete" if complete else "draft_pending_validation",
        "card_ids": batch["card_ids"],
        "cards": audited_cards,
        "formula_queue": formula_queue,
        "summary": {"cards": len(audited_cards), "effects": len(audited_cards), "verdicts": dict(sorted(verdicts.items())), "formula_queue": len(formula_queue), "issues": len(issues)},
    }
    return result, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_id")
    args = parser.parse_args()
    batch, issues = build_batch(args.batch_id)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{args.batch_id}-draft.json").write_bytes(json_bytes(batch))
    if batch["status"] == "complete":
        (OUTPUT / f"{args.batch_id}.json").write_bytes(json_bytes(batch))
    (OUTPUT / f"{args.batch_id}-issues.json").write_bytes(json_bytes({"schema_version": SCHEMA_VERSION, "issues": issues}))
    print(json.dumps(batch["summary"], indent=2, sort_keys=True))
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
