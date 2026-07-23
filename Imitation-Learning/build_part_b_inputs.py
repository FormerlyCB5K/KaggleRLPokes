"""Build reproducible Spec-12b intake, crosswalk, and audit-worklist artifacts."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_ZIP = REPO_ROOT / "Imitation-Learning" / "ptcg_engine.zip"
ENGINE_ROOT = REPO_ROOT / "Imitation-Learning" / "ptcg_engine" / "ptcgProgram 22"
CARD_IMPL = ENGINE_ROOT / "CardImpl.h"
CARD_CSV = REPO_ROOT / "Decks" / "Deck-Builder" / "EN_Card_Data.csv"
CATALOG = (
    REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "all-datasets"
    / "top_ladder_card_catalog.json"
)
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"

SCHEMA_VERSION = 1
POKEMON_SUBTYPES = {"Basic Pokémon", "Stage 1 Pokémon", "Stage 2 Pokémon"}
TRAINER_SUBTYPES = {"Item", "Supporter", "Pokémon Tool", "Stadium"}
ENERGY_SUBTYPES = {"Basic Energy", "Special Energy"}
TYPE_FIELD = "Stage (Pokémon)/Type (Energy and Trainer)"
ENGINE_CARD_TYPES = {
    0: "POKEMON",
    1: "ITEM",
    2: "TOOL",
    3: "SUPPORTER",
    4: "STADIUM",
    5: "BASIC_ENERGY",
    6: "SPECIAL_ENERGY",
}


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def strip_cpp_comments(source: str) -> str:
    """Replace C++ comments with spaces while preserving strings and line numbers."""
    out: list[str] = []
    index = 0
    state = "code"
    quote = ""
    escaped = False
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if state == "code":
            if char in ('"', "'"):
                state = "string"
                quote = char
                escaped = False
                out.append(char)
            elif char == "/" and nxt == "/":
                state = "line_comment"
                out.extend("  ")
                index += 1
            elif char == "/" and nxt == "*":
                state = "block_comment"
                out.extend("  ")
                index += 1
            else:
                out.append(char)
        elif state == "string":
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                state = "code"
        elif state == "line_comment":
            if char == "\n":
                out.append(char)
                state = "code"
            else:
                out.append(" ")
        else:
            if char == "*" and nxt == "/":
                out.extend("  ")
                index += 1
                state = "code"
            elif char == "\n":
                out.append(char)
            else:
                out.append(" ")
        index += 1
    if state == "block_comment":
        raise ValueError("unterminated C++ block comment")
    return "".join(out)


def source_card_locations() -> dict[int, int]:
    source = CARD_IMPL.read_text(encoding="utf-8-sig")
    active = strip_cpp_comments(source)
    locations: dict[int, int] = {}
    for match in re.finditer(r"\bCreateCard\s*\(\s*(\d+)\s*,", active):
        card_id = int(match.group(1))
        if card_id in locations:
            raise ValueError(f"duplicate active CreateCard definition: {card_id}")
        locations[card_id] = active.count("\n", 0, match.start()) + 1
    return locations


def source_attack_count() -> int:
    active = strip_cpp_comments(CARD_IMPL.read_text(encoding="utf-8-sig"))
    return len(re.findall(r"\.attack\s*\(", active))


SKILL_STARTERS = {
    "ability", "abilityBattleField", "abilityActive", "abilityBench", "abilityHand",
    "abilityTrash", "specialAbility", "abilityPlay", "abilityEvolve",
    "abilityBenchToActive", "abilityActiveToBench", "activateSkill",
    "activateSkillOnceTurn", "activateSkillOnceTurnActive",
    "activateSkillOnceTurnBench", "activateSkillFirstTurn", "playSkill", "attachSkill",
    "attachSkillBench", "energySkill", "toolSkill", "stadiumSkill",
    "stadiumActivateSkillOnceTurn", "delaySkill",
}


def source_card_blocks() -> dict[int, dict]:
    source = CARD_IMPL.read_text(encoding="utf-8-sig")
    active = strip_cpp_comments(source)
    matches = list(re.finditer(r"\bCreateCard\s*\(\s*(\d+)\s*,", active))
    blocks: dict[int, dict] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(active)
        block = active[match.start():end]
        card_id = int(match.group(1))
        start_line = active.count("\n", 0, match.start()) + 1
        calls = [
            {
                "method": call.group(1),
                "offset": call.start(),
                "line": start_line + block.count("\n", 0, call.start()),
            }
            for call in re.finditer(r"\.(\w+)\s*\(", block)
        ]
        starters = [call for call in calls if call["method"] == "attack" or call["method"] in SKILL_STARTERS]
        segments: list[dict] = []
        for segment_index, starter in enumerate(starters):
            segment_end = (
                starters[segment_index + 1]["offset"]
                if segment_index + 1 < len(starters)
                else len(block)
            )
            segment_calls = [
                call for call in calls
                if starter["offset"] <= call["offset"] < segment_end
            ]
            segment_text = block[starter["offset"]:segment_end]
            tokens: list[str] = []
            for effect_call in re.finditer(
                r"\.(?:preEffect\w*|postEffect\w*|effect\w*|condition\w*|trigger\w*|target\w*)\s*\(([^)]*)\)",
                segment_text,
            ):
                tokens.extend(re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", effect_call.group(1)))
            segments.append({
                "kind": "attack" if starter["method"] == "attack" else "skill",
                "starter": starter["method"],
                "source_line_start": starter["line"],
                "source_line_end": start_line + block.count("\n", 0, segment_end),
                "method_calls": [call["method"] for call in segment_calls],
                "effect_tokens": list(dict.fromkeys(tokens)),
                "chain_sha256": sha256_bytes(segment_text.encode("utf-8")),
            })
        tera_calls = [call for call in calls if call["method"] == "tera"]
        blocks[card_id] = {
            "source_line_start": start_line,
            "source_line_end": start_line + block.count("\n"),
            "method_calls": [call["method"] for call in calls],
            "segments": segments,
            "tera_lines": [call["line"] for call in tera_calls],
        }
    return blocks


def current_dynamic_references() -> dict[int, list[dict]]:
    path = REPO_ROOT / "Ceruledge-RL" / "features.py"
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    refs: dict[int, list[dict]] = defaultdict(list)
    direct = re.compile(r"(?:\bcid|poke\.id)\s*==\s*(\d+)")
    set_assignment = re.compile(r"^\s*(_[A-Z0-9_]+)\s*=\s*frozenset\(\{([^}]*)\}\)")
    for line_number, line in enumerate(lines, start=1):
        for match in direct.finditer(line):
            refs[int(match.group(1))].append({
                "path": repo_path(path), "line": line_number, "kind": "direct_dynamic_formula"
            })
        assignment = set_assignment.search(line)
        if assignment:
            for token in re.findall(r"\b\d+\b", assignment.group(2)):
                refs[int(token)].append({
                    "path": repo_path(path), "line": line_number,
                    "kind": "dynamic_dependency_group", "group": assignment.group(1),
                })
    return dict(refs)


def encoder_modules():
    encoder_root = REPO_ROOT / "Ceruledge-RL"
    if str(encoder_root) not in sys.path:
        sys.path.insert(0, str(encoder_root))
    import attack_overrides
    import card_data
    import effect_features
    import opponent_tags
    import stat_bakes

    return attack_overrides, card_data, effect_features, opponent_tags, stat_bakes


def dataset_module_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    pattern = re.compile(rb'"module_version"\s*:\s*"([^"]+)"')
    for archive in sorted(DATA_ROOT.rglob("*.zip")):
        with zipfile.ZipFile(archive) as bundle:
            member = next(i for i in bundle.infolist() if i.filename.lower().endswith(".json"))
            match = pattern.search(bundle.read(member))
            if not match:
                raise ValueError(f"module_version missing: {archive}")
            versions[repo_path(archive)] = match.group(1).decode("ascii")
    return versions


def engine_snapshot() -> tuple[list, list]:
    sys.path.insert(0, str(REPO_ROOT))
    from cg_download.api import all_attack, all_card_data

    return all_card_data(), all_attack()


def build_engine_manifest() -> dict:
    with zipfile.ZipFile(ENGINE_ZIP) as bundle:
        bad_crc = bundle.testzip()
        zip_files = [item for item in bundle.infolist() if not item.is_dir()]
        extracted_files = sorted(path for path in ENGINE_ROOT.rglob("*") if path.is_file())
        zip_by_relative = {
            Path(item.filename).relative_to("ptcgProgram 22").as_posix(): item
            for item in zip_files
            if item.filename.startswith("ptcgProgram 22/")
        }
        extracted_by_relative = {
            path.relative_to(ENGINE_ROOT).as_posix(): path for path in extracted_files
        }
        missing_extracted = sorted(set(zip_by_relative) - set(extracted_by_relative))
        extra_extracted = sorted(set(extracted_by_relative) - set(zip_by_relative))
        mismatched: list[str] = []
        file_records: list[dict] = []
        for relative in sorted(set(zip_by_relative) & set(extracted_by_relative)):
            archived = bundle.read(zip_by_relative[relative])
            extracted = extracted_by_relative[relative].read_bytes()
            if archived != extracted:
                mismatched.append(relative)
            file_records.append({
                "path": relative,
                "size_bytes": len(extracted),
                "sha256": sha256_bytes(extracted),
            })

    source_locations = source_card_locations()
    source_attacks = source_attack_count()
    binary_cards, binary_attacks = engine_snapshot()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    meta_ids = {int(card["card_id"]) for card in catalog}
    binary_ids = {int(card.cardId) for card in binary_cards}
    module_versions = dataset_module_versions()

    return {
        "schema_version": SCHEMA_VERSION,
        "engine_identity": {
            "competition_module_version": "1.32.0",
            "user_confirmation": (
                "ptcg_engine.zip is exactly the engine that ran the July 12-14 games"
            ),
            "archive": {
                "path": repo_path(ENGINE_ZIP),
                "size_bytes": ENGINE_ZIP.stat().st_size,
                "sha256": sha256_file(ENGINE_ZIP),
                "members": len(zip_files) + 2,
                "files": len(zip_files),
                "crc_check": "passed" if bad_crc is None else f"failed:{bad_crc}",
            },
            "dataset_module_versions": module_versions,
        },
        "license_scope": {
            "classification": "competition-use-only; not open-source",
            "decision": (
                "Approved for private use throughout this working project; do not share"
            ),
            "readme": repo_path(ENGINE_ROOT / "README.md"),
            "license": repo_path(
                ENGINE_ROOT / "LICENSES" / "LicenseRef-PTCG-ABC-Competition-Use-Only.txt"
            ),
        },
        "extraction": {
            "root": repo_path(ENGINE_ROOT),
            "file_count": len(extracted_files),
            "total_size_bytes": sum(path.stat().st_size for path in extracted_files),
            "missing_extracted": missing_extracted,
            "extra_extracted": extra_extracted,
            "content_mismatches": mismatched,
            "files": file_records,
        },
        "universe_checks": {
            "source_active_card_ids": len(source_locations),
            "source_attack_calls": source_attacks,
            "installed_binary_card_ids": len(binary_ids),
            "installed_binary_attacks": len(binary_attacks),
            "source_binary_card_id_sets_equal": set(source_locations) == binary_ids,
            "meta_card_ids": len(meta_ids),
            "meta_ids_missing_from_source": sorted(meta_ids - set(source_locations)),
            "meta_ids_missing_from_binary": sorted(meta_ids - binary_ids),
            "english_database_sha256": sha256_file(CARD_CSV),
            "part_a_catalog_sha256": sha256_file(CATALOG),
        },
        "validation_strategy": {
            "source_build_toolchain": {
                "required": "Visual Studio 2022 C++20 / v143",
                "msbuild": "unavailable",
                "cl": "unavailable",
            },
            "approved_route": (
                "Exact source traces plus focused scenarios on cg_download simulator"
            ),
            "installed_binary": {
                "windows_path": repo_path(REPO_ROOT / "cg_download" / "cg.dll"),
                "windows_sha256": sha256_file(REPO_ROOT / "cg_download" / "cg.dll"),
                "linux_path": repo_path(REPO_ROOT / "cg_download" / "libcg.so"),
                "linux_sha256": sha256_file(REPO_ROOT / "cg_download" / "libcg.so"),
            },
            "human_review_records": ["HR-B01-001", "HR-B01-002", "HR-B01-003"],
        },
    }


def build_path_map() -> str:
    return """# Engine Source Path Map

- Package/build/license: `README.md`, `LICENSES/`, `game.sln`, `game.vcxproj`
- Card definitions and English text: `CardImpl.h`
- Card-definition builder API: `CreateCard.h`
- Core card/skill structures: `Card.h`, `Skill.h`, `Types.h`
- Effect execution: `EffectProc.h`, `EffectInstant.h`, `EffectContinual.h`
- Conditions and targets: `SatisfyCondition.h`, `TargetList.h`, `SetProperty.h`
- Trigger processing: `PullTrigger.h`, `ActivateInfo.h`
- Game flow and selection: `GameProc.h`, `SelectProc.h`, `SetupProc.h`
- Observation/log serialization: `ToJson.h`, `ApiJson.h`, `AddLog.h`
- Public native API: `Export.cpp`, `Api.h`, `ApiData.h`
- Card/attack enumeration used for crosswalk validation: `Export.cpp::AllCard/AllAttack`
- Included tests: none

Validation uses exact source references plus focused behavior scenarios through the
installed `cg_download` simulator, as approved in `HR-B01-003`.
"""


def card_class_from_subtype(subtype: str) -> str:
    if subtype in POKEMON_SUBTYPES:
        return "pokemon"
    if subtype in TRAINER_SUBTYPES:
        return "trainer"
    if subtype in ENERGY_SUBTYPES:
        return "energy"
    return "unresolved"


def normalize_definition_text(value: str | None) -> str:
    if not value or value == "n/a":
        return ""
    text = unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


def normalize_effect_name(value: str | None) -> str:
    name = normalize_definition_text(value).strip()
    if name.startswith("[Ability]"):
        name = name[len("[Ability]"):].strip()
    return name


def build_crosswalk() -> tuple[list[dict], list[dict], dict]:
    catalog_cards = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    catalog = {int(card["card_id"]): card for card in catalog_cards}
    database_rows: dict[int, list[dict]] = defaultdict(list)
    with CARD_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            database_rows[int(row["Card ID"])].append(row)
    binary_cards, binary_attacks = engine_snapshot()
    binary = {int(card.cardId): card for card in binary_cards}
    attacks = {int(attack.attackId): attack for attack in binary_attacks}
    source = source_card_locations()

    rows: list[dict] = []
    issues: list[dict] = []
    for card_id in sorted(catalog):
        cat = catalog[card_id]
        db_rows = database_rows.get(card_id, [])
        engine = binary.get(card_id)
        source_line = source.get(card_id)
        db_name = db_rows[0]["Card Name"] if db_rows else None
        db_subtype = db_rows[0][TYPE_FIELD] if db_rows else None
        db_class = card_class_from_subtype(db_subtype) if db_subtype else None
        engine_name = engine.name if engine else None
        name_exact = bool(db_name == engine_name == cat["card_name"])
        mapped = bool(db_rows and engine and source_line and name_exact and db_class == cat["card_class"])

        engine_attack_ids = [int(value) for value in engine.attacks] if engine else []
        engine_attack_rows = [attacks[value] for value in engine_attack_ids if value in attacks]
        if len(engine_attack_rows) != len(engine_attack_ids):
            issues.append({
                "card_id": card_id,
                "code": "missing_engine_attack",
                "severity": "error",
            })

        db_attack_rows = [row for row in db_rows if (row.get("Cost") or "n/a") != "n/a"]
        db_effect_rows = [
            row for row in db_rows
            if (row.get("Cost") or "n/a") == "n/a"
            and (row.get("Move Name") or "").strip() != "[Tera]"
            and normalize_definition_text(row.get("Effect Explanation"))
        ]
        definition_differences: list[dict] = []
        formatting_normalizations: list[dict] = []
        if len(db_attack_rows) != len(engine_attack_rows):
            definition_differences.append({
                "kind": "attack_count",
                "database": len(db_attack_rows),
                "engine": len(engine_attack_rows),
            })
        for index, (db_attack, engine_attack) in enumerate(zip(db_attack_rows, engine_attack_rows)):
            if normalize_effect_name(db_attack["Move Name"]) != normalize_effect_name(engine_attack.name):
                definition_differences.append({
                    "kind": "attack_name",
                    "index": index,
                    "database": db_attack["Move Name"],
                    "engine": engine_attack.name,
                })
            elif db_attack["Move Name"] != engine_attack.name:
                formatting_normalizations.append({"kind": "attack_name", "index": index})
            if normalize_definition_text(db_attack["Effect Explanation"]) != normalize_definition_text(engine_attack.text):
                definition_differences.append({
                    "kind": "attack_text",
                    "index": index,
                    "database_sha256": sha256_bytes(normalize_definition_text(db_attack["Effect Explanation"]).encode("utf-8")),
                    "engine_sha256": sha256_bytes(normalize_definition_text(engine_attack.text).encode("utf-8")),
                })
        engine_skills = list(engine.skills) if engine else []
        if len(db_effect_rows) != len(engine_skills):
            definition_differences.append({
                "kind": "effect_count",
                "database": len(db_effect_rows),
                "engine": len(engine_skills),
            })
        for index, (db_effect, engine_skill) in enumerate(zip(db_effect_rows, engine_skills)):
            expected_name = (db_effect.get("Move Name") or "").strip()
            if expected_name and expected_name != "n/a" and normalize_effect_name(expected_name) != normalize_effect_name(engine_skill.name):
                definition_differences.append({
                    "kind": "effect_name",
                    "index": index,
                    "database": expected_name,
                    "engine": engine_skill.name,
                })
            elif expected_name and expected_name != "n/a" and expected_name != engine_skill.name:
                formatting_normalizations.append({"kind": "effect_name", "index": index})
            if normalize_definition_text(db_effect["Effect Explanation"]) != normalize_definition_text(engine_skill.text):
                definition_differences.append({
                    "kind": "effect_text",
                    "index": index,
                    "database_sha256": sha256_bytes(normalize_definition_text(db_effect["Effect Explanation"]).encode("utf-8")),
                    "engine_sha256": sha256_bytes(normalize_definition_text(engine_skill.text).encode("utf-8")),
                })
        database_tera = any((row.get("Move Name") or "").strip() == "[Tera]" for row in db_rows)
        if engine and database_tera != bool(engine.tera):
            definition_differences.append({
                "kind": "tera_flag",
                "database": database_tera,
                "engine": bool(engine.tera),
            })
        if definition_differences:
            issues.append({
                "card_id": card_id,
                "code": "engine_database_definition_mismatch",
                "severity": "error",
                "differences": definition_differences,
            })
        if not mapped:
            issues.append({
                "card_id": card_id,
                "code": "ambiguous_or_mismatched_mapping",
                "severity": "error",
                "catalog_name": cat["card_name"],
                "database_name": db_name,
                "engine_name": engine_name,
                "catalog_class": cat["card_class"],
                "database_class": db_class,
                "source_line": source_line,
            })

        rows.append({
            "card_id": card_id,
            "card_name": cat["card_name"],
            "card_class": cat["card_class"],
            "subtype": cat["subtype"],
            "decks_with_card": cat["decks_with_card"],
            "database_name": db_name,
            "database_row_count": len(db_rows),
            "database_attack_count": len(db_attack_rows),
            "database_effect_count": len(db_effect_rows),
            "engine_card_id": int(engine.cardId) if engine else None,
            "engine_name": engine_name,
            "engine_card_type": ENGINE_CARD_TYPES.get(int(engine.cardType), "UNKNOWN") if engine else None,
            "engine_attack_ids": engine_attack_ids,
            "engine_attack_names": [row.name for row in engine_attack_rows],
            "engine_skill_names": [skill.name for skill in engine_skills],
            "engine_skill_count": len(engine_skills),
            "database_tera": database_tera,
            "engine_tera": bool(engine.tera) if engine else None,
            "definition_status": "exact_after_format_normalization" if not definition_differences else "mismatch",
            "formatting_normalizations": formatting_normalizations,
            "source_path": repo_path(CARD_IMPL) if source_line else None,
            "source_line": source_line,
            "match_method": "exact_numeric_id+exact_name+class" if mapped else "unresolved",
            "mapping_status": "mapped" if mapped else "unresolved",
        })

    summary = {
        "schema_version": SCHEMA_VERSION,
        "part_a_catalog_sha256": sha256_file(CATALOG),
        "engine_archive_sha256": sha256_file(ENGINE_ZIP),
        "cards": len(rows),
        "mapped": sum(row["mapping_status"] == "mapped" for row in rows),
        "unresolved": sum(row["mapping_status"] != "mapped" for row in rows),
        "class_counts": dict(sorted(Counter(row["card_class"] for row in rows).items())),
        "issues": len(issues),
        "definition_mismatches": sum(
            row["definition_status"] == "mismatch" for row in rows
        ),
        "formatting_normalizations": sum(len(row["formatting_normalizations"]) for row in rows),
    }
    return rows, issues, summary


def crosswalk_csv(rows: list[dict]) -> bytes:
    import io

    fields = list(rows[0]) if rows else []
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for record in rows:
        row = dict(record)
        for field in ("engine_attack_ids", "engine_attack_names", "engine_skill_names", "formatting_normalizations"):
            row[field] = json.dumps(row[field], ensure_ascii=False, separators=(",", ":"))
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def build_worklist() -> tuple[list[dict], list[dict], dict, list[dict]]:
    attack_overrides, card_data, effect_features, opponent_tags, stat_bakes = encoder_modules()
    catalog_cards = json.loads(CATALOG.read_text(encoding="utf-8"))["cards"]
    catalog = {int(card["card_id"]): card for card in catalog_cards}
    crosswalk_cards = json.loads((PART_B / "card-id-crosswalk.json").read_text(encoding="utf-8"))["cards"]
    crosswalk = {int(card["card_id"]): card for card in crosswalk_cards}
    database_rows: dict[int, list[dict]] = defaultdict(list)
    with CARD_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            database_rows[int(row["Card ID"])].append(row)
    binary_cards, binary_attacks = engine_snapshot()
    binary = {int(card.cardId): card for card in binary_cards}
    attacks = {int(attack.attackId): attack for attack in binary_attacks}
    source_blocks = source_card_blocks()
    dynamic_refs = current_dynamic_references()
    registry = card_data.CardRegistry.load()

    dossiers: list[dict] = []
    effect_rows: list[dict] = []
    issues: list[dict] = []
    for card_id in sorted(catalog):
        identity = catalog[card_id]
        engine = binary[card_id]
        block = source_blocks[card_id]
        attack_segments = [segment for segment in block["segments"] if segment["kind"] == "attack"]
        skill_segments = [segment for segment in block["segments"] if segment["kind"] == "skill"]
        if len(attack_segments) != len(engine.attacks):
            issues.append({
                "code": "source_engine_attack_segment_count",
                "card_id": card_id,
                "source": len(attack_segments),
                "engine": len(engine.attacks),
            })
        if len(skill_segments) != len(engine.skills):
            issues.append({
                "code": "source_engine_skill_segment_count",
                "card_id": card_id,
                "source": len(skill_segments),
                "engine": len(engine.skills),
            })

        tag_data = opponent_tags.card_tags(card_id)
        static = registry.get(card_id)
        current_attack_by_name: dict[str, list[dict]] = defaultdict(list)
        for attack_spec, raw in zip(static.attacks, tag_data.attack_raws):
            current_attack_by_name[attack_spec.name].append(copy.deepcopy(raw))

        card_effects: list[dict] = []
        attack_index = 0
        skill_index = 0
        tera_index = 0
        for source_row_index, row in enumerate(database_rows[card_id]):
            text = normalize_definition_text(row.get("Effect Explanation"))
            name = (row.get("Move Name") or "").strip()
            cost = row.get("Cost") or "n/a"
            if name == "[Tera]":
                kind = "tera"
                ordinal = tera_index
                tera_index += 1
                engine_ref = {
                    "source_path": repo_path(CARD_IMPL),
                    "source_line_start": block["tera_lines"][ordinal] if ordinal < len(block["tera_lines"]) else None,
                    "source_line_end": block["tera_lines"][ordinal] if ordinal < len(block["tera_lines"]) else None,
                    "starter": "tera",
                    "method_calls": ["tera"],
                    "effect_tokens": [],
                }
                generic = {"status": "not_applicable", "raw": None}
                current = {"included": False, "raw": None, "reason": "Tera not represented by current tag blocks"}
            elif cost != "n/a":
                kind = "attack"
                ordinal = attack_index
                attack_index += 1
                segment = attack_segments[ordinal] if ordinal < len(attack_segments) else None
                attack_id = int(engine.attacks[ordinal]) if ordinal < len(engine.attacks) else None
                engine_attack = attacks.get(attack_id)
                engine_ref = {
                    "attack_id": attack_id,
                    "engine_name": engine_attack.name if engine_attack else None,
                    "source_path": repo_path(CARD_IMPL),
                    **(copy.deepcopy(segment) if segment else {}),
                }
                total_cost = len(re.findall(r"\{[A-Z]\}|●", cost))
                generic = {
                    "status": "parsed",
                    "raw": effect_features.attack_tags(text, total_cost=total_cost),
                }
                queue = current_attack_by_name.get(name, [])
                effective = queue.pop(0) if queue else None
                current = {
                    "included": effective is not None,
                    "raw": effective,
                    "reason": None if effective is not None else "not present in current two-attack card_data view",
                }
            elif text:
                kind = "ability" if identity["card_class"] == "pokemon" else f"{identity['card_class']}_effect"
                ordinal = skill_index
                skill_index += 1
                segment = skill_segments[ordinal] if ordinal < len(skill_segments) else None
                engine_skill = engine.skills[ordinal] if ordinal < len(engine.skills) else None
                engine_ref = {
                    "engine_name": engine_skill.name if engine_skill else None,
                    "source_path": repo_path(CARD_IMPL),
                    **(copy.deepcopy(segment) if segment else {}),
                }
                if kind == "ability":
                    generic = {"status": "parsed", "raw": effect_features.ability_tags(text)}
                    current = {
                        "included": ordinal == 0,
                        "raw": copy.deepcopy(tag_data.ability_raw) if ordinal == 0 else None,
                        "reason": None if ordinal == 0 else "current encoder includes only the first ability",
                    }
                else:
                    generic = {"status": "no_current_general_parser", "raw": None}
                    current = {
                        "included": card_id in stat_bakes.BAKES,
                        "raw": copy.deepcopy(stat_bakes.BAKES.get(card_id)),
                        "reason": "current encoder represents only reviewed stat bakes" if card_id in stat_bakes.BAKES else "not represented",
                    }
            else:
                continue

            effect_id = f"card:{card_id}:{kind}:{ordinal}"
            effect = {
                "effect_id": effect_id,
                "card_id": card_id,
                "card_name": identity["card_name"],
                "card_class": identity["card_class"],
                "source_row_index": source_row_index,
                "kind": kind,
                "ordinal": ordinal,
                "name": name,
                "text": text,
                "printed_cost": None if cost == "n/a" else cost,
                "printed_damage": None if (row.get("Damage") or "n/a") == "n/a" else row.get("Damage"),
                "engine": engine_ref,
                "generic_extraction": generic,
                "current_encoder": current,
                "audit": {
                    "verdict": None,
                    "status": "pending",
                    "human_review_ids": [],
                    "validation_refs": [],
                },
            }
            card_effects.append(effect)
            effect_rows.append(effect)

        if attack_index != len(engine.attacks) or skill_index != len(engine.skills):
            issues.append({
                "code": "database_engine_effect_count",
                "card_id": card_id,
                "database_attacks": attack_index,
                "engine_attacks": len(engine.attacks),
                "database_skills": skill_index,
                "engine_skills": len(engine.skills),
            })
        if bool(tera_index) != bool(engine.tera):
            issues.append({
                "code": "database_engine_tera_count",
                "card_id": card_id,
                "database_tera": tera_index,
                "engine_tera": bool(engine.tera),
            })

        dossiers.append({
            "card_id": card_id,
            "card_name": identity["card_name"],
            "card_class": identity["card_class"],
            "subtype": identity["subtype"],
            "frequency": {
                "games_with_card": identity["games_with_card"],
                "decks_with_card": identity["decks_with_card"],
                "total_copies": identity["total_copies"],
            },
            "crosswalk": copy.deepcopy(crosswalk[card_id]),
            "engine_card_source": {
                "path": repo_path(CARD_IMPL),
                "line_start": block["source_line_start"],
                "line_end": block["source_line_end"],
                "method_calls": block["method_calls"],
            },
            "current_encoder": {
                "override": copy.deepcopy(attack_overrides.OVERRIDES.get(card_id)),
                "stat_bake": copy.deepcopy(stat_bakes.BAKES.get(card_id)),
                "reviewed_max_damage": int(tag_data.max_damage),
                "dynamic_references": copy.deepcopy(dynamic_refs.get(card_id, [])),
            },
            "effects": card_effects,
        })

    return dossiers, effect_rows, {
        "schema_version": SCHEMA_VERSION,
        "cards": len(dossiers),
        "effects": len(effect_rows),
        "effects_by_kind": dict(sorted(Counter(row["kind"] for row in effect_rows).items())),
        "cards_by_class": dict(sorted(Counter(card["card_class"] for card in dossiers).items())),
        "cards_with_overrides": sum(card["current_encoder"]["override"] is not None for card in dossiers),
        "cards_with_stat_bakes": sum(card["current_encoder"]["stat_bake"] is not None for card in dossiers),
        "cards_with_dynamic_references": sum(bool(card["current_encoder"]["dynamic_references"]) for card in dossiers),
        "issues": len(issues),
        "source_catalog_sha256": sha256_file(CATALOG),
        "source_crosswalk_sha256": sha256_file(PART_B / "card-id-crosswalk.json"),
    }, issues


def build_batches(dossiers: list[dict]) -> dict:
    batches: list[dict] = []
    for card_class in ("pokemon", "trainer", "energy"):
        ordered = sorted(
            (card for card in dossiers if card["card_class"] == card_class),
            key=lambda card: (-card["frequency"]["decks_with_card"], card["card_id"]),
        )
        for offset in range(0, len(ordered), 20):
            group = ordered[offset:offset + 20]
            batches.append({
                "batch_id": f"{card_class}-{offset // 20 + 1:02d}",
                "card_class": card_class,
                "card_ids": [card["card_id"] for card in group],
                "cards": [
                    {
                        "card_id": card["card_id"],
                        "card_name": card["card_name"],
                        "decks_with_card": card["frequency"]["decks_with_card"],
                        "effect_count": len(card["effects"]),
                    }
                    for card in group
                ],
                "status": "pending",
            })
    return {
        "schema_version": SCHEMA_VERSION,
        "ordering": "card_class order; decks_with_card descending; card_id ascending; max 20",
        "batch_count": len(batches),
        "batches": batches,
    }


def effect_rows_csv(rows: list[dict]) -> bytes:
    import io

    fields = [
        "effect_id", "card_id", "card_name", "card_class", "kind", "ordinal", "name",
        "text", "printed_cost", "printed_damage", "engine_source_path",
        "engine_source_line_start", "engine_source_line_end", "engine_starter",
        "engine_method_calls", "engine_effect_tokens", "generic_extraction",
        "current_encoder", "audit_status",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for effect in rows:
        engine = effect["engine"]
        writer.writerow({
            "effect_id": effect["effect_id"],
            "card_id": effect["card_id"],
            "card_name": effect["card_name"],
            "card_class": effect["card_class"],
            "kind": effect["kind"],
            "ordinal": effect["ordinal"],
            "name": effect["name"],
            "text": effect["text"],
            "printed_cost": effect["printed_cost"],
            "printed_damage": effect["printed_damage"],
            "engine_source_path": engine.get("source_path"),
            "engine_source_line_start": engine.get("source_line_start"),
            "engine_source_line_end": engine.get("source_line_end"),
            "engine_starter": engine.get("starter"),
            "engine_method_calls": json.dumps(engine.get("method_calls", []), separators=(",", ":")),
            "engine_effect_tokens": json.dumps(engine.get("effect_tokens", []), separators=(",", ":")),
            "generic_extraction": json.dumps(effect["generic_extraction"], sort_keys=True, separators=(",", ":")),
            "current_encoder": json.dumps(effect["current_encoder"], sort_keys=True, separators=(",", ":")),
            "audit_status": effect["audit"]["status"],
        })
    return output.getvalue().encode("utf-8")


def command_b01() -> None:
    manifest = build_engine_manifest()
    write_bytes(PART_B / "engine-source-manifest.json", json_bytes(manifest))
    write_bytes(PART_B / "engine-path-map.md", build_path_map().encode("utf-8"))
    print(json.dumps({
        "archive_sha256": manifest["engine_identity"]["archive"]["sha256"],
        "files": manifest["extraction"]["file_count"],
        "source_cards": manifest["universe_checks"]["source_active_card_ids"],
        "source_attacks": manifest["universe_checks"]["source_attack_calls"],
        "meta_missing": manifest["universe_checks"]["meta_ids_missing_from_source"],
    }, indent=2))


def command_b02() -> None:
    rows, issues, summary = build_crosswalk()
    write_bytes(PART_B / "card-id-crosswalk.json", json_bytes({
        "schema_version": SCHEMA_VERSION,
        "cards": rows,
    }))
    write_bytes(PART_B / "card-id-crosswalk.csv", crosswalk_csv(rows))
    write_bytes(PART_B / "card-id-crosswalk-issues.json", json_bytes({
        "schema_version": SCHEMA_VERSION,
        "issues": issues,
    }))
    write_bytes(PART_B / "card-id-crosswalk-summary.json", json_bytes(summary))
    print(json.dumps(summary, indent=2, sort_keys=True))
    if issues or summary["unresolved"]:
        raise SystemExit(2)


def command_b03() -> None:
    dossiers, effects, summary, issues = build_worklist()
    batches = build_batches(dossiers)
    write_bytes(PART_B / "audit-worklist.json", json_bytes({
        "schema_version": SCHEMA_VERSION,
        "cards": dossiers,
    }))
    write_bytes(PART_B / "audit-effect-rows.csv", effect_rows_csv(effects))
    write_bytes(PART_B / "audit-batch-manifest.json", json_bytes(batches))
    write_bytes(PART_B / "audit-worklist-summary.json", json_bytes(summary))
    write_bytes(PART_B / "audit-worklist-issues.json", json_bytes({
        "schema_version": SCHEMA_VERSION,
        "issues": issues,
    }))
    print(json.dumps({
        **summary,
        "batches": batches["batch_count"],
    }, indent=2, sort_keys=True))
    if issues:
        raise SystemExit(2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("b01", "b02", "b03", "all"))
    args = parser.parse_args()
    if args.command in ("b01", "all"):
        command_b01()
    if args.command in ("b02", "all"):
        command_b02()
    if args.command in ("b03", "all"):
        command_b03()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
