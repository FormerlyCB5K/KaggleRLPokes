# Ceruledge-RL Architecture Handoff

Purpose of this document: summarize the current PPO agent architecture at a high
level so a new session can discuss **generalizing it to other decks/matchups**
without re-reading the whole codebase. Everything lives in `Ceruledge-RL/`.

## Context

- Kaggle Pokémon TCG AI Battle Challenge. The game engine is a C library
  (`cg_download/`) driven turn-by-turn: `battle_start(deck, deck)` →
  loop of `battle_select(list[int])` → `battle_finish()`.
- Each observation carries `obs.select.option` — a flat list of legal options
  for the current decision context (`MAIN`, `TO_HAND`, `DISCARD`, `SWITCH`,
  `SETUP_*`, etc.). The agent's entire job is returning indices into that list.
- Engine constraint discovered the hard way: the C library **cannot run in
  child processes** (fork or spawn both fail). Episode collection is strictly
  sequential, single-process. Don't re-attempt multiprocessing.

## Big picture

A single ~80K-param actor-critic network plays the Ceruledge deck via
**two-stage action selection**, trained with PPO against a configurable
opponent (random / rules-based / frozen self-play copy).

```
observation
    │  features.py: extract_features()
    ▼
16 "words":  12 Pokémon slots + 3 card zones + 1 global    (variable-width inputs
    │        (12 feats)        (16 feats)     (14 feats)    → shared D_MODEL=64)
    │  per-type input MLPs  →  + word-type embedding (8 types)
    ▼
2-layer Transformer encoder (d=64, 2 heads, FF=128, pre-norm)
    │
    ├── words  (16, 64)      — per-slot vectors, reused by Stage 2
    └── pooled (64,)         — attention-weighted pooling (learned query)
            │
            ├── Stage 1 head: Linear(64 → 19 action logits)  + legal-action mask
            ├── Value head:   Linear(64 → 1)                 (PPO critic)
            └── Stage 2:      dot-product scoring of candidate vectors
                              against `pooled`, with a learned STOP token
                              for variable-count selections
```

**Stage 1** picks *what kind* of action (play card X, attach fire, attack,
retreat, pass…) from a fixed 19-action vocabulary, masked to legal actions.
**Stage 2** picks *the target(s)* — which bench slot to attach to, which cards
to fetch from deck, whom Boss's Orders drags up — by dotting `pooled` against
candidate vectors. Candidates come from two sources:

- **Board targets** → the post-transformer word vector of that slot
  (word layout: 0 = our active, 1–5 our bench, 6 opp active, 7–11 opp bench).
- **Pile cards** (deck/discard/hand searches) → `pile_mlp(one-hot-ish 16-vec)`
  via `encode_card_as_zone()` + `model.encode_pile_candidate()`.

Variable-count picks (e.g. "up to 3 cards") append a learned STOP token and
select sequentially until STOP wins.

## Input representation (features.py)

- **Pokémon slot (12 floats):** 5-dim species one-hot + hp_max, hp_curr,
  fire-energy, fighting-energy, retreat cost, attack damage, can_attack —
  all normalized by deck-specific constants (e.g. HP / 270).
- **Zone (16 floats):** for hand / discard / prizes — count of each of the
  deck's 15 unique cards normalized by its deck count, + 1 "is_unknown" flag.
  Prize contents are *inferred* by `GameStateTracker` (full deck − everything
  seen), not observed.
- **Global (14 floats):** prize counts, deck/hand sizes, turn info, plus
  hand-crafted deck strategy signals (Solrock+Lunatone combo flag, energy in
  hand, attacker count, supporter-used, Lunatone-ability-used).

## Training loop (`train.py`)

- **PPO**, CleanRL-style: GAE(γ=0.99, λ=0.95), clipped surrogate (ε=0.2),
  clipped value loss, entropy bonus (0.01), 4 epochs/update, Adam 3e-4,
  grad-norm clip 0.5. Typical batch: 128 episodes/update.
- Only **Stage 1 MAIN decisions** are PPO-trained (stored `Step` = features,
  action, log-prob, value, mask). Stage 2 and sub-selection contexts run
  greedy and get **no direct policy gradient** — they improve only through the
  shared encoder. Known limitation; see `PPO_AUDIT.md`.
- Per-step legal-action masks are stored and re-applied during the update so
  old/new log-probs live in the same masked distribution.
- Exploration: stochastic softmax sampling at Stage 1 (recommended for PPO);
  epsilon-greedy also available.
- Optional prize-shaping reward (`--prize-reward`, edge-triggered on prize
  count drops, ≤0.06/episode at 0.01).
- Episode collection on CPU (model is moved to CPU for rollout, to GPU only
  for the batched update — avoids device mismatches in Stage 2 helpers).
- Opponents: `random` | `rules` (imports `Ceruledge-Agent/main.py`, hard-fails
  at startup if not deployed) | `self` (frozen copy refreshed every N updates).
- wandb logging plus atomic per-update checkpointing and `--resume`
  (model+optimizer+counter+epsilon+histories+wandb run id) for SLURM
  self-requeue. Phase 4 consolidated local and cluster behavior in `train.py`.

## File map

| File | Role |
|---|---|
| `model.py` | Network, action vocabulary constants, Stage 2 scoring |
| `features.py` | Card constants, deck list, observation → tensors, prize inference |
| `actions.py` | Option classification (`build_action_map`), Stage 2 handlers per context |
| `train.py` | Canonical local/cluster PPO trainer with checkpoint/resume |
| `random_agent.py` | Uniform-random legal opponent |
| `submit-batch-ceruledge-ppo.sh` | SLURM script (6h wall, self-requeue + resume) |
| `PPO_AUDIT.md` | Earlier audit of PPO correctness/limitations |

## What is deck-specific vs. deck-agnostic (the generalization question)

**Already deck-agnostic:**
- The transformer core, word-type embeddings, attention pooling, value head.
- The Stage 2 dot-product mechanism + STOP token (works for any candidate set).
- The whole PPO/GAE/checkpoint/wandb machinery and engine plumbing.
- The 12-slot board layout and 3-zone structure (universal to PTCG).

**Hard-coded to the Ceruledge deck (would need redesign per deck):**
1. **Card constants** — 15 card IDs, `DECK_CARDS`, `DECK_COUNTS`, `FULL_DECK`.
2. **Zone vectors are indexed by deck slot** — 15 dims, one per unique card in
   *this* deck. A different deck changes the meaning of every dimension.
3. **Pokémon features** — 5-species one-hot; HP/damage/energy-requirement
   lookup tables; Ceruledge's discard-scaling damage formula baked in.
4. **Stage 1 vocabulary** — 13 of 19 actions are literally "play <named
   card>"; attach actions assume exactly fire+fighting; one bespoke ability
   action (Lunatone). `_CARD_TO_ACTION` in actions.py maps IDs → actions.
5. **Global features** — several are deck-strategy heuristics (Sol/Luna combo,
   fire/fighting counts, "attacker" identity).
6. **Setup heuristics** — `_setup_active`/`_setup_bench` preference orders.
7. **Stage 2 effect handling** — e.g. Boss's Orders recognized by card ID to
   pick opponent-bench candidates.

**Directions previously discussed for generalization** (see memory note
"SVN v2 Architecture" from the supervised-value-network sibling project):
replace card-identity one-hots/slots with **attribute vectors** (type, HP,
stage, energy cost, effect class, damage, …) so any card maps into a shared
feature space; then Stage 1 could shrink to generic verbs (PLAY / ATTACH /
ATTACK / ABILITY / RETREAT / PASS) with Stage 2 doing all card discrimination —
it already scores arbitrary candidate vectors, so it's the natural place for
deck-independence. The open design questions: attribute schema per card type
(Pokémon / Trainer / Energy), how to encode card *effects*, and whether zone
vectors become bags of attribute embeddings instead of per-card counts.

## Current status / known issues

- Training runs verified end-to-end locally vs all three opponent types.
- Untrained policy: ~50% vs random, ~10% vs rules agent.
- Rules opponent occasionally emits an illegal option index; `collect_episode`
  catches the engine's `IndexError` and substitutes a random legal move
  (logged design decision, not a fix of the rules agent itself).
- Cluster deploys must copy `Ceruledge-Agent/` (main.py + deck.csv) as a
  *sibling* of `Ceruledge-RL/` — paths are resolved relative to the files,
  case-sensitive on Linux. The SLURM cluster requires `#SBATCH --time`.
