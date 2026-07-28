"""Exact float32[2239] interchange layout."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import torch

from .features import FeatureFrame
from .spec import (
    DECK_ZONE_WIDTH,
    LIVE_NUMERIC_WIDTH,
    MATCH_WIDTH,
    MAX_DECK,
    MAX_OPTIONS,
    MAX_TOKENS,
    OPTION_NUMERIC_WIDTH,
)

_FIELD_SIZES = (
    ("tok_card_id", MAX_TOKENS),
    ("tok_role", MAX_TOKENS),
    ("tok_num", MAX_TOKENS * LIVE_NUMERIC_WIDTH),
    ("tok_mask", MAX_TOKENS),
    ("deck_ids", MAX_DECK),
    ("glob", MATCH_WIDTH),
    ("opt_type", MAX_OPTIONS),
    ("opt_card", MAX_OPTIONS),
    ("opt_tgt", MAX_OPTIONS),
    ("opt_attack", MAX_OPTIONS),
    ("opt_ent", MAX_OPTIONS),
    ("opt_num", MAX_OPTIONS * OPTION_NUMERIC_WIDTH),
    ("opt_mask", MAX_OPTIONS),
    ("n_options", 1),
    ("deck_zone", MAX_DECK * DECK_ZONE_WIDTH),
    ("tok_tool_id", MAX_TOKENS),
    ("tok_senergy_id", MAX_TOKENS),
)

FIELD_OFFSETS: dict[str, tuple[int, int]] = {}
_cursor = 0
for _name, _size in _FIELD_SIZES:
    FIELD_OFFSETS[_name] = (_cursor, _cursor + _size)
    _cursor += _size
FLAT_DIM = _cursor

assert FLAT_DIM == 2239
assert FIELD_OFFSETS["deck_zone"] == (1919, 2159)
assert FIELD_OFFSETS["tok_senergy_id"] == (2199, 2239)


def _slice(out: np.ndarray, name: str) -> np.ndarray:
    start, end = FIELD_OFFSETS[name]
    return out[start:end]


def encode(frame: FeatureFrame) -> np.ndarray:
    """Pack one variable-length frame, preserving the implementation's first-N behavior."""

    out = np.zeros(FLAT_DIM, dtype=np.float32)

    n_tok = min(frame.n_entities, MAX_TOKENS)
    _slice(out, "tok_card_id")[:n_tok] = frame.tok_card_id[:n_tok]
    _slice(out, "tok_role")[:n_tok] = frame.tok_role[:n_tok]
    _slice(out, "tok_num")[: n_tok * LIVE_NUMERIC_WIDTH] = frame.tok_num[
        :n_tok
    ].reshape(-1)
    _slice(out, "tok_mask")[:n_tok] = 1.0
    _slice(out, "tok_tool_id")[:n_tok] = frame.tok_tool_id[:n_tok]
    _slice(out, "tok_senergy_id")[:n_tok] = frame.tok_senergy_id[:n_tok]

    n_deck = min(len(frame.deck_ids), MAX_DECK)
    _slice(out, "deck_ids")[:n_deck] = frame.deck_ids[:n_deck]
    _slice(out, "deck_zone")[: n_deck * DECK_ZONE_WIDTH] = frame.deck_zone[
        :n_deck
    ].reshape(-1)
    _slice(out, "glob")[:] = frame.glob

    n_opt = min(frame.n_options, MAX_OPTIONS)
    for name in ("opt_type", "opt_card", "opt_tgt", "opt_attack", "opt_ent"):
        _slice(out, name)[:n_opt] = getattr(frame, name)[:n_opt]
    _slice(out, "opt_num")[: n_opt * OPTION_NUMERIC_WIDTH] = frame.opt_num[
        :n_opt
    ].reshape(-1)
    _slice(out, "opt_mask")[:n_opt] = 1.0
    _slice(out, "n_options")[0] = n_opt
    return out


def encode_many(frames: Iterable[FeatureFrame]) -> np.ndarray:
    rows = [encode(frame) for frame in frames]
    if not rows:
        return np.empty((0, FLAT_DIM), dtype=np.float32)
    return np.stack(rows)


def decode_batch(rows: np.ndarray | torch.Tensor) -> dict[str, torch.Tensor]:
    """Decode flat rows into typed model tensors."""

    tensor = torch.as_tensor(rows, dtype=torch.float32)
    if tensor.ndim == 1:
        tensor = tensor.unsqueeze(0)
    if tensor.ndim != 2 or tensor.shape[1] != FLAT_DIM:
        raise ValueError(f"expected (B, {FLAT_DIM}), got {tuple(tensor.shape)}")

    def field(name: str) -> torch.Tensor:
        start, end = FIELD_OFFSETS[name]
        return tensor[:, start:end]

    return {
        "tok_card_id": field("tok_card_id").to(torch.int64),
        "tok_role": field("tok_role").to(torch.int64),
        "tok_num": field("tok_num").reshape(
            -1, MAX_TOKENS, LIVE_NUMERIC_WIDTH
        ),
        "tok_mask": field("tok_mask").to(torch.bool),
        "tok_tool_id": field("tok_tool_id").to(torch.int64),
        "tok_senergy_id": field("tok_senergy_id").to(torch.int64),
        "deck_ids": field("deck_ids").to(torch.int64),
        "deck_zone": field("deck_zone").reshape(
            -1, MAX_DECK, DECK_ZONE_WIDTH
        ),
        "glob": field("glob"),
        "opt_type": field("opt_type").to(torch.int64),
        "opt_card": field("opt_card").to(torch.int64),
        "opt_tgt": field("opt_tgt").to(torch.int64),
        "opt_attack": field("opt_attack").to(torch.int64),
        "opt_ent": field("opt_ent").to(torch.int64),
        "opt_num": field("opt_num").reshape(
            -1, MAX_OPTIONS, OPTION_NUMERIC_WIDTH
        ),
        "opt_mask": field("opt_mask").to(torch.bool),
        "n_options": field("n_options").squeeze(-1).to(torch.int64),
    }
