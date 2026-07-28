"""Runnable end-to-end example: a saved replay -> the 2,239-float decision record -> a forward pass.

This is the shortest complete path through the system. Run it and read the printed output
alongside `02-observation.md`; every number it prints is explained there.

    cd <repo root>
    .venv/bin/python docs/sprint-2026-07-28-handoff/reference/featurize_a_replay.py

It needs no GPU, no engine build and no checkpoint for the first three stages. The final
forward pass is skipped automatically if no checkpoint is on disk.
"""
from __future__ import annotations

import glob
import gzip
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from rl.features import spec as S                      # noqa: E402
from rl.features.featurize import featurize            # noqa: E402
from rl.features.flat import FLAT_DIM, _OFF, encode    # noqa: E402


def load_a_decision_frame():
    """Return (current, select, seat, deck, filename) for a substantive mid-game decision.

    A replay frame is {"obs": {"current":..., "select":...}, "action": [...], ...}.
    `obs` is ALREADY the acting seat's masked view - it is exactly what the agent legally
    sees, so no extra masking is needed. Frames with no `select` block are not decisions.

    We scan for the frame with the most on-board entities so the printed layout is
    representative rather than a setup prompt, and take the DECK OF THE ACTING SEAT
    (the deck-summary block must describe the player being scored).
    """
    paths = sorted(glob.glob(str(REPO / "data" / "replays" / "*.json.gz")))
    if not paths:
        raise SystemExit("no replays in data/replays/ - run any arena match first")

    best = None
    for path in paths[:40]:
        try:
            with gzip.open(path, "rt") as fh:
                replay = json.load(fh)
        except Exception:
            continue
        for frame in replay.get("frames", []):
            obs = frame.get("obs") or {}
            cur, sel = obs.get("current"), obs.get("select")
            if not cur or not sel or len(sel.get("option") or []) < 3:
                continue
            players = cur.get("players") or []
            if len(players) < 2:
                continue
            seat = int(cur.get("yourIndex", 0))
            me = players[seat]
            n = len(me.get("bench") or []) + len(me.get("hand") or [])
            if best is None or n > best[0]:
                deck = replay["agents"][seat]["deck"]
                best = (n, cur, sel, seat, deck, Path(path).name)
        if best and best[0] >= 12:          # good enough; stop scanning
            break
    if best is None:
        raise SystemExit("no decision frame found")
    _, cur, sel, seat, deck, fname = best
    return cur, sel, seat, deck, fname


def main() -> int:
    cur, sel, seat, deck, fname = load_a_decision_frame()
    print(f"replay      : {fname}")
    print(f"seat        : {seat}   turn {cur.get('turn')}   options {len(sel['option'])}")

    # ---------------------------------------------------------------- stage 1: dict
    # featurize() is a PURE FUNCTION of (masked current, select, seat, decklist).
    # No persistent state, no prior frame, no logs. See 04-featurizer.md.
    feat = featurize(cur, sel, seat, deck=deck)
    print("\n--- stage 1: featurize() -> variable-length dict ---")
    for k, v in feat.items():
        arr = np.asarray(v)
        print(f"  {k:<16}{str(arr.shape):<12}{arr.dtype}")

    # ---------------------------------------------------------------- stage 2: flat
    flat = encode(feat)
    assert flat.shape == (FLAT_DIM,) and flat.dtype == np.float32
    print(f"\n--- stage 2: encode() -> one float32[{FLAT_DIM}] ---")
    print("  every field, including integer card ids, is stored as float32;")
    print("  ids are < 2**24 so this is lossless (see 02-observation.md).")

    n_live = int(flat[_OFF["tok_mask"][0]:_OFF["tok_mask"][1]].sum())
    n_opt = int(flat[_OFF["n_options"][0]])
    print(f"  live entity slots : {n_live} / {S.FNUM and 40}")
    print(f"  live options      : {n_opt} / 64")

    # Show the entity block decoded, so the layout is concrete.
    ids = flat[_OFF["tok_card_id"][0]:_OFF["tok_card_id"][1]].astype(int)
    roles = flat[_OFF["tok_role"][0]:_OFF["tok_role"][1]].astype(int)
    rolename = {v: k for k, v in
                {"PAD": 0, "MY_ACTIVE": 1, "MY_BENCH": 2, "OPP_ACTIVE": 3, "OPP_BENCH": 4,
                 "MY_HAND": 5, "DECK": 6, "GLOBAL": 7, "CLS": 8, "STADIUM": 9}.items()}
    print("\n  entity slots (first 12):")
    for i in range(min(12, n_live)):
        num = flat[_OFF["tok_num"][0] + i * S.FNUM: _OFF["tok_num"][0] + (i + 1) * S.FNUM]
        print(f"    slot {i:>2}  card={ids[i]:>5}  role={rolename.get(roles[i], '?'):<11}"
              f"hp_ratio={num[2]:.2f}  energy={num[6] * 5:.0f}")

    # ---------------------------------------------------------------- stage 3: batch
    from rl.features.flat import decode_batch
    batch = decode_batch(flat[None, :].copy())
    print("\n--- stage 3: decode_batch() -> model-ready tensors ---")
    for k, v in batch.items():
        print(f"  {k:<16}{str(tuple(v.shape)):<14}{v.dtype}")

    # ---------------------------------------------------------------- stage 4: net
    # NB fs_config_from_sd() reads d_model off `ora_proj.weight`, so a state_dict WITHOUT
    # the asymmetric value block cannot be loaded at all - the block is effectively
    # mandatory in the checkpoint even though live play never feeds it. See 01-architecture.md.
    ckpts = [p for p in sorted(glob.glob(str(REPO / "data" / "ckpt" / "**" / "step_*.pt"),
                                         recursive=True))
             if "fs-arch-v2" in p]
    if not ckpts:
        print("\n--- stage 4: skipped (no fs-arch-v2 checkpoint under data/ckpt/) ---")
        return 0
    import torch
    from rl.model.fs_net import FSNetRL, fs_config_from_sd, strip_removed_keys
    sd = strip_removed_keys(torch.load(ckpts[-1], map_location="cpu",
                                       weights_only=False)["state_dict"])
    net = FSNetRL(fs_config_from_sd(sd))
    net.load_state_dict(sd)
    net.eval()
    with torch.no_grad():
        out = net(batch)
    live = out.logits[0][:n_opt]
    print(f"\n--- stage 4: forward pass ({Path(ckpts[-1]).name}) ---")
    print(f"  params        : {sum(p.numel() for p in net.parameters()):,}")
    print(f"  logits        : {tuple(out.logits.shape)}  (pad slots are -inf)")
    print(f"  value         : {float(out.value[0]):+.4f}   <- a RETURN, not a probability")
    print(f"  argmax option : {int(live.argmax())} of {n_opt}")
    print(f"  option types  : {[int(x) for x in batch['opt_type'][0][:n_opt]]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
