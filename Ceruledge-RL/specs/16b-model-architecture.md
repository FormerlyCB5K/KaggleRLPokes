# 16b — Model Architecture

## Purpose

Consume spec 13a's 174-`Word` observation and 16a's action classification, and produce
Stage 1 verb logits + Stage 2 candidate scores. First working version — precision is
explicitly deprioritized (confirmed with the user): placeholder widths/depths, single
Linear layers instead of MLPs, "just needs to work as a proof of concept."

## Tensor packing (`Word` -> flat float vectors)

`Word.static` is `PokemonStatic | TrainerEnergyStatic | None`; `Word.live` is a `dict |
None` whose shape depends on `Word.kind`. Nothing before this spec converts these into
tensors (spec 15 explicitly left this out of scope). Packed per `Word.kind`, each into its
own fixed-width content vector — zero-filled wherever a field doesn't apply to that kind:

| `Word.kind` | Content | Width | Why |
|---|---|---|---|
| `zone_card` | `PokemonStatic` fields (`hp_max, type_onehot(10), rule_onehot(3), retreat_cost, weakness_onehot(9), resistance_onehot(9), tag_block(201)`) ++ `TrainerEnergyStatic` fields (`tag_block(54)`) | 234 + 54 = 288 | a zone slot (`our_deck`/`our_hand`/etc.) can hold either card class; both halves are computed, only one is ever nonzero for a given slot |
| `board_pokemon` | `PokemonStatic` (234) ++ flattened `live` dict in fixed key order (`hp_curr(1), attached_energy_counts(11), special_energy_id(10), evolved_from(3, zero-padded card_id list), new_in_play(1), special_conditions(5), attacks_survivable(1), attack_damage(2, zero-padded to spec 11a's fixed 2-attack-row convention), attack_hits_opponent(1)` = 35) | 234 + 35 = 269 | board Pokemon are always Pokemon-class, never Trainer/Energy |
| `stadium` | `TrainerEnergyStatic.tag_block` (stadiums are Trainer-class per `build_any_static`) | 54 | |
| `global` | `turn_number` (normalized, `/50`, clipped to 1.0) | 1 | only field `encoder.py` ever puts in a `global` word's `live` dict |
| `pool` / `pad` | none | 0 | `pool` gets a learned constant embedding (see below); `pad` is masked out of attention entirely, so its content is irrelevant |

`card_index` (present on both static dataclasses) is deliberately **excluded** from the
packed vector — same "no card ID, attributes only" principle already locked for this
project's value-network work (generalization to unseen cards is the whole point).

Explicitly not hand-verified digit-by-digit against the dataclasses at spec-writing time
(per the user's "no need to be super precise" instruction) — the packing code computes
each width from the dataclass/dict shape directly (e.g. `len(PokemonStatic.type_onehot)`)
rather than hardcoding the numbers above, so a future field addition can't silently
desync the model's input width from this table.

## Model body

```
D_MODEL = 128
N_HEADS = 2
N_LAYERS = 2
```

- One `nn.Linear(content_width_for_kind, D_MODEL)` per kind (`zone_card`: 288->128,
  `board_pokemon`: 269->128, `stadium`: 54->128, `global`: 1->128) — single linear layer,
  no hidden layer/activation, per the confirmed placeholder-precision scope.
- `pool` and `pad` words: learned constant `D_MODEL` vectors (`nn.Parameter`), no MLP.
- Role embedding: `nn.Embedding(10, D_MODEL)` — one row per `BoardRole`
  (`our_active/our_bench/opponent_active/opponent_bench`) and per zone name
  (`our_deck/our_hand/our_discard/our_prizes/opponent_discard`), plus one shared "none" row
  for `stadium`/`global`/`pool`/`pad` (`Word.role is None`). Added to the kind-embed output
  (same additive pattern as the project's prior SVN v2 design work, and as Track A's own
  type embedding).
- `nn.TransformerEncoder`, 2 layers, 2 heads, `norm_first=True` — reusing Track A's own
  proven fix (`Ceruledge-RL/model.py`; plain post-norm produced NaN at random init there).
  Attention mask: `Word.attention_masked` (PAD words) excluded, matching spec 13a.
- Attention-weighted pooling: a learned query vector, `softmax(words @ query)` weights,
  weighted sum -> `(D_MODEL,)` pooled vector. Same mechanism already used in this project's
  prior architecture work and in Track A's `CeruledgePolicy`.

## Heads

- **Stage 1**: `nn.Linear(D_MODEL, 8)` from the pooled vector -> one logit per verb (16a's
  8 MAIN-context verbs). Illegal verbs masked to `-inf` before softmax, same masking
  pattern as Track A.
- **Stage 2, board-target candidates** (`RETREAT`/`ATTACK`'s implicit source/`ABILITY`
  source, `ATTACH`/`EVOLVE`'s target half, any generic `CARD`-type option resolving to a
  board Pokemon): score = `dot(pooled, word_embedding)` using that candidate's own
  post-transformer embedding directly — no separate encoder needed, since every board
  Pokemon already has a contextual embedding from the same forward pass.
- **Stage 2, hand-card candidates** (`PLAY`, `ATTACH`'s card half, any generic `CARD`-type
  option resolving to a hand card): same mechanism — hand cards are already `zone_card`
  words (`our_hand`, `HAND_CAPACITY=20`) with their own post-transformer embeddings; no
  separate "pile candidate" pathway is needed the way Track A required one (Track A's
  board words didn't include hand cards at all).
- **Stage 2, `ATTACK` verb**: `nn.Linear(D_MODEL, 2)` off the acting Pokemon's own board
  word embedding -> a score per attack slot (0 or 1, spec 11a's fixed cheapest-first
  ordering) — not a candidate list needing separate per-attack embeddings, since both
  attacks' tags already live inside that one Pokemon's `Word`.
- **Stage 2, compound candidates** (`ATTACH`/`EVOLVE` card+target pairs): score =
  `nn.Linear(2*D_MODEL, 1)` applied to `concat(card_embedding, target_embedding)` — the
  locked interview decision (concat + small projection, not sum, not sequential picking;
  chosen for information-preservation of the joint card x target pair).
- **Stage 2, non-card candidates** (`NUMBER`/`YES`/`NO`/`SPECIAL_CONDITION`): small learned
  embeddings (`nn.Linear(1, D_MODEL)` for `NUMBER`'s literal value; `nn.Embedding(2,
  D_MODEL)` for `YES`/`NO`; `nn.Embedding(5, D_MODEL)` for `SpecialConditionType`), scored
  the same `dot(pooled, ...)` way as board/hand candidates.

## Data

Input: `list[Word]` (174, from `build_observation`), plus 16a's classified verb/candidate
structure for the current decision. Output: Stage 1 logits `(8,)`; Stage 2 scores
`(n_candidates,)` for whichever verb/context is active.

## Interfaces / seams

- Depends on 16a for *which* candidates exist and how they're resolved to a card/board
  reference; this file owns turning those references into vectors and scores.
- Depends on `Imitation-Learning/observation/encoder.py`'s `build_observation()` for the
  `list[Word]` input — no changes needed there.
- Feeds 16c (loss computation needs Stage 1 logits + Stage 2 scores for the recorded
  action's actual verb/candidate).

## Out of scope

- Any tuning of `D_MODEL`/depth/heads, or replacing single Linear layers with real MLPs —
  explicitly deferred past this v1.
- A value head (not needed for imitation learning; add when self-play RL fine-tuning
  becomes its own spec).

## Open questions

- None currently blocking.
