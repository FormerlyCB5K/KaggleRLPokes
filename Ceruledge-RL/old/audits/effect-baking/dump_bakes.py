"""
dump_bakes.py — Worklist dump for the spec-07 effect-baking full audit.

Emits every Tool, Stadium, and ability-holding Pokemon with its effect text and current
stat_bakes.BAKES status, so the manual per-card audit (Phase 2) can proceed.

    python dump_bakes.py                 # TSV: all tools + stadiums + abilities
    python dump_bakes.py --unbaked-only  # only cards with NO bake entry yet
    python dump_bakes.py --kind tool     # restrict to tool | stadium | ability
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
_AUDITS = os.path.dirname(os.path.abspath(__file__))
_RL = os.path.dirname(os.path.dirname(os.path.dirname(_AUDITS)))
sys.path.insert(0, os.path.dirname(_RL))
sys.path.insert(0, _RL)

import card_data as cd
import stat_bakes as sb


def _rows():
    """(card_id, name, kind, effect_text) for every Tool / Stadium / ability-holder."""
    path = cd._default_csv()
    seen_ability = set()
    with open(path, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            cid = int(row["Card ID"])
            name = row.get("Card Name", "")
            typ = row.get("Stage (Pokémon)/Type (Energy and Trainer)", "") or ""
            cat = row.get("Category", "") or ""
            eff = (row.get("Effect Explanation", "") or "").replace("\t", " ").replace("\n", " ")
            move = (row.get("Move Name", "") or "")
            if "Tool" in typ or "Tool" in cat:
                yield cid, name, "tool", eff
            elif "Stadium" in typ or "Stadium" in cat:
                yield cid, name, "stadium", eff
            elif move.strip().startswith("[Ability]") and cid not in seen_ability:
                seen_ability.add(cid)
                yield cid, name, "ability", eff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unbaked-only", action="store_true")
    ap.add_argument("--kind", choices=["tool", "stadium", "ability"])
    args = ap.parse_args()

    out = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")
    out.writerow(["card_id", "name", "kind", "baked", "mods", "text"])
    counts = {"tool": [0, 0], "stadium": [0, 0], "ability": [0, 0]}   # [total, baked]
    for cid, name, kind, eff in _rows():
        if args.kind and kind != args.kind:
            continue
        entry = sb.BAKES.get(cid)
        baked = entry is not None and entry["kind"] == kind
        counts[kind][0] += 1
        if baked:
            counts[kind][1] += 1
        if args.unbaked_only and baked:
            continue
        mods = ";".join(f"{m['stat']}={m['value']}" for m in entry["mods"]) if baked else ""
        out.writerow([cid, name, kind, "yes" if baked else "", mods, eff])

    for k, (tot, bk) in counts.items():
        print(f"# {k}: {tot} total, {bk} baked", file=sys.stderr)


if __name__ == "__main__":
    main()
