"""Build reviewed Spec-12b05 Pokemon audit batches."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
WORKLIST = PART_B / "audit-worklist.json"
BATCHES = PART_B / "audit-batch-manifest.json"
OUTPUT = PART_B / "pokemon-audit"
RECORDED_EVIDENCE = OUTPUT / "pokemon-01-recorded-engine-evidence.json"
HUMAN_REVIEW = PART_B / "human-review-ledger.json"
SCHEMA_VERSION = 1

ENGINE_REQUIREMENTS = {
    "card:343:ability:0": {"methods": ["targetBench", "targetNotRulePokemon"], "tokens": ["NoDamageEnemyAttack"]},
    "card:66:ability:0": {"methods": ["effectDraw", "effectMe", "effectShuffle"], "tokens": ["ToDeckWithAttach"]},
    "card:305:attack:0": {"methods": ["effectSwitch"], "tokens": []},
    "card:140:ability:0": {"methods": ["condition", "conditionNoSameNameSkillThisTurn", "effectDraw"], "tokens": ["KoPreEnemyTurn"]},
    "card:140:attack:0": {"methods": ["postEffectDamagePokemon"], "tokens": []},
    "card:741:attack:0": {"methods": ["effectSwitch"], "tokens": []},
    "card:742:ability:0": {"methods": ["abilityEvolve", "effectDraw"], "tokens": []},
    "card:743:ability:0": {"methods": ["abilityEvolve", "effectDraw"], "tokens": []},
    "card:743:attack:0": {"methods": ["targetHand", "targetActive"], "tokens": ["EffectDamageChangeTargetCount", "DamageCounter", "Enemy"]},
    "card:344:attack:0": {"methods": ["effectEvolvesToEach", "effectShuffle"], "tokens": ["SelectEvolvesFrom"]},
    "card:345:ability:0": {"methods": ["effectMe"], "tokens": ["NoDamageEnemyExAttack"]},
    "card:345:attack:0": {"methods": ["noTargetEffect"], "tokens": []},
    "card:756:ability:0": {"methods": ["activateSkillOnceTurnActive", "conditionNoSameNameSkillThisTurn", "effectDraw"], "tokens": []},
    "card:756:attack:0": {"methods": ["preEffect"], "tokens": ["AttackDamageChangeCoinUntilTail"]},
    "card:112:ability:0": {"methods": ["conditionAttachEnergyMe", "targetDamaged", "targetPokemon"], "tokens": ["RemoveDamageCounter", "DamageCounterRemoved", "Darkness", "Enemy"]},
    "card:112:attack:0": {"methods": ["postEffect"], "tokens": ["Confuse", "Enemy"]},
    "card:646:attack:0": {"methods": ["effectDraw"], "tokens": []},
    "card:648:ability:0": {"methods": ["abilityEvolve", "effectSelectAttachBasicEnergyDeck", "effectAttachFromEach", "effectShuffle"], "tokens": ["DARKNESS_ENERGY", "Marnie"]},
    "card:648:attack:0": {"methods": ["postEffectDamageBench"], "tokens": []},
    "card:414:ability:0": {"methods": ["targetBasicPokemon", "targetCondition"], "tokens": ["NoEffectEnemyAttack", "TeamRocket"]},
    "card:414:attack:0": {"methods": ["targetNameCondition", "preEffectAttackDamageChange"], "tokens": ["IsAttachedEnergyName"]},
    "card:104:ability:0": {"methods": ["trigger", "targetNotMyName"], "tokens": ["PokemonCheckup", "DamageCounter", "Both", "HasAbility"]},
    "card:235:attack:0": {"methods": ["postEffect"], "tokens": ["CannotPlayItemNextTurn", "Enemy"]},
    "card:1031:attack:0": {"methods": ["postEffectDamageBench"], "tokens": []},
    "card:1031:attack:1": {"methods": ["noTargetEffectAndWeakness"], "tokens": []},
}

ENGINE_REQUIREMENTS.update({
    "card:117:tera:0": {"methods": ["tera"], "tokens": []},
    "card:117:ability:0": {"methods": ["abilityBattleField", "effectMe"], "tokens": ["NoDamageEnemyAbilityPokemonAttack"]},
    "card:117:attack:0": {"methods": ["noTargetEffectAndWeakness"], "tokens": []},
    "card:400:attack:0": {"methods": ["postEffectDamageMe"], "tokens": []},
    "card:401:ability:0": {"methods": ["activateSkillOnceTurn", "effectTrashAttachEnergyMe", "targetBasicEnergy"], "tokens": []},
    "card:401:attack:0": {"methods": ["preEffect", "targetPokemon", "targetCondition"], "tokens": ["AttackDamageChangeTargetCount", "Me", "TargetType", "TeamRocket"]},
    "card:431:ability:0": {"methods": ["abilityBattleField", "conditionLess", "targetPokemon", "targetCondition", "effectMe"], "tokens": ["TargetType", "TeamRocket", "CannotAttack"]},
    "card:431:attack:0": {"methods": ["setPreEffect", "targetAttachedEnergy", "maxSelectEnergy", "canNoSelect", "effectEffectedCard", "eVal"], "tokens": ["AttachedBenchPokemon", "ToTrash", "Me", "AttackDamageChangeTargetCount"]},
    "card:434:attack:0": {"methods": ["asActiveEnemyTerastalPokemonAttack"], "tokens": []},
    "card:131:attack:0": {"methods": ["postEffect", "targetTrash", "targetMyName", "maxSelect"], "tokens": ["ToBench", "Me"]},
    "card:132:ability:0": {"methods": ["activateSkillOnceTurn", "effectKoMe", "effect", "targetPokemon", "singleSelect"], "tokens": ["DamageCounter", "Enemy"]},
    "card:133:ability:0": {"methods": ["activateSkillOnceTurn", "effectKoMe", "effect", "targetPokemon", "singleSelect"], "tokens": ["DamageCounter", "Enemy"]},
    "card:133:attack:0": {"methods": ["postEffectActiveEnemy"], "tokens": ["CannotRetreatNextTurn"]},
    "card:666:ability:0": {"methods": ["abilityBattleField", "toActiveOnlySetup"], "tokens": []},
    "card:666:attack:0": {"methods": ["setPostEffect", "effectDeckAttachEnergyBenchAndShuffle", "targetBasicEnergy"], "tokens": []},
    "card:689:attack:0": {"methods": ["postEffectActiveEnemy"], "tokens": ["CannotRetreatNextTurn"]},
    "card:342:ability:0": {"methods": ["abilityBattleField", "effect", "targetPokemon", "targetCondition"], "tokens": ["DamageChangeActive", "Me", "TargetType", "Cynthia"]},
    "card:379:attack:0": {"methods": ["noTargetResistance"], "tokens": []},
    "card:380:ability:0": {"methods": ["activateSkillOnceTurn", "effectDeckToHandAndShuffle", "targetCondition", "targetPokemonCard"], "tokens": ["TargetType", "Cynthia"]},
    "card:381:attack:0": {"methods": ["setPostEffect", "conditionLess", "targetHand", "postEffectSelectActivate", "effectDrawUntil"], "tokens": []},
    "card:381:attack:1": {"methods": ["postEffectTrashEnergyMeAll"], "tokens": []},
    "card:861:attack:0": {"methods": ["preEffect", "targetHand"], "tokens": ["AttackDamageChangeTargetCount", "Enemy"]},
    "card:861:attack:1": {"methods": ["postEffect"], "tokens": ["Sleep", "Enemy"]},
    "card:120:ability:0": {"methods": ["activateSkillOnceTurn", "effectLookAndToHandReverseRestDeckBottom"], "tokens": []},
    "card:121:tera:0": {"methods": ["tera"], "tokens": []},
    "card:121:attack:1": {"methods": ["postEffect", "targetBench"], "tokens": ["DamageCounterAny", "Enemy"]},
    "card:1071:ability:0": {"methods": ["abilityPlay", "conditionNoSameNameSkillThisTurn", "effectDeckToHandAndShuffle", "targetSupporter"], "tokens": []},
    "card:1071:attack:0": {"methods": ["postEffectMe"], "tokens": ["ToHandWithAttach"]},
})

ENGINE_REQUIREMENTS.update({
    "card:387:attack:0": {"methods": ["preEffect", "targetBench", "targetCondition", "noTargetWeaknessOnly"], "tokens": ["AttackDamageChangeDamageCounter", "Me", "TargetType", "Cynthia"]},
    "card:245:attack:0": {"methods": ["postEffect", "effect"], "tokens": ["Confuse", "Enemy", "DamageCounterSwitchAny"]},
    "card:245:attack:1": {"methods": ["preEffect", "targetActive"], "tokens": ["AttackDamageChangeEnergyCount", "Enemy"]},
    "card:92:attack:0": {"methods": ["setPreEffect", "effectBreakIfCoinTail", "preEffectAttackDamageChange"], "tokens": []},
    "card:93:ability:0": {"methods": ["abilityBattleField", "effectFestivalLead"], "tokens": []},
    "card:93:attack:0": {"methods": ["preEffect", "targetBench"], "tokens": ["AttackDamageChangeTargetCount", "Me"]},
    "card:90:ability:0": {"methods": ["activateSkillOnceTurn", "exist", "targetNameCondition", "effectDeckToHandReverseAndShuffle"], "tokens": ["TargetType", "HasAbilityName"]},
    "card:65:attack:1": {"methods": ["setPostEffect", "effectBreakIfCoinTail", "effectMe"], "tokens": ["NoDamageAndEffectAttackNextEnemyTurn"]},
    "card:247:ability:0": {"methods": ["abilityBattleField", "effectFestivalLead"], "tokens": []},
    "card:247:attack:0": {"methods": ["postEffect", "targetPokemon", "singleSelect"], "tokens": ["DamageCounter", "Enemy"]},
    "card:214:ability:0": {"methods": ["abilityBattleField", "trigger", "targetActive", "targetPlayer", "notStack", "effectBreakIfCoinTail", "effectTriggerSubject"], "tokens": ["TriggerType", "Ko", "Enemy", "KoPrizeChangeAlways"]},
    "card:169:attack:1": {"methods": ["preEffectMe"], "tokens": ["AttackDamageChangeDamageCounter"]},
    "card:190:ability:0": {"methods": ["abilityEvolve", "effectSelectAttachBasicEnergyTrash", "targetCardId", "effectAttachFromEach", "targetPokemon", "targetEnergyType"], "tokens": ["METAL_ENERGY", "EnergyType", "Metal"]},
    "card:190:attack:0": {"methods": ["postEffectMe"], "tokens": ["NoWeaknessNextEnemyTurn"]},
    "card:848:attack:0": {"methods": ["setPostEffect", "effectSwitch"], "tokens": ["Me"]},
    "card:849:attack:0": {"methods": ["setPreEffect", "exist", "targetCondition", "preEffectAttackDamageChange"], "tokens": ["TargetType", "BenchToActiveThisTurn"]},
    "card:849:attack:1": {"methods": ["noTargetEffect"], "tokens": []},
    "card:164:attack:0": {"methods": ["setPostEffect", "effectDraw", "effect"], "tokens": ["Draw", "Enemy"]},
    "card:164:attack:1": {"methods": ["setPreEffect", "effectBreakIfCoinTail", "preEffectAttackDamageChange"], "tokens": []},
    "card:817:attack:0": {"methods": ["postEffect", "targetPokemon", "singleSelect"], "tokens": ["DamageCounter", "Enemy"]},
    "card:818:ability:0": {"methods": ["abilityEvolve", "effect"], "tokens": ["Confuse", "Enemy"]},
    "card:791:attack:0": {"methods": ["setPreEffect", "exist", "targetCondition", "preEffectAttackDamageChange"], "tokens": ["TargetType", "Ex"]},
    "card:506:attack:0": {"methods": ["postEffectActiveEnemy"], "tokens": ["CannotAttackNextTurn"]},
    "card:184:ability:0": {"methods": ["abilityBattleField", "effectNoRetreatCost", "targetPokemon", "targetBasicPokemon"], "tokens": []},
    "card:184:attack:0": {"methods": ["postEffectMe"], "tokens": ["CannotAttackNextTurn"]},
})

ENGINE_REQUIREMENTS.update({
    "card:649:attack:0": {"methods": ["preEffectMe"], "tokens": ["AttackDamageChangeTypeEnergyCount"]},
    "card:432:attack:0": {"methods": ["setPostEffect", "existMyBench", "targetDamaged", "targetCondition", "targetBench", "targetActive"], "tokens": ["TeamRocket", "RemoveDamageCounterAll", "Me", "DamageCounterRemoved", "Enemy"]},
    "card:73:attack:0": {"methods": ["postEffectDamageMe"], "tokens": []},
    "card:74:ability:0": {"methods": ["abilityBattleField", "effect", "targetBench"], "tokens": ["NoDamageAndEffectEnemyAttack", "Me"]},
    "card:74:attack:0": {"methods": ["preEffect", "targetActive"], "tokens": ["AttackDamageChangeEnergyCount", "Enemy"]},
    "card:675:ability:0": {"methods": ["activateSkillOnceTurn", "existPokemon", "targetName", "conditionNoSameNameSkillThisTurn", "costHandTrashLimited", "targetCardId", "effectDraw"], "tokens": ["FIGHTING_ENERGY"]},
    "card:676:attack:0": {"methods": ["preEffectFailAttack", "existMyBench", "targetName", "noTargetWeaknessResistance"], "tokens": []},
    "card:678:attack:0": {"methods": ["setPostEffect", "effectSelectAttachBasicEnergyTrash", "targetCardId", "effectAttachFromEach", "targetBench"], "tokens": ["FIGHTING_ENERGY"]},
    "card:678:attack:1": {"methods": ["postEffectMe"], "tokens": ["CannotUseThisAttackNextTurn"]},
    "card:174:ability:0": {"methods": ["activateSkillFirstTurn", "conditionNoSameNameSkillThisTurn", "effectDeckToHandAndShuffle", "targetPokemonCard", "targetHpLessEqual", "targetEnergyType"], "tokens": ["EnergyType", "Colorless"]},
    "card:174:attack:0": {"methods": ["preEffectFailAttack", "existStadium"], "tokens": []},
    "card:272:ability:0": {"methods": ["abilityBattleField", "effect", "targetPokemon", "targetCondition"], "tokens": ["SetWeakness", "Enemy", "TargetType", "EnergyType"]},
    "card:272:attack:0": {"methods": ["preEffect", "targetBench"], "tokens": ["AttackDamageChangeTargetCount", "Both"]},
    "card:677:attack:0": {"methods": ["postEffectMe"], "tokens": ["CannotUseThisAttackNextTurn"]},
    "card:58:attack:0": {"methods": ["postEffectDeckToTrash", "exist", "targetSupporter", "targetCondition"], "tokens": ["TargetType", "Ancient"]},
    "card:109:ability:0": {"methods": ["activateSkillOnceTurnActive", "effectMe", "effectShuffle"], "tokens": ["ToDeckWithAttach"]},
    "card:57:ability:0": {"methods": ["abilityBattleField", "effect", "targetPokemon"], "tokens": ["CanUsePreEvolutionAttack", "Me"]},
    "card:607:attack:0": {"methods": ["setPreEffect", "condition", "preEffectAttackDamageChange"], "tokens": ["ConditionType", "KoAttackDamagePreEnemyTurn"]},
    "card:31:attack:0": {"methods": ["setPostEffect", "effectDraw"], "tokens": []},
    "card:31:attack:1": {"methods": ["setPreEffect", "existStadium", "preEffectAttackDamageChange", "setPostEffect", "effectTrashStadium"], "tokens": []},
    "card:306:attack:0": {"methods": ["preEffect", "targetPokemon", "targetCondition"], "tokens": ["AttackDamageChangeTargetCount", "Enemy", "TargetType", "Ex"]},
    "card:306:attack:1": {"methods": ["noTargetEffect"], "tokens": []},
    "card:122:ability:0": {"methods": ["activateSkillOnceTurnActive", "effectLookAndToHandRestDeckAndShuffle", "targetSupporter"], "tokens": []},
    "card:183:attack:0": {"methods": ["setPostEffect", "existMyBench", "effectSelectAttachEnergyDeck", "targetCardId", "targetBench", "singleSelect", "effectShuffle"], "tokens": ["PSYCHIC_ENERGY", "AttachSelectedCard", "Me"]},
    "card:597:attack:0": {"methods": ["postEffect"], "tokens": ["CannotPlayItemNextTurn", "Enemy"]},
    "card:745:attack:0": {"methods": ["setPostEffect", "effectDraw"], "tokens": []},
})

ENGINE_REQUIREMENTS.update({
    "card:63:attack:0": {"methods": ["setPostEffect", "targetHand", "effectDraw"], "tokens": ["AreaType", "Deck", "ToTrash", "Me"]},
    "card:63:attack:1": {"methods": ["targetAttachedEnergy", "targetBasicEnergy", "selectEnergyAny", "effectEffectedCard", "eVal"], "tokens": ["ToTrash", "Me", "AttackDamageChangeTargetCount"]},
    "card:96:tera:0": {"methods": ["tera"], "tokens": []},
    "card:96:ability:0": {"methods": ["activateSkillOnceTurn", "effectHandAttachEnergyMe", "targetCardId", "effectDraw"], "tokens": ["GRASS_ENERGY"]},
    "card:96:attack:0": {"methods": ["preEffect", "targetActive", "eVal"], "tokens": ["AttackDamageChangeEnergyCount", "Both"]},
    "card:108:tera:0": {"methods": ["tera"], "tokens": []},
    "card:108:attack:0": {"methods": ["postEffectActiveEnemy"], "tokens": ["CannotRetreatNextTurn"]},
    "card:108:attack:1": {"methods": ["setPostEffect", "postEffectSelectActivate", "targetAttachedEnergy", "selectEnergy", "postEffectDamageBench"], "tokens": ["ToDeckAndShuffle", "Me", "TargetType", "AttachedMe"]},
    "card:116:ability:0": {"methods": ["abilityBattleField", "conditionAttachEnergyMe", "effectMe", "eVal"], "tokens": ["Darkness", "MaxHpChange", "DamageChangeActive"]},
    "card:141:ability:0": {"methods": ["activateSkillOnceTurn", "conditionNoSameNameSkillThisTurn", "effectSwitch", "targetEnergyType", "targetNotMyName", "effect"], "tokens": ["Me", "EnergyType", "Darkness", "Poison"]},
    "card:141:attack:0": {"methods": ["preEffect", "eVal"], "tokens": ["AttackDamageChangeTakenPrize", "Enemy"]},
    "card:293:ability:0": {"methods": ["activateSkillOnceTurn", "costHandTrash", "effectDraw"], "tokens": []},
    "card:293:attack:0": {"methods": ["asMyBenchNPokemonAttack"], "tokens": []},
    "card:303:attack:0": {"methods": ["preEffectMe", "eVal"], "tokens": ["AttackDamageChangeDamageCounter"]},
    "card:463:attack:0": {"methods": ["setPostEffect", "effectDeckToHandAndShuffle", "targetSupporter"], "tokens": []},
    "card:463:attack:1": {"methods": ["postEffectActiveEnemy"], "tokens": ["CannotUseSelectedAttack"]},
    "card:473:attack:0": {"methods": ["setPostEffect", "targetHand", "singleSelect", "enemySelect"], "tokens": ["ToTrash", "Me", "Enemy"]},
    "card:474:attack:0": {"methods": ["preEffect", "eVal", "targetTrash", "targetSupporter", "targetNameContains"], "tokens": ["AttackDamageChangeTargetCount", "Me"]},
    "card:674:ability:0": {"methods": ["abilityEvolve", "effectSwitchEnemyBench"], "tokens": []},
    "card:674:attack:0": {"methods": ["postEffectDamageMe"], "tokens": []},
    "card:746:attack:0": {"methods": ["setPostEffect", "effectDeckToHandAndShuffle", "targetPokemonCard"], "tokens": []},
    "card:747:attack:0": {"methods": ["setPostEffect", "targetBench", "effectAttachToEach", "targetDeck", "targetCardId", "maxSelect", "effectShuffle"], "tokens": ["SelectAttachFrom", "Me", "PSYCHIC_ENERGY"]},
    "card:747:attack:1": {"methods": ["preEffect", "eVal", "targetPokemon"], "tokens": ["AttackDamageChangeTypeEnergyCount", "Me"]},
    "card:891:attack:0": {"methods": ["preEffect", "targetHand", "targetNameContains", "targetSupporter", "selectAny", "effectEffectedCard", "eVal"], "tokens": ["ToTrash", "Me", "AttackDamageChangeTargetCount"]},
    "card:906:attack:0": {"methods": ["noTargetEffect"], "tokens": []},
    "card:906:attack:1": {"methods": ["postEffectMe"], "tokens": ["CannotAttackNextTurn"]},
    "card:1051:attack:0": {"methods": ["setPostEffect", "effectDraw"], "tokens": []},
    "card:1052:ability:0": {"methods": ["activateSkillOnceTurn", "effectSelectAttachBasicEnergyHand", "targetCardId", "targetPokemon", "targetEnergyType", "singleSelect"], "tokens": ["FIGHTING_ENERGY", "AttachSelectedCard", "Me", "Fighting"]},
})

ENGINE_REQUIREMENTS.update({
    "card:42:attack:0": {"methods": ["setPostEffect", "effectDeckToHandAndShuffle", "targetPokemonCard"], "tokens": []},
    "card:150:ability:0": {"methods": ["activateSkillOnceTurn", "effectSelectAttachBasicEnergyHand", "targetCardId", "targetPokemon", "singleSelect", "effectEffectedCard", "eVal"], "tokens": ["GRASS_ENERGY", "AttachSelectedCard", "Me", "Heal"]},
    "card:150:attack:0": {"methods": ["preEffect", "eVal", "targetPokemon"], "tokens": ["AttackDamageChangeTypeEnergyCount", "Me"]},
    "card:258:attack:0": {"methods": ["preEffect", "eVal", "targetTrash", "targetBasicEnergy"], "tokens": ["AttackDamageChangeTargetCount", "Enemy"]},
    "card:258:attack:1": {"methods": ["postEffectTrashEnergyMeAll", "postEffectDamageBench"], "tokens": []},
    "card:333:attack:0": {"methods": ["setPreEffect", "effectBreakIfCoinTail", "preEffectAttackDamageChange"], "tokens": []},
    "card:655:attack:0": {"methods": ["setPostEffect", "effectDeckToHandAndShuffle", "targetCondition"], "tokens": ["TargetType", "EnergyTypePokemonOrStadium"]},
    "card:709:attack:0": {"methods": ["setPostEffect", "effectSwitch", "enemySelect", "effectTargetActive"], "tokens": ["Enemy"]},
    "card:710:ability:0": {"methods": ["abilityBattleField", "effect", "targetPokemon"], "tokens": ["DoubleGrassEnergy", "Me"]},
    "card:827:attack:0": {"methods": ["postEffectDamageMe"], "tokens": []},
    "card:828:attack:0": {"methods": ["setPostEffect", "effectDraw"], "tokens": []},
    "card:828:attack:1": {"methods": ["setPreEffect", "exist", "targetDamaged", "preEffectAttackDamageChange"], "tokens": []},
    "card:829:ability:0": {"methods": ["abilityBattleField", "existPokemon", "targetEnergyType", "targetCondition", "effectMe", "eVal"], "tokens": ["Darkness", "TargetType", "MegaEx", "DamageChangeActive"]},
    "card:833:attack:0": {"methods": ["setPostEffect", "effectDeckToBenchAndShuffle", "targetBasicPokemon"], "tokens": []},
    "card:834:ability:0": {"methods": ["activateSkillOnceTurn", "targetDeck", "targetCardId", "effectAttachFromEach", "targetBench", "targetEnergyType", "effectShuffle", "effectEffectedCard", "eVal"], "tokens": ["Darkness", "SelectAttachTo", "Me", "DARKNESS_ENERGY", "DamageCounter"]},
    "card:917:attack:0": {"methods": ["postEffect", "eVal", "targetActive"], "tokens": ["DamageChangeNextTurn", "Enemy"]},
    "card:920:attack:0": {"methods": ["postEffectDamageMe"], "tokens": []},
    "card:970:ability:0": {"methods": ["abilityBattleField", "conditionAttachEnergyMe", "effectMe"], "tokens": ["Darkness", "NoDamageCoin"]},
    "card:970:attack:0": {"methods": ["preEffectMe", "eVal"], "tokens": ["AttackDamageChangeEnergyCount"]},
})


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def expr(kind: str, **fields) -> dict:
    return {"kind": kind, **fields}


def operation(kind: str, target: object, value: object = None, **parameters) -> dict:
    return {
        "kind": "operation",
        "operation": {
            "kind": kind,
            "target": target,
            "value": value,
            "parameters": parameters,
        },
    }


def sequence(*nodes: dict) -> dict:
    return {"kind": "sequence", "nodes": list(nodes)}


def conditional(condition: object, then: dict, otherwise: dict | None = None) -> dict:
    return {"kind": "conditional", "condition": condition, "then": then, "else": otherwise}


def damage_profile(
    printed_base: int | None,
    live_formula: object,
    credible_max: int | str | None,
    theoretical_max: int | str | None,
    *,
    damage_kind: str = "attack_damage",
    expected_value: float | str | None = None,
    required_inputs: list[str] | None = None,
    unknown_reason: str | None = None,
) -> dict:
    return {
        "damage_kind": damage_kind,
        "printed_base": printed_base,
        "live_formula": live_formula,
        "credible_max": credible_max,
        "theoretical_max": theoretical_max,
        "expected_value": expected_value,
        "required_inputs": required_inputs or [],
        "unknown_reason": unknown_reason,
    }


def no_damage(reason: str = "not a damage effect") -> dict:
    return damage_profile(None, None, None, None, unknown_reason=reason)


def fixed_attack(amount: int) -> dict:
    return {
        "verdict": "ordinary_field",
        "activation": {"event": "attack_resolution"},
        "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=amount))),
        "damage_profile": damage_profile(amount, expr("literal", value=amount), amount, amount),
        "observability": ["static"],
        "formula_key": None,
        "change_from_current": None,
        "human_review_ids": [],
    }


def semantic_entries_pokemon_01() -> dict[str, dict]:
    e: dict[str, dict] = {}
    for effect_id, amount in {
        "card:343:attack:0": 30,
        "card:66:attack:0": 90,
        "card:305:attack:1": 20,
        "card:742:attack:0": 30,
        "card:646:attack:1": 10,
        "card:647:attack:0": 60,
        "card:860:attack:0": 10,
        "card:104:attack:0": 60,
        "card:1030:attack:0": 20,
    }.items():
        e[effect_id] = fixed_attack(amount)

    e.update({
        "card:343:ability:0": {
            "verdict": "override_static",
            "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_damage_rule", "own_benched_non_rule_box_pokemon", None, rule="prevent_attack_damage", source="opponent_pokemon_attacks", effects_are_not_prevented=True)),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "barrier=1 loses Bench-only, non-Rule-Box, opponent-attack, and damage-only boundaries", "human_review_ids": [],
        },
        "card:66:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(
                operation("move_cards", "own_deck_top", expr("literal", value=3), destination="own_hand", mode="draw", bind_actual_count="drawn_count"),
                conditional(expr("compare", operator="greater_than", arguments=[expr("read", path="drawn_count"), expr("literal", value=0)]),
                    sequence(operation("move_cards", "this_pokemon_and_all_attached_cards", None, destination="own_deck"), operation("shuffle_cards", "own_deck"))),
            ),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "draw=3 omits conditional self-plus-attachments return and shuffle", "human_review_ids": [],
        },
        "card:305:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("switch_active", "this_pokemon_with_chosen_own_benched_pokemon")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "old attack tags omit the switch", "human_review_ids": [],
        },
        "card:140:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn_same_name", "requirements": ["own_pokemon_ko_during_opponent_previous_turn"]},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=3), destination="own_hand", mode="draw")),
            "damage_profile": no_damage(), "observability": ["public_history"], "formula_key": "pokemon_01_fezandipiti_flip_script_history",
            "change_from_current": "draw=3 omits KO-history condition and same-name usage limit", "human_review_ids": [],
        },
        "card:140:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "chosen_opponent_pokemon", expr("literal", value=100), benched_ignores_weakness_resistance=True)),
            "damage_profile": damage_profile(0, expr("literal", value=100), 100, 100), "observability": ["static"], "formula_key": None,
            "change_from_current": "snipe=100 does not express that Active or Bench may be chosen", "human_review_ids": [],
        },
        "card:741:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=10)), operation("switch_active", "this_pokemon_with_chosen_own_benched_pokemon")),
            "damage_profile": damage_profile(10, expr("literal", value=10), 10, 10), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "old attack tags omit the switch", "human_review_ids": [],
        },
        "card:742:ability:0": {
            "verdict": "override_static", "activation": {"event": "on_evolve_from_hand", "timing": "own_turn", "frequency": "optional_once_for_trigger"},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=2), destination="own_hand", mode="draw")),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "draw=2 omits the from-hand evolution trigger", "human_review_ids": [],
        },
        "card:743:ability:0": {
            "verdict": "override_static", "activation": {"event": "on_evolve_from_hand", "timing": "own_turn", "frequency": "optional_once_for_trigger"},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=3), destination="own_hand", mode="draw")),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "draw=3 omits the from-hand evolution trigger", "human_review_ids": [],
        },
        "card:743:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("place_damage_counters", "opponent_active", expr("multiply", arguments=[expr("literal", value=2), expr("read", path="own_hand_count", observability="observation_direct")]))),
            "damage_profile": damage_profile(0, "20 * own_hand_count", None, None, damage_kind="damage_counters", required_inputs=["own_hand_count"], unknown_reason="credible and theoretical hand-size bounds pending B08"),
            "observability": ["observation_direct"], "formula_key": "pokemon_01_alakazam_powerful_hand",
            "change_from_current": "override and reviewed maximum zero out an exact hand-scaled counter attack", "human_review_ids": ["HR-B05-001"],
        },
        "card:344:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("evolve", "this_pokemon", expr("literal", value=1), source="own_deck", filter="evolves_from_this_pokemon"), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "old attack tags omit deck-search evolution and shuffle", "human_review_ids": [],
        },
        "card:345:ability:0": {
            "verdict": "override_static", "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_damage_rule", "this_pokemon", None, rule="prevent_attack_damage", attacker_filter="pokemon_ex", effects_are_not_prevented=True)),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "immunity=1 loses the Pokemon-ex attacker restriction and damage-only boundary", "human_review_ids": [],
        },
        "card:345:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=120), ignore_target_effects=True, apply_weakness_resistance=True)),
            "damage_profile": damage_profile(120, expr("literal", value=120), 120, 120), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit defender-effect bypass", "human_review_ids": [],
        },
        "card:756:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn_same_name", "requirements": ["source_is_active"]},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=2), destination="own_hand", mode="draw")),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "draw=2 omits Active-only and same-name usage boundaries", "human_review_ids": [],
        },
        "card:756:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": {"kind": "repeat", "random_event": "fair_coin", "until": "tails", "on_each_heads": operation("deal_damage", "opponent_active", expr("literal", value=50), mode="add_to_base"), "practical_enumeration": [{"heads": 0, "damage": 200, "probability": 0.5}, {"heads": 1, "damage": 250, "probability": 0.25}, {"heads": 2, "damage": 300, "probability": 0.125}, {"heads": 3, "damage": 350, "probability": 0.0625}], "omitted_tail": {"heads": ">=4", "probability": 0.0625, "policy": "intentionally_not_expanded_for_top_meta"}},
            "damage_profile": damage_profile(200, "200 + 50 * heads_before_first_tails", 350, "unbounded", expected_value=250.0, required_inputs=["coin_sequence"], unknown_reason="practical ceiling uses approved 0-to-3-head approximation; >=4-head tail omitted"),
            "observability": ["stochastic"], "formula_key": "pokemon_01_mega_kangaskhan_coin_until_tails",
            "change_from_current": "reviewed maximum 200 omits all heads bonuses", "human_review_ids": ["HR-B05-002"],
        },
        "card:112:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn", "requirements": ["this_pokemon_has_darkness_energy"]},
            "program": sequence(operation("remove_damage_counters", "chosen_damaged_own_pokemon", "chosen_count_0_to_min(3,source_counters)", bind_actual_count="moved_count"), operation("place_damage_counters", "chosen_opponent_pokemon", expr("read", path="moved_count"))),
            "damage_profile": damage_profile(None, "10 * moved_count", 30, 30, damage_kind="damage_counters", required_inputs=["chosen_source_damage_counters", "chosen_target"], unknown_reason=None),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_01_munkidori_adrena_brain_transfer",
            "change_from_current": "damage=30/heal=30 loses the shared moved amount, Darkness condition, up-to choice, and both selectors", "human_review_ids": ["HR-B05-001"],
        },
        "card:112:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=60)), operation("apply_special_condition", "opponent_active", expr("literal", value="confused"))),
            "damage_profile": damage_profile(60, expr("literal", value=60), 60, 60), "observability": ["static"], "formula_key": None,
            "change_from_current": "old attack tags omit Confusion", "human_review_ids": [],
        },
        "card:646:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=1), destination="own_hand", mode="draw")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:648:ability:0": {
            "verdict": "override_static", "activation": {"event": "on_evolve_from_hand", "timing": "own_turn", "frequency": "optional_once_for_trigger"},
            "program": sequence(operation("attach_card", "any_distribution_among_own_marnies_pokemon", "chosen_count_0_to_5", source="own_deck", filter="basic_darkness_energy", shared_total_cap=5), operation("shuffle_cards", "own_deck")),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "energy_active=5 and energy_bench=5 can imply separate caps; engine/card text impose one shared total of five", "human_review_ids": [],
        },
        "card:648:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=180)), operation("deal_damage", "chosen_opponent_benched_pokemon", expr("literal", value=30), apply_weakness_resistance=False)),
            "damage_profile": damage_profile(180, expr("literal", value=180), 180, 180), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:414:ability:0": {
            "verdict": "override_static", "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_card_rule", "own_basic_team_rocket_pokemon", None, rule="prevent_effects_of_opponent_attacks", damage_is_not_prevented=True, existing_effects_remain=True)),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "old ability tags encode no protection at all", "human_review_ids": [],
        },
        "card:414:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=60), expr("conditional", condition="has_attached_team_rockets_energy", then=60, else_value=0)]))),
            "damage_profile": damage_profile(60, "60 + (60 if attached Team Rocket's Energy else 0)", 120, 120, required_inputs=["attached_energy_card_names"]),
            "observability": ["observation_direct"], "formula_key": "pokemon_01_articuno_dark_frost",
            "change_from_current": "reviewed maximum 60 omits the conditional +60", "human_review_ids": [],
        },
        "card:104:ability:0": {
            "verdict": "override_static", "activation": {"event": "pokemon_checkup", "frequency": "each_checkup"},
            "program": sequence(operation("place_damage_counters", "each_pokemon_both_sides_with_ability_except_any_froslass", expr("literal", value=1))),
            "damage_profile": damage_profile(None, "10 to each matching Pokemon", "10 per target", "10 per target", damage_kind="damage_counters", required_inputs=["all_pokemon_ids_and_ability_presence"]),
            "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "damage=10 loses both-player spread, every-checkup timing, Ability filter, and Froslass exclusion", "human_review_ids": ["HR-B05-001"],
        },
        "card:235:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=10)), operation("modify_action_rule", "opponent", None, prohibited_action="play_item_from_hand", duration="opponent_next_turn")),
            "damage_profile": damage_profile(10, expr("literal", value=10), 10, 10), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:1031:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=120)), operation("deal_damage", "chosen_opponent_benched_pokemon", expr("literal", value=50), apply_weakness_resistance=False)),
            "damage_profile": damage_profile(120, expr("literal", value=120), 120, 120), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:1031:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=210), ignore_weakness=True, ignore_resistance=True, ignore_target_effects=True)),
            "damage_profile": damage_profile(210, expr("literal", value=210), 210, 210), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit all three bypass rules", "human_review_ids": [],
        },
    })
    return e


def semantic_entries_pokemon_02() -> dict[str, dict]:
    e: dict[str, dict] = {}
    for effect_id, amount in {
        "card:131:attack:1": 30,
        "card:132:attack:0": 50,
        "card:689:attack:1": 110,
        "card:341:attack:0": 20,
        "card:342:attack:0": 80,
        "card:380:attack:0": 40,
        "card:119:attack:0": 10,
        "card:119:attack:1": 40,
        "card:120:attack:0": 70,
        "card:121:attack:0": 70,
    }.items():
        e[effect_id] = fixed_attack(amount)

    tera_program = sequence(operation(
        "modify_damage_rule",
        "this_pokemon_while_benched",
        None,
        rule="prevent_attack_damage",
        attacker_controller="either_player",
        effects_are_not_prevented=True,
    ))
    e.update({
        "card:117:tera:0": {
            "verdict": "override_static",
            "activation": {"event": "continuous_card_rule", "duration": "while_source_is_benched"},
            "program": tera_program,
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "Tera Bench damage prevention is absent from the current tag blocks", "human_review_ids": [],
        },
        "card:117:ability:0": {
            "verdict": "override_static",
            "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_damage_rule", "this_pokemon", None, rule="prevent_attack_damage", attacker_controller="opponent", attacker_filter="pokemon_with_an_ability", effects_are_not_prevented=True)),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "immunity=1 loses the attacker-has-Ability and attack-damage-only boundaries", "human_review_ids": [],
        },
        "card:117:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=140), ignore_weakness=True, ignore_resistance=True, ignore_target_effects=True)),
            "damage_profile": damage_profile(140, expr("literal", value=140), 140, 140), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit all three damage-bypass rules", "human_review_ids": [],
        },
        "card:400:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=30)), operation("deal_damage", "this_pokemon", expr("literal", value=10), damage_source="self_recoil")),
            "damage_profile": damage_profile(30, expr("literal", value=30), 30, 30), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:401:ability:0": {
            "verdict": "override_static",
            "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("attach_card", "this_pokemon", expr("literal", value=1), source="own_discard", filter="basic_energy")),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "energy_active=1 loses the discard source, Basic-Energy filter, self target, and once-per-turn limit", "human_review_ids": [],
        },
        "card:401:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=30), expr("count", path="own_pokemon_in_play", filter="team_rocket")] ))),
            "damage_profile": damage_profile(30, "30 * own_team_rocket_pokemon_in_play", 180, 180, required_inputs=["own_in_play_card_ids_or_team_rocket_flags"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_02_team_rockets_spidops_rocket_rush",
            "change_from_current": "reviewed damage 30 omits multiplication by all own in-play Team Rocket Pokémon, including the attacker", "human_review_ids": [],
        },
        "card:431:ability:0": {
            "verdict": "override_dynamic",
            "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": conditional(
                expr("compare", operator="less_than", arguments=[expr("count", path="own_pokemon_in_play", filter="team_rocket"), expr("literal", value=4)]),
                sequence(operation("modify_action_rule", "this_pokemon", None, prohibited_action="attack", duration="while_count_below_four")),
            ),
            "damage_profile": damage_profile(None, "can_attack = own_team_rocket_pokemon_in_play >= 4", None, None, damage_kind="attack_availability", required_inputs=["own_in_play_card_ids_or_team_rocket_flags"], unknown_reason="not a damage effect"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_02_team_rockets_mewtwo_power_saver",
            "change_from_current": "the current ability vector is all zero and omits the four-Pokémon attack gate", "human_review_ids": [],
        },
        "card:431:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution", "timing": "optional_pre_damage_cost"},
            "program": sequence(
                operation("move_cards", "chosen_energy_attached_to_own_benched_pokemon", "chosen_count_0_to_min(2,eligible)", destination="own_discard", bind_actual_count="discarded_count"),
                operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=160), expr("multiply", arguments=[expr("literal", value=60), expr("read", path="discarded_count")])])),
            ),
            "damage_profile": damage_profile(160, "160 + 60 * discarded_bench_energy_count", 280, 280, required_inputs=["eligible_energy_attached_to_own_bench", "selected_discard_count"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_02_team_rockets_mewtwo_erasure_ball",
            "change_from_current": "damage=160/discard_energy=2 omits the optional 0-to-2 selection, Bench-only source, and +60 per actual discard", "human_review_ids": [],
        },
        "card:434:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution", "requirements": ["opponent_active_is_tera_pokemon"]},
            "program": sequence(operation("copy_or_use_attack", "chosen_attack_of_opponent_active_tera_pokemon", None, use_as_this_attack=True)),
            "damage_profile": damage_profile(0, "resolve chosen attack of opponent Active Tera Pokémon", None, None, required_inputs=["opponent_active_exact_card_id", "chosen_attack_ordinal", "referenced_attack_program"], unknown_reason="credible and theoretical copied-attack maxima pending cross-card resolution in B08"),
            "observability": ["observation_direct", "static"], "formula_key": "pokemon_02_team_rockets_mimikyu_gemstone_mimicry",
            "change_from_current": "reviewed damage zero drops the entire copied-attack program", "human_review_ids": [],
        },
        "card:131:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_own_discarded_duskull", "chosen_count_0_to_min(3,eligible,open_bench_slots)", destination="own_bench")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "old tags omit the up-to-three same-name discard-to-Bench movement", "human_review_ids": [],
        },
        "card:132:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("knock_out", "this_pokemon"), operation("place_damage_counters", "chosen_opponent_pokemon", expr("literal", value=5))),
            "damage_profile": damage_profile(None, expr("literal", value=50), 50, 50, damage_kind="damage_counters", required_inputs=["chosen_opponent_pokemon"]),
            "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "damage=50 loses exact counter semantics, any-opponent-Pokémon targeting, once-per-turn timing, mandatory self-KO, and engine execution order", "human_review_ids": ["HR-B05-001", "HR-B05-003"],
        },
        "card:133:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("knock_out", "this_pokemon"), operation("place_damage_counters", "chosen_opponent_pokemon", expr("literal", value=13))),
            "damage_profile": damage_profile(None, expr("literal", value=130), 130, 130, damage_kind="damage_counters", required_inputs=["chosen_opponent_pokemon"]),
            "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "damage=130 loses exact counter semantics, any-opponent-Pokémon targeting, once-per-turn timing, mandatory self-KO, and engine execution order", "human_review_ids": ["HR-B05-001", "HR-B05-003"],
        },
        "card:133:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=150)), operation("modify_action_rule", "defending_pokemon", None, prohibited_action="retreat", duration="opponent_next_turn")),
            "damage_profile": damage_profile(150, expr("literal", value=150), 150, 150), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:666:ability:0": {
            "verdict": "override_static", "activation": {"event": "game_setup", "source_zone": "own_hand", "timing": "before_opening_active_is_revealed"},
            "program": sequence(operation("move_cards", "this_pokemon", expr("literal", value=1), source="own_hand", destination="own_active", face_down=True, optional=True)),
            "damage_profile": no_damage(), "observability": ["public_history", "observation_direct"], "formula_key": None,
            "change_from_current": "the all-zero ability vector omits the setup-only hand-to-Active rule", "human_review_ids": [],
        },
        "card:666:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=50)), operation("attach_card", "any_distribution_among_own_benched_pokemon", "chosen_count_0_to_min(3,eligible)", source="own_deck", filter="basic_energy", shared_total_cap=3), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(50, expr("literal", value=50), 50, 50), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "energy_accel=3 omits deck source, Basic-Energy filter, Bench-only targets, arbitrary distribution, up-to choice, and shuffle", "human_review_ids": [],
        },
        "card:689:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=20)), operation("modify_action_rule", "defending_pokemon", None, prohibited_action="retreat", duration="opponent_next_turn")),
            "damage_profile": damage_profile(20, expr("literal", value=20), 20, 20), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:342:ability:0": {
            "verdict": "engine_baked", "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_stat", "attacks_used_by_own_cynthias_pokemon_against_opponent_active", expr("literal", value=30), stat="damage_dealt", timing="before_weakness_and_resistance", stacking="per_source_in_play")),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct", "observation_derived"], "formula_key": None,
            "change_from_current": "the generic ability vector is all zero; current stat_bakes.py separately preserves the +30 Cynthia/Active modifier", "human_review_ids": [],
        },
        "card:379:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=20), ignore_resistance=True, apply_weakness=True, apply_target_effects=True)),
            "damage_profile": damage_profile(20, expr("literal", value=20), 20, 20), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit resistance bypass while Weakness and target effects still apply", "human_review_ids": [],
        },
        "card:380:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("move_cards", "chosen_cynthias_pokemon_card", expr("literal", value=1), source="own_deck", destination="own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "search=1 loses the Cynthia's-Pokémon filter, once-per-turn limit, reveal, destination, and shuffle", "human_review_ids": [],
        },
        "card:381:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution", "timing": "optional_post_damage"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=100)), conditional(expr("compare", operator="less_than", arguments=[expr("read", path="own_hand_count"), expr("literal", value=6)]), {"kind": "choice", "chooser": "owner", "options": [sequence(operation("move_cards", "own_deck_top", "6 - own_hand_count", destination="own_hand", mode="draw_until_six")), sequence(operation("no_op", "game_state"))]})),
            "damage_profile": damage_profile(100, expr("literal", value=100), 100, 100), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "draws_cards=6 can imply drawing six; the effect is optional and draws only until the hand reaches six", "human_review_ids": [],
        },
        "card:381:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=260)), operation("move_cards", "all_energy_attached_to_this_pokemon", None, destination="own_discard")),
            "damage_profile": damage_profile(260, expr("literal", value=260), 260, 260), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "discard_energy=2 incorrectly looks capped at the printed cost; the attack discards every Energy attached to the attacker", "human_review_ids": [],
        },
        "card:861:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=50), expr("read", path="opponent_hand_count", observability="observation_direct")]))),
            "damage_profile": damage_profile(50, "50 * opponent_hand_count", None, 2900, required_inputs=["opponent_hand_count"], unknown_reason="credible meta-relevant maximum pending B08; theoretical legal attack-state bound is 58 cards in a 60-card deck because at least one opposing Active card and one unclaimed Prize remain"),
            "observability": ["observation_direct"], "formula_key": "pokemon_02_mega_froslass_resentful_refrain",
            "change_from_current": "reviewed damage 50 omits multiplication by the opponent's public hand count", "human_review_ids": [],
        },
        "card:861:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=150)), operation("apply_special_condition", "opponent_active", expr("literal", value="asleep"))),
            "damage_profile": damage_profile(150, expr("literal", value=150), 150, 150), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit the guaranteed Asleep condition", "human_review_ids": [],
        },
        "card:120:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("reveal_or_inspect", "own_deck_top", expr("literal", value=2), visibility="owner_only"), operation("move_cards", "chosen_one_of_inspected_cards", expr("literal", value=1), destination="own_hand"), operation("move_cards", "other_inspected_card", expr("literal", value=1), destination="own_deck_bottom")),
            "damage_profile": no_damage(), "observability": ["hidden_information", "observation_direct"], "formula_key": None,
            "change_from_current": "the all-zero ability vector omits private top-two inspection, choice, hand movement, and bottom-deck ordering", "human_review_ids": [],
        },
        "card:121:tera:0": {
            "verdict": "override_static", "activation": {"event": "continuous_card_rule", "duration": "while_source_is_benched"},
            "program": tera_program,
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "Tera Bench damage prevention is absent from the current tag blocks", "human_review_ids": [],
        },
        "card:121:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=200)), operation("place_damage_counters", "opponent_benched_pokemon_any_distribution", expr("literal", value=6), distribution="chosen_nonnegative_integer_partition", total_counters=6)),
            "damage_profile": damage_profile(200, expr("literal", value=200), 200, 200), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "counter_snipe=60 loses exact six-counter units and arbitrary distribution across any number of opposing Benched Pokémon", "human_review_ids": ["HR-B05-001"],
        },
        "card:1071:ability:0": {
            "verdict": "override_static", "activation": {"event": "on_play_from_hand_to_bench", "timing": "own_turn", "frequency": "once_per_turn_abilities_named_last_ditch", "source_zone": "own_hand"},
            "program": sequence(operation("move_cards", "chosen_supporter_card", expr("literal", value=1), source="own_deck", destination="own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            "damage_profile": no_damage(), "observability": ["public_history", "observation_direct"], "formula_key": None,
            "change_from_current": "search=1 loses the hand-to-Bench trigger, Supporter filter, reveal/shuffle, optionality, and shared Last-Ditch-name limit", "human_review_ids": [],
        },
        "card:1071:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=60)), operation("move_cards", "this_pokemon_and_all_attached_cards", None, destination="own_hand")),
            "damage_profile": damage_profile(60, expr("literal", value=60), 60, 60), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "old tags omit returning the attacker and every attachment to hand", "human_review_ids": [],
        },
    })
    return e


def semantic_entries_pokemon_03() -> dict[str, dict]:
    e: dict[str, dict] = {}
    for effect_id, amount in {
        "card:89:attack:0": 10,
        "card:89:attack:1": 30,
        "card:90:attack:0": 50,
        "card:65:attack:0": 10,
        "card:214:attack:0": 140,
        "card:959:attack:0": 30,
        "card:169:attack:0": 30,
        "card:848:attack:1": 20,
        "card:818:attack:0": 80,
    }.items():
        e[effect_id] = fixed_attack(amount)

    def festival_lead(formula_key: str) -> dict:
        return {
            "verdict": "override_dynamic",
            "activation": {"event": "continuous_ability", "duration": "while_source_in_play", "requirements": ["festival_grounds_card_1245_is_in_play"]},
            "program": conditional(
                expr("compare", operator="equal", arguments=[expr("read", path="stadium_card_id"), expr("literal", value=1245)]),
                sequence(operation("modify_action_rule", "this_pokemon", expr("literal", value=2), rule="attacks_per_turn", continuation="if_first_attack_kos_active_wait_for_replacement_then_allow_second_attack")),
            ),
            "damage_profile": damage_profile(None, "maximum legal two-attack sequence using this Pokemon's current attack programs", None, None, damage_kind="attack_sequence", required_inputs=["stadium_card_id", "source_attack_programs", "first_attack_ko_and_replacement_state"], unknown_reason="single-attack and full two-attack threat outputs pending B08 composition"),
            "observability": ["observation_direct", "observation_derived", "public_history"], "formula_key": formula_key,
            "change_from_current": "the all-zero ability vector omits the Festival Grounds gate, two-attack allowance, and post-KO replacement continuation", "human_review_ids": [],
        }

    e.update({
        "card:387:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=10), expr("count", path="damage_counters_on_own_benched_cynthias_pokemon")]), ignore_weakness=True, apply_resistance=True, apply_target_effects=True)),
            "damage_profile": damage_profile(10, "10 * total_damage_counters_on_own_benched_cynthias_pokemon", None, None, required_inputs=["own_bench_exact_card_ids_or_cynthia_flags", "own_bench_damage_counter_counts"], unknown_reason="credible and theoretical board/HP-modifier bounds pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_03_cynthias_spiritomb_raging_curse",
            "change_from_current": "reviewed damage 10 omits counter scaling; the existing live helper also over-broadly counts non-Cynthia and non-Benched damaged Pokémon", "human_review_ids": [],
        },
        "card:245:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(
                operation("apply_special_condition", "opponent_active", expr("literal", value="confused")),
                {"kind": "repeat", "count": "chosen_nonnegative_number_of_existing_opponent_damage_counters", "body": sequence(operation("remove_damage_counters", "chosen_opponent_source_pokemon", expr("literal", value=1), bind_actual_count="moved_counter"), operation("place_damage_counters", "chosen_different_opponent_destination_pokemon", expr("read", path="moved_counter"))), "parameters": {"allocation": "any_distribution", "total_damage_counters_conserved": True}},
            ),
            "damage_profile": damage_profile(0, "10 * maximum_counter_concentration_gain_on_one_opponent_pokemon", None, None, damage_kind="damage_counter_relocation", required_inputs=["all_opponent_in_play_damage_counter_counts", "chosen_counter_transfer_allocation"], unknown_reason="no new counters are created; concentration/KO threat calculation pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_03_alakazam_strange_hacking",
            "change_from_current": "the all-zero attack vector omits Confusion and arbitrary conserved redistribution of existing opponent damage counters", "human_review_ids": ["HR-B05-001"],
        },
        "card:245:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=10), expr("multiply", arguments=[expr("literal", value=50), expr("count", path="energy_attached_to_opponent_active")])]))),
            "damage_profile": damage_profile(10, "10 + 50 * energy_attached_to_opponent_active", None, None, required_inputs=["opponent_active_attached_energy_unit_count"], unknown_reason="credible and theoretical maxima pending B08 because attached Energy units are not bounded by a one-unit-per-card assumption"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_03_alakazam_psychic",
            "change_from_current": "reviewed damage 10 omits the +50 multiplier for every Energy attached to the opponent's Active Pokémon", "human_review_ids": [],
        },
        "card:92:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("coin_flip", probability_heads=0.5), sequence(operation("deal_damage", "opponent_active", expr("literal", value=30))), sequence(operation("deal_damage", "opponent_active", expr("literal", value=10)))),
            "damage_profile": damage_profile(10, "30 if heads else 10", 30, 30, expected_value=20.0, required_inputs=["coin_result"]),
            "observability": ["stochastic"], "formula_key": "pokemon_03_applin_tumbling_attack",
            "change_from_current": "probabilistic=1 omits exact 10/30 outcomes and their equal probabilities", "human_review_ids": [],
        },
        "card:93:ability:0": festival_lead("pokemon_03_dipplin_festival_lead"),
        "card:93:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=20), expr("count", path="own_benched_pokemon")]))),
            "damage_profile": damage_profile(20, "20 * own_benched_pokemon_count", 100, 160, required_inputs=["own_bench_occupied_count", "own_bench_capacity"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_03_dipplin_do_the_wave",
            "change_from_current": "reviewed damage 20 omits multiplication by the 0-to-5 occupied Bench count", "human_review_ids": [],
        },
        "card:90:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn", "requirements": ["own_active_has_ability_named_festival_lead"]},
            "program": sequence(operation("move_cards", "chosen_card", expr("literal", value=1), source="own_deck", destination="own_hand"), operation("shuffle_cards", "own_deck")),
            "damage_profile": no_damage(), "observability": ["observation_direct", "observation_derived"], "formula_key": None,
            "change_from_current": "search=1 loses the Active Festival Lead requirement, unrestricted-card result, once-per-turn limit, destination, and shuffle", "human_review_ids": [],
        },
        "card:65:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(
                operation("deal_damage", "opponent_active", expr("literal", value=30)),
                conditional(expr("coin_flip", probability_heads=0.5), sequence(operation("modify_damage_rule", "this_pokemon", None, rule="prevent_attack_damage", source="opponent_pokemon_attacks", duration="opponent_next_turn"), operation("modify_card_rule", "this_pokemon", None, rule="prevent_attack_effects", source="opponent_pokemon_attacks", duration="opponent_next_turn"))),
            ),
            "damage_profile": damage_profile(30, expr("literal", value=30), 30, 30), "observability": ["static", "stochastic"], "formula_key": None,
            "change_from_current": "immunity/probabilistic tags do not preserve that heads prevents both attack damage and effects only during the opponent's next turn", "human_review_ids": [],
        },
        "card:247:ability:0": festival_lead("pokemon_03_swirlix_festival_lead"),
        "card:247:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("place_damage_counters", "chosen_opponent_pokemon", expr("literal", value=2))),
            "damage_profile": damage_profile(0, expr("literal", value=20), 20, 20, damage_kind="damage_counters", required_inputs=["chosen_opponent_pokemon"]),
            "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "counter_snipe=20 loses exact two-counter units and Active-or-Bench opponent targeting", "human_review_ids": ["HR-B05-001"],
        },
        "card:214:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "on_opponent_active_knocked_out", "frequency": "nonstacking_across_wonder_kiss_sources"},
            "program": conditional(expr("coin_flip", probability_heads=0.5), sequence(operation("modify_prize_rule", "owner", expr("literal", value=1), rule="take_additional_prize_for_triggering_ko"))),
            "damage_profile": damage_profile(None, "1 extra Prize if heads else 0", 1, 1, damage_kind="prize_delta", expected_value=0.5, required_inputs=["opponent_active_ko_event", "coin_result"], unknown_reason="not a damage effect"),
            "observability": ["public_history", "stochastic"], "formula_key": "pokemon_03_togekiss_wonder_kiss",
            "change_from_current": "the all-zero ability vector omits KO trigger, fair coin, +1 Prize, and nonstacking rule", "human_review_ids": [],
        },
        "card:169:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=80), expr("multiply", arguments=[expr("literal", value=10), expr("count", path="damage_counters_on_this_pokemon")])]))),
            "damage_profile": damage_profile(80, "80 + 10 * damage_counters_on_this_pokemon", 200, None, required_inputs=["source_current_hp", "source_effective_max_hp"], unknown_reason="credible printed-HP maximum is 200 at 12 counters; legal theoretical maximum with HP modifiers pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_03_duraludon_raging_hammer",
            "change_from_current": "the old max-damage override 30 suppresses this attack; outrage=1 does not retain the exact 80 + current HP-loss formula", "human_review_ids": [],
        },
        "card:190:ability:0": {
            "verdict": "override_static", "activation": {"event": "on_evolve_from_hand", "timing": "own_turn", "frequency": "optional_once_for_trigger"},
            "program": sequence(operation("attach_card", "any_distribution_among_own_metal_pokemon", "chosen_count_0_to_min(2,eligible)", source="own_discard", filter="basic_metal_energy", shared_total_cap=2)),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "energy_active=2 loses the evolution trigger, discard source, Basic Metal filter, up-to/shared cap, Metal-Pokémon targets, and arbitrary distribution", "human_review_ids": [],
        },
        "card:190:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=220)), operation("modify_card_rule", "this_pokemon", None, rule="no_weakness", duration="opponent_next_turn")),
            "damage_profile": damage_profile(220, expr("literal", value=220), 220, 220), "observability": ["static", "public_history"], "formula_key": None,
            "change_from_current": "outrage=1 is incorrect; the post-attack effect removes this Pokémon's Weakness during the opponent's next turn", "human_review_ids": [],
        },
        "card:848:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("switch_active", "this_pokemon_with_chosen_own_benched_pokemon")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "old tags omit the mandatory self-to-Bench switch", "human_review_ids": [],
        },
        "card:849:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("read", path="source_moved_bench_to_active_this_turn", observability="public_history"), sequence(operation("deal_damage", "opponent_active", expr("literal", value=230))), sequence(operation("deal_damage", "opponent_active", expr("literal", value=60)))),
            "damage_profile": damage_profile(60, "230 if source moved from Bench to Active this turn else 60", 230, 230, required_inputs=["source_moved_bench_to_active_this_turn"]),
            "observability": ["public_history"], "formula_key": "pokemon_03_mega_lopunny_gale_thrust",
            "change_from_current": "conditional=1 plus max 230 does not expose the exact 60/230 live branch or required movement history", "human_review_ids": [],
        },
        "card:849:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=160), ignore_target_effects=True, apply_weakness_resistance=True)),
            "damage_profile": damage_profile(160, expr("literal", value=160), 160, 160), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit defender-effect bypass while Weakness and Resistance still apply", "human_review_ids": [],
        },
        "card:164:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=3), destination="own_hand", mode="draw"), operation("move_cards", "opponent_deck_top", expr("literal", value=3), destination="opponent_hand", mode="draw")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "draws_cards=3/deckout=1 does not preserve exact three-card draws for each player or engine resolution order", "human_review_ids": [],
        },
        "card:164:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("coin_flip", probability_heads=0.5), sequence(operation("deal_damage", "opponent_active", expr("literal", value=40))), sequence(operation("deal_damage", "opponent_active", expr("literal", value=20)))),
            "damage_profile": damage_profile(20, "40 if heads else 20", 40, 40, expected_value=30.0, required_inputs=["coin_result"]),
            "observability": ["stochastic"], "formula_key": "pokemon_03_comfey_play_rough",
            "change_from_current": "probabilistic=1 omits exact 20/40 outcomes and their equal probabilities", "human_review_ids": [],
        },
        "card:817:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("place_damage_counters", "chosen_opponent_pokemon", expr("literal", value=1))),
            "damage_profile": damage_profile(0, expr("literal", value=10), 10, 10, damage_kind="damage_counters", required_inputs=["chosen_opponent_pokemon"]),
            "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "counter_snipe=10 loses exact one-counter units and Active-or-Bench opponent targeting", "human_review_ids": ["HR-B05-001"],
        },
        "card:818:ability:0": {
            "verdict": "override_static", "activation": {"event": "on_evolve_from_hand", "timing": "own_turn", "frequency": "optional_once_for_trigger"},
            "program": sequence(operation("apply_special_condition", "opponent_active", expr("literal", value="confused"))),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "the all-zero ability vector omits the from-hand evolution trigger and Confusion of the opponent's Active Pokémon", "human_review_ids": [],
        },
        "card:791:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("read", path="opponent_active_is_pokemon_ex", observability="observation_direct"), sequence(operation("deal_damage", "opponent_active", expr("literal", value=110))), sequence(operation("deal_damage", "opponent_active", expr("literal", value=20)))),
            "damage_profile": damage_profile(20, "110 if opponent_active_is_pokemon_ex else 20", 110, 110, required_inputs=["opponent_active_exact_card_id_or_rule_box_flags"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_03_moltres_fighting_wings",
            "change_from_current": "reviewed damage 20 omits the +90 Pokémon-ex branch", "human_review_ids": [],
        },
        "card:506:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=10)), operation("modify_action_rule", "defending_pokemon", None, prohibited_action="attack", duration="opponent_next_turn")),
            "damage_profile": damage_profile(10, expr("literal", value=10), 10, 10), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:184:ability:0": {
            "verdict": "engine_baked", "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_stat", "own_basic_pokemon_in_play", expr("literal", value=0), stat="retreat_cost", mode="set")),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct", "observation_derived"], "formula_key": None,
            "change_from_current": "switch=1 is misleading; current stat_bakes.py separately and exactly sets retreat cost to zero only for own Basic Pokémon in play", "human_review_ids": [],
        },
        "card:184:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=200)), operation("modify_action_rule", "this_pokemon", None, prohibited_action="attack", duration="own_next_turn")),
            "damage_profile": damage_profile(200, expr("literal", value=200), 200, 200), "observability": ["static", "public_history"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
    })
    return e


def semantic_entries_pokemon_04() -> dict[str, dict]:
    e: dict[str, dict] = {}
    for effect_id, amount in {
        "card:432:attack:1": 70,
        "card:675:attack:0": 50,
        "card:58:attack:1": 160,
        "card:109:attack:0": 10,
        "card:57:attack:0": 30,
        "card:607:attack:1": 100,
        "card:122:attack:0": 50,
        "card:745:attack:1": 10,
    }.items():
        e[effect_id] = fixed_attack(amount)

    e.update({
        "card:649:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=20), expr("multiply", arguments=[expr("literal", value=40), expr("count", path="darkness_energy_units_attached_to_this_pokemon")])]))),
            "damage_profile": damage_profile(20, "20 + 40 * darkness_energy_units_attached_to_this_pokemon", None, None, required_inputs=["source_attached_energy_types_and_unit_counts"], unknown_reason="credible and theoretical Energy-unit bounds pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_04_marnies_morpeko_spiky_wheel",
            "change_from_current": "reviewed damage 20 omits the +40 multiplier for each attached Darkness Energy unit", "human_review_ids": [],
        },
        "card:432:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution", "requirements": ["damaged_own_benched_team_rocket_pokemon_exists"]},
            "program": sequence(operation("remove_damage_counters", "chosen_damaged_own_benched_team_rocket_pokemon", "all", bind_actual_count="moved_count"), operation("place_damage_counters", "opponent_active", expr("read", path="moved_count"))),
            "damage_profile": damage_profile(0, "10 * all_damage_counters_on_chosen_own_benched_team_rocket_pokemon", None, None, damage_kind="damage_counter_relocation", required_inputs=["own_bench_team_rocket_flags", "own_bench_damage_counter_counts"], unknown_reason="credible and theoretical HP-modified source bounds pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_04_team_rockets_wobbuffet_rocket_mirror",
            "change_from_current": "the all-zero attack vector omits all-counter transfer, constrained source selection, opponent-Active target, and conserved moved count", "human_review_ids": ["HR-B05-001"],
        },
        "card:73:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=30)), operation("deal_damage", "this_pokemon", expr("literal", value=10), damage_source="self_recoil")),
            "damage_profile": damage_profile(30, expr("literal", value=30), 30, 30), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:74:ability:0": {
            "verdict": "override_static", "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_damage_rule", "all_own_benched_pokemon", None, rule="prevent_attack_damage", source="opponent_pokemon_attacks"), operation("modify_card_rule", "all_own_benched_pokemon", None, rule="prevent_attack_effects", source="opponent_pokemon_attacks")),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "barrier=1 loses all-own-Bench scope and the distinction that both attack damage and effects are prevented", "human_review_ids": [],
        },
        "card:74:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=10), expr("multiply", arguments=[expr("literal", value=30), expr("count", path="energy_units_attached_to_opponent_active")])]))),
            "damage_profile": damage_profile(10, "10 + 30 * energy_units_attached_to_opponent_active", None, None, required_inputs=["opponent_active_attached_energy_unit_count"], unknown_reason="credible and theoretical Energy-unit bounds pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_04_rabsca_psychic",
            "change_from_current": "reviewed damage 10 omits the +30 multiplier for every Energy unit attached to the opponent's Active Pokémon", "human_review_ids": [],
        },
        "card:675:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn_same_name", "requirements": ["solrock_in_play", "basic_fighting_energy_in_hand_to_discard"]},
            "program": sequence(operation("move_cards", "chosen_basic_fighting_energy", expr("literal", value=1), source="own_hand", destination="own_discard", role="activation_cost"), operation("move_cards", "own_deck_top", expr("literal", value=3), destination="own_hand", mode="draw")),
            "damage_profile": no_damage(), "observability": ["observation_direct", "observation_derived"], "formula_key": None,
            "change_from_current": "draw=3 omits the Solrock requirement, Basic Fighting discard cost, and same-name once-per-turn limit", "human_review_ids": [],
        },
        "card:676:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("read", path="own_bench_contains_lunatone", observability="observation_derived"), sequence(operation("deal_damage", "opponent_active", expr("literal", value=70), ignore_weakness=True, ignore_resistance=True)), sequence(operation("no_op", "game_state", reason="attack_fails"))),
            "damage_profile": damage_profile(70, "70 if own Bench contains Lunatone else 0", 70, 70, required_inputs=["own_bench_exact_card_ids"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_04_solrock_cosmic_beam",
            "change_from_current": "reviewed damage 70 omits the Lunatone-on-Bench failure gate and Weakness/Resistance bypass", "human_review_ids": [],
        },
        "card:678:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=130)), operation("attach_card", "any_distribution_among_own_benched_pokemon", "chosen_count_0_to_min(3,eligible)", source="own_discard", filter="basic_fighting_energy", shared_total_cap=3)),
            "damage_profile": damage_profile(130, expr("literal", value=130), 130, 130), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "energy_accel=3 loses discard source, Basic Fighting filter, Bench-only targets, up-to choice, shared cap, and arbitrary distribution", "human_review_ids": [],
        },
        "card:678:attack:1": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=270)), operation("modify_action_rule", "this_pokemon", None, prohibited_action="use_attack", attack_name="Mega Brave", duration="own_next_turn")),
            "damage_profile": damage_profile(270, expr("literal", value=270), 270, 270), "observability": ["static", "public_history"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:174:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_first_turn_only", "frequency": "once_per_turn_same_name"},
            "program": sequence(operation("move_cards", "chosen_colorless_pokemon_cards_with_printed_hp_at_most_100", "chosen_count_0_to_3", source="own_deck", destination="own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            "damage_profile": no_damage(), "observability": ["observation_direct", "public_history"], "formula_key": None,
            "change_from_current": "search=3 loses first-turn timing, same-name limit, Colorless Pokémon and <=100 HP filters, up-to choice, reveal, and shuffle", "human_review_ids": [],
        },
        "card:174:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("read", path="stadium_is_in_play", observability="observation_direct"), sequence(operation("deal_damage", "opponent_active", expr("literal", value=70))), sequence(operation("no_op", "game_state", reason="attack_fails"))),
            "damage_profile": damage_profile(70, "70 if a Stadium is in play else 0", 70, 70, required_inputs=["stadium_card_id_or_presence"]),
            "observability": ["observation_direct"], "formula_key": "pokemon_04_fan_rotom_assault_landing",
            "change_from_current": "reviewed damage 70 omits the no-Stadium failure gate", "human_review_ids": [],
        },
        "card:272:ability:0": {
            "verdict": "override_static", "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_stat", "all_opponent_dragon_pokemon_in_play", expr("literal", value="psychic_x2"), stat="weakness", mode="set")),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "the all-zero ability vector omits setting every opposing Dragon Pokémon's Weakness to Psychic ×2", "human_review_ids": [],
        },
        "card:272:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=20), expr("multiply", arguments=[expr("literal", value=20), expr("add", arguments=[expr("count", path="own_benched_pokemon"), expr("count", path="opponent_benched_pokemon")])])]))),
            "damage_profile": damage_profile(20, "20 + 20 * (own_bench_count + opponent_bench_count)", 220, 340, required_inputs=["own_bench_occupied_count", "opponent_bench_occupied_count", "both_bench_capacities"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_04_lillies_clefairy_full_moon_rondo",
            "change_from_current": "reviewed damage 20 omits both players' Bench counts and variable Bench capacities", "human_review_ids": [],
        },
        "card:677:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=30)), operation("modify_action_rule", "this_pokemon", None, prohibited_action="use_attack", attack_name="Accelerating Stab", duration="own_next_turn")),
            "damage_profile": damage_profile(30, expr("literal", value=30), 30, 30), "observability": ["static", "public_history"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:58:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "opponent_deck_top", expr("literal", value=1), destination="opponent_discard"), conditional(expr("read", path="own_played_ancient_supporter_from_hand_this_turn", observability="public_history"), sequence(operation("move_cards", "opponent_deck_top", expr("literal", value=3), destination="opponent_discard")))),
            "damage_profile": damage_profile(0, "4 cards milled if an Ancient Supporter was played from hand this turn else 1", 4, 4, damage_kind="opponent_deck_discard_count", required_inputs=["played_ancient_supporter_from_hand_this_turn"], unknown_reason="not a damage effect"),
            "observability": ["public_history", "observation_direct"], "formula_key": "pokemon_04_great_tusk_land_collapse",
            "change_from_current": "deckout=1 omits the Ancient-Supporter history gate and exact 1-versus-4 discard count", "human_review_ids": [],
        },
        "card:109:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn", "requirements": ["source_is_active"]},
            "program": sequence(operation("move_cards", "this_pokemon_and_all_attached_cards", None, destination="own_deck"), operation("shuffle_cards", "own_deck")),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "the all-zero ability vector omits Active-only timing and shuffling this Pokémon plus all attachments into deck", "human_review_ids": [],
        },
        "card:57:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "continuous_ability", "duration": "while_source_in_play"},
            "program": sequence(operation("modify_action_rule", "each_own_evolved_pokemon", None, rule="may_use_attacks_from_previous_evolution_cards", still_require_attack_energy=True)),
            "damage_profile": damage_profile(None, "maximum currently payable attack across current card and exact visible pre-evolution stack", None, None, damage_kind="available_attack_set", required_inputs=["own_evolved_pokemon_exact_card_ids", "visible_pre_evolution_stack_ids", "attached_energy_and_attack_costs", "referenced_attack_programs"], unknown_reason="inherited attack-set and maximum-threat composition pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_04_relicanth_memory_dive",
            "change_from_current": "the all-zero ability vector omits previous-Evolution attack inheritance and retained Energy-cost requirements", "human_review_ids": [],
        },
        "card:607:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("read", path="own_pokemon_ko_by_attack_damage_during_opponent_last_turn", observability="public_history"), sequence(operation("deal_damage", "opponent_active", expr("literal", value=130))), sequence(operation("deal_damage", "opponent_active", expr("literal", value=50)))),
            "damage_profile": damage_profile(50, "130 if own Pokemon was KO'd by attack damage during opponent's last turn else 50", 130, 130, required_inputs=["opponent_previous_turn_attack_damage_ko_history"]),
            "observability": ["public_history"], "formula_key": "pokemon_04_terrakion_retaliate",
            "change_from_current": "revenge=1 does not preserve exact 50/130 branches or the attack-damage/opponent-last-turn trigger boundary", "human_review_ids": [],
        },
        "card:31:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=2), destination="own_hand", mode="draw")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:31:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("read", path="stadium_is_in_play", observability="observation_direct"), sequence(operation("deal_damage", "opponent_active", expr("literal", value=120)), operation("move_cards", "stadium_in_play", expr("literal", value=1), destination="stadium_owner_discard")), sequence(operation("deal_damage", "opponent_active", expr("literal", value=60)))),
            "damage_profile": damage_profile(60, "120 and discard the Stadium if one is in play, else 60", 120, 120, required_inputs=["stadium_card_id_or_presence"]),
            "observability": ["observation_direct"], "formula_key": "pokemon_04_chi_yu_ground_melter",
            "change_from_current": "reviewed damage 60 omits the Stadium-gated +60 branch and mandatory Stadium discard", "human_review_ids": [],
        },
        "card:306:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=60), expr("count", path="opponent_pokemon_ex_in_play")]))),
            "damage_profile": damage_profile(60, "60 * opponent_pokemon_ex_in_play_count", 360, 540, required_inputs=["opponent_in_play_exact_card_ids_or_ex_flags", "opponent_bench_capacity"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_04_dudunsparce_tenacious_tail",
            "change_from_current": "reviewed damage 60 omits multiplication by every opposing Pokémon ex in play and expanded Bench capacity", "human_review_ids": [],
        },
        "card:306:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=150), ignore_target_effects=True, apply_weakness_resistance=True)),
            "damage_profile": damage_profile(150, expr("literal", value=150), 150, 150), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit defender-effect bypass while Weakness and Resistance still apply", "human_review_ids": [],
        },
        "card:122:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn", "requirements": ["source_is_active"]},
            "program": sequence(operation("reveal_or_inspect", "own_deck_top", expr("literal", value=6), visibility="owner_only"), operation("move_cards", "chosen_supporter_among_inspected_cards", "chosen_count_0_to_1", destination="own_hand", reveal=True), operation("shuffle_cards", "all_other_inspected_cards_into_own_deck")),
            "damage_profile": no_damage(), "observability": ["hidden_information", "observation_direct"], "formula_key": None,
            "change_from_current": "the all-zero ability vector omits Active-only top-six inspection, optional Supporter selection/reveal, hand movement, and shuffle", "human_review_ids": [],
        },
        "card:183:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution", "requirements": ["own_bench_not_empty"]},
            "program": sequence(operation("attach_card", "one_chosen_own_benched_pokemon", "chosen_count_0_to_min(2,eligible)", source="own_deck", filter="basic_psychic_energy", all_to_same_target=True), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "energy_accel=2 loses deck source, Basic Psychic filter, one shared Bench target, up-to choice, Bench requirement, and shuffle", "human_review_ids": [],
        },
        "card:597:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=20)), operation("modify_action_rule", "opponent", None, prohibited_action="play_item_from_hand", duration="opponent_next_turn")),
            "damage_profile": damage_profile(20, expr("literal", value=20), 20, 20), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:745:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=1), destination="own_hand", mode="draw")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
    })
    return e


def semantic_entries_pokemon_05() -> dict[str, dict]:
    e: dict[str, dict] = {}
    for effect_id, amount in {
        "card:116:attack:0": 70,
        "card:257:attack:0": 20,
        "card:257:attack:1": 50,
        "card:292:attack:0": 20,
        "card:303:attack:1": 170,
        "card:673:attack:0": 10,
        "card:673:attack:1": 30,
        "card:746:attack:1": 30,
        "card:891:attack:1": 100,
        "card:1051:attack:1": 30,
        "card:1052:attack:0": 80,
    }.items():
        e[effect_id] = fixed_attack(amount)

    def tera_bench_prevention() -> dict:
        return {
            "verdict": "override_static", "activation": {"event": "continuous_rule", "duration": "while_source_is_benched"},
            "program": sequence(operation("modify_damage_rule", "this_pokemon", None, rule="prevent_attack_damage", attacker="either_player", effects_are_not_prevented=True)),
            "damage_profile": no_damage(), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "the current attack/ability tags omit the Tera Bench-only prevention of attack damage from either player's attacks", "human_review_ids": [],
        }

    e.update({
        "card:63:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "all_cards_in_own_hand", None, destination="own_discard"), operation("move_cards", "own_deck_top", expr("literal", value=6), destination="own_hand", mode="draw")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct", "hidden_information"], "formula_key": None,
            "change_from_current": "draws_cards=6 omits discarding the entire current hand before drawing six", "human_review_ids": [],
        },
        "card:63:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_basic_energy_attached_to_any_own_pokemon", "chosen_count_0_to_all", destination="own_discard", bind_actual_count="discarded_basic_energy_count"), operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=70), expr("read", path="discarded_basic_energy_count")]))),
            "damage_profile": damage_profile(0, "70 * chosen Basic Energy cards discarded from own Pokemon", None, None, required_inputs=["all_own_attached_card_ids_and_basic_energy_flags", "chosen_discard_set"], unknown_reason="credible and theoretical attached-card bounds pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_05_raging_bolt_bellowing_thunder",
            "change_from_current": "reviewed damage 70 and discard_energy=1 omit the optional any-count discard across all own Pokémon and exact 70 multiplier", "human_review_ids": [],
        },
        "card:96:tera:0": tera_bench_prevention(),
        "card:96:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("attach_card", "this_pokemon", expr("literal", value=1), source="own_hand", filter="basic_grass_energy", optional=True, bind_success="energy_attached"), conditional(expr("read", path="energy_attached"), sequence(operation("move_cards", "own_deck_top", expr("literal", value=1), destination="own_hand", mode="draw")))),
            "damage_profile": no_damage(), "observability": ["observation_direct", "hidden_information"], "formula_key": None,
            "change_from_current": "energy_accel=1/draw=1 omit the Basic Grass hand source, self-only target, optional activation, once-per-turn limit, and draw-only-if-attached gate", "human_review_ids": [],
        },
        "card:96:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=30), expr("multiply", arguments=[expr("literal", value=30), expr("add", arguments=[expr("count", path="energy_units_attached_to_own_active"), expr("count", path="energy_units_attached_to_opponent_active")])])]))),
            "damage_profile": damage_profile(30, "30 + 30 * Energy units attached to both Active Pokemon", None, None, required_inputs=["both_active_attached_energy_unit_counts"], unknown_reason="credible and theoretical maxima pending B08 because one Energy card need not equal one Energy unit"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_05_teal_mask_ogerpon_myriad_leaf_shower",
            "change_from_current": "reviewed damage 30 omits the +30 multiplier for Energy attached to both Active Pokémon", "human_review_ids": [],
        },
        "card:108:tera:0": tera_bench_prevention(),
        "card:108:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=20)), operation("modify_action_rule", "defending_pokemon", None, prohibited_action="retreat", duration="opponent_next_turn")),
            "damage_profile": damage_profile(20, expr("literal", value=20), 20, 20), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:108:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution", "timing": "optional_post_damage"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=100)), conditional(expr("choice_and_requirement", choice="shuffle_three_attached_energy", minimum_attached_energy_cards=3), sequence(operation("move_cards", "three_chosen_energy_attached_to_this_pokemon", expr("literal", value=3), destination="own_deck"), operation("shuffle_cards", "own_deck"), operation("deal_damage", "chosen_opponent_benched_pokemon", expr("literal", value=120), apply_weakness_resistance=False)))),
            "damage_profile": damage_profile(100, "100 to Active; optionally shuffle exactly 3 attached Energy to deal 120 to one opponent Bench", "100 active + 120 bench", "100 active + 120 bench", damage_kind="multi_target_attack_damage", required_inputs=["source_attached_energy_cards", "opponent_bench_targets", "owner_choice"]),
            "observability": ["observation_direct"], "formula_key": "pokemon_05_wellspring_ogerpon_torrential_pump",
            "change_from_current": "snipe=120/discard_energy=3 lose the optional exactly-three shuffle-to-deck cost, self source, one Bench target, and no Bench Weakness/Resistance", "human_review_ids": [],
        },
        "card:116:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "continuous_ability", "duration": "while_source_has_any_darkness_energy"},
            "program": conditional(expr("compare", operator="greater_than", arguments=[expr("count", path="darkness_energy_units_attached_to_this_pokemon"), expr("literal", value=0)]), sequence(operation("modify_stat", "this_pokemon", expr("literal", value=100), stat="max_hp", mode="add"), operation("modify_damage_rule", "attacks_used_by_this_pokemon", expr("literal", value=100), rule="add_damage_to_opponent_active_before_weakness_resistance"))),
            "damage_profile": damage_profile(None, "+100 max HP and +100 damage to opponent Active from this Pokemon's attacks while Darkness Energy is attached", 100, 100, damage_kind="attack_damage_and_max_hp_modifier", required_inputs=["source_attached_energy_types"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_05_okidogi_adrena_power",
            "change_from_current": "the all-zero ability vector omits the Darkness gate, +100 effective max HP, and +100 outgoing Active damage modifier", "human_review_ids": [],
        },
        "card:141:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn_same_name"},
            "program": sequence(operation("switch_active", "chosen_own_benched_darkness_pokemon_except_pecharunt_ex", expr("literal", value=1)), operation("apply_special_condition", "new_own_active", expr("literal", value="poisoned"))),
            "damage_profile": no_damage(), "observability": ["observation_direct"], "formula_key": None,
            "change_from_current": "switch=1 omits the Darkness-only Bench selector, Pecharunt ex exclusion, same-name limit, and mandatory Poison on the new Active", "human_review_ids": [],
        },
        "card:141:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=60), expr("count", path="prize_cards_taken_by_opponent")]))),
            "damage_profile": damage_profile(0, "60 * Prize cards opponent has taken", 300, 300, required_inputs=["opponent_taken_prize_count"]),
            "observability": ["observation_direct", "public_history"], "formula_key": "pokemon_05_pecharunt_irritated_outburst",
            "change_from_current": "reviewed damage 60 omits multiplication by the opponent's taken-Prize count", "human_review_ids": [],
        },
        "card:293:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn", "requirements": ["own_hand_not_empty"]},
            "program": sequence(operation("move_cards", "one_chosen_card", expr("literal", value=1), source="own_hand", destination="own_discard", role="activation_cost"), operation("move_cards", "own_deck_top", expr("literal", value=2), destination="own_hand", mode="draw")),
            "damage_profile": no_damage(), "observability": ["observation_direct", "hidden_information"], "formula_key": None,
            "change_from_current": "draw=2 omits the mandatory one-card hand discard cost and once-per-turn activation", "human_review_ids": [],
        },
        "card:293:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("copy_and_execute_attack_program", "one_attack_of_a_chosen_own_benched_ns_pokemon", None, still_pay_copied_attack_cost=False, source_attack_cost_already_paid=True)),
            "damage_profile": damage_profile(None, "chosen attack program from one own Benched N's Pokemon", None, None, damage_kind="copied_attack_program", required_inputs=["own_bench_exact_card_ids_and_ns_flags", "referenced_attack_programs", "owner_attack_choice"], unknown_reason="copied attack damage/effect composition pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_05_ns_zoroark_night_joker",
            "change_from_current": "the zero-damage attack vector omits choosing and executing an attack from an own Benched N's Pokémon", "human_review_ids": [],
        },
        "card:303:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=20), expr("count", path="damage_counters_on_this_pokemon")]))),
            "damage_profile": damage_profile(0, "20 * damage counters on this Pokemon", 240, None, required_inputs=["source_current_hp", "source_effective_max_hp"], unknown_reason="credible printed-HP maximum is 240 at 12 counters; theoretical maximum with HP modifiers pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_05_ns_reshiram_powerful_rage",
            "change_from_current": "reviewed damage 20/outrage=1 omit the exact 20 multiplier and zero-damage undamaged state", "human_review_ids": [],
        },
        "card:463:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_supporter_card", "chosen_count_0_to_1", source="own_deck", destination="own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["hidden_information"], "formula_key": None,
            "change_from_current": "search=1 omits the Supporter filter, reveal, hidden-deck fail-to-find allowance, and shuffle", "human_review_ids": [],
        },
        "card:463:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=30)), operation("modify_action_rule", "defending_pokemon", None, prohibited_action="use_selected_attack", selected_by="attacking_player", duration="opponent_next_turn")),
            "damage_profile": damage_profile(30, expr("literal", value=30), 30, 30), "observability": ["static", "public_history"], "formula_key": None,
            "change_from_current": "cooldown=1 does not identify the attacker-selected opposing attack or the defending-Pokémon/opponent-next-turn boundary", "human_review_ids": [],
        },
        "card:473:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution", "requirements": ["own_hand_not_empty"]},
            "program": sequence(operation("move_cards", "one_chosen_own_hand_card", expr("literal", value=1), destination="own_discard"), operation("move_cards", "one_opponent_chosen_opponent_hand_card", expr("literal", value=1), destination="opponent_discard")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["hidden_information", "observation_direct"], "formula_key": None,
            "change_from_current": "the all-zero attack vector omits the own-hand discard gate and subsequent opponent-selected discard from their hand", "human_review_ids": [],
        },
        "card:474:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=20), expr("count", path="team_rocket_named_supporter_cards_in_own_discard")]))),
            "damage_profile": damage_profile(0, "20 * Supporter cards containing Team Rocket in name in own discard", None, None, required_inputs=["own_discard_exact_card_ids", "supporter_flags", "normalized_card_names"], unknown_reason="credible and legal deck-composition maxima pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_05_team_rocket_porygon2_r_command",
            "change_from_current": "reviewed damage 20 omits the exact Supporter/name/discard filters and count multiplier", "human_review_ids": [],
        },
        "card:674:ability:0": {
            "verdict": "override_static", "activation": {"event": "on_evolve_from_hand", "timing": "own_turn", "frequency": "optional_once_for_trigger"},
            "program": sequence(operation("switch_active", "one_chosen_opponent_benched_pokemon", expr("literal", value=1), side="opponent")),
            "damage_profile": no_damage(), "observability": ["observation_direct", "public_history"], "formula_key": None,
            "change_from_current": "switch=1 omits the play-from-hand evolution trigger and opponent-Bench gust target", "human_review_ids": [],
        },
        "card:674:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=210)), operation("deal_damage", "this_pokemon", expr("literal", value=70), damage_kind="self_damage")),
            "damage_profile": damage_profile(210, expr("literal", value=210), 210, 210), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:746:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_pokemon_cards", "chosen_count_0_to_3", source="own_deck", destination="own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["hidden_information"], "formula_key": None,
            "change_from_current": "search=3 omits the Pokémon-card filter, up-to choice, reveal, and shuffle", "human_review_ids": [],
        },
        "card:747:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution", "requirements": ["own_bench_not_empty"]},
            "program": sequence(operation("attach_card", "each_own_benched_pokemon", "up_to_one_basic_psychic_energy_per_target", source="own_deck", per_target_cap=1), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["observation_direct", "hidden_information"], "formula_key": None,
            "change_from_current": "energy_accel=1 loses the per-Benched-Pokémon repetition, deck source, Basic Psychic filter, per-target cap, and final shuffle", "human_review_ids": [],
        },
        "card:747:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=50), expr("count", path="psychic_energy_units_attached_to_all_own_pokemon")]))),
            "damage_profile": damage_profile(0, "50 * Psychic Energy units attached to all own Pokemon", None, None, required_inputs=["all_own_in_play_attached_energy_types_and_units"], unknown_reason="credible and theoretical maxima pending B08 because one Energy card need not equal one Energy unit"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_05_mega_gardevoir_mega_symphonia",
            "change_from_current": "reviewed damage 50 omits the multiplier across Psychic Energy on every own Pokémon", "human_review_ids": [],
        },
        "card:891:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_team_rocket_named_supporter_cards", "chosen_count_0_to_all", source="own_hand", destination="own_discard", bind_actual_count="discarded_supporter_count"), operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=60), expr("read", path="discarded_supporter_count")]))),
            "damage_profile": damage_profile(0, "60 * chosen Team Rocket-named Supporter cards discarded from own hand", None, None, required_inputs=["own_hand_exact_card_ids", "supporter_flags", "normalized_card_names", "chosen_discard_set"], unknown_reason="credible and legal hand/deck-composition maxima pending B08"),
            "observability": ["hidden_information", "observation_derived"], "formula_key": "pokemon_05_team_rocket_honchkrow_rocket_feathers",
            "change_from_current": "reviewed damage 60 omits the optional any-count Team Rocket Supporter discard and exact multiplier", "human_review_ids": [],
        },
        "card:906:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=70), ignore_target_effects=True, apply_weakness_resistance=True)),
            "damage_profile": damage_profile(70, expr("literal", value=70), 70, 70), "observability": ["static"], "formula_key": None,
            "change_from_current": "old tags omit defender-effect bypass while Weakness and Resistance still apply", "human_review_ids": [],
        },
        "card:906:attack:1": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=250)), operation("modify_action_rule", "this_pokemon", None, prohibited_action="attack", duration="own_next_turn")),
            "damage_profile": damage_profile(250, expr("literal", value=250), 250, 250), "observability": ["static", "public_history"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:1051:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "own_deck_top", expr("literal", value=2), destination="own_hand", mode="draw")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:1052:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("attach_card", "one_chosen_own_fighting_pokemon", expr("literal", value=1), source="own_hand", filter="basic_fighting_energy")),
            "damage_profile": no_damage(), "observability": ["observation_direct", "hidden_information"], "formula_key": None,
            "change_from_current": "energy_accel=1 omits the Basic Fighting hand source, Fighting-Pokémon selector, and once-per-turn limit", "human_review_ids": [],
        },
    })
    return e


def semantic_entries_pokemon_06() -> dict[str, dict]:
    e: dict[str, dict] = {}
    for effect_id, amount in {
        "card:42:attack:1": 30,
        "card:655:attack:1": 30,
        "card:710:attack:0": 140,
        "card:829:attack:0": 120,
        "card:833:attack:1": 20,
        "card:834:attack:0": 100,
        "card:917:attack:1": 30,
    }.items():
        e[effect_id] = fixed_attack(amount)

    e.update({
        "card:42:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_pokemon_card", "chosen_count_0_to_1", source="own_deck", destination="own_hand", reveal=True), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["hidden_information"], "formula_key": None,
            "change_from_current": "search=1 omits the Pokémon-card filter, reveal, hidden-deck fail-to-find allowance, and shuffle", "human_review_ids": [],
        },
        "card:150:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("attach_card", "one_chosen_own_pokemon", expr("literal", value=1), source="own_hand", filter="basic_grass_energy", bind_success="energy_attached"), conditional(expr("read", path="energy_attached"), sequence(operation("heal_damage", "same_chosen_own_pokemon", expr("literal", value=30))))),
            "damage_profile": no_damage(), "observability": ["observation_direct", "hidden_information"], "formula_key": None,
            "change_from_current": "energy_accel=1/heal=30 omit the Basic Grass hand source, shared any-own-Pokémon target, draw-free attach gate, and once-per-turn limit", "human_review_ids": [],
        },
        "card:150:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("add", arguments=[expr("literal", value=30), expr("multiply", arguments=[expr("literal", value=30), expr("count", path="grass_energy_units_attached_to_all_own_pokemon")])]))),
            "damage_profile": damage_profile(30, "30 + 30 * Grass Energy units attached to all own Pokemon", None, None, required_inputs=["all_own_in_play_attached_energy_types_and_units"], unknown_reason="credible and theoretical maxima pending B08 because one Energy card need not equal one Energy unit"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_06_hydrapple_syrup_storm",
            "change_from_current": "reviewed damage 30 omits the +30 multiplier across Grass Energy on every own Pokémon", "human_review_ids": [],
        },
        "card:258:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=30), expr("count", path="basic_energy_cards_in_opponent_discard")]))),
            "damage_profile": damage_profile(0, "30 * Basic Energy cards in opponent discard", None, None, required_inputs=["opponent_discard_exact_card_ids", "basic_energy_flags"], unknown_reason="credible and legal deck-composition maxima pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_06_ns_darmanitan_back_draft",
            "change_from_current": "reviewed damage 30 omits the opponent-discard Basic Energy card filter and count multiplier", "human_review_ids": [],
        },
        "card:258:attack:1": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=90)), operation("move_cards", "all_energy_attached_to_this_pokemon", None, destination="own_discard"), operation("deal_damage", "chosen_opponent_benched_pokemon", expr("literal", value=90), apply_weakness_resistance=False)),
            "damage_profile": damage_profile(90, "90 to Active and 90 to one opponent Bench", "90 active + 90 bench", "90 active + 90 bench", damage_kind="multi_target_attack_damage", required_inputs=["opponent_bench_targets"]),
            "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": "snipe=90/discard_energy=3 lose the mandatory all-attached-Energy discard, one Bench target, and no Bench Weakness/Resistance", "human_review_ids": [],
        },
        "card:333:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("coin_flip", probability_heads=0.5), sequence(operation("deal_damage", "opponent_active", expr("literal", value=30))), sequence(operation("deal_damage", "opponent_active", expr("literal", value=10)))),
            "damage_profile": damage_profile(10, "30 if heads else 10", 30, 30, expected_value=20, required_inputs=["coin_result"]),
            "observability": ["stochastic"], "formula_key": "pokemon_06_riolu_quick_attack",
            "change_from_current": "probabilistic=1/reviewed damage 10 omit the exact fair-coin 10/30 distribution and expected damage 20", "human_review_ids": [],
        },
        "card:655:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_cards_matching_grass_pokemon_or_stadium", "chosen_count_0_to_3_total", source="own_deck", destination="own_hand", reveal=True, combination="any"), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["hidden_information"], "formula_key": None,
            "change_from_current": "search=3 omits the combined up-to-three cap, any mixture of Grass Pokémon and Stadiums, reveal, and shuffle", "human_review_ids": [],
        },
        "card:709:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=50)), operation("switch_active", "current_opponent_active_to_bench", expr("literal", value=1), replacement_selected_by="opponent")),
            "damage_profile": damage_profile(50, expr("literal", value=50), 50, 50), "observability": ["static", "observation_direct"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:710:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "continuous_ability", "duration": "while_source_in_play", "stacking": "nonstacking_same_effect"},
            "program": sequence(operation("modify_energy_provision", "each_basic_grass_energy_card_attached_to_any_own_pokemon", expr("literal", value=2), provided_type="grass", mode="set_units_per_card", nonstacking=True)),
            "damage_profile": damage_profile(None, "each attached Basic Grass Energy card provides 2 Grass Energy instead of 1; Wild Growth does not stack", None, None, damage_kind="effective_energy_provision", required_inputs=["all_own_attached_exact_card_ids", "basic_grass_energy_flags", "wild_growth_active"], unknown_reason="not a damage effect; effective payment calculation pending B08"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_06_meganium_wild_growth",
            "change_from_current": "the all-zero ability vector omits doubling Basic Grass Energy provision across all own Pokémon and the nonstacking rule", "human_review_ids": [],
        },
        "card:827:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=30)), operation("deal_damage", "this_pokemon", expr("literal", value=10), damage_kind="self_damage")),
            "damage_profile": damage_profile(30, expr("literal", value=30), 30, 30), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:828:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=70)), operation("move_cards", "own_deck_top", expr("literal", value=2), destination="own_hand", mode="draw")),
            "damage_profile": damage_profile(70, expr("literal", value=70), 70, 70), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:828:attack:1": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": conditional(expr("compare", operator="greater_than", arguments=[expr("count", path="damage_counters_on_this_pokemon"), expr("literal", value=0)]), sequence(operation("deal_damage", "opponent_active", expr("literal", value=270))), sequence(operation("deal_damage", "opponent_active", expr("literal", value=120)))),
            "damage_profile": damage_profile(120, "270 if this Pokemon has any damage counters else 120", 270, 270, required_inputs=["source_current_hp", "source_effective_max_hp"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_06_mega_sharpedo_hungry_jaws",
            "change_from_current": "reviewed damage 120 omits the +150 branch whenever the attacker is damaged", "human_review_ids": [],
        },
        "card:829:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "continuous_ability", "duration": "while_requirement_holds"},
            "program": conditional(expr("read", path="own_in_play_contains_darkness_mega_evolution_pokemon_ex", observability="observation_derived"), sequence(operation("modify_damage_rule", "attacks_used_by_this_pokemon", expr("literal", value=120), rule="add_damage_to_opponent_active_before_weakness_resistance"))),
            "damage_profile": damage_profile(None, "+120 damage to opponent Active from this Pokemon's attacks if any own Darkness Mega Evolution Pokemon ex is in play", 120, 120, damage_kind="attack_damage_modifier", required_inputs=["all_own_in_play_exact_card_ids", "darkness_type_flags", "mega_evolution_ex_flags"]),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_06_seviper_excited_power",
            "change_from_current": "the all-zero ability vector omits the exact Darkness Mega Evolution Pokémon ex board gate and +120 Active-only damage modifier", "human_review_ids": [],
        },
        "card:833:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("move_cards", "chosen_basic_pokemon_cards", "chosen_count_0_to_min(2,open_bench_slots)", source="own_deck", destination="own_bench"), operation("shuffle_cards", "own_deck")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["hidden_information", "observation_direct"], "formula_key": None,
            "change_from_current": "bench_search=2 omits the Basic-Pokémon filter, up-to choice, open-Bench-slot cap, direct deck-to-Bench move, and shuffle", "human_review_ids": [],
        },
        "card:834:ability:0": {
            "verdict": "override_static", "activation": {"event": "manual_ability_activation", "timing": "own_turn", "frequency": "once_per_turn"},
            "program": sequence(operation("attach_card", "one_chosen_own_benched_darkness_pokemon", expr("literal", value=1), source="own_deck", filter="basic_darkness_energy", bind_success="energy_attached"), operation("shuffle_cards", "own_deck"), conditional(expr("read", path="energy_attached"), sequence(operation("place_damage_counters", "same_chosen_own_benched_darkness_pokemon", expr("literal", value=2))))),
            "damage_profile": damage_profile(None, "attach 1 Basic Darkness Energy then place 2 damage counters on the same target", 20, 20, damage_kind="self_damage_counters", required_inputs=["chosen_own_benched_darkness_pokemon", "basic_darkness_energy_in_deck"]),
            "observability": ["observation_direct", "hidden_information"], "formula_key": None,
            "change_from_current": "energy_bench=1/recoil=20 lose deck source, Basic Darkness filter, Darkness Bench target, shuffle, same-target coupling, exact two counters, and once-per-turn limit", "human_review_ids": ["HR-B05-001"],
        },
        "card:917:attack:0": {
            "verdict": "override_static", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("modify_damage_rule", "defending_pokemon_attacks", expr("literal", value=-20), rule="damage_to_any_target_before_weakness_resistance", duration="opponent_next_turn")),
            "damage_profile": damage_profile(0, expr("literal", value=0), 0, 0), "observability": ["public_history"], "formula_key": None,
            "change_from_current": "the all-zero attack vector omits the -20 outgoing damage modifier on the Defending Pokémon during the opponent's next turn", "human_review_ids": [],
        },
        "card:920:attack:0": {
            "verdict": "generic_exact", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("literal", value=220)), operation("deal_damage", "this_pokemon", expr("literal", value=30), damage_kind="self_damage")),
            "damage_profile": damage_profile(220, expr("literal", value=220), 220, 220), "observability": ["static"], "formula_key": None,
            "change_from_current": None, "human_review_ids": [],
        },
        "card:970:ability:0": {
            "verdict": "override_dynamic", "activation": {"event": "when_this_pokemon_would_be_damaged_by_attack", "requirements": ["this_pokemon_has_darkness_energy"]},
            "program": conditional(expr("coin_flip", probability_heads=0.5), sequence(operation("modify_damage_rule", "pending_attack_damage_to_this_pokemon", expr("literal", value=0), rule="prevent_that_damage", effects_are_not_prevented=True))),
            "damage_profile": damage_profile(None, "if Darkness Energy is attached, fair coin prevents all pending attack damage on heads", None, None, damage_kind="incoming_attack_damage_prevention", expected_value="0.5 * incoming attack damage prevented when eligible", required_inputs=["source_attached_energy_types", "pending_attack_damage", "coin_result"], unknown_reason="not outgoing damage"),
            "observability": ["observation_direct", "stochastic"], "formula_key": "pokemon_06_fezandipiti_adrena_pheromone",
            "change_from_current": "immunity=1/probabilistic=1 lose the Darkness gate, attack-damage-only trigger, fair coin, and damage-only prevention boundary", "human_review_ids": [],
        },
        "card:970:attack:0": {
            "verdict": "override_dynamic", "activation": {"event": "attack_resolution"},
            "program": sequence(operation("deal_damage", "opponent_active", expr("multiply", arguments=[expr("literal", value=30), expr("count", path="energy_units_attached_to_this_pokemon")]))),
            "damage_profile": damage_profile(0, "30 * Energy units attached to this Pokemon", None, None, required_inputs=["source_attached_energy_unit_count"], unknown_reason="credible and theoretical maxima pending B08 because one Energy card need not equal one Energy unit"),
            "observability": ["observation_direct", "observation_derived"], "formula_key": "pokemon_06_fezandipiti_energy_feather",
            "change_from_current": "reviewed damage 30 omits multiplication by every Energy unit attached to the attacker", "human_review_ids": [],
        },
    })
    return e


def semantic_entries(batch_id: str) -> dict[str, dict]:
    builders = {
        "pokemon-01": semantic_entries_pokemon_01,
        "pokemon-02": semantic_entries_pokemon_02,
        "pokemon-03": semantic_entries_pokemon_03,
        "pokemon-04": semantic_entries_pokemon_04,
        "pokemon-05": semantic_entries_pokemon_05,
        "pokemon-06": semantic_entries_pokemon_06,
    }
    try:
        return builders[batch_id]()
    except KeyError as exc:
        raise ValueError(f"No semantic audit builder exists for {batch_id}") from exc


def build_batch(batch_id: str = "pokemon-01") -> tuple[dict, list[dict]]:
    worklist = json.loads(WORKLIST.read_text(encoding="utf-8"))
    manifest = json.loads(BATCHES.read_text(encoding="utf-8"))
    batch = next(item for item in manifest["batches"] if item["batch_id"] == batch_id)
    cards = {card["card_id"]: card for card in worklist["cards"]}
    semantics = semantic_entries(batch_id)
    recorded_path = OUTPUT / f"{batch_id}-recorded-engine-evidence.json"
    recorded = json.loads(recorded_path.read_text(encoding="utf-8")) if recorded_path.exists() else None
    review_records = {
        item["id"]: item
        for item in json.loads(HUMAN_REVIEW.read_text(encoding="utf-8"))["records"]
    }
    expected_effect_ids = [
        effect["effect_id"]
        for card_id in batch["card_ids"]
        for effect in cards[card_id]["effects"]
    ]
    issues: list[dict] = []
    if set(expected_effect_ids) != set(semantics):
        issues.append({
            "code": "semantic_key_mismatch",
            "missing": sorted(set(expected_effect_ids) - set(semantics)),
            "extra": sorted(set(semantics) - set(expected_effect_ids)),
        })
    audited_cards = []
    formula_queue = []
    for card_id in batch["card_ids"]:
        source = cards[card_id]
        audited_effects = []
        for effect in source["effects"]:
            semantic = semantics.get(effect["effect_id"])
            if semantic is None:
                continue
            methods = set(effect["engine"].get("method_calls", []))
            tokens = set(effect["engine"].get("effect_tokens", []))
            requirement = ENGINE_REQUIREMENTS.get(effect["effect_id"])
            validation_checks = {}
            validation_refs = []
            if requirement is None:
                validation_checks["ordinary_engine_shape"] = (
                    semantic["verdict"] == "ordinary_field"
                    and effect["engine"].get("method_calls") == ["attack", "textEn"]
                )
                validation_refs.append("binary/database printed damage and active source attack chain")
            else:
                validation_checks["required_engine_methods"] = set(requirement["methods"]) <= methods
                validation_checks["required_engine_tokens"] = set(requirement["tokens"]) <= tokens
                validation_refs.append(
                    f"{effect['engine']['source_path']}:{effect['engine']['source_line_start']}"
                )
            if recorded and effect["effect_id"] in recorded["samples"]:
                recorded_count = len(recorded["samples"][effect["effect_id"]])
                coverage_count = recorded["coverage"]["sample_counts"][effect["effect_id"]]
                validation_checks["recorded_engine_coverage_accounted"] = (
                    recorded_count == coverage_count
                    and recorded.get("checks", {}).get("full_dataset_scan_complete", True)
                )
                if recorded_count >= 3:
                    validation_checks["recorded_engine_samples"] = True
                elif recorded_count:
                    validation_checks["sparse_recorded_sample_with_exact_source_fallback"] = requirement is not None
                else:
                    validation_checks["no_recorded_execution_with_exact_source_fallback"] = requirement is not None
                validation_refs.append(
                    f"{recorded_path.name}#samples/{effect['effect_id']}"
                    f" ({recorded_count} distinct recorded executions)"
                )
            if batch_id == "pokemon-01" and effect["effect_id"] == "card:743:attack:0" and recorded:
                validation_checks["live_formula"] = recorded["checks"]["alakazam_live_formula_passes"]
            validation_checks["human_reviews_resolved"] = all(
                review_records[review_id]["status"] == "resolved"
                for review_id in semantic["human_review_ids"]
            )
            validation_passed = bool(validation_checks) and all(validation_checks.values())
            if not validation_passed:
                issues.append({
                    "code": "effect_validation_failed",
                    "effect_id": effect["effect_id"],
                    "checks": validation_checks,
                })
            record = {
                "effect_id": effect["effect_id"],
                "kind": effect["kind"],
                "name": effect["name"],
                "text": effect["text"],
                "printed_cost": effect["printed_cost"],
                "printed_damage": effect["printed_damage"],
                "engine": effect["engine"],
                "current_encoder": effect["current_encoder"],
                **semantic,
                "validation": {
                    "status": "passed" if validation_passed else "failed",
                    "checks": validation_checks,
                    "refs": validation_refs,
                },
                "audit_status": "complete" if validation_passed else "draft",
            }
            audited_effects.append(record)
            if semantic["formula_key"]:
                formula_queue.append({
                    "formula_key": semantic["formula_key"],
                    "effect_id": effect["effect_id"],
                    "owner": "B08",
                    "required_inputs": semantic["damage_profile"]["required_inputs"],
                    "question": semantic["damage_profile"].get("live_formula") or "activation/state calculation",
                    "status": "queued",
                })
        audited_cards.append({
            "card_id": card_id,
            "card_name": source["card_name"],
            "frequency": source["frequency"],
            "effects": audited_effects,
            "audit_status": (
                "complete" if audited_effects and all(
                    effect["audit_status"] == "complete" for effect in audited_effects
                ) else "draft"
            ),
        })
    complete = (
        not issues
        and len(audited_cards) == len(batch["card_ids"])
        and all(card["audit_status"] == "complete" for card in audited_cards)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "batch_id": batch_id,
        "status": "complete" if complete else "draft_pending_validation",
        "card_ids": batch["card_ids"],
        "cards": audited_cards,
        "formula_queue": formula_queue,
        "summary": {
            "cards": len(audited_cards),
            "effects": sum(len(card["effects"]) for card in audited_cards),
            "verdicts": dict(sorted(__import__("collections").Counter(
                effect["verdict"] for card in audited_cards for effect in card["effects"]
            ).items())),
            "formula_queue": len(formula_queue),
            "issues": len(issues),
        },
    }, issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_id", nargs="?", default="pokemon-01")
    args = parser.parse_args()
    batch, issues = build_batch(args.batch_id)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{args.batch_id}-draft.json").write_bytes(json_bytes(batch))
    if batch["status"] == "complete":
        (OUTPUT / f"{args.batch_id}.json").write_bytes(json_bytes(batch))
    (OUTPUT / f"{args.batch_id}-issues.json").write_bytes(json_bytes({"schema_version": SCHEMA_VERSION, "issues": issues}))
    print(json.dumps(batch["summary"], indent=2, sort_keys=True))
    return 2 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
