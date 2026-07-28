"""Spec 16c: imitation-learning training loop.

Supervised behavior cloning against real recorded ladder games (`policy/data.py`).
Independent of `Ceruledge-RL/train.py` -- no shared code, no shared checkpoint format.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime
import gc
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


def build_run_config(
    *, run_name: str, description: str, raw_dir: str | None, sanitized_dir: str | None,
    source: str, days_per_chunk: int, cache_dir: str | None, max_episodes_per_zip: int | None,
    max_steps: int, epochs: int, lr: float, batch_size: int, val_frac: float, seed: int,
    out_path: str, device: str = "auto", resolved_device: str = "cpu",
    mixed_precision: bool = True,
    resolved_source_days: list[tuple[str, str]] | None = None,
) -> dict:
    """Everything needed to know what a run was, without re-reading the SLURM log:
    run identity, exact CLI switches, and which days of which dataset it trained on."""
    resolved_source_days = resolved_source_days or []
    return {
        "run_name": run_name,
        "description": description,
        "started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source,
        "days_per_chunk": days_per_chunk,
        "cache_dir": cache_dir,
        "raw_dir": raw_dir,
        "raw_days": [day for label, day in resolved_source_days if label == "raw"],
        "sanitized_dir": sanitized_dir,
        "sanitized_days": [
            day for label, day in resolved_source_days if label == "sanitized"
        ],
        "resolved_source_days": [
            {"source": label, "day": day} for label, day in resolved_source_days
        ],
        "max_episodes_per_zip": max_episodes_per_zip,
        "max_steps": max_steps,
        "epochs": epochs,
        "lr": lr,
        "batch_size": batch_size,
        "val_frac": val_frac,
        "seed": seed,
        "device": device,
        "resolved_device": resolved_device,
        "mixed_precision": mixed_precision,
        "out_path": out_path,
    }


def print_run_config(config: dict) -> None:
    print("=" * 70)
    print(f"run_name:             {config['run_name']}")
    print(f"description:          {config['description']}")
    print(f"started_at:           {config['started_at']}")
    print(f"source:               {config['source']}")
    print(f"days_per_chunk:       {config['days_per_chunk']}")
    print(f"cache_dir:            {config['cache_dir'] or '(none -- live extraction)'}")
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
    print(f"device:               {config['device']} -> {config['resolved_device']}")
    print(f"mixed_precision:      {config['mixed_precision']}")
    print(f"out_path:             {config['out_path']}")
    print("=" * 70)


def _split_by_episode(examples: list[data_mod.Example], val_frac: float):
    episode_names = sorted({e.episode_name for e in examples})
    n_val = max(1, int(len(episode_names) * val_frac)) if episode_names else 0
    val_names = set(episode_names[-n_val:]) if n_val else set()
    train_ex = [e for e in examples if e.episode_name not in val_names]
    val_ex = [e for e in examples if e.episode_name in val_names]
    return train_ex, val_ex


def resolve_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda was requested, but PyTorch cannot access CUDA")
    return torch.device(requested)


def _autocast(device: torch.device, enabled: bool):
    if enabled and device.type == "cuda":
        return torch.autocast(device_type="cuda", dtype=torch.float16)
    return contextlib.nullcontext()


def batch_loss_and_correct(
    model: PolicyModel,
    examples: list[data_mod.Example],
    *,
    compute_correct: bool = True,
):
    """Mean loss for a real mini-batch using one shared transformer forward pass."""
    if not examples:
        raise ValueError("examples must contain at least one item")

    word_embeddings, pooled = model.encode_batch([ex.words for ex in examples])
    stage1_logits = model.stage1_logits(pooled)
    losses = []
    correct_tensors = []

    for i, ex in enumerate(examples):
        stage2_scores = scoring.score_candidates(
            model, ex.words, word_embeddings[i], pooled[i], ex.candidates,
            effect_card_id=ex.effect_card_id,
        )
        loss = -F.log_softmax(stage2_scores, dim=0)[ex.label_index]
        if compute_correct:
            correct = stage2_scores.argmax() == ex.label_index

        if ex.verb_index is not None:
            loss = loss - F.log_softmax(stage1_logits[i], dim=0)[ex.verb_index]
            if compute_correct:
                correct = correct & (stage1_logits[i].argmax() == ex.verb_index)

        losses.append(loss)
        if compute_correct:
            correct_tensors.append(correct)

    correct_values = (
        torch.stack(correct_tensors).detach().cpu().to(torch.int64).tolist()
        if compute_correct else []
    )
    return torch.stack(losses).mean(), correct_values


def example_loss_and_correct(model: PolicyModel, ex: data_mod.Example):
    """Compatibility wrapper for callers/tests that operate on one example."""
    loss, correct = batch_loss_and_correct(model, [ex])
    return loss, correct[0]


@torch.inference_mode()
def evaluate(
    model: PolicyModel, examples: list[data_mod.Example], batch_size: int = 128,
    mixed_precision: bool = False,
) -> dict:
    was_training = model.training
    model.eval()
    device = next(model.parameters()).device
    total = 0
    correct = 0
    by_verb = {}
    for start in range(0, len(examples), batch_size):
        batch = examples[start:start + batch_size]
        with _autocast(device, mixed_precision):
            _, batch_correct = batch_loss_and_correct(model, batch)
        for ex, was_correct in zip(batch, batch_correct):
            total += 1
            correct += was_correct
            key = (
                asp.VERBS[ex.verb_index].name
                if ex.verb_index is not None else "sub_selection"
            )
            bucket = by_verb.setdefault(key, [0, 0])
            bucket[0] += was_correct
            bucket[1] += 1
    model.train(was_training)
    return {
        "accuracy": correct / total if total else 0.0,
        "total": total,
        "by_verb": {k: v[0] / v[1] for k, v in by_verb.items()},
    }


def train(
    out_path: str, raw_dir: str | None = None, sanitized_dir: str | None = None,
    source: str = "sanitized", days_per_chunk: int = 1, cache_dir: str | None = None,
    max_episodes_per_zip: int | None = 20, max_steps: int = 300, epochs: int = 3,
    lr: float = 1e-3, batch_size: int = 128, val_frac: float = 0.2, seed: int = 0,
    run_name: str = "", description: str = "", device: str = "auto",
    mixed_precision: bool = True,
):
    """`epochs` is the number of full passes over *every* day-chunk (standard ML
    meaning): each outer epoch visits every chunk once, in order, before any chunk
    repeats -- not "finish all epochs on chunk 1, then move to chunk 2". If
    `cache_dir` is given, each chunk is loaded from a pre-built cache
    (`build_example_cache.py`) instead of re-extracted from `raw_dir`/
    `sanitized_dir` on every revisit -- required to keep `epochs > 1` fast, since
    interleaving means every chunk gets revisited once per outer epoch."""
    random.seed(seed)
    torch.manual_seed(seed)
    resolved_device = resolve_device(device)
    amp_enabled = mixed_precision and resolved_device.type == "cuda"
    if resolved_device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
        torch.set_float32_matmul_precision("high")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    if cache_dir is not None:
        resolved_source_days = data_mod.resolve_cached_source_day_pairs(
            cache_dir=cache_dir, source=source,
            raw_dir=raw_dir, sanitized_dir=sanitized_dir,
        )
    else:
        if source in ("raw", "both") and not raw_dir:
            raise ValueError("raw_dir is required when source is 'raw' or 'both'")
        if source in ("sanitized", "both") and not sanitized_dir:
            raise ValueError(
                "sanitized_dir is required when source is 'sanitized' or 'both'"
            )
        resolved_source_days = data_mod.list_source_day_pairs(
            raw_dir=raw_dir, sanitized_dir=sanitized_dir, source=source,
        )

    config = build_run_config(
        run_name=run_name, description=description, raw_dir=raw_dir,
        sanitized_dir=sanitized_dir, source=source, days_per_chunk=days_per_chunk,
        cache_dir=cache_dir, max_episodes_per_zip=max_episodes_per_zip, max_steps=max_steps,
        epochs=epochs, lr=lr, batch_size=batch_size, val_frac=val_frac,
        seed=seed, out_path=out_path, device=device,
        resolved_device=str(resolved_device), mixed_precision=amp_enabled,
        resolved_source_days=resolved_source_days,
    )
    print_run_config(config)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    config_path = os.path.splitext(out_path)[0] + ".config.json"
    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    if cache_dir is None and epochs > 1:
        print(
            "WARNING: no cache_dir given with epochs > 1 -- each chunk will be "
            "re-extracted from source data once per outer epoch (~1 episode/sec, "
            "multiplied by epochs). Run build_example_cache.py once and pass "
            "cache_dir to avoid repeated extraction."
        )

    model = PolicyModel().to(resolved_device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scaler = torch.amp.GradScaler(
        "cuda", enabled=amp_enabled,
    )

    base = None
    best_acc = -1.0
    saw_any_examples = False

    for outer_epoch in range(epochs):
        if cache_dir is not None:
            chunk_iter = data_mod.iter_cached_examples_by_day_chunk(
                cache_dir=cache_dir, source=source, days_per_chunk=days_per_chunk,
                max_episodes_per_zip=max_episodes_per_zip, max_steps=max_steps,
                raw_dir=raw_dir, sanitized_dir=sanitized_dir,
            )
        else:
            chunk_iter = data_mod.iter_examples_by_day_chunk(
                raw_dir=raw_dir, sanitized_dir=sanitized_dir, source=source,
                max_episodes_per_zip=max_episodes_per_zip, max_steps=max_steps,
                days_per_chunk=days_per_chunk,
            )

        for chunk_label, examples in chunk_iter:
            if not examples:
                print(f"WARNING: chunk {chunk_label!r} yielded no examples, skipping "
                      f"(outer_epoch={outer_epoch})")
                continue
            saw_any_examples = True

            train_ex, val_ex = _split_by_episode(examples, val_frac)
            print(f"[outer_epoch {outer_epoch} chunk {chunk_label}] examples: {len(examples)} "
                  f"total, {len(train_ex)} train, {len(val_ex)} val "
                  f"({len({e.episode_name for e in examples})} episodes)")

            if base is None:
                base = (
                    evaluate(
                        model, val_ex, batch_size=batch_size,
                        mixed_precision=amp_enabled,
                    )
                    if val_ex else {"accuracy": 0.0, "total": 0, "by_verb": {}}
                )
                print(f"[baseline] (outer_epoch {outer_epoch} chunk {chunk_label}) "
                      f"val_accuracy={base['accuracy']:.3f} (n={base['total']}) by_verb={base['by_verb']}")

            # One epoch's worth of true mini-batch training on this chunk.
            random.shuffle(train_ex)
            running_loss = 0.0
            for start in range(0, len(train_ex), batch_size):
                batch = train_ex[start:start + batch_size]
                optimizer.zero_grad(set_to_none=True)
                with _autocast(resolved_device, amp_enabled):
                    loss, _ = batch_loss_and_correct(
                        model, batch, compute_correct=False,
                    )
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
                running_loss += loss.detach().float().item() * len(batch)

            avg_loss = running_loss / len(train_ex) if train_ex else 0.0
            metrics = (
                evaluate(
                    model, val_ex, batch_size=batch_size,
                    mixed_precision=amp_enabled,
                )
                if val_ex else {"accuracy": 0.0, "total": 0, "by_verb": {}}
            )
            print(f"[outer_epoch {outer_epoch} chunk {chunk_label}] train_loss={avg_loss:.4f} "
                  f"val_accuracy={metrics['accuracy']:.3f} (n={metrics['total']}) "
                  f"by_verb={metrics['by_verb']}")
            if metrics["accuracy"] > best_acc:
                best_acc = metrics["accuracy"]
                torch.save({"model_state_dict": model.state_dict(), "val_accuracy": best_acc}, out_path)

            del examples, train_ex, val_ex
            gc.collect()

    if not saw_any_examples:
        raise RuntimeError(
            f"no examples extracted from any chunk (source={source!r}, raw_dir={raw_dir!r}, "
            f"sanitized_dir={sanitized_dir!r}, cache_dir={cache_dir!r})"
        )

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
    parser.add_argument(
        "--days-per-chunk", type=int, default=1,
        help="group N consecutive day-directories into one chunk; extraction and "
             "training happen one chunk at a time so peak memory is bounded to a "
             "chunk's examples rather than the whole dataset (default: 1)",
    )
    parser.add_argument(
        "--cache-dir", default=None,
        help="pre-built per-day Example cache root from build_example_cache.py; if "
             "given, day-chunks are loaded from cache instead of re-extracted from "
             "--raw-dir/--sanitized-dir on every outer epoch -- needed to keep "
             "--epochs > 1 fast. If omitted, chunks are extracted live every outer "
             "epoch (slow when epochs > 1)",
    )
    parser.add_argument("--out", default=os.path.join(_HERE, "checkpoint.pt"))
    parser.add_argument(
        "--max-episodes-per-zip", type=data_mod.parse_episode_limit, default=20,
        help="positive per-day cap, or 'all' for an uncapped full-day run "
             "(default: 20)",
    )
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument(
        "--epochs", type=int, default=3,
        help="outer training epochs -- one full interleaved pass over every "
             "day-chunk per epoch (standard meaning): each chunk is visited once "
             "per epoch before any chunk repeats, not fully trained through before "
             "moving to the next",
    )
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument(
        "--batch-size", type=int, default=128,
        help="real vectorized mini-batch size (default: 128)",
    )
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda"), default="auto",
        help="training device; 'auto' uses CUDA when available (default: auto)",
    )
    parser.add_argument(
        "--no-mixed-precision", action="store_false", dest="mixed_precision",
        help="disable CUDA float16 autocast/gradient scaling",
    )
    parser.add_argument("--val-frac", type=float, default=0.2)
    parser.add_argument("--run-name", default="", help="identifies this run in logs/config JSON")
    parser.add_argument("--description", default="", help="free-text notes on this run's purpose")
    args = parser.parse_args()

    train(
        out_path=args.out, raw_dir=args.raw_dir, sanitized_dir=args.sanitized_dir,
        source=args.source, days_per_chunk=args.days_per_chunk, cache_dir=args.cache_dir,
        max_episodes_per_zip=args.max_episodes_per_zip,
        max_steps=args.max_steps, epochs=args.epochs, lr=args.lr,
        batch_size=args.batch_size, val_frac=args.val_frac,
        run_name=args.run_name, description=args.description,
        device=args.device, mixed_precision=args.mixed_precision,
    )
