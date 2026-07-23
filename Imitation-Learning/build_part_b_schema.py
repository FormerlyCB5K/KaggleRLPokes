"""Build deterministic evidence and schema artifacts for Spec 12b04."""
from __future__ import annotations

import argparse
import copy
import json
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
WORKLIST = PART_B / "audit-worklist.json"
DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"
SCHEMA_VERSION = 1

PROGRAM_NODE_KINDS = ["sequence", "operation", "conditional", "choice", "for_each", "repeat", "reference"]
OPERATION_KINDS = [
    "deal_damage",
    "place_damage_counters",
    "remove_damage_counters",
    "knock_out",
    "apply_special_condition",
    "clear_special_conditions",
    "move_cards",
    "shuffle_cards",
    "attach_card",
    "detach_card",
    "switch_active",
    "evolve",
    "devolve",
    "modify_stat",
    "modify_damage_rule",
    "modify_action_rule",
    "modify_card_rule",
    "modify_prize_rule",
    "provide_energy",
    "copy_or_use_attack",
    "reveal_or_inspect",
    "end_turn",
    "win_game",
    "no_op",
]
EXPRESSION_KINDS = [
    "literal", "read", "count", "add", "subtract", "multiply", "divide", "minimum",
    "maximum", "compare", "and", "or", "not", "coin_flip", "random_choice",
]
OBSERVABILITY_KINDS = [
    "static", "observation_direct", "observation_derived", "public_history",
    "hidden_information", "stochastic", "engine_internal", "unavailable",
]
SCHEMA_FAMILIES = [
    "damage", "healing", "knockout", "special_condition", "zone_movement",
    "attachment", "pokemon_position", "evolution", "stat_modifier", "damage_rule",
    "action_rule", "card_rule", "prize_rule", "energy_provision", "attack_delegation",
    "information", "game_flow", "random_control", "no_non_obvious_effect",
]


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def encoder_modules():
    encoder_root = REPO_ROOT / "Ceruledge-RL"
    if str(encoder_root) not in sys.path:
        sys.path.insert(0, str(encoder_root))
    import effect_features
    import stat_bakes

    return effect_features, stat_bakes


def load_effect_rows() -> list[dict]:
    worklist = json.loads(WORKLIST.read_text(encoding="utf-8"))
    return [effect for card in worklist["cards"] for effect in card["effects"]]


def is_nonzero_tag(value: object) -> bool:
    return value not in (0, 0.0, False, None, "", [], {})


def method_role(method: str) -> str:
    """Classify fluent-engine method names structurally, without inferring semantics."""
    explicit_roles = {
        "enemySelect": "target_or_selection",
        "getCard": "control_or_delegation",
        "multiplyEffectValuePreTargetCount": "metadata_or_value",
        "noTargetEffect": "semantic_effect_candidate",
        "noTargetEffectAndWeakness": "semantic_effect_candidate",
        "noTargetResistance": "semantic_effect_candidate",
        "noTargetWeaknessOnly": "semantic_effect_candidate",
        "noTargetWeaknessResistance": "semantic_effect_candidate",
        "secondEffectStartIndex": "timing_or_continuation",
        "seeingDeck": "target_or_selection",
        "tera": "effect_starter",
    }
    if method in explicit_roles:
        return explicit_roles[method]
    if method in {
        "attack", "abilityBattleField", "abilityEvolve", "abilityPlay", "attachSkill",
        "energySkill", "playSkill", "specialEnergy", "stadiumSkill", "toolSkill",
    }:
        return "effect_starter"
    if method in {"textEn", "eVal", "separator", "priority", "setContext"}:
        return "metadata_or_value"
    if method.startswith(("target", "select", "singleSelect", "multiSelect", "maxSelect")):
        return "target_or_selection"
    if method.startswith(("condition", "exist", "can", "notMe", "notStack", "failSkip")):
        return "requirement_or_guard"
    if method.startswith(("trigger", "activateSkill", "stadiumActivate")):
        return "trigger_or_usage_rule"
    if method.startswith(("preEffect", "postEffect", "setPreEffect", "setPostEffect")):
        return "timing_or_continuation"
    if method.startswith("effect"):
        return "semantic_effect_candidate"
    if method.startswith(("cost", "trashMyTurnEnd")):
        return "cost_or_cleanup"
    if method.startswith(("as", "toActiveOnlySetup", "eachSelectedList", "addCheckList")):
        return "control_or_delegation"
    return "unclassified_engine_method"


def original_taxonomy() -> dict:
    effect_features, stat_bakes = encoder_modules()
    bake_stats: set[str] = set()
    bake_conditions: set[str] = set()
    bake_source_conditions: set[str] = set()
    bake_scopes: set[str] = set()
    for bake in stat_bakes.BAKES.values():
        for modifier in bake.get("mods", []):
            if modifier.get("stat"):
                bake_stats.add(modifier["stat"])
            if modifier.get("condition"):
                bake_conditions.add(modifier["condition"])
            if modifier.get("source_condition"):
                bake_source_conditions.add(modifier["source_condition"])
            if modifier.get("scope"):
                bake_scopes.add(modifier["scope"])
    return {
        "attack_tags": list(effect_features.ATTACK_TAG_FIELDS),
        "ability_tags": list(effect_features.ABILITY_TAG_FIELDS),
        "modifier_vector": {
            "fields": effect_features.modifier_schema(),
            "scale_variables": list(effect_features.SCALE_VARS),
            "bypass_modes": list(effect_features.BYPASS),
            "conditions": list(effect_features.CONDITIONS),
        },
        "effect_keywords": list(effect_features.EFFECT_KEYWORDS),
        "stat_bakes": {
            "stats": sorted(bake_stats),
            "conditions": sorted(bake_conditions),
            "source_conditions": sorted(bake_source_conditions),
            "scopes": sorted(bake_scopes),
        },
    }


def build_mechanic_inventory() -> dict:
    rows = load_effect_rows()
    old = original_taxonomy()
    methods: dict[str, dict] = {}
    method_effects: dict[str, list[str]] = defaultdict(list)
    method_kinds: dict[str, Counter] = defaultdict(Counter)
    token_effects: dict[str, list[str]] = defaultdict(list)
    token_kinds: dict[str, Counter] = defaultdict(Counter)
    signature_effects: dict[tuple, list[str]] = defaultdict(list)

    for row in rows:
        engine = row["engine"]
        for method in engine.get("method_calls", []):
            method_effects[method].append(row["effect_id"])
            method_kinds[method][row["kind"]] += 1
        for token in engine.get("effect_tokens", []):
            token_effects[token].append(row["effect_id"])
            token_kinds[token][row["kind"]] += 1
        signature = (
            row["kind"],
            engine.get("starter"),
            tuple(engine.get("method_calls", [])),
            tuple(engine.get("effect_tokens", [])),
        )
        signature_effects[signature].append(row["effect_id"])

    for method in sorted(method_effects):
        effects = sorted(set(method_effects[method]))
        methods[method] = {
            "role": method_role(method),
            "effect_count": len(effects),
            "counts_by_kind": dict(sorted(method_kinds[method].items())),
            "effect_ids": effects,
        }

    tokens = {
        token: {
            "effect_count": len(set(token_effects[token])),
            "counts_by_kind": dict(sorted(token_kinds[token].items())),
            "effect_ids": sorted(set(token_effects[token])),
        }
        for token in sorted(token_effects)
    }

    signatures = []
    for signature, effect_ids in sorted(signature_effects.items(), key=lambda item: item[0]):
        kind, starter, method_calls, effect_tokens = signature
        signatures.append({
            "signature_id": f"engine-signature-{len(signatures) + 1:03d}",
            "kind": kind,
            "starter": starter,
            "method_calls": list(method_calls),
            "effect_tokens": list(effect_tokens),
            "effect_count": len(effect_ids),
            "effect_ids": sorted(effect_ids),
        })

    parsed = [row for row in rows if row["generic_extraction"]["status"] == "parsed"]
    parsed_nonzero = [
        row for row in parsed
        if any(is_nonzero_tag(value) for value in (row["generic_extraction"].get("raw") or {}).values())
    ]
    parsed_text_zero = [
        row for row in parsed
        if row["text"] and not any(
            is_nonzero_tag(value)
            for value in (row["generic_extraction"].get("raw") or {}).values()
        )
    ]
    attack_usage = Counter()
    ability_usage = Counter()
    for row in parsed:
        raw = row["generic_extraction"].get("raw") or {}
        fields = old["attack_tags"] if row["kind"] == "attack" else old["ability_tags"]
        destination = attack_usage if row["kind"] == "attack" else ability_usage
        for field in fields:
            if is_nonzero_tag(raw.get(field)):
                destination[field] += 1

    role_counts = Counter(record["role"] for record in methods.values())
    unclassified = sorted(
        method for method, record in methods.items()
        if record["role"] == "unclassified_engine_method"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "audit-worklist.json",
        "summary": {
            "effect_rows": len(rows),
            "effects_by_kind": dict(sorted(Counter(row["kind"] for row in rows).items())),
            "effects_with_text": sum(bool(row["text"]) for row in rows),
            "unique_engine_methods": len(methods),
            "unique_engine_tokens": len(tokens),
            "unique_engine_signatures": len(signatures),
            "engine_method_roles": dict(sorted(role_counts.items())),
            "unclassified_engine_methods": unclassified,
        },
        "original_encoder": {
            "taxonomy": old,
            "meta_coverage": {
                "parsed_effects": len(parsed),
                "parsed_effects_with_nonzero_generic_tags": len(parsed_nonzero),
                "nonempty_parsed_effects_with_all_zero_generic_tags": len(parsed_text_zero),
                "no_general_parser": sum(
                    row["generic_extraction"]["status"] == "no_current_general_parser"
                    for row in rows
                ),
                "not_applicable": sum(
                    row["generic_extraction"]["status"] == "not_applicable"
                    for row in rows
                ),
                "current_encoder_included": sum(row["current_encoder"]["included"] for row in rows),
                "current_encoder_excluded": sum(not row["current_encoder"]["included"] for row in rows),
                "attack_tag_nonzero_counts": dict(sorted(attack_usage.items())),
                "ability_tag_nonzero_counts": dict(sorted(ability_usage.items())),
                "all_zero_effect_ids": sorted(row["effect_id"] for row in parsed_text_zero),
            },
        },
        "engine_method_inventory": methods,
        "engine_token_inventory": tokens,
        "engine_signature_inventory": signatures,
    }


def infer_schema_families(row: dict) -> list[str]:
    """Produce broad engine-backed homes for B04 review, not final semantic verdicts."""
    engine = row["engine"]
    methods = set(engine.get("method_calls", []))
    tokens = set(engine.get("effect_tokens", []))
    joined = " ".join(sorted(methods | tokens)).lower()
    families: set[str] = set()

    printed_damage = str(row.get("printed_damage") or "").strip()
    if row["kind"] == "attack" and printed_damage:
        families.add("damage")
    if any(marker in joined for marker in ("damagecounter", "attackdamage", "effectdamage")):
        families.add("damage")
    if any(marker in joined for marker in ("heal", "removedamage", "resethp")):
        families.add("healing")
    if any(marker in joined for marker in ("effectkome", " preko", " ko", "koenemy", "effectko")):
        families.add("knockout")
    if any(marker in joined for marker in (
        "poison", "burn", "sleep", "confuse", "paralyze", "specialcondition",
    )):
        families.add("special_condition")
    if any(marker in joined for marker in (
        "effectdraw", "drawuntil", "deckto", "trashtohand", "trashtodeck", "effectshuffle",
        "tohand", "totrash", "todeck", "toprize", "targettrash", "targethand", "targetdeck",
    )):
        families.add("zone_movement")
    if any(marker in joined for marker in ("attach", "energyswitch", "attachedpokemon")):
        families.add("attachment")
    if any(marker in joined for marker in (
        "effectswitch", "switchenemybench", "targetactive", "toactiveonlysetup",
    )):
        families.add("pokemon_position")
    if any(marker in joined for marker in ("evolve", "devolve")):
        families.add("evolution")
    if any(marker in joined for marker in (
        "maxhp", "retreatcostchange", "attackcostchange", "setweakness", "damagechangeactive",
        "benchcapacity",
    )):
        families.add("stat_modifier")
    if any(marker in joined for marker in (
        "nodamage", "damagechange", "weakness", "resistance", "noeffectenemyattack",
        "playerdamagechange", "takedamagechange",
    )) or any(method.startswith("noTarget") for method in methods):
        families.add("damage_rule")
    if any(marker in joined for marker in (
        "cannotattack", "cannotretreat", "cannotplay", "cannotuse", "noretreatcost",
        "failattack", "canplayfirstturn", "canevolve", "notappearthisturn",
    )):
        families.add("action_rule")
    if any(marker in joined for marker in (
        "noability", "notool", "noeffect", "triggerattachedcard", "effectedcard",
    )):
        families.add("card_rule")
    if "prize" in joined:
        families.add("prize_rule")
    if row["kind"] == "energy_effect" or any(marker in joined for marker in (
        "energycontinual", "specialenergy", "doublegrassenergy",
    )):
        families.add("energy_provision")
    if any(marker in joined for marker in (
        "canusepreevolutionattack", "asmybench", "asactiveenemy", "festivallead",
    )):
        families.add("attack_delegation")
    if any(marker in joined for marker in (
        "lookdeck", "seeingdeck", "tolooking", "reveal",
    )):
        families.add("information")
    if any(marker in joined for marker in ("turnend", "effectwin")):
        families.add("game_flow")
    if any(marker in joined for marker in ("coin", "random", "breakifcointail", "skipifcointail")):
        families.add("random_control")
    if row["kind"] == "tera":
        families.add("damage_rule")

    if not families and not row["text"] and row["kind"] == "attack":
        families.add("no_non_obvious_effect")
    return sorted(families, key=SCHEMA_FAMILIES.index)


def build_family_worklist() -> tuple[dict, list[dict]]:
    rows = load_effect_rows()
    mappings: list[dict] = []
    issues: list[dict] = []
    for row in rows:
        families = infer_schema_families(row)
        if not families:
            issues.append({
                "code": "no_schema_family_hint",
                "effect_id": row["effect_id"],
                "card_id": row["card_id"],
                "card_name": row["card_name"],
                "kind": row["kind"],
                "text": row["text"],
                "engine_method_calls": row["engine"].get("method_calls", []),
                "engine_effect_tokens": row["engine"].get("effect_tokens", []),
            })
        mappings.append({
            "effect_id": row["effect_id"],
            "card_id": row["card_id"],
            "card_name": row["card_name"],
            "kind": row["kind"],
            "candidate_families": families,
            "mapping_status": "pending_semantic_audit",
            "engine_evidence": {
                "source_path": row["engine"].get("source_path"),
                "source_line_start": row["engine"].get("source_line_start"),
                "source_line_end": row["engine"].get("source_line_end"),
                "method_calls": row["engine"].get("method_calls", []),
                "effect_tokens": row["engine"].get("effect_tokens", []),
            },
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "families": SCHEMA_FAMILIES,
        "mappings": mappings,
        "summary": {
            "effects": len(mappings),
            "mapped": sum(bool(item["candidate_families"]) for item in mappings),
            "unmapped": sum(not item["candidate_families"] for item in mappings),
            "family_effect_counts": dict(sorted(Counter(
                family for item in mappings for family in item["candidate_families"]
            ).items())),
        },
    }, issues


def build_schema_contract() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "approved_provisionally_lossless_and_efficient_required",
        "canonical_model": "ordered_compositional_effect_program",
        "compatibility_policy": "flat tags are derived outputs, never semantic authority",
        "approved_lossiness_exceptions": ["HR-B05-002"],
        "effect_program": {
            "required_fields": [
                "effect_id", "card_id", "card_class", "source_kind", "activation",
                "program", "damage_profile", "evidence", "audit",
            ],
            "activation": {
                "fields": ["event", "timing", "frequency", "source_zone", "requirements"],
                "values_are_raw": True,
            },
            "program": {
                "root": "program_node",
                "node_kinds": PROGRAM_NODE_KINDS,
                "ordered": True,
                "branching_is_explicit": True,
            },
            "operation": {
                "kinds": OPERATION_KINDS,
                "common_fields": [
                    "operation_id", "kind", "target", "value", "duration", "parameters",
                ],
            },
            "expression": {
                "kinds": EXPRESSION_KINDS,
                "common_fields": ["kind", "value", "path", "arguments", "observability"],
                "observability_kinds": OBSERVABILITY_KINDS,
            },
            "target": {
                "fields": [
                    "controller", "zone", "entity", "filters", "quantity", "chooser",
                    "ordering", "visibility",
                ],
                "compound_filters_are_explicit": True,
            },
            "duration": {
                "fields": ["start", "end", "while_condition", "stacking", "reset_event"],
            },
            "damage_profile": {
                "fields": [
                    "printed_base", "live_formula", "credible_max", "theoretical_max",
                    "expected_value", "required_inputs", "unknown_reason",
                ],
                "ordinary_zero_or_no_damage_is_explicit": True,
                "selection_policy": (
                    "live, credible, and theoretical values are peers selected by use case; "
                    "unsupported bounds are null with a reason"
                ),
            },
            "evidence": {
                "fields": [
                    "card_text", "engine_source", "engine_handler_tokens",
                    "current_encoder_comparison", "validation_refs",
                ],
            },
            "audit": {
                "fields": ["verdict", "human_review_ids", "reviewer_notes", "status"],
            },
        },
        "semantic_families": SCHEMA_FAMILIES,
        "non_goals": [
            "final tensor dimensions",
            "normalization constants",
            "model architecture",
            "runtime feature ordering",
        ],
    }


def build_approved_approximations() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "approximations": [
            {
                "human_review_id": "HR-B05-002",
                "scope": "top-meta coin-flip outcome profiles",
                "rule": "enumerate zero through three consecutive heads only",
                "omitted_tail": "four or more consecutive heads",
                "requirements": [
                    "retain the exact underlying rule or theoretical-tail label",
                    "mark omitted probability mass explicitly when cheaply calculable",
                    "never fold omitted mass into an enumerated outcome silently",
                ],
                "status": "approved",
            }
        ],
        "default_policy": "No other approximation is authorized without a new human-review decision.",
    }


def build_category_diff() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "human_review_record": "HR-B04-002",
        "status": "approved_provisionally_lossless_and_efficient_required",
        "canonical_change": {
            "from": "independent flat attack/ability tags, modifier vector, keyword bag, and stat bakes",
            "to": "one ordered effect-program AST with typed operations, expressions, targets, and durations",
            "decision_record": "HR-B04-001",
        },
        "merges_and_rehomes": {
            "damage": ["snipe", "counter_snipe", "recoil", "ability.damage", "modifier bench/self damage"],
            "action_rules": ["item_lock", "cooldown", "cubchoo", "retreat_lock"],
            "zone_movement": ["draws_cards", "ability.draw", "ability.search", "deckout", "ability.mill"],
            "attachment": ["energy_accel", "ability.energy_active", "ability.energy_bench", "discard_energy"],
            "pokemon_position": ["ability.gust", "ability.switch"],
            "damage_rules": ["immunity", "ability.immunity", "ability.barrier", "modifier bypass"],
            "control_and_expressions": [
                "conditional", "probabilistic", "revenge", "outrage", "modifier scale variables",
                "modifier conditions",
            ],
            "stat_and_rule_operations": ["stat bake stats", "stat bake scopes", "stat bake conditions"],
        },
        "deprecated_as_canonical": ["effect keyword bag", "separate attack/ability category namespaces"],
        "new_canonical_categories": {
            "program_node_kinds": PROGRAM_NODE_KINDS,
            "operation_kinds": OPERATION_KINDS,
            "expression_kinds": EXPRESSION_KINDS,
            "observability_kinds": OBSERVABILITY_KINDS,
            "semantic_families": SCHEMA_FAMILIES,
        },
        "preservation_rule": "No old capability is deleted; it is rehomed or emitted as a derived label.",
    }


def build_observation_matrix() -> dict:
    rows = [
        ("exact_card_id", "current.players[*].active|bench[*].id and visible zone cards[*].id", "observation_direct", "O(1) per entity"),
        ("hp_and_max_hp", "current.players[*].active|bench[*].hp|maxHp", "observation_direct", "O(1) per Pokemon"),
        ("attached_energy_types", "current.players[*].active|bench[*].energies", "observation_direct", "O(attached energy)"),
        ("attached_energy_card_ids", "current.players[*].active|bench[*].energyCards[*].id", "observation_direct", "O(attached cards)"),
        ("attached_tools", "current.players[*].active|bench[*].tools[*].id", "observation_direct", "O(attached tools)"),
        ("evolution_stack", "current.players[*].active|bench[*].preEvolution[*].id", "observation_direct", "O(evolution depth)"),
        ("new_in_play", "current.players[*].active|bench[*].appearThisTurn", "observation_direct", "O(1) per Pokemon"),
        ("bench_capacity_and_count", "current.players[*].benchMax and len(bench)", "observation_direct", "O(1)"),
        ("special_conditions", "current.players[*].poisoned|burned|asleep|paralyzed|confused", "observation_direct", "O(1)"),
        ("hand_size_both_players", "current.players[*].handCount", "observation_direct", "O(1)"),
        ("own_hand_identity", "current.players[yourIndex].hand[*].id", "observation_direct", "O(hand size)"),
        ("opponent_hand_identity", "current.players[opponent].hand is null", "hidden_information", "do not infer"),
        ("deck_size_both_players", "current.players[*].deckCount", "observation_direct", "O(1)"),
        ("discard_identity_and_count", "current.players[*].discard[*].id", "observation_direct", "O(discard size), cache counts if needed"),
        ("prize_count", "len(current.players[*].prize)", "observation_direct", "O(1)"),
        ("prize_identity", "prize entries are reversed/null for player observations", "hidden_information", "do not infer"),
        ("stadium", "current.stadium[*].id", "observation_direct", "O(1)"),
        ("turn_and_once_turn_flags", "current.turn|turnActionCount|supporterPlayed|stadiumPlayed|energyAttached|retreated", "observation_direct", "O(1)"),
        ("current_selection", "select.context|contextCard|effect|option|remaining values", "observation_direct", "O(selection size)"),
        ("public_prior_events", "logs plus an incremental tracker", "public_history", "O(new logs), never replay full game per observation"),
        ("future_coin_or_random_result", "not determined before resolution", "stochastic", "store distribution/formula"),
        ("derived_board_counts", "count/filter visible board and zones", "observation_derived", "single O(board or zone) pass with shared cache"),
        ("credible_maximum", "registry formula plus explicit deck/state constraints", "observation_derived", "precompile formula; O(required inputs)"),
        ("theoretical_maximum", "static registry proof or legal-state calculation", "static", "precompute and cache"),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "source_evidence": [
            "Imitation-Learning/ptcg_engine/ptcgProgram 22/ToJson.h:40",
            "Imitation-Learning/ptcg_engine/ptcgProgram 22/ToJson.h:96",
            "Imitation-Learning/ptcg_engine/ptcgProgram 22/ToJson.h:134",
            "A streamed July 12 episode player observation was checked against these paths.",
        ],
        "runtime_policy": [
            "Compile exact-card static programs once and look them up by integer card ID.",
            "Compute shared board/zone aggregates once per observation, not once per effect.",
            "Use incremental public-history trackers only for values absent from current state.",
            "Never simulate future actions merely to compute an observation feature.",
            "Never substitute hidden information with an all-zero semantic value.",
        ],
        "inputs": [
            {"input": name, "observation_path_or_rule": path, "observability": obs, "efficient_access": access}
            for name, path, obs, access in rows
        ],
    }


def example_programs() -> list[dict]:
    common_evidence = {
        "card_text": True,
        "engine_source": True,
        "engine_handler_tokens": True,
        "current_encoder_comparison": True,
        "validation_refs": [],
    }
    common_audit = {"verdict": "illustrative", "human_review_ids": [], "reviewer_notes": None, "status": "draft"}
    return [
        {
            "effect_id": "card:63:attack:1",
            "card_id": 63,
            "card_class": "pokemon",
            "source_kind": "attack",
            "activation": {"event": "attack_resolution", "timing": "immediate", "frequency": None, "source_zone": "active", "requirements": []},
            "program": {
                "kind": "sequence",
                "nodes": [
                    {"kind": "operation", "operation": {"operation_id": "discarded_energy", "kind": "detach_card", "target": "chosen_attached_basic_energy", "value": {"kind": "read", "path": "selection.count", "observability": "observation_derived"}, "duration": None, "parameters": {"destination": "discard"}}},
                    {"kind": "operation", "operation": {"operation_id": "damage", "kind": "deal_damage", "target": "opponent_active", "value": {"kind": "multiply", "arguments": [{"kind": "literal", "value": 70}, {"kind": "read", "path": "operation.discarded_energy.actual_count", "observability": "observation_derived"}]}, "duration": None, "parameters": {}}},
                ],
            },
            "damage_profile": {"printed_base": 0, "live_formula": "70 * discarded_basic_energy_count", "credible_max": None, "theoretical_max": None, "expected_value": None, "required_inputs": ["eligible_attached_basic_energy_count"], "unknown_reason": "maxima pending B08"},
            "evidence": copy.deepcopy(common_evidence),
            "audit": copy.deepcopy(common_audit),
        },
        {
            "effect_id": "card:293:ability:0",
            "card_id": 293,
            "card_class": "pokemon",
            "source_kind": "ability",
            "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn", "source_zone": "battlefield", "requirements": ["hand_count_at_least_1"]},
            "program": {"kind": "sequence", "nodes": [
                {"kind": "operation", "operation": {"operation_id": "cost", "kind": "move_cards", "target": "chosen_own_hand_card", "value": {"kind": "literal", "value": 1}, "duration": None, "parameters": {"destination": "discard", "role": "cost"}}},
                {"kind": "operation", "operation": {"operation_id": "draw", "kind": "move_cards", "target": "own_deck_top", "value": {"kind": "literal", "value": 2}, "duration": None, "parameters": {"destination": "hand", "mode": "draw"}}},
            ]},
            "damage_profile": {"printed_base": None, "live_formula": None, "credible_max": None, "theoretical_max": None, "expected_value": None, "required_inputs": [], "unknown_reason": "not a damage effect"},
            "evidence": copy.deepcopy(common_evidence),
            "audit": copy.deepcopy(common_audit),
        },
        {
            "effect_id": "card:1250:trainer_effect:0",
            "card_id": 1250,
            "card_class": "trainer",
            "source_kind": "trainer_effect",
            "activation": {"event": "continuous_stadium", "timing": "while_in_play", "frequency": "continuous", "source_zone": "stadium", "requirements": []},
            "program": {"kind": "conditional", "condition": {"kind": "compare", "arguments": [{"kind": "count", "path": "player.pokemon_in_play", "filters": {"tera": True}}, {"kind": "literal", "value": 0}], "operator": "greater_than"}, "then": {"kind": "operation", "operation": {"operation_id": "bench_capacity", "kind": "modify_stat", "target": "qualifying_player", "value": {"kind": "literal", "value": 8}, "duration": {"while_condition": "has_tera_pokemon_in_play"}, "parameters": {"stat": "bench_capacity", "mode": "set"}}}, "else": {"kind": "operation", "operation": {"operation_id": "cleanup", "kind": "move_cards", "target": "chosen_benched_pokemon_over_five", "value": {"kind": "subtract", "arguments": [{"kind": "count", "path": "player.bench"}, {"kind": "literal", "value": 5}]}, "duration": None, "parameters": {"destination": "discard", "resolution_order": "stadium_owner_first"}}}},
            "damage_profile": {"printed_base": None, "live_formula": None, "credible_max": None, "theoretical_max": None, "expected_value": None, "required_inputs": [], "unknown_reason": "not a damage effect"},
            "evidence": copy.deepcopy(common_evidence),
            "audit": copy.deepcopy(common_audit),
        },
    ]


def validate_expression(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, dict):
        return ["expression_not_object"]
    errors = []
    if value.get("kind") not in EXPRESSION_KINDS:
        errors.append("invalid_expression_kind")
    if value.get("observability") not in (None, *OBSERVABILITY_KINDS):
        errors.append("invalid_observability")
    for argument in value.get("arguments", []):
        errors.extend(validate_expression(argument))
    return errors


def validate_program_node(node: object) -> list[str]:
    if not isinstance(node, dict):
        return ["program_node_not_object"]
    kind = node.get("kind")
    if kind not in PROGRAM_NODE_KINDS:
        return ["invalid_program_node_kind"]
    errors: list[str] = []
    if kind == "sequence":
        if not node.get("nodes"):
            errors.append("empty_sequence")
        for child in node.get("nodes", []):
            errors.extend(validate_program_node(child))
    elif kind == "operation":
        operation = node.get("operation") or {}
        if operation.get("kind") not in OPERATION_KINDS:
            errors.append("invalid_operation_kind")
        errors.extend(validate_expression(operation.get("value")))
    elif kind == "conditional":
        errors.extend(validate_expression(node.get("condition")))
        errors.extend(validate_program_node(node.get("then")))
        if node.get("else") is not None:
            errors.extend(validate_program_node(node.get("else")))
    return errors


def validate_effect_program(program: dict) -> list[str]:
    required = set(build_schema_contract()["effect_program"]["required_fields"])
    errors = [f"missing:{field}" for field in sorted(required - set(program))]
    errors.extend(validate_program_node(program.get("program")))
    return errors


def build_schema_validation_report() -> dict:
    family_worklist, family_issues = build_family_worklist()
    examples = example_programs()
    positives = [{"effect_id": item["effect_id"], "errors": validate_effect_program(item)} for item in examples]
    negative_bad_node = copy.deepcopy(examples[0])
    negative_bad_node["program"]["kind"] = "parallel"
    negative_bad_operation = copy.deepcopy(examples[1])
    negative_bad_operation["program"]["nodes"][1]["operation"]["kind"] = "draw_cards"
    negatives = [
        {"case": "unknown_program_node", "errors": validate_effect_program(negative_bad_node)},
        {"case": "unknown_operation", "errors": validate_effect_program(negative_bad_operation)},
    ]

    mappings = family_worklist["mappings"]
    active_families = sorted({family for item in mappings for family in item["candidate_families"]})
    family_pairs = []
    for family in active_families:
        positive = next(item for item in mappings if family in item["candidate_families"])
        negative = next(item for item in mappings if family not in item["candidate_families"])
        family_pairs.append({
            "family": family,
            "positive_effect_id": positive["effect_id"],
            "negative_effect_id": negative["effect_id"],
            "validation": "routing_positive_and_nearby_negative_present",
        })

    roundtrip = json.loads(json.dumps(examples, ensure_ascii=False)) == examples
    observation_probe = probe_recorded_observation()
    return {
        "schema_version": SCHEMA_VERSION,
        "positive_examples": positives,
        "negative_examples": negatives,
        "family_positive_negative_pairs": family_pairs,
        "roundtrip_serialization": roundtrip,
        "family_mapping_issues": family_issues,
        "checks": {
            "positive_examples_accept": all(not item["errors"] for item in positives),
            "negative_examples_reject": all(item["errors"] for item in negatives),
            "every_active_family_has_pair": len(family_pairs) == len(active_families),
            "all_effects_have_family_home": family_worklist["summary"]["unmapped"] == 0,
            "no_final_tensor_fields": not any(
                token in json.dumps(build_schema_contract()).lower()
                for token in ("normalization_constant", "tensor_index", "feature_position")
            ),
            "roundtrip_serialization": roundtrip,
            "recorded_observation_probe": all(observation_probe["checks"].values()),
        },
        "recorded_observation_probe": observation_probe,
        "losslessness_status": (
            "schema-level checks passed; effect-level losslessness remains gated by B05-B08 audits"
        ),
    }


def probe_recorded_observation() -> dict:
    archive = sorted(DATA_ROOT.rglob("*.zip"))[0]
    with zipfile.ZipFile(archive) as bundle:
        member = sorted(name for name in bundle.namelist() if name.lower().endswith(".json"))[0]
        episode = json.loads(bundle.read(member))
    selected = None
    for step in episode["steps"]:
        for agent in step:
            current = (agent.get("observation") or {}).get("current")
            if not current:
                continue
            own = current["yourIndex"]
            opponent = 1 - own
            active = current["players"][own]["active"]
            if (
                isinstance(current["players"][own]["hand"], list)
                and current["players"][opponent]["hand"] is None
                and active and isinstance(active[0], dict)
            ):
                selected = current
                break
        if selected is not None:
            break
    if selected is None:
        raise ValueError("no suitable player observation found in deterministic probe episode")
    own = selected["yourIndex"]
    opponent = 1 - own
    player = selected["players"][own]
    foe = selected["players"][opponent]
    pokemon = player["active"][0]
    checks = {
        "own_hand_identity_visible": isinstance(player["hand"], list),
        "opponent_hand_identity_hidden": foe["hand"] is None,
        "both_hand_counts_visible": isinstance(player["handCount"], int) and isinstance(foe["handCount"], int),
        "both_deck_counts_visible": isinstance(player["deckCount"], int) and isinstance(foe["deckCount"], int),
        "board_live_fields_visible": all(
            field in pokemon
            for field in ("id", "hp", "maxHp", "appearThisTurn", "energies", "energyCards", "tools", "preEvolution")
        ),
        "turn_flags_visible": all(
            field in selected
            for field in ("turn", "turnActionCount", "supporterPlayed", "stadiumPlayed", "energyAttached", "retreated")
        ),
        "prize_identity_reversed": all(card is None for card in player["prize"] + foe["prize"]),
    }
    return {
        "archive": archive.resolve().relative_to(REPO_ROOT).as_posix(),
        "member": member,
        "checks": checks,
    }


def command_inventory() -> None:
    inventory = build_mechanic_inventory()
    write_bytes(PART_B / "mechanic-inventory.json", json_bytes(inventory))
    print(json.dumps(inventory["summary"], indent=2, sort_keys=True))


def command_draft() -> None:
    worklist, issues = build_family_worklist()
    write_bytes(PART_B / "schema-family-worklist.json", json_bytes(worklist))
    write_bytes(PART_B / "semantic-schema-draft.json", json_bytes(build_schema_contract()))
    write_bytes(PART_B / "category-diff-draft.json", json_bytes(build_category_diff()))
    write_bytes(PART_B / "schema-family-issues.json", json_bytes({
        "schema_version": SCHEMA_VERSION,
        "issues": issues,
    }))
    print(json.dumps(worklist["summary"], indent=2, sort_keys=True))
    if issues:
        raise SystemExit(2)


def command_validate() -> None:
    report = build_schema_validation_report()
    matrix = build_observation_matrix()
    write_bytes(PART_B / "schema-validation-report.json", json_bytes(report))
    write_bytes(PART_B / "engine-observation-matrix.json", json_bytes(matrix))
    write_bytes(PART_B / "semantic-program-examples.json", json_bytes({
        "schema_version": SCHEMA_VERSION,
        "examples": example_programs(),
    }))
    write_bytes(PART_B / "approved-approximations.json", json_bytes(build_approved_approximations()))
    print(json.dumps(report["checks"], indent=2, sort_keys=True))
    if not all(report["checks"].values()):
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inventory", "draft", "validate", "all"))
    args = parser.parse_args()
    if args.command in ("inventory", "all"):
        command_inventory()
    if args.command in ("draft", "all"):
        command_draft()
    if args.command in ("validate", "all"):
        command_validate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
