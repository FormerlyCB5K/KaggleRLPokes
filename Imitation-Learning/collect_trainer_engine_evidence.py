"""Collect recorded module-1.32.0 Trainer-resolution evidence by frozen B06 batch."""
from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
MANIFEST = PART_B / "audit-batch-manifest.json"
OUTPUT = PART_B / "trainer-audit"
MAX_SAMPLES = 3
COLLECTOR_VERSION = 2


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def trainer_targets(batch_id: str) -> dict[int, str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    batches = [item for item in manifest["batches"] if item["batch_id"].startswith("trainer-")]
    if batch_id != "all":
        batches = [next(item for item in batches if item["batch_id"] == batch_id)]
    return {
        int(card_id): f"card:{card_id}:trainer_effect:0"
        for batch in batches
        for card_id in batch["card_ids"]
    }


def compact_current(current: dict | None) -> dict | None:
    if current is None:
        return None
    return {
        "turn": current.get("turn"),
        "players": [
            {
                "hand_count": player.get("handCount"),
                "deck_count": player.get("deckCount"),
                "trash_count": player.get("trashCount"),
                "prize_count": player.get("prizeCount"),
                "active": (player.get("active") or [None])[0],
                "bench": player.get("bench"),
            }
            for player in current.get("players", [])
        ],
    }


def collect(batch_id: str) -> dict:
    targets = trainer_targets(batch_id)
    samples: dict[str, list[dict]] = defaultdict(list)
    signatures: dict[str, set[str]] = defaultdict(set)
    checkpoint_path = OUTPUT / f"{batch_id}-recorded-engine-scan-checkpoint.json"
    archives_read = 0
    members_read = 0
    if checkpoint_path.exists():
        prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if prior.get("batch_id") == batch_id and prior.get("status") == "scan_checkpoint":
            archives_read = int(prior.get("archives_read", 0))
            members_read = int(prior.get("members_read", 0))
            for effect_id, effect_samples in prior.get("samples", {}).items():
                samples[effect_id].extend(effect_samples)
                for sample in effect_samples:
                    signatures[effect_id].add(json.dumps(sample["relevant_logs"], sort_keys=True, separators=(",", ":")))

    archives = sorted(DATA_ROOT.rglob("*.zip"))
    if checkpoint_path.exists() and prior.get("collector_version") != COLLECTOR_VERSION:
        archives_read = 0
        members_read = 0
    for archive in archives[archives_read:]:
        archives_read += 1
        archive_ref = archive.resolve().relative_to(REPO_ROOT).as_posix()
        with zipfile.ZipFile(archive) as bundle:
            for member in sorted(name for name in bundle.namelist() if name.lower().endswith(".json")):
                members_read += 1
                raw = bundle.read(member)
                active_ids = [card_id for card_id, effect_id in targets.items() if len(samples[effect_id]) < MAX_SAMPLES]
                if not active_ids:
                    continue
                markers = [f'{{"cardId": {card_id}, "playerIndex":'.encode("ascii") for card_id in active_ids]
                if not any(marker in raw for marker in markers):
                    continue
                episode = json.loads(raw)
                seen_log_count = 0
                pending: dict | None = None

                def finish_pending() -> None:
                    nonlocal pending
                    if pending is None:
                        return
                    effect_id = pending["effect_id"]
                    signature = json.dumps(pending["relevant_logs"], sort_keys=True, separators=(",", ":"))
                    if len(samples[effect_id]) < MAX_SAMPLES and signature not in signatures[effect_id]:
                        signatures[effect_id].add(signature)
                        samples[effect_id].append({
                            "archive": archive_ref,
                            "episode_member": member,
                            "step_index": pending["step_index"],
                            "agent_index": 0,
                            "play_log": pending["play_log"],
                            "relevant_logs": pending["relevant_logs"],
                            "post_resolution_current": pending["post_resolution_current"],
                        })
                    pending = None

                for step_index, step in enumerate(episode.get("steps", [])):
                    observation = (step[0].get("observation") or {}) if step else {}
                    logs = observation.get("logs") or []
                    if len(logs) < seen_log_count:
                        seen_log_count = 0
                    for log in logs[seen_log_count:]:
                        if log.get("type") in (2, 3, 10, 11, 15):
                            finish_pending()
                        if log.get("type") in (10, 11):
                            effect_id = targets.get(log.get("cardId"))
                            if effect_id and len(samples[effect_id]) < MAX_SAMPLES:
                                pending = {
                                    "effect_id": effect_id,
                                    "step_index": step_index,
                                    "play_log": log,
                                    "relevant_logs": [log],
                                    "post_resolution_current": None,
                                }
                        elif pending is not None and log.get("type") in range(0, 24):
                            pending["relevant_logs"].append(log)
                    seen_log_count = len(logs)
                    if pending is not None:
                        pending["post_resolution_current"] = compact_current(observation.get("current"))
                finish_pending()

        checkpoint = {
            "schema_version": 1,
            "collector_version": COLLECTOR_VERSION,
            "status": "scan_checkpoint",
            "batch_id": batch_id,
            "archives_read": archives_read,
            "members_read": members_read,
            "samples": {effect_id: samples.get(effect_id, []) for effect_id in sorted(targets.values())},
        }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_bytes(json_bytes(checkpoint))

    counts = {effect_id: len(samples.get(effect_id, [])) for effect_id in sorted(targets.values())}
    return {
        "schema_version": 1,
        "collector_version": COLLECTOR_VERSION,
        "status": "complete",
        "batch_id": batch_id,
        "engine_module_version": "1.32.0",
        "archives_read": archives_read,
        "members_read": members_read,
        "coverage": {
            "targets": len(targets),
            "targets_with_sample": sum(count > 0 for count in counts.values()),
            "sample_counts": counts,
        },
        "checks": {
            "full_dataset_scan_complete": archives_read == len(archives) and members_read == 15018,
            "all_targets_have_multiple_samples": all(count >= 2 for count in counts.values()),
        },
        "samples": {effect_id: samples.get(effect_id, []) for effect_id in sorted(targets.values())},
    }


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    choices = sorted(item["batch_id"] for item in manifest["batches"] if item["batch_id"].startswith("trainer-"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_id", choices=[*choices, "all"])
    args = parser.parse_args()
    report = collect(args.batch_id)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{args.batch_id}-recorded-engine-evidence.json").write_bytes(json_bytes(report))
    if args.batch_id == "all":
        for batch_id in choices:
            effect_ids = set(trainer_targets(batch_id).values())
            counts = {effect_id: report["coverage"]["sample_counts"][effect_id] for effect_id in sorted(effect_ids)}
            batch_report = {
                **{key: value for key, value in report.items() if key not in {"batch_id", "coverage", "checks", "samples"}},
                "batch_id": batch_id,
                "coverage": {
                    "targets": len(effect_ids),
                    "targets_with_sample": sum(count > 0 for count in counts.values()),
                    "sample_counts": counts,
                },
                "checks": {
                    "full_dataset_scan_complete": report["checks"]["full_dataset_scan_complete"],
                    "all_targets_have_multiple_samples": all(count >= 2 for count in counts.values()),
                },
                "samples": {effect_id: report["samples"][effect_id] for effect_id in sorted(effect_ids)},
            }
            (OUTPUT / f"{batch_id}-recorded-engine-evidence.json").write_bytes(json_bytes(batch_report))
    print(json.dumps({**report["coverage"], **report["checks"]}, indent=2, sort_keys=True))
    return 0 if report["checks"]["full_dataset_scan_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
