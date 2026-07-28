"""Standalone check of the shipped data — needs NOTHING from this repository.

Copy the pack anywhere, then:

    python verify_standalone.py            # from inside reference/

Only torch and numpy are required. No engine, no `rl` package, no `sim` build. It reloads the
frozen tables, re-derives every invariant the docs assert, and (if the reference checkpoint is
present) rebuilds the static card dictionary the same way the network does.

Use this to check a reimplementation: your tables should reproduce the same numbers.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

PACK = Path(__file__).resolve().parent.parent
T = PACK / "tables"

EXPECT = {  # what 03-card-tables.md and 02-observation.md claim
    "ATK": (1300, 2, 130), "ABL": (1300, 130), "PLAY": (1300, 130),
    "STAT": (1300, 79), "PRIZE": (1300, 1), "ATTACK_SLOT": (1600,),
}
FLAT_DIM, FNUM, EFF_DIM, CF = 2239, 27, 130, 79


def ok(cond: bool, msg: str) -> bool:
    print(f"  [{'PASS' if cond else 'FAIL'}] {msg}")
    return cond


def main() -> int:
    print("=== frozen tables ===")
    tb = torch.load(T / "frozen_tables.pt", map_location="cpu", weights_only=False)
    good = True
    for k, shape in EXPECT.items():
        good &= ok(tuple(tb[k].shape) == shape, f"{k:<12}{tuple(tb[k].shape)} == {shape}")

    print("\n=== schema arithmetic ===")
    good &= ok(tb["ATK"].shape[-1] == EFF_DIM, f"effect descriptor width == {EFF_DIM}")
    good &= ok(tb["STAT"].shape[-1] == CF, f"stat line width == {CF}")
    good &= ok(40 * 5 + 40 * FNUM + 60 + 18 + 64 * 6 + 64 * 4 + 1 + 60 * 4 == FLAT_DIM,
               f"entity+deck+glob+options == {FLAT_DIM}")

    print("\n=== documented properties ===")
    # 'present' is descriptor field index 1
    present_atk0 = int((tb["ATK"][:, 0, 1] > 0).sum())
    present_atk1 = int((tb["ATK"][:, 1, 1] > 0).sum())
    present_abl = int((tb["ABL"][:, 1] > 0).sum())
    present_play = int((tb["PLAY"][:, 1] > 0).sum())
    print(f"  coverage: ATK0 {present_atk0}  ATK1 {present_atk1}  "
          f"ABL {present_abl}  PLAY {present_play}")
    good &= ok(present_atk0 == 1057 and present_atk1 == 499, "attack coverage matches the docs")
    good &= ok(present_abl == 281 and present_play == 146, "ability/play coverage matches the docs")

    # index 0 is the none/pad row for every table
    good &= ok(float(tb["ATK"][0].abs().sum()) == 0.0 and float(tb["STAT"][0].abs().sum()) == 0.0,
               "card id 0 is an all-zero pad row in every table")

    # prize liability takes exactly {0, 1/3, 2/3, 1}
    vals = sorted({round(float(x), 4) for x in tb["PRIZE"].flatten().unique()})
    good &= ok(vals == [0.0, 0.3333, 0.6667, 1.0], f"prize values are {vals} (= 0,1,2,3 over cap 3)")

    # attack slot map only ever points at slot 0 or 1
    good &= ok(int(tb["ATTACK_SLOT"].max()) <= 1, "ATTACK_SLOT only indexes slots 0..1")

    # dmg_modify_*_mag are the only signed descriptor fields (indices 29 and 31 in effect_tags)
    neg_cols = sorted({int(c) for c in (tb["ATK"] < 0).any(0).any(0).nonzero().flatten()})
    print(f"  descriptor columns that can go negative: {neg_cols}")

    print("\n=== card index ===")
    idx = json.loads((T / "card_index.json").read_text())
    over = {k: v for k, v in idx["cards"].items() if v["truncated_attacks"]}
    good &= ok(len(over) == 0, f"no card has >2 attacks (the 2-slot cap loses nothing) [{len(over)}]")
    good &= ok(len(idx["cards"]) == 1267, f"card index covers {len(idx['cards'])} real cards")

    print("\n=== static card dictionary (needs the checkpoint) ===")
    ck = PACK / "checkpoint" / "step_98304000.pt"
    if not ck.exists():
        print("  [SKIP] no checkpoint in the pack")
        return 0 if good else 1
    sd = torch.load(ck, map_location="cpu", weights_only=False)["state_dict"]
    total = sum(v.numel() for v in sd.values() if hasattr(v, "numel"))
    good &= ok(total == 2_370_259, f"checkpoint has {total:,} parameters")
    good &= ok(not any(k.startswith(("card.card_emb", "attack_emb")) for k in sd),
               "no learned card / attack identity table in the checkpoint")
    good &= ok(any(k.startswith("ora_") for k in sd),
               "the asymmetric value block IS present (not stripped at export)")

    # Rebuild the 224-wide dictionary exactly as SharedCardRep.static_table() does.
    lin = lambda w, b, x: x @ sd[w].T + sd[b]
    stat = lin("card.stat_proj.weight", "card.stat_proj.bias", tb["STAT"])          # [N,32]
    eff_in = torch.stack([tb["ATK"][:, 0], tb["ATK"][:, 1], tb["ABL"]], dim=1)      # [N,3,130]
    eff = lin("card.eff_proj.weight", "card.eff_proj.bias", eff_in).flatten(1)      # [N,144]
    row = torch.cat([stat, tb["PRIZE"], eff], dim=-1)                               # [N,177]
    good &= ok(row.shape[-1] == 177, f"pre-projection card row width == {row.shape[-1]}")
    CT = lin("card.card_proj.weight", "card.card_proj.bias", row)                   # [N,224]
    good &= ok(tuple(CT.shape) == (1300, 224), f"static dictionary {tuple(CT.shape)}")
    print(f"  dictionary mean |value| = {float(CT.abs().mean()):.5f}")

    # Cards whose FROZEN inputs collide are indistinguishable - there is no identity parameter.
    live = [i for i in range(1, 1300) if float(tb["STAT"][i].abs().sum()) > 0]
    keys = {}
    for i in live:
        keys.setdefault(hash(row[i].numpy().tobytes()), []).append(i)
    groups = [v for v in keys.values() if len(v) > 1]
    collided = sum(len(v) for v in groups)
    print(f"  collision groups: {len(groups)} covering {collided} of {len(live)} live cards "
          f"({100*collided/len(live):.1f}%)")
    if groups:
        g = max(groups, key=len)
        names = [idx["cards"].get(str(c), {}).get("name", "?") for c in g[:4]]
        print(f"  largest group: {g[:4]} -> {names}")

    print("\n" + ("ALL CHECKS PASSED" if good else "SOME CHECKS FAILED"))
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
