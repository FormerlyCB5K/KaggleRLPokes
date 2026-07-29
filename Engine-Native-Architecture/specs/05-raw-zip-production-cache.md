# 05 - Raw-ZIP Production Cache

Status: implemented and locally validated; July 12-27 cluster build pending,
2026-07-28.

## Objective

Build the full July 12-27 engine-native imitation cache without materializing the
roughly 17 GiB-per-day loose sanitized JSON corpus.

This is a storage-path extension of spec 03. It does not change episode acceptance,
legal-action masking, replay extraction, features, labels, sharding, or the global
game-level split.

## Source contract

The raw root contains exactly one ZIP per requested day:

```text
Imitation-Learning/Top-ladder-data/
  7-12/*.zip
  ...
  7-27/*.zip
```

Every archive must contain at least one JSON member. Episode basenames must be unique
within a day. Non-JSON members such as `manifest.csv` are ignored.

The archive byte size and SHA-256, and each accepted member's uncompressed size, ZIP
member name, CRC, and enclosing archive hash are pinned into the source metadata and
cache identity. Raw-ZIP and loose-sanitized caches cannot silently reuse one another.

## Shared sanitization semantics

`top_ladder_sanitization.py` is the single implementation of:

- JSON parsing and required top-level-key validation;
- `statuses == ["DONE", "DONE"]`;
- `malformed_json` and `non_done_status` exclusions; and
- `select.usable = len(option) != 1` masking.

The existing loose-JSON sanitizer and the raw-ZIP cache path both import this module.

## Two-pass build

The raw mode intentionally reads accepted episodes twice:

1. **Inventory/sanitization pass**
   - hash and inspect each archive;
   - parse and validate every JSON member;
   - calculate masking counters and exclusions;
   - establish the complete accepted-game inventory; and
   - construct spec 03's exact seeded global 90/10 game split.
2. **Tensor pass**
   - reread each accepted member directly from its ZIP;
   - apply the same legal-action mask in memory;
   - extract engine-native decisions and targets; and
   - write immutable train/validation tensor shards.

Worker processes retain one open ZIP handle per encountered archive. Episode payloads
remain bounded; no complete day and no loose sanitized episode is retained on disk.

The cache contains one hash-verified report per day under
`sanitization-reports/`. Each report records the archive hash, accepted and excluded
episodes, masking totals, `storage_mode: direct_to_tensor`, and
`loose_json_files_written: 0`.

## Rebuild and existing data

Existing loose sanitized days do not need to be regenerated. Their raw ZIPs can be
read through the new path alongside newly downloaded days.

The full tensor cache must be a new build in a new output directory. Adding days
changes the source inventory, global split, episode indices, shard contents, and cache
identity; the completed six-day cache remains an independent verified artifact.
The cache directory may live directly under the raw root beside the requested day
directories, as in the production command below. It must not be the raw root itself,
contain the raw root, or be placed inside any requested day directory.

## Commands

Local or interactive:

```bash
python Engine-Native-Architecture/scripts/build_il_dataset.py \
  --source raw-zip \
  --raw-root Imitation-Learning/Top-ladder-data \
  --output-root Imitation-Learning/Top-ladder-data/engine-native-cache-full-2026-07-12-to-2026-07-27 \
  --days 7-12,7-13,7-14,7-15,7-16,7-17,7-18,7-19,7-20,7-21,7-22,7-23,7-24,7-25,7-26,7-27 \
  --workers 16
```

Cluster:

```bash
sbatch Engine-Native-Architecture/cluster/FULL_build_il_dataset.sbatch
```

The cluster script performs a one-ZIP-per-day preflight and requires 180 GiB free by
default. `REQUIRED_GIB` may override the preflight only after measured cache sizing.

## Validation

The focused fixture tests build the same accepted corpus through both storage paths.
It verifies identical split assignments, totals, origins, and every cached tensor;
checks malformed and non-DONE exclusions; confirms no loose episode JSON is written;
exercises two-process raw inspection/building; and verifies report hash enforcement.
They also verify that a sibling cache beneath the raw root is accepted while a cache
inside a requested day directory is rejected.

The full July 12-27 cluster build, its exact archive inventory, throughput, output size,
and row totals remain pending and must be recorded only after the job runs.
