"""
One-time preprocessing: game JSONs → packed numpy cache files.

Eliminates per-run costs of opening 7000+ files, JSON parsing, and
feature extraction. Training runs then load in seconds via np.load().

Usage (run from project root):
    python preprocess.py DATA_DIR --split SPLIT_FILE --out OUT_DIR

Example:
    python preprocess.py "Training-Data/6-16 only" \\
        --split SupervisedValueNetwork/data_split.json \\
        --out   SupervisedValueNetwork/

Produces three files in OUT_DIR:
    train_cache.npz
    val_cache.npz
    test_cache.npz

Each .npz contains:
    idx_flat  int32   (total_nonzero,)   packed sparse indices
    val_flat  float32 (total_nonzero,)   packed sparse values
    idx_ptr   int64   (n_obs + 1,)       CSR pointers into idx_flat
    off_arr   int32   (n_obs, 24)        per-word offsets (local to each obs)
    traj_ptr  int64   (n_traj + 1,)      pointers into observations
    terminals float32 (n_traj,)          +1 win / -1 loss
"""

import argparse
import importlib.util
import json
import os
import sys

import numpy as np
from tqdm import tqdm

# Load features.py by path to avoid collisions with any installed 'features' package.
# Searches the script's directory first, then its parent (handles running from a subdir).
def _load_features():
    here = os.path.dirname(os.path.abspath(__file__))
    for candidate in [here, os.path.dirname(here)]:
        path = os.path.join(candidate, "features.py")
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("_project_features", path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    raise ImportError("features.py not found in script dir or parent dir")

_features        = _load_features()
get_encoder_input = _features.get_encoder_input


def process_files(files: list, label: str) -> dict:
    idx_flat  = []
    val_flat  = []
    idx_ptr   = [0]
    off_rows  = []
    traj_ptr  = [0]
    terminals = []
    n_obs     = 0
    skipped   = 0

    for path in tqdm(files, desc=label, unit="game"):
        try:
            with open(path) as f:
                d = json.load(f)
        except Exception:
            skipped += 1
            continue

        rewards = d.get("rewards", [0, 0])
        steps   = d.get("steps", [])
        if len(steps) < 2:
            skipped += 1
            continue

        decks = [[], []]
        for pi in range(2):
            action    = steps[1][pi].get("action") or []
            decks[pi] = [c for c in action if isinstance(c, int)]

        per_player = [[], []]
        for step in steps:
            for pi in range(2):
                obs     = step[pi].get("observation", {})
                current = obs.get("current")
                if current is None:
                    continue
                your_index = current.get("yourIndex")
                if your_index is None:
                    continue
                deck = decks[your_index]
                if not deck:
                    continue
                try:
                    sv = get_encoder_input(obs, deck)
                    per_player[your_index].append(sv)
                except Exception:
                    continue

        for pi in range(2):
            svs = per_player[pi]
            if not svs or rewards[pi] is None:
                continue
            for sv in svs:
                idx_flat.extend(sv.index)
                val_flat.extend(sv.value)
                idx_ptr.append(len(idx_flat))
                off_rows.append(sv.offset)
                n_obs += 1
            traj_ptr.append(n_obs)
            terminals.append(float(rewards[pi]))

    n_traj = len(terminals)
    msg = f"  {label}: {n_traj} trajectories, {n_obs} observations"
    if skipped:
        msg += f" ({skipped} files skipped)"
    print(msg)

    off_arr = (np.array(off_rows, dtype=np.int32).reshape(-1, 24)
               if off_rows else np.zeros((0, 24), dtype=np.int32))

    return dict(
        idx_flat  = np.array(idx_flat,  dtype=np.int32),
        val_flat  = np.array(val_flat,  dtype=np.float32),
        idx_ptr   = np.array(idx_ptr,   dtype=np.int64),
        off_arr   = off_arr,
        traj_ptr  = np.array(traj_ptr,  dtype=np.int64),
        terminals = np.array(terminals, dtype=np.float32),
    )


def main():
    parser = argparse.ArgumentParser(description="Preprocess game JSONs into numpy cache.")
    parser.add_argument("data_dir", help="Directory of raw game JSON files (used only if split paths are relative)")
    parser.add_argument("--split",  required=True, help="Path to split_<tag>.json")
    parser.add_argument("--out",    default=".",   help="Output directory for *_cache_<tag>.npz files")
    parser.add_argument("--tag",    default=None,
                        help="Dataset tag used in output filenames (default: basename of data_dir, spaces→underscores)")
    args = parser.parse_args()

    tag = args.tag or os.path.basename(args.data_dir.rstrip("/\\")).replace(" ", "_")
    print(f"Dataset tag: {tag!r}")
    print(f"Split file : {args.split}")
    print(f"Output dir : {args.out}")

    with open(args.split) as f:
        split = json.load(f)

    os.makedirs(args.out, exist_ok=True)

    for key in ("train", "val", "test"):
        print(f"\nProcessing {key}...")
        arrays   = process_files(split[key], label=key)
        out_path = os.path.join(args.out, f"{key}_cache_{tag}.npz")
        np.savez_compressed(out_path, **arrays)
        size_mb  = os.path.getsize(out_path) / 1e6
        print(f"  Saved → {out_path}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
