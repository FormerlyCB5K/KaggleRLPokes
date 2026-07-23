"""Spec 16c: imitation-learning training loop.

Supervised behavior cloning against real recorded ladder games (`policy/data.py`).
Independent of `Ceruledge-RL/train.py` -- no shared code, no shared checkpoint format.
"""
from __future__ import annotations

import argparse
import os
import random
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _IL_ROOT)

import torch
import torch.nn.functional as F

from policy import action_space as asp
from policy import data as data_mod
from policy import scoring
from policy.model import PolicyModel


def _split_by_episode(examples: list[data_mod.Example], val_frac: float):
    episode_names = sorted({e.episode_name for e in examples})
    n_val = max(1, int(len(episode_names) * val_frac)) if episode_names else 0
    val_names = set(episode_names[-n_val:]) if n_val else set()
    train_ex = [e for e in examples if e.episode_name not in val_names]
    val_ex = [e for e in examples if e.episode_name in val_names]
    return train_ex, val_ex


def example_loss_and_correct(model: PolicyModel, ex: data_mod.Example):
    word_embeddings, pooled = model.encode(ex.words)

    stage2_scores = scoring.score_candidates(
        model, ex.words, word_embeddings, pooled, ex.option_type, ex.candidates,
        effect_card_id=ex.effect_card_id,
    )
    label = torch.tensor(ex.label_index, dtype=torch.long)
    loss = F.cross_entropy(stage2_scores.unsqueeze(0), label.unsqueeze(0))
    correct = int(stage2_scores.argmax().item() == ex.label_index)

    if ex.verb_index is not None:
        logits = model.stage1_logits(pooled)
        verb_label = torch.tensor(ex.verb_index, dtype=torch.long)
        loss = loss + F.cross_entropy(logits.unsqueeze(0), verb_label.unsqueeze(0))
        correct = int(correct and logits.argmax().item() == ex.verb_index)

    return loss, correct


@torch.no_grad()
def evaluate(model: PolicyModel, examples: list[data_mod.Example]) -> dict:
    model.eval()
    total = 0
    correct = 0
    by_verb = {}
    for ex in examples:
        _, was_correct = example_loss_and_correct(model, ex)
        total += 1
        correct += was_correct
        key = asp.VERBS[ex.verb_index].name if ex.verb_index is not None else "sub_selection"
        bucket = by_verb.setdefault(key, [0, 0])
        bucket[0] += was_correct
        bucket[1] += 1
    model.train()
    return {
        "accuracy": correct / total if total else 0.0,
        "total": total,
        "by_verb": {k: v[0] / v[1] for k, v in by_verb.items()},
    }


def train(
    data_dir: str, out_path: str, max_episodes_per_zip: int | None = 20,
    max_steps: int = 300, epochs: int = 3, lr: float = 1e-3, batch_size: int = 8,
    val_frac: float = 0.2, seed: int = 0,
):
    random.seed(seed)
    torch.manual_seed(seed)

    examples = list(data_mod.iter_all_examples(data_dir, max_episodes_per_zip, max_steps))
    if not examples:
        raise RuntimeError(f"no examples extracted from {data_dir}")
    train_ex, val_ex = _split_by_episode(examples, val_frac)
    print(f"examples: {len(examples)} total, {len(train_ex)} train, {len(val_ex)} val "
          f"({len({e.episode_name for e in examples})} episodes)")

    model = PolicyModel()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)

    base = evaluate(model, val_ex) if val_ex else {"accuracy": 0.0, "total": 0, "by_verb": {}}
    print(f"[baseline] val_accuracy={base['accuracy']:.3f} (n={base['total']}) by_verb={base['by_verb']}")

    best_acc = -1.0
    for epoch in range(epochs):
        random.shuffle(train_ex)
        running_loss = 0.0
        optimizer.zero_grad()
        for step, ex in enumerate(train_ex, start=1):
            loss, _ = example_loss_and_correct(model, ex)
            (loss / batch_size).backward()
            running_loss += loss.item()
            if step % batch_size == 0:
                optimizer.step()
                optimizer.zero_grad()
        if len(train_ex) % batch_size != 0:
            optimizer.step()
            optimizer.zero_grad()

        avg_loss = running_loss / len(train_ex) if train_ex else 0.0
        metrics = evaluate(model, val_ex) if val_ex else {"accuracy": 0.0, "total": 0, "by_verb": {}}
        print(f"[epoch {epoch}] train_loss={avg_loss:.4f} val_accuracy={metrics['accuracy']:.3f} "
              f"(n={metrics['total']}) by_verb={metrics['by_verb']}")
        if metrics["accuracy"] >= best_acc:
            best_acc = metrics["accuracy"]
            torch.save({"model_state_dict": model.state_dict(), "val_accuracy": best_acc}, out_path)

    print(f"saved best checkpoint (val_accuracy={best_acc:.3f}) to {out_path}")
    return {"baseline": base, "best_val_accuracy": best_acc}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=os.path.join(_IL_ROOT, "Top-ladder-data"))
    parser.add_argument("--out", default=os.path.join(_HERE, "checkpoint.pt"))
    parser.add_argument("--max-episodes-per-zip", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--val-frac", type=float, default=0.2)
    args = parser.parse_args()

    train(
        data_dir=args.data_dir, out_path=args.out,
        max_episodes_per_zip=args.max_episodes_per_zip, max_steps=args.max_steps,
        epochs=args.epochs, lr=args.lr, batch_size=args.batch_size, val_frac=args.val_frac,
    )
