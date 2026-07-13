"""Build the reproducible spec-07 verdict table from the audited pool."""
from __future__ import annotations

import csv
import os
import sys
from collections import Counter

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(ARCHIVE_DIR)))
sys.path.insert(0, ROOT)

import card_data as cd
from stat_bakes import BAKES


REVIEWS = {}

DECISION_ZERO = {
    37: "0: user decision — ignore Iron Thorns ex suppression as irrelevant to our deck.",
    56: "0: user decision — ignore Flutter Mane suppression.",
    225: "0: user decision — ignore Gastrodon suppression.",
    272: "0: user decision — ignore the Psychic weakness rewrite.",
}


def pool():
    grouped = {}
    with open(cd._default_csv(), encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            grouped.setdefault(int(row["Card ID"]), []).append(row)
    out = []
    for cid, rows in grouped.items():
        first = rows[0]
        card_type = first.get("Stage (Pokémon)/Type (Energy and Trainer)", "")
        abilities = [r.get("Effect Explanation", "") for r in rows
                     if (r.get("Move Name") or "").startswith("[Ability]")]
        category = first.get("Category", "")
        if "Tool" in card_type or "Tool" in category:
            out.append((cid, first["Card Name"], "tool", first.get("Effect Explanation", "")))
        elif "Stadium" in card_type or "Stadium" in category:
            out.append((cid, first["Card Name"], "stadium", first.get("Effect Explanation", "")))
        elif abilities:
            out.append((cid, first["Card Name"], "ability", " | ".join(abilities)))
    return sorted(out, key=lambda x: (x[2], x[0]))


def mod_text(cid):
    mods = BAKES[cid]["mods"]
    if not mods:
        return "suppression handled by Board"
    fields = []
    for m in mods:
        bits = [f"{m['stat']}={m['value']}", f"scope={m.get('scope', 'self')}"]
        for key in ("condition", "source_condition", "stack_key"):
            if m.get(key):
                bits.append(f"{key}={m[key]}")
        fields.append(", ".join(bits))
    return "; ".join(fields)


def zero_reason(cid, text):
    if cid in DECISION_ZERO:
        return DECISION_ZERO[cid]
    low = text.lower()
    if "+" in text and " hp" in low and "attached" in low:
        return "0: HP Tool is already reflected in observed maxHp/hp."
    if "prevent all damage" in low or "not knocked out" in low or "prevent that damage" in low:
        return "0: full immunity/Sturdy/probabilistic prevention is explicitly out of scope."
    if "heal " in low or "during pokémon checkup" in low:
        return "0: recurring/event-driven healing or Checkup damage is out of static KO baking scope."
    if "damage counter" in low:
        return "0: event-triggered damage-counter movement/placement is not a static attack modifier."
    if "cost" in low:
        return "0: no fixed v1 attack-cost reduction representable by this effect."
    return "0: inspected; no in-scope static HP/damage/weakness/resistance/retreat modifier."


def main():
    rows = []
    for cid, name, kind, effect in pool():
        if cid in BAKES:
            verdict, rationale = "bake", "Implemented in stat_bakes.py."
            mods = mod_text(cid)
        elif cid in REVIEWS:
            verdict, rationale, mods = "review", REVIEWS[cid], ""
        else:
            verdict, rationale, mods = "0", zero_reason(cid, effect), ""
        rows.append((cid, name, kind, verdict, effect, mods, rationale))

    out_tsv = os.path.join(ARCHIVE_DIR, "effect-bakes-verdicts.tsv")
    with open(out_tsv, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(("card_id", "name", "kind", "verdict", "effect_text", "mods", "rationale"))
        w.writerows(rows)

    reviews = [r for r in rows if r[3] == "review"]
    counts = Counter((r[2], r[3]) for r in rows)
    print(f"wrote {len(rows)} verdicts; bake={sum(r[3]=='bake' for r in rows)}, "
          f"review={len(reviews)}, zero={sum(r[3]=='0' for r in rows)}")
    for kind in ("tool", "stadium", "ability"):
        print(kind, {v: counts[kind, v] for v in ("bake", "review", "0")})


if __name__ == "__main__":
    main()
