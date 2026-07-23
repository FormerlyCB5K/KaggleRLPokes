"""Spec 11a's Pokemon attack/ability tag catalog, transcribed into code.

Source: `Ceruledge-RL/specs/11a-pokemon-attribute-tag-vocabulary.md`'s "Tag catalog" table
(49 content tags + `CONDITIONAL`) and Phase 4's locked field list. This module owns Stage 0
(the catalog itself) and Stage 2 (`tag_unseen_pokemon`, the regex-based fallback parser for
any Pokemon outside the 115-card meta vocabulary).

**Apostrophe normalization.** Spec 11a's own Phase 2e audit found every regex here was
drafted with an ASCII `'?` for contractions, but real card text uses the Unicode right
single quote (U+2019) exclusively -- `'?` never matches it. Rather than rewrite 49 regexes
to use a `['’]` character class, `normalize_apostrophes` below converts input text to
the ASCII form before any matching happens, so the drafted patterns work as written.

**Two known small gaps found during transcription, not present in spec 11a's own Phase 4
list** (flagged per this project's no-silent-loss convention, not fixed by design change):
`RETREAT_COST_MOD` carries a real numeric magnitude (a retreat-cost delta) but Phase 4's
magnitude-family list never assigned it one -- classified here as its own family, `/4`
signed, matching `retreat_cost`'s own normalization elsewhere. And `CONDITION` /
`WEAKNESS_OVERRIDE` / `ENERGY_AMPLIFY` each capture a *categorical* value (which status
condition, which new weakness type, which energy type) that the locked 61/70-dim numeric
schema has no dedicated slot for at all -- treated as boolean presence here, the categorical
detail is lost from the numeric encoding (present only in spec 11a's own prose), consistent
with the tag block being a deliberately lossy fallback, not a lossless record.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

MagnitudeFamily = Literal["damage", "count", "hp", "multiplier", "retreat", "boolean"]

DAMAGE_CAP = 350.0
COUNT_CAP = 6.0
HP_CAP = 150.0
MULTIPLIER_CAP = 3.0
RETREAT_CAP = 4.0

CAPS: dict[MagnitudeFamily, float] = {
    "damage": DAMAGE_CAP, "count": COUNT_CAP, "hp": HP_CAP,
    "multiplier": MULTIPLIER_CAP, "retreat": RETREAT_CAP,
}

QualifierName = Literal["distribution", "conserved", "self_referential", "scope"]


@dataclass(frozen=True)
class TagSpec:
    name: str
    magnitude_family: MagnitudeFamily
    regex: str  # combined alternation, matches spec 11a's drafted pattern (apostrophe-normalized text expected)
    capture_group: int | None  # which regex group holds the magnitude, if any
    qualifiers: tuple[QualifierName, ...] = ()


def _normalize(magnitude: float | None, family: MagnitudeFamily) -> float:
    if magnitude is None:
        return 1.0 if family == "boolean" else 0.0
    if family == "boolean":
        return 1.0
    cap = CAPS[family]
    if family == "hp":  # signed -- HP_BUFF can be a debuff (negative)
        return max(-1.0, min(magnitude / cap, 1.0))
    if family == "retreat":  # signed -- RETREAT_COST_MOD can raise or lower cost
        return max(-1.0, min(magnitude / cap, 1.0))
    return min(magnitude / cap, 1.0)  # damage/count/multiplier are unsigned in this dataset


def normalize_apostrophes(text: str) -> str:
    """Real card text uses U+2019 exclusively; every regex below assumes ASCII."""
    return text.replace("’", "'")


# 49 content tags. Regexes copied directly from spec 11a's catalog (already Python-`re`
# compatible), combined into one alternation per tag where the spec drafted multiple.
TAG_CATALOG: dict[str, TagSpec] = {
    "DAMAGE": TagSpec("DAMAGE", "damage", r"(?:does|deals?)\s+(\d+)\s+damage", 1),
    "SNIPE": TagSpec("SNIPE", "damage",
        r"(\d+)\s+damage\s+to\s+1\s+of\s+your\s+opponent's\s+(?:Benched\s+)?Pok[eé]mon", 1,
        qualifiers=("distribution", "scope")),
    "IGNORES_WEAKNESS": TagSpec("IGNORES_WEAKNESS", "boolean",
        r"damage isn't affected by Weakness", None),
    "IGNORES_RESISTANCE": TagSpec("IGNORES_RESISTANCE", "boolean",
        r"damage isn't affected by (?:Weakness or )?Resistance", None),
    "IGNORES_ACTIVE_EFFECTS": TagSpec("IGNORES_ACTIVE_EFFECTS", "boolean",
        r"damage isn't affected by .*any effects on (?:your opponent's|your) Active Pok[eé]mon", None),
    "DAMAGE_IMMUNE_FROM": TagSpec("DAMAGE_IMMUNE_FROM", "boolean",
        r"prevent(?:s)? all damage (?:from (?:and effects of )?attacks.*?)?done to|prevent that damage",
        None, qualifiers=("scope",)),
    "EFFECT_IMMUNE": TagSpec("EFFECT_IMMUNE", "boolean",
        r"prevent(?:s)? all (?:damage from and )?effects of attacks|prevent all damage counters from being placed .+ by effects of attacks",
        None, qualifiers=("scope",)),
    "RECOIL": TagSpec("RECOIL", "damage", r"also does (\d+) damage to itself", 1),
    "DRAW": TagSpec("DRAW", "count",
        r"draw (\d+) cards?|draws? \d+ cards?|draw a card|draw cards until", 1),
    "SELF_SWITCH": TagSpec("SELF_SWITCH", "boolean",
        r"switch this Pok[eé]mon with 1 of your Benched Pok[eé]mon|you may switch 1 of your Benched .+ with your Active Pok[eé]mon|switch (?:your|their) Active .*Pok[eé]mon with 1 of (?:your|their) Benched .*Pok[eé]mon",
        None, qualifiers=("self_referential",)),
    "SELF_MILL": TagSpec("SELF_MILL", "boolean",
        r"shuffle (?:this Pok[eé]mon|it) (?:and all attached cards )?into your deck", None),
    "COUNTER_PLACE": TagSpec("COUNTER_PLACE", "count",
        # Single shared capture group across both verbs -- found during the Trainer/Energy
        # pass (Perilous Jungle, spec 11b's own non-meta spot-check): the old two-group form
        # (`place (\d+)...|put (\d+)...`, capture_group=1) silently lost the real count
        # whenever the "put" branch matched, since group 1 belongs to "place" and group 2 to
        # "put" -- capture_group=1 always read the wrong (unpopulated) group for the far more
        # common "put" phrasing, falling back to boolean presence instead of the real number.
        # Also widened to accept "N *more* damage counters" (a recurring-trigger phrasing
        # Perilous Jungle uses that the original pattern didn't allow for either verb).
        r"(?:place|put) (\d+)(?: more)? damage counters? on", 1,
        qualifiers=("distribution", "scope")),
    "COUNTER_MOVE": TagSpec("COUNTER_MOVE", "count",
        r"move (?:up to )?(\d+|any number of|all) damage counters? (?:from|on) .+ to", 1,
        qualifiers=("conserved", "distribution")),
    "CONDITION": TagSpec("CONDITION", "boolean",
        r"(?:is now|becomes)\s+(Confused|Asleep|Paralyzed|Poisoned|Burned)|[Mm]ake (?:your opponent's|your) Active Pok[eé]mon (Confused|Asleep|Paralyzed|Poisoned|Burned)",
        None),
    "EVOLVE_SEARCH": TagSpec("EVOLVE_SEARCH", "boolean",
        r"search (?:your|their) deck for .*evolves from (?:this|that|1 of (?:your|their)) .*Pok[eé]mon", None),
    "SEARCH_ATTACH": TagSpec("SEARCH_ATTACH", "count",
        r"search (?:your|their) deck for .*attach|reveal them,? and put 1 of them into (?:your|their) hand\.\s*Attach the other|look at the top \d+ cards? of (?:your|their) deck and attach",
        None, qualifiers=("distribution",)),
    "HEAL": TagSpec("HEAL", "count", r"heal (\d+|all) damage", 1),
    "RNG_SCALING_DAMAGE": TagSpec("RNG_SCALING_DAMAGE", "damage",
        r"flip a coin until you get tails.*more damage for each heads", None),
    "CONDITIONAL": TagSpec("CONDITIONAL", "boolean", r"(?!)", None),  # never text-detected, per spec
    "COIN_FLIP_DAMAGE": TagSpec("COIN_FLIP_DAMAGE", "damage",
        r"flip a coin\.?\s*if heads,?\s*this attack does (\d+) more damage", 1),
    "ENERGY_ACCEL": TagSpec("ENERGY_ACCEL", "count",
        r"attach .*Energy card(?:s)? from (?:your|their) discard pile|attach a Basic .*Energy card from (?:your|their) hand",
        None, qualifiers=("distribution",)),
    "SEARCH_HAND": TagSpec("SEARCH_HAND", "count",
        r"search (?:your|their) deck for .*put (?:it|them|1 of them) into (?:your|their) hand", None),
    "REVEAL_DIG": TagSpec("REVEAL_DIG", "count",
        r"look at the (?:top|bottom) (\d+) cards? of (?:your|their) deck", 1),
    "STAT_BUFF": TagSpec("STAT_BUFF", "damage",
        r"attacks used by .+ do (\d+) more damage|the attacks it uses do (\d+) more damage", 1,
        qualifiers=("scope",)),
    "DISCARD_SELF": TagSpec("DISCARD_SELF", "count",
        r"discard\b(?!\s+the\s+top).{0,40}?(?:Energy|cards?)\b.{0,20}?\bfrom\b.{0,20}?(?:this Pok[eé]mon|your (?:Benched )?Pok[eé]mon|your hand)|discard (?:a card from|your hand)|may discard|each player discards cards from their hand until they have (\d+) cards",
        None),
    "ITEM_LOCK": TagSpec("ITEM_LOCK", "boolean",
        r"(?:they|your opponent) can't play any Item cards? from (?:their|your opponent's) hand", None),
    "SETUP_ALT_PLACEMENT": TagSpec("SETUP_ALT_PLACEMENT", "boolean",
        r"if this Pok[eé]mon is in your hand when you are setting up to play, you may put it face down in the Active Spot",
        None),
    "REVIVE_FROM_DISCARD": TagSpec("REVIVE_FROM_DISCARD", "count",
        r"put up to (\d+) .+ from your discard pile onto your Bench", 1),
    "SELF_KO": TagSpec("SELF_KO", "boolean",
        r"if you use this Ability,? this Pok[eé]mon is Knocked Out", None),
    "DOUBLE_ATTACK": TagSpec("DOUBLE_ATTACK", "boolean", r"may use an attack it has twice", None),
    "RETREAT_LOCK": TagSpec("RETREAT_LOCK", "boolean", r"the Defending Pok[eé]mon can't retreat", None),
    "ATTACK_LOCK": TagSpec("ATTACK_LOCK", "boolean", r"the Defending Pok[eé]mon can't use attacks", None),
    "SELF_NO_WEAKNESS": TagSpec("SELF_NO_WEAKNESS", "boolean", r"this Pok[eé]mon has no Weakness", None),
    "SELF_RETURN_TO_HAND": TagSpec("SELF_RETURN_TO_HAND", "boolean",
        r"put this Pok[eé]mon and all attached cards into your hand", None),
    "COOLDOWN": TagSpec("COOLDOWN", "boolean", r"this Pok[eé]mon can't use (?:\S.+|attacks)", None),
    "MILL": TagSpec("MILL", "count", r"discard the top (\d+)? ?cards? of your opponent's deck", 1),
    "EXTRA_PRIZE": TagSpec("EXTRA_PRIZE", "count", r"take (\d+) more Prize cards?", 1),
    "RETREAT_COST_MOD": TagSpec("RETREAT_COST_MOD", "retreat",
        r"no Retreat Cost|Retreat Cost is (?:\{C\})+ (?:less|more)|Retreat Cost of .+ is (?:\{C\})+ (?:less|more)",
        None, qualifiers=("scope",)),
    "ATTACK_INHERIT": TagSpec("ATTACK_INHERIT", "boolean",
        r"can use any attack from its previous Evolutions", None, qualifiers=("scope",)),
    "WEAKNESS_OVERRIDE": TagSpec("WEAKNESS_OVERRIDE", "boolean",
        r"[Tt]he Weakness of (.+?) is now \{(\w)\}", None),
    "STADIUM_REMOVE": TagSpec("STADIUM_REMOVE", "boolean", r"discard that Stadium", None),
    "ATTACK_DISABLE": TagSpec("ATTACK_DISABLE", "boolean",
        r"[Cc]hoose 1 of your opponent's Active Pok[eé]mon's attacks.*can't use that attack", None),
    "HP_BUFF": TagSpec("HP_BUFF", "hp", r"(?:gets|get) ([+-]\d+) HP", 1),
    "SWITCH_FORCE": TagSpec("SWITCH_FORCE", "boolean",
        r"switch (?:out|in) (?:your opponent's|1 of your opponent's) .*(?:Active|Bench)", None),
    "DISCARD_OPP": TagSpec("DISCARD_OPP", "count",
        r"your opponent discards? (?:a card|cards?|\d+ cards?) from their hand|opponent discards first|each player (?:shuffles their hand into their deck|discards cards from their hand) until they have (\d+) cards|you discard .+ you find (?:there|in their hand)",
        None),
    "ENERGY_AMPLIFY": TagSpec("ENERGY_AMPLIFY", "multiplier",
        r"each (?:Basic )?\{?\w+\}? Energy attached to (.+?) provides \{(\w)\}\{\2\} Energy", None,
        qualifiers=("scope",)),
    "STAT_DEBUFF": TagSpec("STAT_DEBUFF", "damage",
        # Widened for spec 11b's own reuse (Antique Jaw Fossil, a non-meta Trainer Tool):
        # a Trainer card states the debuff directly ("your opponent's Active Pokemon do N
        # less damage") since there's no ability-holder's perspective to phrase it from,
        # unlike the original Pokemon-side "the Defending Pokemon" wording (Chikorita).
        r"attacks used by (?:the Defending Pok[eé]mon|your opponent's Active Pok[eé]mon) do (\d+) less damage",
        1, qualifiers=("scope",)),
    "ENERGY_RETURN_TO_DECK": TagSpec("ENERGY_RETURN_TO_DECK", "count",
        r"shuffle (\d+) Energy attached to this Pok[eé]mon into your deck", 1),
    "SEARCH_BENCH": TagSpec("SEARCH_BENCH", "count",
        # "any" alternative added for the unquantified "any number of Basic Pokemon"
        # phrasing (Precious Trolley, non-meta Item) -- captures the literal word "any"
        # into the same group as the digit case; the caller (`tag_unseen_*`) special-cases
        # `raw == "any"` to a magnitude of 5 rather than falling back to bare presence.
        r"search (?:your|their) deck for (?:up to )?(\d+|any) (?:number of )?Basic .*Pok[eé]mon.*put (?:it|them) onto (?:your|their) Bench",
        1),
    "COPY_ATTACK": TagSpec("COPY_ATTACK", "boolean",
        r"[Cc]hoose 1 of (?:your opponent's Active Tera Pok[eé]mon's|your Benched .+'s) attacks and use it as this attack",
        None),
}

assert len(TAG_CATALOG) == 50, f"expected 49 content tags + CONDITIONAL, got {len(TAG_CATALOG)}"
CONTENT_TAGS = tuple(name for name in TAG_CATALOG if name != "CONDITIONAL")
assert len(CONTENT_TAGS) == 49, f"expected 49 content tags, got {len(CONTENT_TAGS)}"


# ---------------------------------------------------------------------------
# Deliverable B -- the regex-based fallback parser for any non-meta Pokemon.
# ---------------------------------------------------------------------------

DISTRIBUTION_RE = re.compile(r"any way you like|any distribution", re.IGNORECASE)


def _detect_self_referential(text: str) -> bool:
    """SELF_SWITCH only. `True` (holder swaps itself) is the pattern that names "this
    Pokemon" as the one moving; `False` (free-choice) is the reverse-order phrasing that
    doesn't."""
    if re.search(r"switch this Pok[eé]mon with 1 of your Benched Pok[eé]mon", text, re.IGNORECASE):
        return True
    return False  # the free-choice pattern matched instead, or ambiguous -- default per spec's stated common case is True, but an explicit free-choice match overrides it


_ADDITIVE_SNIPE_RE = re.compile(
    r"also\s+(?:does|deals?)\s+\d+\s+damage\s+to\s+1\s+of\s+your\s+opponent's\s+(?:Benched\s+)?Pok[eé]mon",
    re.IGNORECASE,
)


def _classify_snipe(text: str) -> str:
    """`DAMAGE` and `SNIPE` must stay independent numbers (see pokemon_meta_tags.py's module
    docstring for the Darmanitan/Fezandipiti distinction this implements): a `SNIPE` clause is
    either "additive" (a separate bonus hit to a Benched Pokemon on top of the attack's own
    base active damage -- "...also does N damage to 1 of your opponent's Benched Pokemon")
    or a "sole" redirect (the attack's *entire* damage is one freely-targetable hit -- "this
    attack does N damage to 1 of your opponent's Pokemon," no "also," no separate base).
    Returns "additive", "sole", or "absent" (no SNIPE clause at all)."""
    if not re.search(TAG_CATALOG["SNIPE"].regex, text, re.IGNORECASE):
        return "absent"
    return "additive" if _ADDITIVE_SNIPE_RE.search(text) else "sole"


def _detect_scope(text: str) -> str:
    """Lightweight heuristic, not a precise parser -- spec 11a's own qualifier prose is the
    authoritative record for known cards; this is only the unseen-card fallback's best
    guess. Order matters: check the more specific phrasings first."""
    lowered = text.lower()
    if "both" in lowered or "each player's" in lowered or "each player’s" in lowered:
        return "both_sides"
    if "your opponent's" in lowered or "opponent's" in lowered:
        return "opponent_named_subset"
    if "your benched" in lowered:
        return "own_bench"
    if "your pokémon in play" in lowered or "each of your" in lowered or "all of your" in lowered:
        return "own_team"
    return "self"


def tag_unseen_pokemon(
    attack_text: str,
    ability_text: str | None,
    printed_cost: str | None,
    printed_damage: float | None = None,
) -> tuple[list[float], list[float] | None]:
    """Returns (attack_vector, ability_vector). `ability_vector` is None if the card has no
    ability text. Each vector's layout: 49 content-tag scalars (CONTENT_TAGS order) +
    CONDITIONAL presence (always 0.0 here, per spec -- never text-detected) + 2 CONDITIONAL
    qualifier bits (always 0.0, same reason) + distribution + conserved + self_referential +
    scope-onehot(6) [+ energy_cost(9) for the attack vector only].

    `energy_cost` itself is out of this function's scope -- it's card-data-sourced, not
    text-detected (spec 11a's own "Energy cost" section); callers append it separately.

    `printed_damage` implements `DAMAGE`'s own documented default case ("or a bare printed
    damage value with no qualifying clause") -- many real attack rows carry a damage number
    with *no* prose describing it at all (the registry's `text` field only narrates
    non-damage effects; a "vanilla" attack, or one whose only notable text is a co-occurring
    non-damage effect like a repositioning switch, has an empty or damage-silent `text`).
    Skipping this fallback was a real, systemic bug caught during this transcription's own
    validation pass: 104 of 201 meta rows' `DAMAGE` tag failed pure text-regex recall before
    this was added, all traced to the same root cause, not 104 separate phrasing gaps.

    `DAMAGE` and `SNIPE` are independent numbers, never mirrored (see `_classify_snipe` and
    pokemon_meta_tags.py's module docstring): an "additive" SNIPE clause ("...also does N
    damage to 1 of your opponent's Benched Pokemon") means a separate bonus hit on top of the
    attack's own base active damage -- both tags fire with their own numbers, the base always
    sourced from `printed_damage` since the additive clause's own regex match would otherwise
    steal the bonus magnitude for `DAMAGE`. A "sole redirect" SNIPE clause ("this attack does
    N damage to 1 of your opponent's Pokemon," no "also") means the entire attack is one
    freely-targetable hit with no guaranteed-active number at all -- only `SNIPE` fires,
    `DAMAGE` stays `0.0`.
    """

    def build_content_vector(text: str, is_attack: bool) -> list[float]:
        normalized = normalize_apostrophes(text)
        vec = []
        distribution = 0.0
        conserved = 0.0
        self_referential = 0.0
        scope_onehot = [0.0] * 6  # self, own_bench, own_team, opponent_named_subset, both_sides, other
        scope_values = ("self", "own_bench", "own_team", "opponent_named_subset", "both_sides", "other")
        any_scoped_tag_present = False
        snipe_class = _classify_snipe(normalized)  # "additive" / "sole" / "absent"
        for name in CONTENT_TAGS:
            spec = TAG_CATALOG[name]
            if name == "DAMAGE":
                # DAMAGE and SNIPE must stay independent numbers (see pokemon_meta_tags.py's
                # module docstring) -- a SNIPE clause's own "does N damage" substring would
                # otherwise also satisfy DAMAGE's generic regex, either stealing the bonus
                # magnitude (additive case) or fabricating a guaranteed-active hit that isn't
                # one (sole-redirect case, e.g. Fezandipiti ex's "Cruel Arrow").
                if snipe_class == "sole":
                    vec.append(0.0)  # entire damage is one redirectable hit -- no separate active guarantee
                    continue
                if snipe_class == "additive":
                    # the only "does/deals N damage" text belongs to SNIPE's own bonus clause;
                    # the true active-guaranteed base is the card's own printed damage.
                    vec.append(_normalize(printed_damage, "damage") if is_attack and printed_damage else 0.0)
                    continue
            match = re.search(spec.regex, normalized, re.IGNORECASE)
            if match is None:
                if name == "DAMAGE" and is_attack and printed_damage:
                    vec.append(_normalize(printed_damage, "damage"))
                else:
                    vec.append(0.0)
                continue
            # Extract a magnitude if this catalog entry has a capture group AND the
            # specific alternation branch that actually matched populated it. Neither is
            # guaranteed: `capture_group=None` entries never try (multi-alternative regexes
            # with inconsistent group numbering); even a wired group can come back `None`
            # when a *different* alternative in the same pattern matched instead (e.g.
            # DRAW's numeric group is unset when the "draw a card" literal alternative is
            # what fired, not the "draw N cards" one).
            #
            # Two real, systemic bugs were caught this way during the non-meta spot-check
            # (Stage 3), both collapsing to the same root cause -- "matched but no magnitude"
            # was silently written as 0.0, indistinguishable from "tag absent": (1) 8 tags
            # with `capture_group=None` (SEARCH_ATTACH, RNG_SCALING_DAMAGE, ENERGY_ACCEL,
            # SEARCH_HAND, DISCARD_SELF, RETREAT_COST_MOD, DISCARD_OPP, ENERGY_AMPLIFY) --
            # e.g. Wiglett's clear "Search your deck for an Item card... put it into your
            # hand" matched `SEARCH_HAND` but showed 0.0; (2) `DRAW`'s own wired group 1
            # returning `None` for the "draw a card" alternative -- Meditite's "Draw a
            # card." matched but also showed 0.0. Both are the same fix: no usable
            # magnitude means treat the tag like a boolean (present, `1.0`), never 0.0.
            raw = match.group(spec.capture_group) if spec.capture_group is not None else None
            magnitude = None
            if raw is not None:
                if name == "SEARCH_BENCH" and raw == "any":
                    # Unquantified "any number of Basic Pokemon" (Precious Trolley) --
                    # user's explicit call: treat as a representative 5, not the usual
                    # at-or-above-cap sentinel other "any"/"all" cases get, since Bench
                    # capacity realistically bounds this well below the count family's cap.
                    magnitude = 5.0
                else:
                    try:
                        magnitude = float(raw)
                    except (TypeError, ValueError):
                        magnitude = None  # e.g. "all"/"any number of" -- treat as at-or-above-cap
            vec.append(1.0 if magnitude is None else _normalize(magnitude, spec.magnitude_family))
            if "distribution" in spec.qualifiers and DISTRIBUTION_RE.search(normalized):
                distribution = 1.0
            if "self_referential" in spec.qualifiers:
                self_referential = 1.0 if _detect_self_referential(normalized) else 0.0
            if "conserved" in spec.qualifiers:
                conserved = 0.0  # not text-derivable per spec 11a -- documented limitation, defaults to the more common net-transfer case
            if "scope" in spec.qualifiers:
                any_scoped_tag_present = True
                scope_onehot = [0.0] * 6
                scope_onehot[scope_values.index(_detect_scope(normalized))] = 1.0
        vec.append(0.0)  # CONDITIONAL presence -- never text-detected
        vec.append(0.0)  # CONDITIONAL.voluntary_cost
        vec.append(0.0)  # CONDITIONAL.near_always_true
        vec.append(distribution)
        vec.append(conserved)
        vec.append(self_referential)
        vec.extend(scope_onehot if any_scoped_tag_present else [0.0] * 6)
        return vec

    def append_energy_cost(vec: list[float]) -> list[float]:
        # energy_cost is card-data-sourced (printed_cost), not text-detected -- 9 dims,
        # zero here if printed_cost is unavailable; a real caller should fill this from
        # card_data.py the same way static_template.py does for HP/type/etc.
        return vec + [0.0] * 9

    attack_vec = append_energy_cost(build_content_vector(attack_text, is_attack=True))
    ability_vec = build_content_vector(ability_text, is_attack=False) if ability_text else None
    return attack_vec, ability_vec
