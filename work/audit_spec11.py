"""Independent mechanical audit of specs 11a/11b against registry.json.

This intentionally parses the Markdown contracts rather than importing the observation
implementation, so the implementation cannot validate itself.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_A = ROOT / "Ceruledge-RL/specs/11a-pokemon-attribute-tag-vocabulary.md"
SPEC_B = ROOT / "Ceruledge-RL/specs/11b-trainer-energy-tag-vocabulary.md"
REGISTRY = ROOT / "Imitation-Learning/meta-card-registry/registry.json"
STRUCTURAL_TAGS = {"DAMAGE", "CONDITIONAL", "MULTI_CHOICE"}


def split_md_row(line: str) -> list[str]:
    """Split a Markdown table row, ignoring pipes inside code spans."""
    if not line.startswith("|"):
        return []
    cells: list[str] = []
    buf: list[str] = []
    in_code = False
    escaped = False
    for ch in line[1:]:
        if escaped:
            buf.extend(("\\", ch))
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
            continue
        if ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    if escaped:
        buf.append("\\")
    if buf:
        cells.append("".join(buf).strip())
    return cells


def code_spans(cell: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group(1)) for m in re.finditer(r"`([^`]*)`", cell)]


def normalize_pattern(pattern: str) -> str:
    # Markdown escapes table pipes, including inside code spans.
    pattern = pattern.replace(r"\|", "|")
    # The source text uses U+2019, while specs use ASCII quotes (sometimes optional).
    optional_quote = "__OPTIONAL_APOSTROPHE__"
    protected_quote = "__APOSTROPHE_CLASS__"
    pattern = pattern.replace("['’]", protected_quote)
    pattern = pattern.replace("'?", optional_quote)
    pattern = pattern.replace("'", "['’]")
    pattern = pattern.replace(optional_quote, "['’]?")
    pattern = pattern.replace(protected_quote, "['’]")
    return pattern


def parse_catalog(path: Path, heading: str, stop_heading: str | None) -> dict[str, list[str]]:
    text = path.read_text(encoding="utf-8")
    start = text.index(heading)
    end = text.index(stop_heading, start) if stop_heading else len(text)
    catalog: dict[str, list[str]] = {}
    for line in text[start:end].splitlines():
        cells = split_md_row(line)
        if len(cells) < 3:
            continue
        tag_match = re.fullmatch(r"`([A-Z][A-Z0-9_]*)`(?:\s+.*)?", cells[0])
        if not tag_match:
            continue
        tag = tag_match.group(1)
        patterns = []
        for _, _, span in code_spans(cells[2]):
            if len(span) >= 3 and span.startswith("/") and span.endswith("/i"):
                patterns.append(normalize_pattern(span[1:-2]))
        catalog[tag] = patterns
    return catalog


def depth_at(cell: str, target: int) -> int:
    depth = 0
    in_code = False
    for ch in cell[:target]:
        if ch == "`":
            in_code = not in_code
        elif not in_code and ch == "(":
            depth += 1
        elif not in_code and ch == ")":
            depth = max(0, depth - 1)
    return depth


def parse_assignments(path: Path) -> tuple[dict[str, list[str]], list[str]]:
    assignments: dict[str, list[str]] = {}
    duplicates: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = split_md_row(line)
        if len(cells) < 3:
            continue
        effect_spans = [span for _, _, span in code_spans(cells[1])]
        effect_ids = [s for s in effect_spans if re.fullmatch(r"card:\d+:[a-z_]+:\d+", s)]
        if len(effect_ids) != 1:
            continue
        effect_id = effect_ids[0]
        tags = []
        for start, _, span in code_spans(cells[2]):
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", span) and depth_at(cells[2], start) == 0:
                tags.append(span)
        if effect_id in assignments:
            duplicates.append(effect_id)
        assignments[effect_id] = tags
    return assignments, duplicates


def registry_rows() -> tuple[dict[str, str], dict[str, str]]:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    pokemon: dict[str, str] = {}
    trainer_energy: dict[str, str] = {}
    for card in data["cards"].values():
        cls = card["identity"]["class"]
        if cls == "pokemon":
            rows = card["attacks"] + card["abilities"]
            target = pokemon
        elif cls in {"trainer", "energy"}:
            rows = card["effects"]
            target = trainer_energy
        else:
            continue
        for row in rows:
            effect_id = row["effect_id"]
            if effect_id in target:
                raise AssertionError(f"duplicate registry effect_id: {effect_id}")
            target[effect_id] = row.get("text") or ""
    return pokemon, trainer_energy


def compile_catalog(catalog: dict[str, list[str]]) -> tuple[dict[str, re.Pattern[str]], dict[str, str]]:
    compiled: dict[str, re.Pattern[str]] = {}
    errors: dict[str, str] = {}
    for tag, patterns in catalog.items():
        if not patterns:
            continue
        try:
            compiled[tag] = re.compile("(?:" + ")|(?:".join(patterns) + ")", re.IGNORECASE)
        except re.error as exc:
            errors[tag] = str(exc)
    return compiled, errors


def main() -> None:
    catalog_a = parse_catalog(SPEC_A, "## Tag catalog (working", "### `distribution` qualifier")
    catalog_b_additions = parse_catalog(SPEC_B, "## Tag catalog additions", "## Manual assignment table")
    catalog_all = dict(catalog_a)
    catalog_all.update(catalog_b_additions)
    compiled, compile_errors = compile_catalog(catalog_all)

    assign_a, dup_a = parse_assignments(SPEC_A)
    assign_b, dup_b = parse_assignments(SPEC_B)
    rows_a, rows_b = registry_rows()
    all_rows = dict(rows_a)
    all_rows.update(rows_b)
    all_assign = dict(assign_a)
    all_assign.update(assign_b)

    print("CATALOG")
    print(json.dumps({
        "11a_tags": len(catalog_a),
        "11b_new_tags": len(catalog_b_additions),
        "combined_tags": len(catalog_all),
        "tags_without_regex": sorted(t for t, p in catalog_all.items() if not p),
        "compile_errors": compile_errors,
    }, indent=2, ensure_ascii=False))

    print("COVERAGE")
    print(json.dumps({
        "registry_11a": len(rows_a),
        "assignments_11a": len(assign_a),
        "missing_11a": sorted(set(rows_a) - set(assign_a)),
        "extra_11a": sorted(set(assign_a) - set(rows_a)),
        "duplicates_11a": dup_a,
        "registry_11b": len(rows_b),
        "assignments_11b": len(assign_b),
        "missing_11b": sorted(set(rows_b) - set(assign_b)),
        "extra_11b": sorted(set(assign_b) - set(rows_b)),
        "duplicates_11b": dup_b,
    }, indent=2, ensure_ascii=False))

    zero_rows = sorted(effect_id for effect_id, tags in all_assign.items() if not tags)
    print("ZERO_ROWS")
    print(json.dumps(zero_rows, indent=2))

    unknown_tags = sorted({tag for tags in all_assign.values() for tag in tags if tag not in catalog_all})
    counts_a = Counter(tag for tags in assign_a.values() for tag in tags)
    counts_b = Counter(tag for tags in assign_b.values() for tag in tags)
    print("ASSIGNMENT_COUNTS")
    print(json.dumps({
        "all_pairs_11a": sum(counts_a.values()),
        "all_pairs_11b": sum(counts_b.values()),
        "validated_pairs_11a": sum(n for tag, n in counts_a.items() if tag not in STRUCTURAL_TAGS),
        "validated_pairs_11b": sum(n for tag, n in counts_b.items() if tag not in STRUCTURAL_TAGS),
        "structural_counts_11a": {tag: counts_a[tag] for tag in sorted(STRUCTURAL_TAGS)},
        "structural_counts_11b": {tag: counts_b[tag] for tag in sorted(STRUCTURAL_TAGS)},
        "unknown_tags": unknown_tags,
    }, indent=2))

    recall_failures: list[dict[str, str]] = []
    for effect_id, tags in all_assign.items():
        for tag in tags:
            if tag in STRUCTURAL_TAGS or tag not in compiled:
                continue
            if not compiled[tag].search(all_rows[effect_id]):
                recall_failures.append({"tag": tag, "effect_id": effect_id, "text": all_rows[effect_id]})
    print("RECALL")
    print(json.dumps({
        "tested_pairs": sum(
            1 for tags in all_assign.values() for tag in tags
            if tag not in STRUCTURAL_TAGS and tag in compiled
        ),
        "failure_count": len(recall_failures),
        "failures": recall_failures,
    }, indent=2, ensure_ascii=False))

    assigned_by_tag: dict[str, set[str]] = defaultdict(set)
    for effect_id, tags in all_assign.items():
        for tag in tags:
            assigned_by_tag[tag].add(effect_id)
    false_positives: list[dict[str, str]] = []
    for tag, regex in compiled.items():
        if tag in STRUCTURAL_TAGS:
            continue
        for effect_id, row_text in all_rows.items():
            if effect_id not in assigned_by_tag[tag] and regex.search(row_text):
                false_positives.append({"tag": tag, "effect_id": effect_id, "text": row_text})
    print("PRECISION")
    print(json.dumps({
        "corpus_rows": len(all_rows),
        "false_positive_count": len(false_positives),
        "false_positives": false_positives,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
