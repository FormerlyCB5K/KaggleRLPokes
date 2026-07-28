"""Frozen mechanical table boundary."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch

from .spec import ATTACK_VOCAB_SIZE, CARD_VOCAB_SIZE, EFFECT_WIDTH, STAT_WIDTH


@dataclass(frozen=True)
class FrozenTables:
    """Frozen mechanics consumed by the learned projections."""

    stat: torch.Tensor
    attack: torch.Tensor
    ability: torch.Tensor
    play: torch.Tensor
    prize: torch.Tensor
    attack_slot: torch.Tensor
    provisional: bool = False

    def validate(self) -> None:
        expected = {
            "stat": ((CARD_VOCAB_SIZE, STAT_WIDTH), torch.float32),
            "attack": ((CARD_VOCAB_SIZE, 2, EFFECT_WIDTH), torch.float32),
            "ability": ((CARD_VOCAB_SIZE, EFFECT_WIDTH), torch.float32),
            "play": ((CARD_VOCAB_SIZE, EFFECT_WIDTH), torch.float32),
            "prize": ((CARD_VOCAB_SIZE, 1), torch.float32),
            "attack_slot": ((ATTACK_VOCAB_SIZE,), torch.int64),
        }
        for name, (shape, dtype) in expected.items():
            value = getattr(self, name)
            if tuple(value.shape) != shape:
                raise ValueError(
                    f"{name}: expected shape {shape}, got {tuple(value.shape)}"
                )
            if value.dtype != dtype:
                raise ValueError(f"{name}: expected dtype {dtype}, got {value.dtype}")
        if self.attack_slot.numel() and not bool(
            ((self.attack_slot == 0) | (self.attack_slot == 1)).all()
        ):
            raise ValueError("attack_slot values must be 0 or 1")

    @classmethod
    def placeholder(cls) -> "FrozenTables":
        tables = cls(
            stat=torch.zeros(CARD_VOCAB_SIZE, STAT_WIDTH, dtype=torch.float32),
            attack=torch.zeros(
                CARD_VOCAB_SIZE, 2, EFFECT_WIDTH, dtype=torch.float32
            ),
            ability=torch.zeros(
                CARD_VOCAB_SIZE, EFFECT_WIDTH, dtype=torch.float32
            ),
            play=torch.zeros(CARD_VOCAB_SIZE, EFFECT_WIDTH, dtype=torch.float32),
            prize=torch.zeros(CARD_VOCAB_SIZE, 1, dtype=torch.float32),
            attack_slot=torch.zeros(ATTACK_VOCAB_SIZE, dtype=torch.int64),
            provisional=True,
        )
        tables.validate()
        return tables

    @classmethod
    def load(cls, path: str | Path) -> "FrozenTables":
        payload = torch.load(Path(path), map_location="cpu", weights_only=True)
        tables = cls(
            stat=payload["STAT"].to(torch.float32),
            attack=payload["ATK"].to(torch.float32),
            ability=payload["ABL"].to(torch.float32),
            play=payload["PLAY"].to(torch.float32),
            prize=payload["PRIZE"].to(torch.float32),
            attack_slot=payload["ATTACK_SLOT"].to(torch.int64),
            provisional=bool(payload.get("provisional", False)),
        )
        tables.validate()
        return tables

    def state_payload(self) -> dict[str, torch.Tensor | bool]:
        self.validate()
        return {
            "STAT": self.stat,
            "ATK": self.attack,
            "ABL": self.ability,
            "PLAY": self.play,
            "PRIZE": self.prize,
            "ATTACK_SLOT": self.attack_slot,
            "provisional": self.provisional,
        }
