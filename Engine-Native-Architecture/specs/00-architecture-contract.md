# 00 - Architecture Contract

Status: superseded provisional baseline, 2026-07-28.

> Do not implement from this file. It records the first-PDF baseline and is retained only
> for provenance. The active contract is
> [`01-implementation-decisions-and-deferrals.md`](01-implementation-decisions-and-deferrals.md),
> which incorporates v3 and the reported implementation handoff.

## 1. Sources of truth

The user-provided **Observation space and network architecture** overview is the design
source of truth, with one approved change: remove the learned card-ID embedding table and
do not replace it.

For runtime facts, legality, and card mechanics, use sources in this order:

1. the acting player's `cg_download.api.Observation`;
2. the engine's public enums and card/rules data;
3. the submitted 60-card deck, for information the acting player legitimately knows;
4. audited repository data only as validation evidence or a documented fallback when the
   engine does not expose required static information.

Existing repository trackers and feature encoders are not runtime dependencies of this
architecture.

## 2. Observation contract

One decision is packed into four contiguous blocks totaling 2,119 fields.

| Block | Fields | Contract |
|---|---:|---|
| Entity inputs | 1,160 | 40 entity slots, six parallel arrays |
| Deck summary | 300 | all 60 slots of the acting player's submitted deck |
| Match state | 18 | turn, Prize/zone counts, per-turn flags, effect remainder |
| Legal options | 641 | up to 64 engine-provided options plus option count |
| **Total** | **2,119** | fixed-width packed interface |

Categorical IDs may be stored in the packed interchange object, but they are embedding or
table-lookup indices, not continuous float features. The typed tensor interface must keep
categorical indices separate from normalized continuous inputs even if a serialized replay
format stores them in one flat numeric record.

### 2.1 Entity slots

There are 40 slots. Each slot contains:

| Field | Width |
|---|---:|
| card ID | 1 |
| role | 1 |
| live numerics | 24 |
| occupied mask | 1 |
| attached Tool ID | 1 |
| attached Special Energy ID | 1 |
| **Per slot** | **29** |

The 24 live numerics, in order:

1. is mine;
2. is active;
3. current HP / max HP;
4. current HP / 300;
5. max HP / 300;
6. damage taken / 300;
7. attached Energy count / 5;
8. attached Tool count / 2;
9. evolution stack depth / 2;
10. played this turn;
11. Poisoned or Burned, Active only;
12. Asleep, Paralyzed, or Confused, Active only;
13-24. attached Energy-unit counts for all 12 engine `EnergyType` values.

Roles follow the overview's ten-value vocabulary:

1. padding;
2. my Active;
3. my Bench;
4. opponent Active;
5. opponent Bench;
6. my hand;
7. deck summary;
8. match state;
9. readout;
10. Stadium in play.

The entity population is both players' Active and Bench Pokemon, the acting player's
visible hand, and the Stadium. Opponent hand and both decks are not entity populations.

The exact deterministic slot allocation, entity ordering, and behavior when hand plus
board occupancy exceeds 40 must be resolved and tested before the encoder is implemented.

### 2.2 Acting-player deck summary

All 60 submitted deck slots are represented:

- card ID: 60 categorical lookup indices;
- zone counts: `60 x 4`, ordered as `[hand, discard, in play, unknown]`, each divided by 4.

`unknown` combines the acting player's deck and Prize cards. It is intentionally not split
using hidden engine state or a Prize tracker.

Card ID is used only to retrieve the frozen static representation. It has no learned
identity embedding.

### 2.3 Match state

The 18 normalized fields, in order:

1. turn number / 30;
2. actions taken this turn / 20;
3. I went first;
4. Supporter already played this turn;
5. Stadium already played this turn;
6. Energy already attached this turn;
7. already retreated this turn;
8. my Prizes remaining / 6;
9. opponent Prizes remaining / 6;
10. my deck count / 60;
11. opponent deck count / 60;
12. my hand count / 12;
13. opponent hand count / 12;
14. my discard count / 30;
15. opponent discard count / 30;
16. damage counters still to place / 20;
17. Energy cost still to pay / 10;
18. a Stadium is in play.

Use the engine's current observation for these values. If a field is not available
directly, its derivation must be separately specified rather than silently tracked.

### 2.4 Legal options

Up to 64 entries are taken directly from `observation.select.option`.

Each option has:

- option type;
- card ID;
- target value expected by the engine;
- attack ID;
- entity pointer into the 40 entity slots, or a no-entity sentinel;
- live-option mask;
- four numerics: `[number, count, min selectable, max selectable]`.

One final scalar carries option count. The engine enumerates legality; the model only ranks
the live entries.

The vocabulary contains the overview's 17 option types:

`number`, `yes`, `no`, `card`, `tool card`, `energy card`, `energy`, `play`, `attach`,
`evolve`, `ability`, `discard`, `retreat`, `attack`, `end turn`, `skill`, and
`special condition`.

The entity pointer is a structural link, not a learned inference. Pointer construction must
be derived from each engine option and the same deterministic entity-slot map used by the
observation.

## 3. Frozen card knowledge

Card mechanics are encoded in frozen tables derived from engine rules/card data. The
tables are checkpoint inputs or reproducible build artifacts, not learned parameters.

### 3.1 Stat line

Each card's stat line is 79 fields:

- seven-way card type;
- seven flags: Basic, Stage 1, Stage 2, ex, Mega ex, Tera, ACE SPEC;
- HP / 300;
- 12-way Energy type;
- 12-way Weakness;
- 12-way Resistance;
- retreat cost / 5;
- two attack slots, each containing base damage / 300 plus 12 typed Energy costs;
- has-second-attack flag.

### 3.2 Effect descriptor

Every attack and ability uses the overview's shared 128-field descriptor:

| Segment | Width |
|---|---:|
| is ability | 1 |
| present | 1 |
| damage | 1 |
| target count | 1 |
| scope | 4 |
| typed cost | 12 |
| effect tags | 56 |
| gated | 1 |
| condition type | 24 |
| condition subject | 19 |
| comparator | 6 |
| name target | 1 |
| branch | 1 |
| **Total** | **128** |

The 56 effect tags and the overview's condition vocabularies are part of this contract.
They will be transcribed exactly into machine-readable ordered vocabularies and verified
against the engine before the table builder is considered complete.

A Trainer play-effect table of the same descriptor shape is required. Its exact placement
in the three effect slots of the static-card assembly is an open contract detail because
the overview names the fourth table but shows only attack 0, attack 1, and ability in the
assembly diagram.

### 3.3 Static card vector without card embedding

The approved assembly is:

```text
stat-line projection     32  <- frozen 79-field stat line
Prize value               1
attack 0 effect          48  <- frozen 128-field descriptor
attack 1 effect          48  <- frozen 128-field descriptor
ability/play effect      48  <- frozen 128-field descriptor
                       ----
                        177  -> learned Linear -> 224
```

The three effect descriptors share projection weights, as in the overview.

There is no learned card embedding. Card identity contributes only by selecting the
appropriate frozen mechanical rows.

## 4. Network contract

### 4.1 Entity assembly

Each occupied entity becomes a 224-wide token:

- static card vector;
- role embedding;
- projection of the 24 live numerics;
- projected static representation of its attached Tool;
- projected static representation of its attached Special Energy.

Tool and Special Energy gates are zero-initialized. A masked empty entity cannot affect
self-attention or downstream pooling.

### 4.2 Deck conditioning

Each of 60 deck slots combines:

- that card's static vector; and
- a projection of its four zone values.

Masked-mean pooling produces one deck vector. That vector produces a FiLM scale and shift
applied to every entity token.

### 4.3 Transformer sequence

The sequence is:

```text
40 entity tokens | deck token | match-state token | 3 registers | readout token
```

The encoder configuration is locked to:

- width 224;
- four layers;
- four heads;
- feed-forward width 448.

There is no positional encoding over Bench order. The three registers are learned scratch
tokens. The readout token is the global summary used by all heads.

### 4.4 Option scoring

Each legal option is encoded from:

- option-type embedding;
- the frozen-mechanics-derived static vector for its card;
- attack embedding projected from 32 fields;
- projection of four option numerics;
- the pointed entity's encoder output, or a learned no-entity vector.

Card ID does not have a learned embedding in option encoding. The option receives card
information only through the frozen mechanical description and its learned projections.

The policy score head consumes:

```text
[readout, option, readout * option]
```

through a two-layer network to one scalar. Softmax is taken only across live engine options.

A second head with the same input shape produces independent include/exclude probabilities
for multi-select prompts. A value head reads the readout token and predicts win probability.

## 5. Engine-first integration boundary

The production encoder should accept an engine observation and the acting-player identity.
It may additionally accept the submitted acting-player deck because that decklist is known
to its owner.

It must not require the existing repository's:

- `Ceruledge-RL.prize_check.PrizeTracker`;
- `Ceruledge-RL.features.GameStateTracker`;
- `Imitation-Learning.observation.encoder.GameState`; or
- `Imitation-Learning.observation.live_adapter`.

Engine data should be used for:

- board and attachment objects;
- HP, damage, status, and evolution information;
- zone counts and visible zone contents;
- once-per-turn flags;
- current selection context and remaining effect costs;
- legal options, option types, targets, counts, and masks.

The current public API has been checked against this requirement:

| Architecture input | Direct engine source |
|---|---|
| turn and actions this turn | `State.turn`, `State.turnActionCount` |
| turn order | `State.yourIndex`, `State.firstPlayer` |
| once-per-turn flags | `State.supporterPlayed`, `stadiumPlayed`, `energyAttached`, `retreated` |
| Stadium | `State.stadium` |
| board Pokemon | `PlayerState.active`, `PlayerState.bench` |
| HP and entered-play flag | `Pokemon.hp`, `maxHp`, `appearThisTurn` |
| Energy, Energy cards, Tools, evolution stack | `Pokemon.energies`, `energyCards`, `tools`, `preEvolution` |
| Active Special Conditions | the five `PlayerState` condition booleans |
| deck, hand, discard, and Prize counts | `PlayerState.deckCount`, `handCount`, `discard`, `prize` |
| acting player's visible hand | `PlayerState.hand` |
| effect-resolution remainder | `SelectData.remainDamageCounter`, `remainEnergyCost` |
| selection bounds and legal options | `SelectData.minCount`, `maxCount`, `option` |
| printed card stat line | `all_card_data()` / `CardData` |
| printed attacks and costs | `all_attack()` / `Attack` |

Face-down Prize entries are `None` in `PlayerState.prize`; their count is usable, their
identity is not. Opponent hand is likewise count-only because `PlayerState.hand` is `None`
for the opponent.

Minimal deterministic derivations may include:

- canonical entity-slot assignment;
- visible-count subtraction from the known submitted deck;
- per-copy deck-summary placement into the four observable zone buckets;
- mapping an option's engine references to an entity pointer;
- frozen static-table lookup.

These are encodings of observable engine facts, not a second game simulator.

## 6. Isolation and validation rules

- No runtime imports from the old observation or policy packages.
- No checkpoint migration from either existing architecture.
- New generated tables and checkpoints use versioned manifests with schema/vocabulary
  hashes.
- Focused tests must validate every packed width and field order.
- Replay tests must compare encoded values to the raw engine observation at sampled
  decisions.
- Hidden-information tests must prove that deck and Prize identities are never read from
  unavailable engine state.
- Option tests must prove that every live option is represented exactly once and that
  masked/padded options cannot be selected.

## 7. Open design details before implementation

1. deterministic allocation/order of the 40 entity slots and overflow behavior;
2. PAD, unknown, and no-entity sentinel indices;
3. Trainer play-effect placement in the static-card vector;
4. which attached Tool/Special Energy ID is used if multiple are present;
5. exact per-copy interpretation of the 60 deck-summary zone vectors;
6. option-to-entity pointer semantics for implicit targets and non-board options;
7. multi-select training and constrained inference when engine prompts are sequential;
8. deterministic construction and versioning of the card and attack vocabularies.

These are precision questions inside the overview, not permission to change its overall
architecture.
