"""Spec 16b glue: dispatches an `action_space.Candidate` to the right embedding/scoring
mechanism on `model.PolicyModel`, based on the option's `OptionType` (never its
`SelectContext` -- see spec 16a). Used identically for MAIN-context Stage 2 and every
sub-selection context.
"""
from __future__ import annotations

import os
import sys

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _IL_ROOT)

from cg_download.api import OptionType  # noqa: E402
from observation.encoder import Word  # noqa: E402

from . import action_space, layout  # noqa: E402

_LITERAL_TYPES = (OptionType.NUMBER, OptionType.YES, OptionType.NO, OptionType.SPECIAL_CONDITION)
_COMPOUND_TYPES = (OptionType.ATTACH, OptionType.EVOLVE)


def _resolve_card_vec(model, words: list[Word], word_embeddings: torch.Tensor,
                       candidate: action_space.Candidate) -> torch.Tensor:
    if candidate.zone_role is not None:
        vec = model.zone_card_embedding(
            word_embeddings, words, candidate.zone_role, candidate.card_id, candidate.occurrence,
        )
        if vec is not None:
            return vec
    # Unresolved (card lives somewhere GameState doesn't model, e.g. opponent hand/deck,
    # or resolution failed) -- zero embedding, per this spec's explicitly deprioritized
    # precision for the long tail of rare AreaTypes.
    return torch.zeros(model.d_model)


def score_one(
    model, words: list[Word], word_embeddings: torch.Tensor, pooled: torch.Tensor,
    option_type: OptionType, candidate: action_space.Candidate,
) -> torch.Tensor:
    if option_type in _LITERAL_TYPES:
        vec = model.literal_embedding(candidate, option_type)
        return model.candidate_score(pooled, vec)

    if option_type in _COMPOUND_TYPES:
        card_vec = _resolve_card_vec(model, words, word_embeddings, candidate)
        target_ref = candidate.target.board_ref if candidate.target is not None else None
        target_vec = (
            model.board_embedding(word_embeddings, target_ref) if target_ref is not None
            else torch.zeros(model.d_model)
        )
        return model.compound_score(card_vec, target_vec)

    if option_type == OptionType.ATTACK:
        active_ref = action_space.BoardRef(role="our_active", slot=0)
        active_emb = model.board_embedding(word_embeddings, active_ref)
        logits = model.attack_slot_logits(active_emb)
        slot = candidate.attack_slot if candidate.attack_slot is not None else 0
        return logits[slot]

    if candidate.board_ref is not None:
        return model.candidate_score(pooled, model.board_embedding(word_embeddings, candidate.board_ref))

    return model.candidate_score(pooled, _resolve_card_vec(model, words, word_embeddings, candidate))


def score_candidates(
    model, words: list[Word], word_embeddings: torch.Tensor, pooled: torch.Tensor,
    option_type: OptionType, candidates: list[action_space.Candidate],
    effect_card_id: int | None = None, include_stop: bool = False,
) -> torch.Tensor:
    """`effect_card_id` (from `obs.select.effect.id` when present) conditions `pooled` on
    *why* this sub-selection is happening -- e.g. discarding for an Ultra Ball cost vs. a
    Brilliant Blender cost shouldn't use the same context-blind scorer (mirrors
    `Ceruledge-RL/actions.py`'s `_handle_card_selection`, which does this for Track A).

    `include_stop=True` appends `model.stop_score(pooled)` as one extra trailing score
    (index `len(candidates)`), for variable-count (`minCount < maxCount`) selections --
    mirrors `Ceruledge-RL/model.py`'s `stage2_scores(include_stop=...)`. A caller doing
    sequential picking can stop once STOP's score wins. Model/scoring-layer capability
    only -- driving live sequential-pick inference with it is separate (RL-scope) work."""
    if not candidates and not include_stop:
        return torch.zeros(0)
    if effect_card_id is not None:
        pooled = model.condition_on_effect(pooled, model.encode_card_by_id(effect_card_id))
    scores = [score_one(model, words, word_embeddings, pooled, option_type, c) for c in candidates]
    if include_stop:
        scores.append(model.stop_score(pooled))
    return torch.stack(scores) if scores else torch.zeros(0)
