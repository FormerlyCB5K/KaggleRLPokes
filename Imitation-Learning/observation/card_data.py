"""Ordinary printed static fields (HP, type, weakness, resistance, retreat, rule status).

`meta-card-registry/registry.json` deliberately does NOT carry these -- its own README
states "the later encoder spec owns ordinary live/static features: current/effective
maximum HP, retreat, type, Weakness, Resistance, new_in_play, and zone position." This
module is that ownership, sourced from `Decks/Deck-Builder/EN_Card_Data.csv`.

The CSV has known data-quality issues (per spec 11a's Phase 3 finding): a handful of rows
carry untranslated Japanese source text. One instance directly affects this module -- Dragon
-type Pokemon show their type as the literal kanji '竜' ("dragon") rather than a bracket
code. Handled explicitly below rather than silently dropped.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .types import RULE_STATUSES, TYPE_LETTER

CSV_PATH = (
    Path(__file__).resolve().parents[2] / "Decks" / "Deck-Builder" / "EN_Card_Data.csv"
)

_DRAGON_KANJI = "竜"

_RULE_MAP = {
    "n/a": "none",
    "Pokémon ex": "ex",
    "Mega Pokémon ex": "mega_ex",
    # ACE SPEC is an orthogonal deckbuilding restriction, not a rule-box status -- treated
    # as "none" for the rule-status field (spec 11a's tag catalog already carries
    # `aceSpec`-adjacent info elsewhere when it matters).
    "ACE SPEC": "none",
}


@dataclass(frozen=True)
class CardStatic:
    card_id: int
    name: str
    card_class: str  # "pokemon" | "trainer" | "energy" (from the Stage/Type column)
    subtype: str  # e.g. "Basic Pokémon", "Pokémon Tool", "Stadium"
    hp: int | None
    type_name: str | None  # one of types.TYPES, or None if unparsed/not applicable
    weakness: str | None
    resistance: str | None
    retreat_cost: int | None
    rule_status: str  # one of types.RULE_STATUSES


def parse_type_letter(raw: str | None) -> str | None:
    """Parse a single-type bracket code (e.g. '{P}') or the Dragon-kanji data bug.

    Returns None for anything else (multi-symbol Energy-provision codes, 'n/a', empty) --
    those aren't a Pokemon "type" in the sense this field means, and are the caller's
    concern, not this parser's.
    """
    if not raw or raw == "n/a":
        return None
    if raw == _DRAGON_KANJI:
        return "Dragon"
    stripped = raw.strip("{}")
    if len(stripped) == 1:
        return TYPE_LETTER.get(stripped)
    return None


def _parse_rule(raw: str) -> str:
    status = _RULE_MAP.get(raw)
    if status is None:
        raise ValueError(f"unrecognized Rule value: {raw!r} -- update _RULE_MAP")
    assert status in RULE_STATUSES
    return status


def _parse_int(raw: str) -> int | None:
    if not raw or raw == "n/a":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _card_class(stage_or_type: str) -> str:
    if "Pokémon" in stage_or_type and stage_or_type not in (
        "Pokémon Tool",
    ):
        return "pokemon"
    if "Energy" in stage_or_type:
        return "energy"
    return "trainer"


@lru_cache(maxsize=1)
def load_card_statics() -> dict[int, CardStatic]:
    """One entry per card_id, deduped across that card's multiple move/attack rows.

    Printed static fields (HP/type/weakness/resistance/retreat/rule) are identical across
    every row sharing a card_id -- only Move Name/Cost/Damage/Effect Explanation vary
    per-row, and those belong to spec 11a/11b's tag block, not this module.
    """
    out: dict[int, CardStatic] = {}
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            card_id = _parse_int(row["Card ID"])
            if card_id is None or card_id in out:
                continue
            stage_col = row["Stage (Pokémon)/Type (Energy and Trainer)"]
            out[card_id] = CardStatic(
                card_id=card_id,
                name=row["Card Name"],
                card_class=_card_class(stage_col),
                subtype=stage_col,
                hp=_parse_int(row["HP"]),
                type_name=parse_type_letter(row["Type"]),
                weakness=parse_type_letter(row["Weakness"]),
                resistance=parse_type_letter(row["Resistance (Type)"]),
                retreat_cost=_parse_int(row["Retreat"]),
                rule_status=_parse_rule(row["Rule"]),
            )
    return out


def get_card_static(card_id: int) -> CardStatic | None:
    return load_card_statics().get(card_id)


@dataclass(frozen=True)
class MoveText:
    name: str
    cost: str | None
    damage: float | None
    text: str


def _parse_damage(raw: str | None) -> float | None:
    if not raw or raw == "n/a":
        return None
    import re
    m = re.match(r"(\d+)", raw.replace("+", ""))
    return float(m.group(1)) if m else None


@lru_cache(maxsize=1)
def _load_all_moves() -> dict[int, tuple[list[MoveText], list[MoveText]]]:
    """card_id -> (attacks, abilities), in printed row order. Feeds Deliverable B
    (`pokemon_tag_catalog.tag_unseen_pokemon`) for any Pokemon outside the 115-card meta
    vocabulary -- the meta cards use `pokemon_meta_tags.META_TAGS` instead, sourced from
    the registry, not this CSV."""
    out: dict[int, tuple[list[MoveText], list[MoveText]]] = {}
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            card_id = _parse_int(row["Card ID"])
            if card_id is None:
                continue
            stage_col = row["Stage (Pokémon)/Type (Energy and Trainer)"]
            if _card_class(stage_col) != "pokemon":
                continue
            move_name = row["Move Name"]
            if move_name == "n/a":
                continue
            move = MoveText(
                name=move_name,
                cost=row["Cost"] if row["Cost"] != "n/a" else None,
                damage=_parse_damage(row["Damage"]),
                text=row["Effect Explanation"] if row["Effect Explanation"] != "n/a" else "",
            )
            attacks, abilities = out.setdefault(card_id, ([], []))
            (abilities if move_name.startswith("[Ability]") else attacks).append(move)
    return out


def get_card_moves(card_id: int) -> tuple[list[MoveText], list[MoveText]]:
    """(attacks, abilities) for a card, in printed order. Empty lists if the card_id has no
    Pokemon-class rows in the CSV."""
    return _load_all_moves().get(card_id, ([], []))


@lru_cache(maxsize=1)
def _load_trainer_energy_text() -> dict[int, str]:
    """card_id -> full effect text, for Trainer/Energy cards only. Unlike Pokemon's
    Move Name/Cost/Damage split, a Trainer/Energy card's whole effect lives in one
    `Effect Explanation` cell (`Move Name` is `n/a`/empty for these rows) -- feeds
    Deliverable B (`trainer_energy_tag_catalog.tag_unseen_trainer_energy`) for any card
    outside the 117-card meta vocabulary."""
    out: dict[int, str] = {}
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            card_id = _parse_int(row["Card ID"])
            if card_id is None:
                continue
            stage_col = row["Stage (Pokémon)/Type (Energy and Trainer)"]
            if _card_class(stage_col) not in ("trainer", "energy"):
                continue
            text = row["Effect Explanation"]
            out[card_id] = text if text and text != "n/a" else ""
    return out


def get_trainer_energy_text(card_id: int) -> str | None:
    """Full effect text for a Trainer/Energy card_id, or None if it isn't one."""
    return _load_trainer_energy_text().get(card_id)
