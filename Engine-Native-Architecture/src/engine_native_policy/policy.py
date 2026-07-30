"""Minimal serving wrapper over the pure featurizer and model."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

import numpy as np
import torch

from .actions import select_options
from .features import FeatureFrame
from .featurize import featurize
from .flat import decode_batch, encode
from .mcts import NeuralMCTS, SearchConfig, SearchResult
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
        search_config: SearchConfig | None = None,
        search_api: object | None = None,
    ) -> None:
        if network.card.provisional and not allow_provisional_tables:
            raise ValueError(
                "provisional frozen tables are architecture-only; "
                "set allow_provisional_tables=True only for tests"
            )
        self.network = network.to(device).eval()
        self.deck = tuple(int(card_id) for card_id in deck)
        self.device = torch.device(device)
        self.search_config = search_config or SearchConfig(enabled=False)
        self.search_config.validate()
        if (
            self.search_config.enabled
            and self.network.config.value_activation != "tanh"
        ):
            raise ValueError(
                "tree search requires a tanh-bounded value head"
            )
        self.search_api = search_api
        self._search_rng = np.random.default_rng(self.search_config.seed)
        self._search_seconds_used = 0.0

    def _remaining_search_seconds(self) -> float | None:
        budget = self.search_config.game_budget_seconds
        if budget is None:
            return None
        return max(0.0, budget - self._search_seconds_used)

    def _effective_search_config(self) -> SearchConfig | None:
        remaining = self._remaining_search_seconds()
        if remaining is not None and remaining <= 0:
            return None
        per_decision = self.search_config.per_decision_seconds
        if remaining is not None:
            per_decision = (
                remaining
                if per_decision is None
                else min(per_decision, remaining)
            )
        return replace(
            self.search_config,
            per_decision_seconds=per_decision,
        )

    @torch.no_grad()
    def infer(self, observation: object) -> tuple[FeatureFrame, PolicyOutput]:
        frame = featurize(observation, self.deck)
        batch = {
            name: value.to(self.device)
            for name, value in decode_batch(encode(frame)).items()
        }
        output = self.network(batch)
        return frame, output

    @torch.no_grad()
    def evaluate(self, observation: object) -> tuple[list[int], PolicyOutput]:
        frame, output = self.infer(observation)
        select = getattr(observation, "select")
        choices = select_options(
            output.logits[0],
            output.incl[0],
            frame.n_options,
            int(select.minCount),
            int(select.maxCount),
        )
        return choices, output

    def search(
        self, observation: object, *, training: bool = False
    ) -> SearchResult:
        if not self.search_config.enabled:
            raise RuntimeError("tree search is disabled for this policy")
        effective_config = self._effective_search_config()
        if effective_config is None:
            raise RuntimeError("tree-search game budget is exhausted")
        from .engine_search import NativeSearchBackend

        backend = NativeSearchBackend(self, search_api=self.search_api)
        result = NeuralMCTS(
            backend,
            effective_config,
            rng=self._search_rng,
        ).search(observation, training=training)
        self._search_seconds_used += result.elapsed_seconds
        return result

    @torch.no_grad()
    def choose(self, observation: object) -> list[int]:
        if (
            self.search_config.enabled
            and self._effective_search_config() is not None
        ):
            return list(self.search(observation, training=False).action)
        choices, _ = self.evaluate(observation)
        return choices
