"""
attack_overrides.py — Hand-authored per-card tag overrides (tier 1 of spec 03).

Schema (specs/completed/03-attack-ability-tagging.md § Override table): OVERRIDES is keyed by
card_id; an entry may provide any subset of:

    "attacks":    list of dicts, one per attack in card_data.py's cheapest-first order.
                  Keys are effect_features.ATTACK_TAG_FIELDS (+ optionally "damage" /
                  "energy_cost"), RAW un-normalized values. A present "attacks" list
                  FULLY REPLACES keyword extraction for ALL of the card's attacks
                  (a missing key in a dict means 0 / card-data default, not tier 2).
    "ability":    dict with effect_features.ABILITY_TAG_FIELDS keys, raw values.
                  Fully replaces ability keyword extraction for the card.
    "virtual_attacks": list of complete aggregate attack dicts used in place of the
                  printed attacks (for copy-attack approximations such as N's Zoroark).
    "max_damage": int — overrides opp_active_max_damage for this card.
    "max_hp":     int — reviewed static HP correction consumed by features.py.

Sections not provided fall through to tier 2 (keyword extraction); e.g. an entry with
only "ability" still lets the attacks go through the keyword layer.

Raw units: snipe/counter_snipe/damage(ability)/heal in HP (counters already ×10);
recoil in self-damage HP; energy_accel/draws_cards/discard_energy/draw/energy_*/search
in counts; booleans 0/1.

Meta-relevant Pokemon worklist (grouped by deck archetype, by top human player) — the
groups below are the audit-pass worklist for future override entries:
    "Trevenant":     frozenset({878, 879, 304, 311, 1115}),
    "Alakazam":      frozenset({109, 741, 742, 743}),
    "Item Lock":     frozenset({235}),   # Budew (Itchy Pollen)
    "Dragapult":     frozenset({119, 120, 121}),
    "Lucario":       frozenset({333, 677, 974, 678, 673, 674}),
    "Mewtwo":        frozenset({431, 400, 401}),
    "Big Stage 1s":  frozenset({666}),   # plain Cinderace
    "Starmie":       frozenset({1030, 1031}),
    "Archaludon":    frozenset({169, 839, 992, 190, 57}),   # 57 = Relicanth
    "Festival Lead": frozenset({89, 90, 42, 92, 149, 346, 93, 100, 240}),
    "Crustle":       frozenset({345, 533, 344, 532}),
    "Garchomp":      frozenset({379, 380, 381, 342, 341, 387}),
    "Lopunny":       frozenset({758, 848, 849}),
    "Honchkrow":     frozenset({463, 891, 473, 474}),
    "Grimmsnarl":    frozenset({646, 647, 648}),
    "Iono's":        frozenset({265, 268, 269, 270, 271}),
    "Stall":         frozenset({117, 386}),   # Cornerstone (Mask) Ogerpon ex/non-ex
    "Cubchoo":       frozenset({506}),
    "Deck out":      frozenset({97, 493, 494, 98, 495, 164}),  # Litwick/Lampent/Chandelure + Comfey
    "Barbaracle":    frozenset({1052, 1051, 116, 890}),
    "Mega Abomasnow": frozenset({418, 722, 723}),
    "N's Zoroark":   frozenset({292, 293}),
"""
from __future__ import annotations

# Card ids referenced by the global item_locked flag (spec 02) — resolved from
# EN_Card_Data.csv, not guessed.
BUDEW = 235          # Itchy Pollen
FRILLISH = 597       # Oceanic Gloom (identical item-lock effect)
TYRANITAR = 290      # Daunting Gaze — continuous item lock while active (global check)

ITEM_LOCK_ATTACKERS = frozenset({BUDEW, FRILLISH})

# Seed entries per spec 03 (§ Seed entries). All ids resolved from EN_Card_Data.csv.
OVERRIDES: dict[int, dict] = {
    # -- item lock attacks --------------------------------------------------------
    BUDEW:    {"attacks": [{"item_lock": 1}]},
    FRILLISH: {"attacks": [{"item_lock": 1}]},
    # Tyranitar (290): continuous item lock handled by the global item_locked flag
    # (active check); its attack tags go through tier 2 (Cracking Stomp -> deckout).

    # -- attack lock --------------------------------------------------------------
    506: {"attacks": [{"cubchoo": 1}]},                       # Cubchoo — Snotted Up

    # -- deck-out line: mark the whole line as mill strategy ----------------------
    # Litwick 97 (TWM): Call for Family / Live Coal
    97:  {"attacks": [{"deckout": 1}, {"deckout": 1}]},
    # Litwick 493 (WHT): Brighten and Burn
    493: {"attacks": [{"deckout": 1, "probabilistic": 1}]},
    # Lampent 494 (WHT): Fire Blast
    494: {"attacks": [{"deckout": 1, "discard_energy": 1}]},
    # Chandelure 98 (TWM): Alluring Light ability (each player draws) + Mind Ruler
    98:  {"attacks": [{"deckout": 1}],
          "ability": {"mill": 1, "draw": 1}},
    # Chandelure 495 (WHT): Incendiary Pillar / Burn It All Up
    495: {"attacks": [{"deckout": 1},
                      {"deckout": 1, "discard_energy": 2}]},
    # Comfey 164: Flower Shower / Play Rough
    164: {"attacks": [{"deckout": 1, "draws_cards": 3},
                      {"probabilistic": 1}]},

    # -- probabilistic without coin-flip text -------------------------------------
    # Mega Abomasnow ex 723: Hammer-lanche (top-6 self-discard scaling) / Frost Barrier
    723: {"attacks": [{"probabilistic": 1}, {}], "max_damage": 600},

    # -- Munkidori 112: Adrena-Brain moves up to 3 counters our->their side -------
    112: {"ability": {"heal": 30, "damage": 30}},

    # -- IMMUNITY -----------------------------------------------------------------
    345: {"ability": {"immunity": 1}},   # Crustle (DRI) — Mysterious Rock Inn
    533: {"ability": {"immunity": 1}},   # Crustle (BLK) — Sturdy
    330: {"ability": {"immunity": 1}},   # Sylveon (PRE) — Safeguard
    117: {"ability": {"immunity": 1}},   # Cornerstone Mask Ogerpon ex — Cornerstone Stance

    # -- BARRIER ------------------------------------------------------------------
    343: {"ability": {"barrier": 1}},    # Shaymin (DRI) — Flower Curtain
    74:  {"ability": {"barrier": 1}},    # Rabsca — Spherical Shield
    858: {"ability": {"barrier": 1}},    # Psyduck — Damp
    626: {"ability": {"barrier": 1}},    # Patrat (per spec seed)

    # -- GUST ---------------------------------------------------------------------
    674: {"attacks": [{"recoil": 70}],
          "ability": {"gust": 1}},       # Hariyama — Wild Press / Heave-Ho Catcher
    310: {"ability": {"gust": 1}, "max_damage": 170},

    # User-reviewed matchup corrections. Hop's Snorlax can contribute three
    # non-stacking +30 boosts in the target deck, so all Hop Pokemon get +90.
    878: {"attacks": [{"probabilistic": 1, "immunity": 1}], "max_damage": 100},
    879: {"attacks": [{"revenge": 1}, {"retreat_lock": 1}], "max_damage": 180},
    304: {"attacks": [{"recoil": 80}], "max_damage": 230},
    307: {"max_damage": 110},
    308: {"max_damage": 170},
    309: {"max_damage": 140},
    311: {"attacks": [{"conditional": 1}], "max_damage": 210},

    # Remove misleading keyword hits or add explicit card semantics.
    743: {"attacks": [{}]},
    333: {"max_damage": 30},
    431: {"max_damage": 280},
    401: {"max_damage": 180},
    169: {"max_damage": 30},
    839: {"attacks": [{}]},
    190: {"attacks": [{"outrage": 1}]},
    92:  {"max_damage": 30},
    93:  {"max_damage": 340},
    240: {"max_damage": 260},
    849: {"attacks": [{"conditional": 1}, {}], "max_damage": 230},
    891: {"max_damage": 360},
    648: {"ability": {"search": 5, "energy_active": 5, "energy_bench": 5}},
    270: {"max_damage": 30},
    116: {"max_hp": 230, "max_damage": 170},
    293: {
        "virtual_attacks": [
            {"energy_cost": 2, "damage": 250, "cooldown": 1},
            {"energy_cost": 2, "damage": 90, "snipe": 90, "discard_energy": 2},
        ],
        "max_damage": 290,
    },
}


def get_override(card_id) -> dict | None:
    """Tier-1 lookup. A non-None result replaces keyword extraction for the sections
    it provides ("attacks" / "ability" / "max_damage"); missing sections fall through
    to tier 2."""
    if card_id is None:
        return None
    return OVERRIDES.get(int(card_id))
