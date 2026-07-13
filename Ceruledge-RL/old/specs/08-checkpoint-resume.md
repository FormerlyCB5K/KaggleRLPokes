# 08 — Checkpoint & Resume (`--resume`)

> **Archived:** This proposal targets `train_rules-2.py`, which is not present in the
> current project. Phase 4 consolidated checkpoint/resume support into canonical
> `train.py` and removed the former duplicate cluster trainer.
> Retained only in case a separate rules-opponent trainer is reintroduced.

## Purpose

Give `train_rules-2.py` seamless resume across SLURM self-requeues, so a job killed at
the 6 h wall continues from where it stopped instead of restarting training. The Slurm
launcher already passes `--resume` unconditionally; this spec implements it by porting
the proven checkpoint/resume pattern from canonical `train.py`.

## Background

`train_rules-2.py` currently saves only `model.state_dict()` (`policy_update{N}.pth`,
`policy_final.pth`). Resuming from weights alone resets the Adam optimizer state, the
`update` counter, the decayed `epsilon`, the plot histories, and spawns a new wandb
run. `Ceruledge-RL/train.py` now solves this; `submit-batch-ceruledge-ppo.sh`
relies on it via `--signal=B:USR1@180` → requeue trap. `train_rules-2.py` is the
rules-opponent variant of the same script and must behave identically.

## Historical design — port from the canonical trainer

Mirror `train.py`. Restore state matches it: **model, optimizer, update
counter, epsilon, reward/winrate/update histories, and wandb run id.** RNG and engine
state are deliberately NOT restored (the `cg_download` engine RNG isn't controllable;
optimizer-exact continuation is the project's definition of "seamless").

Four edits to `train_rules-2.py`:

1. **CLI flag.** Add next to the other `_p.add_argument(...)` calls:
   `--resume` (`action="store_true", default=False`). Resolve `RESUME =
   _args.resume`. Add `CKPT_PATH = os.path.join(OUT_DIR, "checkpoint.pth")` beside
   `PLOT_DIR`.

2. **`save_checkpoint(...)`.** Add the atomic writer (copy of
   canonical trainer): `torch.save` `{model (CPU tensors), optimizer, update,
   epsilon, reward_history, winrate_history, update_nums, wandb_run_id}` to
   `CKPT_PATH + ".tmp"`, then `os.replace(tmp, CKPT_PATH)`.

3. **Resume block in `train()`.** After `model`/`optimizer`/`epsilon` and the history
   lists are created, before the self-play opponent copy: initialise `start_update = 1`,
   `wandb_run_id = None`; if `RESUME and os.path.exists(CKPT_PATH)`, load and restore
   all fields and set `start_update = ckpt["update"] + 1`; else if `RESUME`, print
   "starting fresh". Ensure the self-play `opponent_model` is created AFTER this block
   so it clones restored weights. Pass `id=wandb_run_id, resume="allow"` to
   `_wandb.init(...)` and capture `wandb_run_id = _wandb.run.id` after init.
   (Mirrors `train.py`.)

4. **Loop bounds + checkpoint call.** Change the loop to `for update in
   range(start_update, N_UPDATES + 1)`. After the existing `SAVE_EVERY` snapshot block,
   call `save_checkpoint(...)` **every update**.

## Files

- Archived: `Ceruledge-RL/old/specs/08-checkpoint-resume.md` (this spec).
- Modified at implementation time: `Ceruledge-RL/train_rules-2.py` (the four edits).
- Reference: `Ceruledge-RL/train.py`,
  `Ceruledge-RL/submit-batch-ceruledge-ppo.sh`.

## Out of scope

- Changing PPO mechanics, hyperparameters, reward shaping, or the SLURM script.
- Restoring python/torch/engine RNG state (matching canonical `train.py`).
- Refactoring `train_rules-2.py` into a common module if that trainer returns.

## Acceptance criteria

- `python train_rules-2.py --resume` with no `checkpoint.pth` starts fresh at update 1
  and prints the "starting fresh" notice.
- After ≥1 update, `OUT_DIR/checkpoint.pth` exists and re-running with `--resume`
  prints "continuing at update N+1" and the loop starts there.
- Restored run reuses the same wandb run id (no new run created).
- A checkpoint is written after every update; killing mid-write leaves a valid
  `checkpoint.pth` (atomic replace).
- `save_checkpoint` payload keys match `train.py` exactly.

## Open questions

- None. (Pattern follows the working `train.py` implementation.)
