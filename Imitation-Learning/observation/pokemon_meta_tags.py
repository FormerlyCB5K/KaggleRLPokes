"""Deliverable A: the 201-row meta Pokemon tag table, transcribed from spec 11a's manual
assignment table (`Ceruledge-RL/specs/11a-pokemon-attribute-tag-vocabulary.md`, "Manual
assignment table" section, batches 1-6) into structured data.

**Dynamic-magnitude policy** (a judgment call needed for rows whose true value depends on
live board state, not a fixed printed number -- documented here rather than resolved
silently, per this project's no-silent-loss convention):

1. A registry-approved statistic exists (`expected_value`) -> use it. Only Mega Kangaskhan
   ex (`card:756:attack:0`) qualifies.
2. The row states an explicit cap ("up to N", "top N") -> use the resulting concrete
   maximum.
3. "Base X (guaranteed), + Y if [condition/per-unit scaling]" -> use the guaranteed base X.
   Covers both binary conditional-bonus rows and open-ended per-unit-scaling rows with a
   nonzero floor uniformly; the bonus is separately visible via the `CONDITIONAL` flag where
   applicable.
4. A pure per-unit scaling formula with **no** base (the whole value is `k * N`, zero at
   N=0) -> the at-or-above-cap sentinel (magnitude = that family's own cap, normalizing to
   `1.0`), matching spec 11a's own stated convention for uncapped scaling.
5. An unspecified count implied singular ("search for a card") -> `1`.
6. "All" / "any amount" / "any number" -> the at-or-above-cap sentinel (rule 4's sentinel).

Every row below that isn't a bare printed number carries an inline comment naming which
rule applied. `SNIPE`'s magnitude is **never** inferred from `DAMAGE`'s value or vice versa
(see spec 11a's Darmanitan/Grimmsnarl distinction) -- each is transcribed from its own
explicit number in the manual assignment table.

**`DAMAGE` vs `SNIPE`, refined (post-transcription correction):** `DAMAGE` is damage
guaranteed to land on the active target of a normal attack; `SNIPE` is damage delivered via
a bench-eligible redirect/choice mechanism, independent of `DAMAGE`. Two distinct shapes,
never conflated:
- **Additive** (a fixed base attack damage plus a *separate* bonus hit to a Benched
  Pokemon, phrased "...also does N damage to 1 of your opponent's Benched Pokemon") -- both
  tags fire, each with its own number. E.g. N's Darmanitan (`card:258:attack:1`, "Flamebody
  Cannon"): 90 to the active (printed base) + 90 to a Benched Pokemon (bonus) ->
  `DAMAGE=90, SNIPE=90`, hitting two Pokemon total. Same shape for `card:648:attack:0`,
  `card:1031:attack:0`, `card:108:attack:1`.
- **Sole redirect** (the attack's entire damage is one freely-targetable hit -- "this attack
  does N damage to 1 of your opponent's Pokemon," no "also," no separate base) -- only
  `SNIPE` fires; `DAMAGE` does not co-fire, since there is no guaranteed-active number
  independent of the redirect. E.g. Fezandipiti ex (`card:140:attack:0`, "Cruel Arrow"): a
  single 100-damage hit to any one of the opponent's Pokemon (the "(Don't apply Weakness
  and Resistance for Benched Pokemon)" ruling note is what makes this bench-eligible, not a
  literal "Benched" in the main clause) -> `SNIPE=100` only, hitting exactly one Pokemon.

Originally transcribed as `DAMAGE=100, SNIPE=100` for Fezandipiti ex, mirroring Darmanitan's
shape -- caught as wrong because it made a 1-Pokemon-hit row and a 2-Pokemon-hit row
indistinguishable in the tag block. Fixed here; the general regex-fallback path
(`pokemon_tag_catalog.tag_unseen_pokemon`) carries the equivalent fix for non-meta cards.
"""
from __future__ import annotations

from .pokemon_tag_catalog import CAPS, CONTENT_TAGS, TAG_CATALOG, _normalize

# Row shape: (card_id, "attack"|"ability", row_index, [(tag_name, magnitude_or_None, qualifiers), ...])
# qualifiers is a dict subset of {"distribution": bool, "conserved": bool,
# "self_referential": bool, "scope": str}; omitted keys use the default (single / False /
# True / "self" respectively). magnitude=None means "boolean tag, presence only."
_AT_CAP_DAMAGE = CAPS["damage"]
_AT_CAP_COUNT = CAPS["count"]

_RAW_ROWS: list[tuple[int, str, int, list[tuple[str, float | None, dict]]]] = [
    # --- Batch 1 ---
    (741, "attack", 0, [("DAMAGE", 10, {}), ("SELF_SWITCH", None, {})]),
    (742, "attack", 0, [("DAMAGE", 30, {})]),
    (742, "ability", 0, [("DRAW", 2, {})]),
    (743, "attack", 0, [("COUNTER_PLACE", _AT_CAP_COUNT, {})]),  # rule 4: 2*hand, no base
    (743, "ability", 0, [("DRAW", 3, {})]),
    (305, "attack", 0, [("SELF_SWITCH", None, {})]),  # explicitly no DAMAGE (0-damage attack)
    (305, "attack", 1, [("DAMAGE", 20, {})]),
    (66, "attack", 0, [("DAMAGE", 90, {})]),
    (66, "ability", 0, [("DRAW", 3, {}), ("SELF_MILL", None, {}), ("CONDITIONAL", None, {"near_always_true": True})]),  # rule 2: up to 3
    (344, "attack", 0, [("EVOLVE_SEARCH", None, {})]),
    (345, "attack", 0, [("DAMAGE", 120, {}), ("IGNORES_ACTIVE_EFFECTS", None, {})]),
    (345, "ability", 0, [("DAMAGE_IMMUNE_FROM", None, {"scope": "self"})]),
    (756, "attack", 0, [("RNG_SCALING_DAMAGE", 250, {})]),  # rule 1: registry expected_value
    (756, "ability", 0, [("DRAW", 2, {})]),
    (112, "attack", 0, [("DAMAGE", 60, {}), ("CONDITION", None, {})]),
    (112, "ability", 0, [("COUNTER_MOVE", 3, {"conserved": False})]),  # rule 2: up to 3
    (646, "attack", 0, [("DRAW", 1, {})]),
    (646, "attack", 1, [("DAMAGE", 10, {})]),
    (343, "attack", 0, [("DAMAGE", 30, {})]),
    (343, "ability", 0, [("DAMAGE_IMMUNE_FROM", None, {"scope": "own_bench"})]),
    (140, "attack", 0, [("SNIPE", 100, {})]),  # sole free-choice hit (Cruel Arrow: "100 damage
    # to 1 of your opponent's Pokemon") -- the entire attack is one redirectable hit, not a
    # guaranteed active hit + bonus snipe, so DAMAGE does not co-fire (see module docstring)
    (140, "ability", 0, [("DRAW", 3, {})]),
    (648, "attack", 0, [("DAMAGE", 180, {}), ("SNIPE", 30, {})]),  # two distinct numbers, per spec
    (648, "ability", 0, [("SEARCH_ATTACH", 5, {"distribution": True})]),  # rule 2: up to 5
    (647, "attack", 0, [("DAMAGE", 60, {})]),
    (860, "attack", 0, [("DAMAGE", 10, {})]),
    (1030, "attack", 0, [("DAMAGE", 20, {})]),
    (104, "attack", 0, [("DAMAGE", 60, {})]),
    (104, "ability", 0, [("COUNTER_PLACE", _AT_CAP_COUNT, {})]),  # rule 4: 1 per ability-holder, no base
    (1031, "attack", 0, [("DAMAGE", 120, {}), ("SNIPE", 50, {})]),
    (1031, "attack", 1, [("DAMAGE", 210, {}), ("IGNORES_ACTIVE_EFFECTS", None, {})]),
    (414, "attack", 0, [("DAMAGE", 60, {}), ("CONDITIONAL", None, {})]),  # rule 3: base 60
    (414, "ability", 0, [("EFFECT_IMMUNE", None, {"scope": "own_team"})]),
    (400, "attack", 0, [("DAMAGE", 30, {}), ("RECOIL", 10, {})]),

    # --- Batch 2 ---
    (401, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 30*own TR count, no base
    (401, "ability", 0, [("ENERGY_ACCEL", 1, {})]),  # rule 5: unspecified, singular context
    (379, "attack", 0, [("DAMAGE", 20, {}), ("IGNORES_RESISTANCE", None, {})]),
    (380, "attack", 0, [("DAMAGE", 40, {})]),
    (380, "ability", 0, [("SEARCH_HAND", 1, {})]),  # rule 5
    (341, "attack", 0, [("DAMAGE", 20, {})]),
    (434, "attack", 0, [("COPY_ATTACK", None, {})]),
    (119, "attack", 0, [("DAMAGE", 10, {})]),
    (119, "attack", 1, [("DAMAGE", 40, {})]),
    (120, "attack", 0, [("DAMAGE", 70, {})]),
    (120, "ability", 0, [("REVEAL_DIG", 2, {})]),
    (342, "attack", 0, [("DAMAGE", 80, {})]),
    (342, "ability", 0, [("STAT_BUFF", 30, {"scope": "own_team"})]),
    (381, "attack", 0, [("DAMAGE", 100, {}), ("DRAW", 6, {}), ("CONDITIONAL", None, {})]),  # target hand size 6, treated as the magnitude
    (381, "attack", 1, [("DAMAGE", 260, {}), ("DISCARD_SELF", _AT_CAP_COUNT, {})]),  # rule 6: all energy
    (235, "attack", 0, [("DAMAGE", 10, {}), ("ITEM_LOCK", None, {})]),
    (431, "attack", 0, [("DAMAGE", 280, {}), ("DISCARD_SELF", 2, {})]),  # rule 2: 160+60*2=280 max; discard up to 2
    (431, "ability", 0, []),  # known gap: pure attack-legality gate, deliberately all-zero
    (666, "attack", 0, [("DAMAGE", 50, {}), ("SEARCH_ATTACH", 3, {"distribution": True})]),  # rule 2: up to 3
    (666, "ability", 0, [("SETUP_ALT_PLACEMENT", None, {})]),
    (861, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 50*opp hand size, no base
    (861, "attack", 1, [("DAMAGE", 150, {}), ("CONDITION", None, {})]),
    (121, "attack", 0, [("DAMAGE", 70, {})]),
    (121, "attack", 1, [("DAMAGE", 200, {}), ("COUNTER_PLACE", 6, {"distribution": True})]),
    (131, "attack", 0, [("REVIVE_FROM_DISCARD", 3, {})]),  # rule 2: up to 3
    (131, "attack", 1, [("DAMAGE", 30, {})]),
    (132, "attack", 0, [("DAMAGE", 50, {})]),
    (132, "ability", 0, [("COUNTER_PLACE", 5, {}), ("SELF_KO", None, {})]),
    (117, "attack", 0, [("DAMAGE", 140, {}), ("IGNORES_ACTIVE_EFFECTS", None, {})]),
    (117, "ability", 0, [("DAMAGE_IMMUNE_FROM", None, {"scope": "self"})]),
    (93, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 20*own bench count, no base
    (93, "ability", 0, [("DOUBLE_ATTACK", None, {}), ("CONDITIONAL", None, {})]),
    (133, "attack", 0, [("DAMAGE", 150, {}), ("RETREAT_LOCK", None, {"scope": "opponent_named_subset"})]),
    (133, "ability", 0, [("COUNTER_PLACE", 13, {}), ("SELF_KO", None, {})]),
    (92, "attack", 0, [("DAMAGE", 10, {}), ("COIN_FLIP_DAMAGE", 20, {})]),

    # --- Batch 3 ---
    (89, "attack", 0, [("DAMAGE", 10, {})]),
    (89, "attack", 1, [("DAMAGE", 30, {})]),
    (90, "attack", 0, [("DAMAGE", 50, {})]),
    (90, "ability", 0, [("SEARCH_HAND", 1, {})]),  # rule 5: "any card"
    (387, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {}), ("IGNORES_WEAKNESS", None, {})]),  # rule 4: 10*counters, no base
    (247, "attack", 0, [("COUNTER_PLACE", 2, {})]),
    (247, "ability", 0, [("DOUBLE_ATTACK", None, {}), ("CONDITIONAL", None, {})]),
    (169, "attack", 0, [("DAMAGE", 30, {})]),
    (169, "attack", 1, [("DAMAGE", 80, {})]),  # rule 3: base 80, +10/counter
    (190, "attack", 0, [("DAMAGE", 220, {}), ("SELF_NO_WEAKNESS", None, {})]),
    (190, "ability", 0, [("ENERGY_ACCEL", 2, {"distribution": True})]),  # rule 2: up to 2
    (164, "attack", 0, [("DRAW", 3, {})]),
    (164, "attack", 1, [("DAMAGE", 20, {}), ("COIN_FLIP_DAMAGE", 20, {})]),
    (506, "attack", 0, [("DAMAGE", 10, {}), ("ATTACK_LOCK", None, {"scope": "opponent_named_subset"})]),
    (689, "attack", 0, [("DAMAGE", 20, {}), ("RETREAT_LOCK", None, {"scope": "opponent_named_subset"})]),
    (689, "attack", 1, [("DAMAGE", 110, {})]),
    (65, "attack", 0, [("DAMAGE", 10, {})]),
    (65, "attack", 1, [("DAMAGE", 30, {}), ("DAMAGE_IMMUNE_FROM", None, {"scope": "self"}), ("EFFECT_IMMUNE", None, {"scope": "self"})]),
    (1071, "attack", 0, [("DAMAGE", 60, {}), ("SELF_RETURN_TO_HAND", None, {})]),
    (1071, "ability", 0, [("SEARCH_HAND", 1, {})]),
    (817, "attack", 0, [("COUNTER_PLACE", 1, {})]),
    (678, "attack", 0, [("DAMAGE", 130, {}), ("ENERGY_ACCEL", 3, {"distribution": True})]),  # rule 2: up to 3
    (678, "attack", 1, [("DAMAGE", 270, {}), ("COOLDOWN", None, {})]),
    (677, "attack", 0, [("DAMAGE", 30, {}), ("COOLDOWN", None, {})]),
    (848, "attack", 0, [("SELF_SWITCH", None, {})]),
    (848, "attack", 1, [("DAMAGE", 20, {})]),
    (849, "attack", 0, [("DAMAGE", 60, {}), ("CONDITIONAL", None, {})]),  # rule 3: base 60
    (849, "attack", 1, [("DAMAGE", 160, {}), ("IGNORES_ACTIVE_EFFECTS", None, {})]),
    (676, "attack", 0, [("DAMAGE", 70, {}), ("IGNORES_WEAKNESS", None, {}), ("IGNORES_RESISTANCE", None, {}), ("CONDITIONAL", None, {})]),
    (245, "attack", 0, [("CONDITION", None, {}), ("COUNTER_MOVE", _AT_CAP_COUNT, {"conserved": True, "distribution": True})]),  # "any amount" -> rule 6
    (245, "attack", 1, [("DAMAGE", 10, {})]),  # rule 3: base 10, +50/opp energy
    (818, "attack", 0, [("DAMAGE", 80, {})]),
    (818, "ability", 0, [("CONDITION", None, {})]),
    (58, "attack", 0, [("MILL", 4, {}), ("CONDITIONAL", None, {})]),  # rule 2: 1 base +3 conditional, up to 4
    (58, "attack", 1, [("DAMAGE", 160, {})]),

    # --- Batch 4 ---
    (675, "attack", 0, [("DAMAGE", 50, {})]),
    (675, "ability", 0, [("DRAW", 3, {}), ("DISCARD_SELF", 1, {})]),
    (649, "attack", 0, [("DAMAGE", 20, {})]),  # rule 3: base 20, +40/{D}Energy
    (791, "attack", 0, [("DAMAGE", 20, {}), ("CONDITIONAL", None, {})]),  # rule 3: base 20
    (214, "attack", 0, [("DAMAGE", 140, {})]),
    (214, "ability", 0, [("EXTRA_PRIZE", 1, {})]),
    (959, "attack", 0, [("DAMAGE", 30, {})]),
    (184, "attack", 0, [("DAMAGE", 200, {}), ("COOLDOWN", None, {})]),
    (184, "ability", 0, [("RETREAT_COST_MOD", 0, {"scope": "own_team"})]),  # sets to 0
    (57, "attack", 0, [("DAMAGE", 30, {})]),
    (57, "ability", 0, [("ATTACK_INHERIT", None, {"scope": "self"})]),
    (745, "attack", 0, [("DRAW", 1, {})]),
    (745, "attack", 1, [("DAMAGE", 10, {})]),
    (432, "attack", 0, [("COUNTER_MOVE", _AT_CAP_COUNT, {"conserved": False})]),  # rule 6: "all"
    (432, "attack", 1, [("DAMAGE", 70, {})]),
    (73, "attack", 0, [("DAMAGE", 30, {}), ("RECOIL", 10, {})]),
    (74, "attack", 0, [("DAMAGE", 10, {})]),  # rule 3: base 10, +30/opp energy
    (74, "ability", 0, [("DAMAGE_IMMUNE_FROM", None, {"scope": "own_bench"}), ("EFFECT_IMMUNE", None, {"scope": "own_bench"})]),
    (174, "attack", 0, [("DAMAGE", 70, {}), ("CONDITIONAL", None, {})]),
    (174, "ability", 0, [("SEARCH_HAND", 3, {})]),  # rule 2: up to 3
    (272, "attack", 0, [("DAMAGE", 20, {})]),  # rule 3: base 20, +20/bench both sides
    (272, "ability", 0, [("WEAKNESS_OVERRIDE", None, {"scope": "opponent_named_subset"})]),
    (746, "attack", 0, [("SEARCH_HAND", 3, {})]),  # rule 2: up to 3
    (746, "attack", 1, [("DAMAGE", 30, {})]),
    (747, "attack", 0, [("SEARCH_ATTACH", 1, {})]),  # 1 per own benched pokemon -- rule 4-ish, but "1" per unit is the per-unit rate itself, treat as unspecified singular baseline
    (747, "attack", 1, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 50*total P energy, no base
    (109, "attack", 0, [("DAMAGE", 10, {})]),
    (109, "ability", 0, [("SELF_MILL", None, {})]),
    (607, "attack", 0, [("DAMAGE", 50, {}), ("CONDITIONAL", None, {})]),  # rule 3: base 50
    (607, "attack", 1, [("DAMAGE", 100, {})]),
    (31, "attack", 0, [("DRAW", 2, {})]),
    (31, "attack", 1, [("DAMAGE", 60, {}), ("STADIUM_REMOVE", None, {}), ("CONDITIONAL", None, {})]),  # rule 3: base 60
    (306, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 60*opp ex count, no base
    (306, "attack", 1, [("DAMAGE", 150, {}), ("IGNORES_ACTIVE_EFFECTS", None, {})]),
    (463, "attack", 0, [("SEARCH_HAND", 1, {})]),
    (463, "attack", 1, [("DAMAGE", 30, {}), ("ATTACK_DISABLE", None, {})]),

    # --- Batch 5 ---
    (891, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {}), ("DISCARD_SELF", _AT_CAP_COUNT, {})]),  # rule 4/6: uncapped
    (891, "attack", 1, [("DAMAGE", 100, {})]),
    (116, "attack", 0, [("DAMAGE", 70, {})]),
    (116, "ability", 0, [("HP_BUFF", 100, {}), ("STAT_BUFF", 100, {"scope": "self"}), ("CONDITIONAL", None, {})]),
    (122, "attack", 0, [("DAMAGE", 50, {})]),
    (122, "ability", 0, [("REVEAL_DIG", 6, {})]),
    (183, "attack", 0, [("SEARCH_ATTACH", 2, {})]),  # rule 2: up to 2
    (597, "attack", 0, [("DAMAGE", 20, {}), ("ITEM_LOCK", None, {})]),
    (96, "attack", 0, [("DAMAGE", 30, {})]),  # rule 3: base 30, +30/energy both actives
    (96, "ability", 0, [("ENERGY_ACCEL", 1, {}), ("DRAW", 1, {}), ("CONDITIONAL", None, {})]),
    (673, "attack", 0, [("DAMAGE", 10, {})]),
    (673, "attack", 1, [("DAMAGE", 30, {})]),
    (674, "attack", 0, [("DAMAGE", 210, {}), ("RECOIL", 70, {})]),
    (674, "ability", 0, [("SWITCH_FORCE", None, {"scope": "opponent_named_subset"})]),
    (292, "attack", 0, [("DAMAGE", 20, {})]),
    (293, "attack", 0, [("COPY_ATTACK", None, {})]),
    (293, "ability", 0, [("DISCARD_SELF", 1, {}), ("DRAW", 2, {})]),
    (1051, "attack", 0, [("DRAW", 2, {})]),
    (1051, "attack", 1, [("DAMAGE", 30, {})]),
    (1052, "attack", 0, [("DAMAGE", 80, {})]),
    (1052, "ability", 0, [("ENERGY_ACCEL", 1, {})]),
    (473, "attack", 0, [("DISCARD_SELF", 1, {}), ("DISCARD_OPP", 1, {}), ("CONDITIONAL", None, {})]),
    (474, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 20*TR supporters discarded, no base
    (303, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 20*counters on self, no base
    (303, "attack", 1, [("DAMAGE", 170, {})]),
    (333, "attack", 0, [("DAMAGE", 10, {}), ("COIN_FLIP_DAMAGE", 20, {})]),
    (63, "attack", 0, [("DISCARD_SELF", _AT_CAP_COUNT, {}), ("DRAW", 6, {})]),  # rule 6: all hand
    (63, "attack", 1, [("DAMAGE", _AT_CAP_DAMAGE, {}), ("DISCARD_SELF", _AT_CAP_COUNT, {})]),  # rule 4/6: uncapped
    (906, "attack", 0, [("DAMAGE", 70, {}), ("IGNORES_ACTIVE_EFFECTS", None, {})]),
    (906, "attack", 1, [("DAMAGE", 250, {}), ("COOLDOWN", None, {})]),
    (150, "attack", 0, [("DAMAGE", 30, {})]),  # rule 3: base 30, +30/G energy
    (150, "ability", 0, [("ENERGY_ACCEL", 1, {}), ("HEAL", 30, {}), ("CONDITIONAL", None, {})]),
    (709, "attack", 0, [("DAMAGE", 50, {}), ("SWITCH_FORCE", None, {"scope": "opponent_named_subset"})]),

    # --- Batch 6 ---
    (710, "attack", 0, [("DAMAGE", 140, {})]),
    (710, "ability", 0, [("ENERGY_AMPLIFY", 2, {"scope": "own_team"})]),
    (917, "attack", 0, [("STAT_DEBUFF", 20, {"scope": "opponent_named_subset"})]),
    (917, "attack", 1, [("DAMAGE", 30, {})]),
    (920, "attack", 0, [("DAMAGE", 220, {}), ("RECOIL", 30, {})]),
    (108, "attack", 0, [("DAMAGE", 20, {}), ("RETREAT_LOCK", None, {"scope": "opponent_named_subset"})]),
    (108, "attack", 1, [("DAMAGE", 100, {}), ("SNIPE", 120, {}), ("ENERGY_RETURN_TO_DECK", 3, {}), ("CONDITIONAL", None, {"voluntary_cost": True})]),
    (141, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 60*prizes taken, no base
    (141, "ability", 0, [("SELF_SWITCH", None, {"self_referential": False}), ("CONDITION", None, {}), ("CONDITIONAL", None, {})]),
    (257, "attack", 0, [("DAMAGE", 20, {})]),
    (257, "attack", 1, [("DAMAGE", 50, {})]),
    (258, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 30*energy in opp discard, no base
    (258, "attack", 1, [("DAMAGE", 90, {}), ("DISCARD_SELF", _AT_CAP_COUNT, {}), ("SNIPE", 90, {})]),  # 2 pokemon hit, both 90 (see module docstring)
    (970, "attack", 0, [("DAMAGE", _AT_CAP_DAMAGE, {})]),  # rule 4: 30*energy on self, no base
    (970, "ability", 0, [("DAMAGE_IMMUNE_FROM", None, {"scope": "self"}), ("CONDITIONAL", None, {})]),
    (655, "attack", 0, [("SEARCH_HAND", 3, {})]),  # rule 2: up to 3
    (655, "attack", 1, [("DAMAGE", 30, {})]),
    (827, "attack", 0, [("DAMAGE", 30, {}), ("RECOIL", 10, {})]),
    (828, "attack", 0, [("DAMAGE", 70, {}), ("DRAW", 2, {})]),
    (828, "attack", 1, [("DAMAGE", 120, {}), ("CONDITIONAL", None, {})]),  # rule 3: base 120
    (42, "attack", 0, [("SEARCH_HAND", 1, {})]),
    (42, "attack", 1, [("DAMAGE", 30, {})]),
    (833, "attack", 0, [("SEARCH_BENCH", 2, {})]),  # rule 2: up to 2
    (833, "attack", 1, [("DAMAGE", 20, {})]),
    (834, "attack", 0, [("DAMAGE", 100, {})]),
    (834, "ability", 0, [("SEARCH_ATTACH", 1, {}), ("COUNTER_PLACE", 2, {}), ("CONDITIONAL", None, {})]),
    (829, "attack", 0, [("DAMAGE", 120, {})]),
    (829, "ability", 0, [("STAT_BUFF", 120, {"scope": "self"}), ("CONDITIONAL", None, {})]),
]


def _build_vector(tags: list[tuple[str, float | None, dict]], is_attack_row: bool) -> list[float]:
    scope_values = ("self", "own_bench", "own_team", "opponent_named_subset", "both_sides", "other")
    by_name = {t[0]: t for t in tags}
    vec = [_normalize(by_name[name][1], TAG_CATALOG[name].magnitude_family) if name in by_name else 0.0
           for name in CONTENT_TAGS]
    cond = by_name.get("CONDITIONAL")
    vec.append(1.0 if cond is not None else 0.0)
    vec.append(1.0 if (cond and cond[2].get("voluntary_cost")) else 0.0)
    vec.append(1.0 if (cond and cond[2].get("near_always_true")) else 0.0)
    distribution = any(t[2].get("distribution") for t in tags)
    conserved = any(t[2].get("conserved") for t in tags)
    self_ref_entries = [t for t in tags if "self_referential" in t[2]]
    # Default True only matters when SELF_SWITCH is actually present; otherwise this bit
    # must stay 0.0 like every other tag-absent case (bug caught by the known-gap check:
    # card:431:ability:0 has no tags at all and must be exactly all-zero).
    if self_ref_entries:
        self_referential = self_ref_entries[0][2]["self_referential"]
    elif "SELF_SWITCH" in by_name:
        self_referential = True
    else:
        self_referential = False
    scope_entries = [t for t in tags if "scope" in t[2]]
    vec.append(1.0 if distribution else 0.0)
    vec.append(1.0 if conserved else 0.0)
    vec.append(1.0 if self_referential else 0.0)
    scope_onehot = [0.0] * 6
    if scope_entries:
        scope_onehot[scope_values.index(scope_entries[0][2]["scope"])] = 1.0
    vec.extend(scope_onehot)
    if is_attack_row:
        vec.extend([0.0] * 9)  # energy_cost -- card-data-sourced, not part of this transcription
    return vec


def build_meta_table() -> dict[int, dict[str, list[float]]]:
    """card_id -> {"card:ID:attack:0": vec70, "card:ID:attack:1": vec70 (if present),
    "card:ID:ability:0": vec61 (if present)}."""
    table: dict[int, dict[str, list[float]]] = {}
    for card_id, kind, index, tags in _RAW_ROWS:
        effect_id = f"card:{card_id}:{kind}:{index}"
        table.setdefault(card_id, {})[effect_id] = _build_vector(tags, kind == "attack")
    return table


META_TAGS = build_meta_table()
