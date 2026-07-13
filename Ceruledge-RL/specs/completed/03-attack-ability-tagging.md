# 03 — Attack & Ability Tagging (Opponent Cards)

## Purpose

Define how an arbitrary opponent card's attacks and ability are converted into the
fixed-width tag blocks consumed by the opponent-Pokémon vector
(`02-observation-encoding.md`). Three-tier precedence, applied per card:

1. **Override table** (`attack_overrides.py`, repurposed — see below): hand-authored
   entry fully replaces extraction for that card.
2. **Keyword/regex extraction** from the card's effect text (`effect_features.py`,
   extended): damage and cost always come from `card_data.py`; tags from the trigger
   patterns below.
3. **Zeros**: no override, no keyword hit → all tags 0.0. An untagged card reads as a
   vanilla attacker (printed damage, cost, nothing else) — accepted behavior; specific
   decks get hard-coded in later iterations.

## Attack block schema — 18 dims, 2 blocks per card

Attacks ordered **cheapest-first** (existing `card_data.py` order). Single-attack
cards: second block all zeros.

| # | Field | Value / normalization | Trigger (tier 2) |
|---|---|---|---|
| 0 | energy_cost | total cost, type-blind, / 5 clipped | card data |
| 1 | damage | printed or overridden damage, clipped at 270, / 270 | card data / override |
| 2 | SNIPE | bench damage N / 100 | `"{N} damage"` … `"opponent's Benched Pokémon"` or `"of your opponent's Pokémon"` — extend the existing `_RX_BENCH` pattern |
| 3 | counter_snipe | N counters × 10 / 100 (damage-equivalent) | `"Put {N} damage counters"` … `"opponent's"` … `"Pokémon"` |
| 4 | conditional | bool — some extra condition must hold for the attack | **override table only** (no keyword) |
| 5 | item_lock | bool | `"can't play any Item cards"` |
| 6 | cooldown | bool — attacker must skip a turn after using this | `"During your next turn, this Pokémon can't use"` |
| 7 | energy_accel | N energy attached / 3 | `"attach up to {N}"` |
| 8 | draws_cards | N / 6 | `"draw a card"` (N=1), `"draw {N} cards"` |
| 9 | discard_energy | N / 5; "discard all Energy" → N = this attack's total cost | `"discard {N} Energy"`, `"discard {N} energy cards"`, `"discard all Energy"` |
| 10 | Cubchoo | bool — blocks our attacking | `"the Defending Pokémon can't use attacks"` |
| 11 | deckout | bool — mill/deck-out strategy | `"opponent's deck"`, `"Each player draws"` |
| 12 | probabilistic | bool — coin flips / random effects | `"Flip a coin"` (reuse existing coin-flip regexes), `"top {N} cards of your deck"` |
| 13 | revenge | bool — more damage if our Pokémon was KO'd last turn | `"Knocked Out"` … `"opponent's last turn"` |
| 14 | outrage | bool — damage scales with own damage taken | `"each damage counter on this Pokémon"` |
| 15 | retreat_lock | bool — opponent cannot retreat next turn | manual override pending next full audit |
| 16 | immunity | bool — prevents incoming attack damage next turn | manual override pending next full audit |
| 17 | recoil | self-damage HP / 70, clipped | manual override pending next full audit |

### Opponent max damage (feeds `attacks_survivable` on our side)

`opp_active_max_damage = max(block.damage_raw for the active's attacks)` using
overridden damage where present, otherwise the printed number as-is. Known bad for
some variable-damage decks — fix by adding overrides, not parser cleverness.

## Ability block schema — 11 dims, 1 block per card

Only the card's **first ability** is encoded; a second ability is ignored (rare).

Numeric tags (DRAW, DAMAGE, ENERGY_ACTIVE, ENERGY_BENCH, SEARCH, HEAL): extract the
number from the ability text; if the text matches the trigger but contains no number
and says `"once during your turn"`, use **N = 1**.

| # | Field | Value / normalization | Trigger (tier 2) |
|---|---|---|---|
| 0 | DRAW | N / 6 | `"draw {N} cards"`, `"draw cards until {…N}"` (use the target hand size as N) |
| 1 | DAMAGE | N counters × 10 / 100 | `"put {N} damage counter"` (abilities deal counters, not damage) |
| 2 | IMMUNITY | bool | **override only** — Crustle, Sylveon, Cornerstone Mask Ogerpon (see seed list) |
| 3 | GUST | bool | `"switch in 1 of your opponent's Benched"`; override additionally seeds Hariyama, Hop's Dubwool |
| 4 | ENERGY_ACTIVE | N / 3 | `"during your turn, you may attach a Basic"` (energy anywhere / active) |
| 5 | ENERGY_BENCH | N / 3 | same pattern + `"Benched"` |
| 6 | SEARCH | N / 3 | `"Search your deck"` |
| 7 | BARRIER | bool — protection effects; signals "rarely worth KOing" | **override only** — Shaymin, Rabsca, Psyduck, Patrat |
| 8 | HEAL | counters: N × 10 / 100; `"heal {N} damage"`: N / 100 | `"heal"` |
| 9 | MILL | bool — forces us to draw toward deck-out | `"each player draw"`, `"opponent's deck"` |
| 10 | SWITCH | bool — retreat reduction or free switching | `"Your {…} Retreat Cost"`, `"Switch one of your {…} Pokémon"`, `"switch your Active Pokémon"` |

## Override table (`attack_overrides.py`, repurposed)

The existing file's never-populated `CardStats` full-replace schema is **replaced**.
New entry shape, keyed by card_id:

```python
OVERRIDES: dict[int, dict] = {
    card_id: {
        "attacks": [ {attack-block fields, raw un-normalized values}, ... ],  # optional
        "ability": {ability-block fields, raw un-normalized},                 # optional
        "max_damage": int,                                                    # optional
    },
}
```

An override, when present for a card, **fully replaces** keyword extraction for the
sections it provides (an entry with only `"ability"` still lets attacks go through
tier 2). Keep the file's documented meta-deck card-ID lists — they are the worklist
for populating overrides.

### Seed entries (author these with the initial implementation)

- **Budew (235)** — attack: `item_lock = 1`.
- **Frillish** — attack: `item_lock = 1` (identical effect to Budew; resolve card_id
  from card data).
- **Tyranitar** — its continuous item lock is handled in the **global** `item_locked`
  flag (active-check), not here; no attack/ability tag needed for it. Resolve id for
  the global check.
- **Cubchoo (506)** — attack: `Cubchoo = 1`.
- **Deck-out line (97, 493, 494, 98, 495, 164)** — Litwick/Lampent/Chandelure +
  Comfey: `deckout = 1` on the relevant attacks/abilities (MILL for abilities).
- **Mega Abomasnow (723)** — `probabilistic = 1` (random effect without coin-flip
  text).
- **Munkidori** — ability ("move up to 3 damage counters from 1 of your Pokémon to 1
  of your opponent's Pokémon"): **HEAL = 3 counters AND DAMAGE = 3 counters** (0.3
  each after normalization). Resolve card_id.
- **IMMUNITY** — Crustle (345, 533 line: 344/532 Dwebble), Sylveon, Cornerstone Mask
  Ogerpon (117, 386): `IMMUNITY = 1`. Resolve missing ids.
- **BARRIER** — Shaymin, Rabsca, Psyduck, Patrat: `BARRIER = 1`. Resolve ids.
- **GUST** — Hariyama, Hop's Dubwool: `GUST = 1`. Resolve ids.
- **conditional** — populated during the audit pass (below); starts empty.

Card ids marked "resolve" must be looked up from the card CSV / `all_card_data()` at
implementation time, not guessed.

## Parser implementation notes

- Extend `effect_features.py`; reuse its normalization helper (`_norm`), coin-flip
  regexes (→ probabilistic), and `_RX_BENCH` (→ SNIPE). The old 27-dim MODIFIER
  vector and `EFFECT_KEYWORDS` bag are superseded by these tag schemas for this
  encoder (leave them in place if other code still imports them).
- All extraction is case-insensitive; normalize curly quotes (existing `_norm`).
- Numbers written as words ("draw two cards") — handle at least one…six.

## Validation: dump script + audit pass (required deliverable)

The keyword trigger lists above are **provisional**. The implementation MUST include a
dump script (`old/audits/tagging/dump_tags.py`) that iterates the full card pool and emits, per
card: card name/id, each attack's raw effect text next to its extracted 18-dim block
(raw values, not normalized), and the ability text next to its 11-dim block, in a
greppable/reviewable format (markdown table or TSV).

Planned process after implementation: a manual audit pass reads every card's effect
text, compares it against the dump, and flags mismatches/ambiguities for keyword
refinement and new override entries. Build the dump script to make that diff easy.

## Out of scope

- **Tool card tagging** — no tag schema for Tools. Tool effects that map onto encoded
  stats are baked into those stats per `02-observation-encoding.md` (§ Tool baking);
  everything else is covered by the bare `has_tool` flag.
- Encoding attack effects on **our** Pokémon (species one-hot carries them).
- Trainer/Energy card attribute encoding (opponent zones aren't encoded at all).
- EV-weighting probabilistic damage (tag flag only; `expected_heads` not used here).
- Multi-ability cards beyond the first ability.
