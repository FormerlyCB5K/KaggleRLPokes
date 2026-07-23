"""Inventory exact card IDs from top-ladder Kaggle episode archives.

The episode JSON embeds a very large visualization replay. Fully materializing that tree
is needlessly slow when the two submitted decks are available in the first visualization
action and repeated as the agents' root setup actions. This module extracts the bounded
deck value, validates it, and independently confirms the exact root action arrays.

Run from the repository root, for example:

    python Imitation-Learning/analyze_top_ladder_cards.py \
        --archive Imitation-Learning/Top-ladder-data/7-12/*.zip \
        --output-dir Imitation-Learning/meta-card-analysis/7-12-pilot

    python Imitation-Learning/analyze_top_ladder_cards.py \
        --all \
        --output-dir Imitation-Learning/meta-card-analysis/all-datasets
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import uuid
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = 1
SCRIPT_VERSION = "1.0.0"
DECK_SIZE = 60

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"
DEFAULT_CARD_CSV = REPO_ROOT / "Decks" / "Deck-Builder" / "EN_Card_Data.csv"

CARD_TYPE_FIELD = "Stage (Pokémon)/Type (Energy and Trainer)"
POKEMON_TYPES = frozenset({"Basic Pokémon", "Stage 1 Pokémon", "Stage 2 Pokémon"})
TRAINER_TYPES = frozenset({"Item", "Supporter", "Pokémon Tool", "Stadium"})
ENERGY_TYPES = frozenset({"Basic Energy", "Special Energy"})

_EPISODE_ID_RE = re.compile(rb'"EpisodeId"\s*:\s*(\d+)')
_UUID_RE = re.compile(rb'"id"\s*:\s*"([^"\\]+)"')
_DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


class ExtractionError(ValueError):
    """A stable episode rejection with a machine-readable issue code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class EpisodeRecord:
    episode_key: str
    episode_id: int | None
    fallback_id: str | None
    dataset_date: str
    archive_path: str
    member_name: str
    decks: tuple[tuple[int, ...], tuple[int, ...]]

    @property
    def content_signature(self) -> str:
        payload = json.dumps(self.decks, separators=(",", ":")).encode("ascii")
        return hashlib.sha256(payload).hexdigest()


def _repo_path(path: Path) -> str:
    """Stable repo-relative display path when possible."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def discover_archives(data_root: Path = DEFAULT_DATA_ROOT) -> list[Path]:
    return sorted(
        (path.resolve() for path in data_root.rglob("*.zip") if path.is_file()),
        key=lambda path: path.as_posix(),
    )


def dataset_date(path: Path) -> str:
    match = _DATE_RE.search(path.name)
    if match:
        return match.group(1)
    parent = path.parent.name
    short = re.fullmatch(r"(\d{1,2})-(\d{1,2})", parent)
    if short:
        return f"unknown-{int(short.group(1)):02d}-{int(short.group(2)):02d}"
    return parent or "unknown"


def _bounded_json_value(raw: bytes, start: int) -> tuple[object, int]:
    """Decode one JSON array/object without decoding the remainder of a huge episode."""
    while start < len(raw) and raw[start] in b" \t\r\n":
        start += 1
    if start >= len(raw) or raw[start] not in (ord("["), ord("{")):
        raise ExtractionError("invalid_json_value", "expected a JSON array or object")

    opening = raw[start]
    closing = ord("]") if opening == ord("[") else ord("}")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(raw)):
        byte = raw[index]
        if in_string:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                in_string = False
            continue
        if byte == ord('"'):
            in_string = True
        elif byte == opening:
            depth += 1
        elif byte == closing:
            depth -= 1
            if depth == 0:
                value_raw = raw[start:index + 1]
                try:
                    return json.loads(value_raw), index + 1
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ExtractionError("invalid_json", str(exc)) from exc
        elif byte in (ord("["), ord("{")):
            depth += 1
        elif byte in (ord("]"), ord("}")):
            depth -= 1
            if depth < 0:
                break
    raise ExtractionError("invalid_json", "unterminated JSON value")


def _validate_deck(deck: object, agent_index: int) -> tuple[int, ...]:
    prefix = f"agent {agent_index} deck"
    if not isinstance(deck, list):
        raise ExtractionError("deck_not_list", f"{prefix} is not a list")
    if len(deck) != DECK_SIZE:
        raise ExtractionError(
            "invalid_deck_length", f"{prefix} has {len(deck)} cards, expected {DECK_SIZE}"
        )
    if any(isinstance(card_id, bool) for card_id in deck):
        raise ExtractionError("boolean_card_id", f"{prefix} contains a Boolean card ID")
    if any(not isinstance(card_id, int) for card_id in deck):
        raise ExtractionError("non_integer_card_id", f"{prefix} contains a non-integer ID")
    if any(card_id <= 0 for card_id in deck):
        raise ExtractionError("non_positive_card_id", f"{prefix} contains a non-positive ID")
    return tuple(deck)


def extract_episode(
    raw: bytes,
    *,
    archive_path: str,
    member_name: str,
    date: str,
) -> EpisodeRecord:
    """Extract and independently verify both submitted decks from one episode."""
    stripped = raw.strip()
    if not stripped.startswith(b"{") or not stripped.endswith(b"}"):
        raise ExtractionError("invalid_json", "episode is not a complete JSON object")

    visualize_at = raw.find(b'"visualize"')
    if visualize_at < 0:
        raise ExtractionError("missing_visualize", "visualization replay not found")
    action_at = raw.find(b'"action"', visualize_at)
    if action_at < 0:
        raise ExtractionError("missing_deck_action", "visualization action not found")
    colon_at = raw.find(b":", action_at)
    if colon_at < 0:
        raise ExtractionError("invalid_json", "visualization action has no value")

    action, _ = _bounded_json_value(raw, colon_at + 1)
    if not isinstance(action, list) or len(action) != 2:
        raise ExtractionError(
            "invalid_deck_action", "first visualization action must contain two decks"
        )
    decks = (_validate_deck(action[0], 0), _validate_deck(action[1], 1))

    # Independent source check: root setup actions serialize as "action":<60-ID-list>.
    # The visualization action is nested as "action":[<deck0>,<deck1>] and therefore
    # cannot satisfy this exact pattern.
    multiplicities = Counter(decks)
    for deck, expected in multiplicities.items():
        # Kaggle's episode serializer may insert whitespace after commas. Match the
        # exact 60 integer sequence while allowing JSON whitespace between tokens.
        encoded_items = rb"\s*,\s*".join(str(card_id).encode("ascii") for card_id in deck)
        pattern = re.compile(
            rb'"action"\s*:\s*\[\s*' + encoded_items + rb"\s*\]"
        )
        found = len(pattern.findall(raw))
        if found < expected:
            raise ExtractionError(
                "deck_source_mismatch",
                f"submitted root action found {found} time(s), expected {expected}",
            )
        if found > expected:
            raise ExtractionError(
                "duplicate_deck_submission",
                f"submitted root action found {found} time(s), expected {expected}",
            )

    id_match = _EPISODE_ID_RE.search(raw[: min(len(raw), 250_000)])
    episode_id = int(id_match.group(1)) if id_match else None
    uuid_match = _UUID_RE.search(raw[: min(len(raw), 250_000)])
    fallback_id = uuid_match.group(1).decode("utf-8") if uuid_match else None
    signature_seed = json.dumps(decks, separators=(",", ":")).encode("ascii")
    if episode_id is not None:
        episode_key = f"episode:{episode_id}"
    else:
        base = fallback_id or member_name
        fallback_hash = hashlib.sha256(base.encode("utf-8") + signature_seed).hexdigest()
        episode_key = f"fallback:{fallback_hash}"

    return EpisodeRecord(
        episode_key=episode_key,
        episode_id=episode_id,
        fallback_id=fallback_id,
        dataset_date=date,
        archive_path=archive_path,
        member_name=member_name,
        decks=decks,
    )


def load_card_metadata(csv_path: Path) -> dict[int, dict]:
    metadata: dict[int, dict] = {}
    with csv_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            card_id = int(row["Card ID"])
            if card_id in metadata:
                continue
            subtype = row[CARD_TYPE_FIELD]
            if subtype in POKEMON_TYPES:
                card_class = "pokemon"
            elif subtype in TRAINER_TYPES:
                card_class = "trainer"
            elif subtype in ENERGY_TYPES:
                card_class = "energy"
            else:
                card_class = "unresolved"
            metadata[card_id] = {
                "card_id": card_id,
                "card_name": row["Card Name"],
                "card_class": card_class,
                "subtype": subtype,
            }
    return metadata


def scan_archives(archives: Iterable[Path]) -> tuple[list[EpisodeRecord], list[dict], list[dict]]:
    """Return unique episodes, issue ledger, and immutable archive manifests."""
    unique: dict[str, EpisodeRecord] = {}
    signatures: dict[str, str] = {}
    issues: list[dict] = []
    archive_manifests: list[dict] = []

    for archive in sorted((Path(p).resolve() for p in archives), key=lambda p: p.as_posix()):
        archive_label = _repo_path(archive)
        date = dataset_date(archive)
        archive_info = {
            "path": archive_label,
            "dataset_date": date,
            "size_bytes": archive.stat().st_size,
            "sha256": sha256_file(archive),
            "zip_members": 0,
            "json_members": 0,
            "accepted_unique_episodes": 0,
            "duplicate_episodes": 0,
            "rejected_json_members": 0,
            "non_json_members": 0,
        }
        with zipfile.ZipFile(archive) as bundle:
            members = sorted(bundle.infolist(), key=lambda item: item.filename)
            archive_info["zip_members"] = len(members)
            for member in members:
                if member.is_dir() or not member.filename.lower().endswith(".json"):
                    archive_info["non_json_members"] += 1
                    continue
                archive_info["json_members"] += 1
                try:
                    raw = bundle.read(member)
                    record = extract_episode(
                        raw,
                        archive_path=archive_label,
                        member_name=member.filename,
                        date=date,
                    )
                except (ExtractionError, KeyError, RuntimeError, zipfile.BadZipFile) as exc:
                    code = exc.code if isinstance(exc, ExtractionError) else "archive_read_error"
                    issues.append({
                        "severity": "error",
                        "code": code,
                        "archive_path": archive_label,
                        "dataset_date": date,
                        "member_name": member.filename,
                        "message": str(exc),
                    })
                    archive_info["rejected_json_members"] += 1
                    continue

                signature = record.content_signature
                prior = unique.get(record.episode_key)
                if prior is not None:
                    if signatures[record.episode_key] != signature:
                        issues.append({
                            "severity": "error",
                            "code": "episode_id_collision",
                            "archive_path": archive_label,
                            "dataset_date": date,
                            "member_name": member.filename,
                            "episode_key": record.episode_key,
                            "message": "same episode identity has different submitted decks",
                        })
                        archive_info["rejected_json_members"] += 1
                    else:
                        issues.append({
                            "severity": "info",
                            "code": "duplicate_episode",
                            "archive_path": archive_label,
                            "dataset_date": date,
                            "member_name": member.filename,
                            "episode_key": record.episode_key,
                            "canonical_archive_path": prior.archive_path,
                            "canonical_member_name": prior.member_name,
                        })
                        archive_info["duplicate_episodes"] += 1
                    continue

                unique[record.episode_key] = record
                signatures[record.episode_key] = signature
                archive_info["accepted_unique_episodes"] += 1
        archive_manifests.append(archive_info)

    return list(unique.values()), issues, archive_manifests


def aggregate_cards(
    episodes: Iterable[EpisodeRecord], metadata: dict[int, dict]
) -> tuple[list[dict], list[dict], dict]:
    accum: dict[int, dict] = {}
    issues: list[dict] = []
    episode_list = sorted(episodes, key=lambda ep: (ep.dataset_date, ep.episode_key))

    for episode in episode_list:
        game_counts: Counter[int] = Counter()
        for deck_index, deck in enumerate(episode.decks):
            counts = Counter(deck)
            game_counts.update(counts)
            for card_id, copies in counts.items():
                entry = accum.setdefault(card_id, {
                    "games": set(),
                    "decks": 0,
                    "copies": 0,
                    "min_copies": copies,
                    "max_copies": copies,
                    "dates": set(),
                    "archives": set(),
                    "per_date": defaultdict(lambda: {"games": set(), "decks": 0, "copies": 0}),
                })
                entry["decks"] += 1
                entry["copies"] += copies
                entry["min_copies"] = min(entry["min_copies"], copies)
                entry["max_copies"] = max(entry["max_copies"], copies)
                entry["dates"].add(episode.dataset_date)
                entry["archives"].add(episode.archive_path)
                date_entry = entry["per_date"][episode.dataset_date]
                date_entry["decks"] += 1
                date_entry["copies"] += copies
                date_entry["games"].add(episode.episode_key)
        for card_id in game_counts:
            accum[card_id]["games"].add(episode.episode_key)

    cards: list[dict] = []
    for card_id in sorted(accum):
        values = accum[card_id]
        meta = metadata.get(card_id)
        if meta is None or meta["card_class"] == "unresolved":
            issues.append({
                "severity": "error",
                "code": "unresolved_card_id" if meta is None else "unresolved_card_subtype",
                "card_id": card_id,
                "card_name": meta["card_name"] if meta else None,
                "subtype": meta["subtype"] if meta else None,
                "message": "observed card cannot be classified from the frozen database",
            })
        dates = sorted(values["dates"])
        cards.append({
            "card_id": card_id,
            "card_name": meta["card_name"] if meta else None,
            "card_class": meta["card_class"] if meta else "unresolved",
            "subtype": meta["subtype"] if meta else None,
            "metadata_resolved": bool(meta and meta["card_class"] != "unresolved"),
            "dataset_dates": dates,
            "source_archives": sorted(values["archives"]),
            "games_with_card": len(values["games"]),
            "decks_with_card": values["decks"],
            "total_copies": values["copies"],
            "min_copies_in_containing_deck": values["min_copies"],
            "max_copies_in_containing_deck": values["max_copies"],
            "first_dataset_date": dates[0],
            "last_dataset_date": dates[-1],
            "per_date": {
                date: {
                    "games_with_card": len(values["per_date"][date]["games"]),
                    "decks_with_card": values["per_date"][date]["decks"],
                    "total_copies": values["per_date"][date]["copies"],
                }
                for date in sorted(values["per_date"])
            },
        })

    summary = {
        "unique_episodes": len(episode_list),
        "deck_instances": 2 * len(episode_list),
        "submitted_card_copies": 2 * DECK_SIZE * len(episode_list),
        "unique_card_ids": len(cards),
        "cards_by_class": dict(sorted(Counter(c["card_class"] for c in cards).items())),
        "cards_by_subtype": dict(sorted(Counter(c["subtype"] for c in cards).items())),
    }
    return cards, issues, summary


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _csv_bytes(cards: list[dict]) -> bytes:
    import io

    fields = [
        "card_id", "card_name", "card_class", "subtype", "metadata_resolved",
        "dataset_dates", "source_archives", "games_with_card", "decks_with_card",
        "total_copies", "min_copies_in_containing_deck",
        "max_copies_in_containing_deck", "first_dataset_date", "last_dataset_date",
        "per_date",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for card in cards:
        row = dict(card)
        for key in ("dataset_dates", "source_archives", "per_date"):
            row[key] = json.dumps(row[key], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def _summary_markdown(summary: dict, archive_manifests: list[dict], issues: list[dict]) -> bytes:
    errors = sum(issue["severity"] == "error" for issue in issues)
    info = len(issues) - errors
    lines = [
        "# Top-Ladder Card Inventory", "",
        f"- Unique episodes: {summary['unique_episodes']:,}",
        f"- Deck instances: {summary['deck_instances']:,}",
        f"- Submitted card copies: {summary['submitted_card_copies']:,}",
        f"- Unique exact card IDs: {summary['unique_card_ids']:,}",
        f"- Error issues: {errors:,}",
        f"- Informational issues: {info:,}", "",
        "## Cards by class", "",
    ]
    for card_class, count in summary["cards_by_class"].items():
        lines.append(f"- {card_class}: {count:,}")
    lines += ["", "## Archives", ""]
    for archive in archive_manifests:
        lines.append(
            f"- `{archive['path']}`: {archive['json_members']:,} JSON members, "
            f"{archive['accepted_unique_episodes']:,} accepted unique, "
            f"{archive['duplicate_episodes']:,} duplicates, "
            f"{archive['rejected_json_members']:,} rejected"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_artifacts(
    *,
    cards: list[dict],
    issues: list[dict],
    summary: dict,
    archive_manifests: list[dict],
    card_csv: Path,
    argv: list[str],
) -> dict[str, bytes]:
    class_ids = {
        card_class: [c["card_id"] for c in cards if c["card_class"] == card_class]
        for card_class in ("pokemon", "trainer", "energy")
    }
    artifacts: dict[str, bytes] = {
        "top_ladder_card_catalog.json": _json_bytes({
            "schema_version": SCHEMA_VERSION,
            "cards": cards,
        }),
        "top_ladder_card_catalog.csv": _csv_bytes(cards),
        "pokemon_ids.json": _json_bytes(class_ids["pokemon"]),
        "trainer_ids.json": _json_bytes(class_ids["trainer"]),
        "energy_ids.json": _json_bytes(class_ids["energy"]),
        "issues.json": _json_bytes({
            "schema_version": SCHEMA_VERSION,
            "issue_counts": dict(sorted(Counter(i["code"] for i in issues).items())),
            "issues": sorted(
                issues,
                key=lambda i: (
                    i.get("severity", ""), i.get("code", ""),
                    i.get("archive_path", ""), i.get("member_name", ""),
                    i.get("card_id", -1),
                ),
            ),
        }),
        "summary.md": _summary_markdown(summary, archive_manifests, issues),
    }
    output_hashes = {
        name: hashlib.sha256(content).hexdigest() for name, content in sorted(artifacts.items())
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "script_version": SCRIPT_VERSION,
        "command": argv,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "card_database": {
            "path": _repo_path(card_csv),
            "size_bytes": card_csv.stat().st_size,
            "sha256": sha256_file(card_csv),
        },
        "archives": archive_manifests,
        "summary": summary,
        "issue_counts": dict(sorted(Counter(i["code"] for i in issues).items())),
        "output_sha256_excluding_manifest": output_hashes,
    }
    artifacts["run_manifest.json"] = _json_bytes(manifest)
    return artifacts


def write_artifacts(output_dir: Path, artifacts: dict[str, bytes]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    # Create temporary files in the destination directory so they inherit the same
    # Windows ACL as the final artifacts. Moving files out of tempfile's private
    # directory can preserve its owner-only ACL and make the results unreadable to the
    # interactive workspace owner even though their contents are valid.
    temporary: dict[str, Path] = {}
    try:
        for name, content in sorted(artifacts.items()):
            temp_path = output_dir / f".{name}.{uuid.uuid4().hex}.tmp"
            with temp_path.open("xb") as handle:
                handle.write(content)
            temporary[name] = temp_path
        for name in sorted(artifacts):
            os.replace(temporary[name], output_dir / name)
            del temporary[name]
    finally:
        for temp_path in temporary.values():
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def _resolve_archives(args: argparse.Namespace) -> list[Path]:
    if args.all:
        archives = discover_archives(args.data_root)
    else:
        archives = sorted({Path(path).resolve() for path in args.archive})
    if not archives:
        raise SystemExit("no archives selected/discovered")
    missing = [str(path) for path in archives if not path.is_file()]
    if missing:
        raise SystemExit(f"archive(s) not found: {missing}")
    return archives


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--archive", action="append", default=[], type=Path)
    group.add_argument("--all", action="store_true", help="scan every ZIP under --data-root")
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--card-csv", type=Path, default=DEFAULT_CARD_CSV)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    archives = _resolve_archives(args)
    card_csv = args.card_csv.resolve()
    metadata = load_card_metadata(card_csv)
    episodes, scan_issues, archive_manifests = scan_archives(archives)
    cards, card_issues, summary = aggregate_cards(episodes, metadata)
    issues = scan_issues + card_issues

    stable_argv = [
        "python", "Imitation-Learning/analyze_top_ladder_cards.py",
        *( ["--all"] if args.all else [item for p in archives for item in ("--archive", _repo_path(p))] ),
        "--card-csv", _repo_path(card_csv),
        "--output-dir", _repo_path(args.output_dir),
    ]
    artifacts = build_artifacts(
        cards=cards,
        issues=issues,
        summary=summary,
        archive_manifests=archive_manifests,
        card_csv=card_csv,
        argv=stable_argv,
    )
    write_artifacts(args.output_dir.resolve(), artifacts)

    error_count = sum(issue["severity"] == "error" for issue in issues)
    print(
        f"wrote {len(cards)} cards from {summary['unique_episodes']} episodes "
        f"to {_repo_path(args.output_dir)} ({error_count} error issues)"
    )
    return 2 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
