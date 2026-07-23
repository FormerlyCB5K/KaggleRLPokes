"""Consumer loader for the generated exact-card-ID semantic registry."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load_registry() -> dict[str, Any]:
    return json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_formulas() -> dict[str, Any]:
    return json.loads((ROOT / "formulas.json").read_text(encoding="utf-8"))


def is_meta_card(card_id: int) -> bool:
    return str(int(card_id)) in load_registry()["cards"]


def get_card(card_id: int) -> dict[str, Any] | None:
    return load_registry()["cards"].get(str(int(card_id)))


def get_formula(formula_key: str) -> dict[str, Any] | None:
    return load_formulas()["formulas"].get(formula_key)


def formulas_for_card(card_id: int) -> list[dict[str, Any]]:
    keys = load_formulas()["affected_cards"].get(str(int(card_id)), [])
    return [load_formulas()["formulas"][key] for key in keys]


def unseen_fallback_contract(card_id: int) -> dict[str, Any]:
    if is_meta_card(card_id):
        raise ValueError(f"card_id {card_id} is present in the exact meta registry")
    return load_registry()["unseen_card_fallback"]
