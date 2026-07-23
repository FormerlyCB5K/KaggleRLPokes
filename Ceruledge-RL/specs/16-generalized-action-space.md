# 16 — Generalized Action Space + POC Model + Imitation Learning

**Status: in progress, 2026-07-22.**

## What this is

A deck-agnostic action space (which legal engine options map to which policy decisions)
paired with a new, from-scratch policy model that consumes spec 13a/15's 174-word
observation, and a first working training pipeline (imitation learning from recorded
ladder games) to actually produce a trained checkpoint.

This is the natural counterpart to specs 11-15, which generalized the *observation* side
(any-deck Pokemon/zone encoding, live-engine adapter). Nothing before this consumed that
observation in a model — spec 15 explicitly left "packing `list[Word]` into model input
tensors... or any SVN v2 model code" out of scope. This spec builds that model.

## Why not reuse the existing Ceruledge-RL policy

`Ceruledge-RL/actions.py` + `model.py` (what `train.py` actually runs today) are
Ceruledge-specific top to bottom: 19 hardcoded per-card Stage-1 actions
(`ACTION_PLAY_CERULEDGE`, `ACTION_ATTACH_FIRE`, ...), and `features.py` underneath them
bakes in Ceruledge's own stat dimensions and fixed 60-card deck. That pipeline is left
completely untouched by this spec — it keeps training exactly as it does today. This spec
builds a second, independent pipeline on top of the deck-agnostic `Imitation-Learning/
observation/` package instead.

## Scope (v1)

- A verb classification of every legal `obs.select.option` entry, driven by the engine's
  own `OptionType`/`AreaType` vocabulary — no hardcoded card IDs anywhere (see 16a).
- A tensor-packing layer: `Word` (spec 13a/15's output) -> fixed-width float vectors,
  per `Word.kind` (see 16b).
- A policy model: per-kind Linear embed -> role embedding -> small Transformer -> attention
  pool -> Stage 1 verb head + Stage 2 candidate scoring (see 16b).
- An imitation-learning data pipeline over `Imitation-Learning/Top-ladder-data/*.zip`
  (real recorded games, genuinely diverse non-Ceruledge decks, real chosen actions) and a
  training loop that produces a checkpoint (see 16c).
- Explicit non-goal-for-now: precision. Architecture widths/depths are placeholders
  (`D_MODEL=128`, 2 heads, 2 layers) chosen to get a working proof of concept, not tuned.

## Explicitly out of scope

- Self-play / PPO fine-tuning on top of the IL checkpoint (a real follow-up once IL
  produces a sane baseline).
- Registering the resulting model as an opponent-pool member or wiring it into
  `Ceruledge-RL/train.py` in any way.
- Making `Ceruledge-RL`'s own `PrizeTracker`/`GameStateTracker` deck-agnostic (irrelevant
  here — this pipeline never uses them; deck/prize state comes straight from
  `live_adapter.build_game_state`, which already handles this generically for arbitrary
  decks per spec 15).
- `SETUP_ACTIVE_POKEMON`/`SETUP_BENCH_POKEMON` decisions (no verb/candidate scoring;
  out of scope same as Track A).
- Hyperparameter tuning, architecture search, or performance optimization of the
  transformer body.

## Success criteria

- Given a real recorded `cg_download.api.Observation` + our_idx, the action-classification
  module (16a) correctly identifies which verb (or, for sub-selection contexts, which
  generic candidate list) the recorded `action` belongs to, across arbitrary decks in
  `Top-ladder-data` — not just Ceruledge.
- The model (16b) runs a forward pass on real `build_observation()` output without shape
  errors or NaNs.
- The training loop (16c) runs end-to-end on real `Top-ladder-data` episodes and produces
  a saved checkpoint, with move-prediction accuracy on held-out episodes clearly better
  than a random/majority baseline.

## Components

- [`16a-action-classification.md`](16a-action-classification.md) — verb vocabulary +
  universal per-`OptionType` candidate resolution (covers every `SelectContext`, not just
  the handful Track A implemented).
- [`16b-model-architecture.md`](16b-model-architecture.md) — tensor packing, transformer
  body, Stage 1/Stage 2 heads.
- [`16c-imitation-learning.md`](16c-imitation-learning.md) — data extraction, label
  construction, loss, training loop.

## Key decisions

1. Stage 1 verbs are derived directly from the engine's own `OptionType` enum
   (`SelectType.MAIN`'s own docstring lists exactly: PLAY, ATTACH, EVOLVE, ABILITY,
   DISCARD, RETREAT, ATTACK, END — 8 verbs), not a hand-picked vocabulary. All card-specific
   discrimination happens in Stage 2.
2. Verb classification generalizes for free to every `SelectContext` the engine defines
   (48+ as of this session) by keying candidate-embedding shape on `OptionType` (17 values)
   rather than writing per-`SelectContext` handlers — `SelectContext` only matters for
   min/max-count semantics, never for how a candidate is encoded.
3. Compound candidates (ATTACH/EVOLVE: a card + a target Pokemon in one option) score via
   concat(card_embedding, target_embedding) + a small learned projection, not plain sum or
   sequential picking — chosen for information-preservation (a joint pair score beats a
   greedy card-then-target factorization).
4. Architecture precision is explicitly deprioritized for v1: `D_MODEL=128`, 2 attention
   heads, 2 transformer layers, `norm_first=True` (reusing Track A's own proven fix — plain
   post-norm produced NaN at random init there), single Linear (no hidden layer) per word
   kind for the embed step.
5. Training path: imitation learning first, from real recorded ladder games (which already
   contain both the `observation` and the actual chosen `action` per decision — confirmed
   by inspecting `Top-ladder-data/7-12/*.zip` directly). Self-play RL fine-tuning is a
   follow-up spec once IL produces a working baseline. No checkpoint-migration path is
   needed since nothing existed before this to migrate from.
6. This is a second, independent pipeline living alongside (not replacing or modifying)
   `Ceruledge-RL/actions.py`/`model.py`/`train.py`, which continue running unchanged.

## Open questions

- None currently blocking; architecture/training hyperparameters are intentionally
  placeholder-quality per the confirmed v1 scope.
