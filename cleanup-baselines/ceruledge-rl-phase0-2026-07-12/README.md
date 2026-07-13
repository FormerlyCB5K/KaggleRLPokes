# Ceruledge-RL Cleanup Baseline — Phase 0

Created: 2026-07-12

## Purpose

This directory is the recoverable baseline taken before reorganizing or deleting any
Ceruledge-RL specifications, documentation, audit artifacts, prototypes, helpers, or
runtime files.

A scoped archive was used instead of a repository-wide commit because the surrounding
worktree already contained many unrelated modified, deleted, and untracked files.

## Snapshot scope

- `Ceruledge-RL/` in full, including its current generated/ignored contents.
- Root `smoke_test_encoder.py`.
- Root `smoke_test_prize_check.py`.

The snapshot contains 104 files.

## Recovery artifacts

- `ceruledge-rl-source.zip` — compressed source snapshot.
- `manifest-sha256.csv` — path, size, and SHA-256 for all 104 archived files.
- `integrity-check.txt` — archive-to-manifest and post-test source-drift verification.
- `git-status-before.txt` — repository status before the baseline tests.
- `git-status-after.txt` — repository status after the baseline tests.

Archive SHA-256:

```text
D85419077A13D03BECA2ABCB77E667CB068DF7E77F59F87909DF618F58A618BA
```

The archive contains exactly 104 file entries, with zero missing files, zero extra files,
and zero hash mismatches against the manifest. The 81 active-source rows checked again
after testing had zero drift. Generated `__pycache__` and `out/` rows were excluded from
the post-test drift comparison because tests may legitimately update generated files;
their original snapshot versions remain covered by the archive manifest.

## Baseline verification results

All checks passed:

- Python compilation of all top-level `Ceruledge-RL/*.py` modules and both root smoke
  tests.
- `effect_features.py` self-test.
- `opponent_tags.py` self-test: 1,267 cards checked; 631 cards with tags.
- `stat_bakes.py` self-test.
- `test_features.py`: all generalized feature tests.
- `smoke_test_prize_check.py`: unit tests plus 10 full simulated games; all prize
  invariants passed.
- `smoke_test_encoder.py`: 10 full games, 543 encoder checks, and 8 live evolution
  checks; all passed.

Individual command output is stored in the corresponding `test-*.txt` files.

## Restore guidance

Do not extract this archive directly over an active working tree without reviewing the
changes. Extract it to a temporary directory, compare it against the current tree, and
restore only the intended paths. Use `manifest-sha256.csv` to verify restored content.
