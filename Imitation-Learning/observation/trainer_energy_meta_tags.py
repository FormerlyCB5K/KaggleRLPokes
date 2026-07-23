"""Deliverable A: the 109-row meta Trainer/Energy tag table, transcribed directly from
`meta-card-registry/registry.json`'s own effect text for every `card:*:trainer_effect:*`/
`card:*:energy_effect:*` row (109 rows across 117 known card IDs -- 8 Basic Energy cards
have no effect row and need no entry here). Spec 11b's own manual assignment table
(`Ceruledge-RL/specs/11b-trainer-energy-tag-vocabulary.md`) was used as a starting map, not
the final source -- every row below was re-derived from the registry's own text, matching
how `pokemon_meta_tags.py` was built and this project's "re-derive fresh, don't trust prior
prose" convention.

**Dynamic-magnitude policy** -- identical to `pokemon_meta_tags.py`'s 6 rules, reused
verbatim since it's the same registry-grounded judgment call:

1. A registry-approved statistic exists -> use it. (No Trainer/Energy row qualifies --
   unlike Mega Kangaskhan ex on the Pokemon side, no row here needs an `expected_value`.)
2. An explicit cap ("up to N", "top N") -> the resulting concrete maximum.
3. "Base X (guaranteed) + Y if [condition]" -> the guaranteed base X, `CONDITIONAL` flagged
   separately.
4. A pure per-unit scaling formula with no base -> the at-or-above-cap sentinel.
5. An unspecified count implied singular ("search for a card") -> `1`, **generalized here**
   to a determinable *total* card count for combined-criteria searches (e.g. "a Stadium
   card and an Energy card" -> `2`, not `None` -- the total cards actually placed into
   hand is a well-defined number even when each individual criterion is a single card;
   confirmed self-consistent against `SEARCH_HAND`'s own single-criterion rows).
6. "All" / "any amount" / "any number" -> the at-or-above-cap sentinel.

**Judgment calls and edge cases found during this transcription, documented rather than
silently resolved (per this project's no-silent-loss convention):**

- **`SEARCH_HAND`'s magnitude = total cards retrieved**, not "number of criteria" -- see
  rule 5's generalization above. Verified self-consistent across all ~20 `SEARCH_HAND` rows
  in this table (single-criterion rows all get `1`; multi-criterion rows get the count of
  distinct cards named).
- **`DISCARD_OPP`/`DRAW`'s "until you have N cards" phrasing encodes the *target hand
  size*, not a card count**, per spec 11b's own flag on Xerosic's Machinations. Kept as-is
  (the target size is itself a well-defined, useful number) but the semantic difference
  from an ordinary count is real and worth remembering if this tag block is ever consumed
  downstream expecting a literal card-count meaning.
- **Asymmetric player-count effects collapse to the acting player's own value** (e.g. Team
  Rocket's Archer: "you draw 5, opponent draws 3" -> `DRAW(5)`), since the schema has one
  scalar per tag, not a per-player pair. The asymmetry itself is lost from the numeric
  encoding, same treatment as spec 11a gave Morty's Conviction-style per-player draws on
  the Pokemon side.
- **`RETREAT_COST_MOD`'s absolute-zero exception (N's Castle, `card:1253`): "have no
  Retreat Cost" sets an *absolute* new cost of 0, not a *relative delta* of 0** -- every
  other `RETREAT_COST_MOD` row in this table (Air Balloon's `-2`, Gravity Gemstone's `+1`)
  is a genuine signed delta. A literal magnitude of `0.0` here would collapse to
  indistinguishable-from-absent under the same presence+magnitude collapse this project
  used to justify dropping the separate presence bit in the first place (an invariant this
  row is a real, single exception to). Represented as boolean presence (`1.0`, the
  "matched but no usable numeric magnitude" convention already used elsewhere in this
  codebase) rather than a literal `0.0` that would read as "tag absent." Flagged here as a
  real representation gap, not silently absorbed.
- **A stale scope-applicability catch (see `trainer_energy_tag_catalog.py`'s own module
  docstring): `ENERGY_MOVE` gets the `scope` qualifier** on Handheld Fan's row
  (`card:1161`, `scope=opponent_internal`) even though spec 11b's locked Phase 4 list omits
  `ENERGY_MOVE` from its scope-applicable tags -- the tag's own earlier catalog-table entry
  already documented this qualifier, and the row genuinely needs it to be distinguishable
  from the ordinary own-side-to-own-side case (Energy Switch, `card:1116`).
- **Three rows use `scope="other"`** (Gravity Gemstone's "both Active Pokemon" --
  spec 11b's own prose flags this as "a scope value beyond self/own-team/opponent"; Risky
  Ruins' "any player" Bench-entry trigger) since the locked 6-value scope enum
  (`self, own_bench, own_team, opponent_named_subset, both_sides, other`) has no dedicated
  value for either shape -- `other` is exactly the catch-all bucket this situation exists
  for.
- **`SURVIVE_KO`'s minimum-HP magnitude (Survival Brace, `card:1155`, "becomes 10") is
  transcribed manually here (`10`) even though the catalog's own drafted regex has no
  capture group for it** -- a real Deliverable B (regex-fallback) limitation, acceptable
  since `SURVIVE_KO` has exactly one known meta card and no non-meta instance found during
  Stage 3's spot-check; noted, not fixed, same treatment `RNG_SCALING_DAMAGE` got on the
  Pokemon side for being "narrow, written for the one known instance."
"""
from __future__ import annotations

from .pokemon_tag_catalog import CAPS as _POKEMON_CAPS
from .trainer_energy_tag_catalog import CONTENT_TAGS, TAG_CATALOG, _normalize

_AT_CAP_COUNT = _POKEMON_CAPS["count"]

# Row shape: (card_id, "trainer_effect"|"energy_effect", row_index, [(tag_name, magnitude_or_None, qualifiers)])
_RAW_ROWS: list[tuple[int, str, int, list[tuple[str, float | None, dict]]]] = [
    # --- Supporter batch (39 rows) ---
    (1182, "trainer_effect", 0, [("SWITCH_FORCE", None, {})]),
    (1184, "trainer_effect", 0, [("DISCARD_RETRIEVE", 3, {})]),  # rule 2: up to 3
    (1185, "trainer_effect", 0, [("REVEAL_DIG", 6, {})]),
    (1186, "trainer_effect", 0, [("DISCARD_OPP", 2, {})]),  # rule 2: up to 2
    (1187, "trainer_effect", 0, [
        ("DISCARD_SELF", 1, {}),  # cost, working decision #1
        ("DRAW", _AT_CAP_COUNT, {}),  # rule 4: pure per-unit scaling, no base
    ]),
    (1188, "trainer_effect", 0, [("SEARCH_DECK_TOP", 2, {})]),
    (1189, "trainer_effect", 0, [("EVOLVE_SEARCH", None, {})]),
    (1191, "trainer_effect", 0, [
        ("SELF_SWITCH", None, {}),
        ("STAT_BUFF", 30, {"scope": "opponent_named_subset"}),
        ("MULTI_CHOICE", None, {}),
    ]),
    (1192, "trainer_effect", 0, [
        ("DISCARD_SELF", _AT_CAP_COUNT, {}),  # rule 6: all (hand)
        ("DRAW", 5, {}),
    ]),
    (1194, "trainer_effect", 0, [("SEARCH_HAND", 2, {})]),  # rule 5: 2 distinct cards named
    (1195, "trainer_effect", 0, [
        ("SEARCH_ATTACH", 2, {"distribution": True}),  # rule 2: up to 2
        ("CONDITION", None, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (1197, "trainer_effect", 0, [("DISCARD_OPP", 3, {})]),  # target hand size, not a count
    (1198, "trainer_effect", 0, [
        ("SEARCH_HAND", 1, {}),
        ("SEARCH_ATTACH", 1, {}),
    ]),
    (1202, "trainer_effect", 0, [("REVEAL_DIG", 7, {})]),
    (1203, "trainer_effect", 0, [
        ("SELF_SWITCH", None, {}),
        ("DRAW", 5, {}),  # target hand size
        ("CONDITIONAL", None, {}),
    ]),
    (1204, "trainer_effect", 0, [
        ("SWITCH_FORCE", None, {}),
        ("CONDITION", None, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (1205, "trainer_effect", 0, [("SEARCH_HAND", 3, {})]),  # rule 2: up to 3
    (1206, "trainer_effect", 0, [
        ("DISCARD_SELF", _AT_CAP_COUNT, {}),  # rule 6: all (hand)
        ("SEARCH_HAND", 3, {}),  # rule 5: 3 distinct cards named
    ]),
    (1208, "trainer_effect", 0, [
        ("DISCARD_SELF", 1, {}),  # cost
        ("DRAW", 6, {}),  # target hand size
    ]),
    (1210, "trainer_effect", 0, [("SEARCH_HAND", 2, {})]),  # rule 2: max of the two OR caps
    (1211, "trainer_effect", 0, [("STAT_BUFF", 40, {"scope": "opponent_named_subset"})]),
    (1212, "trainer_effect", 0, [("HEAL", 70, {})]),
    (1213, "trainer_effect", 0, [
        ("HAND_RESET", None, {}),
        ("DRAW", 4, {}),
    ]),
    (1216, "trainer_effect", 0, [
        ("DRAW", 5, {}),  # rule 3: guaranteed base
        ("CONDITIONAL", None, {}),
    ]),
    (1217, "trainer_effect", 0, [
        ("HAND_RESET", None, {}),
        ("DRAW", 5, {}),  # asymmetric (5 self / 3 opp) -- self value kept, see module docstring
    ]),
    (1218, "trainer_effect", 0, [
        ("SELF_SWITCH", None, {}),
        ("SWITCH_FORCE", None, {}),
        ("CONDITIONAL", None, {"voluntary_cost": True}),
    ]),
    (1219, "trainer_effect", 0, [("SEARCH_HAND", 1, {})]),
    (1220, "trainer_effect", 0, [("SEARCH_HAND", 3, {})]),  # rule 2: up to 3
    (1223, "trainer_effect", 0, [
        ("HAND_RESET", None, {}),
        ("DRAW", 5, {}),  # coin-flip-determined; larger deterministic branch value kept
        ("CONDITIONAL", None, {}),
    ]),
    (1224, "trainer_effect", 0, [("DRAW", 3, {})]),
    (1225, "trainer_effect", 0, [("SEARCH_HAND", 2, {})]),  # rule 5: 2 distinct cards named
    (1227, "trainer_effect", 0, [
        ("HAND_RESET", None, {}),
        ("DRAW", 6, {}),  # rule 3: guaranteed base
        ("CONDITIONAL", None, {}),
    ]),
    (1228, "trainer_effect", 0, [
        ("DAMAGE_IMMUNE_FROM", None, {"scope": "self"}),
        ("EFFECT_IMMUNE", None, {"scope": "self"}),
    ]),
    (1229, "trainer_effect", 0, [
        ("HEAL", _AT_CAP_COUNT, {}),  # rule 6: all
        ("ENERGY_RETURN_TO_HAND", None, {}),
        ("CONDITIONAL", None, {"near_always_true": True}),
    ]),
    (1231, "trainer_effect", 0, [("SEARCH_HAND", 3, {})]),  # rule 5: 3 distinct cards named
    (1235, "trainer_effect", 0, [
        ("REVEAL_DIG", 6, {}),
        ("SEARCH_ATTACH", 1, {}),
    ]),
    (1236, "trainer_effect", 0, [("DRAW", 3, {})]),
    (1238, "trainer_effect", 0, [("DISCARD_RETRIEVE", 4, {})]),  # rule 2: up to 4
    (1240, "trainer_effect", 0, [("ENERGY_ACCEL", 2, {})]),  # rule 2: up to 2

    # --- Item batch (32 rows) ---
    (1077, "trainer_effect", 0, [("REVEAL_DIG", 4, {})]),
    (1079, "trainer_effect", 0, [
        ("EVOLVE_FROM_HAND", None, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (1080, "trainer_effect", 0, [
        ("HAND_RESET", None, {}),
        ("DRAW", 5, {}),  # asymmetric (5 self / 2 opp) -- self value kept
    ]),
    (1081, "trainer_effect", 0, [("DISCARD_OPP_BOARD", 1, {})]),
    (1086, "trainer_effect", 0, [("SEARCH_BENCH", 2, {})]),  # rule 2: up to 2
    (1087, "trainer_effect", 0, [
        ("DISCARD_OPP", 5, {}),  # target hand size
        ("DISCARD_SELF", 5, {}),  # target hand size
    ]),
    (1088, "trainer_effect", 0, [
        ("SWITCH_FORCE", None, {}),
        ("SELF_SWITCH", None, {}),
        ("CONDITIONAL", None, {"voluntary_cost": True}),
    ]),
    (1092, "trainer_effect", 0, [
        ("DISCARD_SELF", 3, {}),  # cost
        ("SEARCH_HAND", 4, {}),  # rule 5: 4 distinct cards named
    ]),
    (1094, "trainer_effect", 0, [("REVEAL_DIG", 7, {})]),
    (1095, "trainer_effect", 0, [("CONDITION", None, {})]),  # Burned + Confused, simultaneous
    (1097, "trainer_effect", 0, [("DISCARD_RETRIEVE", 1, {})]),  # rule 5: 1 card either way
    (1098, "trainer_effect", 0, [("ENERGY_ACCEL", 2, {})]),  # rule 2: up to 2 targets, 1 each
    (1102, "trainer_effect", 0, [("REVEAL_DIG", 7, {})]),
    (1109, "trainer_effect", 0, [("DISCARD_RETRIEVE", 2, {})]),  # rule 2: up to 2
    (1113, "trainer_effect", 0, [("ENERGY_ACCEL", 1, {})]),  # rule 5: unspecified singular
    (1116, "trainer_effect", 0, [("ENERGY_MOVE", 1, {})]),
    (1118, "trainer_effect", 0, [("DISCARD_RETRIEVE", 2, {})]),  # rule 2: up to 2
    (1119, "trainer_effect", 0, [("SEARCH_HAND", 1, {})]),
    (1120, "trainer_effect", 0, [
        ("DISCARD_OPP_BOARD", 1, {}),
        ("CONDITIONAL", None, {}),  # coin-flip heads-gated
    ]),
    (1121, "trainer_effect", 0, [
        ("DISCARD_SELF", 2, {}),  # cost
        ("SEARCH_HAND", 1, {}),
    ]),
    (1122, "trainer_effect", 0, [("REVEAL_DIG", 7, {})]),
    (1123, "trainer_effect", 0, [("SELF_SWITCH", None, {})]),
    (1129, "trainer_effect", 0, [("DISCARD_TO_DECK", 5, {})]),  # rule 2: up to 5
    (1134, "trainer_effect", 0, [("SEARCH_HAND", 1, {})]),
    (1137, "trainer_effect", 0, [("DISCARD_OPP_BOARD", 2, {})]),  # rule 2: up to 2, either side
    (1139, "trainer_effect", 0, [("DISCARD_TO_DECK", 5, {})]),  # rule 2: up to 5
    (1141, "trainer_effect", 0, [("STAT_BUFF", 30, {"scope": "own_team"})]),
    (1142, "trainer_effect", 0, [("SEARCH_HAND", 1, {})]),  # OR of two single-card options
    (1145, "trainer_effect", 0, [("SEARCH_HAND", 1, {})]),
    (1146, "trainer_effect", 0, [("ENERGY_ACCEL", 1, {})]),
    (1147, "trainer_effect", 0, [("HEAL", 80, {})]),  # targeting restriction, not CONDITIONAL
    (1152, "trainer_effect", 0, [("SEARCH_HAND", 1, {})]),

    # --- Pokemon Tool batch (11 rows) ---
    (1155, "trainer_effect", 0, [
        ("SURVIVE_KO", 10, {}),  # manually transcribed, see module docstring
        ("SELF_CONSUME", None, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (1156, "trainer_effect", 0, [
        ("DRAW", 2, {}),
        ("ON_DAMAGED_TRIGGER", None, {}),
    ]),
    (1158, "trainer_effect", 0, [("STAT_BUFF", 50, {"scope": "self"})]),
    (1159, "trainer_effect", 0, [("HP_BUFF", 100, {"scope": "self"})]),
    (1161, "trainer_effect", 0, [
        # "opponent_internal" (moves the attacker's own Energy among the attacker's own
        # side) has no dedicated value in the locked 6-value scope enum -- mapped to the
        # closest available bucket, "opponent_named_subset" (affects the opponent's side),
        # losing the "internal redistribution, not own-side-affecting" nuance. See module
        # docstring's stale-scope-list note.
        ("ENERGY_MOVE", 1, {"scope": "opponent_named_subset"}),
        ("ON_DAMAGED_TRIGGER", None, {}),
    ]),
    (1166, "trainer_effect", 0, [("RETREAT_COST_MOD", 1, {"scope": "other"})]),  # both Active Pokemon
    (1167, "trainer_effect", 0, [
        ("COUNTER_PLACE", 12, {}),
        ("ON_DAMAGED_TRIGGER", None, {}),
        ("SELF_CONSUME", None, {}),
        ("CONDITIONAL", None, {"near_always_true": True}),
    ]),
    (1173, "trainer_effect", 0, [("HP_BUFF", 70, {"scope": "self"})]),
    (1174, "trainer_effect", 0, [("RETREAT_COST_MOD", -2, {"scope": "self"})]),
    (1175, "trainer_effect", 0, [("STAT_BUFF", 30, {"scope": "self"})]),
    (1176, "trainer_effect", 0, [
        ("COUNTER_PLACE", 4, {}),
        ("ON_DAMAGED_TRIGGER", None, {}),
    ]),

    # --- Stadium batch (17 rows) ---
    (1242, "trainer_effect", 0, [("HEAL", 10, {"scope": "own_team"})]),
    (1244, "trainer_effect", 0, [("DAMAGE_REDUCTION", 30, {"scope": "both_sides"})]),
    (1245, "trainer_effect", 0, [("CONDITION_IMMUNITY", None, {"scope": "both_sides"})]),
    (1246, "trainer_effect", 0, [("SUPPRESS_TOOLS", None, {"scope": "both_sides"})]),
    (1247, "trainer_effect", 0, [("DAMAGE_IMMUNE_FROM", None, {"scope": "both_sides"})]),
    (1249, "trainer_effect", 0, [
        ("EVOLVE_SEARCH", None, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (1250, "trainer_effect", 0, [("BENCH_CAPACITY_MOD", 8, {"scope": "both_sides"})]),
    (1252, "trainer_effect", 0, [("HP_BUFF", -30, {"scope": "both_sides"})]),
    (1253, "trainer_effect", 0, [("RETREAT_COST_MOD", None, {"scope": "both_sides"})]),  # absolute 0, see module docstring
    (1256, "trainer_effect", 0, [("SUPPRESS_ABILITIES", None, {"scope": "both_sides"})]),
    (1257, "trainer_effect", 0, [("DRAW", 2, {})]),
    (1259, "trainer_effect", 0, [("SEARCH_HAND", 1, {})]),
    (1260, "trainer_effect", 0, [("COUNTER_PLACE", 2, {"scope": "other"})]),
    (1261, "trainer_effect", 0, [("EVOLUTION_RULE_MOD", None, {"scope": "both_sides"})]),
    (1262, "trainer_effect", 0, [("SELF_SWITCH", None, {})]),
    (1264, "trainer_effect", 0, [("EFFECT_IMMUNE", None, {"scope": "both_sides"})]),
    (1266, "trainer_effect", 0, [("ATTACK_COST_MOD", 1, {"scope": "both_sides"})]),

    # --- Special Energy batch (10 rows) ---
    (11, "energy_effect", 0, [("EFFECT_IMMUNE", None, {"scope": "self"})]),
    (12, "energy_effect", 0, [
        ("FLEXIBLE_ENERGY_PROVISION", 1, {}),
        ("PRIZE_DENIAL", 1, {}),
    ]),
    (13, "energy_effect", 0, [
        ("DRAW", 4, {}),
        ("ON_ATTACH_TRIGGER", None, {}),
    ]),
    (14, "energy_effect", 0, [
        ("COUNTER_PLACE", 2, {}),
        ("ON_DAMAGED_TRIGGER", None, {}),
    ]),
    (15, "energy_effect", 0, [
        ("FLEXIBLE_ENERGY_PROVISION", 2, {}),
        ("SELF_CONSUME", None, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (16, "energy_effect", 0, [
        ("FLEXIBLE_ENERGY_PROVISION", 1, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (17, "energy_effect", 0, [
        ("SELF_CONSUME", None, {}),
        ("FLEXIBLE_ENERGY_PROVISION", 1, {}),
        ("CONDITIONAL", None, {}),
    ]),
    (18, "energy_effect", 0, [("HP_BUFF", 20, {"scope": "self"})]),
    (19, "energy_effect", 0, [
        ("SEARCH_BENCH", 2, {}),  # rule 2: up to 2
        ("ON_ATTACH_TRIGGER", None, {}),
    ]),
    (20, "energy_effect", 0, [("EFFECT_IMMUNE", None, {"scope": "self"})]),
]

assert len(_RAW_ROWS) == 109, f"expected 109 rows, got {len(_RAW_ROWS)}"


def _build_vector(tags: list[tuple[str, float | None, dict]], is_content: bool) -> list[float]:
    vec = [0.0] * len(CONTENT_TAGS)
    conditional_presence = 0.0
    conditional_voluntary = 0.0
    conditional_near_always = 0.0
    multi_choice = 0.0
    on_damaged = 0.0
    on_attach = 0.0
    distribution = 0.0
    conserved = 0.0
    self_referential = 0.0
    scope_onehot = [0.0] * 6
    scope_values = ("self", "own_bench", "own_team", "opponent_named_subset", "both_sides", "other")
    any_scoped_tag_present = False

    by_name: dict[str, tuple[float | None, dict]] = {}
    for name, magnitude, qualifiers in tags:
        if name == "CONDITIONAL":
            conditional_presence = 1.0
            if qualifiers.get("voluntary_cost"):
                conditional_voluntary = 1.0
            if qualifiers.get("near_always_true"):
                conditional_near_always = 1.0
            continue
        if name == "MULTI_CHOICE":
            multi_choice = 1.0
            continue
        if name == "ON_DAMAGED_TRIGGER":
            on_damaged = 1.0
            continue
        if name == "ON_ATTACH_TRIGGER":
            on_attach = 1.0
            continue
        by_name[name] = (magnitude, qualifiers)
        idx = CONTENT_TAGS.index(name)
        spec = TAG_CATALOG[name]
        vec[idx] = _normalize(magnitude, spec.magnitude_family)
        if qualifiers.get("distribution"):
            distribution = 1.0
        if "scope" in qualifiers:
            any_scoped_tag_present = True
            scope_onehot = [0.0] * 6
            scope_onehot[scope_values.index(qualifiers["scope"])] = 1.0

    result = list(vec)
    result.append(conditional_presence)
    result.append(conditional_voluntary)
    result.append(conditional_near_always)
    result.append(multi_choice)
    result.append(on_damaged)
    result.append(on_attach)
    result.append(distribution)
    result.append(conserved)
    result.append(self_referential)
    result.extend(scope_onehot if any_scoped_tag_present else [0.0] * 6)
    return result


def build_meta_table() -> dict[int, dict[str, list[float]]]:
    out: dict[int, dict[str, list[float]]] = {}
    for card_id, kind, row_index, tags in _RAW_ROWS:
        effect_id = f"card:{card_id}:{kind}:{row_index}"
        out.setdefault(card_id, {})[effect_id] = _build_vector(tags, is_content=True)
    return out


META_TAGS = build_meta_table()
