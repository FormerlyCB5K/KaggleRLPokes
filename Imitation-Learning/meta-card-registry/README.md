# Top-Ladder Exact-Card-ID Semantic Registry

Status: Spec 12 complete. Registry schema `1.0.0`; formula schema `1.0.0`.

## Start here

`registry.json` is the canonical complete coverage registry. It contains exactly 232 cards and 314 effect rows. Card keys are decimal exact card IDs in numeric ascending order. Do not collapse printings, owners, forms, or biological species.

Python consumers may import `registry.py`; other languages should read the JSON directly. `card_ids.json` and `card_ids.py` contain the stable categorical vocabulary: 115 Pokémon, 99 Trainer, and 18 Energy IDs. Their disjoint union is the 232-ID one-hot vocabulary.

## Files

- `registry.json`: canonical 232-card coverage registry.
- `formulas.json`: canonical declarative registry for all 79 dynamic formulas, scenario fixtures, and formula-to-card/effect reverse indexes.
- `overrides.json`: generated 201-card special-override view; never edit it independently.
- `card_ids.json` / `card_ids.py`: exact-ID vocabulary and numeric indices.
- `registry.py`: small Python loader and lookup API.
- `schema.json`: schema versions, required fields, verdict enum, and semantic-program schema.
- `provenance.json`: frozen input hashes, engine identity, license scope, and human-review state.
- `validation.json`: mechanical acceptance checks and counts.
- `artifact-manifest.json`: deterministic hashes for every generated artifact except itself.

## Precedence and fallback

For a known ID, use the exact card entry first. Apply an effect-level override only where its verdict is `override_static` or `override_dynamic`. An `engine_baked` or `ordinary_field` row is a coverage/delegation record and must not be added again as a second feature. `generic_exact` means the generalized behavior was reviewed and is exact.

For an unseen ID, use ordinary printed fields plus the generalized text/effect parser. Never borrow an override because an unseen card shares a name, species, owner, or mechanic. Missing dynamic state remains explicit unknown/masked; never substitute zero.

## Card records

Each card has `identity`, `coverage_verdict`, ordered `attacks`, ordered `abilities`, other `effects`, `calculations`, provenance, and integration notes. `source_order` preserves every engine row—there is no historical two-attack/one-ability truncation. `program` is the canonical ordered semantic AST. Raw counts, HP, Energy, counters, timing, targets, and conditions remain unnormalized.

The later encoder spec owns ordinary live/static features: current/effective maximum HP, retreat, type, Weakness, Resistance, `new_in_play`, and zone position.

### An intuitive way to navigate one card

Think of a card entry as four layers:

1. `identity` says exactly which printing this is.
2. `attacks`, `abilities`, and `effects` preserve what the card can do, in source order.
3. Each semantic `program` describes the ordered operations: condition, target, value, timing, and side effects.
4. `calculations` points to any live formula whose value depends on board state, history, or randomness.

For card ID 743, Alakazam, `attacks[0]` is Powerful Hand. Its printed cost is retained, its `damage_kind` is `damage_counters`, and its program says to place two counters per card in the owner's hand on the opposing Active Pokémon. Its calculation points to `pokemon_01_alakazam_powerful_hand`, whose live raw result is `20 * own_hand_count` HP-equivalent while still preserving the crucial fact that the effect uses counters rather than ordinary attack damage.

The same pattern handles cards that do not fit one scalar:

- Mega Kangaskhan ex, card 756: Rapid-Fire Combo keeps base damage, repeated fair-coin control flow, exact `200 + 50 * heads`, and the separately approved practical 0–3-head table.
- Wellspring Mask Ogerpon ex, card 108: Torrential Pump is an ordered split effect—100 to the Active, optionally shuffle exactly three attached Energy, then 120 to one Benched target. It should not be flattened into “220 damage.”
- Team Rocket's Mimikyu, card 434: Gemstone Mimicry carries a Tera-only source gate and a referenced attack program. The copied program retains its own conditions and operations.
- N's Zoroark ex, card 293: Night Joker similarly references a selected Benched N's Pokémon attack rather than pretending every possible copied attack is a fixed property of Zoroark.

## A plausible attack/effect representation for the later encoder

This is guidance, not a final tensor contract. Once a Pokémon's ordinary fields are available—HP, type, retreat, Weakness, Resistance, position, and turn flags—a reasonable compiler can create one semantic token per source attack rather than one hand-written vector per card.

Conceptually, an attack token can contain:

- presence, source ordinal, currently payable, and currently legal;
- printed Energy cost by type and total cost;
- printed base damage, exact live damage, credible maximum, legal/theoretical maximum, and explicit-known masks;
- a damage-kind one-hot such as ordinary damage, damage counters, fixed KO, or no direct damage;
- multi-hot operation families derived from the AST: damage, counter movement, healing, zone movement, Energy attach/discard/provision, switch/gust, status, evolution, rule modification, Prize modification, information, and attack delegation;
- target/scope fields such as self, own Active, own Bench, opponent Active, opponent Bench, all Pokémon, or selected card;
- timing and duration fields such as attack resolution, once per turn, while in play, next turn, or Pokémon Checkup;
- condition/input-source fields: current observation, public-history tracker, private/hidden state, registry lookup, or stochastic result;
- scalar parameters with masks—for example counters per hand card, maximum selected Energy, heal amount, or Prize delta; and
- stochastic summaries where relevant: probability, expected value, enumerated practical outcomes, and an approximation flag.

The ordered `program` remains authoritative. The fixed fields above are compiled summaries that make learning efficient; they should not replace the AST when an effect has multiple ordered operations. A small sequence/set encoder over all attack tokens is safer than truncating to two attacks. It can either leave attack tokens separate for attention or pool them into a fixed-size `attack_summary`.

A plausible Pokémon-level composition is:

```text
pokemon_semantics = combine(all ordered attack tokens, ability/effect tokens)
pokemon_representation = concat(
    ordinary live/static Pokémon fields,
    pokemon_semantics,
    exact-card-ID one-hot
)
```

The exact-card-ID one-hot is therefore a high-precision identity backstop, not a substitute for attack meaning. The semantic portion lets the model generalize between cards that share operations, while the one-hot preserves meta-card-specific distinctions and overrides. Unknown values need companion masks; a hidden or unavailable quantity must not look like a real zero.

For Powerful Hand at 12 cards in hand, for example, the compiled attack token would mark Psychic cost, payable/legal state, damage counters, opponent-Active target, observation-direct hand count, multiplier 20 HP-equivalent per card, and live value 240. It would not apply Weakness or Resistance. For Torrential Pump, the token/program pair would preserve Active damage, the exact-three-Energy optional cost, the separate Bench target/damage, and their resolution order.

## Dynamic calculations

Look up `formula_key` in `formulas.json`. Every entry declares inputs, source/observability, raw output meaning, bounds or explicit unknown, algorithm handler/parameters, order, fallback, saturation, engine evidence, and scenarios. The executable reference used for parity testing is `../build_dynamic_formula_registry.py`; declarative metadata is authoritative and should be ported into the implementation rather than replaced by opaque lambdas.

Damage counters remain counter counts with `damage_kind=damage_counters`; a 10-HP equivalent may be derived for threat/KO logic without applying Weakness, Resistance, or attack-damage rules. Mega Kangaskhan's `HR-B05-002` practical table is the sole approved approximation; its exact evaluator accepts every nonnegative head count.

## Minimal Python usage

```python
from registry import get_card, formulas_for_card, unseen_fallback_contract

card = get_card(743)              # exact Alakazam printing
calculations = formulas_for_card(743)
fallback = unseen_fallback_contract(999999)
```

## Validation

From the repository root run:

```powershell
python Imitation-Learning/build_meta_card_registry.py
python Imitation-Learning/test_meta_card_registry.py
python Imitation-Learning/archive/spec12-development/run_archived_tests.py
```

The active registry suite has 11 tests. The archived development runner preserves the other 89 Part A/B tests. Together, the expected Spec-12 result is 100 passing tests, all 79 formulas and 237 scenarios reconciled, and identical hashes after a second registry build.

## Next task

Create a new specification to design and wire the full imitation-learning observation encoding. Combine this registry's difficult semantics with the ordinary fields owned by that spec. That implementation must choose feature layout, normalization, masks, tracker interfaces, and model integration; none of those choices are made here.
