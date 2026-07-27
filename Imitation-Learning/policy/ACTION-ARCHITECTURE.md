# Action Space Architecture

This document describes the action space only — how a legal-move list from the engine
becomes a scored decision. It does not cover the observation encoder (see
`Imitation-Learning/observation/OBSERVATION-ARCHITECTURE.md`) or the imitation-learning data
pipeline (spec 16c). It corresponds to `Imitation-Learning/policy/action_space.py` (spec 16a),
`packing.py`/`layout.py`/`model.py`/`scoring.py` (spec 16b), which implement
`Ceruledge-RL/specs/16-generalized-action-space.md`, `16a-action-classification.md`, and
`16b-model-architecture.md`.

This is the newer, any-deck action space. It is a different design from
`Ceruledge-RL/actions.py`/`model.py` (still what `Ceruledge-RL/train.py` actually trains
today), which hardcodes 19 per-card Stage-1 actions (`ACTION_PLAY_CERULEDGE`,
`ACTION_ATTACH_FIRE`, ...) specific to the Ceruledge 60-card deck. The two pipelines are
independent — this one is untouched by, and doesn't touch, that one.

## 1. Overview

### 1.1 Two-stage decisions

Every real decision the engine presents (`obs.select`) is handled in one of two shapes:

1. **Stage 1 — verb.** Only in `SelectContext.MAIN` (the top-level "what do you want to do
   this turn" decision). Exactly 8 verbs, taken directly from `SelectType.MAIN`'s own
   documented `OptionType` vocabulary: `PLAY, ATTACH, EVOLVE, ABILITY, DISCARD, RETREAT,
   ATTACK, END`. The model scores all 8 from one pooled observation vector; illegal verbs
   (not present in `obs.select.option` this turn) are masked to `-inf` before softmax.
2. **Stage 2 — candidate.** Every context, including MAIN once a verb is chosen and every
   non-MAIN sub-selection (choosing a target, a discard, a search hit, a count, ...). A flat
   list of candidates, each scored independently against the pooled state (or, for compound
   candidates, against each other).

### 1.2 Candidate shape is a function of `OptionType`, never `SelectContext`

This is the load-bearing simplification of the whole design. The engine defines 48+
`SelectContext` values (`TO_BENCH`, `HEAL`, `DEVOLVE`, `DAMAGE_COUNTER`,
`SWITCH_ENERGY_CARD`, ...), but only 17 `OptionType` values, and a candidate's *structure*
(what it references, how it's embedded) depends only on which `OptionType` it is — a `CARD`
option is resolved the same way whether the surrounding `SelectContext` is `TO_HAND` or
`DEVOLVE` or something the classifier has never special-cased before. `SelectContext` only
changes *how many* candidates must be picked (`minCount`/`maxCount`) and *why*
(`obs.select.effect`), never what a candidate looks like.

Practical effect: one generic resolver (§2.2) covers every `SelectContext` the engine
defines, not just the handful (`TO_HAND`, `DISCARD`, `SWITCH`, `TO_ACTIVE`,
`DISCARD_ENERGY_CARD`, `ACTIVATE`) `Ceruledge-RL/actions.py` hardcoded — everything else in
that old pipeline silently fell into a random-choice fallback.

### 1.3 No card ID is ever hardcoded

Classification reads only `cg_download.api`'s own `OptionType`/`AreaType`/`SelectContext`
enums plus the live `Observation` — never a specific card's identity. The one place card
*data* (not the engine) is consulted is a generic `subtype == "Supporter"` check, used for
once-per-turn bookkeeping fed to the model as a feature (not for legality — the engine's own
`state.supporterPlayed` already keeps illegal repeat-Supporter options out of
`obs.select.option`). This replaces `Ceruledge-RL/actions.py`'s hardcoded
`_SUPPORTER_IDS = {Boss_Orders, Explorers_Guidance, Carmine}` with a check that works for any
card. Boss's-Orders-style opponent-vs-own-board targeting likewise falls out for free from
every `CARD` option's own `playerIndex`/`area` — no `effect == Boss_Orders` special case
needed.

### 1.4 Compound candidates

`ATTACH` and `EVOLVE` options each carry two references in one option: a hand card and a
target board Pokémon. Both halves are resolved independently (§2.3) and scored together as a
pair — `concat(card_embedding, target_embedding)` through a small learned projection, not a
plain sum and not sequential (card-then-target) picking. This was a deliberate choice for
information-preservation: a joint pair score can represent "this card is good specifically
*with* this target" in a way a factored sum or greedy two-step pick cannot.

### 1.5 Resolution is best-effort, not exhaustive

Some candidates reference cards or positions `GameState`/the observation don't model at all
(the opponent's hand or deck — a documented limitation carried over from spec 15) or fall
into rare `AreaType`s (`ENERGY`, `PRE_EVOLUTION`, `PLAYER`) this module leaves unresolved.
These candidates fall back to a zero embedding rather than raising — a real, accepted
precision gap for the long tail, not silent wrongness for the common case.

### 1.6 What every score is actually computed against

All Stage 2 scoring reuses the same post-transformer word embeddings the observation encoder
already produced — no separate "candidate encoder" exists. A candidate that resolves to a
specific board Pokémon or zone card gets scored as `dot(pooled_state, that_word's_own_
contextual_embedding)`. This is why classification's real job (§2.2) is narrower than it
sounds: it doesn't need to build a new representation for a card, only to say *which existing
word* in the 174-word sequence a candidate points at.

### 1.7 Out of scope

`SETUP_ACTIVE_POKEMON`/`SETUP_BENCH_POKEMON` decisions are not scored at all (no verb, no
candidates — matches the old pipeline's own scope boundary). This module never enforces
legality itself; `obs.select.option` is already the engine's own filtered legal list.

---

## 2. Feature-by-feature tables

### 2.1 Stage 1 verb vocabulary (`VERBS`, MAIN context only)

| Verb (`OptionType`) | Index | What it represents |
|---|---|---|
| `PLAY` | 0 | Play a card from hand |
| `ATTACH` | 1 | Attach a card (Energy/Tool) from hand to a board Pokémon |
| `EVOLVE` | 2 | Evolve a board Pokémon using a card from hand |
| `ABILITY` | 3 | Use a Pokémon's Ability |
| `DISCARD` | 4 | Discard as a main action (rare direct case; most discarding is a sub-selection, §2.2) |
| `RETREAT` | 5 | Retreat the Active Pokémon |
| `ATTACK` | 6 | Use one of the Active Pokémon's attacks |
| `END` | 7 | End the turn |

Scored by `nn.Linear(D_MODEL, 8)` off the pooled observation vector; illegal verbs (absent
from this turn's `obs.select.option`) masked to `-inf` before softmax.

### 2.2 Stage 2 candidate resolution, by `OptionType`

| `OptionType` | What it references | How it's resolved | How it's scored |
|---|---|---|---|
| `CARD` | One card, via `area`/`index`/`playerIndex` | Generic resolver over every `AreaType` (`DECK, HAND, DISCARD, ACTIVE, BENCH, PRIZE, STADIUM, ENERGY, TOOL, PRE_EVOLUTION, PLAYER, LOOKING`) | `dot(pooled, word_embedding)` — board word if it resolved to a board position, else zone-card word |
| `TOOL_CARD` | A Tool attached to a Pokémon (`area`/`index`/`playerIndex`/`toolIndex`) | Resolves the owning Pokémon, then indexes its `tools` list | `dot(pooled, board_word_embedding)` of the *owning Pokémon* — the Tool card itself has no separate word |
| `ENERGY_CARD` | An Energy card attached to a Pokémon (`...`/`energyIndex`) | Same as `TOOL_CARD`, indexes `energyCards` | `dot(pooled, board_word_embedding)` of the owning Pokémon |
| `ENERGY` | One attached energy *unit*, not a specific card (same card_id can back multiple units) | Owning Pokémon resolved via `board_ref`; no card identity | `dot(pooled, board_word_embedding)` of the owning Pokémon |
| `PLAY` | A hand card (wire format carries only `index`, no `area`) | Resolved directly against `our_hand`, bypassing the generic `area`-based resolver (which would silently fail — `PLAY` has no `area`) | `dot(pooled, our_hand zone-card word embedding)` |
| `ATTACH` (compound) | Card half: a hand card. Target half: a board Pokémon (`inPlayArea`/`inPlayIndex`) | Card via `HAND` area; target always the acting player's own board | `compound_score`: `Linear(concat(card_embedding, target_embedding))` (§2.5) |
| `EVOLVE` (compound) | Same shape as `ATTACH` | Same as `ATTACH` | Same as `ATTACH` |
| `RETREAT` | A board Pokémon (`area`/`index`) | Generic board resolver | `dot(pooled, board_word_embedding)` |
| `DISCARD` | A card, in-hand or in-play (`area`/`index`) | Generic resolver (card + optional board ref) | `dot(pooled, word_embedding)` |
| `ABILITY` | A board Pokémon (`area`/`index`) | Generic board resolver | `dot(pooled, board_word_embedding)` |
| `ATTACK` | One of the acting Pokémon's own two attack slots (`attackId`) | No card resolution — both attacks already live inside the acting Pokémon's own `Word` tag block. `attackId` (an opaque engine ID, not a 0/1 slot) is mapped to spec 11a's cheapest-first slot via a self-learning cache (§2.9) | `Linear(D_MODEL, 2)` off the acting Pokémon's own board-word embedding → one logit per slot, indexed by the resolved slot |
| `SKILL` | An ordering choice over a `cardId`/`serial` | `serial` matched against a known board Pokémon if possible, else treated as a bare card reference; falls back to a best-effort search of our own always-visible zones (hand, discard) since `SKILL` carries no `area` | `dot(pooled, word_embedding)` if resolved, else zero embedding |
| `NUMBER` | A literal count to pick | The number itself, as a scalar (`candidate.literal`) | `Linear(1, D_MODEL)` embedding of the literal, then `dot(pooled, ·)` |
| `YES` | Fixed binary choice | No card | `nn.Embedding(2, D_MODEL)` row 0, then `dot(pooled, ·)` |
| `NO` | Fixed binary choice | No card | `nn.Embedding(2, D_MODEL)` row 1, then `dot(pooled, ·)` |
| `SPECIAL_CONDITION` | One of 5 `SpecialConditionType` values | The enum value, as `candidate.literal` | `nn.Embedding(5, D_MODEL)` row, then `dot(pooled, ·)` |
| `END` | No sub-data | N/A (only ever a Stage 1 verb, not a Stage 2 candidate) | N/A |

### 2.3 `Candidate` structure

Every resolved option becomes one `Candidate`, regardless of `OptionType` — unused fields for
a given type simply stay at their default.

| Field | Type | What it holds |
|---|---|---|
| `option_index` | int | Index into `obs.select.option` this candidate came from |
| `card_id` | int \| None | Resolved card identity, if any |
| `zone_role` | str \| None | Which of `GameState`'s zone-card arrays (`our_hand`, `our_deck`, `our_discard`, `opponent_discard`, `our_prizes`) `card_id` should be looked up in; `None` if the card lives somewhere `GameState` doesn't model (e.g. opponent hand/deck) |
| `occurrence` | int | Disambiguates duplicate copies of the same `card_id` in one zone (e.g. two Fire Energy in hand) — how many same-`card_id` items precede this one in the zone's raw pre-sort order, which lines up with the same index among the sorted zone words |
| `board_ref` | `BoardRef` \| None | Resolved board position (`role` + `slot`), if this candidate references a board Pokémon |
| `attack_slot` | int \| None | Resolved attack slot (0 or 1), `ATTACK` candidates only |
| `literal` | float \| None | The literal value for `NUMBER`/`YES`/`NO`/`SPECIAL_CONDITION` candidates |
| `target` | `Candidate` \| None | For compound `ATTACH`/`EVOLVE` candidates only — the target board Pokémon, as its own (partial) `Candidate` |

`BoardRef` itself is just `{role: "our_active" | "our_bench" | "opponent_active" |
"opponent_bench", slot: int}` (`slot` always 0 for the two `*_active` roles).

### 2.4 Word content packing (what a candidate's `dot(pooled, ·)` is actually scored against)

Every board/zone candidate's embedding *is* the corresponding observation word's own
post-transformer embedding — no separate candidate encoder exists. Recap of packed content
widths (full field-level detail lives in `OBSERVATION-ARCHITECTURE.md` §2); `card_id`/
`card_index` are always excluded from packed content, same attribute-only principle as the
rest of this project's card representations:

| `Word.kind` | Packed content | Width |
|---|---|---|
| `zone_card` | `PokemonStatic` fields ++ `TrainerEnergyStatic` fields (both halves always computed; only one is ever nonzero per real slot, since a zone slot is either a Pokémon or a Trainer/Energy card) | 234 + 54 = 288 |
| `board_pokemon` | `PokemonStatic` fields ++ flattened live dict (`hp_curr, attached_energy_counts(11), special_energy_id(10), evolved_from(3), new_in_play, special_conditions(5), attacks_survivable, attack_damage(2), attack_hits_opponent`) | 234 + 35 = 269 |
| `stadium` | `TrainerEnergyStatic` fields (Stadiums are always Trainer-class) | 54 |
| `global` | 12 scalars — `turn_number`, `supporter_played`, our/opponent prize counts, our/opponent deck counts, our/opponent discard counts, opponent hand count, `item_locked`, `energy_attached_this_turn`, `turn_order`. Full field-level detail in `OBSERVATION-ARCHITECTURE.md` §2.8 | 12 |
| `pool` / `pad` | none — model supplies a learned constant embedding instead | 0 |

### 2.5 Role vocabulary

`nn.Embedding(10, D_MODEL)`, added to each word's kind-embedding output: 5 zone-name rows
(`our_deck, our_hand, our_discard, our_prizes, opponent_discard`) + 4 board-role rows
(`our_active, our_bench, opponent_active, opponent_bench`) + 1 shared `_none` row for any word
whose `role` is `None` (`stadium`, `global`, `pool`, `pad`).

### 2.6 Compound scoring (`ATTACH` / `EVOLVE`)

| Step | What happens |
|---|---|
| Card half | Resolved to a hand `zone_card` word embedding (or a zero vector if unresolved) |
| Target half | Resolved to a board `board_pokemon` word embedding via `candidate.target.board_ref` (or a zero vector if the option carried no legal target, which shouldn't normally happen but is handled defensively) |
| Score | `Linear(2·D_MODEL → 1)` applied to `concat(card_vec, target_vec)` — a single learned joint projection, not `card_score + target_score` |

### 2.7 Effect-conditioned sub-selections

Many sub-selections happen *because* of a triggering card (discarding for an Ultra Ball cost
vs. a Brilliant Blender cost shouldn't be scored identically). When `obs.select.effect.id` is
present, the pooled state is biased before scoring any candidate in that sub-selection:
`pooled' = pooled + effect_card_embedding` (plain additive conditioning, this project's
established pattern — mirrors `Ceruledge-RL/model.py`'s own `condition_on_effect`). The effect
card's embedding is built directly from its `card_id` via `encode_card_by_id`, independent of
whether that card currently occupies any word in the observation (e.g. a Trainer card that's
mid-resolution and not yet in the discard pile).

### 2.8 Variable-count selections (STOP token)

For sub-selections where `minCount < maxCount` (e.g. "discard up to 2 cards"), a learned STOP
embedding is scored the same `dot(pooled, ·)` way as every other candidate
(`model.stop_score`), appended as one extra trailing score. A sequential-picking caller can
stop selecting once STOP's score wins. This is model/scoring capability only — wiring it into
live sequential-pick inference is separate, not-yet-built RL-scope work.

### 2.9 Attack-slot resolution

`Option.attackId` is an opaque engine ID (real observed values look like 153, 154), not a
0/1 slot — mapping it to spec 11a's fixed cheapest-first attack-row convention requires
knowing the card's *other* attack ID(s) for comparison. Rather than a hardcoded per-card
table, a small in-memory cache (`_ATTACK_ID_ORDER: dict[card_id, list[attack_id]]`) learns
each card's ascending `attackId` order the first time multiple of its attacks appear together
as legal options in the same decision, and reuses that order on future decisions where only
one of that card's attacks happens to be legal. Falls back to slot 0 the first time a card's
attack is ever seen in isolation, before any ordering has been learned — a real, self-healing
precision gap rather than a hardcoded card list.
