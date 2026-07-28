"""Deterministic policy/include-head decoding."""

from __future__ import annotations

import torch


def _rank(indices: list[int], probabilities: torch.Tensor) -> list[int]:
    return sorted(indices, key=lambda index: (-float(probabilities[index]), index))


def project_to_bounds(
    chosen: set[int],
    probabilities: torch.Tensor,
    n_options: int,
    min_count: int,
    max_count: int,
) -> list[int]:
    """Project a thresholded multi-selection to the engine cardinality bounds."""

    n = max(0, min(int(n_options), int(probabilities.numel())))
    minimum = max(0, min(int(min_count), n))
    maximum = max(minimum, min(int(max_count), n))
    selected = {index for index in chosen if 0 <= index < n}

    if len(selected) > maximum:
        selected = set(_rank(list(selected), probabilities)[:maximum])
    if len(selected) < minimum:
        remaining = [index for index in range(n) if index not in selected]
        for index in _rank(remaining, probabilities)[: minimum - len(selected)]:
            selected.add(index)
    return sorted(selected)


def select_options(
    logits: torch.Tensor,
    include_logits: torch.Tensor,
    n_options: int,
    min_count: int,
    max_count: int,
) -> list[int]:
    """Decode one engine selection prompt exactly as the reported implementation."""

    n = max(0, min(int(n_options), int(logits.numel())))
    if n == 0:
        return []
    if int(max_count) <= 1:
        return [int(torch.argmax(logits[:n]).item())]

    probabilities = torch.sigmoid(include_logits[:n])
    chosen = {
        index
        for index in range(n)
        if float(probabilities[index]) >= 0.5
    }
    return project_to_bounds(
        chosen,
        probabilities,
        n_options=n,
        min_count=min_count,
        max_count=max_count,
    )
