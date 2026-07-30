# 06 - AlphaZero-Style Search Decisions

Status: active design and staged-implementation record, 2026-07-30.

This file records decisions made during architecture discussion. The user authorized
the gated terminal-outcome value-learning phase on 2026-07-30. Multi-selection search
semantics remain deferred until MCTS implementation planning. Integration with the
run-config system is also deferred until the user confirms that the concurrently
developed config work is ready to extend.

This work applies only to `Engine-Native-Architecture/` and its
`Imitation-Learning/` data and training path. `Ceruledge-RL/` is deprecated.

## 1. Search family

- Use an AlphaZero-style neural MCTS: the network policy supplies action priors and the
  network value evaluates nonterminal leaves.
- Do not perform random rollouts.
- Use one shared network body with policy and value heads.
- The initial phase remains imitation learning. AlphaZero-style self-play fine-tuning is
  a later phase, not part of the first implementation.
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

Use the AlphaZero PUCT form:

```text
argmax_a [ Q(s,a) + U(s,a) ]

U(s,a) = C(s) * P(s,a) * sqrt(N(s)) / (1 + N(s,a))

C(s) = log((1 + N(s) + c_base) / c_base) + c_init
```

- `P(s,a)` is the policy prior over the engine's legal options.
- `Q(s,a)` is the backed-up mean outcome value.
- `N(s)` and `N(s,a)` are parent and edge visit counts.
- `c_base` and `c_init` must be configurable and logged.
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
- Keep boundary detection local and minimal. The exact pre-transition detection
  mechanism remains an implementation-planning question because `search_step` may
  automatically advance across hidden-state consumption.

## 7. Search output and budgets

- Root visit counts define the search policy.
- Training gameplay may sample from visit counts using a configurable temperature and
  may use configurable root Dirichlet noise.
- Validation, evaluation, and Kaggle play choose the highest-visit root action
  deterministically, except that an immediate proven terminal win takes precedence.
- Training and evaluation must have separate repetition and wall-clock budgets. Training
  may use more search than evaluation.
- Kaggle play must respect the ten-minute total game budget. Search needs both a
  per-decision limit and game-budget-aware time management; exact allocation remains for
  implementation planning.
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

## 10. Hard implementation gate

MCTS and self-play coding is gated on completion and review of terminal-outcome value
learning in the imitation pipeline.

Before the gate may be opened:

1. the imitation dataset/cache path must supply the recorded terminal outcome from the
   acting player's perspective;
2. the value head must use the locked `tanh` output and win/draw/loss target;
3. the imitation trainer must optimize and report the value objective without changing
   the existing expert policy targets;
4. focused validation must demonstrate correct perspective, targets, loss behavior,
   checkpoint/resume behavior, and validation metrics; and
5. the completed value-learning change and its evidence must be reviewed by the user.

Until the user explicitly approves that review and lifts this gate:

- do not implement the shared MCTS runtime;
- do not implement MCTS inference/search integration;
- do not implement self-play data generation or self-play training;
- do not add placeholder MCTS modules, scripts, tests, or config switches; and
- do not treat completion of automated tests alone as permission to proceed.

Architecture discussion and implementation planning may continue while the gate is
closed, but MCTS/self-play source changes may not begin.

## 11. Value-learning implementation awaiting user review

The gated imitation-learning change is implemented as follows:

- cache schema `engine-native-il-v2` adds one scalar `float32 value_target` to every
  decision row;
- the label is derived once from the episode's final two-player rewards and attached
  from the acting player's perspective: higher reward `+1`, equal rewards `0`, lower
  reward `-1`;
- malformed, missing, non-finite, or non-numeric rewards are hard errors rather than
  silently producing a label;
- the existing categorical and joint-Bernoulli expert policy targets are unchanged;
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

This is an intentional cache-schema break. Existing `engine-native-il-v1` caches do not
contain outcomes and must be rebuilt before value-head training.

Focused validation on 2026-07-30 passed all 70 tests under
`Engine-Native-Architecture/tests`, including acting-perspective and draw targets,
invalid-reward rejection, cache target validation, joint-loss gradients, value range,
metrics, interrupted/resumed training equality, serving-bundle metadata, exact
2,370,259-parameter accounting, and unchanged golden reference outputs.

The run-config/batch-script extension for MCTS remains unimplemented until the MCTS
gate opens. Every search parameter listed in section 7 must then be exposed by the
command line and batch entry point, written to the run config, and reflected in
`cluster/COMMAND_EXAMPLES.txt`. The current imitation entry point already exposes and
logs `value_loss_weight = 0.01`, records the no-shaping terminal-outcome contract, and
records tree search as explicitly disabled. The MCTS gate remains closed until the user
reviews this implementation and explicitly opens it.
