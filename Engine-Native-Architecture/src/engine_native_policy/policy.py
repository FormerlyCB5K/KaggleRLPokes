"""Minimal serving wrapper over the pure featurizer and model."""

from __future__ import annotations

from collections.abc import Sequence

import torch

from .actions import select_options
from .featurize import featurize
from .flat import decode_batch, encode
from .model import EngineNativeNet, PolicyOutput


class EngineNativePolicy:
    """Rank the legal options already supplied by the game engine."""

    def __init__(
        self,
        network: EngineNativeNet,
        deck: Sequence[int],
        *,
        device: str | torch.device = "cpu",
        allow_provisional_tables: bool = False,
    ) -> None:
        if network.card.provisional and not allow_provisional_tables:
            raise ValueError(
                "provisional frozen tables are architecture-only; "
                "set allow_provisional_tables=True only for tests"
            )
        self.network = network.to(device).eval()
        self.deck = tuple(int(card_id) for card_id in deck)
        self.device = torch.device(device)

    @torch.no_grad()
    def evaluate(self, observation: object) -> tuple[list[int], PolicyOutput]:
        frame = featurize(observation, self.deck)
        batch = {
            name: value.to(self.device)
            for name, value in decode_batch(encode(frame)).items()
        }
        output = self.network(batch)
        select = getattr(observation, "select")
        choices = select_options(
            output.logits[0],
            output.incl[0],
            frame.n_options,
            int(select.minCount),
            int(select.maxCount),
        )
        return choices, output

    @torch.no_grad()
    def choose(self, observation: object) -> list[int]:
        choices, _ = self.evaluate(observation)
        return choices
