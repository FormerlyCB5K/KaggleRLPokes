# 11b — Trainer/Energy Attribute Tag Vocabulary

Part of [`11-pokemon-word-observation-encoding.md`](11-pokemon-word-observation-encoding.md).

Status: **Complete and independently re-verified (2026-07-16); transcribed into code
(2026-07-21).** All phases (0-4) done: all 109 Trainer+Energy rows tagged across 5 class
batches, coverage/recall/precision validated, 12-card non-meta spot-check, field list
locked at 91 dimensions (**corrected to 53 during code transcription** — the presence-bit
collapse already applied to spec 11a's Pokemon tag block applies here too, see Phase 4's
amendment note). A subsequent `/code-review` audit pass re-extracted every regex and
assignment fresh from both this file and spec 11a's and found 5 regexes here that had been
validated in scratch scripts but never actually written into this catalog
(`DISCARD_RETRIEVE`, `DISCARD_OPP_BOARD`, `ENERGY_MOVE`, `SELF_CONSUME`,
`FLEXIBLE_ENERGY_PROVISION`) — all fixed, see spec 11a's "Code-review audit and fix pass"
for the full combined writeup and final numbers (310/310 rows, 285/285 recall pairs, 0
unintended false positives across both specs). Transcribed into
`Imitation-Learning/observation/trainer_energy_tag_catalog.py` +
`trainer_energy_meta_tags.py`, wired into `trainer_energy_static.py` — see
`Imitation-Learning/observation/TRAINER_ENERGY_TAG_TRANSCRIPTION_REPORT.md` for the full
writeup.

**Phase 0 correction note.** A fresh extraction from `registry.json` (109 rows: 99 Trainer +
10 Special Energy, `effects` section — Basic Energy correctly has none), with a walker that
explicitly handles `repeat` and `choice` node kinds from the start (a bug class that cost
real rework in spec 11a's Phase 0/2 — see that spec's Phase 2a for the postmortem, applied
here upfront instead of discovered later), gives: `move_cards` 102, `shuffle_cards` 36,
`switch_active` 10, `modify_damage_rule` 8, `modify_stat` 7, `inspect_cards` 7,
`place_damage_counters` 4, `evolve` 4, `apply_special_condition` 4, `heal_damage` 4,
`provide_energy` 10, `modify_effect_rule` 2, `select_targets` 2, `enforce_bench_capacity` 2,
and 13 Trainer-specific rule-modification kinds at 1 each (matching the list below). Node
count distribution: 46 rows need 1 operation, 37 need 2, 11 need 3, 12 need 4, 2 need 5, 1
needs 6. Close to, but not identical to, the numbers in the original draft below (off by a
few on several counts, `provide_energy` wasn't broken out in the original Trainer-side
table) — consistent with spec 11a's finding that hand-drafted census tables drift from a
fresh extraction by a small amount that isn't worth forensic reconciliation, since Phase 1
tags every row from its own ground truth, not from this aggregate table. Also confirmed: a
`choice` (pick-one-of-N) top-level node is a real, recurring Supporter pattern here (e.g.
Kieran, "Choose 1: ..."), not a one-off the way it was in 11a — Phase 1 needs an explicit
policy for it from the start (see Working design decisions once Phase 1 begins).

## Purpose

Design the analogous widened tag vocabulary for Trainer and Energy cards — the same
philosophy as spec 11a (card-ID identity is primary where a card is known; tags are a
fallback/warm-start, nearly-lossless-not-lossless), applied to a different card shape.

Unlike Pokémon, Trainer/Energy cards have no board-slot analogue and no static/live
split of their own. Most Trainers (Item, Supporter — 71 of the 99 audited Trainer cards)
resolve once and leave no persistent state on the card itself. Pokémon Tools and Stadiums
do have an ongoing board effect, but that effect is already delegated elsewhere: a Tool's
consequence lives in the attached Pokémon's live state (spec 11's `has_tool` and
stat-baked modifiers), and a Stadium's consequence lives in the future global word (spec
13's stadium one-hot and stat-baked modifiers). This spec only needs to characterize each
card's own effect signature — what it does when played — not re-represent where that
effect's consequence eventually shows up.

**This is a planning deliverable, not a parser.** As with spec 11a, the concrete output
is: (1) a tag catalog and meanings; (2) a detection rule (regex and/or keyword logic) per
tag, ready to hand to a future implementation pass, meant to fire on never-before-seen
Trainer/Energy cards; (3) a complete manual tag assignment for all 109 audited Trainer/
Energy effect rows, built from the registry's exact ground truth; and (4) that manual
assignment doubling as the production lookup table for the 117 known meta Trainer/Energy
cards — detection rules are only ever exercised on cards outside that vocabulary. No code
is written as part of this spec.

## Behavior — the review process

Same four-phase shape as spec 11a, adapted to what the registry census actually shows for
this card class — the underlying operation vocabulary is meaningfully different (and
noisier) than the Pokémon side, so it is reviewed separately rather than assumed to be a
subset.

**Phase 0 — Starting vocabulary from the operation-kind census.** Across the 99 audited
Trainer cards (32 Item, 39 Supporter, 11 Pokémon Tool, 17 Stadium; 99 effect rows, zero
cards with no effect row):

| Operation kind | Occurrences |
|---|---:|
| `move_cards` | 104 |
| `shuffle_cards` | 35 |
| conditional branches | 12 |
| `switch_active` | 9 |
| `inspect_cards` | 7 |
| `modify_damage_rule` | 7 |
| `modify_stat` | 6 |
| `evolve` | 4 |
| `apply_special_condition` | 4 |
| `heal_damage` | 4 |
| `place_damage_counters` | 3 |
| `select_targets`, `enforce_bench_capacity` | 2 each |
| `move_attachment`, `replace_knock_out`, `reveal_cards`, `conceal_cards`, `remove_special_conditions`, `modify_condition_rule`, `suppress_card_effects`, `modify_card_movement_rule`, `modify_bench_capacity`, `suppress_abilities`, `modify_evolution_rule`, `modify_counter_rule`, `modify_attack_cost` | 1 each |

Node-count distribution: 46 rows need 1 operation, 28 need 2, 12 need 3, 10 need 4, 2
need 5, and 1 needs 6 — visibly heavier than the Pokémon side, where the maximum was 3.
Supporters in particular tend to chain several sub-effects (search, then draw, then
shuffle) in one card.

Across the 18 audited Energy cards (8 Basic, 10 Special; 10 effect rows total): 8 of the 8
Basic Energy cards have **no effect row at all** — they need only the ordinary type/
identity fields already handled elsewhere, no new tags. The 10 Special Energy rows are
simple by comparison to Trainers: node-count distribution 1/8/1 (one 1-node row, eight
2-node rows, one 3-node row), dominated by `provide_energy` (12 occurrences) with a few
`modify_effect_rule`, `modify_attachment_rule`, `modify_stat`, `modify_prize_rule` rows.

Where a Trainer operation kind overlaps one already tagged in spec 11a (`move_cards` →
`DRAW`/`DISCARD`/`SEARCH_ATTACH`, `shuffle_cards` → `MILL`, `heal_damage` → `HEAL`,
`modify_stat` → `STAT_BUFF`/`STAT_DEBUFF`, `switch_active` → `SWITCH_FORCE`,
`apply_special_condition` → `CONDITION`, `place_damage_counters` → `COUNTER_PLACE`,
`evolve` → `EVOLVE_EFFECT`), reuse and extend the same named tag rather than defining a
parallel one — keeps the two vocabularies consistent if they're ever consumed by a shared
downstream component. The remaining kinds are Trainer-specific rule-modification effects
with no Pokémon-side analogue (`suppress_abilities`, `modify_bench_capacity`,
`modify_evolution_rule`, `modify_card_movement_rule`, `replace_knock_out`,
`enforce_bench_capacity`, `modify_counter_rule`, `modify_attack_cost`,
`modify_condition_rule`, `suppress_card_effects`) and need their own new tag families.

**Phase 1 — Batched walkthrough, producing the manual tag assignment.** Same discipline as
11a, run separately per class (Item/Supporter, Tool, Stadium, Energy) since their typical
shapes differ enough that one combined pass would blur useful groupings. Assign tags from
the registry's exact ground truth, not English text or the old encoder. Tool and Stadium
rows specifically only need their *triggering/ongoing-rule signature* captured here — not
a restatement of how that rule later modifies a Pokémon's or the board's live state, which
spec 11/13 already own. This pass's output — the row-by-row assignment for all 109 rows —
becomes the production lookup table for the 117 known Trainer/Energy IDs (see Interfaces).

**Phase 2 — Coverage pass, then draft detection rules.** First confirm the target bar: no
all-zero rows across the 99 Trainer + 18 Energy cards; any remaining gap explicitly listed
for sign-off. Then draft each tag's detection rule (regex/keyword logic, magnitude capture
where applicable — same schema as 11a) and check it against the English text of every
meta-card row already manually assigned that tag.

**Phase 3 — Non-meta sanity spot-check**, same as 11a, against Trainer/Energy cards
outside the 117-ID vocabulary.

**Phase 4 — Lock the field list, widths, normalization, and known-gaps list.**

## Deliverable format

Same per-tag schema as spec 11a: name, meaning, detection rule, magnitude capture (if
any), and the full list of assigned rows by card ID and effect ID. The complete 109-row
assignment table lives in this file as the output of Phase 1/2, doubling as the audit
record and the runtime lookup table for the 117 known cards.

## Working design decisions (established during Phase 1, Supporter batch)

Two decisions specific to Trainer cards, beyond the two already established in 11a (base
`DAMAGE` tag; tag block = effect content not activation triggers), both anticipated by this
spec's own Phase 0 note that Trainer/Energy needed its own review rather than assuming
11a's policies transfer unchanged:

1. **"You can use this card only if X" usage-restriction clauses are activation-legality
   gates for the whole card**, structurally the same *kind* of thing as a Pokémon ability's
   "once during your turn" (11a's working decision #2) — dropped entirely, not tagged,
   *unless* the clause itself describes a real cost the player pays (most commonly "only if
   you discard another card from your hand"), in which case the cost gets its own content
   tag (`DISCARD_SELF`) while the bare legality aspect is still dropped. This is a
   pervasive pattern here — 7 of the first 39 Supporter rows carry one — unlike 11a, where
   in-program `conditional` branches (not whole-card usage gates) were the norm. Turn-order
   gates ("only if you go first"), Prize-count gates ("only if you have more/fewer Prize
   cards than your opponent"), and board-state gates ("only if any of your ... were Knocked
   Out") are all dropped the same way; the effect that follows is tagged as unconditional,
   since once the card is legally playable its effect always fully resolves.
2. **A `MULTI_CHOICE` companion flag for "Choose 1 of N" menu cards.** Confirmed in Phase 0
   as a real, recurring Supporter shape (not a one-off the way Cynthia's Garchomp ex's
   nested `choice` node was in 11a). Policy: tag every constituent option's own content tag
   normally, plus `MULTI_CHOICE` on the row as a whole, meaning only one of the tagged
   effects actually resolves per use, player's choice — mirrors the `CONDITIONAL` policy
   (tag the gated content, flag that it's gated) rather than inventing per-option
   sub-structure.

## Tag catalog additions (Trainer/Energy-specific, Phase 1 Supporter batch)

New tags not carried over from spec 11a, each validated against its own source row's text
at draft time (not deferred to a later pass, per the process fix from 11a's postmortem):

| Tag | Meaning | Detection rule (draft) | Magnitude capture |
|---|---|---|---|
| `HAND_RESET` | Shuffles the stated player's (or both players') hand into their deck, typically as a precursor to a fresh draw. Distinct from `DISCARD_SELF` (goes to discard, not deck) and from Pokémon's `SELF_MILL` (Pokémon-specific). | `/shuffle(?:s)? (?:your\|their) hand into (?:your\|their) deck/i` | which player(s) |
| `DISCARD_RETRIEVE` | Retrieves card(s) from the user's own discard pile directly into hand — a capped count, or a single unspecified card. Distinct from `REVIVE_FROM_DISCARD` (Pokémon-only, goes to Bench, spec 11a) and `SEARCH_HAND` (comes from the deck, not the discard pile). | `/put (?:up to (\d+)\|a) .+ from (?:your\|their) discard pile into (?:your\|their) hand/i` — widened after a code-review audit found Night Stretcher's "Put **a** Pokémon or a Basic Energy card from your discard pile into your hand" (no "up to N") failed the original count-only pattern | group 1 = count cap if present; combination criteria |
| `ENERGY_RETURN_TO_HAND` | Returns Energy attached to a target Pokémon to the owner's hand. Distinct from Pokémon's `SELF_RETURN_TO_HAND` (returns the Pokémon itself, spec 11a) — this returns only the attached Energy. | `/put all Energy attached to (?:that\|this) Pok[eé]mon into your hand/i` | scope: target Pokémon |
| `SEARCH_DECK_TOP` | Searches the deck for card(s) and places them back on top of the deck in a chosen order — a pure sequencing/setup advantage, no hand or board change. | `/search your deck for (\d+) cards?,.*put (?:those cards\|them) on top of (?:it\|your deck)/i` | group 1 = count |
| `MULTI_CHOICE` | Companion flag: this row presents 2+ mutually exclusive effect options — only one resolves per use, player's choice. All constituent option tags are listed on the same row; this flag marks that they don't all happen simultaneously. | n/a — set from the registry's top-level `choice` node presence, mirroring `CONDITIONAL`'s programmatic-only detection for known cards | none |
| `EVOLVE_FROM_HAND` | Evolves a chosen own Pokémon directly using a card already in hand (no deck search), typically skipping an intermediate evolution stage. Distinct from `EVOLVE_SEARCH` (searches the deck). | `/if you have a Stage 2 card in your hand that evolves from that Pok[eé]mon.*(?:put\|evolve)/i` | qualifier: which stage is skipped |
| `DISCARD_OPP_BOARD` | Discards card(s) attached to / on the opponent's board (Energy, Tools) — as opposed to `DISCARD_OPP` (their hand). A real gap identified during spec 11a's Phase 3 non-meta spot-check (Cobalion) that turns out to recur inside 11b's own audited 117-card set, so it gets a real tag here rather than staying a logged gap. | `/discard (?:a\|an) (?:Special )?Energy from 1 of your opponent's Pok[eé]mon\|[Cc]hoose up to (\d+) Pok[eé]mon Tools attached to Pok[eé]mon/i` — added a second alternative after a code-review audit found Tool Scrapper's "Choose up to 2 Pokémon Tools attached to Pokémon (yours or your opponent's) and discard them" didn't match the Energy-only original pattern | card type filter (Special Energy / any Energy / Tool); qualifier: opponent-only vs. either side |
| `DISCARD_TO_DECK` | Shuffles card(s) from the user's own discard pile back into their deck (not hand — contrast `DISCARD_RETRIEVE`, not board). | `/shuffle up to (\d+) .+ from your discard pile into your deck/i` | group 1 = count cap; card-type filter |
| `ENERGY_MOVE` | Moves attached Energy from one Pokémon to another. Default scope is the user's own side (own → own, the Energy analogue of `COUNTER_MOVE`'s conserved redistribution); a `scope=opponent_internal` qualifier covers the rarer triggered case where a Tool moves the *attacker's* Energy among the attacker's own side. Distinct from `ENERGY_ACCEL` (attaches from an off-board source, not board-internal movement). Another real Phase-3-identified gap (Forretress, spec 11a) that recurs in-sample here. | `/[Mm]ove (?:a\|an) (?:Basic )?Energy from 1 of your Pok[eé]mon to another of your Pok[eé]mon\|move an Energy from the Attacking Pok[eé]mon to 1 of your opponent's Benched Pok[eé]mon/i` — added the second alternative (the `scope=opponent_internal` phrasing) after a code-review audit found Handheld Fan's own triggered text didn't match the own-side-only original pattern, despite that shape being explicitly documented in this row's own meaning column | count; `distribution` qualifier if scaled; `scope` qualifier |
| `SELF_CONSUME` | The card discards/removes itself from play after its effect resolves, or automatically at a stated timing point (e.g. end of turn) — a one-shot Tool/Stadium/Energy, not a persistent one. | `/discard this card\|discard it at the end of your turn/i` — added the second alternative after a code-review audit found Ignition Energy's "discard it at the end of your turn" (an automatic, timing-based self-consume, not the outcome-gated "discard this card" phrasing every other assigned row uses) failed the original pattern | none |
| `SURVIVE_KO` | Prevents a Knocked-Out result once, leaving the Pokémon at a stated minimum HP — typically gated on the holder being at full HP beforehand. A genuinely new mechanic, absent from all of spec 11a's Pokémon vocabulary (Pokémon attacks/abilities have no self-preservation-from-KO shape; this is Tool-specific). | `/would be Knocked Out by damage from an attack.*it is not Knocked Out/i` | minimum HP left |
| `ON_DAMAGED_TRIGGER` | Companion flag: this row's effect only fires when the card's holder, while in the Active Spot, is damaged by an opponent's attack — fires even if the holder is simultaneously Knocked Out. A recurring, strategically meaningful Tool trigger shape (4 of 11 audited Tools use it), kept as an explicit flag rather than folded into ad hoc prose each time, the same way `CONDITIONAL`/`MULTI_CHOICE` are explicit companion flags rather than free text. | `/is in the Active Spot and is damaged by an attack from your opponent's Pok[eé]mon/i` | none |
| `ATTACK_COST_MOD` | Modifies the Energy cost required to use attacks for a stated scope of Pokémon. No Pokémon-side analogue — Stadium-specific. | `/attacks used by .+ cost \{C\} more/i` | scope; cost delta |
| `SUPPRESS_TOOLS` | Pokémon Tools currently in play have no effect, for a stated scope. | `/Pok[eé]mon Tools attached to .+ have no effect/i` | scope |
| `CONDITION_IMMUNITY` | A scope of Pokémon is cured of, and then immune to, Special Conditions — typically gated on a board-state qualifier (e.g. having any Energy attached). Distinct from a single Pokémon's coin-flip-gated `DAMAGE_IMMUNE_FROM`/`EFFECT_IMMUNE` (spec 11a) — this is a battlefield-wide status-condition-specific immunity. | `/recovers? from all Special Conditions and can't be affected by any Special Conditions/i` | scope; gating qualifier |
| `EVOLUTION_RULE_MOD` | Modifies the normal evolution-timing restriction (e.g. allows evolving a Pokémon the same turn it was played) for a stated scope. | `/can evolve into .+ during the turn they play those Pok[eé]mon/i` | scope; which restriction is lifted |
| `DAMAGE_REDUCTION` | Reduces incoming damage by a stated flat amount for a scope of Pokémon — partial mitigation, distinct from `DAMAGE_IMMUNE_FROM`'s full block. | `/take (\d+) less damage from attacks/i` | group 1 = reduction amount; scope |
| `SUPPRESS_ABILITIES` | A scope of Pokémon have their Abilities disabled. | `/Pok[eé]mon in play .+ have no Abilities/i` | scope |
| `BENCH_CAPACITY_MOD` | Modifies the maximum Bench size for a scope of players, typically gated on a board-state qualifier, with a stated reversion behavior if the condition lapses or the card leaves play. | `/can have up to (\d+) Pok[eé]mon on their Bench/i` | group 1 = new cap; gating qualifier; reversion behavior |
| `ON_ATTACH_TRIGGER` | Companion flag: this row's effect only fires at the moment this card is attached from hand — a second recurring trigger shape alongside `ON_DAMAGED_TRIGGER` (2 of 10 audited Special Energy cards use it). | `/[Ww]hen you attach this card from your hand to/i` | none |
| `FLEXIBLE_ENERGY_PROVISION` | This card provides more than the ordinary single fixed-type Energy unit — multiple units freely split across a stated type set, "every type, 1 at a time," or the same type repeated (e.g. "provides {C}{C}{C} Energy instead"), optionally gated on a board-state qualifier (e.g. only if attached to a Basic/Evolution Pokémon). Ordinary single-type provision is a printed static field handled elsewhere, not part of this tag block (parallel to `DAMAGE` being the base case for attacks) — this tag exists specifically for the non-ordinary cases. | `/provides? .*(?:in any combination of\|every type of) .*Energy\|provides \{(\w)\}(?:\{\1\}){1,} Energy instead/i` — the repeated-unit alternative was validated against Ignition Energy's "provides {C}{C}{C} Energy instead" when this tag was first drafted, but only the first alternative was actually written into this row; a code-review audit caught the gap | unit count; type set; gating qualifier if conditional |
| `PRIZE_DENIAL` | Reduces the number of Prize cards the *opponent* takes when they KO the card's holder — a denial effect, the inverse of `EXTRA_PRIZE` (which benefits the effect's own controller). Typically a once-per-game-limited effect. | `/that player takes (\d+) fewer Prize cards?/i` | group 1 = reduction amount; once-per-game qualifier |

## Manual assignment table — Phase 1 progress

**Supporter batch (39 rows, frequency order).** Ground truth from each row's `program` and
English text jointly (Trainer effect programs are closer to natural-language paraphrase
than Pokémon's, per this spec's own Purpose section — the registry's structured fields and
the printed text agree far more often here than diverge).

| Card | Effect ID | Tags assigned |
|---|---|---|
| Hilda | `card:1225:trainer_effect:0` | `SEARCH_HAND`(criteria: 1 Evolution Pokémon + 1 Energy card) |
| Xerosic's Machinations | `card:1197:trainer_effect:0` | `DISCARD_OPP`(down to hand size 3 — magnitude is a target size, not a count) |
| Lillie's Determination | `card:1227:trainer_effect:0` | `HAND_RESET`(self), `DRAW`(6, conditional-alternate 8), `CONDITIONAL` (gated on: exactly 6 Prize cards remaining) |
| Boss's Orders | `card:1182:trainer_effect:0` | `SWITCH_FORCE`(opponent's Bench → Active, user chooses) |
| Dawn | `card:1231:trainer_effect:0` | `SEARCH_HAND`(criteria: 1 Basic + 1 Stage 1 + 1 Stage 2 Pokémon) |
| Lana's Aid | `card:1184:trainer_effect:0` | `DISCARD_RETRIEVE`(up to 3, combination of non-Rule-Box Pokémon + Basic Energy) |
| Team Rocket's Petrel | `card:1219:trainer_effect:0` | `SEARCH_HAND`(criteria: a Trainer card) |
| Wally's Compassion | `card:1229:trainer_effect:0` | `HEAL`(all, target: 1 own Mega Evolution Pokémon `ex`), `ENERGY_RETURN_TO_HAND`(target: same Pokémon), `CONDITIONAL`(qualifier: **near_always_true** — fails only if no damage was present to heal) |
| Crispin | `card:1198:trainer_effect:0` | `SEARCH_HAND`(1 of 2 searched Basic Energy, different types), `SEARCH_ATTACH`(the other of the 2, → 1 own Pokémon) |
| Team Rocket's Ariana | `card:1216:trainer_effect:0` | `DRAW`(to hand size 5, conditional-alternate to 8), `CONDITIONAL` (gated on: all own in-play Pokémon are Team Rocket's) |
| Team Rocket's Proton | `card:1220:trainer_effect:0` | `SEARCH_HAND`(up to 3, Basic Team Rocket's Pokémon) — usage clause ("if you go first") dropped per working decision #1 |
| Judge | `card:1213:trainer_effect:0` | `HAND_RESET`(both players), `DRAW`(4, both players) |
| Team Rocket's Giovanni | `card:1218:trainer_effect:0` | `SELF_SWITCH`(restricted to Team Rocket's-named Pokémon), `SWITCH_FORCE`(conditional on the first switch happening), `CONDITIONAL`(qualifier: **voluntary_cost**) |
| Brock's Scouting | `card:1210:trainer_effect:0` | `SEARCH_HAND`(up to 2 Basic Pokémon OR 1 Evolution Pokémon) |
| Carmine | `card:1192:trainer_effect:0` | `DISCARD_SELF`(all, hand), `DRAW`(5) — usage clause ("if you go first") dropped |
| Urbain | `card:1236:trainer_effect:0` | `DRAW`(3) |
| Cheren | `card:1224:trainer_effect:0` | `DRAW`(3) |
| Team Rocket's Archer | `card:1217:trainer_effect:0` | `HAND_RESET`(both players), `DRAW`(5, self / 3, opponent — asymmetric) — usage clause (own Team Rocket's Pokémon KO'd last opponent turn) dropped |
| Explorer's Guidance | `card:1185:trainer_effect:0` | `REVEAL_DIG`(top 6, keep 2 to hand; qualifier: remainder **discarded**, not returned to deck — a disposal variant not seen in 11a's Pokémon instances) |
| Eri | `card:1186:trainer_effect:0` | `DISCARD_OPP`(up to 2, Item cards specifically, qualifier: after opponent reveals hand) |
| Salvatore | `card:1189:trainer_effect:0` | `EVOLVE_SEARCH`(criteria: no-Ability evolution card) — usage/timing clause dropped |
| Colress's Tenacity | `card:1194:trainer_effect:0` | `SEARCH_HAND`(criteria: 1 Stadium + 1 Energy card) |
| Lisia's Appeal | `card:1204:trainer_effect:0` | `SWITCH_FORCE`(opponent's Bench, restricted to Basic Pokémon, → Active), `CONDITION`(Confused, conditional), `CONDITIONAL` |
| Surfer | `card:1203:trainer_effect:0` | `SELF_SWITCH`(qualifier: player-directed own-side Active swap — Trainer context, no "itself" to reference), `DRAW`(to hand size 5, conditional), `CONDITIONAL` |
| Drayton | `card:1202:trainer_effect:0` | `REVEAL_DIG`(top 7, criteria: find 1 Pokémon + 1 Trainer card) |
| Kieran | `card:1191:trainer_effect:0` | `SELF_SWITCH`(option), `STAT_BUFF`(option: +30 dmg vs opponent's `ex`/`V` Active, pre-W/R, this turn only), `MULTI_CHOICE` |
| Acerola's Mischief | `card:1228:trainer_effect:0` | `DAMAGE_IMMUNE_FROM`(scope: chosen own Pokémon; qualifier: only vs `{ex}` attackers; duration: opponent's next turn), `EFFECT_IMMUNE`(same scope/qualifiers/duration) — usage clause (opponent Prize count) dropped |
| Iris's Fighting Spirit | `card:1208:trainer_effect:0` | `DISCARD_SELF`(1, hand — cost to play), `DRAW`(to hand size 6) |
| Black Belt's Training | `card:1211:trainer_effect:0` | `STAT_BUFF`(scope: own team; +40 dmg vs opponent's `ex` Active, pre-W/R; qualifier: this-turn-only duration) |
| Cook | `card:1212:trainer_effect:0` | `HEAL`(70, target: own Active) |
| Morty's Conviction | `card:1187:trainer_effect:0` | `DISCARD_SELF`(1, hand — cost to play), `DRAW`(× opponent's Benched Pokémon count — dynamic) |
| Harlequin | `card:1223:trainer_effect:0` | `HAND_RESET`(both players), `DRAW`(5 self / 3 opp if heads, else 3 self / 5 opp — coin-flip-determined asymmetric outcome) |
| Rosa's Encouragement | `card:1240:trainer_effect:0` | `ENERGY_ACCEL`(up to 2, Basic Energy, own discard → 1 own Stage 2 Pokémon) — usage clause (Prize count) dropped |
| Cyrano | `card:1205:trainer_effect:0` | `SEARCH_HAND`(up to 3, Pokémon `ex`) |
| Tarragon | `card:1238:trainer_effect:0` | `DISCARD_RETRIEVE`(up to 4, combination of `{F}` Pokémon + Basic `{F}` Energy) |
| Larry's Skill | `card:1206:trainer_effect:0` | `DISCARD_SELF`(all, hand), `SEARCH_HAND`(criteria: 1 Pokémon + 1 Supporter + 1 Basic Energy) |
| Ciphermaniac's Codebreaking | `card:1188:trainer_effect:0` | `SEARCH_DECK_TOP`(2, chosen order) |
| Janine's Secret Art | `card:1195:trainer_effect:0` | `SEARCH_ATTACH`(up to 2 targets, Basic `{D}` Energy, 1 per chosen `{D}` Pokémon, `distribution`=**shared_cap_any_split**), `CONDITION`(Poisoned, conditional on own Active being among the chosen), `CONDITIONAL` |
| Waitress | `card:1235:trainer_effect:0` | `REVEAL_DIG`(top 6; qualifier: found Energy card destination is **direct attach**, not hand — a destination variant), `SEARCH_ATTACH`(1, Basic Energy found among revealed, → 1 own Pokémon) |

**Item batch (32 rows, frequency order).** Two new tags (`DISCARD_OPP_BOARD`, `ENERGY_MOVE`)
had their draft regex validated immediately against source text before being committed —
caught a real bug in both (a markdown-table alternation escape, `\|`, copy-pasted literally
into the Python test instead of unescaped to `|`) at the single-instance stage rather than
after it could propagate, unlike the equivalent apostrophe bug in 11a that reached 29
instances before being caught in a deferred batch validation.

| Card | Effect ID | Tags assigned |
|---|---|---|
| Buddy-Buddy Poffin | `card:1086:trainer_effect:0` | `SEARCH_BENCH`(up to 2, Basic Pokémon ≤70 HP) |
| Poké Pad | `card:1152:trainer_effect:0` | `SEARCH_HAND`(criteria: a non-Rule-Box Pokémon) |
| Rare Candy | `card:1079:trainer_effect:0` | `EVOLVE_FROM_HAND`(qualifier: skips Stage 1, Basic → Stage 2), `CONDITIONAL` (gated on: holding the right Stage 2 card) — usage/timing clause dropped |
| Enhanced Hammer | `card:1081:trainer_effect:0` | `DISCARD_OPP_BOARD`(1, Special Energy, from 1 opponent Pokémon) |
| Pokégear 3.0 | `card:1122:trainer_effect:0` | `REVEAL_DIG`(top 7, criteria: find 1 Supporter card) |
| Jumbo Ice Cream | `card:1147:trainer_effect:0` | `HEAL`(80, target: own Active; qualifier: target must have ≥3 Energy attached — a targeting restriction, not a program conditional) |
| Night Stretcher | `card:1097:trainer_effect:0` | `DISCARD_RETRIEVE`(1, a Pokémon OR Basic Energy card) |
| Switch | `card:1123:trainer_effect:0` | `SELF_SWITCH`(Trainer-context qualifier) |
| Sacred Ash | `card:1129:trainer_effect:0` | `DISCARD_TO_DECK`(up to 5, Pokémon) |
| Ultra Ball | `card:1121:trainer_effect:0` | `DISCARD_SELF`(2, hand — cost to play), `SEARCH_HAND`(criteria: a Pokémon) |
| Hand Trimmer | `card:1087:trainer_effect:0` | `DISCARD_OPP`(down to hand size 5), `DISCARD_SELF`(down to hand size 5) |
| Crushing Hammer | `card:1120:trainer_effect:0` | `DISCARD_OPP_BOARD`(1, any Energy, coin-flip heads-gated) |
| Bug Catching Set | `card:1094:trainer_effect:0` | `REVEAL_DIG`(top 7, criteria: up to 2 in combination of `{G}` Pokémon + Basic `{G}` Energy) |
| Team Rocket's Transceiver | `card:1134:trainer_effect:0` | `SEARCH_HAND`(criteria: a Team-Rocket-named Supporter card) |
| Unfair Stamp | `card:1080:trainer_effect:0` | `HAND_RESET`(both players), `DRAW`(5 self / 2 opp, asymmetric) — usage clause dropped |
| Fighting Gong | `card:1142:trainer_effect:0` | `SEARCH_HAND`(criteria: a Basic `{F}` Energy card OR a Basic `{F}` Pokémon) |
| Mega Signal | `card:1145:trainer_effect:0` | `SEARCH_HAND`(criteria: a Mega Evolution Pokémon `ex`) |
| Tool Scrapper | `card:1137:trainer_effect:0` | `DISCARD_OPP_BOARD`(up to 2, Pokémon Tools; qualifier: target either side's attached Tools, player's choice — broader than the opponent-only default) |
| Premium Power Pro | `card:1141:trainer_effect:0` | `STAT_BUFF`(scope: own `{F}`-type Pokémon; +30 dmg to opponent's Active, pre-W/R; this-turn-only) |
| Dusk Ball | `card:1102:trainer_effect:0` | `REVEAL_DIG`(**bottom** 7 — qualifier: examined zone is bottom, not top; criteria: find 1 Pokémon) |
| Wondrous Patch | `card:1146:trainer_effect:0` | `ENERGY_ACCEL`(1, Basic `{P}`, own discard → 1 own Benched `{P}` Pokémon) |
| Energy Recycler | `card:1139:trainer_effect:0` | `DISCARD_TO_DECK`(up to 5, Basic Energy) |
| Energy Search | `card:1119:trainer_effect:0` | `SEARCH_HAND`(criteria: a Basic Energy card) |
| Secret Box | `card:1092:trainer_effect:0` | `DISCARD_SELF`(3, hand — cost to play), `SEARCH_HAND`(criteria: 1 Item + 1 Tool + 1 Supporter + 1 Stadium) |
| Dangerous Laser | `card:1095:trainer_effect:0` | `CONDITION`(Burned + Confused, simultaneous) |
| Roto-Stick | `card:1077:trainer_effect:0` | `REVEAL_DIG`(top 4, criteria: any number of Supporter cards found — uncapped) |
| N's PP Up | `card:1113:trainer_effect:0` | `ENERGY_ACCEL`(1, Basic Energy, own discard → 1 own Benched N's-named Pokémon) |
| Energy Switch | `card:1116:trainer_effect:0` | `ENERGY_MOVE`(1, Basic Energy, own Pokémon → own Pokémon) |
| Glass Trumpet | `card:1098:trainer_effect:0` | `ENERGY_ACCEL`(up to 2 targets, Basic Energy, own discard → own Benched `{C}` Pokémon, 1 per chosen target — qualifier: target-count-capped-1-each, a third distribution shape distinct from `shared_cap_any_split`, see Phase 4 note) — usage clause dropped |
| Energy Retrieval | `card:1118:trainer_effect:0` | `DISCARD_RETRIEVE`(up to 2, Basic Energy) |
| Miracle Headset | `card:1109:trainer_effect:0` | `DISCARD_RETRIEVE`(up to 2, Supporter cards) |
| Prime Catcher | `card:1088:trainer_effect:0` | `SWITCH_FORCE`(opponent's Bench → Active), `SELF_SWITCH`(conditional on the first switch happening), `CONDITIONAL`(qualifier: voluntary_cost) |

**Pokémon Tool batch (11 rows, frequency order).** Per this spec's own scope note (Purpose
section): Tools only need their *triggering/ongoing-rule signature* captured, not a
restatement of how the rule later modifies live state (spec 11/13 own that). In practice
this means reusing 11a's passive-modifier tags (`HP_BUFF`, `RETREAT_COST_MOD`, `STAT_BUFF`)
almost unchanged, scoped to "the Pokémon this card is attached to."

| Card | Effect ID | Tags assigned |
|---|---|---|
| Hero's Cape | `card:1159:trainer_effect:0` | `HP_BUFF`(+100, scope: holder) |
| Handheld Fan | `card:1161:trainer_effect:0` | `ENERGY_MOVE`(1, qualifier: scope=**opponent_internal** — moves the attacker's Energy among the attacker's own Pokémon), `ON_DAMAGED_TRIGGER` |
| Brave Bangle | `card:1175:trainer_effect:0` | `STAT_BUFF`(scope: holder; +30 dmg vs opponent's `ex` Active, pre-W/R; qualifier: gated on holder having no Rule Box) |
| Cynthia's Power Weight | `card:1173:trainer_effect:0` | `HP_BUFF`(+70, scope: holder; qualifier: restricted to Cynthia's-named Pokémon) |
| Air Balloon | `card:1174:trainer_effect:0` | `RETREAT_COST_MOD`(scope: holder; delta: −2) |
| Deluxe Bomb | `card:1167:trainer_effect:0` | `COUNTER_PLACE`(12, target: the attacking Pokémon), `ON_DAMAGED_TRIGGER`, `SELF_CONSUME`, `CONDITIONAL`(qualifier: **near_always_true** — "if you placed any" is an outcome check) |
| Gravity Gemstone | `card:1166:trainer_effect:0` | `RETREAT_COST_MOD`(scope: **both Active Pokémon** — a scope value beyond self/own-team/opponent, see Phase 4 note; delta: +1; duration: while holder is Active) |
| Maximum Belt | `card:1158:trainer_effect:0` | `STAT_BUFF`(scope: holder; +50 dmg vs opponent's `ex` Active, pre-W/R) |
| Punk Helmet | `card:1176:trainer_effect:0` | `COUNTER_PLACE`(4, target: the attacking Pokémon; qualifier: holder restricted to `{D}` type), `ON_DAMAGED_TRIGGER` |
| Lucky Helmet | `card:1156:trainer_effect:0` | `DRAW`(2), `ON_DAMAGED_TRIGGER` |
| Survival Brace | `card:1155:trainer_effect:0` | `SURVIVE_KO`(minimum HP: 10; qualifier: gated on holder having full HP), `SELF_CONSUME`, `CONDITIONAL` |

**Stadium batch (17 rows, frequency order).** A different character from every prior batch:
battlefield-wide, usually symmetric ("both yours and your opponent's"), continuous
rule-modification effects — the Trainer-specific operation kinds with no Pokémon-side
analogue (`suppress_abilities`, `modify_bench_capacity`, `modify_evolution_rule`, etc.,
flagged back in Phase 0) live almost entirely here. 7 new tags, all validated against
source text before being written in.

| Card | Effect ID | Tags assigned |
|---|---|---|
| Nighttime Mine | `card:1266:trainer_effect:0` | `ATTACK_COST_MOD`(scope: all Tera Pokémon, both sides; delta: +`{C}`) |
| Battle Cage | `card:1264:trainer_effect:0` | `EFFECT_IMMUNE`(scope: both sides' Benched Pokémon, symmetric; qualifier: restricted to counter-placement effects specifically — normal attack damage still applies) |
| Spikemuth Gym | `card:1259:trainer_effect:0` | `SEARCH_HAND`(criteria: a Marnie's Pokémon; qualifier: symmetric, either player on their own turn) |
| Team Rocket's Factory | `card:1257:trainer_effect:0` | `DRAW`(2; qualifier: symmetric, either player) — usage clause (played a Team-Rocket Supporter this turn) dropped |
| Jamming Tower | `card:1246:trainer_effect:0` | `SUPPRESS_TOOLS`(scope: both sides) |
| Surfing Beach | `card:1262:trainer_effect:0` | `SELF_SWITCH`(qualifier: symmetric both players; restricted to `{W}`-type Pokémon) |
| Neutralization Zone | `card:1247:trainer_effect:0` | `DAMAGE_IMMUNE_FROM`(scope: both sides' non-Rule-Box Pokémon; qualifier: only vs `{ex}`/`{V}` attackers, symmetric; also — this specific card cannot be retrieved from the discard pile, a rare card-level meta-property noted here rather than as a new tag) |
| Festival Grounds | `card:1245:trainer_effect:0` | `CONDITION_IMMUNITY`(scope: both sides' Pokémon with any Energy attached; effect: cure + immune to all Special Conditions) |
| Forest of Vitality | `card:1261:trainer_effect:0` | `EVOLUTION_RULE_MOD`(scope: both players' `{G}`-type Pokémon; effect: same-turn evolution allowed) |
| Risky Ruins | `card:1260:trainer_effect:0` | `COUNTER_PLACE`(2, target: any newly-Benched Basic non-`{D}` Pokémon, either side; qualifier: triggered on Bench entry — a one-off trigger shape, not formalized as a companion flag the way `ON_DAMAGED_TRIGGER` was, since only this one card uses it so far) |
| Full Metal Lab | `card:1244:trainer_effect:0` | `DAMAGE_REDUCTION`(scope: both sides' `{M}`-type Pokémon; −30 dmg, post-W/R) |
| Team Rocket's Watchtower | `card:1256:trainer_effect:0` | `SUPPRESS_ABILITIES`(scope: both sides' `{C}`-type Pokémon) |
| Community Center | `card:1242:trainer_effect:0` | `HEAL`(10, scope: **each** of that player's own Pokémon — team-wide, not single-target; qualifier: symmetric both players) — usage clause dropped |
| Grand Tree | `card:1249:trainer_effect:0` | `EVOLVE_SEARCH`(criteria: Stage 1 evolving from a Basic; qualifier: symmetric), `EVOLVE_SEARCH`(criteria: Stage 2 evolving from the newly-evolved Stage 1, conditional on the first evolve happening), `CONDITIONAL` |
| Area Zero Underdepths | `card:1250:trainer_effect:0` | `BENCH_CAPACITY_MOD`(scope: both players; new cap: 8; qualifier: gated on having a Tera Pokémon in play; reversion: discard down to 5 Bench slots if the condition lapses or the card leaves play) |
| Gravity Mountain | `card:1252:trainer_effect:0` | `HP_BUFF`(**−30**, scope: both sides' Stage 2 Pokémon — negative magnitude represents a debuff; no separate `HP_DEBUFF` tag minted for one instance) |
| N's Castle | `card:1253:trainer_effect:0` | `RETREAT_COST_MOD`(scope: both sides' N's-named Pokémon; new cost: 0) |

**Special Energy batch (10 rows, frequency order) — final Phase 1 batch. All 109 Trainer +
Energy rows now tagged.** Ordinary single-type Energy provision (the common "provides
`{X}` Energy" clause on every card here) is treated as a static printed field handled
elsewhere, not tagged in this block — mirrors `DAMAGE` being the untagged default case for
plain attacks in spec 11a. Only non-ordinary provision (`FLEXIBLE_ENERGY_PROVISION`) and
each card's *additional* effect get tags.

| Card | Effect ID | Tags assigned |
|---|---|---|
| Telepath Psychic Energy | `card:19:energy_effect:0` | `SEARCH_BENCH`(up to 2, Basic `{P}` Pokémon), `ON_ATTACH_TRIGGER` |
| Grow Grass Energy | `card:18:energy_effect:0` | `HP_BUFF`(+20, scope: holder; restricted to `{G}`-type) |
| Mist Energy | `card:11:energy_effect:0` | `EFFECT_IMMUNE`(scope: holder) |
| Spiky Energy | `card:14:energy_effect:0` | `COUNTER_PLACE`(2, target: the attacking Pokémon), `ON_DAMAGED_TRIGGER` |
| Enriching Energy | `card:13:energy_effect:0` | `DRAW`(4), `ON_ATTACH_TRIGGER` |
| Team Rocket's Energy | `card:15:energy_effect:0` | `FLEXIBLE_ENERGY_PROVISION`(2 units, any combination of `{P}`/`{D}`), `SELF_CONSUME`(qualifier: only if attached to a non-Team-Rocket's Pokémon — violation-triggered, not unconditional) |
| Rock Fighting Energy | `card:20:energy_effect:0` | `EFFECT_IMMUNE`(scope: holder; restricted to `{F}`-type) |
| Ignition Energy | `card:17:energy_effect:0` | `SELF_CONSUME`(qualifier: automatic, end of the turn attached — a distinct timing from the outcome-gated Tool instances), `FLEXIBLE_ENERGY_PROVISION`(qualifier: base 1 unit, scales to 3 if holder is an Evolution Pokémon), `CONDITIONAL` |
| Prism Energy | `card:16:energy_effect:0` | `FLEXIBLE_ENERGY_PROVISION`(qualifier: base `{C}` fixed-type, upgrades to any-type/1-unit if holder is a Basic Pokémon), `CONDITIONAL` |
| Legacy Energy | `card:12:energy_effect:0` | `FLEXIBLE_ENERGY_PROVISION`(any type, 1 unit, unconditional), `PRIZE_DENIAL`(−1, qualifier: once per game, triggered on holder being KO'd by attack damage) |

## Phase 2 — coverage and detection-rule validation (2026-07-16)

**Coverage.** Reconstructed a structured (effect_id → tags) table from the Phase 1 batches
and cross-checked it against every `effect_id` in the registry's `trainer`/`energy` rows:
109/109 accounted for, zero missing, zero phantom rows, **zero all-zero rows** — better than
11a's bar (which had exactly one deliberate all-zero row for a pure attack-legality gate).
Trainer cards don't produce that shape: a usage-restriction clause here only ever gates part
of a card's text (Working decision #1), never the entire row, since a legally-played Trainer
card always resolves some effect.

**Detection-rule validation.** All 144 tag-assignment pairs (across every row, 21 new
11b-specific tags plus 24 reused/extended from 11a) tested for recall against their own
source text, immediately at draft time during Phase 1 rather than deferred — first full
systematic pass still found 10 failures, all on tags *reused* from 11a against Trainer-only
phrasing that had never actually been spot-checked (as opposed to trusted by analogy). That
count is a real improvement over 11a's initial 43 on a similarly sized batch, and the
causal story is direct: every failure here traces to a place the "validate immediately"
discipline was skipped (reusing an 11a pattern on faith) rather than a place it was
followed. Fixed all 10 — mostly small phrasing generalizations (a `heal all` magnitude form,
a "put 1 of them into your hand" split-outcome phrasing, "the attacks *it* uses" for
Tool/Energy self-reference, an "each player discards until N" symmetric form) plus one real
regex bug independent of any card text: `\{C\}+` only repeats the closing brace, not the
whole `{C}` token — corrected to `(?:\{C\})+`. All 8 propagated to their canonical home in
spec 11a's catalog (`HEAL`, `SEARCH_HAND`, `SEARCH_ATTACH`, `DISCARD_OPP`, `DISCARD_SELF`,
`STAT_BUFF`, `RETREAT_COST_MOD`, `EFFECT_IMMUNE`) rather than left as a locally-diverging
copy, since those tags' definitions are owned there.

Then ran the reverse (false-positive) check — every rule against all 109 rows, not just its
assigned ones — and caught two real bugs introduced while fixing the recall failures above:
a `SEARCH_ATTACH` alternative drafted too loosely (matched bare `ENERGY_ACCEL` text with no
search context at all) and a `DISCARD_SELF` alternative that didn't anchor on "each player,"
so it fired on a `DISCARD_OPP`-only row. Both fixed and re-verified; a follow-up recall
check then caught a third gap the `SEARCH_ATTACH` rewrite had accidentally dropped (the
"look at the top N cards ... and attach" phrasing). Final state: **0 recall failures, 0
false positives** across all 109 rows and every tag.

## Phase 3 — non-meta sanity spot-check (2026-07-16)

Source: `Decks/Deck-Builder/EN_Card_Data.csv`, filtered to Item/Supporter/Pokémon
Tool/Stadium/Special Energy rows outside the 117-card vocabulary: 100 non-meta rows with
non-trivial effect text. Sampled 12 cards (14 rows, counting two cards with both an ability
and an item-level effect) across all 5 subtypes.

| Card | Result |
|---|---|
| Energy Coin, Dragon Elixir, Energy Search Pro, Rescue Board, Team Rocket's Venture Bomb, N's Plan, Lumiose Galette, Counter Gain | All 8 fired the correct tag (`SEARCH_ATTACH`, `HEAL`, `SEARCH_HAND`, `RETREAT_COST_MOD`, `COUNTER_PLACE`, `ENERGY_MOVE`, `HEAL`, `ATTACK_COST_MOD` respectively) with no changes needed — notably `ENERGY_MOVE` and `ATTACK_COST_MOD`, two of the newest 11b-specific tags, generalizing cleanly to cards never seen while drafting them. |
| Antique Cover Fossil, Antique Plume Fossil | Both fired correctly (`EFFECT_IMMUNE`/`DAMAGE_IMMUNE_FROM` on their ability text). Interesting edge case surfaced in passing: these are "Fossil" Items played *as if they were a Basic Pokémon* — a card-class-blending mechanic with no equivalent anywhere in the audited 117. Their "you may discard this card from play" clause fired `DISCARD_SELF` (via its intentionally loose `may discard` catch-all) — `SELF_CONSUME` would also fire on the same text in the real system (its pattern independently matches "discard this card" as a substring), so both tags co-occur. Not wrong — a self-discarding card is defensibly both — just a minor, harmless redundancy in the same spirit as `IGNORES_ACTIVE_EFFECTS` subsuming the narrower Weakness/Resistance tags in spec 11a. Not fixed; noted for Phase 4. |
| Team Rocket's Bother-Bot | Fired nothing. Genuine gap, logged: turning a face-down Prize card face up and revealing/swapping a card from the opponent's hand — Prize-card manipulation has no existing tag anywhere in this vocabulary. |
| Meddling Memo | Fired nothing. Genuine gap, logged: shuffles the *opponent's* hand specifically to the *bottom* of their deck (not a random shuffle-in), then they redraw the same count. Close in spirit to `HAND_RESET` but for the opponent, not the acting player, and position-specific (bottom, not shuffled) — a candidate for generalizing `HAND_RESET` with a `whose`/`position` qualifier rather than a wholly new tag, but not decided here. |

**Outcome:** 12 of 14 rows correct with zero changes, 2 genuine out-of-sample gaps logged
(neither reachable from the 109-row audited set, so Phase 1/2's coverage bar is
unaffected), 1 harmless tag-overlap noted. Consistent with 11a's Phase 3 experience — the
vocabulary generalizes well to unseen cards within the mechanics it already covers, and
genuinely new mechanics surface cleanly as explicit gaps rather than silent all-zero rows
or wrong tags.

## Code-review audit and fix pass (2026-07-16)

A `/code-review` pass re-extracted every regex and assignment directly from both this file
and spec 11a's, independently of session memory, and re-ran coverage/recall/precision
against all 310 rows across both specs. Found and fixed 5 regexes here (`DISCARD_RETRIEVE`,
`DISCARD_OPP_BOARD`, `ENERGY_MOVE`, `SELF_CONSUME`, `FLEXIBLE_ENERGY_PROVISION`) that had
been validated in scratch scripts during Phase 1/2 but never actually written into this
catalog, plus 12 more in spec 11a's shared catalog (`COPY_ATTACK` was missing entirely).
Full writeup and final clean re-verification (0 recall failures, 0 unintended false
positives, 310/310 coverage) is in spec 11a's own "Code-review audit and fix pass" section,
since the audit tooling covered both files together.

## Phase 4 — locked field list, widths, and normalization (2026-07-16)

Per spec 11b's own Interfaces note, a Trainer/Energy card has no board-slot/live-state
split — this tag block *is* the card's whole zone-word content, a separate vector from
spec 11a's Pokémon attribute block (different card-word type in the observation), not a
literal concatenation onto it, even though many tag *names* and qualifier conventions are
shared.

**Content tags: 38, corrected to 39 during code transcription (2026-07-21)** — 19 reused
unchanged from spec 11a (`DAMAGE_IMMUNE_FROM`, `EFFECT_IMMUNE`, `DRAW`, `SELF_SWITCH`,
`COUNTER_PLACE`, `CONDITION`, `EVOLVE_SEARCH`, `SEARCH_ATTACH`, `HEAL`, `ENERGY_ACCEL`,
`SEARCH_HAND`, `REVEAL_DIG`, `STAT_BUFF`, `DISCARD_SELF`, `DISCARD_OPP`, `SWITCH_FORCE`,
`HP_BUFF`, `RETREAT_COST_MOD`, `SEARCH_BENCH`) + 19 new to 11b (`HAND_RESET`,
`DISCARD_RETRIEVE`, `ENERGY_RETURN_TO_HAND`, `SEARCH_DECK_TOP`, `EVOLVE_FROM_HAND`,
`DISCARD_OPP_BOARD`, `DISCARD_TO_DECK`, `ENERGY_MOVE`, `SELF_CONSUME`, `SURVIVE_KO`,
`ATTACK_COST_MOD`, `SUPPRESS_TOOLS`, `CONDITION_IMMUNITY`, `EVOLUTION_RULE_MOD`,
`DAMAGE_REDUCTION`, `SUPPRESS_ABILITIES`, `BENCH_CAPACITY_MOD`,
`FLEXIBLE_ENERGY_PROVISION`, `PRIZE_DENIAL`) **+ `STAT_DEBUFF` (a 20th reused tag, added
post-transcription)** — this list originally omitted `STAT_DEBUFF` even though spec 11a
already has it for exactly the "reduce opponent's outgoing attack damage" shape (distinct
from `DAMAGE_REDUCTION`'s defender-intake framing); a real non-meta Trainer Tool (Antique
Jaw Fossil, "attacks used by your opponent's Active Pokemon do 30 less damage") needs it,
found during the code transcription's own non-meta spot-check. `STAT_DEBUFF`'s shared
regex (`pokemon_tag_catalog.py`) was widened to accept this Trainer-context phrasing
alongside the original Pokemon-side "the Defending Pokemon" wording. Same fixed-width pair
convention as 11a: 1 presence bit + 1 magnitude scalar per tag (`0.0` when absent or purely
boolean), normalized by the same magnitude families (damage, count, HP, multiplier) —
extended with a **cost family** for `ATTACK_COST_MOD` (divide by a cap of 3, the widest
Energy-cost delta seen) and reusing the count-cap (6) for Bench-size deltas.

**Amendment, found during code transcription (2026-07-21):** the presence bit collapses
losslessly into the magnitude scalar here too, exactly the fix already applied to spec
11a's Pokemon tag block (108/117 → 61/70) — across all 109 real assigned rows, no
magnitude-bearing tag is ever assigned exactly `0` while present. One row (N's Castle,
`card:1253`, "have no Retreat Cost") is a genuine absolute-zero effect that would collide
with this collapse if encoded as literal `0` — represented as boolean presence instead,
not a numeric zero. Corrected total width below.

**Companion flags: `CONDITIONAL` (shared with 11a, 3 bits: presence + `voluntary_cost` +
`near_always_true`) + 3 new to 11b** — `MULTI_CHOICE` (1 bit: this row is a "choose 1 of
N" menu, all listed content tags are options not simultaneous effects), `ON_DAMAGED_TRIGGER`
(1 bit: fires when the holder is damaged while Active), `ON_ATTACH_TRIGGER` (1 bit: fires
at the moment this card is attached from hand). 6 bits total.

**Shared cross-tag qualifiers, extended from spec 11a's set:**

- `distribution` (1 bit, same as 11a) — applies here to `SEARCH_ATTACH`, `ENERGY_ACCEL`,
  `COUNTER_PLACE`, `ENERGY_MOVE`.
- `conserved` (1 bit, same as 11a) — kept in the shared schema for `COUNTER_MOVE`/
  `ENERGY_MOVE` even though no currently-tagged 11b row exercises it, so the two
  vocabularies' shared tags stay bit-compatible.
- `self_referential` (1 bit, same as 11a) — `SELF_SWITCH` in Trainer context is always the
  "no itself to reference" case (a Supporter/Item causes the swap, it isn't the swapped
  Pokémon), so this bit is always `0`/false for every 11b row that uses the tag — kept for
  schema consistency, not because 11b needs the distinction itself.
- `scope` — **widened from 11a's 5-value enum to 6**, adding `both_sides` (symmetric
  Stadium effects: "both yours and your opponent's Pokémon"), a category that didn't exist
  anywhere in the 115-card Pokémon sample but is common here (11 of 17 Stadiums use it).
  Applies to `DAMAGE_IMMUNE_FROM`, `EFFECT_IMMUNE`, `COUNTER_PLACE`, `HP_BUFF`, `STAT_BUFF`,
  `RETREAT_COST_MOD`, `ATTACK_COST_MOD`, `SUPPRESS_TOOLS`, `CONDITION_IMMUNITY`,
  `EVOLUTION_RULE_MOD`, `DAMAGE_REDUCTION`, `SUPPRESS_ABILITIES`, `BENCH_CAPACITY_MOD`.
  **This widening is retroactive to spec 11a's own locked field list** — the `scope` field
  is a shared convention, not owned separately by each spec, so 11a's Phase 4 section
  should be read as using the 6-value enum too, even though no Pokémon row happens to need
  the 6th value.

**Total width: 38×2 + 6 + 1 + 1 + 1 + 6 = 91 dimensions — corrected to 38 + 6 + 1 + 1 + 1 +
6 = 53** after the presence-bit collapse above, **then to 39 + 6 + 1 + 1 + 1 + 6 = 54**
after `STAT_DEBUFF` was added as a 20th reused content tag.

**Known residual approximations, not silently accepted:**

- Glass Trumpet's `ENERGY_ACCEL` (Item batch) needs a *third* distribution shape beyond
  `single`/`shared_cap_any_split`: "up to 2 targets, each gets exactly 1 unit" (a
  target-count cap, not a units-pool cap). Currently only noted in that row's prose
  qualifier, not a locked enum value — one instance isn't enough to justify widening the
  `distribution` field to 3 states yet; revisit if it recurs.
- `EFFECT_IMMUNE` on Battle Cage is restricted to one specific effect category
  (counter-placement) rather than all non-damage effects — captured in prose, not a
  separate locked qualifier, the same treatment 11a gave Crustle's `{ex}`-only restriction
  on `DAMAGE_IMMUNE_FROM`.

## Known gaps — final sign-off list

1. Prize-card manipulation (non-meta, Team Rocket's Bother-Bot) — turning a face-down Prize
   card face up and revealing/swapping a card from the opponent's hand. No existing tag
   covers Prize-card-zone manipulation at all. Not reachable from the 109-row audited set;
   not retrofitted.
2. Opponent-hand-to-bottom-of-deck (non-meta, Meddling Memo) — close to `HAND_RESET` but
   targets the opponent specifically and to a specific deck position (bottom, not shuffled
   in). A candidate for a `whose`/`position` qualifier on `HAND_RESET` if it recurs; not
   decided here.
3. `DISCARD_SELF` / `SELF_CONSUME` co-occurrence on self-discarding "Fossil" Items (non-meta) —
   both tags' patterns independently match "discard this card," so both fire together.
   Accepted as harmless, truthful redundancy, the same treatment 11a gave the
   `IGNORES_ACTIVE_EFFECTS`/`IGNORES_WEAKNESS` overlap.
4. Glass Trumpet's third distribution shape and Battle Cage's narrow `EFFECT_IMMUNE`
   restriction (both above) — captured in row-level prose, not yet formalized as locked
   qualifier values; affects 2 of 109 rows.
5. All 7 items on spec 11a's own known-gaps list, since the two specs share `scope` and
   several other conventions and a few of 11a's gaps (opponent-board discard,
   own-side Energy redistribution) were specifically resolved *for this spec's own audited
   sample* via `DISCARD_OPP_BOARD` and `ENERGY_MOVE` — worth cross-referencing rather than
   treating the two gap lists as independent.

## Data

Input corpus: `Imitation-Learning/meta-card-registry/registry.json`, filtered to
`identity.class in ("trainer", "energy")` (117 cards, 109 effect rows). Same ground-truth
priority as 11a: registry `program`/`damage_profile` fields over English text, over the
old encoder's existing behavior.

## Interfaces / seams

Same two-path runtime split as 11a: the 117 known Trainer/Energy IDs are looked up
directly from the Phase 1/2 manual assignment table; everything else runs through the
Phase 2 detection rules against the card's English text. One tag schema, two ways of
populating it.

This vocabulary has an existing consumer today, not just a future one: the current
model's shared "zone MLP" already encodes individual Trainer/Energy card identity vectors
for the four zone words, for Stage-2 discard/search candidates, and for the
`obs.select.effect` triggering-card conditioning vector. A richer tag vocabulary would
improve that path immediately, even before spec 13's zone-word redesign lands — though
wiring it in is a separate implementation step, out of scope here.

If spec 13 adopts per-card zone words, a Trainer/Energy zone word is simply this card's
identity/tag vector — there's no static/live split to thread through the way there is for
Pokémon (see Purpose above).

## Out of scope

- Pokémon tag vocabulary — spec 11a.
- Where a Tool's or Stadium's *ongoing* effect gets represented once active (spec 11's
  Pokémon live-state fields, spec 13's global word) — this spec only covers the card's
  own effect signature.
- Zone-word and global-state design — spec 13.
- The compositional-AST direction explored earlier and shelved.
- Implementing the parser itself and wiring the lookup table into the codebase. This
  spec's deliverable is the vocabulary, the ready-to-implement detection rules, and the
  manual assignment table — not the code that executes them.

## Open questions

- Given the heavier node-count distribution here (max 6, vs. Pokémon's max 3), Phase 1
  needs to decide a cap-and-overflow policy explicitly for Trainers rather than assuming
  11a's approach transfers unchanged — flag for review during that phase, not decided now.
- Whether Stadium cards need any additional identity signal beyond their effect tags,
  given the current model already has a separate 6-Stadium one-hot in the global word —
  possible duplication to resolve when spec 13 is written.
- How strictly a detection rule must reproduce the manual assignment on known-card text
  (Phase 2) is a judgment call for that phase, not fixed here.
