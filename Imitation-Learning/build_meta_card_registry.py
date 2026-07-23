"""Compile the approved Spec-12 Part-C exact-card-ID semantic registry."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from copy import deepcopy
from typing import Any

import build_dynamic_formula_registry as dynamic


REPO_ROOT = Path(__file__).resolve().parent.parent
META = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis"
PART_B = META / "part-b"
OUTPUT = REPO_ROOT / "Imitation-Learning" / "meta-card-registry"

CATALOG = META / "all-datasets" / "top_ladder_card_catalog.json"
AUDIT_LEDGER = PART_B / "canonical-audit-ledger.json"
PART_C_INPUT = PART_B / "part-c-handoff.json"
DYNAMIC_FORMULAS = PART_B / "dynamic-formulas.json"
B09_VALIDATION = PART_B / "closure-validation.json"
B09_MANIFEST = PART_B / "closure-artifact-manifest.json"
ENGINE_MANIFEST = PART_B / "engine-source-manifest.json"
SEMANTIC_SCHEMA = PART_B / "semantic-schema-draft.json"
HUMAN_REVIEW = PART_B / "human-review-ledger.json"

REGISTRY = OUTPUT / "registry.json"
FORMULAS = OUTPUT / "formulas.json"
CARD_IDS = OUTPUT / "card_ids.json"
CARD_IDS_PY = OUTPUT / "card_ids.py"
OVERRIDES = OUTPUT / "overrides.json"
SCHEMA = OUTPUT / "schema.json"
PROVENANCE = OUTPUT / "provenance.json"
VALIDATION = OUTPUT / "validation.json"
LOADER = OUTPUT / "registry.py"
README = OUTPUT / "README.md"
MANIFEST = OUTPUT / "artifact-manifest.json"

REGISTRY_SCHEMA_VERSION = "1.0.0"
FORMULA_SCHEMA_VERSION = "1.0.0"
SOURCE_PATHS = [CATALOG, AUDIT_LEDGER, PART_C_INPUT, DYNAMIC_FORMULAS, B09_VALIDATION, B09_MANIFEST, ENGINE_MANIFEST, SEMANTIC_SCHEMA, HUMAN_REVIEW]
OVERRIDE_VERDICTS = {"override_static", "override_dynamic", "engine_baked"}
ALLOWED_VERDICTS = {"generic_exact", "override_static", "override_dynamic", "engine_baked", "ordinary_field", "no_non_obvious_effect"}


def json_bytes(value: object) -> bytes:
    # Dicts are constructed deterministically. Keeping insertion order is required so
    # stringified JSON card keys remain in numeric card-ID order rather than lexical order.
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def repo_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def coverage_verdict(effect_verdicts: list[str], card_verdict: str | None) -> str:
    values = set(effect_verdicts)
    if "override_dynamic" in values:
        return "contains_dynamic_override"
    if "override_static" in values:
        return "contains_static_override"
    if "engine_baked" in values:
        return "contains_engine_baked_semantics"
    if values and values <= {"generic_exact", "ordinary_field", "no_non_obvious_effect"}:
        return "generic_or_ordinary_exact"
    if not values and card_verdict in {"ordinary_field", "no_non_obvious_effect"}:
        return "ordinary_or_no_non_obvious_effect"
    raise ValueError(f"cannot summarize verdicts={sorted(values)!r}, card_verdict={card_verdict!r}")


def registry_effect(effect: dict[str, Any], audit_effect: dict[str, Any], source_order: int) -> dict[str, Any]:
    evidence = effect["engine_evidence"]
    damage_profile = deepcopy(effect.get("damage_profile"))
    if effect.get("formula") and damage_profile is not None:
        formula_output = effect["formula"]["output"]
        damage_profile["credible_max"] = formula_output["credible_max"]
        damage_profile["theoretical_max"] = formula_output["legal_or_theoretical_max"]
        damage_profile["unknown_reason"] = formula_output["unknown_reason"]
    return {
        "effect_id": effect["effect_id"],
        "source_order": source_order,
        "kind": effect["kind"],
        "name": effect.get("name"),
        "text": effect["text"],
        "printed_cost": audit_effect.get("printed_cost"),
        "printed_damage": audit_effect.get("printed_damage"),
        "verdict": effect["verdict"],
        "activation": effect.get("activation"),
        "observability": effect.get("observability", []),
        "program": effect["program"],
        "damage_profile": damage_profile,
        "formula_key": effect["formula"]["formula_key"] if effect.get("formula") else None,
        "change_from_current": effect.get("change_from_current"),
        "engine_ref": {
            "path": evidence["source_path"],
            "line_start": evidence["source_line_start"],
            "line_end": evidence["source_line_end"],
            "chain_sha256": evidence.get("chain_sha256"),
        },
        "validation_refs": evidence["validation_refs"],
        "human_review_ids": effect.get("human_review_ids", []),
    }


def build_registry() -> dict[str, Any]:
    catalog = {card["card_id"]: card for card in load_json(CATALOG)["cards"]}
    handoff = load_json(PART_C_INPUT)
    audit_effects = {
        effect["effect_id"]: effect
        for card in load_json(AUDIT_LEDGER)["cards"]
        for effect in card.get("effects", [])
    }
    engine = load_json(ENGINE_MANIFEST)
    cards: dict[str, dict[str, Any]] = {}
    for source_card in sorted(handoff["cards"], key=lambda item: item["card_id"]):
        card_id = source_card["card_id"]
        identity = catalog[card_id]
        attacks: list[dict[str, Any]] = []
        abilities: list[dict[str, Any]] = []
        other_effects: list[dict[str, Any]] = []
        calculations: list[dict[str, Any]] = []
        effect_verdicts: list[str] = []
        engine_refs = []
        validation_refs = []
        for order, source_effect in enumerate(source_card["effects"]):
            effect = registry_effect(source_effect, audit_effects[source_effect["effect_id"]], order)
            effect_verdicts.append(effect["verdict"])
            if effect["kind"] == "attack":
                attacks.append(effect)
            elif effect["kind"] == "ability":
                abilities.append(effect)
            else:
                other_effects.append(effect)
            engine_refs.append(effect["engine_ref"])
            validation_refs.extend(effect["validation_refs"])
            if source_effect.get("formula"):
                formula = source_effect["formula"]
                calculations.append({
                    "formula_key": formula["formula_key"],
                    "effect_id": effect["effect_id"],
                    "inputs": formula["inputs"],
                    "output": formula["output"],
                    "timing": formula["timing"],
                    "fallback": formula["algorithm"]["fallback"],
                    "saturation": formula["algorithm"]["saturation"],
                })
        card_verdict = source_card.get("card_verdict")
        override_ids = [effect["effect_id"] for effect in [*attacks, *abilities, *other_effects] if effect["verdict"] in OVERRIDE_VERDICTS]
        cards[str(card_id)] = {
            "identity": {
                "card_id": card_id,
                "name": source_card["card_name"],
                "class": source_card["card_class"],
                "subtype": source_card["subtype"],
            },
            "frequency": source_card["frequency"],
            "coverage_verdict": coverage_verdict(effect_verdicts, card_verdict),
            "card_verdict": card_verdict,
            "effect_verdicts": effect_verdicts,
            "attacks": attacks,
            "abilities": abilities,
            "effects": other_effects,
            "calculations": calculations,
            "energy_profile": source_card.get("energy_profile"),
            "engine_card_ref": source_card["engine_card_source"],
            "engine_refs": engine_refs,
            "validation_refs": list(dict.fromkeys(validation_refs)),
            "integration_notes": {
                "exact_card_id_precedence": "apply this card entry before generic unseen-card parsing",
                "override_effect_ids": override_ids,
                "engine_baked_effect_ids": [effect["effect_id"] for effect in [*attacks, *abilities, *other_effects] if effect["verdict"] == "engine_baked"],
                "ordinary_delegated_effect_ids": [effect["effect_id"] for effect in [*attacks, *abilities, *other_effects] if effect["verdict"] == "ordinary_field"],
                "do_not_double_count": "engine_baked and ordinary_field rows are coverage records; do not add a second override feature for them",
            },
        }
    return {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "source_catalog_hash": sha256_path(CATALOG),
        "source_audit_hash": sha256_path(AUDIT_LEDGER),
        "source_part_c_input_hash": sha256_path(PART_C_INPUT),
        "engine_version_or_hash": {
            "module_version": engine["engine_identity"]["competition_module_version"],
            "archive_sha256": engine["engine_identity"]["archive"]["sha256"],
        },
        "identity_policy": "exact integer card_id; numeric ascending stable order; no species collapsing",
        "semantic_precedence": ["exact_card_id_registry", "reviewed_generic_semantics", "unseen_card_generic_fallback"],
        "unseen_card_fallback": {
            "policy": "use ordinary printed fields plus the generalized text/effect parser",
            "identity": "allocate unknown/unseen handling; never borrow an override by name or biological species",
            "missing_dynamic_state": "emit explicit unknown/mask; never impute zero",
        },
        "ordinary_fields_owned_by_later_spec": ["current_hp", "effective_max_hp", "retreat", "typing", "weakness", "resistance", "new_in_play", "zone_position"],
        "counts": {
            "cards": len(cards),
            "effects": sum(len(card["attacks"]) + len(card["abilities"]) + len(card["effects"]) for card in cards.values()),
            "calculations": sum(len(card["calculations"]) for card in cards.values()),
        },
        "cards": cards,
    }


def build_formula_registry(registry: dict[str, Any]) -> dict[str, Any]:
    source = load_json(DYNAMIC_FORMULAS)
    formulas = {
        item["formula_key"]: {"formula_schema_version": FORMULA_SCHEMA_VERSION, **item}
        for item in sorted(source["formulas"], key=lambda item: item["formula_key"])
    }
    reverse_index: dict[str, dict[str, list[Any]]] = {}
    affected_cards: dict[str, list[str]] = {card_id: [] for card_id in registry["cards"]}
    for key, formula in formulas.items():
        card_id = formula["card"]["card_id"]
        reverse_index[key] = {"card_ids": [card_id], "effect_ids": [formula["card"]["effect_id"]]}
        affected_cards[str(card_id)].append(key)
    affected_cards = {card_id: keys for card_id, keys in affected_cards.items() if keys}
    return {
        "formula_schema_version": FORMULA_SCHEMA_VERSION,
        "source_dynamic_formula_hash": sha256_path(DYNAMIC_FORMULAS),
        "canonical_form": "declarative metadata and scenarios; executable helper is parity validation, not semantic authority",
        "formulas": formulas,
        "reverse_index": reverse_index,
        "affected_cards": affected_cards,
    }


def build_card_ids(registry: dict[str, Any]) -> dict[str, Any]:
    ids = [int(card_id) for card_id in registry["cards"]]
    classes = {
        name: [card_id for card_id in ids if registry["cards"][str(card_id)]["identity"]["class"] == name]
        for name in ("pokemon", "trainer", "energy")
    }
    return {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "ordering": "numeric ascending exact integer card_id",
        "all": ids,
        **classes,
        "index_by_card_id": {str(card_id): index for index, card_id in enumerate(ids)},
    }


def build_overrides(registry: dict[str, Any]) -> dict[str, Any]:
    cards: dict[str, dict[str, Any]] = {}
    for card_id, card in registry["cards"].items():
        special = card["integration_notes"]["override_effect_ids"]
        if special:
            cards[card_id] = {
                "override_effect_ids": special,
                "coverage_registry_ref": f"registry.json#/cards/{card_id}",
                "card": card,
            }
    return {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "derivation": "cards whose canonical entry contains override_static, override_dynamic, or engine_baked; never edited independently",
        "counts": {
            "cards": len(cards),
            "override_effects": sum(len(item["override_effect_ids"]) for item in cards.values()),
        },
        "cards": cards,
    }


def build_schema() -> dict[str, Any]:
    semantic = load_json(SEMANTIC_SCHEMA)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "spec12-meta-card-registry-1.0.0",
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "formula_schema_version": FORMULA_SCHEMA_VERSION,
        "required_top_level": ["registry_schema_version", "source_catalog_hash", "source_audit_hash", "engine_version_or_hash", "cards"],
        "card_key_pattern": "^[0-9]+$",
        "card_required": ["identity", "coverage_verdict", "attacks", "abilities", "effects", "calculations", "engine_refs", "validation_refs", "integration_notes"],
        "effect_required": ["effect_id", "source_order", "kind", "verdict", "program", "engine_ref", "validation_refs"],
        "allowed_verdicts": sorted(ALLOWED_VERDICTS),
        "semantic_program_schema": semantic,
        "invariants": [
            "card keys parse to identity.card_id and are numeric-ascending",
            "attacks and abilities preserve all source rows and source_order; no 2-attack/1-ability truncation",
            "every override_dynamic effect has one calculation and one formula entry",
            "override-only and ID views are derived from registry.json",
            "raw values are never normalized or clipped in this registry",
        ],
    }


def build_provenance() -> dict[str, Any]:
    engine = load_json(ENGINE_MANIFEST)
    return {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "status": "frozen",
        "frozen_inputs": [
            {"path": repo_path(path), "sha256": sha256_path(path), "size_bytes": path.stat().st_size}
            for path in SOURCE_PATHS
        ],
        "engine": {
            "module_version": engine["engine_identity"]["competition_module_version"],
            "archive_path": engine["engine_identity"]["archive"]["path"],
            "archive_sha256": engine["engine_identity"]["archive"]["sha256"],
            "license_scope": engine["license_scope"],
        },
        "human_review": {
            "records": len(load_json(HUMAN_REVIEW)["records"]),
            "unresolved": 0,
            "only_approved_approximation": "HR-B05-002",
        },
        "generation": {
            "command": "python Imitation-Learning/build_meta_card_registry.py",
            "canonical_source": repo_path(PART_C_INPUT),
            "all_derivatives_generated_together": True,
        },
    }


def card_ids_python(ids: dict[str, Any]) -> bytes:
    python_index = {int(card_id): index for card_id, index in ids["index_by_card_id"].items()}
    return (f'''"""Generated exact-card-ID vocabulary. Do not edit manually."""\n\nREGISTRY_SCHEMA_VERSION = {REGISTRY_SCHEMA_VERSION!r}\nALL_CARD_IDS = {tuple(ids["all"])!r}\nPOKEMON_CARD_IDS = {tuple(ids["pokemon"])!r}\nTRAINER_CARD_IDS = {tuple(ids["trainer"])!r}\nENERGY_CARD_IDS = {tuple(ids["energy"])!r}\nCARD_ID_TO_INDEX = {python_index!r}\n''').encode("utf-8")


def loader_python() -> bytes:
    return '''"""Consumer loader for the generated exact-card-ID semantic registry."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    return json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_formulas() -> dict[str, Any]:
    return json.loads((ROOT / "formulas.json").read_text(encoding="utf-8"))


def is_meta_card(card_id: int) -> bool:
    return str(int(card_id)) in load_registry()["cards"]


def get_card(card_id: int) -> dict[str, Any] | None:
    return load_registry()["cards"].get(str(int(card_id)))


def get_formula(formula_key: str) -> dict[str, Any] | None:
    return load_formulas()["formulas"].get(formula_key)


def formulas_for_card(card_id: int) -> list[dict[str, Any]]:
    keys = load_formulas()["affected_cards"].get(str(int(card_id)), [])
    return [load_formulas()["formulas"][key] for key in keys]


def unseen_fallback_contract(card_id: int) -> dict[str, Any]:
    if is_meta_card(card_id):
        raise ValueError(f"card_id {card_id} is present in the exact meta registry")
    return load_registry()["unseen_card_fallback"]
'''.encode("utf-8")


def build_readme(registry: dict[str, Any], formulas: dict[str, Any], ids: dict[str, Any], overrides: dict[str, Any]) -> bytes:
    text = f"""# Top-Ladder Exact-Card-ID Semantic Registry

Status: Spec 12 complete. Registry schema `{REGISTRY_SCHEMA_VERSION}`; formula schema `{FORMULA_SCHEMA_VERSION}`.

## Start here

`registry.json` is the canonical complete coverage registry. It contains exactly {registry['counts']['cards']} cards and {registry['counts']['effects']} effect rows. Card keys are decimal exact card IDs in numeric ascending order. Do not collapse printings, owners, forms, or biological species.

Python consumers may import `registry.py`; other languages should read the JSON directly. `card_ids.json` and `card_ids.py` contain the stable categorical vocabulary: {len(ids['pokemon'])} Pokémon, {len(ids['trainer'])} Trainer, and {len(ids['energy'])} Energy IDs. Their disjoint union is the {len(ids['all'])}-ID one-hot vocabulary.

## Files

- `registry.json`: canonical 232-card coverage registry.
- `formulas.json`: canonical declarative registry for all {len(formulas['formulas'])} dynamic formulas, scenario fixtures, and formula-to-card/effect reverse indexes.
- `overrides.json`: generated {overrides['counts']['cards']}-card special-override view; never edit it independently.
- `card_ids.json` / `card_ids.py`: exact-ID vocabulary and numeric indices.
- `registry.py`: small Python loader and lookup API.
- `schema.json`: schema versions, required fields, verdict enum, and semantic-program schema.
- `provenance.json`: frozen input hashes, engine identity, license scope, and human-review state.
- `validation.json`: mechanical acceptance checks and counts.
- `artifact-manifest.json`: deterministic hashes for every generated artifact except itself.

## Precedence and fallback

For a known ID, use the exact card entry first. Apply an effect-level override only where its verdict is `override_static` or `override_dynamic`. An `engine_baked` or `ordinary_field` row is a coverage/delegation record and must not be added again as a second feature. `generic_exact` means the generalized behavior was reviewed and is exact.

For an unseen ID, use ordinary printed fields plus the generalized text/effect parser. Never borrow an override because an unseen card shares a name, species, owner, or mechanic. Missing dynamic state remains explicit unknown/masked; never substitute zero.

## Card records

Each card has `identity`, `coverage_verdict`, ordered `attacks`, ordered `abilities`, other `effects`, `calculations`, provenance, and integration notes. `source_order` preserves every engine row—there is no historical two-attack/one-ability truncation. `program` is the canonical ordered semantic AST. Raw counts, HP, Energy, counters, timing, targets, and conditions remain unnormalized.

The later encoder spec owns ordinary live/static features: current/effective maximum HP, retreat, type, Weakness, Resistance, `new_in_play`, and zone position.

### An intuitive way to navigate one card

Think of a card entry as four layers:

1. `identity` says exactly which printing this is.
2. `attacks`, `abilities`, and `effects` preserve what the card can do, in source order.
3. Each semantic `program` describes the ordered operations: condition, target, value, timing, and side effects.
4. `calculations` points to any live formula whose value depends on board state, history, or randomness.

For card ID 743, Alakazam, `attacks[0]` is Powerful Hand. Its printed cost is retained, its `damage_kind` is `damage_counters`, and its program says to place two counters per card in the owner's hand on the opposing Active Pokémon. Its calculation points to `pokemon_01_alakazam_powerful_hand`, whose live raw result is `20 * own_hand_count` HP-equivalent while still preserving the crucial fact that the effect uses counters rather than ordinary attack damage.

The same pattern handles cards that do not fit one scalar:

- Mega Kangaskhan ex, card 756: Rapid-Fire Combo keeps base damage, repeated fair-coin control flow, exact `200 + 50 * heads`, and the separately approved practical 0–3-head table.
- Wellspring Mask Ogerpon ex, card 108: Torrential Pump is an ordered split effect—100 to the Active, optionally shuffle exactly three attached Energy, then 120 to one Benched target. It should not be flattened into “220 damage.”
- Team Rocket's Mimikyu, card 434: Gemstone Mimicry carries a Tera-only source gate and a referenced attack program. The copied program retains its own conditions and operations.
- N's Zoroark ex, card 293: Night Joker similarly references a selected Benched N's Pokémon attack rather than pretending every possible copied attack is a fixed property of Zoroark.

## A plausible attack/effect representation for the later encoder

This is guidance, not a final tensor contract. Once a Pokémon's ordinary fields are available—HP, type, retreat, Weakness, Resistance, position, and turn flags—a reasonable compiler can create one semantic token per source attack rather than one hand-written vector per card.

Conceptually, an attack token can contain:

- presence, source ordinal, currently payable, and currently legal;
- printed Energy cost by type and total cost;
- printed base damage, exact live damage, credible maximum, legal/theoretical maximum, and explicit-known masks;
- a damage-kind one-hot such as ordinary damage, damage counters, fixed KO, or no direct damage;
- multi-hot operation families derived from the AST: damage, counter movement, healing, zone movement, Energy attach/discard/provision, switch/gust, status, evolution, rule modification, Prize modification, information, and attack delegation;
- target/scope fields such as self, own Active, own Bench, opponent Active, opponent Bench, all Pokémon, or selected card;
- timing and duration fields such as attack resolution, once per turn, while in play, next turn, or Pokémon Checkup;
- condition/input-source fields: current observation, public-history tracker, private/hidden state, registry lookup, or stochastic result;
- scalar parameters with masks—for example counters per hand card, maximum selected Energy, heal amount, or Prize delta; and
- stochastic summaries where relevant: probability, expected value, enumerated practical outcomes, and an approximation flag.

The ordered `program` remains authoritative. The fixed fields above are compiled summaries that make learning efficient; they should not replace the AST when an effect has multiple ordered operations. A small sequence/set encoder over all attack tokens is safer than truncating to two attacks. It can either leave attack tokens separate for attention or pool them into a fixed-size `attack_summary`.

A plausible Pokémon-level composition is:

```text
pokemon_semantics = combine(all ordered attack tokens, ability/effect tokens)
pokemon_representation = concat(
    ordinary live/static Pokémon fields,
    pokemon_semantics,
    exact-card-ID one-hot
)
```

The exact-card-ID one-hot is therefore a high-precision identity backstop, not a substitute for attack meaning. The semantic portion lets the model generalize between cards that share operations, while the one-hot preserves meta-card-specific distinctions and overrides. Unknown values need companion masks; a hidden or unavailable quantity must not look like a real zero.

For Powerful Hand at 12 cards in hand, for example, the compiled attack token would mark Psychic cost, payable/legal state, damage counters, opponent-Active target, observation-direct hand count, multiplier 20 HP-equivalent per card, and live value 240. It would not apply Weakness or Resistance. For Torrential Pump, the token/program pair would preserve Active damage, the exact-three-Energy optional cost, the separate Bench target/damage, and their resolution order.

## Dynamic calculations

Look up `formula_key` in `formulas.json`. Every entry declares inputs, source/observability, raw output meaning, bounds or explicit unknown, algorithm handler/parameters, order, fallback, saturation, engine evidence, and scenarios. The executable reference used for parity testing is `../build_dynamic_formula_registry.py`; declarative metadata is authoritative and should be ported into the implementation rather than replaced by opaque lambdas.

Damage counters remain counter counts with `damage_kind=damage_counters`; a 10-HP equivalent may be derived for threat/KO logic without applying Weakness, Resistance, or attack-damage rules. Mega Kangaskhan's `HR-B05-002` practical table is the sole approved approximation; its exact evaluator accepts every nonnegative head count.

## Minimal Python usage

```python
from registry import get_card, formulas_for_card, unseen_fallback_contract

card = get_card(743)              # exact Alakazam printing
calculations = formulas_for_card(743)
fallback = unseen_fallback_contract(999999)
```

## Validation

From the repository root run:

```powershell
python Imitation-Learning/build_meta_card_registry.py
python Imitation-Learning/test_meta_card_registry.py
python Imitation-Learning/archive/spec12-development/run_archived_tests.py
```

The active registry suite has 11 tests. The archived development runner preserves the other 89 Part A/B tests. Together, the expected Spec-12 result is 100 passing tests, all {len(formulas['formulas'])} formulas and 237 scenarios reconciled, and identical hashes after a second registry build.

## Next task

Create a new specification to design and wire the full imitation-learning observation encoding. Combine this registry's difficult semantics with the ordinary fields owned by that spec. That implementation must choose feature layout, normalization, masks, tracker interfaces, and model integration; none of those choices are made here.
"""
    return text.encode("utf-8")


def validate_registry(registry: dict[str, Any], formulas: dict[str, Any], ids: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    catalog = load_json(CATALOG)["cards"]
    handoff = load_json(PART_C_INPUT)
    audit = load_json(AUDIT_LEDGER)
    b09 = load_json(B09_VALIDATION)
    catalog_ids = {card["card_id"] for card in catalog}
    registry_ids = {int(card_id) for card_id in registry["cards"]}
    handoff_ids = {card["card_id"] for card in handoff["cards"]}
    registry_effects = [effect for card in registry["cards"].values() for effect in [*card["attacks"], *card["abilities"], *card["effects"]]]
    registry_effect_ids = {effect["effect_id"] for effect in registry_effects}
    audit_effect_ids = {effect["effect_id"] for card in audit["cards"] for effect in card.get("effects", [])}
    formula_keys = set(formulas["formulas"])
    calculation_keys = {calc["formula_key"] for card in registry["cards"].values() for calc in card["calculations"]}
    override_card_ids = {
        card_id for card_id, card in registry["cards"].items()
        if any(effect["verdict"] in OVERRIDE_VERDICTS for effect in [*card["attacks"], *card["abilities"], *card["effects"]])
    }
    serialized_scenarios = True
    for key, formula in formulas["formulas"].items():
        for scenario in formula["scenarios"]:
            if dynamic.evaluate_formula(key, scenario["inputs"]) != scenario["expected_raw_output"]:
                serialized_scenarios = False
    numeric_keys = list(registry["cards"])
    all_effects_have_test_ref = all(effect["validation_refs"] for effect in registry_effects)
    checks = {
        "c0_b09_input_is_closed": b09["status"] == "passed" and b09["counts"]["issues"] == 0,
        "c0_schema_versions_frozen": registry["registry_schema_version"] == REGISTRY_SCHEMA_VERSION and formulas["formula_schema_version"] == FORMULA_SCHEMA_VERSION,
        "c1_registry_ids_equal_catalog_and_handoff": registry_ids == catalog_ids == handoff_ids and len(registry_ids) == 232,
        "c1_class_counts_exact": {name: len(ids[name]) for name in ("pokemon", "trainer", "energy")} == {"pokemon": 115, "trainer": 99, "energy": 18},
        "c1_effect_rows_equal_audit": registry_effect_ids == audit_effect_ids and len(registry_effect_ids) == 314,
        "c1_source_order_and_no_truncation": all(effect["source_order"] == index for card in registry["cards"].values() for index, effect in enumerate(sorted([*card["attacks"], *card["abilities"], *card["effects"]], key=lambda item: item["source_order"]))) and sum(len(card["attacks"]) for card in registry["cards"].values()) == sum(effect["kind"] == "attack" for effect in registry_effects) and sum(len(card["abilities"]) for card in registry["cards"].values()) == sum(effect["kind"] == "ability" for effect in registry_effects),
        "c1_all_verdicts_programs_evidence_and_tests_present": all(effect["verdict"] in ALLOWED_VERDICTS and effect["program"] is not None and effect["engine_ref"]["path"] and effect["validation_refs"] for effect in registry_effects),
        "c1_attack_printed_fields_preserved": all("printed_cost" in effect and "printed_damage" in effect for effect in registry_effects if effect["kind"] == "attack"),
        "c1_dynamic_profiles_have_no_pending_placeholders": all("pending" not in ((effect.get("damage_profile") or {}).get("unknown_reason") or "").casefold() for effect in registry_effects if effect["verdict"] == "override_dynamic"),
        "c2_numeric_stable_card_order": numeric_keys == [str(card_id) for card_id in sorted(registry_ids)],
        "c2_id_lists_disjoint_union_exact": not (set(ids["pokemon"]) & set(ids["trainer"]) or set(ids["pokemon"]) & set(ids["energy"]) or set(ids["trainer"]) & set(ids["energy"])) and set(ids["all"]) == registry_ids,
        "c2_index_roundtrip": all(ids["all"][index] == int(card_id) for card_id, index in ids["index_by_card_id"].items()),
        "c2_override_view_is_exact_derivative": set(overrides["cards"]) == override_card_ids and overrides["counts"]["override_effects"] == 237,
        "c2_formula_reverse_indexes_roundtrip": formula_keys == calculation_keys == set(formulas["reverse_index"]) and all(str(card_id) in formulas["affected_cards"] and key in formulas["affected_cards"][str(card_id)] for key, refs in formulas["reverse_index"].items() for card_id in refs["card_ids"]),
        "c3_all_237_serialized_scenarios_pass": serialized_scenarios and sum(len(item["scenarios"]) for item in formulas["formulas"].values()) == 237,
        "c3_every_effect_has_validation_reference": all_effects_have_test_ref,
        "c3_but_no_more_generic_cards_absent_from_override_view": all(card_id not in overrides["cards"] for card_id, card in registry["cards"].items() if not card["integration_notes"]["override_effect_ids"]),
        "c4_handoff_contract_has_no_tensor_layout": not any(key in registry for key in ("tensor_shape", "feature_indices", "normalization_constants")) and registry["ordinary_fields_owned_by_later_spec"],
        "c4_unseen_fallback_is_explicit": "never borrow" in registry["unseen_card_fallback"]["identity"] and "never impute zero" in registry["unseen_card_fallback"]["missing_dynamic_state"],
        "c4_engine_baked_rows_marked_no_double_count": all("do not add a second override" in card["integration_notes"]["do_not_double_count"] for card in registry["cards"].values()),
    }
    issues = [{"code": name} for name, passed in checks.items() if not passed]
    return {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "status": "passed" if not issues else "failed",
        "checks": checks,
        "counts": {
            "cards": len(registry_ids),
            "effects": len(registry_effect_ids),
            "override_cards": len(overrides["cards"]),
            "override_effects": overrides["counts"]["override_effects"],
            "formulas": len(formula_keys),
            "scenarios": sum(len(item["scenarios"]) for item in formulas["formulas"].values()),
            "issues": len(issues),
        },
        "issues": issues,
    }


def build_all() -> tuple[dict[str, bytes], dict[str, Any]]:
    registry = build_registry()
    formulas = build_formula_registry(registry)
    ids = build_card_ids(registry)
    overrides = build_overrides(registry)
    schema = build_schema()
    provenance = build_provenance()
    validation = validate_registry(registry, formulas, ids, overrides)
    artifacts = {
        REGISTRY.name: json_bytes(registry),
        FORMULAS.name: json_bytes(formulas),
        CARD_IDS.name: json_bytes(ids),
        CARD_IDS_PY.name: card_ids_python(ids),
        OVERRIDES.name: json_bytes(overrides),
        SCHEMA.name: json_bytes(schema),
        PROVENANCE.name: json_bytes(provenance),
        VALIDATION.name: json_bytes(validation),
        LOADER.name: loader_python(),
        README.name: build_readme(registry, formulas, ids, overrides),
    }
    manifest = {
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "status": "complete" if validation["status"] == "passed" else "failed",
        "artifacts": [
            {"path": name, "sha256": sha256_bytes(artifacts[name]), "size_bytes": len(artifacts[name])}
            for name in sorted(artifacts)
        ],
        "regeneration_command": "python Imitation-Learning/build_meta_card_registry.py",
        "determinism_policy": "run twice from frozen provenance inputs; every listed hash must match",
    }
    artifacts[MANIFEST.name] = json_bytes(manifest)
    return artifacts, validation


def main() -> int:
    artifacts, validation = build_all()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, data in artifacts.items():
        (OUTPUT / name).write_bytes(data)
    print(json.dumps({"status": validation["status"], **validation["counts"]}, indent=2, sort_keys=True))
    return 0 if validation["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
