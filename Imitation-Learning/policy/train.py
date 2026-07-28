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
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _IL_ROOT)

import torch
import torch.nn.functional as F

from policy import action_space as asp
from policy import data as data_mod
from policy import scoring
from policy import training_split
from policy.model import PolicyModel

RESUME_CHECKPOINT_VERSION = 1


def build_run_config(
    *, run_name: str, description: str, raw_dir: str | None, sanitized_dir: str | None,
    source: str, days_per_chunk: int, cache_dir: str | None, max_episodes_per_zip: int | None,
    max_steps: int, epochs: int, lr: float, batch_size: int, val_frac: float, seed: int,
    out_path: str, device: str = "auto", resolved_device: str = "cpu",
    mixed_precision: bool = True, split_path: str | None = None,
    resume_path: str | None = None, resume: bool = False,
    early_stopping_patience: int = 5, early_stopping_min_delta: float = 0.001,
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
        "split_path": split_path,
        "resume_path": resume_path,
        "resume": resume,
        "early_stopping_patience": early_stopping_patience,
        "early_stopping_min_delta": early_stopping_min_delta,
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
    print(f"split_path:           {config['split_path']}")
    print(f"resume_path:          {config['resume_path']}")
    print(f"resume:               {config['resume']}")
    print(f"early_stop_patience:  {config['early_stopping_patience']}")
    print(f"early_stop_min_delta: {config['early_stopping_min_delta']}")
    print(f"out_path:             {config['out_path']}")
    print("=" * 70)


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
        "correct": correct,
        "by_verb": {k: v[0] / v[1] for k, v in by_verb.items()},
        "by_verb_counts": {
            k: {"correct": v[0], "total": v[1]} for k, v in by_verb.items()
        },
    }


def evaluate_fixed_validation(
    model: PolicyModel,
    *,
    split_path: str,
    split: dict,
    batch_size: int,
    mixed_precision: bool,
) -> dict:
    """Evaluate the same persisted game-level holdout, one small day shard at a time."""
    total = 0
    correct = 0
    by_verb: dict[str, list[int]] = {}
    for entry in split["source_days"]:
        examples = training_split.load_validation_shard(
            split_path, split, entry["source"], entry["day"],
        )
        metrics = evaluate(
            model, examples, batch_size=batch_size,
            mixed_precision=mixed_precision,
        )
        total += metrics["total"]
        correct += metrics["correct"]
        for key, counts in metrics["by_verb_counts"].items():
            bucket = by_verb.setdefault(key, [0, 0])
            bucket[0] += counts["correct"]
            bucket[1] += counts["total"]
        del examples
        gc.collect()
    if total != split["validation_positions"]:
        raise RuntimeError(
            "fixed validation position count changed: "
            f"split={split['validation_positions']}, evaluated={total}"
        )
    return {
        "accuracy": correct / total if total else 0.0,
        "total": total,
        "correct": correct,
        "by_verb": {key: value[0] / value[1] for key, value in by_verb.items()},
        "by_verb_counts": {
            key: {"correct": value[0], "total": value[1]}
            for key, value in by_verb.items()
        },
    }


def _save_torch_atomic(path: str, value) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    temp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    torch.save(value, temp_path)
    os.replace(temp_path, path)


def _training_signature(config: dict, split: dict) -> dict:
    """Resume-critical settings; target epoch count and job identity may change."""
    return {
        "source": config["source"],
        "resolved_source_days": config["resolved_source_days"],
        "cache_inventory_hash": split["cache_inventory_hash"],
        "split_hash": split["split_hash"],
        "max_episodes_per_zip": config["max_episodes_per_zip"],
        "max_steps": config["max_steps"],
        "lr": config["lr"],
        "batch_size": config["batch_size"],
        "val_frac": config["val_frac"],
        "seed": config["seed"],
        "mixed_precision": config["mixed_precision"],
        "early_stopping_patience": config["early_stopping_patience"],
        "early_stopping_min_delta": config["early_stopping_min_delta"],
    }


def _checkpoint_payload(
    *,
    model: PolicyModel,
    optimizer: torch.optim.Optimizer,
    scaler,
    signature: dict,
    outer_epoch: int,
    next_mini_epoch_index: int,
    completed_mini_epochs: int,
    baseline: dict,
    best_acc: float,
    epochs_without_improvement: int,
    finished: bool,
) -> dict:
    payload = {
        "checkpoint_version": RESUME_CHECKPOINT_VERSION,
        "training_signature": signature,
        "model_state_dict": model.state_dict(),
        "optimizer_state_dict": optimizer.state_dict(),
        "scaler_state_dict": scaler.state_dict(),
        "outer_epoch": outer_epoch,
        "next_mini_epoch_index": next_mini_epoch_index,
        "completed_mini_epochs": completed_mini_epochs,
        "baseline": baseline,
        "best_val_accuracy": best_acc,
        "epochs_without_improvement": epochs_without_improvement,
        "finished": finished,
        "python_random_state": random.getstate(),
        "torch_random_state": torch.get_rng_state(),
    }
    if torch.cuda.is_available():
        payload["cuda_random_states"] = torch.cuda.get_rng_state_all()
    return payload


def _restore_resume_state(
    *,
    path: str,
    model: PolicyModel,
    optimizer: torch.optim.Optimizer,
    scaler,
    signature: dict,
    device: torch.device,
) -> dict:
    state = torch.load(path, map_location=device, weights_only=False)
    if state.get("checkpoint_version") != RESUME_CHECKPOINT_VERSION:
        raise RuntimeError(
            f"resume checkpoint version mismatch at {path!r}: "
            f"saved={state.get('checkpoint_version')!r}, "
            f"current={RESUME_CHECKPOINT_VERSION}"
        )
    if state.get("training_signature") != signature:
        raise RuntimeError(
            "resume checkpoint training configuration does not match this run; "
            "use the original settings or a new output directory"
        )
    model.load_state_dict(state["model_state_dict"])
    optimizer.load_state_dict(state["optimizer_state_dict"])
    scaler.load_state_dict(state["scaler_state_dict"])
    random.setstate(state["python_random_state"])
    torch.set_rng_state(state["torch_random_state"].cpu())
    if device.type == "cuda" and "cuda_random_states" in state:
        torch.cuda.set_rng_state_all(
            [rng_state.cpu() for rng_state in state["cuda_random_states"]]
        )
    return state


def train(
    out_path: str, raw_dir: str | None = None, sanitized_dir: str | None = None,
    source: str = "sanitized", days_per_chunk: int = 1, cache_dir: str | None = None,
    max_episodes_per_zip: int | None = 20, max_steps: int = 300, epochs: int = 3,
    lr: float = 1e-3, batch_size: int = 256, val_frac: float = 0.1, seed: int = 0,
    run_name: str = "", description: str = "", device: str = "auto",
    mixed_precision: bool = True, split_path: str | None = None,
    resume_path: str | None = None, resume: bool = False,
    rebuild_split: bool = False, early_stopping_patience: int = 5,
    early_stopping_min_delta: float = 0.001,
):
    """Train using one shuffled cached day per resumable mini-epoch.

    A full outer epoch visits every cached source/day exactly once in a newly
    shuffled order. Train/validation membership is one fixed random split over
    global game IDs, so positions from a held-out game can never leak into training.
    """
    if cache_dir is None:
        raise ValueError(
            "cache-backed training is required for the fixed global game split; "
            "run build_example_cache.py and pass --cache-dir"
        )
    if days_per_chunk != 1:
        raise ValueError(
            "days_per_chunk must be 1: one cached day is the resumable mini-epoch"
        )
    if epochs < 1:
        raise ValueError(f"epochs must be >= 1, got {epochs}")
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if early_stopping_patience < 0:
        raise ValueError("early_stopping_patience must be >= 0")
    if early_stopping_min_delta < 0:
        raise ValueError("early_stopping_min_delta must be >= 0")

    random.seed(seed)
    torch.manual_seed(seed)
    resolved_device = resolve_device(device)
    amp_enabled = mixed_precision and resolved_device.type == "cuda"
    if resolved_device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
        torch.set_float32_matmul_precision("high")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True

    resolved_source_days = data_mod.resolve_cached_source_day_pairs(
        cache_dir=cache_dir, source=source,
        raw_dir=raw_dir, sanitized_dir=sanitized_dir,
    )
    out_stem = os.path.splitext(out_path)[0]
    split_path = split_path or out_stem + ".game-split.json"
    resume_path = resume_path or out_stem + ".resume.pt"

    config = build_run_config(
        run_name=run_name, description=description, raw_dir=raw_dir,
        sanitized_dir=sanitized_dir, source=source, days_per_chunk=days_per_chunk,
        cache_dir=cache_dir, max_episodes_per_zip=max_episodes_per_zip, max_steps=max_steps,
        epochs=epochs, lr=lr, batch_size=batch_size, val_frac=val_frac,
        seed=seed, out_path=out_path, device=device,
        resolved_device=str(resolved_device), mixed_precision=amp_enabled,
        split_path=split_path, resume_path=resume_path, resume=resume,
        early_stopping_patience=early_stopping_patience,
        early_stopping_min_delta=early_stopping_min_delta,
        resolved_source_days=resolved_source_days,
    )
    print_run_config(config)
    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    config_path = os.path.splitext(out_path)[0] + ".config.json"
    with open(config_path, "w") as handle:
        json.dump(config, handle, indent=2)

    split = training_split.prepare_or_load_game_split(
        split_path=split_path,
        cache_dir=cache_dir,
        source=source,
        val_frac=val_frac,
        seed=seed,
        max_episodes_per_zip=max_episodes_per_zip,
        max_steps=max_steps,
        raw_dir=raw_dir,
        sanitized_dir=sanitized_dir,
        rebuild=rebuild_split,
    )
    validation_games = training_split.validation_key_set(split)
    print(
        f"fixed game split: {split['training_games']} train / "
        f"{split['validation_game_count']} validation games; "
        f"{split['training_positions']} train / "
        f"{split['validation_positions']} validation positions; "
        f"hash={split['split_hash']}"
    )
    for entry in split["source_days"]:
        print(
            f"  {entry['source']}/{entry['day']}: "
            f"games={entry['training_games']} train+"
            f"{entry['validation_games']} val, "
            f"positions={entry['training_positions']} train+"
            f"{entry['validation_positions']} val"
        )

    model = PolicyModel().to(resolved_device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scaler = torch.amp.GradScaler(
        "cuda", enabled=amp_enabled,
    )

    signature = _training_signature(config, split)
    base = None
    best_acc = -1.0
    epochs_without_improvement = 0
    outer_epoch = 0
    next_mini_epoch_index = 0
    completed_mini_epochs = 0

    if resume and os.path.isfile(resume_path):
        state = _restore_resume_state(
            path=resume_path,
            model=model,
            optimizer=optimizer,
            scaler=scaler,
            signature=signature,
            device=resolved_device,
        )
        base = state["baseline"]
        best_acc = state["best_val_accuracy"]
        epochs_without_improvement = state["epochs_without_improvement"]
        outer_epoch = state["outer_epoch"]
        next_mini_epoch_index = state["next_mini_epoch_index"]
        completed_mini_epochs = state["completed_mini_epochs"]
        if state.get("finished"):
            print(
                f"resume checkpoint is already finished at outer_epoch={outer_epoch}; "
                f"best_val_accuracy={best_acc:.3f}"
            )
            return {"baseline": base, "best_val_accuracy": best_acc}
        print(
            f"resumed {resume_path}: outer_epoch={outer_epoch}, "
            f"next_mini_epoch_index={next_mini_epoch_index}, "
            f"completed_mini_epochs={completed_mini_epochs}, "
            f"best_val_accuracy={best_acc:.3f}"
        )
    elif resume:
        print(f"no resume checkpoint at {resume_path}; starting fresh")

    if base is None:
        baseline_started = time.perf_counter()
        base = evaluate_fixed_validation(
            model,
            split_path=split_path,
            split=split,
            batch_size=batch_size,
            mixed_precision=amp_enabled,
        )
        print(
            f"[baseline] fixed_val_accuracy={base['accuracy']:.3f} "
            f"(n={base['total']}) elapsed={time.perf_counter() - baseline_started:.1f}s "
            f"by_verb={base['by_verb']}"
        )

    finished = False
    while outer_epoch < epochs and not finished:
        mini_epoch_order = list(resolved_source_days)
        random.Random(f"{seed}:outer_epoch:{outer_epoch}").shuffle(mini_epoch_order)

        for mini_index in range(next_mini_epoch_index, len(mini_epoch_order)):
            label, day = mini_epoch_order[mini_index]
            mini_started = time.perf_counter()
            examples, _manifest = data_mod.load_cached_source_day(
                cache_dir, label, day,
                max_episodes_per_zip=max_episodes_per_zip,
                max_steps=max_steps,
                raw_dir=raw_dir,
                sanitized_dir=sanitized_dir,
            )
            train_ex = [
                example for example in examples
                if training_split.game_key(label, day, example.episode_name)
                not in validation_games
            ]
            expected_entry = next(
                entry for entry in split["source_days"]
                if entry["source"] == label and entry["day"] == day
            )
            if len(train_ex) != expected_entry["training_positions"]:
                raise RuntimeError(
                    f"training position count changed for {label}/{day}: "
                    f"split={expected_entry['training_positions']}, loaded={len(train_ex)}"
                )
            random.Random(
                f"{seed}:outer_epoch:{outer_epoch}:{label}:{day}"
            ).shuffle(train_ex)

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
            completed_mini_epochs += 1
            elapsed = time.perf_counter() - mini_started
            print(
                f"[outer_epoch {outer_epoch} mini_epoch {mini_index + 1}/"
                f"{len(mini_epoch_order)} {label}/{day}] "
                f"train_examples={len(train_ex)} train_loss={avg_loss:.4f} "
                f"elapsed={elapsed:.1f}s throughput="
                f"{len(train_ex) / elapsed if elapsed else 0.0:.1f} examples/s"
            )
            del examples, train_ex
            gc.collect()

            is_last_mini_epoch = mini_index + 1 == len(mini_epoch_order)
            if is_last_mini_epoch:
                validation_started = time.perf_counter()
                metrics = evaluate_fixed_validation(
                    model,
                    split_path=split_path,
                    split=split,
                    batch_size=batch_size,
                    mixed_precision=amp_enabled,
                )
                improved = metrics["accuracy"] > (
                    best_acc + early_stopping_min_delta
                )
                if improved:
                    best_acc = metrics["accuracy"]
                    epochs_without_improvement = 0
                    _save_torch_atomic(out_path, {
                        "model_state_dict": model.state_dict(),
                        "val_accuracy": best_acc,
                        "outer_epoch": outer_epoch,
                        "completed_mini_epochs": completed_mini_epochs,
                        "split_hash": split["split_hash"],
                    })
                else:
                    epochs_without_improvement += 1
                print(
                    f"[outer_epoch {outer_epoch} fixed_validation] "
                    f"accuracy={metrics['accuracy']:.3f} (n={metrics['total']}) "
                    f"elapsed={time.perf_counter() - validation_started:.1f}s "
                    f"best={best_acc:.3f} no_improvement="
                    f"{epochs_without_improvement}/{early_stopping_patience or 'disabled'} "
                    f"by_verb={metrics['by_verb']}"
                )
                finished = (
                    early_stopping_patience > 0
                    and epochs_without_improvement >= early_stopping_patience
                )
                outer_epoch += 1
                next_mini_epoch_index = 0
            else:
                next_mini_epoch_index = mini_index + 1

            state = _checkpoint_payload(
                model=model,
                optimizer=optimizer,
                scaler=scaler,
                signature=signature,
                outer_epoch=outer_epoch,
                next_mini_epoch_index=next_mini_epoch_index,
                completed_mini_epochs=completed_mini_epochs,
                baseline=base,
                best_acc=best_acc,
                epochs_without_improvement=epochs_without_improvement,
                finished=finished,
            )
            _save_torch_atomic(resume_path, state)
            print(
                f"saved resume checkpoint after mini_epoch={completed_mini_epochs} "
                f"to {resume_path}"
            )
            if finished:
                print(
                    f"early stopping after {epochs_without_improvement} "
                    "full validation checks without sufficient improvement"
                )
                break

        next_mini_epoch_index = 0

    print(
        f"training finished at outer_epoch={outer_epoch}; "
        f"best fixed validation accuracy={best_acc:.3f}; best checkpoint={out_path}"
    )
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
        help="compatibility option; must remain 1 because one cached day is one "
             "resumable mini-epoch",
    )
    parser.add_argument(
        "--cache-dir", default=None,
        help="required pre-built per-day Example cache root from "
             "build_example_cache.py",
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
        help="maximum full-corpus passes; each pass visits every shuffled day "
             "mini-epoch once and then evaluates the fixed validation set",
    )
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument(
        "--batch-size", type=int, default=256,
        help="real vectorized mini-batch size (default: 256)",
    )
    parser.add_argument(
        "--device", choices=("auto", "cpu", "cuda"), default="auto",
        help="training device; 'auto' uses CUDA when available (default: auto)",
    )
    parser.add_argument(
        "--no-mixed-precision", action="store_false", dest="mixed_precision",
        help="disable CUDA float16 autocast/gradient scaling",
    )
    parser.add_argument(
        "--val-frac", type=float, default=0.1,
        help="fraction of globally shuffled games held out in the fixed split "
             "(default: 0.1)",
    )
    parser.add_argument(
        "--split-path", default=None,
        help="persistent game-split JSON; defaults beside --out",
    )
    parser.add_argument(
        "--rebuild-split", action="store_true",
        help="replace the saved split and validation shards using the requested seed",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="resume model/optimizer/progress from the latest mini-epoch checkpoint",
    )
    parser.add_argument(
        "--resume-path", default=None,
        help="latest-state checkpoint; defaults beside --out",
    )
    parser.add_argument(
        "--early-stopping-patience", type=int, default=5,
        help="stop after this many full validation checks without improvement; "
             "0 disables early stopping (default: 5)",
    )
    parser.add_argument(
        "--early-stopping-min-delta", type=float, default=0.001,
        help="minimum fixed-validation accuracy increase counted as improvement "
             "(default: 0.001)",
    )
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
        split_path=args.split_path, resume_path=args.resume_path,
        resume=args.resume, rebuild_split=args.rebuild_split,
        early_stopping_patience=args.early_stopping_patience,
        early_stopping_min_delta=args.early_stopping_min_delta,
    )
