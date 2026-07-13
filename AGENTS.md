# Project Guidance

This repository contains several Pokemon TCG Pocket competition agents and experiments.
The current primary development area is `Ceruledge-RL/` unless the user names another
agent or subsystem.

## Start of every task

1. Read `PROJECT_MEMORY.md` for the concise project handoff.
2. For Ceruledge RL work, read `Ceruledge-RL/specs/README.md` and the active spec linked
   there. Use `Ceruledge-RL/MODEL-ARCHITECTURE.md` for the reader-oriented description
   of implemented model behavior.
3. Inspect the relevant source and current git status before making changes. The
   worktree may contain substantial user changes; never discard, rewrite, or stage
   unrelated work.
4. Treat files under `Ceruledge-RL/old/` as historical context, not current contracts.

## Sources of truth

- Executable code and focused tests define actual current behavior.
- Active and completed specs under `Ceruledge-RL/specs/` document intended behavior.
- `Ceruledge-RL/MODEL-ARCHITECTURE.md` summarizes the implemented architecture.
- `PROJECT_MEMORY.md` is a navigation aid and handoff summary. If it conflicts with
  code or a current spec, verify the discrepancy and update the memory rather than
  forcing the implementation to match the summary.
- `docs/experiments.md` records completed or running experiments. Do not invent metrics.

## Working conventions

- Prefer narrow changes with focused validation first.
- Run Python commands from the repository root unless a command explicitly says
  otherwise; several modules depend on root-relative imports and paths.
- Preserve generated submissions, checkpoints, archives, datasets, and large binaries
  unless the user explicitly asks to regenerate or remove them.
- Do not use `Ceruledge-RL/deck.csv` as the source of truth where a current spec or the
  implemented fixed deck list says otherwise.
- Record exact commands, configurations, checkpoint locations, metrics, and conclusions
  for meaningful training/evaluation runs in `docs/experiments.md`.

## Validation menu

Choose checks proportional to the change. Common focused checks include:

```powershell
python Ceruledge-RL/test_features.py
python Ceruledge-RL/test_dispatch.py
python Ceruledge-RL/test_pool.py
python smoke_test_prize_check.py
python smoke_test_encoder.py
```

For a short PPO loop, use an isolated output directory and disable external logging:

```powershell
python Ceruledge-RL/train.py --episodes-per-update 4 --n-updates 2 --log-every 1 --no-wandb --out-dir <temporary-output-directory>
```

Check `python Ceruledge-RL/train.py --help` before relying on optional opponent or pool
arguments, because the active opponent-pool work may change their behavior.

## Maintaining project memory

At the end of substantial project work, update `PROJECT_MEMORY.md` when the architecture,
current phase, important decisions, validation status, or next steps materially changed.
Keep it concise and point to detailed source files instead of duplicating them. Add a
dated entry to `docs/experiments.md` only when an experiment was actually run or a
result was supplied by the user. Clearly label unknown, proposed, running, and verified
information. Never replace newer user-written notes with older conversational context.

