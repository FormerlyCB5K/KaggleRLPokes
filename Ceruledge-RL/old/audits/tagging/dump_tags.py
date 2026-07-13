"""
dump_tags.py — Audit dump for spec-03 tag extraction (required deliverable).

Iterates the full card pool and emits, per Pokemon card: name/id, each attack's raw
effect text next to its extracted block (RAW values, not normalized), and the ability
text next to its block — TSV, greppable, one row per attack/ability.

Usage:
    python dump_tags.py                > tags_dump.tsv     # full pool
    python dump_tags.py --tagged-only  > tags_dump.tsv     # only rows with a tag hit
    python dump_tags.py --ids 235 290  # specific cards

Columns:
    card_id  name  kind(attack1/attack2/ability)  tier(override/keyword/zeros)
    <raw tag fields>  max_damage  text
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

_ARCHIVE = os.path.dirname(os.path.abspath(__file__))
_RL = os.path.dirname(os.path.dirname(os.path.dirname(_ARCHIVE)))
sys.path.insert(0, _RL)

import card_data as cd
import effect_features as ef
from attack_overrides import get_override
from opponent_tags import card_tags


def _card_names() -> dict[int, str]:
    names: dict[int, str] = {}
    with open(cd._default_csv(), encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            names.setdefault(int(row["Card ID"]), row.get("Card Name", ""))
    return names


def _fmt(text: str) -> str:
    return (text or "").replace("\t", " ").replace("\n", " ").strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tagged-only", action="store_true",
                    help="only emit rows where at least one tag fired")
    ap.add_argument("--ids", type=int, nargs="*", default=None,
                    help="restrict to these card ids")
    args = ap.parse_args()

    reg = cd.CardRegistry.load()
    names = _card_names()
    out = csv.writer(sys.stdout, delimiter="\t", lineterminator="\n")

    atk_fields = ef.ATTACK_TAG_FIELDS
    abl_fields = ef.ABILITY_TAG_FIELDS
    header = (["card_id", "name", "kind", "tier"]
              + sorted(set(atk_fields) | set(abl_fields))
              + ["cost", "damage", "max_damage", "text"])
    out.writerow(header)
    tag_cols = sorted(set(atk_fields) | set(abl_fields))

    ids = args.ids if args.ids else sorted(reg.stats)
    n_rows = 0
    for cid in ids:
        st = reg.get(cid)
        if not st.attacks and not st.abilities:
            continue                                   # trainers/energy: no tag surface
        t = card_tags(cid)
        ov = get_override(cid) or {}
        name = names.get(cid, "?")

        for i, raw in enumerate(t.attack_raws):
            is_virtual = ov.get("virtual_attacks") is not None
            tier = ("override" if ov.get("attacks") is not None or is_virtual
                    else "keyword" if any(raw.get(f, 0) for f in atk_fields)
                    else "zeros")
            if args.tagged_only and tier == "zeros":
                continue
            atk = st.attacks[i] if i < len(st.attacks) else None
            text = (f"(virtual aggregate attack {i + 1})" if is_virtual
                    else (_fmt(atk.effect_text) or f"({atk.name})"))
            out.writerow([cid, name, f"attack{i + 1}", tier]
                         + [raw.get(c, "") if c in atk_fields else "" for c in tag_cols]
                         + [raw["energy_cost"], raw["damage"], t.max_damage,
                            text])
            n_rows += 1

        if st.abilities or ov.get("ability") is not None:
            raw = t.ability_raw
            tier = ("override" if ov.get("ability") is not None
                    else "keyword" if any(raw.get(f, 0) for f in abl_fields)
                    else "zeros")
            if not (args.tagged_only and tier == "zeros"):
                out.writerow([cid, name, "ability", tier]
                             + [raw.get(c, "") if c in abl_fields else "" for c in tag_cols]
                             + ["", "", t.max_damage,
                                _fmt(st.abilities[0] if st.abilities else "(override only)")])
                n_rows += 1

    print(f"# {n_rows} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
