"""Shared constants for the spec 13a observation encoder.

Values here are locked design decisions from
`Ceruledge-RL/specs/11-pokemon-word-observation-encoding.md` and
`Ceruledge-RL/specs/13a-observation-space-design.md`. Do not add new constants without a
corresponding spec update.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Type vocabulary (spec 11 base field schema)
# ---------------------------------------------------------------------------

# Full type one-hot: 10 dims, no Fairy. Bracket-letter codes match the engine/card-data
# convention (EN_Card_Data.csv, CardImpl.h text).
TYPES = ("Grass", "Fire", "Water", "Lightning", "Psychic", "Fighting", "Darkness", "Metal",
         "Dragon", "Colorless")
TYPE_LETTER = {
    "G": "Grass", "R": "Fire", "W": "Water", "L": "Lightning", "P": "Psychic",
    "F": "Fighting", "D": "Darkness", "M": "Metal", "N": "Dragon", "C": "Colorless",
}
TYPE_INDEX = {t: i for i, t in enumerate(TYPES)}

# Weakness/resistance one-hot: 9 dims, no Fairy, no Dragon (nothing is weak to or resists
# Dragon in the current format).
WR_TYPES = ("Grass", "Fire", "Water", "Lightning", "Psychic", "Fighting", "Darkness",
            "Metal", "Colorless")
WR_TYPE_INDEX = {t: i for i, t in enumerate(WR_TYPES)}

# attached_energy_counts bucket vocabulary: 11 dims (9 WR_TYPES-shaped buckets + Rainbow +
# Team Rocket Energy). Special Energy -> bucket mapping locked in spec 11.
ENERGY_BUCKETS = WR_TYPES + ("Rainbow", "Team Rocket Energy")
ENERGY_BUCKET_INDEX = {b: i for i, b in enumerate(ENERGY_BUCKETS)}

# Card-name -> bucket for Special Energy cards with a fixed (non-context-dependent) bucket.
# Prism Energy is handled separately (context-dependent on host evolution stage).
SPECIAL_ENERGY_FIXED_BUCKET = {
    "Ignition Energy": "Colorless",
    "Mist Energy": "Colorless",
    "Spiky Energy": "Colorless",
    "Enriching Energy": "Colorless",
    "Boomerang Energy": "Colorless",
    "Legacy Energy": "Rainbow",
    "Team Rocket's Energy": "Team Rocket Energy",
    "Telepath Psychic Energy": "Psychic",
    "Grow Grass Energy": "Grass",
    "Rock Fighting Energy": "Fighting",
}
PRISM_ENERGY_NAME = "Prism Energy"

# special_energy_id identity vocabulary (spec 14 amendment): one presence dim per meta
# Special Energy card. Order is arbitrary but must stay stable once trained against.
SPECIAL_ENERGY_IDS = (
    "Telepath Psychic Energy", "Grow Grass Energy", "Mist Energy", "Spiky Energy",
    "Enriching Energy", "Team Rocket's Energy", "Rock Fighting Energy", "Ignition Energy",
    "Prism Energy", "Legacy Energy",
)
SPECIAL_ENERGY_ID_INDEX = {n: i for i, n in enumerate(SPECIAL_ENERGY_IDS)}

# ---------------------------------------------------------------------------
# Rule status (spec 11 base field schema): 3-dim one-hot
# ---------------------------------------------------------------------------

RULE_STATUSES = ("none", "ex", "mega_ex")
RULE_STATUS_INDEX = {r: i for i, r in enumerate(RULE_STATUSES)}

# ---------------------------------------------------------------------------
# Special conditions (spec 11 base field schema): 5-dim multi-hot, active only
# ---------------------------------------------------------------------------

SPECIAL_CONDITIONS = ("Asleep", "Paralyzed", "Burned", "Poisoned", "Confused")

# ---------------------------------------------------------------------------
# Zone word budget (spec 13a) -- total must equal 174
# ---------------------------------------------------------------------------

DECK_CAPACITY = 47
PRIZE_CAPACITY = 6
HAND_CAPACITY = 20
DISCARD_CAPACITY = 40
BOARD_CAPACITY = 18  # (1 active + 8 max bench) x 2 sides
STADIUM_CAPACITY = 1
GLOBAL_CAPACITY = 1
POOL_CAPACITY = 1

TOTAL_WORDS = (
    DECK_CAPACITY + PRIZE_CAPACITY + HAND_CAPACITY + DISCARD_CAPACITY * 2 + BOARD_CAPACITY
    + STADIUM_CAPACITY + GLOBAL_CAPACITY + POOL_CAPACITY
)
assert TOTAL_WORDS == 174, f"word budget drifted from spec 13a: got {TOTAL_WORDS}"

MAX_BENCH = 8  # Area Zero Underdepths

# ---------------------------------------------------------------------------
# Null-like token kinds (spec 13a)
# ---------------------------------------------------------------------------

PAD = "PAD"  # no card here at all -- masked out of attention and pooling
UNK = "UNK"  # a real, currently-hidden card -- NOT masked

# ---------------------------------------------------------------------------
# Attack-row convention (spec 11a): single source of truth. Previously redeclared
# independently in static_template.py, Imitation-Learning/policy/packing.py, and
# Imitation-Learning/policy/model.py -- centralized here so a future change to this
# convention can't silently desync between them.
# ---------------------------------------------------------------------------

N_ATTACK_ROWS = 2  # cheapest-first, per the old encoding's convention (spec 02/03)

# ---------------------------------------------------------------------------
# Word-role vocabulary (spec 13a): single source of truth for the role strings
# `encoder.py`'s `BoardRole` Literal and zone assembly already use. Previously
# redeclared independently in Imitation-Learning/policy/packing.py, layout.py, and
# action_space.py -- centralized here for the same reason as N_ATTACK_ROWS above.
# ---------------------------------------------------------------------------

BOARD_ROLES = ("our_active", "our_bench", "opponent_active", "opponent_bench")
ZONE_ROLES = ("our_deck", "our_hand", "our_discard", "our_prizes", "opponent_discard")
