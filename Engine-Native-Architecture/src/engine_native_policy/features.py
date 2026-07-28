"""Typed variable-length feature representation before flat packing."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .spec import DECK_ZONE_WIDTH, LIVE_NUMERIC_WIDTH, MATCH_WIDTH, OPTION_NUMERIC_WIDTH


def _array(
    value: np.ndarray | list, dtype: np.dtype, shape_tail: tuple[int, ...] = ()
) -> np.ndarray:
    arr = np.asarray(value, dtype=dtype)
    if shape_tail and arr.shape[1:] != shape_tail:
        raise ValueError(f"expected trailing shape {shape_tail}, got {arr.shape}")
    return arr


@dataclass(frozen=True)
class FeatureFrame:
    """One unpadded policy decision."""

    tok_card_id: np.ndarray
    tok_role: np.ndarray
    tok_num: np.ndarray
    tok_tool_id: np.ndarray
    tok_senergy_id: np.ndarray
    deck_ids: np.ndarray
    deck_zone: np.ndarray
    glob: np.ndarray
    opt_type: np.ndarray
    opt_card: np.ndarray
    opt_tgt: np.ndarray
    opt_attack: np.ndarray
    opt_ent: np.ndarray
    opt_num: np.ndarray

    def __post_init__(self) -> None:
        integer_fields = (
            "tok_card_id",
            "tok_role",
            "tok_tool_id",
            "tok_senergy_id",
            "deck_ids",
            "opt_type",
            "opt_card",
            "opt_tgt",
            "opt_attack",
            "opt_ent",
        )
        for name in integer_fields:
            object.__setattr__(self, name, _array(getattr(self, name), np.int64))
        object.__setattr__(
            self, "tok_num", _array(self.tok_num, np.float32, (LIVE_NUMERIC_WIDTH,))
        )
        object.__setattr__(
            self, "deck_zone", _array(self.deck_zone, np.float32, (DECK_ZONE_WIDTH,))
        )
        object.__setattr__(self, "glob", _array(self.glob, np.float32))
        object.__setattr__(
            self, "opt_num", _array(self.opt_num, np.float32, (OPTION_NUMERIC_WIDTH,))
        )

        n_tok = len(self.tok_card_id)
        for name in ("tok_role", "tok_num", "tok_tool_id", "tok_senergy_id"):
            if len(getattr(self, name)) != n_tok:
                raise ValueError(f"{name} length does not match entity count")

        if self.glob.shape != (MATCH_WIDTH,):
            raise ValueError(f"glob must have shape ({MATCH_WIDTH},), got {self.glob.shape}")

        if len(self.deck_ids) != len(self.deck_zone):
            raise ValueError("deck_ids and deck_zone lengths differ")

        n_opt = len(self.opt_type)
        for name in ("opt_card", "opt_tgt", "opt_attack", "opt_ent", "opt_num"):
            if len(getattr(self, name)) != n_opt:
                raise ValueError(f"{name} length does not match option count")

    @property
    def n_entities(self) -> int:
        return len(self.tok_card_id)

    @property
    def n_options(self) -> int:
        return len(self.opt_type)
