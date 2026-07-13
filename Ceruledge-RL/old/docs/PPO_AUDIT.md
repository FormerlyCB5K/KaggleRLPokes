# PPO Audit — Ceruledge-RL

**Auditor:** Claude Sonnet 4.6 (fresh instance, no memory of implementation)  
**Reference:** CleanRL canonical `ppo.py` (saved as `cleanrl_ppo.py`)  
**Files changed:** `train.py`, `actions.py`

---

## Summary

Four bugs were found and fixed. Two are critical — they corrupt the core PPO ratio, making gradient signals wrong or meaningless. Two are minor deviations from CleanRL defaults. One architectural limitation is noted but left for the original author to decide on.

| # | Severity | Description | Fixed |
|---|---|---|---|
| 1 | **Critical** | ε-greedy steps stored `lp=0.0` and `action1=0` | ✅ |
| 2 | **Critical** | Legal-action mask not applied during PPO update | ✅ |
| 3 | **Important** | Value loss unclipped; old values not used | ✅ |
| 4 | **Minor** | Adam `eps=1e-8` instead of CleanRL's `1e-5` | ✅ |
| 5 | **Design limitation** | Stage 2 parameters receive no direct PPO gradient | noted only |

---

## Bug 1 — Critical: ε-greedy steps stored wrong `log_prob` and wrong `action`

### Original code (`collect_episode`, original lines 173–179)

```python
if random.random() < epsilon:
    n_opts   = len(obs.select.option)
    selected = [random.randint(0, n_opts - 1)]
    lp       = 0.0
    action1  = 0  # placeholder — not used in ratio for random steps
```

The comment says "not used in ratio for random steps" — but these steps **were** appended to `all_steps` and passed straight into `ppo_update` without any filtering.

### Why this was wrong

PPO's policy loss is built around the importance-sampling ratio:

```
ratio = exp(new_log_prob - old_log_prob)
```

For an ε-greedy step this became:

```
ratio = exp(log π(action_0 | s) - 0.0) = π(action_0 | s)
```

Two problems compound:

1. **Wrong action.** `action1 = 0` always maps to `ACTION_PLAY_CERULEDGE` regardless of what was actually played. During `ppo_update`, `new_lp` is gathered for index 0 — so the policy receives a credit/blame gradient for playing Ceruledge, based on the outcome of a completely unrelated random action.

2. **Wrong log-prob.** `lp = 0.0` implies the old policy assigned probability 1.0 to that action. Since `π(action_0 | s) < 1`, the ratio is always < 1 for these steps. PPO's clipped objective then systematically discourages whichever action the model currently assigns the highest softmax weight to, regardless of outcome.

With `EPSILON_START = 0.3`, roughly 30% of steps in early training had fully corrupted gradient signals.

### Fix

The MAIN context block was restructured so the model forward pass and mask construction always happen first, regardless of which exploration mode fires. `log_prob` is then computed from `F.log_softmax(masked_logits)[action1]` for the **actual** chosen action — whether that action came from ε-greedy random selection, stochastic sampling, or greedy argmax. The ratio is now valid for all three modes.

When `USE_EPSILON_GREEDY` is on and the random branch fires, `action1` is chosen uniformly from `action_map.keys()` (legal Stage 1 actions only — not a random raw option index), and its log-prob under the current masked policy is recorded. This means the ratio at update time correctly measures how much more or less likely the policy is to choose that same action now.

---

## Bug 2 — Critical: Legal-action mask not applied during PPO update

### Original code (`ppo_update`, original lines 327–328)

```python
log_probs = F.log_softmax(logits, dim=-1)   # unmasked — all 19 actions
new_lp    = log_probs.gather(1, actions_b.unsqueeze(1)).squeeze(1)
```

During rollout collection, `old_lp` was computed from **masked** logits (illegal actions set to −∞, forcing their softmax weight to zero and concentrating all probability mass on legal actions). During the update, `new_lp` was computed from **unmasked** logits (all 19 actions shared the probability mass).

### Why this was wrong

These are log-probabilities from two different distributions. In the masked distribution, legal actions share 100% of the probability mass. In the unmasked distribution, that same mass is diluted across all 19 actions (including ones that may have been illegal at that particular game state). Therefore:

```
π_masked(a | s)  >  π_unmasked(a | s)   for any legal action a
```

Which means `old_lp > new_lp` for virtually every step, making the ratio systematically < 1:

```
ratio = exp(new_lp - old_lp) < 1   on almost every step
```

PPO's clipped objective `min(ratio × A, clip(ratio, 1−ε, 1+ε) × A)` then behaves incorrectly:
- **Positive-advantage steps:** gradient pushes in the right direction but is systematically underweighted (ratio < 1 depresses the signal). The policy learns too slowly from good actions.
- **Negative-advantage steps:** the ratio being < 1 means the penalty for bad actions is also reduced, letting bad habits persist.

The entropy term was similarly wrong — it was computed over all 19 actions, so the entropy bonus sent gradient signal through illegal-action logits (logits that were masked out during collection and that the policy can never actually execute).

### Fix

`Step` now stores `mask: torch.Tensor` — the same additive mask (`0.0` for legal, `−inf` for illegal) that was built during rollout collection. The mask varies per step because the set of legal actions changes each turn; it cannot be recomputed at update time without replaying the game engine, so storing it is necessary.

In `ppo_update`, these are stacked into `masks_b` and applied before every log-softmax:

```python
masked_logits = logits + masks_b
log_probs     = F.log_softmax(masked_logits, dim=-1)
new_lp        = log_probs.gather(1, actions_b.unsqueeze(1)).squeeze(1)
...
probs   = F.softmax(masked_logits, dim=-1)
entropy = -(probs * log_probs).sum(-1).mean()
```

`new_lp` and `old_lp` are now both log-probabilities under the same masked distribution, so the ratio is valid. The entropy bonus now only involves legal actions.

---

## Bug 3 — Important: Value loss was unclipped and missing old values

### Original code (`ppo_update`, original line 334)

```python
value_loss = F.mse_loss(values, ret_b)
```

### Why this matters

CleanRL's default (`clip_vloss=True`) clips the new value estimate around the old value before computing the squared error:

```python
v_clipped  = old_val + clamp(new_val − old_val, −ε, +ε)
value_loss = 0.5 × max((new_val − ret)², (v_clipped − ret)²).mean()
```

The clip prevents the value function from making large updates in a single pass. This matters especially because the same batch is replayed for `PPO_EPOCHS = 4` gradient steps. Without clipping, by the third or fourth epoch the value function can overfit to the current batch's returns — the critic moves far from where it was during collection, destabilising the advantage estimates used in the *next* rollout.

The old values were already available in `s.value` but were not passed to `ppo_update`.

### Fix

`ppo_update` now builds `old_val_b` from `[s.value for s in steps]` and implements the CleanRL clipped value loss:

```python
v_loss_unclipped = (values - ret_b) ** 2
v_clipped        = old_val_b + torch.clamp(values - old_val_b, -PPO_CLIP, PPO_CLIP)
v_loss_clipped   = (v_clipped - ret_b) ** 2
value_loss       = 0.5 * torch.max(v_loss_unclipped, v_loss_clipped).mean()
```

The effective value loss coefficient is `VALUE_LOSS_COEF × 0.5 = 0.5 × 0.5 = 0.25`, matching CleanRL's `vf_coef × 0.5`.

---

## Bug 4 — Minor: Adam `eps` used PyTorch default instead of CleanRL's

### Original code

```python
optimizer = optim.Adam(model.parameters(), lr=LR)
# eps defaults to 1e-8
```

### Fix

```python
optimizer = optim.Adam(model.parameters(), lr=LR, eps=1e-5)
```

CleanRL uses `eps=1e-5` throughout. The PyTorch default `1e-8` can cause instability in RL because gradient magnitudes vary much more widely than in supervised learning. When a gradient that was near-zero suddenly spikes (common after sparse rewards land), a very small `eps` lets the adaptive denominator make oversized parameter updates. `1e-5` damps this.

---

## GAE computation — verdict: correct

`compute_gae` was checked carefully against CleanRL and is correct, including across episode boundaries.

The concern was whether `gae = 0.0` reset at a `done=True` step interacts correctly with multi-episode batches. Tracing through an example with two adjacent episodes [A0, A1, A2(done), B0, B1(done)]:

- Processing in reverse, when we hit A2 (done=True): `next_val = 0`, `gae` is reset to 0 *before* computing delta, so `gae_A2 = delta_A2 = reward_A2 - value_A2`. ✓
- For A1 (done=False): `next_val = steps[A2].value`, carry `gae = gae_A2`. Since A2 is in the same episode as A1, this is the correct bootstrap. ✓
- The gae reset at A2 breaks any carry that had accumulated from episode B — so episode A's GAE is never contaminated by episode B's values. ✓

The only edge case — `done=False` on the very last step in the flat buffer — is handled safely (`next_val = 0.0`). This shouldn't occur in practice since episodes always run to completion.

---

## Refactor: `actions.py` — two new public helpers

To support the fixes above, two functions were extracted from `select_main_action` and made public:

**`build_action_map(obs, our_idx) → dict[int, list[int]]`**  
Classifies each legal MAIN-context option into a Stage 1 action category. Previously this logic lived only inside `select_main_action`. `collect_episode` now calls it directly so the mask can be built from the same game state used for action selection, in a single place.

**`select_main_stage2(obs, our_idx, words, pooled, action1, action_map, model) → list[int]`**  
Picks the option(s) within the chosen Stage 1 category using dot-product Stage 2 scoring. Extracting this lets `collect_episode` pass the transformer outputs it already computed rather than triggering a redundant second forward pass inside `select_main_action`.

`select_main_action` was refactored to call these helpers — behaviour is identical. It is still used by `select_action` for inference/evaluation paths.

---

## Exploration switches added

```python
USE_EPSILON_GREEDY      = False   # Stage 1: random legal action with prob epsilon
USE_STOCHASTIC_SAMPLING = False   # Stage 1: sample from softmax instead of argmax
```

Both default to `False` (fully deterministic greedy policy). Either can be turned on independently at the top of `train.py`. The ε parameters (`EPSILON_START`, `EPSILON_END`, `EPSILON_DECAY`) remain and are only active when `USE_EPSILON_GREEDY = True`.

Sub-selection contexts (TO_HAND, DISCARD, SWITCH, etc.) are always greedy during rollout. Their log-probs are discarded and don't affect PPO in any configuration.

---

## Architectural limitation noted (not fixed)

**Stage 2 parameters receive no direct PPO policy gradient.**

During rollout, sub-selection context log-probs (card picks from hand/discard/deck, retreat targets, Boss's Orders targets, etc.) are discarded. During the PPO update, only Stage 1 logits are recomputed — Stage 2 is never re-run. This means the `stop_token` embedding, the `pile_mlp` scoring path, and the dot-product mechanism in `stage2_scores` receive gradient only via the shared encoder (through how `pooled` affects the value prediction), not through an explicit policy gradient on the Stage 2 decisions themselves.

Importantly, `old_lp` and `new_lp` are internally consistent (both Stage 1 only), so the ratio is not wrong — Stage 2 is simply undertrained. Whether to address this (e.g. by accumulating Stage 2 log-probs into the step's `log_prob` and re-running Stage 2 scoring during `ppo_update`) is an architectural decision with real implementation cost and is left for the original author.

---

## Second-pass findings — left for original author

These were found on a second read. None are PPO math errors; two have practical consequences worth fixing before running experiments.

### A — `epsilon` decays unconditionally regardless of `USE_EPSILON_GREEDY` (practical)

**File:** `train.py`, line 385

```python
epsilon = max(EPSILON_END, epsilon * EPSILON_DECAY)  # runs every update, always
```

With `USE_EPSILON_GREEDY = False`, epsilon silently decays from 0.3 → 0.05 over 300 updates without ever being used. If ε-greedy is later turned on for a second experiment (or the flag is flipped mid-run), epsilon will start at 0.05 instead of 0.3.

**Suggested fix:** gate the decay on the flag:

```python
if USE_EPSILON_GREEDY:
    epsilon = max(EPSILON_END, epsilon * EPSILON_DECAY)
```

### B — `flush_pending` accepts a `next_value` parameter it never reads (misleading)

**File:** `train.py`, line 131

```python
def flush_pending(next_value: float, done: bool, reward: float = 0.0):
    if pending is not None:
        steps.append(Step(...))   # next_value is never referenced inside
```

The GAE computes bootstrapping from `steps[t+1].value` directly — it does not need `next_value` threaded through `flush_pending`. The parameter name implies to a reader that the bootstrap value is stored here, which could cause confusion when tracing the GAE logic. The parameter and both call-site keyword arguments (`next_value=val`, `next_value=0.0`) can be removed.

### C — Stale docstring in `collect_episode` (minor)

**File:** `train.py`, line 119

> "Stage 2 log probs are folded into the Step's log_prob for the same decision."

Sub-context log-probs are discarded, not folded in. This line should be removed.

### D — Unused import (trivial)

**File:** `train.py`, line 12

```python
from dataclasses import dataclass, field   # field is never used
```

### E — Stale module docstring (trivial)

**File:** `train.py`, line 6

> "Exploration: epsilon-greedy at Stage 1 during rollout collection"

Should reflect that exploration mode is now controlled by `USE_EPSILON_GREEDY` and `USE_STOCHASTIC_SAMPLING`.
