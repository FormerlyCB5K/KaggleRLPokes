"""
card_data.py — CSV-backed per-card static registry for the generalized Pokemon encoder.

Parses Decks/Deck-Builder/EN_Card_Data.csv into a per-card_id CardStats record: type,
weakness/resistance (collapsed to Fire/Fighting booleans — the only types our Ceruledge
attacker ever cares about), stage, rule (ex/Mega ex), max HP, retreat cost, and up to
MAX_ATTACKS=2 attacks (cheapest-first) + ability effect texts.

Ported and trimmed from the sibling ptcg-kaggle-fork's learn/card_features.py +
learn/derived_features.py (CardStats/AttackSpec shape, CSV parsing helpers). Trimmed
because this project only needs Fire ({R}) vs Fighting ({F}) vs "other" distinctions,
not the fork's full 9/11-type basis.

Pure-Python (csv + re only), no torch/numpy dependency, so it can be imported anywhere
features.py already is.

    python card_data.py        # self-test
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass, field

FIRE_SYM = "{R}"
FIGHTING_SYM = "{F}"

STAGES = ["Basic Pokémon", "Stage 1 Pokémon", "Stage 2 Pokémon"]
RULES = ["n/a", "Pokémon ex", "Mega Pokémon ex"]
# Full type basis (fork's POK_TYPES), kept for Identity's type one-hot — needed to
# evaluate effect conditions like "opponent's active is a {P} Pokémon".
POK_TYPES = ["{G}", "{R}", "{W}", "{L}", "{P}", "{F}", "{D}", "{M}", "竜", "{C}"]

MAX_ATTACKS = 2
_COL_TYPE = "Stage (Pokémon)/Type (Energy and Trainer)"
_COL_RESIST = "Resistance (Type)"

_TYPE_RE = re.compile(r"\{[A-Z]\}|竜")
_DMG_IN_TEXT = re.compile(r"does (\d+) damage")
_ENERGY_PIP_RE = re.compile(r"\{[A-Z]\}|●")


def _first_type(field_val: str | None):
    """First element symbol of a CSV Type/Weakness/Resistance field ({R}{R} -> {R})."""
    if not field_val or field_val == "n/a":
        return None
    m = _TYPE_RE.search(field_val)
    return m.group(0) if m else None


def _is_attack(row: dict) -> bool:
    """Attack rows carry an energy cost; ability/Tera/Trainer rows have a blank cost."""
    return (row.get("Cost") or "n/a") != "n/a"


def _energy_pip_counts(cost_str: str) -> tuple[int, int, int]:
    """Cost string -> (fire_count, fighting_count, total_count). Only Fire/Fighting are
    typed; any other pip (colorless or otherwise) only contributes to the total."""
    fire = fighting = total = 0
    if cost_str and cost_str != "n/a":
        for token in _ENERGY_PIP_RE.findall(cost_str):
            total += 1
            if token == FIRE_SYM:
                fire += 1
            elif token == FIGHTING_SYM:
                fighting += 1
    return fire, fighting, total


def _damage_hp(row: dict) -> int:
    """Attack base damage in HP. Prefers the Damage column's digits; falls back to the
    'does N damage' phrase in effect text for the handful of attacks with a blank column
    (mirrors the fork's card_features._damage_ratio source selection)."""
    dmg = row.get("Damage", "")
    if dmg and dmg != "n/a":
        digits = re.sub(r"[^0-9]", "", dmg)
        if digits:
            return int(digits)
    m = _DMG_IN_TEXT.search(row.get("Effect Explanation", "") or "")
    return int(m.group(1)) if m else 0


def _damage_sort_key(row: dict) -> tuple[int, int]:
    _, _, total = _energy_pip_counts(row.get("Cost", ""))
    return (total, _damage_hp(row))


@dataclass
class AttackSpec:
    name: str
    fire_count: int
    fighting_count: int
    total_cost: int
    damage_base: int
    effect_text: str


@dataclass
class CardStats:
    type_sym: str | None = None
    weak_fire: bool = False
    weak_fighting: bool = False
    resist_fire: bool = False
    resist_fighting: bool = False
    stage: str | None = None
    is_ex: bool = False
    is_mega_ex: bool = False
    max_hp: int = 0
    retreat: int = 0
    attacks: list[AttackSpec] = field(default_factory=list)
    abilities: list[str] = field(default_factory=list)


_EMPTY_STATS = CardStats()


def _build_card_stats(rows: list) -> CardStats:
    first = rows[0]
    rule = first.get("Rule", "n/a")
    weak_sym = _first_type(first.get("Weakness", ""))
    resist_sym = _first_type(first.get(_COL_RESIST, ""))

    atk_rows = [r for r in rows if _is_attack(r)]
    # [Tera] rows are the Tera rule text, not an ability — excluding them keeps
    # "first ability" meaningful for spec-03 tag extraction.
    abl_rows = [r for r in rows if not _is_attack(r)
                and (r.get("Move Name") or "").strip() != "[Tera]"]
    atk_rows.sort(key=_damage_sort_key)

    attacks = []
    for r in atk_rows[:MAX_ATTACKS]:
        fire, fighting, total = _energy_pip_counts(r.get("Cost", ""))
        attacks.append(AttackSpec(
            name=(r.get("Move Name") or "").strip(),
            fire_count=fire,
            fighting_count=fighting,
            total_cost=total,
            damage_base=_damage_hp(r),
            effect_text=r.get("Effect Explanation", "") or "",
        ))

    hp = first.get("HP", "")
    retreat = first.get("Retreat", "")
    return CardStats(
        type_sym=_first_type(first.get("Type", "")),
        weak_fire=(weak_sym == FIRE_SYM),
        weak_fighting=(weak_sym == FIGHTING_SYM),
        resist_fire=(resist_sym == FIRE_SYM),
        resist_fighting=(resist_sym == FIGHTING_SYM),
        stage=first.get(_COL_TYPE) if first.get(_COL_TYPE) in STAGES else None,
        is_ex=(rule == "Pokémon ex"),
        is_mega_ex=(rule == "Mega Pokémon ex"),
        max_hp=int(hp) if hp and hp != "n/a" else 0,
        retreat=int(retreat) if retreat and retreat != "n/a" else 0,
        attacks=attacks,
        abilities=[r.get("Effect Explanation", "") or "" for r in abl_rows],
    )


def load_card_rows(csv_path: str | None = None) -> dict:
    """card_id (int) -> list of CSV rows (one per move/ability), in file order."""
    path = csv_path or _default_csv()
    rows_by_id: dict = {}
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cid = int(row["Card ID"])
            rows_by_id.setdefault(cid, []).append(row)
    return rows_by_id


_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)


def _default_csv() -> str:
    cands = [
        os.environ.get("PTCG_CARD_CSV"),
        os.path.join(_REPO, "Decks", "Deck-Builder", "EN_Card_Data.csv"),
        os.path.join(_HERE, "EN_Card_Data.csv"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError(
        "EN_Card_Data.csv not found. Set $PTCG_CARD_CSV or place it at "
        f"Decks/Deck-Builder/EN_Card_Data.csv. Looked in: {[c for c in cands if c]}")


class CardRegistry:
    """Cached card_id -> CardStats lookup. `.get(id)` returns an empty/neutral CardStats
    for None/unknown ids so an absent Pokemon slot contributes zeros downstream."""

    _cache: dict = {}

    def __init__(self, stats: dict):
        self.stats = stats

    @classmethod
    def load(cls, csv_path: str | None = None) -> "CardRegistry":
        key = os.path.realpath(csv_path or _default_csv())
        reg = cls._cache.get(key)
        if reg is None:
            rows_by_id = load_card_rows(key)
            stats = {cid: _build_card_stats(rows) for cid, rows in rows_by_id.items()}
            reg = cls(stats)
            cls._cache[key] = reg
        return reg

    def get(self, card_id) -> CardStats:
        if card_id is None:
            return _EMPTY_STATS
        return self.stats.get(int(card_id), _EMPTY_STATS)


def _selftest():
    reg = CardRegistry.load()
    assert len(reg.stats) > 1000, "suspiciously few parsed cards"
    assert reg.get(None) is _EMPTY_STATS
    assert reg.get(10 ** 9) is _EMPTY_STATS

    # Ceruledge ex (id 320): known Fire attacker, ex rule.
    ceruledge = reg.get(320)
    assert ceruledge.is_ex, ceruledge
    assert ceruledge.type_sym == FIRE_SYM, ceruledge.type_sym
    assert len(ceruledge.attacks) >= 1, ceruledge.attacks
    for a in ceruledge.attacks:
        assert a.total_cost >= a.fire_count + a.fighting_count

    # cheapest-first ordering holds
    some = next(cid for cid, st in reg.stats.items() if len(st.attacks) == 2)
    st = reg.get(some)
    assert st.attacks[0].total_cost <= st.attacks[1].total_cost, st.attacks

    print(f"card_data self-test PASSED: {len(reg.stats)} cards parsed")


if __name__ == "__main__":
    _selftest()
