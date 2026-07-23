"""Collect recorded attachment evidence for all 18 Spec-12b07 Energy cards."""
from __future__ import annotations

import json
import zipfile
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
MANIFEST = PART_B / "audit-batch-manifest.json"
OUTPUT = PART_B / "energy-audit"
MAX_SAMPLES = 3


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def targets() -> dict[int, str]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    batch = next(item for item in manifest["batches"] if item["batch_id"] == "energy-01")
    return {int(card_id): f"card:{card_id}:energy_attachment" for card_id in batch["card_ids"]}


def collect() -> dict:
    target_map = targets()
    samples: dict[str, list[dict]] = defaultdict(list)
    signatures: dict[str, set[str]] = defaultdict(set)
    checkpoint_path = OUTPUT / "energy-01-recorded-attachment-scan-checkpoint.json"
    archives_read = 0
    members_read = 0
    if checkpoint_path.exists():
        prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if prior.get("status") == "scan_checkpoint":
            archives_read = int(prior.get("archives_read", 0))
            members_read = int(prior.get("members_read", 0))
            for evidence_id, prior_samples in prior.get("samples", {}).items():
                samples[evidence_id].extend(prior_samples)
                for sample in prior_samples:
                    signatures[evidence_id].add(json.dumps(sample["relevant_logs"], sort_keys=True, separators=(",", ":")))

    archives = sorted(DATA_ROOT.rglob("*.zip"))
    for archive in archives[archives_read:]:
        archives_read += 1
        archive_ref = archive.resolve().relative_to(REPO_ROOT).as_posix()
        with zipfile.ZipFile(archive) as bundle:
            for member in sorted(name for name in bundle.namelist() if name.lower().endswith(".json")):
                members_read += 1
                active_ids = [card_id for card_id, evidence_id in target_map.items() if len(samples[evidence_id]) < MAX_SAMPLES]
                if not active_ids:
                    continue
                raw = bundle.read(member)
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
                    evidence_id = pending["evidence_id"]
                    signature = json.dumps(pending["relevant_logs"], sort_keys=True, separators=(",", ":"))
                    if len(samples[evidence_id]) < MAX_SAMPLES and signature not in signatures[evidence_id]:
                        signatures[evidence_id].add(signature)
                        samples[evidence_id].append({
                            "archive": archive_ref,
                            "episode_member": member,
                            "step_index": pending["step_index"],
                            "attach_log": pending["attach_log"],
                            "relevant_logs": pending["relevant_logs"],
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
                        if log.get("type") == 11:
                            evidence_id = target_map.get(log.get("cardId"))
                            if evidence_id and len(samples[evidence_id]) < MAX_SAMPLES:
                                pending = {"evidence_id": evidence_id, "step_index": step_index, "attach_log": log, "relevant_logs": [log]}
                        elif pending is not None and log.get("type") in range(0, 24):
                            pending["relevant_logs"].append(log)
                    seen_log_count = len(logs)
                finish_pending()

        checkpoint = {
            "schema_version": 1, "status": "scan_checkpoint", "archives_read": archives_read, "members_read": members_read,
            "samples": {evidence_id: samples.get(evidence_id, []) for evidence_id in sorted(target_map.values())},
        }
        OUTPUT.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_bytes(json_bytes(checkpoint))

    counts = {evidence_id: len(samples.get(evidence_id, [])) for evidence_id in sorted(target_map.values())}
    return {
        "schema_version": 1, "status": "complete", "batch_id": "energy-01", "engine_module_version": "1.32.0",
        "archives_read": archives_read, "members_read": members_read,
        "coverage": {"targets": len(target_map), "targets_with_sample": sum(count > 0 for count in counts.values()), "sample_counts": counts},
        "checks": {"full_dataset_scan_complete": archives_read == len(archives) and members_read == 15018, "all_targets_have_multiple_samples": all(count >= 2 for count in counts.values())},
        "samples": {evidence_id: samples.get(evidence_id, []) for evidence_id in sorted(target_map.values())},
    }


def main() -> int:
    report = collect()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "energy-01-recorded-attachment-evidence.json").write_bytes(json_bytes(report))
    print(json.dumps({**report["coverage"], **report["checks"]}, indent=2, sort_keys=True))
    return 0 if report["checks"]["full_dataset_scan_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
