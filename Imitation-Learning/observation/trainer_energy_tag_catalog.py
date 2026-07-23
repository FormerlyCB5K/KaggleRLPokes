"""Spec 11b's Trainer/Energy attribute tag catalog, transcribed into code.

Source: `Ceruledge-RL/specs/11b-trainer-energy-tag-vocabulary.md`'s "Tag catalog additions"
table (19 new tags) and Phase 4's locked field list (39 content tags total: 19 new + 20
reused verbatim from spec 11a -- see the `STAT_DEBUFF` note below). This module owns
Stage 0 (the catalog itself) and Stage 2 (`tag_unseen_trainer_energy`, the regex-based
fallback parser for any Trainer/Energy card outside the 117-card meta vocabulary).

**Reuse, not duplication.** The 20 tags 11b shares with 11a (`DAMAGE_IMMUNE_FROM`,
`EFFECT_IMMUNE`, `DRAW`, `SELF_SWITCH`, `COUNTER_PLACE`, `CONDITION`, `EVOLVE_SEARCH`,
`SEARCH_ATTACH`, `HEAL`, `ENERGY_ACCEL`, `SEARCH_HAND`, `REVEAL_DIG`, `STAT_BUFF`,
`DISCARD_SELF`, `DISCARD_OPP`, `SWITCH_FORCE`, `HP_BUFF`, `RETREAT_COST_MOD`,
`SEARCH_BENCH`, `STAT_DEBUFF`) are imported directly from `pokemon_tag_catalog.TAG_CATALOG`
-- same `TagSpec` objects, not copies, so the two vocabularies can never drift apart on a
shared tag's definition. `CONDITIONAL` (never text-detected, 3 companion bits) is likewise
the same shared object.

**`STAT_DEBUFF` added post-transcription (2026-07-21).** Spec 11b's own locked Phase 4
list of 19 reused tags omitted it, but a real non-meta Trainer Tool found during Stage 3's
spot-check (Antique Jaw Fossil, "attacks used by your opponent's Active Pokemon do 30 less
damage") needs exactly this shape -- a genuine specification gap, not a design choice, since
spec 11a's own `STAT_DEBUFF` already exists for precisely this attacker-output-nerf
framing (distinct from `DAMAGE_REDUCTION`'s defender-intake framing). Its regex was
widened in `pokemon_tag_catalog.py` to also accept the Trainer-context phrasing
("your opponent's Active Pokemon do N less damage") alongside the original Pokemon-side
"the Defending Pokemon" wording (Chikorita, `card:917:attack:0`) -- both still resolve to
the same shared `TagSpec`, so neither vocabulary needs its own copy.

**New magnitude family.** `ATTACK_COST_MOD` needs a `cost` family (cap 3, "the widest
Energy-cost delta seen" per spec 11b's own Phase 4 note) that `pokemon_tag_catalog.CAPS`
doesn't have. Rather than mutate that module's shared `CAPS` dict from here (action at a
distance on a foreign module), this file defines its own small `_normalize`/`CAPS` that
extends the Pokemon-side values with `cost` -- a few duplicated lines, in exchange for
each module owning its own family table.

**A stale-list catch found while transcribing (documented, not silently fixed):** spec
11b's own Phase 4 locked `scope`-applicability list omits `ENERGY_MOVE`, but a real
assigned row (Handheld Fan, `card:1161:trainer_effect:0`) uses `scope=opponent_internal`
on exactly this tag -- the tag's own catalog-table entry (drafted earlier in Phase 1)
already documents this qualifier ("a `scope=opponent_internal` qualifier covers the rarer
triggered case"). The Phase 4 list is stale relative to the actual assignment table, the
same class of drift spec 11a's own Phase 4 section had (48 vs 49 tags) and spec 11b's own
`conserved`/`COUNTER_MOVE` count (2 vs 3). `ENERGY_MOVE` is given the `scope` qualifier
here, matching the real assigned row, not the stale Phase 4 prose.
"""
from __future__ import annotations

import re
from typing import Literal

from .pokemon_tag_catalog import (
    CAPS as _POKEMON_CAPS,
    DISTRIBUTION_RE,
    TAG_CATALOG as POKEMON_TAG_CATALOG,
    TagSpec,
    _detect_scope,
    normalize_apostrophes,
)

TeMagnitudeFamily = Literal["damage", "count", "hp", "multiplier", "retreat", "cost", "boolean"]

COST_CAP = 3.0
CAPS: dict[str, float] = dict(_POKEMON_CAPS)
CAPS["cost"] = COST_CAP


def _normalize(magnitude: float | None, family: str) -> float:
    # `magnitude is None` means "tag present, no usable numeric value" (a genuinely
    # boolean tag, or a magnitude-bearing tag whose real number isn't captured here) --
    # always `1.0`, regardless of family. Never `0.0`: that would be indistinguishable
    # from "tag absent," exactly the bug class this session already found and fixed in
    # `pokemon_tag_catalog.tag_unseen_pokemon` (8 capture_group=None tags silently zeroed).
    # N's Castle's `RETREAT_COST_MOD` (absolute-zero Retreat Cost, not a delta of zero --
    # see trainer_energy_meta_tags.py's module docstring) is the concrete case that would
    # have collided with this if `_normalize` still special-cased only `family=="boolean"`.
    if magnitude is None:
        return 1.0
    if family == "boolean":
        return 1.0
    cap = CAPS[family]
    if family in ("hp", "retreat"):  # signed families
        return max(-1.0, min(magnitude / cap, 1.0))
    return min(magnitude / cap, 1.0)


# The 20 tags shared verbatim with spec 11a -- same TagSpec objects, no copy.
# `STAT_DEBUFF` added post-transcription: spec 11b's own locked Phase 4 list of 19 reused
# tags omitted it, but a real non-meta Trainer Tool (Antique Jaw Fossil, "attacks used by
# your opponent's Active Pokemon do 30 less damage") needs exactly this shape -- a genuine
# spec gap, not a design choice. Its regex was widened in pokemon_tag_catalog.py to accept
# Trainer-context phrasing alongside the original Pokemon-side "the Defending Pokemon"
# wording -- see that module's own STAT_DEBUFF comment.
_SHARED_TAG_NAMES = (
    "DAMAGE_IMMUNE_FROM", "EFFECT_IMMUNE", "DRAW", "SELF_SWITCH", "COUNTER_PLACE",
    "CONDITION", "EVOLVE_SEARCH", "SEARCH_ATTACH", "HEAL", "ENERGY_ACCEL", "SEARCH_HAND",
    "REVEAL_DIG", "STAT_BUFF", "DISCARD_SELF", "DISCARD_OPP", "SWITCH_FORCE", "HP_BUFF",
    "RETREAT_COST_MOD", "SEARCH_BENCH", "STAT_DEBUFF",
)
assert len(_SHARED_TAG_NAMES) == 20, f"expected 20 shared tags, got {len(_SHARED_TAG_NAMES)}"

# The 19 tags new to spec 11b, regexes transcribed from its "Tag catalog additions" table.
_NEW_TAGS: dict[str, TagSpec] = {
    "HAND_RESET": TagSpec("HAND_RESET", "boolean",
        r"shuffle(?:s)? (?:your|their) hand into (?:your|their) deck", None),
    "DISCARD_RETRIEVE": TagSpec("DISCARD_RETRIEVE", "count",
        r"put (?:up to (\d+)|a) .+ from (?:your|their) discard pile into (?:your|their) hand", 1),
    "ENERGY_RETURN_TO_HAND": TagSpec("ENERGY_RETURN_TO_HAND", "boolean",
        r"put all Energy attached to (?:that|this) Pok[eé]mon into your hand", None),
    "SEARCH_DECK_TOP": TagSpec("SEARCH_DECK_TOP", "count",
        r"search your deck for (\d+) cards?,.*put (?:those cards|them) on top of (?:it|your deck)", 1),
    "EVOLVE_FROM_HAND": TagSpec("EVOLVE_FROM_HAND", "boolean",
        r"if you have a Stage 2 card in your hand that evolves from that Pok[eé]mon.*(?:put|evolve)", None),
    "DISCARD_OPP_BOARD": TagSpec("DISCARD_OPP_BOARD", "count",
        r"discard (?:a|an) (?:Special )?Energy from 1 of your opponent's Pok[eé]mon"
        r"|[Cc]hoose up to (\d+) Pok[eé]mon Tools attached to Pok[eé]mon", 1),
    "DISCARD_TO_DECK": TagSpec("DISCARD_TO_DECK", "count",
        r"shuffle up to (\d+) .+ from your discard pile into your deck", 1),
    "ENERGY_MOVE": TagSpec("ENERGY_MOVE", "count",
        r"[Mm]ove (?:a|an|up to \d+|any amount of) (?:Basic )?Energy from"
        r" (?:1 of your Pok[eé]mon to another of your"
        r"|your Benched Pok[eé]mon to your Active"
        r"|the Pok[eé]mon you moved to your Bench to the new Active) Pok[eé]mon"
        r"|move an Energy from the Attacking Pok[eé]mon to 1 of your opponent's Benched Pok[eé]mon",
        None, qualifiers=("distribution", "conserved", "scope")),
    "SELF_CONSUME": TagSpec("SELF_CONSUME", "boolean",
        r"discard this card|discard it at the end of your turn", None),
    "SURVIVE_KO": TagSpec("SURVIVE_KO", "hp",
        r"would be Knocked Out by damage from an attack.*it is not Knocked Out", None),
    "ATTACK_COST_MOD": TagSpec("ATTACK_COST_MOD", "cost",
        r"attacks used by .+ cost (?:\{C\})+ more", None, qualifiers=("scope",)),
    "SUPPRESS_TOOLS": TagSpec("SUPPRESS_TOOLS", "boolean",
        r"Pok[eé]mon Tools attached to .+ have no effect", None, qualifiers=("scope",)),
    "CONDITION_IMMUNITY": TagSpec("CONDITION_IMMUNITY", "boolean",
        r"recovers? from all Special Conditions and can't be affected by any Special Conditions",
        None, qualifiers=("scope",)),
    "EVOLUTION_RULE_MOD": TagSpec("EVOLUTION_RULE_MOD", "boolean",
        r"can evolve into .+ during the turn they play those Pok[eé]mon", None, qualifiers=("scope",)),
    "DAMAGE_REDUCTION": TagSpec("DAMAGE_REDUCTION", "damage",
        r"take (\d+) less damage from attacks", 1, qualifiers=("scope",)),
    "SUPPRESS_ABILITIES": TagSpec("SUPPRESS_ABILITIES", "boolean",
        r"Pok[eé]mon in play .+ have no Abilities", None, qualifiers=("scope",)),
    "BENCH_CAPACITY_MOD": TagSpec("BENCH_CAPACITY_MOD", "count",
        r"can have up to (\d+) Pok[eé]mon on their Bench", 1, qualifiers=("scope",)),
    "FLEXIBLE_ENERGY_PROVISION": TagSpec("FLEXIBLE_ENERGY_PROVISION", "count",
        r"provides? .*(?:in any combination of|every type of) .*Energy"
        r"|provides \{(\w)\}(?:\{\1\}){1,} Energy instead", None),
    "PRIZE_DENIAL": TagSpec("PRIZE_DENIAL", "count",
        r"that player takes (\d+) fewer Prize cards?", 1),
}
assert len(_NEW_TAGS) == 19, f"expected 19 new tags, got {len(_NEW_TAGS)}"

# 3 new companion flags (alongside the shared `CONDITIONAL`). Never text-detected:
# `MULTI_CHOICE` mirrors `CONDITIONAL`'s programmatic-only detection (registry `choice`
# node presence). `ON_DAMAGED_TRIGGER`/`ON_ATTACH_TRIGGER` do have real drafted regexes.
_COMPANION_FLAGS: dict[str, TagSpec] = {
    "MULTI_CHOICE": TagSpec("MULTI_CHOICE", "boolean", r"(?!)", None),  # never text-detected, per spec
    "ON_DAMAGED_TRIGGER": TagSpec("ON_DAMAGED_TRIGGER", "boolean",
        r"is in the Active Spot and is damaged by an attack from your opponent's Pok[eé]mon", None),
    "ON_ATTACH_TRIGGER": TagSpec("ON_ATTACH_TRIGGER", "boolean",
        r"when you attach this card from your hand to", None),
}

TAG_CATALOG: dict[str, TagSpec] = {
    **{name: POKEMON_TAG_CATALOG[name] for name in _SHARED_TAG_NAMES},
    **_NEW_TAGS,
    "CONDITIONAL": POKEMON_TAG_CATALOG["CONDITIONAL"],
    **_COMPANION_FLAGS,
}

assert len(TAG_CATALOG) == 43, (
    f"expected 39 content tags + CONDITIONAL + 3 companion flags = 43, got {len(TAG_CATALOG)}"
)
CONTENT_TAGS = tuple(
    name for name in TAG_CATALOG
    if name not in ("CONDITIONAL", "MULTI_CHOICE", "ON_DAMAGED_TRIGGER", "ON_ATTACH_TRIGGER")
)
assert len(CONTENT_TAGS) == 39, f"expected 39 content tags, got {len(CONTENT_TAGS)}"

TAG_BLOCK_WIDTH = 39 + 6 + 1 + 1 + 1 + 6  # content + companion flags + qualifiers = 54

_SCOPE_VALUES = ("self", "own_bench", "own_team", "opponent_named_subset", "both_sides", "other")


def tag_unseen_trainer_energy(text: str) -> list[float]:
    """Deliverable B -- the regex-based fallback parser for any Trainer/Energy card outside
    the 117-card meta vocabulary. One text block per card (no attack/ability split, no
    `energy_cost` append -- those are Pokemon-specific, spec 11a's own scope).

    Layout: 39 content-tag scalars (`CONTENT_TAGS` order) + `CONDITIONAL` presence +
    `voluntary_cost` + `near_always_true` (always 0.0 here, never text-detected) +
    `MULTI_CHOICE` (always 0.0, same reason) + `ON_DAMAGED_TRIGGER` + `ON_ATTACH_TRIGGER`
    (both real regexes) + distribution + conserved (always 0.0, not text-derivable, same
    limitation as spec 11a) + self_referential (always 0.0 -- `SELF_SWITCH` in Trainer
    context never has an "itself" to reference, per spec 11b's own Phase 4 note) +
    scope-onehot(6).
    """
    from .pokemon_tag_catalog import normalize_apostrophes

    normalized = normalize_apostrophes(text)
    vec = [0.0] * len(CONTENT_TAGS)
    distribution = 0.0
    scope_onehot = [0.0] * 6
    any_scoped_tag_present = False

    for name in CONTENT_TAGS:
        spec = TAG_CATALOG[name]
        match = re.search(spec.regex, normalized, re.IGNORECASE)
        if match is None:
            continue
        idx = CONTENT_TAGS.index(name)
        raw = match.group(spec.capture_group) if spec.capture_group is not None else None
        magnitude = None
        if raw is not None:
            if name == "SEARCH_BENCH" and raw == "any":
                # Unquantified "any number of Basic Pokemon" -- user's explicit call:
                # treat as a representative 5, not the usual at-cap sentinel. See
                # pokemon_tag_catalog.py's own SEARCH_BENCH comment for the full rationale.
                magnitude = 5.0
            else:
                try:
                    magnitude = float(raw)
                except (TypeError, ValueError):
                    magnitude = None
        vec[idx] = _normalize(magnitude, spec.magnitude_family)
        if "distribution" in spec.qualifiers and DISTRIBUTION_RE.search(normalized):
            distribution = 1.0
        if "scope" in spec.qualifiers:
            any_scoped_tag_present = True
            scope_onehot = [0.0] * 6
            scope_onehot[_SCOPE_VALUES.index(_detect_scope(normalized))] = 1.0

    on_damaged = 1.0 if re.search(TAG_CATALOG["ON_DAMAGED_TRIGGER"].regex, normalized, re.IGNORECASE) else 0.0
    on_attach = 1.0 if re.search(TAG_CATALOG["ON_ATTACH_TRIGGER"].regex, normalized, re.IGNORECASE) else 0.0

    result = list(vec)
    result.append(0.0)  # CONDITIONAL presence -- never text-detected
    result.append(0.0)  # CONDITIONAL.voluntary_cost
    result.append(0.0)  # CONDITIONAL.near_always_true
    result.append(0.0)  # MULTI_CHOICE -- never text-detected, registry `choice` node only
    result.append(on_damaged)
    result.append(on_attach)
    result.append(distribution)
    result.append(0.0)  # conserved -- not text-derivable, same limitation as spec 11a
    result.append(0.0)  # self_referential -- always False in Trainer context
    result.extend(scope_onehot if any_scoped_tag_present else [0.0] * 6)
    return result
