# Project Memory

Last refreshed: 2026-07-12

## Purpose

This repository explores agents for a Pokemon TCG Pocket Kaggle competition. It includes
rules-based agents, evolutionary tuning, supervised value-network work, submission
builders, and a reinforcement-learning policy centered on the Ceruledge deck.

## Current focus

The most developed active track is `Ceruledge-RL/`. Its current phase is the multi-agent
opponent pool described by `Ceruledge-RL/specs/09-opponent-pool.md` and split into specs
`09a` through `09e`. The active-spec index is `Ceruledge-RL/specs/README.md`.

The opponent-pool phase covers:

- collision-safe opponent registration/loading and deck resolution;
- side-aware episode dispatch and deck selection;
- weighted per-episode opponent sampling and CLI configuration;
- startup validation and deployment of all required agent folders; and
- per-opponent metrics and plots.

Some related code and tests already exist (`opponents.py`, `test_dispatch.py`, and
`test_pool.py`), so confirm implementation status against each active spec before
assuming a subsection is unfinished or complete.

## Ceruledge RL architecture snapshot

- The policy pilots the fixed Ceruledge deck but observes arbitrary opponent decks with
  a generalized opponent Pokemon representation.
- A state contains 23 logical transformer words: 9 friendly board slots, 9 opponent
  board slots, 4 friendly card-zone words, and 1 global word.
- Source widths are 19 friendly features, 75 opponent features, 16 zone features, and
  24 global features. Each is projected to width 64.
- The model is a two-layer, two-head actor-critic transformer with attention pooling and
  19 broad Stage 1 action categories.
- Stage 2 uses dot-product candidate scoring for targets and follow-up selections.
- Important current limitation: PPO directly trains Stage 1 only; Stage 2 target/STOP
  choices do not receive their own policy-gradient objective.
- Checkpoints from the older 16-word layout are incompatible with the current 23-word
  architecture and require a fresh training run.

Full details and accepted limitations are in `Ceruledge-RL/MODEL-ARCHITECTURE.md`.

## Important files

- `Ceruledge-RL/train.py` — PPO training loop and CLI.
- `Ceruledge-RL/model.py` — actor-critic transformer.
- `Ceruledge-RL/features.py` — observation encoding.
- `Ceruledge-RL/actions.py` — action translation and candidate selection.
- `Ceruledge-RL/opponents.py` — opponent registry/loading.
- `Ceruledge-RL/opponent_tags.py` — generalized opponent capability tags.
- `Ceruledge-RL/stat_bakes.py` — effective live stat modifiers.
- `Ceruledge-RL/effect_features.py` — effect extraction/features.
- `Ceruledge-RL/card_data.py` — card data support.
- `Ceruledge-RL/specs/` — current and completed implementation contracts.
- `Ceruledge-RL/old/` — historical/deferred material only.
- `cleanup-baselines/ceruledge-rl-phase0-2026-07-12/` — preserved phase-zero
  baseline artifacts and integrity/test records.

## Other project areas

- `Ceruledge-Agent/`, `Clefable-Agent/`, and `Alakazam-Agent/` contain rules-based agents.
- `Evo-V2/` contains evolutionary weight tuning and its latest visible output.
- `SupervisedValueNetwork/` contains supervised value-network training work.
- `Lucario-Baseline/` contains a baseline agent.
- `build_submission_*.py` and `Submissions/` contain packaging scripts and artifacts.
- `cg_download/` contains the local game/simulation bindings and native libraries.

## Known cautions

- The worktree was already heavily modified and contained many untracked files when
  this memory was created. Preserve unrelated user work and inspect status before edits.
- Large PDFs, archives, native libraries, submissions, and generated outputs are present.
  Avoid broad scans or rewrites of binary/generated artifacts.
- `Ceruledge-RL/deck.csv` has been documented as outdated for some architecture-level
  deck counts; use current code/spec contracts as the authority.
- Text from some older files may display mojibake depending on console encoding. Do not
  mechanically rewrite those files merely to normalize display encoding.

## Current validation state

Historical completed specs and the phase-zero baseline report passing focused tests and
live smoke checks. No fresh validation suite was run when this memory file was created.
Consult `cleanup-baselines/ceruledge-rl-phase0-2026-07-12/` for the preserved baseline,
then run checks appropriate to any new change.

## Next handoff

Before continuing the opponent-pool phase, compare specs `09a`-`09e` with the current
implementation and tests, mark only verified sections complete, and identify the first
remaining acceptance criterion. Record real training/evaluation runs in
`docs/experiments.md`.

