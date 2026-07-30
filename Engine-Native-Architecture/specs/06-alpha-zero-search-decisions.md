# 06 - AlphaZero-Style Search Decisions

Status: active implementation record; value-learning gate and MCTS implementation
approved by the user on 2026-07-30.

This file records decisions and their staged implementation. The user authorized the
gated terminal-outcome value-learning phase and then the MCTS phase on 2026-07-30.
Multi-selection semantics and config integration are now implemented as specified below.

This work applies only to `Engine-Native-Architecture/` and its
`Imitation-Learning/` data and training path. `Ceruledge-RL/` is deprecated.

## 1. Search family

- Use an AlphaZero-style neural MCTS: the network policy supplies action priors and the
  network value evaluates nonterminal leaves.
- Do not perform random rollouts.
- Use one shared network body with policy and value heads.
- Imitation learning remains the initialization phase. AlphaZero-style self-play is a
  separate subsequent pipeline and never rewrites the offline expert targets.
- Search must be available when trained agents play, including training-time gameplay
  evaluation.
- Do not run MCTS over the recorded imitation corpus to relabel or distill its expert
  policy targets. Search is not part of the offline imitation loss.
- Prepare a separate AlphaZero-style MCTS self-play pipeline as the next training stage.
  That later pipeline will use root visit distributions as policy targets and terminal
  outcomes as value targets.

## 2. Legal actions and policy use

- The engine-provided option list is the sole source of legal actions.
- Do not reconstruct legality or add a second game-rules legality mask.
- The existing fixed-width option tensor may continue to mask unused padding slots; this
  is a tensor-shape mask, not a legality system.
- For ordinary single-selection nodes, retain every engine-provided legal action.
- Do not hard-prune to policy top-k by default. AlphaZero-style PUCT provides soft
  pruning because finite search spends most visits on high-prior or high-value actions
  without making lower-prior legal actions permanently unreachable.
- An experimental hard-pruning switch may be added later, but its default must be off
  and its use must be explicit in run configuration.

### 2.1 Multi-selection search semantics

- Dragapult ex's `DamageCounterAny` resolution is not a true multi-selection. The engine
  exposes it as repeated single-selection prompts, and `remainDamageCounter` is already
  present in the engine-native global features. Search may therefore traverse each
  counter placement as an ordinary single-selection edge.
- In the first MCTS implementation, a true multi-selection is a policy-resolved forced
  macro-action. The existing inclusion head deterministically produces one complete
  legal subset using its current threshold-and-cardinality projection; the engine applies
  that subset, and MCTS continues from the resulting state.
- Do not introduce partial-selection nodes, a STOP-action search protocol, or a separate
  multi-selection state tracker in the first implementation.
- Because MCTS has only one generated subset at such a prompt, it cannot compare or
  improve alternative subsets. Self-play must not treat the resulting one-child visit
  distribution as a meaningful search-improved inclusion target. Until genuine subset
  branching exists, the inclusion head remains trained from imitation targets and
  multi-selection states are omitted from the self-play search-policy objective.

Known follow-up problem: add optional search over multiple complete legal subsets without
introducing partial-selection state. The preferred extension is a bounded candidate
generator that ranks complete subsets using the factorized inclusion probabilities,
uses each complete subset as one MCTS edge, and recovers the initial behavior when its
candidate count is one. Exact enumeration may be used when the legal subset space is
small; otherwise generation must remain bounded. The design, limits, training targets,
and validation criteria for this extension remain future work.

## 3. Tree policy

Use the original AlphaGo Zero/AlphaZero constant-`c_puct` PUCT form:

```text
argmax_a [ Q(s,a) + U(s,a) ]

U(s,a) = c_puct * P(s,a) * sqrt(N(s)) / (1 + N(s,a))
```

- `P(s,a)` is the policy prior over the engine's legal options.
- `Q(s,a)` is the backed-up mean outcome value.
- `N(s)` and `N(s,a)` are parent and edge visit counts.
- `c_puct` must be configurable and logged. The papers did not publish a universal
  numeric value, so the initial default must be validated empirically rather than
  silently borrowing the later dynamic `c_base`/`c_init` formula.
- Root Dirichlet noise and visit-temperature sampling are training-play exploration
  controls only. Evaluation and Kaggle play use no root noise.

## 4. Value target and reward shaping

- Replace the previously intended shaped discounted-return meaning for search models
  with the AlphaZero terminal-outcome target from the current player's perspective:
  win `+1`, draw `0`, and loss `-1`.
- Bound the value output to `[-1, 1]` with `tanh`.
- Nonterminal search leaves are evaluated directly by this value head.
- Terminal states are scored exactly from the engine result and never evaluated by the
  value head.
- The config record must state the absence of shaping explicitly rather than silently
  omitting reward details. Its reward section must carry equivalent information to:

```json
{
  "reward_shaping": {
    "enabled": false,
    "value_target": "terminal_outcome",
    "win": 1.0,
    "draw": 0.0,
    "loss": -1.0,
    "discount": 1.0,
    "value_activation": "tanh"
  }
}
```

## 5. Terminal handling

- Keep the first implementation simple.
- Every reached terminal leaf receives its exact win/draw/loss value.
- If a legal root child is itself an immediate terminal win, select it immediately.
- A terminal win found deeper in one sampled line is not automatically a proven root
  win because an opponent may have another response.
- Do not add a general endgame solver, broad proof-number search, or complex solved-state
  propagation in the first implementation.

## 6. Imperfect information and randomness

- Search continues only through deterministic transitions justified by public
  information.
- Stop at the configured depth limit or before a transition whose result consumes
  imperfect information, including a coin flip, unknown draw, deck search or reveal,
  facedown Prize reveal, or an opponent decision whose legal choices depend on hidden
  cards.
- The official competition search API is permitted at inference, but it simulates the
  hidden card identities predicted and supplied by the agent. It does not reveal the
  true hidden state and it does not automatically stop when a guessed identity begins to
  affect the branch.
- Use `manual_coin=True` so a coin flip becomes an explicit boundary rather than a
  sampled outcome.
- Do not introduce a `GameStateTracker`, `PrizeTracker`, hidden-card reconstruction,
  belief-state tracker, or determinization ensemble.
- Keep boundary detection local and minimal. The first implementation combines
  pre-transition effect/END checks with post-step log, zone, prompt, and actor checks,
  and backs up the last safe public-information value.
- TODO after the conservative first version: revisit public-information inference that
  can safely narrow deck and facedown-Prize composition without accessing true hidden
  state. Do not block initial MCTS on this extension and do not introduce a general
  tracker as part of the first version.

## 7. Search output and budgets

- Root visit counts define the search policy.
- Training gameplay may sample from visit counts using a configurable temperature and
  may use configurable root Dirichlet noise.
- Use AlphaZero's initial search profile: 800 simulations for training, moves sampled
  from root visit counts, root Dirichlet exploration during self-play, and greedy
  highest-visit play during evaluation. All values remain configurable.
- Validation, evaluation, and Kaggle play choose the highest-visit root action
  deterministically, except that an immediate proven terminal win takes precedence.
- Training and evaluation must have separate repetition and wall-clock budgets. Training
  may use more search than evaluation.
- Kaggle play must respect the ten-minute total game budget. Search exposes both a
  per-decision limit and a cumulative game search budget; exhaustion falls back to the
  raw policy head.
- MCTS repetitions, maximum depth, PUCT parameters, search temperatures/noise, wall-clock
  limits, and network hyperparameters must ultimately be batch-script switches and be
  logged by the config system.
- Models without tree search must record search as explicitly disabled rather than
  silently omitting search metadata.

## 8. Checkpoint compatibility

- Model width, layer count, head count, feed-forward width, and related architecture
  switches may require fresh training runs. This is accepted.
- Compatibility loading may be provided where shapes match, but new architecture sweeps
  do not need to preserve full checkpoint compatibility.

## 9. Locked training boundary

The initial implementation has two narrowly separated responsibilities:

1. extend the existing imitation-learning pipeline so the policy continues to learn
   expert actions while the value head learns the recorded game's terminal outcome; and
2. prepare a separate MCTS self-play pipeline for later AlphaZero-style policy
   improvement.

The imitation stage does not backpropagate through search, replace expert actions with
MCTS visits, or perform offline search distillation. The self-play stage, when activated
later, will generate its own `(state, root visit distribution, terminal outcome)`
training examples.

## 10. Implementation gate

MCTS and self-play coding was gated on completion and review of terminal-outcome value
learning in the imitation pipeline. The user reviewed and opened this gate on
2026-07-30.

Before the gate may be opened:

1. the imitation dataset/cache path must supply the recorded terminal outcome from the
   acting player's perspective;
2. the value head must use the locked `tanh` output and win/draw/loss target;
3. the imitation trainer must optimize and report the value objective without changing
   the existing expert policy targets;
4. focused validation must demonstrate correct perspective, targets, loss behavior,
   checkpoint/resume behavior, and validation metrics; and
5. the completed value-learning change and its evidence must be reviewed by the user.

The shared MCTS runtime and self-play preparation are authorized. The initial self-play
checkpoint policy is the AlphaZero/latest-network policy: each game pins one immutable
hash of the current latest checkpoint from start to finish, the resulting training
update becomes the next latest network, and there is no AlphaGo Zero 55% promotion
gate. Periodic head-to-head evaluation remains diagnostic and does not gate promotion.

## 12. Initial MCTS and self-play implementation

The first implementation now includes:

- a generic constant-`c_puct` neural MCTS with direct value leaves, exact terminal
  scoring, root Dirichlet noise only in training, temperature-controlled root-visit
  sampling in training, and greedy root visits in evaluation;
- an engine-native bridge using only engine-provided legal options, `manual_coin=True`,
  policy-resolved true multi-select macro-actions, and conservative local
  hidden-information boundaries;
- fresh trees per real decision, immediate root-terminal-win selection, configurable
  simulation/depth/per-decision/cumulative-game budgets, and deterministic seeds;
- search-enabled serving bundles that require a `tanh` value head and preserve every
  resolved search switch in `model.pt` and the bundle manifest;
- a latest-network self-play generator that pins the checkpoint per game, stores root
  visit distributions and acting-player terminal outcomes in atomic per-game shards,
  retains forced/multi-select positions as value-only examples, and records the exact
  checkpoint hash for every game;
- a replay-window trainer using equal policy/value coefficients of `1.0`, L2 coefficient
  `1e-4`, a deterministic game-disjoint train/validation split, and no promotion gate;
  and
- cluster entry points and reference commands for imitation configuration, self-play
  generation, replay training, and time-bounded Kaggle packaging.

The meaningful network shape switches are model width, encoder layers, attention heads,
feed-forward width, static/effect projection widths, register count, and dropout. They
are available in the shared imitation batch entry point and logged in checkpoints and
run configs. `d_num` remains fixed by the 2,239-field interchange schema and `d_card`
remains a deliberately dead compatibility field, so neither is presented as a
misleading training switch.

The cumulative search budget is accounted across decisions by a serving policy instance.
When exhausted, serving falls back to the raw policy head instead of exceeding the
configured game budget. The reference Kaggle profile reserves two minutes of the
ten-minute game limit by using a 480-second cumulative search cap; this is a configurable
operational starting point rather than a paper-derived constant.

## 11. Completed value-learning implementation

The gated imitation-learning change is implemented as follows:

- cache schema `engine-native-il-v3` adds one scalar `float32 value_target` to every
  decision row and retains forced one-option decisions;
- the label is derived once from the episode's final two-player rewards and attached
  from the acting player's perspective: higher reward `+1`, equal rewards `0`, lower
  reward `-1`;
- malformed, missing, non-finite, or non-numeric rewards are hard errors rather than
  silently producing a label;
- the existing categorical and joint-Bernoulli expert policy targets are unchanged;
- forced one-option rows contribute value MSE but are excluded from policy loss and
  policy metrics, so they send no gradient to either policy head;
- imitation-created models use `ModelConfig(value_activation="tanh")`, while the
  default legacy/reference construction retains identity activation so the supplied
  golden checkpoint remains exactly reproducible;
- the training objective is mean policy NLL plus `value_loss_weight * value_mse`;
- imitation learning uses `value_loss_weight = 0.01`, exactly matching AlphaGo Zero's
  supervised-learning experiment, while the later AlphaZero self-play objective will
  use equal policy/value coefficients of `1.0`;
- early stopping and best-checkpoint selection use the combined validation loss;
  policy NLL remains separately reported;
- validation additionally reports value MSE, MAE, decisive-outcome sign accuracy,
  mean prediction, mean target, and decisive-example count;
- exact-resume checkpoints include partial value-loss totals, combined best loss,
  policy NLL at that checkpoint, and model configuration; and
- folder-agent bundles preserve the checkpoint's value activation so dashboards and
  later search consumers evaluate the trained value consistently.

This is an intentional cache-schema break. Existing `engine-native-il-v1` and
`engine-native-il-v2` caches must be rebuilt before the current value-head training.

Focused validation on 2026-07-30 passed all 75 tests under
`Engine-Native-Architecture/tests`, including acting-perspective and draw targets,
invalid-reward rejection, forced-choice value-only gradients, cache target validation,
joint-loss gradients, value range, metrics, interrupted/resumed training equality,
serving-bundle metadata, exact 2,370,259-parameter accounting, and unchanged golden
reference outputs.

The run-config/batch-script extension is implemented. Every current search parameter is
exposed by the command line and batch entry points, written to run config, and reflected
in `cluster/COMMAND_EXAMPLES.txt`. Imitation runs expose and log
`value_loss_weight = 0.01`, record the no-shaping terminal-outcome contract, and record
tree search explicitly as either disabled or with the complete resolved profile,
including `c_puct`.
