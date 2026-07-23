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
   `test_live_adapter_replay.py` already established.

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
per-step random split would leak. A simple holdout fraction (e.g. last N% of episodes by
filename) is enough for v1; no cross-validation needed yet.

### Training loop

- Standard supervised loop: batch several decision steps (padding candidate-count
  dimensions, masking illegal/absent slots to `-inf` before softmax), Adam, checkpoint the
  best validation accuracy.
- Evaluation metric: top-1 accuracy against the recorded action, both overall and split by
  verb, on held-out episodes. Success bar (per spec 16's overview): clearly better than a
  random/majority baseline — no specific target percentage is fixed for this v1.

## Data

Input: `Imitation-Learning/Top-ladder-data/*/*.zip` (already present in this checkout:
`7-12`, `7-13`, `7-14`). Output: a PyTorch checkpoint (model state dict) plus a small
run log (loss/accuracy curves), location TBD at implementation time (likely alongside the
model code under `Imitation-Learning/`).

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
