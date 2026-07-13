# 02 — Observation Encoding (Generalized Ceruledge Bot)

## Purpose

Replace the current `features.py` encoding with one that generalizes to **arbitrary
opponent decks** while still piloting the fixed Ceruledge deck. Our side keeps
deck-specific identity (species one-hots, card-slot zone vectors); the opponent side is
encoded purely by **attributes** (HP, type, rule, attack/ability tags) so any card the
engine throws at us maps into a shared feature space.

The two-stage transformer architecture (Stage 1 action vocabulary, Stage 2 dot-product
candidate scoring, word-type embeddings, attention pooling) is **unchanged** by this
spec. Only the input representation and its input MLPs change.

#Sebastian's comments (Sebastian is the human user) are marked at the end of a line with a #

## Word inventory

**23 words** feed the transformer, produced by **four separate input MLPs**:

| Words | Count | Dims each | Input MLP |
|---|---|---|---|
| Our Pokémon (active, bench 1–8) | 9 | 19 | our-Pokémon MLP |
| Opponent Pokémon (active, bench 1–8) | 9 | 75 | opponent-Pokémon MLP |
| Zones (hand, discard, deck, prizes) | 4 | 16 | shared zone MLP (one MLP for all 4) |
| Global | 1 | 24 | global MLP |

Word role is carried by the existing word-type embedding mechanism, not by the feature
vectors. Our active, our bench, opponent active, and opponent bench are four distinct
roles. All eight bench positions on one side deliberately share one role embedding:
bench positions are strategically equivalent, while our bench and the opponent's bench
remain distinct. The fixed word ordering is stable end-to-end so Stage 2 always maps a
candidate back to the same board slot. The four zones have distinct role embeddings.

The zone MLP is deliberately shared across all 4 zones (a possible later change to
per-zone MLPs is out of scope).

Empty Pokémon slots (both sides): **all-zeros vector**. No is_occupied flag.

## Shared conventions

- All features normalized to [0, 1] unless stated otherwise; clip before dividing.
- **Hits ratios** (used three times below): computed with integer division,
  `min(numerator // denominator, 4) / 4`. If the denominator is 0 (no damage / no
  usable attack), encode the clip max: **1.0**.
- Special-condition flags: 5 binary dims in the order **Asleep, Paralyzed, Burned,
  Poisoned, Confused**. They can co-occur (not a strict one-hot). Only active Pokémon
  can have them; bench slots always 0.
- **No opponent active** (start of game / mid-KO replacement): treat the missing
  active as having **0 HP**. So `attack_hits_opponent` = 0.0, and `ceruledge_KO`
  stays 1.0 (its stated rule). We never make decisions in these moments; the values
  just need to be well-defined.

### Effective-stat semantics (Specs 06 and 07)

The formulas below name the underlying/base quantities. The implemented encoder then
routes KO-relevant values through the reviewed effective-stat layer defined by Specs
`06-effect-baking.md` and `07-effect-baking-audit.md`. This is the accepted architecture.

Before normalization and hit/KO calculations, applicable Tool, Ability, Stadium,
weakness, resistance, HP-aura, retreat, attack-cost, damage-dealt, and damage-reduction
effects are baked into the relevant values. Tool HP changes already reflected by the
engine in observed `hp`/`maxHp` are not applied a second time. Live board-dependent
damage formulas that cannot be represented faithfully by one printed scalar are
evaluated from board state. The resulting values remain clipped to `[0, 1]` at the
feature boundary.

## Zone vectors — 4 × 16 dims

Zones encoded: **our** hand, discard, deck, prizes. Opponent zones are NOT encoded
(their prize/hand/discard/deck *counts* appear in the global vector only).

Each zone vector = 15 floats + 1 flag:

- Dims 0–14: count of each of the 15 unique Ceruledge deck cards, in the existing
  `DECK_CARDS` order, each divided by its `DECK_COUNTS` copy count (so each dim ∈ [0,1]).
- Dim 15: `is_unknown` flag.
- Unknown zone: **all 15 counts = 0.0, flag = 1.0**. (Changed from the old −1.0 fill.)

Zone contents:

- **Hand, discard**: read directly from the observation.
- **Prizes**: from the prize tracker (`prize_check.py` — see spec `01-prize-tracker.md`).
- **Deck**: computed by elimination: full deck − hand − discard − in-play cards
  (including attached energy) − known prizes.
- **Until the prize tracker resolves prize contents, BOTH deck and prizes are encoded
  as unknown** (zeros + flag). Once prizes are known, both encode real counts.

## Global vector — 24 dims

| # | Feature | Encoding |
|---|---|---|
| 0 | solrock_lunatone_combo | 1.0 if both Solrock and Lunatone are in play on our side |
| 1 | num_ceruledge_line | (count of our in-play Ceruledge ex + Charcadet) / 4, clipped |
| 2 | ceruledge_damage | (Fire + Fighting energy cards in our discard) / 16, clipped |
| 3 | ceruledge_KO | effective Ceruledge damage / opponent active effective current HP, **clipped at 1.0** (real division, not the hits convention; ≥1 means Ceruledge KOs their active). Base damage is `30 + 20 × discard_energy_count`; apply the effective-stat semantics above. No opp active → 1.0 |
| 4 | turn_number | total turns elapsed (both players) / 30, clipped. No explicit game-phase flag — the model infers stage |
| 5 | item_locked | see below |
| 6 | energy_attached | `obs.current.energyAttached`: the engine reports that we already used the manual Energy attachment this turn |
| 7 | supporter_used | we already played a supporter this turn |
| 8 | lunar_used | Lunatone ability used this turn |
| 9 | turn_order | 1.0 if we went second, 0.0 first, 0.5 unknown (existing convention) |
| 10–13 | our prizes, hand, discard, deck | / 6, / 15, / 46, / 46 |
| 14–17 | opp prizes, hand, discard, deck | / 6, / 15, / 46, / 46 |
| 18–23 | stadium one-hot | Nighttime Mine, Team Rocket's Watchtower, Forest of Vitality, N's Castle, Area Zero Underdepths, Spikemuth Gym |

### Stadium one-hot

Read the shared stadium spot from `obs.current.stadium`. Append six binary dimensions
to the existing global vector in this exact order:

| # | Stadium |
|---|---|
| 18 | Nighttime Mine |
| 19 | Team Rocket's Watchtower |
| 20 | Forest of Vitality |
| 21 | N's Castle |
| 22 | Area Zero Underdepths |
| 23 | Spikemuth Gym |

Set the matching dimension to `1.0` when that stadium is in play. With no stadium in
play, or with any stadium not listed above, all six dimensions are `0.0`. No other
stadiums are encoded, and this adds no new transformer word; the dimensions are wired
directly into the existing global word and global input MLP.

### item_locked semantics

One flag, three sources, all producing the identical game effect (we can't play Items):

- **Budew** or **Frillish** used its item-locking attack on the opponent's last turn →
  tracked state: set when the attack is observed, **cleared at the end of our turn**.
  The two are mechanically indistinguishable.
- **Tyranitar** is the opponent's active Pokémon → continuous, checked live from the
  current observation every step (no tracking, no expiry logic).

`item_locked = budew_frillish_tracked OR tyranitar_active_now`.

## Our Pokémon vector — 19 dims × 9 slots

| # | Feature | Encoding |
|---|---|---|
| 0 | hp_max | / 270 |
| 1 | hp_curr | / own hp_max |
| 2 | is_ceruledge_line | 1.0 for Ceruledge ex or Charcadet | # (This is identical to a type encoding, as just Ceruledge and Charcadet are Fire; the rest in our deck are Fighting.)
| 3–7 | species one-hot | Ceruledge ex, Charcadet, Solrock, Lunatone, Drilbur (existing `POKE_IDS` order) |
| 8 | new_in_play | 1.0 if this card entered play OR evolved this turn; cleared at turn end. Exists solely for evolution legality |
| 9 | fire_energy_attached | / 2, clipped |
| 10 | fighting_energy_attached | / 2, clipped |
| 11 | attacks_survivable | hits ratio using effective current HP and the opponent active's effective maximum credible damage against this slot |
| 12 | attack_damage | effective damage / 270. Base values: Ceruledge ex `30 + 20 × discard_energy_count` (clip at 270), Solrock 70, Lunatone 50, Drilbur 20, Charcadet 0 |
| 13 | attack_hits_opponent | hits ratio using opponent effective current HP and our effective damage against that opponent; base attack damage 0 → 1.0 ("can never KO") |
| 14–18 | special conditions | 5 flags (see shared conventions) |

No ability, attack-cost, or retreat dims on our side — the species one-hot fully
determines them, so the network can learn them implicitly.

`opp_active_max_damage` starts from the highest damage across the opponent active's
attacks from spec `03-attack-ability-tagging.md`, then applies reviewed live
board-dependent formulas and effective-stat modifiers from Specs 06/07. Card-specific
dynamic formulas may be implemented in the feature/effective-stat layer when that is
safer and simpler than forcing a live value into the static override table. Zero / no
attacks → attacks_survivable = 1.0.

## Opponent Pokémon vector — 75 dims × 9 slots

Layout: 28 base dims + 2 × 18 attack blocks + 11 ability block.

### Base — dims 0–27

| # | Feature | Encoding |
|---|---|---|
| 0 | hp_max | / 340 |
| 1 | hp_curr | / own hp_max |
| 2–4 | rule one-hot | none / ex / mega ex |
| 5 | has_tool | 1.0 if a Tool card is attached (any tool, regardless of baking below) |
| 6 | retreat_cost | / 4 |
| 7–16 | type one-hot | 10 types: Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, Dragon, Colorless (no Fairy) |
| 17 | is_weak_to_fire | flag |
| 18 | is_weak_to_fighting | flag |
| 19 | resists_fire | flag |
| 20 | resists_fighting | flag |
| 21 | attacks_survivable_vs_ceruledge | hits ratio using opponent effective current HP and effective Ceruledge damage; base Ceruledge damage is `30 + 20 × our_discard_energy_count` |
| 22 | num_energy_attached | total energy cards, type-blind, / 5, clipped |
| 23–27 | special conditions | 5 flags |

### Effective-stat baking

Apply the effective-stat semantics above and the reviewed bake table from Specs 06/07.
For example, an HP aura changes effective HP, a retreat-reducing Tool lowers effective
`retreat_cost`, and a conditional damage modifier participates in KO math when its live
condition is satisfied. Tools whose effects do not map onto an encoded or KO-relevant
quantity contribute nothing beyond `has_tool`. Tool *tagging* as a separate schema is
still out of scope.

### Attack blocks — dims 28–45 and 46–63

Two 18-dim blocks, one per attack, **cheapest-first** (the order `card_data.py` already
produces). Cards with one attack: second block all zeros. Block layout and tag
extraction are defined in `03-attack-ability-tagging.md` (§ Attack block schema).

### Ability block — dims 64–74

One 11-dim block. If a card has two abilities, **encode only the first and ignore the
second**. Layout and extraction in `03-attack-ability-tagging.md` (§ Ability block
schema).

## Tracker state requirements

The per-game tracker (successor to `GameStateTracker`) must maintain:

- Per-turn inferred flags: `supporter_used`, `lunar_used` (reset each turn).
- `energy_attached` is not duplicated in tracker state; read the engine-owned
  `obs.current.energyAttached` flag directly.
- `item_locked` tracking for Budew/Frillish attacks (set on observation of the attack,
  cleared at end of our turn).
- `new_in_play` per our-side Pokémon (set on entering play or evolving; cleared at turn
  end).
- Prize knowledge via `prize_check.py`; deck-by-elimination depends on it.

## Verification (acceptance bar)

Before any training run on the new encoder:

- **Unit tests**: hand-computed expected vectors for known game states (at minimum:
  early-game state with unknown prizes, mid-game state with resolved prizes, an
  opponent card hitting each tag tier, a status-afflicted active, an empty bench slot).
- **Live smoke test**: a full game against a scripted agent, asserting every step:
  correct shapes (9×19, 9×75, 4×16, 24), all values in [0, 1], no NaNs/infs. The
  Transformer output must have 23 words.

## Out of scope

- Encoding opponent zones (hand/discard/deck contents).
- Per-zone MLPs (shared MLP for now).
- Piloting decks other than Ceruledge (Stage 1 vocabulary and our-side encodings stay
  deck-specific).
- Game-phase one-hot flags (turn_number float only).
- Changes to Stage 1/Stage 2 mechanics, PPO training loop, or model core beyond the
  four new input MLPs and word count (16 → 23).

## Open questions

- None at spec time. Keyword tag lists in `03` are explicitly provisional (see that
  file's audit section).
