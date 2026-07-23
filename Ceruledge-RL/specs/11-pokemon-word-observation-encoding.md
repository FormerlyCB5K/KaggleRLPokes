# 11 — Pokémon Word Observation Encoding — Overview

Status: **design complete and transcribed into tested standalone code under
`Imitation-Learning/observation/` (2026-07-21). Both tag vocabularies are complete. The
live-engine adapter and training integration remain open, as does one design question:
whether `attacks_survivable` should consider only currently affordable attacks.**

## What this is

The observation encoding for a Pokémon TCG agent that can pilot *any* deck, trained by
imitation learning on top-ladder bot replay data (`Imitation-Learning/`), rather than an
agent hardcoded to one five-card deck. This spec covers exactly one piece of that: the
**Pokémon board-slot word** — the fixed-width vector representing one Pokémon in play,
friendly or opponent. It does not cover Trainer/Energy cards (spec 11b), card-zone words,
or global state (spec 13).

**Spec 11 and its children (11a, 11b) are planning documents, not implementation.** Their
deliverable is a design artifact: a catalog of tag names, their meanings, detection rules
(regex/keyword logic ready to hand to a future implementation pass) for never-before-seen
cards, and a complete manual tag assignment for every audited meta card. No parser, model
code, or training loop was written *as part of these specs*. A later implementation pass
has since transcribed them into `Imitation-Learning/observation/`; wiring that package to
the live engine and training consumer is still pending.

## Session summary (2026-07-16)

This spec is the output of a long design conversation, condensed here so the reasoning
isn't lost:

1. Started from the existing 23-word transformer (`Ceruledge-RL/model.py`,
   `features.py`), which is deliberately asymmetric today: the friendly side is a
   deck-specific species one-hot (Ceruledge only), the opponent side is a generic
   75-dimensional attribute/tag vector built to face any deck. Generalizing to "pilot any
   deck" requires collapsing that asymmetry — both sides need the same schema.
2. A separate, already-completed audit (spec 12, `Imitation-Learning/meta-card-registry/`)
   exhaustively catalogued every exact card ID played at the top of the ladder over a
   recent 3-day window: 232 cards (115 Pokémon / 99 Trainer / 18 Energy) across 15,018
   games, with every attack/ability/effect compiled into a structured "effect program"
   AST and verified against card text and engine source.
3. A first design pass proposed compiling that AST directly into a wide (~560-dim) fixed
   structured record per Pokémon, consumed by one flat projection. Two rounds of outside
   review (documented in two discussion artifacts, links below) found this technically
   sound but overengineered for what the attribute block is actually for: it optimized
   for near-total losslessness on a component that was only ever meant to be a fallback
   and a warm start, not the primary signal.
4. That produced a course correction (this spec): the card-ID embedding is the primary
   signal for known meta cards; the attribute/effect tag block is a deliberately lossy
   fallback for unseen cards and a warm start for known ones. The right design is closer
   to the *original* flat-tag scheme (16 attack tags / 11 ability tags), substantially
   widened and refined using the spec-12 registry as a reference/checklist — not a
   compositional AST consumer.
5. A follow-up interview resolved a scope-boundary loose end: how a Pokémon card should
   be represented if it's sitting in a zone (hand/discard/deck) rather than on the board,
   given a future spec (13) may move zones to one word per card. Resolution: factor the
   Pokémon word into a reusable static template and board-only live state (see below).

Reference artifacts from the shelved AST direction (kept for context, not part of the
current plan): [round 1](https://claude.ai/code/artifact/d0399233-8e2d-43f5-8f43-fd842746fc12),
[round 2](https://claude.ai/code/artifact/868e7b7e-9f72-4fc5-81ce-fcf4442450df).

## Design philosophy

> Card-ID embedding as (near-)perfect identity, with effect encoding as a fallback. The
> expanded tag vocabulary should be expansive enough to cover all attacks and abilities
> *nearly* losslessly, without compromising performance with the larger observation.

Consequences:

- The card-ID embedding (a lookup table over the 115 audited Pokémon IDs, plus one shared
  "unknown" vector) is expected to do most of the work for the ~115 cards that recur
  constantly in top-ladder play.
- The attribute/effect tag block exists so that (a) a Pokémon the model has never seen
  still gets a reasonable, non-embarrassing representation, and (b) known cards get a
  warm start early in training before their embedding is well fit.
- Because the tag block is a fallback, not the source of truth, some real loss is
  acceptable — unlike spec 12's registry, which is held to a zero-silent-loss bar because
  it's an archival ground-truth artifact, not a training input.
- Width still matters. The goal is "nearly lossless," not "lossless" — a design that
  regains full AST fidelity at the cost of a several-hundred-dimension word per Pokémon
  has overshot the actual requirement.

## Scope (this spec)

- Defines the Pokémon board-slot word structure: which fields are static vs. live, and
  how they combine.
- Defines the card-ID embedding contract (vocabulary source, UNK handling).
- Defines the runtime split for the attribute/effect tag block: a manually-tagged lookup
  table for the 115 known meta Pokémon, a regex/detection-rule parser as fallback for
  everything else. Hands off the actual tag catalog and detection rules to spec 11a.
- Establishes the seam spec 13 will use if it moves Pokémon zone cards to per-card words.
- Scope is planning: tag vocabularies, detection rules, and manual ground-truth tagging.
  Not code.

## Explicitly out of scope

- The attack/ability tag vocabulary itself — that's spec 11a's deliverable, not decided
  here.
- Trainer and Energy card tag vocabularies — spec 11b.
- Card-zone word design and global-state assembly — spec 13. This spec does not decide
  whether zones become per-card words; it only makes sure the Pokémon static template is
  usable that way if spec 13 chooses to.
- The compositional-AST consumer design explored earlier in this session. Shelved, not
  deleted — the reasoning is preserved in the linked artifacts if it's ever revisited.
- Any code or implementation. No implementation should start until the tag vocabularies
  in 11a/11b are drafted and signed off.

## The Pokémon word structure

Every Pokémon — friendly or opponent, known or unseen — factors into two pieces:

**(a) Static template** — means the same thing regardless of where the card currently is:
- Card-ID embedding (115-entry vocabulary from the spec-12 registry, plus one shared UNK
  vector for anything outside it).
- The attribute/effect tag block (spec 11a): for the 115 known meta Pokémon, a manually
  assigned lookup table built directly from the spec-12 registry's exact ground truth (no
  regex involved — we already know precisely what these cards do). For everything else,
  a widened regex/keyword detection-rule parser designed and validated against that same
  manually-tagged sample. The lookup table is strictly more accurate than re-deriving the
  same tags from English text, which is why known cards use it directly instead of also
  being routed through the regex parser. Includes `energy_cost` per attack row (see spec
  11a's schema) — card-data-sourced, not text-detected, and only meaningful for attack
  rows (abilities have no energy cost under real rules).
- Static printed fields (widths locked 2026-07-16, see "Base field schema" below):
  `hp_max`, type, rule status, `retreat_cost`, weakness type, resistance type.

**(b) Live board state** — only meaningful while the Pokémon is actually in play:
- `hp_curr`, `attached_energy_counts`, `tool_template` (spec 13a).
- Status conditions (Active only).
- `new_in_play`.
- Threat/KO hit-ratio features (`attacks_survivable`, `attack_damage`,
  `attack_hits_opponent`) — depend on the opposing Pokémon's current state, can't be
  computed off-board. **`attacks_survivable`'s exact reference-attacker definition is
  still open** — see "Base field schema" below.
- On-field aura overrides to weakness type (resistance never needs this — see below): see
  "Base field schema" below — these reuse the static field's own dimensions rather than
  adding a separate "effective" copy.

**Dividing rule:** static = fixed by the card's print, never changes this game. Live =
anything that can change during play, even if it started from a static base.

## Base field schema (locked 2026-07-16, one open item)

Resolves this spec's earlier "exact field widths" open question for everything outside
the attack/ability tag block (spec 11a) and the zone/attachment structure (spec 13a).

### Static

| Field | Encoding | Note |
|---|---|---|
| `hp_max` | `/ 340` | One shared max across the full audited pool — replaces the old encoding's asymmetric `/270` (our side) vs `/340` (opponent side) split. |
| Type | 10-dim one-hot: Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, Dragon, Colorless (no Fairy) | Same list the old opponent-side encoding already used; now applied symmetrically to both sides. |
| Rule status | 3-dim one-hot: none / `ex` / Mega `ex` | |
| `retreat_cost` | `/ 4` | |
| Weakness type | 9-dim one-hot: Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, Colorless (no Fairy, **no Dragon** — nothing is weak to Dragon in the current format) | All-zero = no weakness. |
| Resistance type | Same 9-dim one-hot as weakness | All-zero = no resistance — the common case; most current-format cards have none printed. **Never live-overridden (spec 14 confirmed 2026-07-16): the engine has no mechanism to change resistance dynamically at all** — always the static printed value, no exceptions. |

**On-field aura overrides (weakness only — resistance never needs this).** When a Pokémon
is on the board and an active Stadium/Ability aura changes its weakness type, the encoder
overwrites that Pokémon's own weakness one-hot field in place for the board word — there is
no separate "effective" duplicate field. A card sitting in a zone (hand/deck/discard) always
gets the pure printed value; only the board-word computation path is ever permitted to apply
an aura override, and only for as long as the Pokémon remains on the field affected by that
aura. This keeps the field count identical between zone words and board words — spec 13's
zone words reuse the exact same static fields, just
without the override ever being applied.

### Live

| Field | Encoding | Note |
|---|---|---|
| `hp_curr` | `/ hp_max` (own, post-bake) | **Resolved (spec 14):** no baking needed at all — the engine already resolves every continual HP modifier into the observation's `hp`/`maxHp` fields, regardless of source. Read directly, always. |
| `attached_energy_counts` | **11-dim** vector (the 9-type list plus `Rainbow` and `Team Rocket Energy`, see below), one count per attached Energy's bucket, `/ 5` clipped | |
| `special_energy_id` | **Resolved (spec 14):** 10-dim identity vector, one per meta Special Energy card, presence-based (not count). Exists only as a fallback signal for Special Energy effects that don't fit any bakeable KO-math category (`EFFECT_IMMUNE`, `DRAW`, `COUNTER_PLACE`, `FLEXIBLE_ENERGY_PROVISION`, `PRIZE_DENIAL`, etc.) — deliberately imperfect for those, same trade as spec 11a's tag block. Any Special Energy effect that *does* fit a bakeable category is baked instead (spec 14 audited all 10 meta Special Energy cards; none qualified — see that spec for why). |
| `tool_template` | Spec 13a | |
| `new_in_play` | Flag | Now symmetric — the old encoding only tracked this on our side. |
| Special conditions | 5-dim **multi-hot** (can co-occur): Asleep, Paralyzed, Burned, Poisoned, Confused; Active only | Unchanged from the old design — conditions can legally stack (e.g. Asleep + Poisoned). |
| `attacks_survivable` | Hits-ratio feature | **Locked 2026-07-16.** Reference attacker = the single highest damage value across **every** Pokémon on the opposing board (active and all bench slots, not just the current active), each Pokémon's own contribution taken as the max across its own attacks (mirrors the old `opp_active_max_damage` per-Pokémon max, now maxed again across the whole opposing roster). Symmetric both sides. This is a general fragility/worst-case-threat signal, independent of whether that attacker is currently active or could legally reach this slot this turn — resolves the earlier bench-targeting question without needing to gate on `SNIPE` reach. Not yet addressed: whether the max should only consider attacks the opposing Pokémon can *currently afford* (given its attached Energy vs. the new `energy_cost` field) or all printed attacks regardless of current affordability — minor, worth confirming before implementation but not blocking. |
| `attack_damage` | Effective, live, per-attack | Derived from spec 11a's `DAMAGE` tag + dynamic formulas + effective-stat baking ([`14-effect-baking-audit.md`](14-effect-baking-audit.md)), symmetric both sides — the old design only computed this on our side, with hardcoded per-species base values. |
| `attack_hits_opponent` | Hits-ratio feature | Symmetric now, both sides — the old design only computed this on our side. |

**Shared hits-ratio convention (carried forward unchanged):** `min(numerator // denominator, 4) / 4`,
integer division; if the denominator is 0 (no damage / no usable attack), encode the clip
max, `1.0`. Applies to `attacks_survivable` and `attack_hits_opponent`.

### Special Energy → `attached_energy_counts` bucket mapping (added 2026-07-16)

`attached_energy_counts` widens from the original 9 dims (8 basic types + Colorless) to
**11 dims**: those same 9 plus two new dedicated buckets, `Rainbow` and
`Team Rocket Energy` — all `/ 5` clipped, same as every other dimension.

| Bucket | Cards |
|---|---|
| Colorless (existing dim) | Basic Colorless Energy, plus Special Energy that functions as Colorless: Ignition Energy, Mist Energy, Spiky Energy, Enriching Energy, Boomerang Energy |
| `Rainbow` (new dim) | Legacy Energy; Prism Energy **when attached to a Basic Pokémon** — see the conditional rule below |
| `Team Rocket Energy` (new dim) | Team Rocket Energy — its own dedicated bucket, not folded into any type or into Colorless/`Rainbow` |
| Type-specific dims (existing — no new dims needed) | Telepathic Energy → Psychic; Growing Energy → Grass; Rocky Energy → Fighting; any other type-specific Special Energy maps the same way, onto its provided type's existing dimension |

**Prism Energy is the one context-dependent case.** Unlike every other entry above (a fixed
lookup by card ID), Prism Energy's bucket depends on the *live* state of the Pokémon it's
attached to: `Rainbow` while the host is currently a **Basic** Pokémon, Colorless once the
host has evolved. This has to be recomputed whenever the host's evolution stage changes,
not baked once at attach-time — unlike every other Special Energy in this table, which has
a fixed bucket regardless of board context.

This list is not guaranteed exhaustive against spec 12's full Energy census (~18 audited
IDs). Any Special Energy encountered that isn't covered here needs its bucket confirmed
before implementation, not silently defaulted.

A board word = static template + live state + a board-role embedding (our-active,
our-bench, opponent-active, opponent-bench — reusing the role-embedding mechanism already
in the current 23-word model). A future zone word for a Pokémon card (spec 13's decision,
not this spec's) would be static template alone + a zone-role embedding — no need to
invent placeholder values for HP fraction, status, or energy count for a card sitting in
hand.

The static template must be implemented as a genuinely separate, standalone-callable
piece — not a slice carved out of one combined output vector — since a card in hand has
no live state to slice from.

## Success criteria

- The static-template / live-state split is implemented as two separately callable
  functions (or an equivalent clean seam), not one monolithic combined encoder.
- A board word's live-state half is entirely absent (not zero-padded-but-present) when
  computed for a context with no board state, once spec 13 needs that.
- The attribute/effect tag block (once 11a lands) produces effectively zero all-zero
  assignments across the 115 audited Pokémon's 201 effect rows, with any remaining known
  gaps listed explicitly rather than silently accepted.
- The regex/detection-rule fallback is validated against the same manually-tagged sample
  (does it reproduce a reasonable approximation of the ground-truth tags when run on
  known cards' text, even though production never actually routes known cards through it)
  before being trusted on genuinely unseen cards.
- Both friendly and opponent Pokémon are encoded through the exact same function.

## Components

- [`11a-pokemon-attribute-tag-vocabulary.md`](11a-pokemon-attribute-tag-vocabulary.md) —
  the systematic review plan to derive the widened Pokémon attack/ability tag vocabulary.
- [`11b-trainer-energy-tag-vocabulary.md`](11b-trainer-energy-tag-vocabulary.md) — the
  analogous review plan for Trainer and Energy cards.
- [`13-card-zone-observation-space.md`](13-card-zone-observation-space.md) — card-zone
  words, global state, and how zones move to persistent per-card words. Design phase.

## Key decisions

See the numbered session summary above; restated as a flat list for reference:

1. Symmetric friendly/opponent Pokémon encoding — one function, both sides.
2. Card-ID embedding is the primary signal for known cards; attribute tags are a fallback
   and warm start, not required to be lossless.
3. Static template / live board state split, with the "changeable during play" dividing
   rule.
4. Two-path runtime for the attribute/effect tag block: a manually-tagged lookup table
   (built from spec-12 registry ground truth) for the 115 known meta Pokémon, and a
   regex/keyword detection-rule parser as fallback for everything else. The manual
   tagging doubles as the parser's validation set — it is not merely a design-time aid,
   it is the production data source for known cards.
5. The full compositional-AST direction is shelved, not adopted, for this component.
6. Card-ID dropout during training and leave-card-out/leave-archetype-out evaluation are
   carried forward as required methodology whenever training is designed (out of scope
   for this spec, which only covers the encoding function).
7. Spec 11/11a/11b are planning deliverables: tag catalogs, detection rules, and a
   complete manual tag assignment for the meta sample. No parser or model code is written
   here.

## Open questions

- Exact dimensionality of the card-ID embedding (tunable hyperparameter; not fixed here).
- **Effect-baking redesign** — see [`14-effect-baking-audit.md`](14-effect-baking-audit.md).
  Resolved: HP needs no baking (engine already resolves it) and resistance never does
  (no engine mechanism can change it); retreat cost, weakness, attack cost, and flat
  damage deltas still need real bake-table entries, audited against the meta Tool/
  Stadium/Ability/Special-Energy pool. **Now resolved**, including the Special Energy
  identity question below.
- Whether multiple *different* Special Energy IDs simultaneously attached to one Pokémon
  all need to show up in `special_energy_id` (multi-hot) rather than a single slot — minor,
  presumed yes, not yet explicitly confirmed (see spec 14).
- Whether `attacks_survivable`'s opposing-board max should filter to only attacks the
  opposing Pokémon can currently afford (vs. `energy_cost`) or consider all printed attacks
  regardless of current affordability — minor, not blocking.
- Whether spec 13 actually adopts per-card zone words at all, and if so how much of the
  static template it uses. Explicitly deferred to spec 13 — **now resolved**: spec 13a
  adopted fixed-capacity padded zone arrays using this spec's static template.
