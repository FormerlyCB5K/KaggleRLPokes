from __future__ import annotations

import numpy as np
import torch

from engine_native_policy.features import FeatureFrame
from engine_native_policy.flat import FIELD_OFFSETS, FLAT_DIM, decode_batch, encode
from engine_native_policy.spec import (
    ENTITY_CONCEPTUAL_TOTAL,
    LIVE_NUMERIC_WIDTH,
    MAX_OPTIONS,
    MAX_TOKENS,
    OPTION_CONCEPTUAL_TOTAL,
    TRANSFORMER_TOKENS,
)
from engine_native_policy.tables import FrozenTables
from engine_native_policy.vocab import (
    COMPARATORS,
    CONDITION_SUBJECTS,
    CONDITION_TYPES,
    EFFECT_LAYOUT,
    EFFECT_TAGS,
    STAT_LAYOUT,
)


def frame_with_overflow() -> FeatureFrame:
    return FeatureFrame(
        tok_card_id=np.arange(1, 42),
        tok_role=np.ones(41),
        tok_num=np.zeros((41, LIVE_NUMERIC_WIDTH), dtype=np.float32),
        tok_tool_id=np.zeros(41),
        tok_senergy_id=np.zeros(41),
        deck_ids=np.arange(1, 61),
        deck_zone=np.zeros((60, 4), dtype=np.float32),
        glob=np.zeros(18, dtype=np.float32),
        opt_type=np.zeros(65),
        opt_card=np.arange(65),
        opt_tgt=np.zeros(65),
        opt_attack=np.zeros(65),
        opt_ent=np.full(65, -1),
        opt_num=np.zeros((65, 4), dtype=np.float32),
    )


def test_locked_dimensions_and_offsets() -> None:
    assert FLAT_DIM == 2239
    assert ENTITY_CONCEPTUAL_TOTAL == 1280
    assert OPTION_CONCEPTUAL_TOTAL == 641
    assert TRANSFORMER_TOKENS == 46
    assert FIELD_OFFSETS == {
        "tok_card_id": (0, 40),
        "tok_role": (40, 80),
        "tok_num": (80, 1160),
        "tok_mask": (1160, 1200),
        "deck_ids": (1200, 1260),
        "glob": (1260, 1278),
        "opt_type": (1278, 1342),
        "opt_card": (1342, 1406),
        "opt_tgt": (1406, 1470),
        "opt_attack": (1470, 1534),
        "opt_ent": (1534, 1598),
        "opt_num": (1598, 1854),
        "opt_mask": (1854, 1918),
        "n_options": (1918, 1919),
        "deck_zone": (1919, 2159),
        "tok_tool_id": (2159, 2199),
        "tok_senergy_id": (2199, 2239),
    }


def test_encode_keeps_first_40_entities_and_first_64_options() -> None:
    row = encode(frame_with_overflow())
    assert row.shape == (2239,)
    assert row.dtype == np.float32
    batch = decode_batch(row)
    assert batch["tok_mask"].sum().item() == MAX_TOKENS
    assert batch["tok_card_id"][0, -1].item() == 40
    assert batch["opt_mask"].sum().item() == MAX_OPTIONS
    assert batch["n_options"].item() == MAX_OPTIONS


def test_decode_restores_index_mask_and_numeric_dtypes() -> None:
    batch = decode_batch(encode(frame_with_overflow()))
    assert batch["tok_card_id"].dtype == torch.int64
    assert batch["opt_ent"].dtype == torch.int64
    assert batch["tok_mask"].dtype == torch.bool
    assert batch["opt_mask"].dtype == torch.bool
    assert batch["tok_num"].dtype == torch.float32
    assert batch["tok_num"].shape == (1, 40, 27)
    assert batch["deck_zone"].shape == (1, 60, 4)
    assert batch["opt_num"].shape == (1, 64, 4)


def test_placeholder_tables_have_exact_contract() -> None:
    tables = FrozenTables.placeholder()
    tables.validate()
    assert tables.provisional
    assert tables.stat.shape == (1300, 79)
    assert tables.attack.shape == (1300, 2, 130)
    assert tables.ability.shape == (1300, 130)
    assert tables.play.shape == (1300, 130)
    assert tables.prize.shape == (1300, 1)
    assert tables.attack_slot.shape == (1600,)


def test_frozen_vocabularies_and_layouts_are_pinned() -> None:
    assert len(EFFECT_TAGS) == 56
    assert len(CONDITION_TYPES) == 24
    assert len(CONDITION_SUBJECTS) == 19
    assert len(COMPARATORS) == 6
    assert STAT_LAYOUT[-1] == ("has_second_attack", 78, 79)
    assert EFFECT_LAYOUT[-2:] == (
        ("fetch_count", 128, 129),
        ("play_cost", 129, 130),
    )
