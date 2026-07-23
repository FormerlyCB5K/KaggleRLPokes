# 12b01 — Engine Intake and Source Freeze

Step B01 of [`12b`](12b-meta-card-semantics-audit.md).

Status: **COMPLETE (2026-07-15)**

Result: the exact module-version `1.32.0` engine ZIP was integrity-checked and extracted
without modifying source. All 45 files match the archive byte-for-byte. Active source
contains 1,267 card IDs and 1,556 attacks; all 232 meta IDs are present. The user
approved private project use and source-trace plus installed-simulator validation.
Artifacts: `Imitation-Learning/meta-card-analysis/part-b/engine-source-manifest.json`
and `engine-path-map.md`.

## Goal

Make the engine a fixed, readable, reproducible evidence source before interpreting any
card mechanic.

## Actions

1. Resolve the user-provided local engine path without moving or rewriting it.
2. Record Git commit/status when available; otherwise hash every relevant source file
   and the containing archive, if applicable.
3. Locate card definitions, effect/opcode handlers, observation serialization, tests,
   and build/run instructions.
4. Record dataset engine/module version clues and any mismatch with the supplied source.
5. Run the smallest read-only self-test or baseline command that proves the engine can
   be inspected/executed. If it cannot run, record the precise dependency blocker.
6. Write `engine-source-manifest.json` plus a short path map under the Part-B artifact
   directory.

## Termination condition

The engine has one immutable identity, every required source area is located, and its
baseline test status is recorded. No semantic audit has started.

## Validation

- Recompute hashes/version twice; results match.
- Every recorded path exists and is readable.
- The engine working tree is unchanged by intake checks.
- Baseline command passes, or a concrete non-semantic execution limitation is documented
  and approved before B02.

Stop if the engine path/version is missing or ambiguous.
