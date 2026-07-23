"""
opponent_tags.py — Per-card attack/ability tag blocks for the opponent-Pokemon vector.

Assembles the fixed-width blocks defined in specs/completed/03-attack-ability-tagging.md from the
three tiers: attack_overrides.OVERRIDES (tier 1) -> effect_features keyword extraction
(tier 2) -> zeros (tier 3, vanilla attacker).

    card_tag_vectors(card_id) -> (attack_blocks: 36 floats [2 x 18, cheapest-first],
                                  ability_block: 11 floats,
                                  max_damage: int raw HP)

Damage and cost come from card_data.py; an override's "attacks" list fully replaces the
keyword tags (and optionally damage/energy_cost), "ability" fully replaces the ability
tags, and "max_damage" overrides the max-damage scalar. A reviewed "max_hp" correction
is consumed by features.py. Results are cached per card_id.

    python opponent_tags.py        # self-test
"""
from __future__ import annotations

import card_data as cd
import effect_features as ef
from attack_overrides import get_override

N_ATTACK_BLOCK = 18         # cost, damage, then ATTACK_TAG_FIELDS (16)
N_ABILITY_BLOCK = 11        # ABILITY_TAG_FIELDS
MAX_ATTACK_DAMAGE = 270.0   # damage clipped at 270: our max HP is 270, so overkill above

# (field, divisor) in block order after cost/damage; divisor None = boolean 0/1
_ATTACK_NORMS: list[tuple[str, float | None]] = [
    ("snipe", 100.0), ("counter_snipe", 100.0), ("conditional", None),
    ("item_lock", None), ("cooldown", None), ("energy_accel", 3.0),
    ("draws_cards", 6.0), ("discard_energy", 5.0), ("cubchoo", None),
    ("deckout", None), ("probabilistic", None), ("revenge", None), ("outrage", None),
    ("retreat_lock", None), ("immunity", None), ("recoil", 70.0),
]
_ABILITY_NORMS: list[tuple[str, float | None]] = [
    ("draw", 6.0), ("damage", 100.0), ("immunity", None), ("gust", None),
    ("energy_active", 3.0), ("energy_bench", 3.0), ("search", 3.0),
    ("barrier", None), ("heal", 100.0), ("mill", None), ("switch", None),
]
assert [f for f, _ in _ATTACK_NORMS] == ef.ATTACK_TAG_FIELDS
assert [f for f, _ in _ABILITY_NORMS] == ef.ABILITY_TAG_FIELDS


def _clip01(x: float) -> float:
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def attack_block_schema() -> list[str]:
    return ["energy_cost", "damage"] + ef.ATTACK_TAG_FIELDS


def ability_block_schema() -> list[str]:
    return list(ef.ABILITY_TAG_FIELDS)


def _attack_raw(atk: cd.AttackSpec, override: dict | None) -> dict:
    """One attack -> raw dict {energy_cost, damage, <16 tag fields>}."""
    raw = {"energy_cost": atk.total_cost, "damage": atk.damage_base}
    if override is not None:
        # tier 1: the override dict fully replaces keyword extraction (missing tag
        # fields mean 0); damage/energy_cost fall back to card data unless given.
        raw.update({k: 0 for k in ef.ATTACK_TAG_FIELDS})
        raw.update(override)
    else:
        raw.update(ef.attack_tags(atk.effect_text, total_cost=atk.total_cost))
    return raw


def _ability_raw(abilities: list[str], override: dict | None) -> dict:
    """First ability only (spec 02); override fully replaces extraction."""
    if override is not None:
        raw = {k: 0 for k in ef.ABILITY_TAG_FIELDS}
        raw.update(override)
        return raw
    return ef.ability_tags(abilities[0] if abilities else None)


def _attack_vec(raw: dict | None) -> list[float]:
    if raw is None:
        return [0.0] * N_ATTACK_BLOCK
    v = [_clip01(raw["energy_cost"] / 5.0),
         _clip01(min(raw["damage"], MAX_ATTACK_DAMAGE) / MAX_ATTACK_DAMAGE)]
    for field, div in _ATTACK_NORMS:
        x = float(raw.get(field, 0))
        v.append(_clip01(x / div) if div else _clip01(x))
    return v


def _ability_vec(raw: dict) -> list[float]:
    v = []
    for field, div in _ABILITY_NORMS:
        x = float(raw.get(field, 0))
        v.append(_clip01(x / div) if div else _clip01(x))
    return v


class _CardTags:
    __slots__ = ("attack_raws", "ability_raw", "max_damage",
                 "attack_vecs", "ability_vec")

    def __init__(self, attack_raws, ability_raw, max_damage):
        self.attack_raws = attack_raws          # list[dict], card's real attacks only
        self.ability_raw = ability_raw          # dict
        self.max_damage = max_damage            # int, raw HP
        self.attack_vecs = [_attack_vec(r) for r in attack_raws]
        self.ability_vec = _ability_vec(ability_raw)


_cache: dict[int, _CardTags] = {}


def card_tags(card_id) -> _CardTags:
    """Raw + vectorized tag blocks for one card, cached. Unknown/None id -> empty."""
    key = int(card_id) if card_id is not None else -1
    hit = _cache.get(key)
    if hit is not None:
        return hit

    st = cd.CardRegistry.load().get(card_id)
    ov = get_override(card_id) or {}
    virtual_attacks = ov.get("virtual_attacks")
    if virtual_attacks is not None:
        attack_raws = []
        for spec in virtual_attacks[:cd.MAX_ATTACKS]:
            raw = {"energy_cost": 0, "damage": 0}
            raw.update({k: 0 for k in ef.ATTACK_TAG_FIELDS})
            raw.update(spec)
            attack_raws.append(raw)
    else:
        ov_attacks = ov.get("attacks")
        attack_raws = []
        for i, atk in enumerate(st.attacks[:cd.MAX_ATTACKS]):
            atk_ov = None
            if ov_attacks is not None:
                atk_ov = ov_attacks[i] if i < len(ov_attacks) else {}
            attack_raws.append(_attack_raw(atk, atk_ov))

    ability_raw = _ability_raw(st.abilities, ov.get("ability"))

    if "max_damage" in ov:
        max_damage = int(ov["max_damage"])
    else:
        max_damage = max((r["damage"] for r in attack_raws), default=0)

    tags = _CardTags(attack_raws, ability_raw, max_damage)
    _cache[key] = tags
    return tags


def card_tag_vectors(card_id) -> tuple[list[float], list[float], int]:
    """(36 floats: 2 attack blocks cheapest-first, 11 floats: ability block,
    max_damage raw HP). Single-attack cards: second block zeros."""
    t = card_tags(card_id)
    blocks = list(t.attack_vecs) + [None] * (cd.MAX_ATTACKS - len(t.attack_vecs))
    flat: list[float] = []
    for b in blocks[:cd.MAX_ATTACKS]:
        flat += b if b is not None else [0.0] * N_ATTACK_BLOCK
    return flat, list(t.ability_vec), t.max_damage


# =======================================================================================
def _selftest():
    import math

    # empty / unknown
    av, bv, md = card_tag_vectors(None)
    assert av == [0.0] * 36 and bv == [0.0] * 11 and md == 0

    # Budew 235 — override item_lock, cost/damage from card data (Itchy Pollen: free, 10)
    av, bv, md = card_tag_vectors(235)
    s = attack_block_schema()
    a1 = dict(zip(s, av[:18]))
    assert a1["item_lock"] == 1.0, a1
    assert a1["damage"] == 10 / 270.0, a1
    assert a1["energy_cost"] == 0.0, a1
    assert av[18:] == [0.0] * 18          # single attack -> second block zeros
    assert md == 10, md

    # Tyranitar 290 — no override: tier-2 keywords (Cracking Stomp -> deckout)
    av, bv, md = card_tag_vectors(290)
    a1, a2 = dict(zip(s, av[:18])), dict(zip(s, av[18:]))
    assert a2["deckout"] == 1.0 or a1["deckout"] == 1.0, (a1, a2)
    assert md == 150, md

    # Munkidori 112 — ability override heal=30 & damage=30 -> 0.3 each
    _, bv, _ = card_tag_vectors(112)
    b = dict(zip(ability_block_schema(), bv))
    assert abs(b["heal"] - 0.3) < 1e-9 and abs(b["damage"] - 0.3) < 1e-9, b

    # IMMUNITY / BARRIER / GUST seeds
    for cid, fld in ((117, "immunity"), (330, "immunity"), (343, "barrier"),
                     (74, "barrier"), (674, "gust"), (310, "gust")):
        _, bv, _ = card_tag_vectors(cid)
        assert dict(zip(ability_block_schema(), bv))[fld] == 1.0, (cid, fld)

    # Chandelure 495 — override marks deckout on both attacks; Burn It All Up
    # discard_energy=2; max damage = 180 printed
    av, bv, md = card_tag_vectors(495)
    a1, a2 = dict(zip(s, av[:18])), dict(zip(s, av[18:]))
    assert a1["deckout"] == 1.0 and a2["deckout"] == 1.0
    assert md == 180, md

    # N's Zoroark ex — two aggregate copied-attack threat blocks.
    av, _, md = card_tag_vectors(293)
    z1, z2 = dict(zip(s, av[:18])), dict(zip(s, av[18:]))
    assert z1["damage"] == 250 / 270.0 and z1["cooldown"] == 1.0, z1
    assert z1["recoil"] == 0.0, z1
    assert z2["damage"] == 90 / 270.0 and z2["snipe"] == 0.9, z2
    assert z2["discard_energy"] == 0.4 and md == 290, (z2, md)

    # everything in [0,1] over the whole pool; vanilla cards fully zero-tagged
    reg = cd.CardRegistry.load()
    n_tagged = 0
    for cid in reg.stats:
        av, bv, md = card_tag_vectors(cid)
        assert len(av) == 36 and len(bv) == 11
        assert all(math.isfinite(x) and 0.0 <= x <= 1.0 for x in av + bv), cid
        assert md >= 0
        if any(x > 0 for x in av[2:18] + av[20:36] + bv):
            n_tagged += 1
    print(f"opponent_tags self-test PASSED ({len(reg.stats)} cards, {n_tagged} with tags)")


if __name__ == "__main__":
    _selftest()
