"""
Heuristic weights for the Clefable MCTS Agent.

Every numerical constant used in heuristic_score() lives here so the
evolutionary tuner can treat the full set as a flat parameter vector.

Naming convention:  W_<heuristic-id>_<brief-description>

NOT tuned here:
  HEURISTIC_NORM  — kept fixed to avoid scale-ambiguity with all other weights.
  Game-mechanic constants (attack damage formula: 120 + 40×psychic, cap 4).
"""

# ── Score normalisation (fixed, not tuned) ────────────────────────────────────
HEURISTIC_NORM = 40.0

# ── H1: Attacker-count bonuses ────────────────────────────────────────────────
W_ATTACKER_1 = 2.0    # 1st Clefairy/Clefable in play
W_ATTACKER_2 = 1.5    # 2nd
W_ATTACKER_3 = 1.0    # 3rd

# ── H2: Dunsparce bench-setter ────────────────────────────────────────────────
W_DUNSPARCE        =  1.0   # per Dunsparce in play
W_DUNSPARCE_ENERGY = -1.0   # per energy on Dunsparce (wasted attach)

# ── H4: Mega Clefable ex presence ────────────────────────────────────────────
W_MEGA_CLEFABLE_EX = 2.5    # per Mega Clefable ex (capped at 2 copies)

# ── H5: Dudunsparce in hand, ready to evolve ─────────────────────────────────
W_DUDUNSPARCE_HAND = 0.5    # per Dudunsparce (capped by Dunsparce count in play)

# ── H6: Poke Pad in hand ─────────────────────────────────────────────────────
W_POKE_PAD_HAND = 0.3

# ── H7 & H8: Smoochum setup bonuses ─────────────────────────────────────────
W_SMOOCHUM_ACTIVE =  3.0    # H7: Smoochum active + bare bench attacker + low energy
W_SMOOCHUM_PLAY   =  1.0    # H8: any Smoochum in play when resources are scarce

# ── H9: Energy distribution across attackers ─────────────────────────────────
W_E_A1_E1  =  2.0   # 1st-most-loaded attacker, 1st energy
W_E_A1_E2  =  3.0   # 1st attacker, 2nd energy (attack-ready threshold)
W_E_A2_E1  =  2.0   # 2nd attacker, 1st energy
W_E_A2_E2  =  1.0   # 2nd attacker, 2nd energy
W_E_EXCESS = -1.0   # each energy beyond the above table entries

# ── H10: Active / bench Clefable position + Hero's Cape ──────────────────────
W_ACTIVE_CLEFABLE_E0   = -5.0  # active with 0 energy = dead weight
W_ACTIVE_CLEFABLE_E1   =  3.0  # active with 1 energy = one attach away
W_ACTIVE_CLEFABLE_E2   =  5.0  # active with ≥2 energy = ready to attack
W_ACTIVE_CLEFABLE_CAPE =  2.0  # bonus: active Clefable has cape + ≥1 energy
W_ACTIVE_CLEFAIRY_CAPE =  0.5  # Clefairy active with cape
W_ACTIVE_NONA_CAPE     = -3.0  # non-attacker active with cape (wasted)
W_BENCH_CLEFABLE_CAPE  =  1.0  # bench Clefable: cape + ≥1 energy
W_BENCH_CLEFAIRY_CAPE  =  0.5  # bench Clefairy with cape
W_BENCH_NONA_CAPE      = -3.0  # bench non-attacker with cape (wasted)

# ── H11: Attack damage potential ─────────────────────────────────────────────
W_ONE_ENERGY_AWAY      =  1.0  # active Clefable: 1 energy + psychic in hand
W_BENCH_ATTACKER_READY =  1.0  # bench Clefable: ≥1 energy + psychic in hand
W_KO_FLAT              =  7.0  # flat reward for being able to KO opponent active
W_KO_PER_PRIZE         =  2.0  # extra per prize card the KO target is worth

# ── H12: Cannot-attack energy accounting ─────────────────────────────────────
W_WASTED_ENERGY = -1.0   # per energy on non-attacking active Pokémon
W_BENCH_ENERGY  =  1.0   # per energy building on a bench attacker

# ── H13: Prize differential ──────────────────────────────────────────────────
W_PRIZE_DIFF = 15.0      # multiplied by (their_prizes − our_prizes)

# ── H14: Damage progress toward 2-shot ───────────────────────────────────────
W_DMG_PROGRESS = 5.0     # per 100 combined damage (attack + existing on target)

# ── H15: Attacking with unplayed trainers in hand ────────────────────────────
W_ATTACK_WITH_TRAINERS = -1.0

# ── H17: Psychic Energy in hand ──────────────────────────────────────────────
W_PSYCHIC_IN_HAND = 0.5   # per Psychic Energy card

# ── H18: Opponent energy in play ─────────────────────────────────────────────
W_OPP_ENERGY_IN_PLAY = -1.0  # per energy on any opponent Pokémon

# ── H19: Non-attacker active when opponent has 1 prize left ──────────────────
W_NONATT_ACTIVE_LATE = -10.0

# ── H20: Damage taken by our Clefairy / Mega Clefable ex ────────────────────
W_ATTACKER_DAMAGE = -0.2  # per 10-damage counter on our attackers

# ── H21: Deck thinning penalty ───────────────────────────────────────────────
W_DECK_LOW_PENALTY  = 1.0  # × (10 − deck_count) when deck < 10
W_DECK_CRIT_PENALTY = 2.0  # replaces above when deck_count < 3

# ── H22: Hand-size bonus ─────────────────────────────────────────────────────
W_HAND_TIER1 = 0.9   # per card in hand, cards 1–10
W_HAND_TIER2 = 0.4   # per card in hand, cards 11–20 (capped at 20)

# ── P2: Recovery card bonuses ────────────────────────────────────────────────
W_NIGHT_STRETCHER_LIVE  = 0.5   # Night Stretcher in hand + attacker in discard
W_ENERGY_RETRIEVAL_LIVE = 0.5   # Energy Retrieval in hand + Psychic in discard
W_DAWN_LIVE             = 0.5   # Dawn in hand + ≥2 Psychic in discard

# ── P3: Opponent bench pressure ──────────────────────────────────────────────
W_OPP_BENCH_PENALTY = 0.5   # per opponent benched Pokémon

# ── P4: Prize lead + attack-ready momentum ───────────────────────────────────
W_PRIZE_LEAD_MOMENTUM = 2.0

# ── P5: Dunsparce + Dudunsparce engine complete ──────────────────────────────
W_ENGINE_COMPLETE = 1.0
