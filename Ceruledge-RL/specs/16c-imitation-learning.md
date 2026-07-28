# 16c — Imitation Learning Pipeline

## Purpose

Train 16b's model to predict the actual move a recorded player made, using
`Imitation-Learning/Top-ladder-data/*/*.zip` — real Kaggle episode replays across
genuinely diverse (non-Ceruledge) decks. Confirmed by direct inspection: each step's
per-player entry has both `observation` (the exact JSON the engine hands the bot — same
shape `cg_download.utils.to_dataclass` already converts, per spec 15) and `action` (the
actual chosen option indices, e.g. `action=[0]` for a single choice, `[]` when that player
had no decision that step). This gives real supervised labels with no extra tooling.

## Behavior

### Extraction

**Off-by-one alignment (confirmed by direct inspection, not documented anywhere):**
`steps[i][player].action` is the action taken *in response to* `steps[i-1][player]
.observation` — the same step index's own `observation` already reflects the state
*after* that action resolved. Pairing `action` with the same-index `observation` produces
nonsensical results (e.g. `action=[1]` against a 1-option list, which is out of range) —
confirmed against real data: 614/614 sampled actions are valid indices into the
*previous* step's option list for that player, 0/614 against the same step's. The
competition's own `specification.action` field ("List of option index") doesn't mention
this shift; it was only found by testing both pairings against real recorded games.

For each episode zip, for each player, walk `steps[i-1][player].observation` paired with
`steps[i][player].action`, `i` from 1 to `len(steps)-1`. Skip pairs where the previous
observation has no `select` (`obs.current is None`, or nothing to decide) or `action` is
empty.

For each such (obs, action) pair:
1. `build_game_state(obs, our_idx, prize_tracker, our_tracker, opponent_tracker)` (spec
   15's adapter) -> `build_observation(state)` (spec 13a) -> `list[Word]`.
2. Run 16a's classifier on `obs` to get the verb map (if `SelectContext.MAIN`) or the flat
   candidate list (otherwise).
3. Match the recorded `action` (list of option indices) against the classified
   verb/candidates to build the label:
   - MAIN context: label = (verb of `obs.select.option[action[0]]`, index of `action[0]`
     within that verb's candidate list). For compound `ATTACH`/`EVOLVE` options, the label
     candidate is the resolved (card, target) pair matching that option index.
   - Non-MAIN context: label = index of `action[0]` within the flat candidate list.
     **Only `action[0]` is supervised for multi-count selections** (`minCount`/`maxCount`
     > 1) — confirmed by inspection that the recorded JSON has exactly one `observation`
     snapshot per step-entry, so `action[1]`, `action[2]`, etc. are picks made against a
     live, already-updated option list (the previous pick removed) that the recording
     never captures; there is nothing to validate or supervise those later picks against.
     This means v1's IL supervision is weaker for multi-select decisions (Drilbur-style
     variable-count picks) than for single-select ones — an accepted v1 gap, not a bug.
4. One tracker triple (`PrizeTracker`, our `GameStateTracker`, opponent `GameStateTracker`)
   per `(episode, our_idx)` pair, reused across that episode's steps — same lifecycle
   `test_live_adapter_replay.py` already established. Advance the trackers on every
   distinct chronological observation, including forced choices marked `usable=false`
   that are excluded from supervision. Replay observations carry delta logs since the
   preceding selection; filtering a forced choice before updating the trackers can
   otherwise lose the only log for a prize take or another stateful event. Repeated
   copies of the non-acting player's unchanged observation are deduplicated before
   tracker updates.

### Labels excluded from v1

- Steps where `action == []` (no decision made by this player that step — the other
  player acted, or nothing was legal).
- `SETUP_ACTIVE_POKEMON`/`SETUP_BENCH_POKEMON` decisions (matches 16a's scope).

### Loss

- MAIN-context steps: cross-entropy over the 8 verbs (masked to legal verbs present in
  `obs.select.option`) + cross-entropy over that verb's candidates (masked to the actual
  candidate list size) — two terms, summed.
- Non-MAIN steps: cross-entropy over the flat candidate list only.
- Both terms share the same forward pass (one `list[Word]` -> one model call per decision
  step).

### Data split

Split by **episode**, not by step — steps within one game are highly correlated, so a
per-step random split would leak. The implementation gathers every global game key
(`source`, `day`, `episode filename`), shuffles the complete game inventory with a fixed
seed, and holds out an exact fraction (10% by default). Every position from a validation
game is excluded from training.

The exact validation-game list, seed, cache-inventory fingerprint, per-day integrity
counts, and split hash are persisted beside the checkpoint. A changed seed, fraction, or
cache inventory fails rather than silently changing validation. Fixed validation
examples are materialized once into per-day shards and reused across epochs/resubmitted
jobs. There is no rare-position oversampling or special diagnostic holdout.

### Training loop

- Standard supervised loop with Adam and true vectorized mini-batches; checkpoint the
  best fixed-validation accuracy. One mini-batch shares a single transformer
  forward/backward call while retaining per-example variable candidate lists for Stage
  2 scoring. The cluster default batch size is 256.
- `--device auto` selects CUDA when available; cluster scripts require CUDA explicitly
  and request one GPU. CUDA training uses float16 autocast plus gradient scaling by
  default, enables TF32 for eligible float32 matrix multiplications, and can disable
  mixed precision with `--no-mixed-precision`.
- Evaluation uses the same vectorized batches under inference mode. Training skips
  per-example accuracy transfers from GPU to CPU; evaluation transfers one correctness
  tensor per batch.
- Training is day-chunked because retaining all extracted examples would require roughly
  225 GB for 14 full days. One cached source/day is one **mini-epoch**: load once, remove
  globally held-out games, shuffle all remaining positions, train, save resumable state,
  and release memory. Day order is reshuffled every outer epoch. This keeps cache I/O to
  one load per training day/pass instead of rereading every day to construct globally
  mixed batches.
- One outer epoch visits every source/day mini-epoch exactly once and then evaluates the
  same complete fixed validation set. The model and optimizer persist across
  mini-epochs.
- `Imitation-Learning/build_example_cache.py` extracts each source/day pair once, in
  parallel across episodes, and writes
  `Top-ladder-data/example-cache/<source>/<day>.pkl` plus a manifest. Later epochs reload
  those pickles instead of repeating live observation extraction.
- Manifests lock the Example schema version, source label/day, extraction limits, source
  metadata fingerprint, and example count. Source-backed training fails if any required
  day is missing or stale; cache-only cluster operation validates the copied cache's own
  manifest inventory.
- Cache-backed input is required so the global split, validation shards, and resume
  position can be made persistent without re-extracting games.
- A latest-state checkpoint is written atomically after every mini-epoch and includes
  model, optimizer, mixed-precision scaler, RNG state, next day/epoch, fixed split
  identity, baseline, best accuracy, and early-stopping state. `--resume` continues from
  it. The AiMOS/NPL scripts request a pre-walltime signal, terminate any partial current
  mini-epoch, and submit a continuation; at worst only the interrupted day is repeated.
- Early stopping checks the fixed validation set after each complete outer epoch.
  Defaults are patience 5 and minimum accuracy improvement 0.001; patience 0 disables it.
- Evaluation metric: top-1 accuracy against the recorded action, both overall and split by
  verb, on held-out episodes. Success bar (per spec 16's overview): clearly better than a
  random/majority baseline — no specific target percentage is fixed for this v1.

## Data

Input: raw `Imitation-Learning/Top-ladder-data/<day>/*.zip` archives or the preferred
sanitized per-episode JSON dataset under `Top-ladder-data/sanitized/<day>/`. The reusable
cache lives under `Top-ladder-data/example-cache/` by default. Output is a PyTorch
checkpoint plus a sibling run-configuration JSON and scheduler logs.

## Interfaces / seams

- Depends on 15's `live_adapter.build_game_state` and 13a's `build_observation` for the
  observation side (unchanged, reused as-is).
- Depends on 16a for label construction (verb + candidate classification) and 16b for the
  model forward pass and loss computation.
- Independent of `Ceruledge-RL/train.py` entirely — no shared code, no shared checkpoint
  format.

## Out of scope

- Self-play / PPO fine-tuning on top of the resulting checkpoint (follow-up spec).
- Hyperparameter search, learning-rate schedules, or data augmentation.
- Deploying the trained model as an opponent-pool member.

## Open questions

- None currently blocking.
