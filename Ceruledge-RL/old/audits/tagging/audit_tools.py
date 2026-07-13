"""
audit_tools.py — Tooling for the iterative tag-audit workflow (see PLAN.md).

    python audit_tools.py snapshot <out.json>       # raw tags for the whole pool
    python audit_tools.py diff <pre.json> <post.json>
    python audit_tools.py sample <round> [n=100]    # unseen Pokemon-only batch dump

Run from anywhere; paths resolve relative to this file.
"""
from __future__ import annotations

import json
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")

_AUDITS = os.path.dirname(os.path.abspath(__file__))
_RL = os.path.dirname(os.path.dirname(os.path.dirname(_AUDITS)))
sys.path.insert(0, os.path.dirname(_RL))    # repo root
sys.path.insert(0, _RL)                     # Ceruledge-RL modules win

import card_data as cd
import effect_features as ef
from attack_overrides import get_override
from opponent_tags import card_tags
from dump_tags import _card_names

LEDGER = os.path.join(_AUDITS, "audited_ids.txt")


def _pokemon_pool() -> list[int]:
    """Cards playable as Pokemon: CSV stage is Basic/Stage 1/Stage 2."""
    reg = cd.CardRegistry.load()
    return sorted(cid for cid, st in reg.stats.items() if st.stage in cd.STAGES)


def _read_ledger() -> set[int]:
    if not os.path.exists(LEDGER):
        return set()
    with open(LEDGER, encoding="utf-8") as fh:
        return {int(line) for line in fh if line.strip()}


def cmd_snapshot(out_path: str) -> None:
    reg = cd.CardRegistry.load()
    snap = {}
    for cid in sorted(reg.stats):
        t = card_tags(cid)
        snap[str(cid)] = {
            "attacks": [{k: v for k, v in raw.items() if v} for raw in t.attack_raws],
            "ability": {k: v for k, v in t.ability_raw.items() if v},
            "max_damage": t.max_damage,
        }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, ensure_ascii=False, indent=0, sort_keys=True)
    print(f"snapshot: {len(snap)} cards -> {out_path}")


def cmd_diff(pre_path: str, post_path: str) -> None:
    with open(pre_path, encoding="utf-8") as fh:
        pre = json.load(fh)
    with open(post_path, encoding="utf-8") as fh:
        post = json.load(fh)
    names = _card_names()
    n = 0
    for cid in sorted(set(pre) | set(post), key=int):
        a, b = pre.get(cid, {}), post.get(cid, {})
        if a == b:
            continue
        n += 1
        print(f"--- {cid} | {names.get(int(cid), '?')}")
        for i, (ra, rb) in enumerate(zip(a.get("attacks", []), b.get("attacks", []))):
            if ra != rb:
                keys = sorted(set(ra) | set(rb))
                delta = {k: (ra.get(k, 0), rb.get(k, 0)) for k in keys
                         if ra.get(k, 0) != rb.get(k, 0)}
                print(f"    atk{i + 1}: {delta}")
        if a.get("ability") != b.get("ability"):
            keys = sorted(set(a.get("ability", {})) | set(b.get("ability", {})))
            delta = {k: (a.get("ability", {}).get(k, 0), b.get("ability", {}).get(k, 0))
                     for k in keys
                     if a.get("ability", {}).get(k, 0) != b.get("ability", {}).get(k, 0)}
            print(f"    ability: {delta}")
        if a.get("max_damage") != b.get("max_damage"):
            print(f"    max_damage: {a.get('max_damage')} -> {b.get('max_damage')}")
    print(f"# {n} cards changed")


def cmd_sample(round_no: int, n: int = 100) -> None:
    seen = _read_ledger()
    pool = [cid for cid in _pokemon_pool() if cid not in seen]
    random.seed(100 + round_no)
    batch = sorted(random.sample(pool, min(n, len(pool))))

    reg = cd.CardRegistry.load()
    names = _card_names()
    out_path = os.path.join(_AUDITS, f"batch{round_no}.txt")
    with open(out_path, "w", encoding="utf-8") as out:
        for cid in batch:
            st = reg.get(cid)
            t = card_tags(cid)
            ov = get_override(cid) or {}
            out.write(f"=== {cid} | {names.get(cid, '?')}"
                      f"{' | OVERRIDE' if ov else ''}\n")
            for i, raw in enumerate(t.attack_raws):
                atk = st.attacks[i] if i < len(st.attacks) else None
                active = {k: v for k, v in raw.items()
                          if k in ef.ATTACK_TAG_FIELDS and v}
                name = atk.name if atk is not None else "virtual aggregate"
                out.write(f"  ATK{i+1} [{name}] cost={raw['energy_cost']} "
                          f"dmg={raw['damage']} tags={active or '{}'}\n")
                text = (atk.effect_text if atk is not None
                        else f"virtual aggregate attack {i + 1}")
                out.write(f"    text: {text or '(none)'}\n")
            if st.abilities:
                active = {k: v for k, v in t.ability_raw.items() if v}
                out.write(f"  ABL tags={active or '{}'}\n")
                out.write(f"    text: {st.abilities[0]}\n")
                for extra in st.abilities[1:]:
                    out.write(f"    (2nd ability, ignored): {extra}\n")
            out.write(f"  max_damage={t.max_damage}\n")

    with open(LEDGER, "a", encoding="utf-8") as fh:
        for cid in batch:
            fh.write(f"{cid}\n")
    print(f"sample: round {round_no}, {len(batch)} cards -> {out_path} "
          f"(pool had {len(pool)} unseen)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "snapshot":
        cmd_snapshot(sys.argv[2])
    elif cmd == "diff":
        cmd_diff(sys.argv[2], sys.argv[3])
    elif cmd == "sample":
        cmd_sample(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 100)
    else:
        print(__doc__)
        sys.exit(1)
