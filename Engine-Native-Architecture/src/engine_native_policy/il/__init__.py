"""Engine-native behavior-cloning data pipeline."""

from .replay import (
    DECLARED_SKIP_REASONS,
    ReplayContractError,
    ReplayDecision,
    extract_submitted_decks,
    iter_episode_decisions,
)
from .targets import DecisionTarget, TargetContractError, build_target
from .trainer import TrainingConfig, run_training

__all__ = [
    "DECLARED_SKIP_REASONS",
    "DecisionTarget",
    "ReplayContractError",
    "ReplayDecision",
    "TargetContractError",
    "TrainingConfig",
    "build_target",
    "extract_submitted_decks",
    "iter_episode_decisions",
    "run_training",
]
