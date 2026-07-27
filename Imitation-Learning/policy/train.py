"""Spec 16c: imitation-learning training loop.

Supervised behavior cloning against real recorded ladder games (`policy/data.py`).
Independent of `Ceruledge-RL/train.py` -- no shared code, no shared checkpoint format.
"""
from __future__ import annotations

import argparse
import datetime
import json
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


def _subdirs(path: str | None) -> list[str]:
    if not path or not os.path.isdir(path):
        return []
    return sorted(
        name for name in os.listdir(path) if os.path.isdir(os.path.join(path, name))
    )


def build_run_config(
    *, run_name: str, description: str, raw_dir: str | None, sanitized_dir: str | None,
    source: str, max_episodes_per_zip: int | None, max_steps: int, epochs: int,
    lr: float, batch_size: int, val_frac: float, seed: int, out_path: str,
) -> dict:
    """Everything needed to know what a run was, without re-reading the SLURM log:
    run identity, exact CLI switches, and which days of which dataset it trained on."""
    return {
        "run_name": run_name,
        "description": description,
        "started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source,
        "raw_dir": raw_dir,
        "raw_days": _subdirs(raw_dir) if source in ("raw", "both") else [],
        "sanitized_dir": sanitized_dir,
        "sanitized_days": _subdirs(sanitized_dir) if source in ("sanitized", "both") else [],
        "max_episodes_per_zip": max_episodes_per_zip,
        "max_steps": max_steps,
        "epochs": epochs,
        "lr": lr,
        "batch_size": batch_size,
        "val_frac": val_frac,
        "seed": seed,
        "out_path": out_path,
    }


def print_run_config(config: dict) -> None:
    print("=" * 70)
    print(f"run_name:             {config['run_name']}")
    print(f"description:          {config['description']}")
    print(f"started_at:           {config['started_at']}")
    print(f"source:               {config['source']}")
    if config["source"] in ("raw", "both"):
        print(f"raw_dir:              {config['raw_dir']}")
        print(f"raw_days:             {', '.join(config['raw_days']) or '(none found)'}")
    if config["source"] in ("sanitized", "both"):
        print(f"sanitized_dir:        {config['sanitized_dir']}")
        print(f"sanitized_days:       {', '.join(config['sanitized_days']) or '(none found)'}")
    print(f"max_episodes_per_zip: {config['max_episodes_per_zip']}")
    print(f"max_steps:            {config['max_steps']}")
    print(f"epochs:               {config['epochs']}")
    print(f"lr:                   {config['lr']}")
    print(f"batch_size:           {config['batch_size']}")
    print(f"val_frac:             {config['val_frac']}")
    print(f"seed:                 {config['seed']}")
    print(f"out_path:             {config['out_path']}")
    print("=" * 70)


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
        model, ex.words, word_embeddings, pooled, ex.candidates,
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
    out_path: str, raw_dir: str | None = None, sanitized_dir: str | None = None,
    source: str = "sanitized", max_episodes_per_zip: int | None = 20,
    max_steps: int = 300, epochs: int = 3, lr: float = 1e-3, batch_size: int = 8,
    val_frac: float = 0.2, seed: int = 0, run_name: str = "", description: str = "",
):
    random.seed(seed)
    torch.manual_seed(seed)

    config = build_run_config(
        run_name=run_name, description=description, raw_dir=raw_dir,
        sanitized_dir=sanitized_dir, source=source,
        max_episodes_per_zip=max_episodes_per_zip, max_steps=max_steps,
        epochs=epochs, lr=lr, batch_size=batch_size, val_frac=val_frac,
        seed=seed, out_path=out_path,
    )
    print_run_config(config)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    config_path = os.path.splitext(out_path)[0] + ".config.json"
    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    examples = list(data_mod.iter_all_examples(
        raw_dir=raw_dir, sanitized_dir=sanitized_dir, source=source,
        max_episodes_per_zip=max_episodes_per_zip, max_steps=max_steps,
    ))
    if not examples:
        raise RuntimeError(
            f"no examples extracted (source={source!r}, raw_dir={raw_dir!r}, "
            f"sanitized_dir={sanitized_dir!r})"
        )
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
    parser.add_argument(
        "--source", choices=("raw", "sanitized", "both"), default="sanitized",
        help="which dataset(s) to train on -- see policy/data.py:iter_all_examples",
    )
    parser.add_argument(
        "--raw-dir", default=os.path.join(_IL_ROOT, "Top-ladder-data"),
        help="raw archive root (Top-ladder-data/<day>/*.zip); used when --source is raw or both",
    )
    parser.add_argument(
        "--sanitized-dir", default=None,
        help="sanitized dataset root (<root>/<day>/*.json); used when --source is sanitized or both",
    )
    parser.add_argument("--out", default=os.path.join(_HERE, "checkpoint.pt"))
    parser.add_argument("--max-episodes-per-zip", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--val-frac", type=float, default=0.2)
    parser.add_argument("--run-name", default="", help="identifies this run in logs/config JSON")
    parser.add_argument("--description", default="", help="free-text notes on this run's purpose")
    args = parser.parse_args()

    train(
        out_path=args.out, raw_dir=args.raw_dir, sanitized_dir=args.sanitized_dir,
        source=args.source, max_episodes_per_zip=args.max_episodes_per_zip,
        max_steps=args.max_steps, epochs=args.epochs, lr=args.lr,
        batch_size=args.batch_size, val_frac=args.val_frac,
        run_name=args.run_name, description=args.description,
    )
