"""Shared validation and legal-action masking for top-ladder episode data.

This module deliberately has no project-model dependencies. Both the historical
loose-JSON sanitizer and the engine-native raw-ZIP cache builder import these
functions so the two storage paths apply identical episode semantics.
"""

from __future__ import annotations

import json


REQUIRED_EPISODE_KEYS = ("info", "rewards", "statuses", "steps")
DONE_STATUSES = ["DONE", "DONE"]


def sanitize_member(raw: bytes) -> tuple[dict | None, dict | None]:
    """Parse and validate one raw episode."""

    try:
        episode = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, {"reason": "malformed_json"}

    if not isinstance(episode, dict) or any(
        key not in episode for key in REQUIRED_EPISODE_KEYS
    ):
        return None, {"reason": "malformed_json"}

    statuses = episode.get("statuses")
    if statuses != DONE_STATUSES:
        return None, {"reason": "non_done_status", "statuses": statuses}

    return episode, None


def mask_episode(episode: dict) -> tuple[int, int, int]:
    """Add ``select.usable`` and return total, usable, and masked counts."""

    steps_total = 0
    steps_usable = 0
    steps_masked = 0
    for step in episode.get("steps") or []:
        if not isinstance(step, list):
            continue
        for player_entry in step:
            if not isinstance(player_entry, dict):
                continue
            observation = player_entry.get("observation")
            if not isinstance(observation, dict):
                continue
            select = observation.get("select")
            if not isinstance(select, dict):
                continue
            steps_total += 1
            option = select.get("option")
            if option is None:
                continue
            usable = len(option) != 1
            select["usable"] = usable
            if usable:
                steps_usable += 1
            else:
                steps_masked += 1
    return steps_total, steps_usable, steps_masked
