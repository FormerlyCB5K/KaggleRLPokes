"""Direct extraction from sanitized Kaggle episode JSON."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


DECLARED_SKIP_REASONS = (
    "no_action",
    "no_current",
    "no_select",
    "unusable",
    "fewer_than_two_options",
    "option_overflow",
)


class ReplayContractError(ValueError):
    """A sanitized episode violates the locked replay contract."""


@dataclass(frozen=True)
class ReplayDecision:
    """One action paired with the observation it answers."""

    observation_json: dict[str, Any]
    action: tuple[int, ...]
    deck: tuple[int, ...]
    player: int
    response_step: int


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _player_entry(step: Any, player: int) -> dict[str, Any] | None:
    if not isinstance(step, list) or player >= len(step):
        return None
    entry = step[player]
    return entry if isinstance(entry, dict) else None


def extract_submitted_decks(
    episode: dict[str, Any], *, n_players: int = 2
) -> tuple[tuple[int, ...], ...]:
    """Find one non-conflicting 60-card submission for each player."""

    steps = episode.get("steps")
    if not isinstance(steps, list):
        raise ReplayContractError("episode.steps must be a list")

    candidates: list[set[tuple[int, ...]]] = [set() for _ in range(n_players)]
    for step in steps:
        for player in range(n_players):
            entry = _player_entry(step, player)
            if entry is None:
                continue
            action = entry.get("action")
            if (
                isinstance(action, list)
                and len(action) == 60
                and all(_is_integer(card_id) for card_id in action)
            ):
                candidates[player].add(tuple(action))

    decks: list[tuple[int, ...]] = []
    for player, found in enumerate(candidates):
        if not found:
            raise ReplayContractError(
                f"player {player} has no authoritative 60-card deck submission"
            )
        if len(found) != 1:
            raise ReplayContractError(
                f"player {player} has conflicting 60-card deck submissions"
            )
        decks.append(next(iter(found)))
    return tuple(decks)


def iter_episode_decisions(
    episode: dict[str, Any],
    *,
    skip_counts: Counter[str] | None = None,
    n_players: int = 2,
) -> Iterator[ReplayDecision]:
    """Yield all usable decisions and count every declared non-example category."""

    counts = skip_counts if skip_counts is not None else Counter()
    decks = extract_submitted_decks(episode, n_players=n_players)
    steps = episode.get("steps")
    assert isinstance(steps, list)

    for response_step in range(1, len(steps)):
        response = steps[response_step]
        previous = steps[response_step - 1]
        for player in range(n_players):
            response_entry = _player_entry(response, player)
            action = response_entry.get("action") if response_entry is not None else None
            if not action:
                counts["no_action"] += 1
                continue
            if not isinstance(action, list):
                raise ReplayContractError(
                    f"step {response_step} player {player}: action must be a list"
                )

            previous_entry = _player_entry(previous, player)
            observation = (
                previous_entry.get("observation")
                if previous_entry is not None
                else None
            )
            if not isinstance(observation, dict) or not observation.get("current"):
                counts["no_current"] += 1
                continue
            select = observation.get("select")
            if not isinstance(select, dict):
                counts["no_select"] += 1
                continue
            if select.get("usable", True) is False:
                counts["unusable"] += 1
                continue
            options = select.get("option")
            n_options = len(options) if isinstance(options, list) else 0
            if n_options < 2:
                counts["fewer_than_two_options"] += 1
                continue
            if n_options > 64:
                counts["option_overflow"] += 1
                continue

            yield ReplayDecision(
                observation_json=observation,
                action=tuple(action),
                deck=decks[player],
                player=player,
                response_step=response_step,
            )


def validate_skip_counts(counts: Counter[str]) -> None:
    undeclared = sorted(key for key, value in counts.items() if value and key not in DECLARED_SKIP_REASONS)
    if undeclared:
        raise ReplayContractError(f"undeclared replay skip categories: {undeclared}")
