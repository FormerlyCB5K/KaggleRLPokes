# Observation Architecture

This document describes the observation encoder only — not the policy/value network that
consumes it. It corresponds to the implementation in `Imitation-Learning/observation/`
(`encoder.py`, `zones.py`, `static_template.py`, `trainer_energy_static.py`, `live_state.py`,
`board_context.py`, `pokemon_tag_catalog.py`, `trainer_energy_tag_catalog.py`, `types.py`),
which implements the locked design in `Ceruledge-RL/specs/11-pokemon-word-observation-encoding.md`,
`11a`, `11b`, `13-card-zone-observation-space.md`, `13a-observation-space-design.md`, and the
`14-effect-baking-audit.md` corrections layered on top.

This is the newer, any-deck observation space (spec 11/13/13a/14). It is a different design
from the older 23-word Ceruledge-specific encoding described in
`Ceruledge-RL/MODEL-ARCHITECTURE.md` — that document still describes the currently-trained
Ceruledge PPO policy; this one describes the successor encoder built to generalize across
decks.

## 1. Overview

### 1.1 The word model

The observation is a fixed-length sequence of **174 "words."** Each word is one card-shaped
slot — a card sitting in a zone, a Pokémon in a board position, the active Stadium, or a
handful of scalar/reserved slots. Every word has the same top-level shape regardless of what
it holds:

- **kind** — what role this word plays structurally (`zone_card`, `board_pokemon`, `stadium`,
  `global`, `pool`, `pad`). Not learned; used for masking and for picking which sub-builder
  produced the word.
- **role** — for board words only, which of the four board positions this is
  (`our_active` / `our_bench` / `opponent_active` / `opponent_bench`). Intended to drive a
  learned role embedding downstream, the same mechanism the old 23-word encoder already used.
- **static** — the card's printed identity: which card it is, plus a fixed-width numeric
  encoding of its printed stats and effect text. Present for any word that holds a real or
  hidden card; `None` for PAD/global/pool words.
- **live** — game-state-dependent fields that printed card data alone can't give you (current
  HP, attached Energy, special conditions, threat ratios against the current board). Only
  board Pokémon and the global word have a `live` block; zone cards and the Stadium do not.
- **attention_masked** — `True` only for PAD. Everything else, including a hidden (UNK) card,
  participates in attention and pooling.

### 1.2 Why cards are split into "static" and "live"

A card's printed text (HP, type, "does 120 damage") is the same everywhere it appears. What
changes is board-specific: how much damage it's *currently* taken, what's attached to it right
now, whether it's Asleep. Splitting these means the identical printed-stat encoding is reused
for a card sitting in the deck, the hand, the discard, or the board — only board positions pay
for the extra live fields.

### 1.3 Two ways a card gets its numeric encoding

Every card needs a fixed-width vector describing its printed effect text (the "tag block").
There are two paths, tried in order:

1. **Known meta card → transcribed lookup.** For the ~115 Pokémon and ~117 Trainer/Energy
   cards in the current competition meta, a human-reviewed table
   (`pokemon_meta_tags.META_TAGS` / `trainer_energy_meta_tags.META_TAGS`) gives the exact tag
   vector directly — no parsing involved.
2. **Unknown card → regex fallback.** Any card outside that vocabulary (an off-meta tech
   choice, a card added after the table was built) falls back to a regex parser
   (`tag_unseen_pokemon` / `tag_unseen_trainer_energy`) run against the card's own printed
   move/effect text, producing a vector in the same layout.

This means the observation never needs a species-identity dimension to represent an
*opponent's* card correctly — any legal card, seen or not, degrades gracefully into the same
attribute schema. Only our own deck (and any other card the model should individually
recognize) additionally gets a **card-ID embedding index** (`card_index`) into a shared
embedding table; `card_index = UNK_CARD_INDEX` for anything outside that vocabulary or for a
genuinely hidden card.

### 1.4 PAD vs. UNK

Two distinct "nothing here" states exist, and they are not interchangeable:

- **PAD** — no card at all (an empty zone slot beyond current occupancy, an empty bench
  position). Masked out of self-attention and pooling entirely.
- **UNK** — a real card whose identity is currently hidden from us (our own face-down,
  unrevealed Prize cards are the only case in the current design). Gets the same all-zero
  identity/static template as PAD's slot *content*, but is **not** attention-masked — its mere
  presence (a card exists here, we just can't see it) is still informative to the model.

### 1.5 Canonical ordering

Within a zone, known cards are sorted by card ID (a deterministic, gameplay-independent
tiebreak) rather than by reveal order, draw order, or any other history-dependent ordering.
This keeps the encoding order-invariant to how cards happened to arrive in the zone — spec
13a's rationale is that gameplay order is not itself a meaningful feature and building order
sensitivity in would just add noise for the model to learn around.

### 1.6 Word budget (174 total)

| Zone / slot | Word kind | Count | Card contents |
|---|---|---|---|
| Our deck | `zone_card` | 47 | known cards, PAD beyond occupancy |
| Our prizes | `zone_card` | 6 | known + UNK (our own hidden prizes) + PAD |
| Our hand | `zone_card` | 20 | known cards, PAD beyond occupancy |
| Our discard | `zone_card` | 40 | known cards (fully revealed zone), PAD beyond occupancy |
| Opponent discard | `zone_card` | 40 | known cards (fully revealed zone), PAD beyond occupancy |
| Board | `board_pokemon` | 18 | 1 active + 8 bench, both sides; PAD for empty positions |
| Stadium | `stadium` | 1 | the in-play Stadium card, or PAD if none |
| Global | `global` | 1 | scalar game-wide state (currently: `turn_number`) |
| Pool | `pool` | 1 | reserved, currently empty (no static/live content) |

Our own deck and hand are never hidden from the observation (we always know our own list);
the opponent's hand and deck are simply not represented as zones at all — nothing in the
observation encodes "I don't know what's in the opponent's hand" beyond its absence. Overflow
(more cards in a zone than its capacity) is tracked via `overflow_count` rather than silently
dropped, though it isn't currently exposed to the model as its own word/feature.

---

## 2. Feature-by-feature tables

### 2.1 Card identity (every real/UNK card word)

| Field | Width | What it measures | Notes |
|---|---|---|---|
| `card_index` | 1 (embedding lookup index) | Which exact card this is, for cards the model should recognize by identity | `UNK_CARD_INDEX` (one shared out-of-vocabulary slot) for any card outside the shared card-ID vocabulary, or for a genuinely hidden (UNK) card |

### 2.2 Pokémon static block (printed stats)

Applies to every Pokémon word: zone cards, board Pokémon, and (rarely) a Pokémon-typed
Stadium slot doesn't apply — Stadiums always resolve through the Trainer/Energy template
(§2.5), even though most Stadiums are Trainer cards by game rules.

| Field | Width | What it measures | Normalization |
|---|---|---|---|
| `hp_max` | 1 | Printed max HP | `/340`, clipped to 1.0 |
| `type_onehot` | 10 | Printed Pokémon type | One-hot over `Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, Dragon, Colorless` (no Fairy) |
| `rule_onehot` | 3 | Rule-box status | One-hot over `none, ex, mega_ex` |
| `retreat_cost` | 1 | Printed retreat cost | `/4`, clipped to 1.0 |
| `weakness_onehot` | 9 | Printed Weakness type | One-hot over 9 types (no Fairy, no Dragon — nothing is weak to Dragon in the current format); all-zero if no Weakness. **On board words only**, this is live-overwritten if an in-play aura (e.g. Lillie's Clefairy ex) changes it — zone words always keep the pure printed value |
| `resistance_onehot` | 9 | Printed Resistance type | Same 9-type vocabulary as Weakness; all-zero if none. Never live-overwritten — no bake mechanism exists for Resistance |
| `tag_block` | 201 (`70×2 + 61`) | Encoded attack/ability effect text | See §2.3 |

An UNK/PAD Pokémon slot gets all-zero identity and all-zero base fields (an unknown card has
no printed data to encode).

### 2.3 Pokémon tag block (attack/ability effect encoding)

Three rows per Pokémon: **attack 0**, **attack 1** (cheapest-first, zero-padded if the card
has fewer than 2 attacks), **ability 0** (only the first ability is encoded; a second ability
is ignored). Each attack row is 70 dims, the ability row is 61 dims — the only difference is
attack rows carry a 9-dim `energy_cost` the ability row doesn't.

**Row layout (61 dims, ability; +9 `energy_cost` = 70 for attacks):**

| Segment | Width | What it measures |
|---|---|---|
| 49 content-tag scalars | 49 | One scalar per tag below — presence (1.0) or a normalized magnitude, per tag |
| `CONDITIONAL` presence | 1 | Effect is gated on a condition the schema doesn't otherwise encode (registry-sourced only; never text-detected) |
| `CONDITIONAL.voluntary_cost` | 1 | The condition is a cost the player chooses to pay, not an external trigger |
| `CONDITIONAL.near_always_true` | 1 | The condition is true in the overwhelming majority of real games (soft-boolean hint) |
| `distribution` | 1 | The effect's targets/counters are freely distributable ("any way you like") rather than fixed |
| `conserved` | 1 | For counter-moving effects, whether the total is conserved (moved) vs. duplicated — not text-derivable, defaults to 0 |
| `self_referential` | 1 | For `SELF_SWITCH`, whether the card itself is the one that swaps (vs. a free choice of which Benched Pokémon moves) |
| `scope_onehot` | 6 | Who the effect targets: `self, own_bench, own_team, opponent_named_subset, both_sides, other` — only populated when a tag with a `scope` qualifier fired |
| `energy_cost` (attack rows only) | 9 | Printed attack cost, one dim per type + colorless-count style encoding (card-data sourced, not text-detected) |

**The 49 content tags:**

| Tag | Magnitude family | What it measures |
|---|---|---|
| `DAMAGE` | damage | Base damage dealt to the defending Pokémon |
| `SNIPE` | damage | Damage to a freely-targetable (often Benched) opposing Pokémon — tracked independently of `DAMAGE`, never mirrored |
| `IGNORES_WEAKNESS` | boolean | This attack's damage isn't affected by Weakness |
| `IGNORES_RESISTANCE` | boolean | This attack's damage isn't affected by Resistance (sometimes Weakness too) |
| `IGNORES_ACTIVE_EFFECTS` | boolean | Damage ignores effects currently on the target Active Pokémon |
| `DAMAGE_IMMUNE_FROM` | boolean | Prevents all damage from attacks under some stated condition |
| `EFFECT_IMMUNE` | boolean | Prevents all (not just damage) effects of attacks |
| `RECOIL` | damage | Self-inflicted damage from using this attack |
| `DRAW` | count | Cards drawn |
| `SELF_SWITCH` | boolean | User switches itself for a Benched Pokémon |
| `SELF_MILL` | boolean | User (and attachments) shuffled into its own deck |
| `COUNTER_PLACE` | count | Damage counters placed on a target |
| `COUNTER_MOVE` | count | Damage counters moved from one Pokémon to another |
| `CONDITION` | boolean | Inflicts a Special Condition (which one is not numerically encoded) |
| `EVOLVE_SEARCH` | boolean | Searches the deck for a card that evolves from a named Pokémon |
| `SEARCH_ATTACH` | count | Searches deck/hand for Energy and attaches it outright |
| `HEAL` | count | HP healed |
| `RNG_SCALING_DAMAGE` | damage | Damage that scales with repeated coin flips until tails |
| `COIN_FLIP_DAMAGE` | damage | Bonus damage conditional on a single coin-flip heads |
| `ENERGY_ACCEL` | count | Attaches Energy from hand/discard outside the normal per-turn attachment |
| `SEARCH_HAND` | count | Searches deck for a card and puts it directly into hand |
| `REVEAL_DIG` | count | Looks at the top/bottom N cards of a deck |
| `STAT_BUFF` | damage | Increases damage dealt by attacks used by a scope of Pokémon |
| `DISCARD_SELF` | count | Discards cards from own hand/board |
| `ITEM_LOCK` | boolean | Opponent can't play Item cards |
| `SETUP_ALT_PLACEMENT` | boolean | Can be placed face-down as the Active Pokémon during setup |
| `REVIVE_FROM_DISCARD` | count | Returns a Pokémon from the discard pile onto the Bench |
| `SELF_KO` | boolean | Using this Ability knocks out its own user |
| `DOUBLE_ATTACK` | boolean | May use an attack it has twice |
| `RETREAT_LOCK` | boolean | The Defending Pokémon can't retreat |
| `ATTACK_LOCK` | boolean | The Defending Pokémon can't use attacks |
| `SELF_NO_WEAKNESS` | boolean | This Pokémon has no Weakness |
| `SELF_RETURN_TO_HAND` | boolean | User and its attachments return to hand |
| `COOLDOWN` | boolean | User can't attack/use this again for a period |
| `MILL` | count | Discards cards from the top of the opponent's deck |
| `EXTRA_PRIZE` | count | Take additional Prize cards on a KO |
| `RETREAT_COST_MOD` | retreat (signed) | Modifies a Retreat Cost (own or a named target's) |
| `ATTACK_INHERIT` | boolean | Can use attacks from its own previous Evolutions |
| `WEAKNESS_OVERRIDE` | boolean | Sets a new Weakness type on a target (which type is not numerically encoded) |
| `STADIUM_REMOVE` | boolean | Discards the in-play Stadium |
| `ATTACK_DISABLE` | boolean | Locks out one specific chosen opposing attack |
| `HP_BUFF` | hp (signed) | Modifies max HP, can be a debuff |
| `SWITCH_FORCE` | boolean | Forces the opponent to switch their Active/Bench Pokémon |
| `DISCARD_OPP` | count | Forces discards from the opponent's hand |
| `ENERGY_AMPLIFY` | multiplier | Energy attached within a scope provides extra Energy (which type is not numerically encoded) |
| `STAT_DEBUFF` | damage | Reduces damage dealt by the opponent's (or a named target's) attacks |
| `ENERGY_RETURN_TO_DECK` | count | Shuffles attached Energy back into the deck |
| `SEARCH_BENCH` | count | Searches the deck for Basic Pokémon and benches them |
| `COPY_ATTACK` | boolean | Copies and uses another Pokémon's attack as this attack |

Not counted among the 49: `CONDITIONAL` itself is its own presence bit plus two qualifier
bits (see the row-layout table above), sourced only from the meta lookup — the regex fallback
never sets it.

### 2.4 Pokémon live-state block (board words only)

Zone cards (deck/hand/discard/prizes) never get a `live` block. Board Pokémon do.

| Field | Width | What it measures | Normalization / source |
|---|---|---|---|
| `hp_curr` | 1 | Current HP fraction remaining | `hp / max_hp` (both already fully effect-resolved by the engine — nothing re-derived), clipped to 1.0 |
| `attached_energy_counts` | 11 | Count of attached Energy per bucket | 9 type buckets + `Rainbow` + `Team Rocket Energy`; each `/5`, clipped to 1.0. Basic Energy falls into its own printed type; Special Energy uses a locked name→bucket map; Prism Energy is `Rainbow` while the host is Basic, `Colorless` once evolved |
| `special_energy_id` | 10 | Which specific meta Special Energy card(s) are attached | Multi-hot presence, one dim per tracked Special Energy card (`Telepath Psychic Energy`, `Grow Grass Energy`, `Mist Energy`, `Spiky Energy`, `Enriching Energy`, `Team Rocket's Energy`, `Rock Fighting Energy`, `Ignition Energy`, `Prism Energy`, `Legacy Energy`) — multiple can be lit at once |
| `evolved_from` | 3 | Prior evolution stage card IDs | Raw card-ID integers (not one-hot/embedded here), padded with `0` up to depth 3; `0` means "no entry," not literal card-ID 0 |
| `new_in_play` | 1 | Whether this Pokémon entered play this turn | Boolean |
| `special_conditions` | 5 | Active Special Conditions | Multi-hot over `Asleep, Paralyzed, Burned, Poisoned, Confused` |
| `attacks_survivable` | 1 | How many hits from the single hardest-hitting Pokémon on the *entire* opposing board this Pokémon can survive | `min(effective_hp // worst_opposing_damage, 4) / 4`; `1.0` if the opposing board can't deal any damage |
| `attack_damage` | 2 | Effective damage this Pokémon's two attack slots would deal to the opposing Active right now | Post-Weakness(×2)/Resistance(−30)/bake-adjusted, `/DAMAGE_CAP(350)`, clipped to 1.0; `[0.0, 0.0]` if there's no opposing Active |
| `attack_hits_opponent` | 1 | How many hits at this Pokémon's best current damage it would take to KO the opposing Active | Same hits-ratio mechanism as `attacks_survivable`, referenced against the opposing Active specifically |

`attacks_survivable` and `attack_hits_opponent`/`attack_damage` are genuinely pairwise —
computed per board slot against the relevant opposing reference, not shared across the board
— so target-restricted bonuses (e.g. Maximum Belt) are reflected correctly per slot.

### 2.5 Trainer/Energy static block

Trainer and Energy cards have no board-slot analogue and no static/live split — the same
template is used whether the card is sitting in a zone, is the active Stadium, or (for a Tool)
would be fused into a Pokémon's live state.

| Field | Width | What it measures | Notes |
|---|---|---|---|
| `card_index` | 1 (embedding lookup) | Which exact card this is | Same shared vocabulary/UNK convention as §2.1 |
| `tag_block` | 54 | Encoded card effect text | Single row — no attack/ability split, no `energy_cost` (Pokémon-specific) |

**Row layout (54 dims):**

| Segment | Width | What it measures |
|---|---|---|
| 39 content-tag scalars | 39 | 20 tags reused verbatim from the Pokémon catalog + 19 new tags (below) |
| `CONDITIONAL` presence + 2 qualifier bits | 3 | Same meaning as §2.3, shared object with the Pokémon catalog |
| `MULTI_CHOICE` | 1 | Registry-only flag for a card with a structured multi-option choice; never text-detected |
| `ON_DAMAGED_TRIGGER` | 1 | Effect triggers when this card's holder is damaged by an opposing attack while Active |
| `ON_ATTACH_TRIGGER` | 1 | Effect triggers at the moment this card is attached from hand |
| `distribution` | 1 | Same meaning as §2.3 |
| `conserved` | 1 | Same meaning as §2.3 — always 0, not text-derivable |
| `self_referential` | 1 | Always 0 in Trainer/Energy context (no "itself" to reference the way a Pokémon's own `SELF_SWITCH` does) |
| `scope_onehot` | 6 | Same 6-value vocabulary as §2.3 |

**20 tags reused from the Pokémon catalog** (identical `TagSpec`, same object, can never
drift): `DAMAGE_IMMUNE_FROM`, `EFFECT_IMMUNE`, `DRAW`, `SELF_SWITCH`, `COUNTER_PLACE`,
`CONDITION`, `EVOLVE_SEARCH`, `SEARCH_ATTACH`, `HEAL`, `ENERGY_ACCEL`, `SEARCH_HAND`,
`REVEAL_DIG`, `STAT_BUFF`, `DISCARD_SELF`, `DISCARD_OPP`, `SWITCH_FORCE`, `HP_BUFF`,
`RETREAT_COST_MOD`, `SEARCH_BENCH`, `STAT_DEBUFF` — see §2.3 for what each measures.

**19 tags new to Trainer/Energy:**

| Tag | Magnitude family | What it measures |
|---|---|---|
| `HAND_RESET` | boolean | Shuffles a hand into its owner's deck |
| `DISCARD_RETRIEVE` | count | Returns cards from the discard pile to hand |
| `ENERGY_RETURN_TO_HAND` | boolean | Puts all Energy attached to a target Pokémon into hand |
| `SEARCH_DECK_TOP` | count | Searches the deck for N cards and places them on top of the deck |
| `EVOLVE_FROM_HAND` | boolean | Enables evolving a Pokémon using a Stage 2 card straight from hand |
| `DISCARD_OPP_BOARD` | count | Discards Energy/Tools attached to an opposing Pokémon |
| `DISCARD_TO_DECK` | count | Shuffles cards from the discard pile back into the deck |
| `ENERGY_MOVE` | count | Moves (not duplicates) an attached Energy from one Pokémon to another |
| `SELF_CONSUME` | boolean | This card discards itself as part of its own effect |
| `SURVIVE_KO` | hp | Prevents a Knock Out that would otherwise occur, once |
| `ATTACK_COST_MOD` | cost | Increases the Energy cost of attacks used by a scope of Pokémon |
| `SUPPRESS_TOOLS` | boolean | Pokémon Tools attached within a scope have no effect |
| `CONDITION_IMMUNITY` | boolean | Recovers from and becomes immune to all Special Conditions |
| `EVOLUTION_RULE_MOD` | boolean | Relaxes the normal same-turn evolution restriction |
| `DAMAGE_REDUCTION` | damage | Reduces damage taken from attacks, within a scope |
| `SUPPRESS_ABILITIES` | boolean | Pokémon in play within a scope have no Abilities |
| `BENCH_CAPACITY_MOD` | count | Changes the maximum Bench size |
| `FLEXIBLE_ENERGY_PROVISION` | count | Provides Energy of any type / multiple types at once |
| `PRIZE_DENIAL` | count | Reduces the number of Prize cards an opponent takes on a KO |

### 2.6 Zone words (deck / hand / discard / prizes)

Every slot in these five zones (`our_deck`, `our_prizes`, `our_hand`, `our_discard`,
`opponent_discard`) is a `zone_card` word carrying only the static block from §2.1/§2.2/§2.5
(whichever template matches the card's class) — **no live block, no role beyond which zone it's
in.** Zone words never get the live-aura weakness overwrite described in §2.2 — they always
carry the pure printed value, even if the card would behave differently on the actual board
right now.

| Zone | Capacity | Hidden slots | What's visible |
|---|---|---|---|
| Our deck | 47 | none | Full known contents (we always know our own deck) |
| Our prizes | 6 | Yes — unrevealed own prizes are UNK | Known revealed prizes as real cards, rest as UNK |
| Our hand | 20 | none | Full known contents |
| Our discard | 40 | none | Fully public zone |
| Opponent discard | 40 | none | Fully public zone |

The opponent's hand and deck are not represented at all — there is no "hidden opponent zone"
word; their non-visibility is expressed purely by their absence from the observation.

### 2.7 Board words

18 slots total: our active + 8 bench, then opponent active + 8 bench (fixed order), each
tagged with one of the four `BoardRole` values (`our_active`, `our_bench`, `opponent_active`,
`opponent_bench`) so a downstream role embedding can distinguish them. Missing positions are
PAD. Each occupied slot carries the full static block (§2.2, with the live weakness overwrite
applied) plus the full live block (§2.4).

### 2.8 Stadium / Global / Pool words

| Word | Kind | Static | Live | What it measures |
|---|---|---|---|---|
| Stadium | `stadium` | Full Trainer/Energy template (§2.5) for the in-play Stadium card | none | Which Stadium is active and its encoded effect. PAD if no Stadium is in play |
| Global | `global` | none | `turn_number` (1 scalar) | Game-wide state not attached to any specific card. Currently only turn number; the two known stadium-driven suppression effects (`Jamming Tower` disabling Tools, `Team Rocket's Watchtower` disabling Colorless Abilities) are computed as board-context inputs rather than encoded as their own global fields |
| Pool | `pool` | none | none | Reserved capacity, currently unused — carries no information yet |
