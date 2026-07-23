"""Bootstraps imports of `meta-card-registry`'s `registry.py`/`card_ids.py`.

That directory isn't a package (no `__init__.py`, per its own README -- it expects
consumers to import the two modules directly), so this inserts it onto `sys.path` once
and re-exports what this package needs.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REGISTRY_DIR = Path(__file__).resolve().parents[1] / "meta-card-registry"
if str(_REGISTRY_DIR) not in sys.path:
    sys.path.insert(0, str(_REGISTRY_DIR))

import card_ids as _card_ids  # noqa: E402
import registry as _registry  # noqa: E402

ALL_CARD_IDS = _card_ids.ALL_CARD_IDS
POKEMON_CARD_IDS = _card_ids.POKEMON_CARD_IDS
TRAINER_CARD_IDS = _card_ids.TRAINER_CARD_IDS
ENERGY_CARD_IDS = _card_ids.ENERGY_CARD_IDS
CARD_ID_TO_INDEX = _card_ids.CARD_ID_TO_INDEX
UNK_CARD_INDEX = len(ALL_CARD_IDS)  # one shared slot past the last real index

get_card = _registry.get_card
is_meta_card = _registry.is_meta_card
formulas_for_card = _registry.formulas_for_card
