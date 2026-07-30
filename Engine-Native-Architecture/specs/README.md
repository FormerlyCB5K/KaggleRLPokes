# Specifications

Specifications in this folder govern only `Engine-Native-Architecture/`.

## Active

- [`01-implementation-decisions-and-deferrals.md`](01-implementation-decisions-and-deferrals.md)
  - active authority rules, locked behavior, provisional-table assumptions, v3
  discrepancies, and deferred work.
- [`02-implementation-plan.md`](02-implementation-plan.md) - phased implementation plan
  and verified completion status for the provisional Python milestone.
- [`03-imitation-data-to-train-handoff.md`](03-imitation-data-to-train-handoff.md) -
  implemented contract for converting the sanitized six-day TEST corpus into
  supervised tensor shards, standard PyTorch batches, and behavior-cloning losses
  without trackers or the previous observation/action pipeline. The user reported the
  uncapped cache and CUDA acceptance jobs completed successfully.
- [`04-behavior-cloning-trainer.md`](04-behavior-cloning-trainer.md) - implemented
  full-validation, atomic-checkpoint, exact-resume behavior-cloning trainer and
  six-day SLURM continuation contract. Full cluster optimization remains pending.
- [`05-raw-zip-production-cache.md`](05-raw-zip-production-cache.md) - implemented
  two-pass direct raw-ZIP sanitization and tensor-cache path for July 12-27. It avoids
  loose sanitized episode JSON while preserving spec 03's global split and cache
  semantics. The full cluster build remains pending.
- [`06-alpha-zero-search-decisions.md`](06-alpha-zero-search-decisions.md) - active
  design record for AlphaZero-style PUCT, terminal-outcome value learning,
  deterministic-public search boundaries, simple terminal handling, and search-budget
  controls. Its gated imitation phase is implemented with cache schema v2, `tanh`
  terminal-outcome learning, a joint policy/value objective, value metrics, and
  exact-resume checkpoint support. A hard gate still forbids all MCTS/self-play coding
  until this implementation and its validation evidence are reviewed and explicitly
  approved by the user.

## Superseded

- [`00-architecture-contract.md`](00-architecture-contract.md) - retained first-PDF
  baseline; do not implement from it.

Future implementation specs should be added here rather than to `Ceruledge-RL/specs/`.
They must preserve the architecture contract or explicitly record an approved deviation.
