# 14 — Effect-Baking Audit (Generalized/Symmetric Redesign)

Status: **audit complete for Tool/Stadium/Ability/Special-Energy sources (2026-07-16);
candidate list locked, condition predicates identified, no code.** Supersedes the scope
(not the mechanism) of `completed/06-effect-baking.md` / `completed/07-effect-baking-audit.md`.

## Purpose

Redo effect baking for the new symmetric, any-deck design (spec 11), reusing the old
`stat_bakes.py` mechanism (`BAKES` table keyed by card ID, `Modifier{stat, value, scope,
condition}`, a predicate registry) but scoped only to the meta card pool — no
regex/generalization fallback, unlike the tag vocabularies (11a/11b). If a card outside the
audited meta set has a bakeable effect, it simply gets no bake; that's an accepted gap here,
not a defect to fix.

**Scope, as instructed:** Pokémon Tools, Stadiums, Pokémon Abilities, and (added same day)
Special Energy — not Supporters, Items, or attack-triggered continual effects. See
"Explicitly excluded" below for what that ruled out and why it's flagged rather than
silently dropped. The Special Energy pass also resolves spec 11/13a's separate open question
of whether attached Special Energy needs its own identity representation — see "Candidate
audit — Special Energy" below.

## Engine-truth findings (2026-07-16, from reading the actual engine source)

Read directly from `Imitation-Learning/ptcg_engine/ptcgProgram 22/{State.h, EffectContinual.h,
ToJson.h, Card.h}` — this is the actual competition engine, not a black-box empirical probe
like the old spec 07's Phase 0. Findings:

| Category | Engine behavior | Baking needed? |
|---|---|---|
| HP | `state.getMaxHp`/`getHp` = `master.hp + card.hpChange` (± damage); **serialized directly** in `ToJson.h`'s `PokemonJson` (`hp`, `maxHp` keys). `hpChange` is written by the identical `EffectType::MaxHpChange` case regardless of source — verified for a Tool (Hero's Cape), another Tool (Cynthia's Power Weight), a Stadium (Gravity Mountain, negative value), and an Energy card (Grow Grass Energy). | **No.** Delete the `hp_delta`/`HP_BUFF` bake category entirely. This contradicts the old spec 06/07's assumption that only Tool HP was pre-baked and abilities/stadiums needed manual baking — that assumption doesn't hold against the actual source. |
| Resistance | No `EffectType` exists to change it — `Resistance` only appears as a `TargetType` (condition matching), never as a modifier. No card in this engine can dynamically change resistance. | **No, and never will.** Not a bake category at all; always the static printed value. |
| Retreat cost | `state.retreatCost(card)` computes the live effective value (`master.retreatCost + retreatCostChange + thisTurn.retreatCostChange`, `noRetreatCost` override) — **but this is never serialized** to the observation (`ToJson.h` has no `retreatCost` key in the live board state; only a static per-card-master dump exists in `Api.h`, which is just the printed database). | **Yes.** Real work, same as before. |
| Weakness | `state.getWeakness(card, master)` computes the live override (`noWeaknessNextEnemyTurn`, `weaknessIndex` via `EffectType::SetWeakness`) — **also never serialized.** | **Yes.** Real work, same as before. |
| Attack/Energy cost | Engine tracks live cost-reduction fields (`attackCostChangeColorless`, `attackCostDown`, etc.) internally — **also never serialized.** | **Yes**, per this session's explicit instruction to scan the meta pool for attack-cost effects and bake them case-by-case. |
| Outgoing/incoming damage (flat) | No equivalent single-field accessor found — inherently attacker/defender-context-dependent (e.g. Maximum Belt only applies vs. `{ex}` specifically), so there's no way the engine could pre-resolve this into one static per-card field the way it does for HP. | **Yes.** Real work, same as before — this is the old `damage_dealt_delta`/`damage_taken_delta` category, unaffected by the HP finding. |

## Candidate audit — Tools (11 meta rows, per spec 11b)

| Card | Tag (source: 11b) | Bake? | Proposed modifier |
|---|---|---|---|
| Hero's Cape | `HP_BUFF`(+100) | **No** | Engine-resolved, see above |
| Cynthia's Power Weight | `HP_BUFF`(+70, restricted to Cynthia's-named) | **No** | Engine-resolved |
| Air Balloon | `RETREAT_COST_MOD`(scope: holder; delta −2) | Yes | `{stat: retreat_delta, value: -2, scope: self, condition: tool_active}` |
| Gravity Gemstone | `RETREAT_COST_MOD`(scope: **both Active Pokémon**; delta +1; duration: while holder is Active) | Yes | `{stat: retreat_delta, value: +1, scope: all_active, condition: holder_is_active AND tool_active}` — note the unusual scope: this Tool affects *both* active Pokémon's retreat, not just its own holder |
| Brave Bangle | `STAT_BUFF`(scope: holder; +30 dmg vs opponent's `{ex}` Active, pre-W/R; gated on holder having no Rule Box) | Yes | `{stat: damage_dealt_delta, value: +30, scope: self, condition: tool_active AND NOT holder_has_rule_box, target_restriction: defender_has_rule_box}` — pre-W/R, matches engine's `DamageChangeEx` mechanism exactly |
| Maximum Belt | `STAT_BUFF`(scope: holder; +50 dmg vs opponent's `{ex}` Active, pre-W/R) | Yes | `{stat: damage_dealt_delta, value: +50, scope: self, condition: tool_active, target_restriction: defender_has_rule_box}` |
| Handheld Fan | `ENERGY_MOVE`, `ON_DAMAGED_TRIGGER` | No | Action effect (Energy repositioning), not a KO-math stat — stays tag-only |
| Deluxe Bomb | `COUNTER_PLACE`, `ON_DAMAGED_TRIGGER`, `SELF_CONSUME` | No | Direct damage-counter placement is a resolved action, not a passive modifier |
| Punk Helmet | `COUNTER_PLACE`, `ON_DAMAGED_TRIGGER` | No | Same as Deluxe Bomb |
| Lucky Helmet | `DRAW`, `ON_DAMAGED_TRIGGER` | No | Not KO-relevant |
| Survival Brace | `SURVIVE_KO`, `SELF_CONSUME`, `CONDITIONAL` | No | Sturdy-style survive-the-lethal-hit — explicitly out of scope per the old spec 06 boundary, carried forward unchanged |

## Candidate audit — Stadiums (17 meta rows, per spec 11b)

| Card | Tag (source: 11b) | Bake? | Proposed modifier |
|---|---|---|---|
| Nighttime Mine | `ATTACK_COST_MOD`(scope: all Tera Pokémon, both sides; delta +`{C}`) | Yes | `{stat: attack_cost_delta, value: +1 (generic/Colorless), scope: all, condition: holder_is_tera}` |
| Full Metal Lab | `DAMAGE_REDUCTION`(scope: both sides' `{M}`-type; −30 dmg, **post-W/R**) | Yes | `{stat: damage_taken_delta, value: -30, scope: all, condition: holder_is_type:Metal, ordering: post_wr}` — ordering matters: this applies *after* the Weakness/Resistance multiplier, unlike the pre-W/R deltas above, so `effective_damage`'s formula needs a post-multiplier subtraction step, not just an addend to the pre-multiplier base |
| N's Castle | `RETREAT_COST_MOD`(scope: both sides' N's-named; new cost 0) | Yes | `{stat: retreat_set, value: 0, scope: all, condition: holder_name_prefix:"N's"}` — new predicate needed, see below |
| Gravity Mountain | `HP_BUFF`(**−30**, scope: both sides' Stage 2) | **No** | Engine-resolved (negative values go through the identical `hpChange` accumulator, confirmed in engine source) |
| Jamming Tower | `SUPPRESS_TOOLS`(scope: both sides) | N/A — not a bake itself | **Cross-cutting condition**: gates every Tool-sourced bake above (Air Balloon, Gravity Gemstone, Brave Bangle, Maximum Belt) with an added `AND NOT jamming_tower_in_play` term |
| Team Rocket's Watchtower | `SUPPRESS_ABILITIES`(scope: both sides' `{C}`-type) | N/A — not a bake itself | **Cross-cutting condition**: gates every ability-sourced bake below when the ability's holder is Colorless-type and this Stadium is in play |
| Battle Cage | `EFFECT_IMMUNE`(counter-placement only) | No | Non-damage effect immunity, not KO-relevant |
| Neutralization Zone | `DAMAGE_IMMUNE_FROM`(scope: both sides' non-Rule-Box; only vs `{ex}`/`{V}`) | No | Full immunity stays tag-only, see "Explicitly excluded" |
| Festival Grounds | `CONDITION_IMMUNITY` | No | Status-condition immunity, not HP/damage math |
| Forest of Vitality | `EVOLUTION_RULE_MOD` | No | Not KO-relevant |
| Area Zero Underdepths | `BENCH_CAPACITY_MOD`(cap 8) | No | Already structurally accounted for in spec 13a's 18-word board budget (`1 active + 8 bench × 2 sides`) — no additional bake needed |
| Spikemuth Gym, Team Rocket's Factory, Community Center, Grand Tree, Risky Ruins, Surfing Beach | Search/draw/heal/evolve/switch/counter-trigger tags | No | Action effects, not passive stat modifiers |

## Candidate audit — Abilities (from spec 11a's 115-Pokémon pass)

| Card | Tag (source: 11a) | Bake? | Proposed modifier |
|---|---|---|---|
| Latias ex | `RETREAT_COST_MOD`(scope: own Basic; new cost 0) | Yes | `{stat: retreat_set, value: 0, scope: own_team, condition: ability_active AND is_basic}` |
| Lillie's Clefairy ex | `WEAKNESS_OVERRIDE`(scope: opponent's `{N}`-type; new weakness `{P}`) | Yes | `{stat: weakness_set, value: Psychic, scope: opponent_side, condition: ability_active AND holder_is_type:Dragon}` |
| Cynthia's Roserade | `STAT_BUFF`(scope: own Cynthia's-named; +30 dmg to opponent Active, pre-W/R) | Yes | `{stat: damage_dealt_delta, value: +30, scope: own_team, condition: ability_active AND attacker_name_prefix:"Cynthia's", target_restriction: is_opponent_active}` |
| Okidogi | `HP_BUFF`(+100) + `STAT_BUFF`(scope: self; +100 dmg, pre-W/R; `CONDITIONAL` on `{D}` Energy attached to self) | HP: **No**. STAT_BUFF: Yes | `{stat: damage_dealt_delta, value: +100, scope: self, condition: ability_active AND attacker_has_energy_type:Darkness, target_restriction: is_opponent_active}` |
| Seviper | `STAT_BUFF`(scope: self; +120 dmg, pre-W/R; `CONDITIONAL` on own `{D}` Mega Evolution `ex` in play) | Yes | `{stat: damage_dealt_delta, value: +120, scope: self, condition: ability_active AND own_side_has:mega_ex_type_darkness, target_restriction: is_opponent_active}` — condition is board-wide, not about the attacker itself; new predicate needed |
| Crustle, Shaymin, Cornerstone Mask Ogerpon ex, Rabsca, Fezandipiti | `DAMAGE_IMMUNE_FROM` (+ `EFFECT_IMMUNE` for Rabsca) | No | Full immunity stays tag-only, see "Explicitly excluded" |
| Team Rocket's Articuno | `EFFECT_IMMUNE`(non-damage effects only) | No | Not KO-relevant |

## Candidate audit — Special Energy (10 meta rows, per spec 11b)

**Resolution (2026-07-16), addressing spec 11/13a's open "does Special Energy need its own
identity representation" question:** any Special Energy effect that fits this spec's
existing bakeable categories (retreat cost, weakness, attack cost, flat damage deltas) gets
baked the same way as the Tool/Stadium/Ability entries above. Anything else falls back to a
new `special_energy_id` identity field (see spec 11's "Base field schema") — an imperfect
signal by design, the same "nearly lossless, not lossless" trade spec 11a's tag block
already makes, not something this audit needs to make airtight.

Going through all 10: **none qualify for a new bake entry.**

| Card | Tag (source: 11b) | Bake? | Why |
|---|---|---|---|
| Grow Grass Energy | `HP_BUFF`(+20, restricted to `{G}`-type) | **No** | Engine-resolved, same finding as every other HP source above |
| Mist Energy | `EFFECT_IMMUNE`(scope: holder) | No | Non-damage effect immunity, not a bakeable KO-math category — same exclusion as `DAMAGE_IMMUNE_FROM`/`EFFECT_IMMUNE` elsewhere in this audit |
| Rock Fighting Energy | `EFFECT_IMMUNE`(scope: holder; `{F}`-type restricted) | No | Same as Mist Energy |
| Telepath Psychic Energy | `SEARCH_BENCH`, `ON_ATTACH_TRIGGER` | No | Action effect |
| Enriching Energy | `DRAW`(4), `ON_ATTACH_TRIGGER` | No | Action effect |
| Spiky Energy | `COUNTER_PLACE`(2, target: attacker), `ON_DAMAGED_TRIGGER` | No | Direct counter placement is a resolved action, not a passive modifier — same exclusion as Deluxe Bomb/Punk Helmet |
| Team Rocket's Energy | `FLEXIBLE_ENERGY_PROVISION`, `SELF_CONSUME` | No | Affects which types this card can pay costs *as*, not the holder's retreat/weakness/damage — an `attached_energy_counts`/legality concern, not a KO-math stat |
| Ignition Energy | `SELF_CONSUME`, `FLEXIBLE_ENERGY_PROVISION`, `CONDITIONAL` | No | Same as Team Rocket's Energy |
| Prism Energy | `FLEXIBLE_ENERGY_PROVISION`, `CONDITIONAL` | No | Already fully handled by the Rainbow/Colorless conditional bucket mapping in spec 11's `attached_energy_counts` section — not a new category |
| Legacy Energy | `FLEXIBLE_ENERGY_PROVISION`, `PRIZE_DENIAL`(−1, once per game, on holder KO'd by attack damage) | No | `PRIZE_DENIAL` is a real KO-adjacent effect, but it modifies the *prize-count consequence* of a KO, not HP/damage/retreat/weakness/attack-cost — a genuinely different effect category this spec's bake mechanism was never built for. Flagged, not solved: falls back to the identity field like everything else in this table. |

**New field: `special_energy_id`.** A 10-dim identity vector (one per Special Energy card
in the meta pool, per spec 12's census), living as a compact live-state field on the host
Pokémon word alongside `attached_energy_counts` — same "compact field, no separate token"
treatment as `tool_template`. Presence-based (does at least one copy of this ID appear among
the holder's attached Energy), not a count — `attached_energy_counts`' bucket counts already
answer the "how much" question; this field only exists to give the model *some* signal for
the non-bakeable effects in the table above (`EFFECT_IMMUNE`, `DRAW`, `COUNTER_PLACE`,
`FLEXIBLE_ENERGY_PROVISION`, `PRIZE_DENIAL`, etc.) that don't fit any KO-math bake. Not
guaranteed lossless for those effects — that's an accepted trade, not a gap to close later.
**Open detail:** whether multiple *different* Special Energy IDs simultaneously attached to
one Pokémon need to all show up (a multi-hot, not a strict single-select) — presumed yes,
same reasoning as `energy_cost`'s multi-type vector, not yet explicitly confirmed.

## New condition predicates needed (extending the old registry)

The old registry (`is_active`, `full_hp`, `has_tool`, `attacker_is_fire`/`attacker_is_fighting`,
`attacker_is_basic`/`attacker_is_evolution`, `attacker_has_rule_box`, `holder_is_fire`/
`holder_is_fighting`/`holder_is_type:{X}`) generalizes cleanly except for two things it never
needed under the old fixed-opponent design:

- `attacker_has_rule_box` → needs a symmetric `defender_has_rule_box` too (Brave Bangle/
  Maximum Belt key off the *target's* rule-box status, not the attacker's — the old design
  only ever needed the attacker-side version since our side was fixed and never held these
  Tools).
- `holder_is_fire`/`holder_is_fighting` → generalize to `holder_is_type:{X}` over all types
  (already the stated pattern, just needs the full 9-type range, not the old 2-type subset).

Net new predicates this audit surfaced:
- `tool_active` / `ability_active` — holder's Tool/Ability isn't currently suppressed
  (`AND NOT` the relevant `SUPPRESS_*` Stadium condition) *and* the source card is actually
  attached/in-play. Replaces the implicit always-on assumption the old registry didn't need
  to state, since nothing in the old meta suppressed Tools/Abilities.
- `holder_name_prefix:{X}` — matches a card-family naming convention (N's, Cynthia's,
  Team Rocket's). Needed for N's Castle, Cynthia's Roserade.
- `own_side_has:{condition}` — a board-wide existence check independent of the attacker's
  own identity (Seviper's gate is about the *board*, not about itself). The old registry's
  predicates were all evaluated on `(holder, attacker, board)` for a single Pokémon; this is
  the first case needing a pure board-level existence check.
- `holder_is_tera` — needed for Nighttime Mine.
- `is_basic` — needed for Latias ex (already implied by `evolutionType` data, just wasn't a
  named predicate before).

## Explicitly excluded (flagged, not silently dropped)

- **Full damage immunity** (`DAMAGE_IMMUNE_FROM`, `EFFECT_IMMUNE`) — carried forward
  unchanged from spec 06's original scope decision: these stay as tag-only signals in spec
  11a/11b's attribute block, not folded into the `attacks_survivable`/`attack_hits_opponent`
  hit-ratio math. Six cards affected (Crustle, Shaymin, Cornerstone Mask Ogerpon ex, Rabsca,
  Fezandipiti, Team Rocket's Articuno on the ability side; Neutralization Zone, Battle Cage
  on the Stadium side).
- **Sturdy-style survive-the-lethal-hit** (Survival Brace's `SURVIVE_KO`) — carried forward
  unchanged from spec 06's original scope.
- **Supporter/Item-sourced modifiers** — three cards surfaced during cross-referencing that
  carry the same bakeable tags as the Tool/Stadium/Ability candidates above, but are outside
  this pass's stated scope: Kieran, Black Belt's Training, Premium Power Pro (all
  `STAT_BUFF`, all Supporter/Item, all "this turn only" duration). Not included here because
  the scope for this pass was explicitly Tool/Stadium/Ability — flagged in case a future pass
  wants Supporter/Item-sourced temporary buffs covered too.
- **Attack-triggered continual effects** — Archaludon ex's `SELF_NO_WEAKNESS` (its own
  attack grants itself no-Weakness for the opponent's next turn) and Chikorita's
  `STAT_DEBUFF` (its attack reduces the opponent's outgoing damage for their next turn) are
  both KO-relevant and both map directly to real engine mechanisms (`NoWeaknessNextEnemyTurn`,
  a `DamageChangeActive`-style modifier) — but they're sourced from *attacks*, not
  Tools/Stadiums/Abilities, and the old `stat_bakes.py`'s `BAKES` table only ever keyed
  `"kind": "tool" | "ability" | "stadium"` — no `"attack"` kind existed. These also need
  turn-scoped tracking (activate on attack use, expire at a specific point), a different
  shape than a static per-card-ID lookup. Flagged as a real gap this cross-reference
  surfaced, explicitly out of this pass's stated scope, not solved here.

## Interfaces / seams

Extends `stat_bakes.py` (spec 06) with the new predicates above, generalized to the
symmetric board (any Pokémon can hold any of these bakes, not just our fixed deck / their
generic side). `hp_delta` and the whole `HP_BUFF` bake path are removed entirely — `hp_curr`/
`hp_max` read `hp`/`maxHp` straight from the observation. Resistance gets no predicate or
modifier path at all — it's always the static printed value from spec 11's base field
schema.

## Out of scope

- Code / implementation — this is a planning/audit deliverable, same convention as
  11/11a/11b/13a.
- Supporter/Item-sourced temporary buffs (see "Explicitly excluded").
- Attack-triggered continual effects (see "Explicitly excluded").
- Full damage immunity and Sturdy-style survival (unchanged exclusions from spec 06).
