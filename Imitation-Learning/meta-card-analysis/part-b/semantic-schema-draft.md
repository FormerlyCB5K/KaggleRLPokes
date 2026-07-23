# B04 Compositional Semantic Schema Draft

Status: **provisionally approved — lossless meta coverage and efficient compilation required**

The canonical object is an ordered effect-program abstract syntax tree. Flat tags are
derived compatibility views and are not edited independently.

## Program structure

Each exact `effect_id` records activation, an ordered program, a damage profile,
evidence, and audit state. Program nodes are `sequence`, `operation`, `conditional`,
`choice`, `for_each`, `repeat`, or `reference`. This preserves ordering, branches,
selection, repeated effects, and delegated attacks without inventing card-specific
top-level fields.

## Canonical operations

The proposed operations are:

- damage and health: `deal_damage`, `place_damage_counters`,
  `remove_damage_counters`, `knock_out`;
- conditions: `apply_special_condition`, `clear_special_conditions`;
- cards and attachments: `move_cards`, `shuffle_cards`, `attach_card`, `detach_card`;
- Pokémon movement/evolution: `switch_active`, `evolve`, `devolve`;
- persistent rules: `modify_stat`, `modify_damage_rule`, `modify_action_rule`,
  `modify_card_rule`, `modify_prize_rule`, `provide_energy`;
- delegated behavior and information: `copy_or_use_attack`, `reveal_or_inspect`;
- terminal/control outcomes: `end_turn`, `win_game`, `no_op`.

Targets carry controller, zone, entity, filters, quantity, chooser, ordering, and
visibility. Durations carry start/end events, while-conditions, stacking behavior, and
reset events.

## Expressions and observability

Values and conditions use composable expressions: `literal`, `read`, `count`, `add`,
`subtract`, `multiply`, `divide`, `minimum`, `maximum`, `compare`, `and`, `or`, `not`,
`coin_flip`, and `random_choice`.

Every state read is classified as `static`, `observation_direct`,
`observation_derived`, `public_history`, `hidden_information`, `stochastic`,
`engine_internal`, or `unavailable`. This explicitly separates cheap live calculations
from hidden/history-dependent behavior.

## Damage profile

Every attack records printed base damage, a live formula, credible maximum, theoretical
maximum, expected value when relevant, required inputs, and an explicit unknown reason
when a bound cannot be justified. These are raw values; this spec does not choose neural
normalization or feature positions.

Live, credible, and theoretical values are peers, not a quality ranking. The useful
value depends on the decision: current live damage supports immediate tactics, while a
credible or theoretical maximum can better represent future threat. Hand-scaling
Alakazam attacks after draw-heavy turns are a canonical example. Unsupported bounds are
`null` with a reason, never guessed.

Approved stochastic exception (`HR-B05-002`): top-meta coin-flip profiles enumerate at
most zero through three consecutive heads. Outcomes requiring four or more consecutive
heads are explicitly marked as an omitted tail instead of expanded. This is the only
approved lossiness exception; every other approximation requires new human review.

## Audit families

The 19 broad families in `schema-family-worklist.json` organize review and may overlap.
They are not an additional semantic authority. The first engine-informed pass assigns
all 314 effects to at least one family with no gaps.

## Original encoder transition

Existing tags are rehomed rather than discarded. Examples:

- `snipe`, `counter_snipe`, `recoil`, and ability damage become targeted damage or
  damage-counter operations;
- `item_lock`, `cooldown`, `cubchoo`, and `retreat_lock` become action-rule changes with
  explicit target and duration;
- draw/search/mill/deckout become card movements with explicit source, destination, and
  visibility;
- energy acceleration and discard become card movement plus attachment/detachment;
- `conditional`, `probabilistic`, `revenge`, `outrage`, scale variables, and old
  conditions become program control or expressions;
- stat bakes become ordinary stat/damage/action/card-rule operations.

The keyword bag and separate attack/ability namespaces cease to be canonical. Derived
compatibility tags may reproduce them from the audited program.

Machine-readable contracts and the exhaustive diff are in
`semantic-schema-draft.json` and `category-diff-draft.json`.

## Illustrative meta-card mappings

These examples demonstrate the schema shape; their final audited payloads and engine
scenarios are still governed by B05–B08.

### Raging Bolt ex (`card_id: 63`) — Bellowing Thunder

The program first selects any number of Basic Energy attached across the player's
Pokémon, moves those selected cards to the discard pile, and then deals
`70 × selected_count` damage. The selected-count expression is shared by the cost and
damage nodes, so the two cannot drift. The live value is observation-derived; credible
and theoretical maxima remain separate audit fields.

### N's Zoroark ex (`card_id: 293`)

Trade activates at most once during the player's turn, requires discarding one card
from hand as a cost, and then draws two cards. Night Joker selects one attack belonging
to one of the player's Benched N's Pokémon and executes a reference to that selected
attack. The referenced attack retains its own ordered program instead of being reduced
to a generic “copy attack” flag.

### Area Zero Underdepths (`card_id: 1250`)

This continuous Stadium program conditionally changes each qualifying player's Bench
capacity to eight while they have a Tera Pokémon in play. Losing the condition or the
Stadium leaving play triggers ordered cleanup to five Benched Pokémon, with the player
who played the Stadium resolving first when both players must discard. Capacity,
condition lifetime, cleanup movement, and player ordering are therefore distinct
program components.
