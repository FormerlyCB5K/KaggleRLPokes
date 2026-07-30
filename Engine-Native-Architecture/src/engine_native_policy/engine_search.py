"""Competition-engine bridge for conservative public-information MCTS."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

import torch
from cg_download import api as default_search_api

from .actions import select_options
from .mcts import (
    ActionPrior,
    LeafValue,
    PositionEvaluation,
    StepResult,
)
from .spec import OptionKind
from .vocab import EFFECT_TAGS

if TYPE_CHECKING:
    from .features import FeatureFrame
    from .policy import EngineNativePolicy


_HIDDEN_EFFECT_TAGS = frozenset(
    {
        "draw",
        "draw_mag",
        "search_deck_to_hand",
        "search_deck_to_field",
        "deck_peek_reorder",
        "disrupt_opp_hand",
        "mill_opp",
        "mill_self",
        "dmg_scale_coin",
        "coin_flip",
    }
)
_HIDDEN_EFFECT_COLUMNS = tuple(
    20 + EFFECT_TAGS.index(name) for name in sorted(_HIDDEN_EFFECT_TAGS)
)
_HIDDEN_LOG_NAMES = frozenset(
    {"SHUFFLE", "DRAW", "DRAW_REVERSE", "MOVE_CARD_REVERSE", "COIN"}
)
_HIDDEN_AREA_NAMES = frozenset({"DECK", "PRIZE"})


def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    if name is not None:
        return str(name)
    return str(value).rsplit(".", 1)[-1].upper()


def _repeat_to_length(values: Sequence[int], length: int) -> list[int]:
    if length <= 0:
        return []
    if not values:
        raise ValueError("cannot predict hidden cards from an empty deck")
    return [int(values[index % len(values)]) for index in range(length)]


class NativeSearchBackend:
    """Adapt native ``search_begin/search_step`` to the generic tree.

    Hidden identities are deterministic placeholders only. Search stops before
    they can legitimately influence a backed-up branch.
    """

    def __init__(
        self,
        policy: "EngineNativePolicy",
        *,
        search_api: object | None = None,
    ) -> None:
        self.policy = policy
        self.api = search_api or default_search_api
        self.root_player: int | None = None
        self.started = False
        self._evaluations: dict[int, PositionEvaluation] = {}
        self._frames: dict[int, FeatureFrame] = {}

    @staticmethod
    def _key(state: Any) -> int:
        return int(getattr(state, "searchId", id(state)))

    def _pokemon_fallback(self) -> int:
        stat = self.policy.network.card.STAT
        for card_id in self.policy.deck:
            if 0 <= card_id < stat.shape[0] and float(stat[card_id, 0]) > 0:
                return int(card_id)
        return int(self.policy.deck[0])

    def _hidden_inputs(self, observation: object) -> dict[str, list[int]]:
        current = getattr(observation, "current")
        my = int(current.yourIndex)
        opponent = 1 - my
        mine = current.players[my]
        theirs = current.players[opponent]
        fallback = list(self.policy.deck)
        opponent_active: list[int] = []
        active = list(theirs.active or [])
        if active and active[0] is None:
            opponent_active = [self._pokemon_fallback()]
        return {
            "your_deck": _repeat_to_length(fallback, int(mine.deckCount)),
            "your_prize": _repeat_to_length(
                fallback, len(mine.prize or [])
            ),
            "opponent_deck": _repeat_to_length(
                fallback, int(theirs.deckCount)
            ),
            "opponent_prize": _repeat_to_length(
                fallback, len(theirs.prize or [])
            ),
            "opponent_hand": _repeat_to_length(
                fallback, int(theirs.handCount)
            ),
            "opponent_active": opponent_active,
        }

    def start(self, root_observation: object) -> Any:
        current = getattr(root_observation, "current", None)
        if current is None:
            raise ValueError("search root requires a current engine state")
        self.root_player = int(current.yourIndex)
        state = self.api.search_begin(
            root_observation,
            manual_coin=True,
            **self._hidden_inputs(root_observation),
        )
        self.started = True
        return state

    def evaluate(self, state: Any) -> PositionEvaluation:
        key = self._key(state)
        cached = self._evaluations.get(key)
        if cached is not None:
            return cached
        observation = state.observation
        frame, output = self.policy.infer(observation)
        select = observation.select
        if select is None or frame.n_options < 1:
            raise RuntimeError("nonterminal search state has no legal options")
        if int(select.maxCount) > 1:
            action = tuple(
                select_options(
                    output.logits[0],
                    output.incl[0],
                    frame.n_options,
                    int(select.minCount),
                    int(select.maxCount),
                )
            )
            actions = (ActionPrior(action, 1.0),)
        else:
            probabilities = torch.softmax(
                output.logits[0, : frame.n_options].float(), dim=0
            ).detach().cpu()
            actions = tuple(
                ActionPrior((index,), float(probabilities[index]))
                for index in range(frame.n_options)
            )
        evaluation = PositionEvaluation(
            player=int(observation.current.yourIndex),
            value=float(output.value[0].detach().float().cpu()),
            actions=actions,
        )
        self._evaluations[key] = evaluation
        self._frames[key] = frame
        return evaluation

    def _parent_leaf(self, state: Any) -> LeafValue:
        evaluation = self.evaluate(state)
        return LeafValue(evaluation.player, evaluation.value)

    def _effect_crosses_hidden_boundary(
        self, state: Any, action: tuple[int, ...]
    ) -> bool:
        if len(action) != 1:
            return False
        self.evaluate(state)
        frame = self._frames[self._key(state)]
        index = action[0]
        if index < 0 or index >= frame.n_options:
            raise ValueError("search action is outside the legal option list")
        kind = OptionKind(int(frame.opt_type[index]))
        if kind == OptionKind.END:
            return True
        card_id = int(frame.opt_card[index])
        card = self.policy.network.card
        if kind == OptionKind.ATTACK:
            attack_id = int(frame.opt_attack[index])
            slot = int(card.ATTACK_SLOT[attack_id].detach().cpu())
            effect = card.ATK[card_id, slot]
        elif kind in (OptionKind.ABILITY, OptionKind.SKILL):
            effect = card.ABL[card_id]
        elif kind == OptionKind.PLAY:
            effect = card.PLAY[card_id]
        else:
            return False
        values = effect[list(_HIDDEN_EFFECT_COLUMNS)]
        return bool((values != 0).any().detach().cpu())

    @staticmethod
    def _terminal_leaf(observation: object, player: int) -> LeafValue | None:
        current = getattr(observation, "current", None)
        if current is None or int(current.result) < 0:
            return None
        result = int(current.result)
        value = 0.0 if result not in (0, 1) else (
            1.0 if result == player else -1.0
        )
        return LeafValue(player, value, proven_terminal=True)

    def _post_step_hidden(self, observation: object) -> bool:
        current = getattr(observation, "current", None)
        select = getattr(observation, "select", None)
        if current is None:
            return True
        if (
            self.root_player is not None
            and int(current.yourIndex) != self.root_player
        ):
            return True
        for log in getattr(observation, "logs", None) or []:
            if _enum_name(log.type) in _HIDDEN_LOG_NAMES:
                return True
            if _enum_name(log.type) == "MOVE_CARD":
                if (
                    _enum_name(getattr(log, "fromArea", None))
                    in _HIDDEN_AREA_NAMES
                    or _enum_name(getattr(log, "toArea", None))
                    in _HIDDEN_AREA_NAMES
                ):
                    return True
        if select is None:
            return True
        if getattr(select, "deck", None) is not None:
            return True
        if getattr(current, "looking", None) is not None:
            return True
        for option in select.option or []:
            if _enum_name(getattr(option, "area", None)) in _HIDDEN_AREA_NAMES:
                return True
        return False

    @staticmethod
    def _is_coin_prompt(observation: object) -> bool:
        select = getattr(observation, "select", None)
        return (
            select is not None
            and _enum_name(getattr(select, "context", None)) == "COIN_HEAD"
        )

    def step(self, state: Any, action: tuple[int, ...]) -> StepResult:
        parent = self._parent_leaf(state)
        if self._effect_crosses_hidden_boundary(state, action):
            return StepResult(leaf=parent)
        child = self.api.search_step(int(state.searchId), list(action))
        terminal = self._terminal_leaf(child.observation, parent.player)
        if terminal is not None:
            return StepResult(leaf=terminal)
        if self._is_coin_prompt(child.observation):
            evaluation = self.evaluate(child)
            return StepResult(
                leaf=LeafValue(evaluation.player, evaluation.value)
            )
        if self._post_step_hidden(child.observation):
            return StepResult(leaf=parent)
        return StepResult(child=child)

    def finish(self) -> None:
        try:
            if self.started:
                self.api.search_end()
        finally:
            self.started = False
            self._evaluations.clear()
            self._frames.clear()
