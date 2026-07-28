"""Ordered frozen-feature vocabularies reported by the implementation handoff."""

from __future__ import annotations

CARD_TYPES = (
    "POKEMON",
    "ITEM",
    "TOOL",
    "SUPPORTER",
    "STADIUM",
    "BASIC_ENERGY",
    "SPECIAL_ENERGY",
)

ENERGY_TYPES = (
    "COLORLESS",
    "GRASS",
    "FIRE",
    "WATER",
    "LIGHTNING",
    "PSYCHIC",
    "FIGHTING",
    "DARKNESS",
    "METAL",
    "DRAGON",
    "RAINBOW",
    "TEAM_ROCKET",
)

SCOPES = ("self", "single", "all_bench", "any")

EFFECT_TAGS = (
    "src_ability",
    "src_attack_effect",
    "draw",
    "draw_mag",
    "search_deck_to_hand",
    "search_deck_to_field",
    "recover_from_trash",
    "deck_peek_reorder",
    "energy_accel",
    "attach_from_trash",
    "energy_switch",
    "discard_opp_energy",
    "disrupt_opp_hand",
    "mill_opp",
    "mill_self",
    "gust",
    "switch_self",
    "heal",
    "heal_mag",
    "put_counters",
    "put_counters_mag",
    "self_damage",
    "bench_snipe",
    "multi_target",
    "dmg_scale_energy",
    "dmg_scale_coin",
    "dmg_scale_prize",
    "dmg_scale_other",
    "dmg_modify_dealt",
    "dmg_modify_dealt_mag",
    "dmg_modify_taken",
    "dmg_modify_taken_mag",
    "block_damage_all",
    "block_damage_ex",
    "block_damage_basic",
    "block_damage_ability",
    "block_damage_threshold",
    "block_threshold_mag",
    "block_effects",
    "status_inflict",
    "status_recover_immune",
    "lock_attack",
    "lock_retreat",
    "lock_hand_use",
    "lock_ability",
    "self_drawback",
    "prize_extra",
    "prize_deny",
    "ko_prize_modifier",
    "instant_ko_or_win",
    "coin_flip",
    "retreat_cost_mod",
    "attack_cost_mod",
    "evolve_support",
    "attack_from_bench",
    "misc_permanent",
)

CONDITION_TYPES = (
    "Always",
    "AnyTargetAfterEffect",
    "CountTarget",
    "CountTarget2",
    "CountTargetMeOrEnemy",
    "CompareCountTargetMeEnemy",
    "CountEnergy",
    "CountEnergyType",
    "CompareCountEnergyMeEnemy",
    "AttackEnergyExtra",
    "NotFullBench",
    "MyTurn",
    "Turn",
    "KoPreEnemyTurn",
    "KoPreEnemyTurnTeamRocket",
    "KoAttackDamagePreEnemyTurn",
    "KoAttackDamageEthanPreEnemyTurn",
    "KoAttackDamageHopPreEnemyTurn",
    "NoSameNameSkillThisTurn",
    "SameAttackPreMyTurn",
    "CoinHeadCount",
    "AttachActive",
    "MysteryGarden",
    "LoveBall",
)

CONDITION_SUBJECTS = (
    "IsAttachedEnergyType",
    "Supporter",
    "DamageCounter",
    "Poison",
    "Ex",
    "Name",
    "CardId",
    "BasicEnergy",
    "EnergyCard",
    "Tool",
    "Stadium",
    "Ability",
    "Evolve",
    "Bench",
    "Active",
    "Rocket",
    "Tera",
    "Ancient",
    "subj_other",
)

COMPARATORS = (
    "Equal",
    "GreaterEqual",
    "LessEqual",
    "NotEqual",
    "Greater",
    "Less",
)

STAT_LAYOUT = (
    ("card_type", 0, 7),
    ("flags", 7, 14),
    ("hp", 14, 15),
    ("energy_type", 15, 27),
    ("weakness", 27, 39),
    ("resistance", 39, 51),
    ("retreat", 51, 52),
    ("attack_0", 52, 65),
    ("attack_1", 65, 78),
    ("has_second_attack", 78, 79),
)

EFFECT_LAYOUT = (
    ("is_ability", 0, 1),
    ("present", 1, 2),
    ("damage", 2, 3),
    ("target_count", 3, 4),
    ("scope", 4, 8),
    ("cost_by_type", 8, 20),
    ("effect_tags", 20, 76),
    ("gated", 76, 77),
    ("cond_type", 77, 101),
    ("cond_subject", 101, 120),
    ("comparator", 120, 126),
    ("name_target", 126, 127),
    ("branch", 127, 128),
    ("fetch_count", 128, 129),
    ("play_cost", 129, 130),
)

assert len(CARD_TYPES) == 7
assert len(ENERGY_TYPES) == 12
assert len(SCOPES) == 4
assert len(EFFECT_TAGS) == 56
assert len(CONDITION_TYPES) == 24
assert len(CONDITION_SUBJECTS) == 19
assert len(COMPARATORS) == 6
assert STAT_LAYOUT[-1][-1] == 79
assert EFFECT_LAYOUT[-1][-1] == 130
