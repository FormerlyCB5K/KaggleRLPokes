# 04 — Training Plan (New Encoder)

## Purpose

Record the training decisions that accompany the generalized encoder
(`completed/02-observation-encoding.md`,
`completed/03-attack-ability-tagging.md`). The PPO loop
mechanics themselves are unchanged; this covers model lifecycle and opponents.

## Model lifecycle

- The word count (16 → 23) and all four input MLPs change, which **breaks existing
  checkpoints**. The model is **retrained from scratch** — no warm-starting, no
  weight migration. Old checkpoints are abandoned (keep them on disk for reference
  until the new model beats the old one head-to-head).

## Opponent pool

Training samples one opponent per episode from a pool, replacing pure self-play:

- **Our previous agents**: the rules-based Ceruledge agent, Clefable MCTS, Alakazam,
  Lucario baseline (whichever run in the training harness).
- **External agents**: a couple of agents downloaded from elsewhere (e.g. public
  Kaggle competition submissions).
- Self-play snapshots may be mixed in via the existing opponent-swapping pattern.

The pool is the whole point of the generalized opponent encoding — the model must
see decks other than Ceruledge during training.

## Out of scope

- Changes to PPO hyperparameters, reward shaping, or the training loop itself.
- Curriculum / league mechanics (pool sampling is uniform for now).

## Open questions

- Which external agents to download, and from where (public Kaggle notebooks are the
  likely source). Resolve before the first full training run.
- Pool sampling weights (uniform vs. skewed toward stronger opponents).
