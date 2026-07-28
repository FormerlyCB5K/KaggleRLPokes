"""Focused tests for vectorized imitation-learning batches."""
from __future__ import annotations

import os
import sys

import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
_REPO_ROOT = os.path.dirname(_IL_ROOT)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _IL_ROOT)

from cg_download.api import OptionType
from observation.encoder import Word
from observation.types import TOTAL_WORDS
from policy import action_space as asp
from policy import data as data_mod
from policy.model import PolicyModel
from policy.train import batch_loss_and_correct, evaluate, resolve_device


def _words(turn_number: int) -> list[Word]:
    return (
        [
            Word(
                kind="pad", role=None, static=None, live=None,
                attention_masked=True,
            )
        ] * (TOTAL_WORDS - 2)
        + [
            Word(
                kind="global", role=None, static=None,
                live={"turn_number": turn_number}, attention_masked=False,
            ),
            Word(
                kind="pool", role=None, static=None, live=None,
                attention_masked=False,
            ),
        ]
    )


def _example(turn_number: int, label: int, verb_index: int | None) -> data_mod.Example:
    candidates = [
        asp.Candidate(option_index=0, option_type=OptionType.YES, literal=1.0),
        asp.Candidate(option_index=1, option_type=OptionType.NO, literal=0.0),
    ]
    return data_mod.Example(
        words=_words(turn_number),
        option_type=OptionType.YES,
        verb_index=verb_index,
        candidates=candidates,
        label_index=label,
        episode_name=f"episode-{turn_number}",
    )


def test_encode_batch_matches_single_observation_api():
    model = PolicyModel()
    model.eval()
    words_batch = [_words(2), _words(7)]

    with torch.inference_mode():
        batch_words, batch_pooled = model.encode_batch(words_batch)
        singles = [model.encode(words) for words in words_batch]

    assert batch_words.shape == (2, TOTAL_WORDS, model.d_model)
    assert batch_pooled.shape == (2, model.d_model)
    for i, (single_words, single_pooled) in enumerate(singles):
        assert torch.allclose(batch_words[i], single_words, atol=1e-5)
        assert torch.allclose(batch_pooled[i], single_pooled, atol=1e-5)


def test_real_minibatch_loss_backpropagates_once_for_mixed_labels():
    model = PolicyModel()
    examples = [_example(2, 0, 0), _example(7, 1, None)]

    loss, correct = batch_loss_and_correct(model, examples)
    loss.backward()

    assert loss.ndim == 0
    assert torch.isfinite(loss)
    assert len(correct) == 2
    assert any(parameter.grad is not None for parameter in model.parameters())


def test_evaluate_batches_and_restores_training_mode():
    model = PolicyModel()
    model.train()
    examples = [_example(2, 0, 0), _example(7, 1, None)]

    metrics = evaluate(model, examples, batch_size=2)

    assert model.training
    assert metrics["total"] == 2
    assert set(metrics["by_verb"]) == {asp.VERBS[0].name, "sub_selection"}


def test_resolve_device_cpu_is_explicitly_supported():
    assert resolve_device("cpu") == torch.device("cpu")
