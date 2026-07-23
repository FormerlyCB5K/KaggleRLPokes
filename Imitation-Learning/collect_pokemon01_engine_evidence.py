"""Collect compact exact-engine behavior samples from recorded top-ladder episodes."""
from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "Imitation-Learning" / "Top-ladder-data"
PART_B = REPO_ROOT / "Imitation-Learning" / "meta-card-analysis" / "part-b"
WORKLIST = PART_B / "audit-worklist.json"
OUTPUT = PART_B / "pokemon-audit" / "pokemon-01-recorded-engine-evidence.json"
TARGET_EFFECT_IDS_BY_BATCH = {
    "pokemon-01": {
    "card:305:attack:0", "card:140:attack:0", "card:741:attack:0",
    "card:743:attack:0", "card:345:attack:0", "card:756:attack:0",
    "card:112:attack:0", "card:648:attack:0", "card:414:attack:0",
    "card:235:attack:0", "card:1031:attack:0", "card:1031:attack:1",
    },
    "pokemon-02": {
        "card:117:attack:0", "card:400:attack:0", "card:401:attack:0",
        "card:431:attack:0", "card:434:attack:0", "card:131:attack:0",
        "card:133:attack:0", "card:666:attack:0", "card:689:attack:0",
        "card:379:attack:0", "card:381:attack:0", "card:381:attack:1",
        "card:861:attack:0", "card:861:attack:1", "card:121:attack:1",
        "card:1071:attack:0",
    },
    "pokemon-03": {
        "card:387:attack:0", "card:245:attack:0", "card:245:attack:1",
        "card:92:attack:0", "card:93:attack:0", "card:65:attack:1",
        "card:247:attack:0", "card:169:attack:1", "card:190:attack:0",
        "card:848:attack:0", "card:849:attack:0", "card:849:attack:1",
        "card:164:attack:0", "card:164:attack:1", "card:817:attack:0",
        "card:791:attack:0", "card:506:attack:0", "card:184:attack:0",
    },
    "pokemon-04": {
        "card:649:attack:0", "card:432:attack:0", "card:73:attack:0",
        "card:74:attack:0", "card:676:attack:0", "card:678:attack:0",
        "card:678:attack:1", "card:174:attack:0", "card:272:attack:0",
        "card:677:attack:0", "card:58:attack:0", "card:607:attack:0",
        "card:31:attack:0", "card:31:attack:1", "card:306:attack:0",
        "card:306:attack:1", "card:183:attack:0", "card:597:attack:0",
        "card:745:attack:0",
    },
    "pokemon-05": {
        "card:63:attack:0", "card:63:attack:1", "card:96:attack:0",
        "card:108:attack:0", "card:108:attack:1", "card:141:attack:0",
        "card:293:attack:0", "card:303:attack:0", "card:463:attack:0",
        "card:463:attack:1", "card:473:attack:0", "card:474:attack:0",
        "card:674:attack:0", "card:746:attack:0", "card:747:attack:0",
        "card:747:attack:1", "card:891:attack:0", "card:906:attack:0",
        "card:906:attack:1", "card:1051:attack:0",
    },
    "pokemon-06": {
        "card:42:attack:0", "card:150:attack:0", "card:258:attack:0",
        "card:258:attack:1", "card:333:attack:0", "card:655:attack:0",
        "card:709:attack:0", "card:827:attack:0", "card:828:attack:0",
        "card:828:attack:1", "card:833:attack:0", "card:917:attack:0",
        "card:920:attack:0", "card:970:attack:0",
    },
}
TARGET_EFFECT_IDS = TARGET_EFFECT_IDS_BY_BATCH["pokemon-01"]
MAX_SAMPLES = 3


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def attack_targets(target_effect_ids: set[str] = TARGET_EFFECT_IDS) -> dict[int, str]:
    worklist = json.loads(WORKLIST.read_text(encoding="utf-8"))
    return {
        int(effect["engine"]["attack_id"]): effect["effect_id"]
        for card in worklist["cards"]
        for effect in card["effects"]
        if effect["effect_id"] in target_effect_ids
    }


def compact_current(current: dict | None, attacking_player: int) -> dict | None:
    if current is None:
        return None
    player = current["players"][attacking_player]
    pokemon = [item for item in player["active"] + player["bench"] if item]
    return {
        "turn": current["turn"],
        "attacking_player": attacking_player,
        "hand_count": player["handCount"],
        "board": [
            {
                "id": item["id"],
                "serial": item["serial"],
                "hp": item["hp"],
                "max_hp": item["maxHp"],
                "energy_card_ids": [card["id"] for card in item["energyCards"]],
                "energy_types": item["energies"],
            }
            for item in pokemon
        ],
    }


def collect(batch_id: str = "pokemon-01") -> dict:
    target_effect_ids = TARGET_EFFECT_IDS_BY_BATCH[batch_id]
    targets = attack_targets(target_effect_ids)
    samples: dict[str, list[dict]] = defaultdict(list)
    signatures: dict[str, set[str]] = defaultdict(set)
    archives_read = 0
    members_read = 0
    checkpoint_path = PART_B / "pokemon-audit" / f"{batch_id}-recorded-engine-scan-checkpoint.json"
    if checkpoint_path.exists():
        prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if prior.get("batch_id") == batch_id and prior.get("status") == "scan_checkpoint":
            archives_read = int(prior.get("archives_read", 0))
            members_read = int(prior.get("members_read", 0))
            for effect_id, effect_samples in prior.get("samples", {}).items():
                samples[effect_id].extend(effect_samples)
                for sample in effect_samples:
                    core = [
                        log for log in sample["relevant_logs"] if log.get("type") not in (6, 7)
                    ]
                    signatures[effect_id].add(json.dumps(core, sort_keys=True, separators=(",", ":")))

    archives = sorted(DATA_ROOT.rglob("*.zip"))
    for archive in archives[archives_read:]:
        archives_read += 1
        archive_ref = archive.resolve().relative_to(REPO_ROOT).as_posix()
        with zipfile.ZipFile(archive) as bundle:
            for member in sorted(name for name in bundle.namelist() if name.lower().endswith(".json")):
                members_read += 1
                raw_episode = bundle.read(member)
                active_attack_ids = [
                    attack_id for attack_id, effect_id in targets.items()
                    if len(samples[effect_id]) < MAX_SAMPLES
                ]
                if not active_attack_ids:
                    break
                executed_attack_markers = [
                    f'{{"attackId": {attack_id}, "cardId":'.encode("ascii")
                    for attack_id in active_attack_ids
                ]
                if not any(marker in raw_episode for marker in executed_attack_markers):
                    continue
                episode = json.loads(raw_episode)
                seen_log_count = 0
                pending: dict | None = None

                def finish_pending() -> None:
                    nonlocal pending
                    if pending is None:
                        return
                    effect_id = pending["effect_id"]
                    relevant = pending["relevant_logs"]
                    core_for_signature = [
                        log for log in relevant if log.get("type") not in (6, 7)
                    ]
                    signature = json.dumps(core_for_signature, sort_keys=True, separators=(",", ":"))
                    if (
                        len(samples[effect_id]) < MAX_SAMPLES
                        and signature not in signatures[effect_id]
                    ):
                        signatures[effect_id].add(signature)
                        samples[effect_id].append({
                            "archive": archive_ref,
                            "episode_member": member,
                            "step_index": pending["step_index"],
                            "agent_index": 0,
                            "attack_log": pending["attack_log"],
                            "relevant_logs": relevant,
                            "post_resolution_current": pending["post_resolution_current"],
                        })
                    pending = None

                for step_index, step in enumerate(episode["steps"]):
                    observation = (step[0].get("observation") or {}) if step else {}
                    logs = observation.get("logs") or []
                    if len(logs) < seen_log_count:
                        seen_log_count = 0
                    new_logs = logs[seen_log_count:]
                    seen_log_count = len(logs)
                    for log in new_logs:
                        if log.get("type") == 15:
                            finish_pending()
                            effect_id = targets.get(log.get("attackId"))
                            if effect_id and len(samples[effect_id]) < MAX_SAMPLES:
                                pending = {
                                    "effect_id": effect_id,
                                    "step_index": step_index,
                                    "attack_log": log,
                                    "relevant_logs": [log],
                                    "post_resolution_current": None,
                                }
                        elif pending is not None and log.get("type") in (6, 7, 8, 16, 17, 18, 19, 20, 21, 22):
                            pending["relevant_logs"].append(log)
                    if pending is not None:
                        pending["post_resolution_current"] = compact_current(
                            observation.get("current"), int(pending["attack_log"]["playerIndex"])
                        )
                finish_pending()
                if all(len(samples[effect_id]) >= MAX_SAMPLES for effect_id in target_effect_ids):
                    break
        checkpoint = {
            "schema_version": 1,
            "batch_id": batch_id,
            "status": "scan_checkpoint",
            "archives_read": archives_read,
            "members_read": members_read,
            "sample_counts": {
                effect_id: len(samples.get(effect_id, []))
                for effect_id in sorted(target_effect_ids)
            },
            "samples": {
                effect_id: samples.get(effect_id, [])
                for effect_id in sorted(target_effect_ids)
            },
        }
        checkpoint_path.write_bytes(json_bytes(checkpoint))
        if all(len(samples[effect_id]) >= MAX_SAMPLES for effect_id in target_effect_ids):
            break

    formula_checks = []
    for sample in samples["card:743:attack:0"]:
        counter_changes = [
            log for log in sample["relevant_logs"]
            if log.get("type") == 16 and log.get("putDamageCounter") is True
        ]
        post_hand_count = sample["post_resolution_current"]["hand_count"]
        attacking_player = sample["attack_log"]["playerIndex"]
        moved_to_hand = sum(
            log.get("playerIndex") == attacking_player and log.get("toArea") == 2
            for log in sample["relevant_logs"]
        )
        moved_from_hand = sum(
            log.get("playerIndex") == attacking_player and log.get("fromArea") == 2
            for log in sample["relevant_logs"]
        )
        hand_count = post_hand_count - moved_to_hand + moved_from_hand
        actual = max((-int(log["value"]) for log in counter_changes), default=None)
        formula_checks.append({
            "effect_id": "card:743:attack:0",
            "hand_count": hand_count,
            "post_resolution_hand_count": post_hand_count,
            "net_cards_moved_to_hand_after_attack": moved_to_hand - moved_from_hand,
            "expected_hp_loss": 20 * hand_count,
            "observed_hp_loss": actual,
            "passed": actual == 20 * hand_count,
            "evidence": {
                "archive": sample["archive"],
                "episode_member": sample["episode_member"],
                "step_index": sample["step_index"],
            },
        })

    common_checks = {
        "full_dataset_scan_complete": archives_read == len(archives),
        "all_targets_have_multiple_samples": all(
            len(samples.get(effect_id, [])) >= MAX_SAMPLES
            for effect_id in target_effect_ids
        ),
    }
    formula_specific_checks = ({
        "alakazam_has_multiple_samples": len(formula_checks) >= 3,
        "alakazam_live_formula_passes": bool(formula_checks) and all(item["passed"] for item in formula_checks),
    } if batch_id == "pokemon-01" else {})
    return {
        "schema_version": 1,
        "engine_identity": "recorded module_version 1.32.0 top-ladder episodes",
        "archives_read": archives_read,
        "members_read": members_read,
        "batch_id": batch_id,
        "target_effect_ids": sorted(target_effect_ids),
        "samples": {effect_id: samples.get(effect_id, []) for effect_id in sorted(target_effect_ids)},
        "coverage": {
            "targets": len(target_effect_ids),
            "targets_with_sample": sum(bool(samples.get(effect_id)) for effect_id in target_effect_ids),
            "sample_counts": {effect_id: len(samples.get(effect_id, [])) for effect_id in sorted(target_effect_ids)},
        },
        "formula_checks": formula_checks,
        "checks": {**common_checks, **formula_specific_checks},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch_id", nargs="?", default="pokemon-01", choices=sorted(TARGET_EFFECT_IDS_BY_BATCH))
    args = parser.parse_args()
    report = collect(args.batch_id)
    output = PART_B / "pokemon-audit" / f"{args.batch_id}-recorded-engine-evidence.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(json_bytes(report))
    print(json.dumps({**report["coverage"], **report["checks"]}, indent=2, sort_keys=True))
    return 0 if report["checks"]["full_dataset_scan_complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
