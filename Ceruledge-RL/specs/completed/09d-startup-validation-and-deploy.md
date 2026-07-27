# 09d — Startup Validation & Deploy

Part 4 of [`09-opponent-pool.md`](09-opponent-pool.md). Depends on `09a` (resolvers).
Independent of `09c` but most useful once pools exist. Ensures a multi-hour cluster job
never dies mid-run because an agent folder wasn't copied.

## Purpose

Validate the **entire active opponent set** before the first episode, failing loudly with
actionable diagnostics; and update the cluster deploy so all pooled agent folders are
present.

## Behavior

### Fail-fast validation

After CLI parsing resolves the active set (single `--opponent` or `--opponent-pool`),
before any episode runs, for **every** member:

1. Resolve and import its module via the `09a` unique-name loader. On failure, hard-fail
   naming the offending module path, the resolved `_parent`, and the expected layout
   (`<parent>/Ceruledge-RL/train.py` and `<parent>/<Agent-Folder>/...`), in the tone of
   the existing `_load_rules_agent` diagnostic.
2. Resolve its deck. Hard-fail if the CSV is absent (report the exact path **and** flag
   the casing, e.g. "expected `Alakazam-Agent/Deck.csv` (capital D)"), if the inline
   `DECK` attribute is missing, or if the deck length is implausible (e.g. not in a
   sane 40–60 range).
3. For `self`, confirm the model/snapshot path is viable (it is created from the live
   model, so this is a no-op check beyond membership).

Validation imports each agent exactly once and reuses the `09a` cache, so it doubles as
warming the loader. `random` and `self` require no folder.

### Deploy

- Cluster deploy now copies **every pooled agent folder** — with its deck file at exact
  casing — next to `Ceruledge-RL/`, in addition to `cg_download/`.
- Update `submit-batch-ceruledge-ppo.sh` and/or the deploy notes to list the folders and
  state the copy step. A run whose active set references a folder that wasn't copied must
  fail at startup (by the validation above), not mid-run.

## Data

Reads the same module/deck sources as `09a`. Writes only log output (diagnostics).

## Interfaces / seams

- Consumes `09a` resolvers and the active-set resolution from `09c` (or the single
  `--opponent` from `09b`).
- Gatekeeps the training loop: validation runs to completion before episode 0.

## Validation steps

1. **Happy path.** With all seed folders present, a pooled run passes validation and
   proceeds to training. Validation output lists each member as OK.
2. **Missing folder.** Temporarily rename/remove one agent folder (e.g.
   `Clefable-Agent/`) and start a run whose pool includes it. Assert the process aborts
   **before episode 0** with a message naming the missing path and `_parent`.
3. **Casing trap.** Point the Alakazam entry at lowercase `deck.csv` on a
   case-sensitive filesystem (or simulate) and assert the failure message calls out the
   expected capital-`Deck.csv`.
4. **Implausible deck.** Feed a truncated/empty deck file and assert it fails validation
   with a length diagnostic rather than starting and crashing later.
5. **Deploy check.** Confirm `submit-batch-ceruledge-ppo.sh` (or notes) enumerates every
   pooled folder; a dry read of the script shows the copy step covers them.

## Success conditions

- Any missing/broken/mis-cased member causes an immediate, clearly-diagnosed abort before
  training starts.
- A complete, correctly-deployed pool passes validation and trains.
- The deploy script/notes account for all pooled agent folders.

## Out of scope

- Sampling and metrics (`09c`, `09e`).
- Auto-downloading or auto-copying agent folders (deploy is still manual/scripted).
