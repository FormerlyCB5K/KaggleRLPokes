"""AlphaZero-style policy/value Monte Carlo tree search."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol

import numpy as np


@dataclass(frozen=True)
class SearchConfig:
    """Resolved search switches shared by training and serving."""

    enabled: bool = False
    simulations: int = 800
    max_depth: int = 32
    c_puct: float = 1.5
    dirichlet_alpha: float = 0.3
    dirichlet_epsilon: float = 0.25
    temperature: float = 1.0
    per_decision_seconds: float | None = None
    game_budget_seconds: float | None = None
    seed: int = 20260730

    def validate(self) -> None:
        if self.simulations < 1:
            raise ValueError("simulations must be positive")
        if self.max_depth < 1:
            raise ValueError("max_depth must be positive")
        if not math.isfinite(self.c_puct) or self.c_puct < 0:
            raise ValueError("c_puct must be finite and nonnegative")
        if (
            not math.isfinite(self.dirichlet_alpha)
            or self.dirichlet_alpha <= 0
        ):
            raise ValueError("dirichlet_alpha must be finite and positive")
        if (
            not math.isfinite(self.dirichlet_epsilon)
            or not 0 <= self.dirichlet_epsilon <= 1
        ):
            raise ValueError("dirichlet_epsilon must be in [0, 1]")
        if not math.isfinite(self.temperature) or self.temperature < 0:
            raise ValueError("temperature must be finite and nonnegative")
        if (
            self.per_decision_seconds is not None
            and (
                not math.isfinite(self.per_decision_seconds)
                or self.per_decision_seconds <= 0
            )
        ):
            raise ValueError(
                "per_decision_seconds must be finite and positive when set"
            )
        if (
            self.game_budget_seconds is not None
            and (
                not math.isfinite(self.game_budget_seconds)
                or self.game_budget_seconds <= 0
            )
        ):
            raise ValueError(
                "game_budget_seconds must be finite and positive when set"
            )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionPrior:
    action: tuple[int, ...]
    prior: float


@dataclass(frozen=True)
class PositionEvaluation:
    """Network evaluation from ``player``'s perspective."""

    player: int
    value: float
    actions: tuple[ActionPrior, ...]


@dataclass(frozen=True)
class LeafValue:
    """A resolved leaf value and whether it proves a terminal result."""

    player: int
    value: float
    proven_terminal: bool = False


@dataclass(frozen=True)
class StepResult:
    """Either a traversable child state or a boundary/terminal leaf."""

    child: Any | None = None
    leaf: LeafValue | None = None

    def __post_init__(self) -> None:
        if (self.child is None) == (self.leaf is None):
            raise ValueError("StepResult requires exactly one of child or leaf")


class SearchBackend(Protocol):
    """Game-specific bridge used by the generic tree."""

    def start(self, root_observation: object) -> Any: ...

    def evaluate(self, state: Any) -> PositionEvaluation: ...

    def step(self, state: Any, action: tuple[int, ...]) -> StepResult: ...

    def finish(self) -> None: ...


@dataclass
class _Edge:
    action: tuple[int, ...]
    prior: float
    visits: int = 0
    value_sum: float = 0.0
    child: "_Node | None" = None
    leaf: LeafValue | None = None

    @property
    def q(self) -> float:
        return self.value_sum / self.visits if self.visits else 0.0


@dataclass
class _Node:
    state: Any
    player: int
    value: float
    edges: list[_Edge]

    @property
    def visits(self) -> int:
        return sum(edge.visits for edge in self.edges)


@dataclass(frozen=True)
class SearchResult:
    action: tuple[int, ...]
    actions: tuple[tuple[int, ...], ...]
    visit_counts: tuple[int, ...]
    visit_policy: tuple[float, ...]
    root_value: float
    simulations_completed: int
    elapsed_seconds: float
    max_depth_reached: int
    immediate_terminal_win: bool
    stop_reason: str


def _validate_evaluation(evaluation: PositionEvaluation) -> None:
    if not math.isfinite(evaluation.value) or not -1 <= evaluation.value <= 1:
        raise ValueError("position value must be finite and in [-1, 1]")
    if not evaluation.actions:
        raise ValueError("a nonterminal position must contain at least one action")
    actions = [item.action for item in evaluation.actions]
    if len(actions) != len(set(actions)):
        raise ValueError("position actions must be unique")
    priors = [item.prior for item in evaluation.actions]
    if any(not math.isfinite(value) or value < 0 for value in priors):
        raise ValueError("action priors must be finite and nonnegative")
    if sum(priors) <= 0:
        raise ValueError("at least one action prior must be positive")


def _node(state: Any, evaluation: PositionEvaluation) -> _Node:
    _validate_evaluation(evaluation)
    total = sum(item.prior for item in evaluation.actions)
    return _Node(
        state=state,
        player=int(evaluation.player),
        value=float(evaluation.value),
        edges=[
            _Edge(action=item.action, prior=float(item.prior) / total)
            for item in evaluation.actions
        ],
    )


def _value_for_player(leaf: LeafValue, player: int) -> float:
    return leaf.value if int(leaf.player) == int(player) else -leaf.value


def _choose_edge(node: _Node, c_puct: float) -> _Edge:
    exploration_scale = math.sqrt(max(1, node.visits))
    return max(
        node.edges,
        key=lambda edge: (
            edge.q
            + c_puct
            * edge.prior
            * exploration_scale
            / (1 + edge.visits),
            edge.prior,
            tuple(-value for value in edge.action),
        ),
    )


def _backup(path: list[tuple[_Node, _Edge]], leaf: LeafValue) -> None:
    for node, edge in reversed(path):
        edge.visits += 1
        edge.value_sum += _value_for_player(leaf, node.player)


def _visit_policy(visits: list[int]) -> tuple[float, ...]:
    total = sum(visits)
    if total == 0:
        return tuple(0.0 for _ in visits)
    return tuple(value / total for value in visits)


def _sample_index(
    visits: list[int],
    priors: list[float],
    temperature: float,
    rng: np.random.Generator,
) -> int:
    if temperature <= 1e-8:
        return max(
            range(len(visits)),
            key=lambda index: (visits[index], priors[index], -index),
        )
    counts = np.asarray(visits, dtype=np.float64)
    if not bool(counts.any()):
        weights = np.asarray(priors, dtype=np.float64)
    else:
        weights = np.power(counts, 1.0 / temperature)
    weights /= weights.sum()
    return int(rng.choice(len(visits), p=weights))


class NeuralMCTS:
    """Run one fresh AlphaZero-style tree for each real decision."""

    def __init__(
        self,
        backend: SearchBackend,
        config: SearchConfig,
        *,
        rng: np.random.Generator | None = None,
    ) -> None:
        config.validate()
        self.backend = backend
        self.config = config
        self.rng = rng or np.random.default_rng(config.seed)

    def _expand_edge(self, node: _Node, edge: _Edge) -> None:
        if edge.child is not None or edge.leaf is not None:
            return
        outcome = self.backend.step(node.state, edge.action)
        if outcome.leaf is not None:
            edge.leaf = outcome.leaf
            return
        assert outcome.child is not None
        evaluation = self.backend.evaluate(outcome.child)
        edge.child = _node(outcome.child, evaluation)

    def _apply_root_noise(self, root: _Node) -> None:
        if len(root.edges) <= 1 or self.config.dirichlet_epsilon == 0:
            return
        noise = self.rng.dirichlet(
            np.full(len(root.edges), self.config.dirichlet_alpha)
        )
        epsilon = self.config.dirichlet_epsilon
        for edge, value in zip(root.edges, noise.tolist()):
            edge.prior = (1 - epsilon) * edge.prior + epsilon * value

    def search(
        self,
        root_observation: object,
        *,
        training: bool,
    ) -> SearchResult:
        started = time.perf_counter()
        completed = 0
        max_depth_reached = 0
        stop_reason = "simulation_limit"
        immediate: tuple[int, _Edge] | None = None
        try:
            root_state = self.backend.start(root_observation)
            root = _node(root_state, self.backend.evaluate(root_state))
            if training:
                self._apply_root_noise(root)

            # Probe every legal root edge so a one-action terminal win cannot be
            # hidden behind finite visit allocation.
            for index, edge in enumerate(root.edges):
                self._expand_edge(root, edge)
                if (
                    edge.leaf is not None
                    and edge.leaf.proven_terminal
                    and _value_for_player(edge.leaf, root.player) == 1.0
                ):
                    immediate = (index, edge)
                    break

            if immediate is not None:
                visits = [0 for _ in root.edges]
                visits[immediate[0]] = 1
                return SearchResult(
                    action=immediate[1].action,
                    actions=tuple(edge.action for edge in root.edges),
                    visit_counts=tuple(visits),
                    visit_policy=_visit_policy(visits),
                    root_value=root.value,
                    simulations_completed=0,
                    elapsed_seconds=time.perf_counter() - started,
                    max_depth_reached=1,
                    immediate_terminal_win=True,
                    stop_reason="immediate_terminal_win",
                )

            while completed < self.config.simulations:
                if (
                    self.config.per_decision_seconds is not None
                    and time.perf_counter() - started
                    >= self.config.per_decision_seconds
                ):
                    stop_reason = "wall_clock"
                    break
                node = root
                path: list[tuple[_Node, _Edge]] = []
                depth = 0
                leaf: LeafValue | None = None
                while leaf is None:
                    edge = _choose_edge(node, self.config.c_puct)
                    path.append((node, edge))
                    depth += 1
                    max_depth_reached = max(max_depth_reached, depth)
                    self._expand_edge(node, edge)
                    if edge.leaf is not None:
                        leaf = edge.leaf
                    else:
                        assert edge.child is not None
                        node = edge.child
                        if depth >= self.config.max_depth:
                            leaf = LeafValue(node.player, node.value)
                        elif node.visits == 0:
                            leaf = LeafValue(node.player, node.value)
                _backup(path, leaf)
                completed += 1

            visits = [edge.visits for edge in root.edges]
            priors = [edge.prior for edge in root.edges]
            temperature = self.config.temperature if training else 0.0
            selected = _sample_index(
                visits, priors, temperature, self.rng
            )
            return SearchResult(
                action=root.edges[selected].action,
                actions=tuple(edge.action for edge in root.edges),
                visit_counts=tuple(visits),
                visit_policy=_visit_policy(visits),
                root_value=root.value,
                simulations_completed=completed,
                elapsed_seconds=time.perf_counter() - started,
                max_depth_reached=max_depth_reached,
                immediate_terminal_win=False,
                stop_reason=stop_reason,
            )
        finally:
            self.backend.finish()
