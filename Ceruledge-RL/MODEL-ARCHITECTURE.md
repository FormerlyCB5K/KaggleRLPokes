# Ceruledge Policy Model Architecture

This document describes the current, near-final board representation and policy
interface used by the generalized Ceruledge reinforcement-learning agent. It is written
for readers who have no prior experience with this codebase or this model architecture.

The current implementation is defined primarily by `features.py`, `model.py`,
`actions.py`, `opponent_tags.py`, and `stat_bakes.py`. The design specifications in
`specs/completed/02-observation-encoding.md`,
`specs/completed/03-attack-ability-tagging.md`, and
`specs/completed/06-effect-baking.md` explain the intent behind those implementations.

## 1. Overview

### 1.1 What this document is about

The agent's job is to receive a Pokémon TCG game observation and return indices into
the game engine's current list of legal choices. The raw game state is too large and
irregular to send directly to a small neural network: the number and meaning of legal
actions change from decision to decision, hidden zones are only partially observable,
and different Pokémon have different attacks and abilities.

The system therefore has two major layers:

1. **Observation encoding.** The current game is converted into a fixed collection of
   numeric vectors describing our board, the opponent's board, our known card zones,
   and global game state.
2. **Policy and action translation.** A transformer turns those vectors into a board
   representation. A fixed action head chooses a broad action category, and a second
   scoring stage maps that category back to concrete engine options and targets.

The observation encoder is deliberately asymmetric. Our deck is fixed and fully known,
so our cards can use compact deck-specific identities. The opponent may use any legal
deck, so opponent Pokémon are represented through shared attributes such as HP, type,
attack properties, and ability properties rather than species identity.

### 1.2 Transformer model in brief

The policy is a small actor-critic transformer with **100,260 trainable parameters**.
One encoded game state becomes 23 logical "words":

- 9 words for our Active and eight possible Bench Pokémon;
- 9 words for the opponent's Active and eight possible Bench Pokémon;
- 4 words for our hand, discard, deck, and prizes; and
- 1 word for global game state.

The four source vector types have different widths, so four input MLPs independently
project them into a shared 64-dimensional space. Learned role embeddings tell the model
whether a word is our Active, our Bench, the opponent's Active, the opponent's Bench,
a particular card zone, or the global word.

The 23 words pass through a two-layer transformer encoder with two attention heads.
A learned attention-pooling query then combines them into one 64-dimensional summary
of the state. From that summary, the model produces:

- 19 logits for broad action categories;
- one scalar value estimate for PPO training; and
- dot-product scores used to rank concrete targets and follow-up choices.

The model is feed-forward rather than recurrent. Persistent information that cannot be
read from a single observation—such as inferred prizes, a recently applied Item lock,
or which Pokémon evolved this turn—is maintained by a small external game-state tracker
and included in the encoded features.

### 1.3 Important clarifications

The following scope boundaries are central to understanding the architecture:

- **The current policy only pilots the Ceruledge deck.** Its friendly Pokémon features,
  zone vocabulary, action categories, setup behavior, and several strategy features are
  specifically designed around that 60-card list.
- **It can observe and play against arbitrary opponent decks.** Opponent Pokémon do not
  use a species one-hot. Any opponent card in the database can be mapped into the same
  75-dimensional attribute schema.
- **Generalized opponent observation does not make the friendly policy deck-agnostic.**
  It means one Ceruledge policy can face many different decks without changing its input
  dimensions.
- **Bench positions on the same side are strategically equivalent.** All eight of our
  Bench positions share one role embedding, and all eight opponent Bench positions
  share another. Our Bench and the opponent's Bench remain distinct. Fixed word ordering
  is maintained throughout inference so every transformed word maps consistently back
  to its engine slot.
- **We intend to extend the system to pilot additional decks.** The expected approach is
  to reuse the current generalized opponent-side input design when constructing the
  friendly-side representation and action vocabulary for each new deck.
- **A trained checkpoint belongs to one model layout and policy role.** The previous
  16-word model cannot be loaded into this 23-word architecture. This model must be
  trained from scratch in a new run directory.

### 1.4 Future plans

Current future directions include:

- training separate copies of this same model on different matchups, producing
  matchup-specialized policies;
- improving learned handling of search and other follow-up selections;
- investigating the reinforcement-learning **options framework** as a possible way to
  organize multi-step decisions; and
- extending the architecture to pilot decks other than Ceruledge while reusing the
  generalized opponent representation developed here.

These are future directions, not claims about the current implementation.

## 2. Inputs

### 2.1 The four actual neural-network inputs

The neural forward pass receives exactly four tensors:

| Tensor | Shape for one state | Scalar values |
|---|---:|---:|
| Our Pokémon | `9 × 19` | 171 |
| Opponent Pokémon | `9 × 75` | 675 |
| Our card zones | `4 × 16` | 64 |
| Global state | `24` | 24 |
| **Total** | **23 logical words** | **934 floats** |

Their transformer word order is fixed:

| Word indices | Meaning | Source width |
|---:|---|---:|
| 0 | Our Active Pokémon | 19 |
| 1–8 | Our Bench positions 1–8 | 19 each |
| 9 | Opponent Active Pokémon | 75 |
| 10–17 | Opponent Bench positions 1–8 | 75 each |
| 18 | Our hand | 16 |
| 19 | Our discard | 16 |
| 20 | Our deck | 16 |
| 21 | Our prizes | 16 |
| 22 | Global state | 24 |

The engine's legal-option list is **not** part of these 934 floats. Legal options are
used after the forward pass to mask invalid action categories and construct target
candidates. This distinction is discussed in the Outputs section.

### 2.2 Shared encoding conventions

All delivered feature values are clipped to `[0, 1]`. Normalized counts and damage
values therefore saturate at their documented maximums.

#### Empty Pokémon slots

An empty Active or Bench input begins as an all-zero feature vector. There is no
explicit `is_occupied` feature.

#### Hit-ratio features

Three combat features compress durability into five possible values:

```text
min(numerator // denominator, 4) / 4
```

Possible outputs are `0.00`, `0.25`, `0.50`, `0.75`, and `1.00`.

- `0.00` means the target is within the next hit's KO range.
- `0.25`, `0.50`, and `0.75` represent approximately one, two, or three full hits.
- `1.00` represents four or more hits, no usable damage, or a zero denominator.

This is intentionally coarse and is not a continuous HP-to-damage fraction.

#### Special conditions

Five condition flags always appear in this order:

1. Asleep;
2. Paralyzed;
3. Burned;
4. Poisoned; and
5. Confused.

They may co-occur. Only Active Pokémon receive condition flags because those conditions
do not remain on Benched Pokémon under the game rules.

### 2.3 Stateful inputs and trackers

Most features come directly from `obs.current`, but a small `GameStateTracker` retains
information that cannot always be reconstructed from one observation.

It maintains:

- whether Lunatone's Lunar Cycle ability was used this turn;
- a supporter-use fallback marker;
- whether Budew or Frillish applied an Item lock that is still active;
- the friendly Pokémon serials that evolved during the current turn; and
- inferred prize identities and known card serials.

Per-turn flags reset when the engine turn number changes. Repeated processing of the
same observation is guarded so logs are not applied twice.

The manual-Energy-attachment flag is not duplicated in tracker state. The engine
directly exposes `obs.current.energyAttached`, which is the source for that feature.

#### `new_in_play`

A friendly Pokémon receives `new_in_play = 1` if either:

- the engine reports `poke.appearThisTurn`; or
- the Pokémon's serial appears in a friendly `EVOLVE` log during the current turn.

The evolution-serial set clears at the next turn. This feature exists primarily to
represent evolution legality.

#### Prize inference

Prize identities begin unknown. At the first full-deck search, the tracker subtracts
all visible or otherwise accounted-for friendly cards from the fixed 60-card list.

The accounting includes:

- hand and discard;
- Pokémon in play;
- attached Energy and Tools;
- pre-evolutions;
- the revealed deck; and
- the Trainer currently resolving the search, which can temporarily exist in no normal
  zone.

Card serials are retained after this first resolution. If a previously unseen serial
later appears in hand, discard, or play, that card is recognized as a taken prize and
removed from the inferred prize counts.

### 2.4 Our Pokémon: 19 features per slot

Our side is intentionally deck-specific.

| Dim | Feature | Meaning |
|---:|---|---|
| 0 | Effective maximum HP | Effective maximum HP divided by 270. |
| 1 | Current HP fraction | Effective current HP divided by effective maximum HP. |
| 2 | Ceruledge line | `1` for Ceruledge ex or Charcadet. |
| 3 | Ceruledge ex | Species one-hot. |
| 4 | Charcadet | Species one-hot. |
| 5 | Solrock | Species one-hot. |
| 6 | Lunatone | Species one-hot. |
| 7 | Drilbur | Species one-hot. |
| 8 | New in play | Played or evolved during the current turn. |
| 9 | Fire Energy attached | Count divided by 2 and clipped. |
| 10 | Fighting Energy attached | Count divided by 2 and clipped. |
| 11 | Attacks survivable | Hit ratio using this Pokémon's effective current HP and the opponent Active's effective maximum credible damage against this slot. |
| 12 | Attack damage | Friendly base damage plus applicable outgoing damage bonuses, divided by 440. |
| 13 | Hits to KO opponent | Hit ratio using the opponent Active's effective HP and this Pokémon's target-specific effective damage. |
| 14 | Asleep | Active only. |
| 15 | Paralyzed | Active only. |
| 16 | Burned | Active only. |
| 17 | Poisoned | Active only. |
| 18 | Confused | Active only. |

Friendly base attack damage is hard-coded because species identity fully determines the
relevant attack:

- Ceruledge ex: `30 + 20 × friendly Fire/Fighting Energy in discard`, capped at 440
  for the raw attack-damage feature;
- Solrock: 70;
- Lunatone: 50;
- Drilbur: 20; and
- Charcadet: 0. This deliberately ignores Charcadet's minor 1-Energy 10-damage attack;
  its non-damaging Energy-search attack is almost always preferred, so a 0-damage feature
  is the right strategic summary.

Dimension 12 adds outgoing damage bonuses but does not apply target Weakness,
Resistance, or damage reduction. Those target-specific effects are applied in dimension
13. Dimension 11 similarly routes the opponent threat through target-specific combat
math for each friendly slot.

### 2.5 Opponent Pokémon: 75 features per slot

The opponent representation is the core generalization mechanism. It does not identify
the opponent Pokémon by species. Instead, every Pokémon is converted into:

```text
28 base attributes
+ 18 attributes for attack 1
+ 18 attributes for attack 2
+ 11 attributes for ability 1
= 75 features
```

#### 2.5.1 Opponent base block: dimensions 0–27

| Dim | Feature | Meaning |
|---:|---|---|
| 0 | Effective maximum HP | Maximum of observed HP, database HP, and reviewed override HP, plus applicable HP auras; divided by 440. |
| 1 | Current HP fraction | Effective current HP divided by effective maximum HP. |
| 2 | No rule | Plain/non-ex Pokémon. |
| 3 | Pokémon ex | Rule one-hot; excludes Mega ex (those set dimension 4 instead). |
| 4 | Mega Pokémon ex | Rule one-hot. |
| 5 | Has Tool | Any Tool is attached, even if the Tool is currently suppressed. |
| 6 | Effective retreat cost | Effective retreat cost divided by 4. |
| 7 | Grass type | Type one-hot. |
| 8 | Fire type | Type one-hot. |
| 9 | Water type | Type one-hot. |
| 10 | Lightning type | Type one-hot. |
| 11 | Psychic type | Type one-hot. |
| 12 | Fighting type | Type one-hot. |
| 13 | Darkness type | Type one-hot. |
| 14 | Metal type | Type one-hot. |
| 15 | Dragon type | Type one-hot. |
| 16 | Colorless type | Type one-hot. |
| 17 | Weak to Fire | Effective weakness flag. |
| 18 | Weak to Fighting | Effective weakness flag. |
| 19 | Resists Fire | Effective resistance flag. |
| 20 | Resists Fighting | Effective resistance flag. |
| 21 | Survives Ceruledge | Hit ratio using effective current HP and Ceruledge's target-specific effective damage. | 
| 22 | Attached Energy count | Total Energy cards, type-blind, divided by 5. |
| 23 | Asleep | Active only. |
| 24 | Paralyzed | Active only. |
| 25 | Burned | Active only. |
| 26 | Poisoned | Active only. |
| 27 | Confused | Active only. |

#### 2.5.2 Attack extraction and ordering

At most two attacks are encoded. They are ordered cheapest-first by total printed
Energy cost, using printed/base damage as a tiebreaker.

Attack properties follow a three-tier extraction system:

1. A reviewed per-card override, when one exists.
2. Conservative regex/keyword extraction from the attack's effect text.
3. Zero effect tags when no reviewed or recognized effect applies.

Printed Energy cost and damage normally come from the card database. Overrides can
replace those fields. Selected copy-attack cards use reviewed virtual attacks so that a
zero printed attack does not imply zero strategic threat.

The attack-cost features are then updated with live board-dependent modifiers. Palafin's
variable recoil is also calculated from its current damage. Maximum-damage threat has a
small set of reviewed live formulas for cards whose output depends on hand size, damage
counters, discard contents, attached Energy across an archetype, or similar board state.

#### 2.5.3 Attack block: 18 features

Attack 1 occupies dimensions 28–45. Attack 2 occupies dimensions 46–63.

| Relative dim | Feature | Encoding and meaning |
|---:|---|---|
| 0 | Energy cost | Effective total Energy cost divided by 5. Energy types are not distinguished. |
| 1 | Damage | Printed, overridden, or approximated damage divided by 270 (our max HP; damage above that is overkill). |
| 2 | Snipe | Bench or spread damage divided by 100. |
| 3 | Counter snipe | Damage-counter placement converted to HP and divided by 100. |
| 4 | Conditional | Some additional condition must hold; normally supplied by an override. |
| 5 | Item lock | Prevents Item use. |
| 6 | Cooldown | Attacker cannot reuse the attack on its next turn. |
| 7 | Energy acceleration | Energy attached by the attack divided by 3. |
| 8 | Draws cards | Cards drawn divided by 6. |
| 9 | Discards Energy | Energy discarded divided by 5. |
| 10 | Full attack lock | Prevents the defending Pokémon from attacking. Named `cubchoo` internally. |
| 11 | Deck-out | Mill or deck-out strategy signal. |
| 12 | Probabilistic | Coin flip, random card, or other stochastic result. |
| 13 | Revenge | Improves after a Pokémon was KO'd on the previous turn. |
| 14 | Outrage | Damage scales with damage counters on the attacker. |
| 15 | Retreat lock | Prevents retreat during the opponent's next turn. |
| 16 | Attack immunity | Grants next-turn attack-damage prevention. |
| 17 | Recoil | Self-damage divided by 70. |

A Pokémon with one attack receives an all-zero second block.

#### 2.5.4 Ability block: dimensions 64–74

Only the first ability is encoded.

| Dim | Feature | Encoding and meaning |
|---:|---|---|
| 64 | Draw | Cards drawn divided by 6. |
| 65 | Damage | Damage-counter placement converted to HP and divided by 100. |
| 66 | Immunity | Relevant damage or effect immunity. |
| 67 | Gust | Can pull an opponent Bench Pokémon Active. |
| 68 | Energy to Active/anywhere | Energy accelerated divided by 3. |
| 69 | Energy to Bench | Bench-specific Energy acceleration divided by 3. |
| 70 | Search | Cards searched divided by 3. |
| 71 | Barrier | Protection that makes a Pokémon or board less worthwhile to attack. |
| 72 | Heal | Healing amount divided by 100. |
| 73 | Mill | Advances a deck-out strategy. |
| 74 | Switch | Free switching or retreat-related mobility. |

### 2.6 Effective stat baking

Attack and ability tags describe strategic capabilities. Effective stat baking serves a
different purpose: it makes the derived KO arithmetic aware of reviewed Tool, Ability,
and Stadium effects so the neural network does not have to rediscover routine combat
arithmetic from experience.

For every observation, the encoder builds a board object containing both in-play teams,
their Active markers, the current Stadium, attached cards, and remaining prize counts.
Reviewed modifiers can then affect:

- maximum and current HP;
- damage dealt;
- damage taken;
- Fire/Fighting Weakness and Resistance;
- retreat cost;
- attack cost;
- prize-scaled damage or cost;
- opponent-Bench-scaled cost; and
- Fighting-Energy-scaled HP.

Modifier applicability can depend on live conditions such as:

- whether the holder is Active or Benched;
- whether it is at full HP;
- whether it has a Tool or particular Energy type;
- its type, stage, rule status, or trainer-name archetype;
- the attacker's type or rule status;
- current prizes; or
- the presence of another Pokémon on the same side.

The effective damage calculation is conceptually:

```text
base or reviewed credible damage
+ applicable outgoing damage bonuses
×2 for relevant Weakness
−30 for relevant Resistance
+ applicable incoming-damage modifiers
clipped at zero
```

The resulting values feed:

- our `attacks_survivable`;
- our `attack_damage` bonuses;
- our `attack_hits_opponent`;
- opponent `attacks_survivable_vs_ceruledge`;
- opponent effective HP;
- opponent effective retreat and attack costs;
- opponent Fire/Fighting Weakness and Resistance flags; and
- global `ceruledge_KO`.

The system avoids known double counting. In particular, HP Tools already reflected in
the engine's observed HP are not added again. Jamming Tower can suppress Tool bakes, and
Team Rocket's Watchtower can suppress applicable Colorless-Pokémon Ability bakes.

Attack cost is represented as capability information. It does not gate or zero the
opponent's damage feature based on currently attached Energy.

Full immunity, Sturdy-like survival, recurring healing, and exotic hard damage caps are
not folded into the hit-ratio calculations. Some appear as separate tags instead.

### 2.7 Our card-zone inputs: four 16-feature words

The zones are ordered hand, discard, deck, prizes. Each contains normalized counts for
the 15 unique cards in the fixed deck, followed by `is_unknown`.

| Dim | Card | Original copies |
|---:|---|---:|
| 0 | Ceruledge ex | 4 |
| 1 | Charcadet | 4 |
| 2 | Solrock | 2 |
| 3 | Lunatone | 2 |
| 4 | Drilbur | 1 |
| 5 | Fire Energy | 7 |
| 6 | Fighting Energy | 13 |
| 7 | Night Stretcher | 4 |
| 8 | Brilliant Blender | 1 |
| 9 | Fighting Gong | 4 |
| 10 | Ultra Ball | 4 |
| 11 | Poké Pad | 3 |
| 12 | Boss's Orders | 3 |
| 13 | Explorer's Guidance | 4 |
| 14 | Carmine | 4 |
| 15 | Unknown flag | — |

Each count is divided by its original copy count. For example, two visible Ceruledge ex
cards produce `2 / 4 = 0.5` in that zone.

Hand and discard are observed directly. Until prize identities are resolved, both deck
and prizes use:

```text
[0, 0, ..., 0, 1]
```

After resolution, prizes use inferred remaining counts and deck is calculated as:

```text
full deck − hand − discard − cards tied up in play − known prizes
```

Cards tied up in play include attached Energy, attached Tools, and pre-evolutions.

### 2.8 Global input: 24 features

| Dim | Feature | Meaning |
|---:|---|---|
| 0 | Solrock–Lunatone combo | Both species are in play on our side. |
| 1 | Ceruledge-line count | In-play Ceruledge ex plus Charcadet, divided by 4. |
| 2 | Ceruledge discard driver | Friendly Fire/Fighting Energy in discard, divided by 16. |
| 3 | Ceruledge KO ratio | Effective Ceruledge damage divided by opponent Active effective current HP, clipped to 1. No opponent Active gives 1. |
| 4 | Turn number | Total engine turn number divided by 30. |
| 5 | Item locked | Tracked Budew/Frillish lock or Tyranitar currently Active. |
| 6 | Energy attached | Engine flag indicating the manual attachment was used this turn. |
| 7 | Supporter used | Engine supporter flag or tracker fallback. |
| 8 | Lunar Cycle used | Tracker flag for the current turn. |
| 9 | Turn order | `1` if we went second, `0` if first, `0.5` if unknown. |
| 10 | Our prizes | Remaining count divided by 6. |
| 11 | Our hand size | Divided by 15. |
| 12 | Our discard size | Divided by 46. |
| 13 | Our deck size | Divided by 46. |
| 14 | Opponent prizes | Remaining count divided by 6. |
| 15 | Opponent hand size | Divided by 15. |
| 16 | Opponent discard size | Divided by 46. |
| 17 | Opponent deck size | Divided by 46. |
| 18 | Nighttime Mine | Stadium one-hot. |
| 19 | Team Rocket's Watchtower | Stadium one-hot. |
| 20 | Forest of Vitality | Stadium one-hot. |
| 21 | N's Castle | Stadium one-hot. |
| 22 | Area Zero Underdepths | Stadium one-hot. |
| 23 | Spikemuth Gym | Stadium one-hot. |

An unlisted Stadium leaves dimensions 18–23 zero, although a reviewed stat-bake effect
from that Stadium may still change derived combat values.

### 2.9 Projection, role embeddings, transformer, and pooling

Four MLPs project the source vectors into the shared transformer width:

| Input type | Projection |
|---|---|
| Our Pokémon | `19 → 38 → GELU → 64` |
| Opponent Pokémon | `75 → 150 → GELU → 64` |
| Card zones | `16 → 32 → GELU → 64` |
| Global state | `24 → 48 → GELU → 64` |

All four card zones share one projection MLP.

Nine learned role embeddings are added: our Active, our Bench, opponent Active,
opponent Bench, hand, discard, deck, prizes, and global. There is no separate positional
embedding for individual Bench positions.

The transformer uses:

- model width 64;
- two encoder layers;
- two attention heads;
- feed-forward width 128;
- GELU activation;
- pre-layer normalization; and
- zero dropout.

A learned 64-dimensional pooling query scores all 23 output words. Softmax converts
those scores into attention weights, and their weighted sum becomes the pooled state
used by the policy and value heads.

### 2.10 Input omissions and representation limitations

The following omissions are either deliberate scope decisions or known lossy parts of
the representation.

#### Hidden and opponent-zone information

The model does not receive opponent hand identities, deck composition, prize
composition, or a card-vector representation of opponent discard. It sees only their
counts. It also does not retain a learned memory of opponent cards revealed earlier and
then returned to a hidden zone.

#### Opponent identity and attributes

Opponent species identity is deliberately omitted. Cards with identical represented
attributes are indistinguishable. Opponent evolutionary stage is also not a direct
feature, even though stage may be used internally by stat-bake conditions.

Opponent attached Energy is type-blind. The model sees total count and attack cost but
not whether the attached types actually satisfy the attack. Tool identity is absent
except where a reviewed Tool changes a baked stat; otherwise only `has_tool` remains.

Only Fire and Fighting Weakness/Resistance are exposed. Fairy is not part of the ten-type
basis.

#### Friendly-side simplifications

Our Pokémon do not directly encode generic stage, rule, retreat cost, attack cost,
Weakness, Resistance, attack-effect tags, ability tags, or Tool identity. Species
identity is expected to carry the fixed deck's static semantics.

Our attack-cost changes are not represented. In particular, an effect that raises
Ceruledge's Energy requirement can change legality in the engine without changing a
friendly attack-cost feature, because no such feature exists.

#### Effect coverage

At most two attacks and the first ability are represented. Additional attacks or
abilities are discarded. Complex card text is handled conservatively: unrecognized
wording becomes zero tags rather than speculative features. Copy attacks, variable
damage, untranslated text, and conditional effects may require reviewed approximations.

Most attack-effect tags describe capability, not current temporary state. The model may
know that an attack can grant immunity or cooldown without knowing whether that effect
is active now. Full immunity and Sturdy-like survival are not incorporated into hit
ratios.

The opponent maximum-damage threat is payability-blind. It can represent the strongest
credible attack even when insufficient Energy is currently attached. Cost and Energy
count are left for the network to consider separately.

#### Lossy normalization

Clipping removes distinctions above the configured scales, including:

- friendly HP above 270;
- opponent HP above 440;
- friendly attack damage above 440;
- opponent attack damage above 270;
- snipe/counter damage above 100;
- recoil above 70;
- more than two friendly Fire or Fighting Energy;
- more than five opponent Energy; and
- hit counts above four.

The five-level hit ratio also discards exact HP margins, overkill, fractional hit
differences, and distinctions between four hits and much higher durability.

#### State and context omissions

The network is feed-forward and has no recurrent memory. Only engineered tracker state
persists. It has no explicit early/mid/late game category, opponent per-turn action-use
flags, current selection-context feature, or encoded legal-option list.

Only six Stadium identities have global one-hots. Other reviewed Stadium effects can be
baked into combat features, but the policy may not know which unlisted Stadium caused
the change.

#### Empty-slot behavior

Empty slots begin as zero feature vectors, but they are not attention-masked. MLP biases
and role embeddings make their projected words nonzero, so the transformer and pooling
mechanism can attend to empty positions. There is no `is_occupied` flag.

#### Known accepted edge cases

Before the first deck search, deck and prize identities are entirely unknown. During a
Trainer's resolution, the feature-level deck-by-elimination calculation can temporarily
overcount that Trainer by one because it may be absent from every normal zone. This is a
documented, accepted TODO.

For a zero-damage friendly species, the zero-damage rule gives
`attack_hits_opponent = 1` even in the transient no-opponent-Active state. Damaging
species receive 0 in that state. Decisions are normally not requested during this edge
case.

## 3. Outputs

### 3.1 How output selection works

The neural network does not directly output a raw engine option. It first scores 19
broad **Stage 1** action categories, such as "attach Fire Energy," "play Ultra Ball,"
"attack," or "pass." The game engine's legal options are translated into those
categories, and illegal categories are masked to negative infinity before softmax. If
the chosen category corresponds to several concrete options—for example, attaching
Energy to several possible Pokémon—a **Stage 2** dot-product scorer ranks candidate
targets using the pooled state and transformed board/card vectors. The final result is
a list of indices into the engine's current option list.

### 3.2 Direct model outputs

One forward pass returns:

| Output | Shape | Use |
|---|---:|---|
| Transformed words | `B × 23 × 64` | Contextual board/zone words reused for target candidates. |
| Pooled state | `B × 64` | Whole-state summary for policy, value, and target scoring. |
| Stage 1 logits | `B × 19` | Raw broad-action scores. |
| Value | `B` | Scalar expected-return estimate used by PPO. |

The 19 Stage 1 actions are:

| ID | Action |
|---:|---|
| 0 | Play or evolve Ceruledge ex |
| 1 | Play Charcadet |
| 2 | Play Solrock |
| 3 | Play Lunatone |
| 4 | Play Drilbur |
| 5 | Play Night Stretcher |
| 6 | Play Brilliant Blender |
| 7 | Play Fighting Gong |
| 8 | Play Ultra Ball |
| 9 | Play Poké Pad |
| 10 | Play Boss's Orders |
| 11 | Play Explorer's Guidance |
| 12 | Play Carmine |
| 13 | Attach Fire Energy |
| 14 | Attach Fighting Energy |
| 15 | Retreat |
| 16 | Attack |
| 17 | Use Lunatone's ability |
| 18 | End turn/pass |

**Drilbur's ability is not one of these 19 categories.** Only Lunatone's Lunar Cycle is
promoted to a learned Stage 1 action (ID 17). Like other optional triggered abilities,
Drilbur's surfaces to the agent as a separate `ACTIVATE` (YES/NO) sub-selection, which is
resolved heuristically as always-YES (§3.3–3.4), not by the learned head. So the *choice*
to use it is not currently a learned decision.

**Each hand card has its own Stage 1 category,** so the network never confuses Ultra Ball
(ID 8) with Brilliant Blender (ID 6) *at Stage 1*. The follow-up cost/discard selection is
also effect-aware: the triggering card (`obs.select.effect`) is encoded through the shared
zone MLP and added to the pooled state before the Stage 2 card scorer ranks candidates, so
discarding for an Ultra Ball cost and discarding for a Brilliant Blender cost use
different conditioned states rather than one purpose-agnostic ranking (§3.3).

### 3.3 Stage 2 and follow-up selections

Stage 2 assigns each candidate the score:

```text
pooled_state · candidate_vector
```

Friendly and opponent Pokémon candidates reuse their post-transformer words. Cards from
hand, discard, deck, or a temporary revealed pile use a 16-feature card identity vector
passed through the shared zone MLP.

For sub-selection card contexts (discard, search-to-hand), the pooled state is first
conditioned on the triggering effect card: `obs.select.effect` is encoded through the same
zone MLP and added to `pooled_state`, so the ranking depends on *why* the cards are being
chosen (e.g. an Ultra Ball cost versus a Brilliant Blender cost).

Examples:

- After Stage 1 chooses **Attach Fire**, Stage 2 compares the transformed words for the
  legal friendly Active/Bench targets.
- After **Boss's Orders**, the follow-up `SWITCH` decision compares opponent Bench words.
- After **Ultra Ball**, discard and deck-search candidates are encoded as individual
  card vectors and ranked.
- After **Retreat**, the destination is chosen from friendly Bench words.
- **Pass** normally maps directly to the engine's single END option.

Variable-count card selections can include a learned STOP token. Candidates are chosen
one at a time and removed from the remaining list. The pooled state is not recomputed
after each pick.

Setup, first-player selection, and some follow-up contexts are handled outside the
learned Stage 1 head through fixed routing or heuristics.

### 3.4 Output omissions and not-yet-clean implementations

The output system is functional but contains several important limitations:

- **Stage 2 is not directly trained by PPO.** PPO stores and recomputes only the Stage 1
  action log probability. Target, search, discard, switch, promotion, and STOP choices
  receive no direct policy-gradient objective.
- **The STOP token has no effective training path in the current PPO loop.** The zone
  MLP and board words learn through Stage 1 and value prediction, but not specifically
  from whether a Stage 2 target was good.
- **Stage 2 is greedy during rollout.** Stage 1 may use stochastic exploration, but
  targets and follow-up selections generally do not.
- **Multiple attacks are not cleanly distinguished.** All legal attacks map to the one
  `ACTION_ATTACK` category. If several raw attacks are legal, their current Stage 2
  candidates are zero vectors, so the first tied engine option normally wins.
- **MAIN candidate support is incomplete.** Fire/Fighting attachments and Ceruledge
  evolution targets receive meaningful candidate words: `select_main_stage2` maps a Bench
  `EVOLVE` candidate to its Bench word and an Active `EVOLVE` candidate to the Active word
  (`words[0]`), so evolving the Active Charcadet is now ranked on equal footing with Bench
  evolutions. Other duplicate raw options generally still receive zero vectors.
- **Retreat Energy discard is uninformed.** Attached Energy choices use zero candidate
  vectors, so the model cannot deliberately preserve one Energy type over another.
- **Optional activation is heuristic.** `ACTIVATE` chooses YES when available.
- **Setup is heuristic.** The opening Active is chosen by a fixed species priority list
  rather than a learned output (`train.py` `_setup_active`): the first of
  Solrock → Charcadet → Lunatone → Drilbur present in hand. Ceruledge ex is absent because
  it is a Stage 1 evolution and cannot be put directly into play during setup. The agent
  deliberately **benches nothing at setup** (`_setup_bench` declines whenever the engine
  allows it); bench development happens later through normal MAIN play.
- **Unsupported selection contexts fall back to option order.** They return the first
  required option indices rather than using a learned decision.
- **Multi-pick selections are not combination-aware.** Removing selected candidates is
  the only state change between picks; the model does not update its pooled state to
  reflect the partial selection.
- **The Stage 1 vocabulary is Ceruledge-specific.** It cannot pilot another deck without
  a new friendly-side vocabulary and action mapping.
- **The generalized opponent encoder is not yet matched by generalized training.** The
  current training harness still needs the planned multi-deck opponent pool before the
  model will routinely learn from arbitrary matchup distributions.

The most important future output-side question is whether Stage 2 and multi-step
follow-up decisions should remain lightweight dot-product helpers, receive their own
learned policies, or be reorganized through a higher-level options framework.
