# 11a — Pokémon Attribute/Effect Tag Vocabulary

Part of [`11-pokemon-word-observation-encoding.md`](11-pokemon-word-observation-encoding.md).

Status: **Complete and independently re-verified (2026-07-16), amended same day to add
`energy_cost`, then amended again during transcription (see below) to collapse the
presence+magnitude pair and fix a stale tag count.** All phases (0-4) done: census
corrected, all 115 Pokémon / 201 rows tagged across 6 batches, 49 content tags +
`CONDITIONAL`, full program-node-kind audit, coverage/recall/precision validated, 12-card
non-meta spot-check (expanded to 50 during transcription, see "Transcription amendment"),
7-item known-gaps sign-off. A subsequent `/code-review` audit pass (see "Code-review audit
and fix pass" below) re-extracted every regex and assignment fresh from the file text — not
session memory — and found that several in-session "0 failures" claims described
scratch-script regexes that were never actually written into this catalog. Fixed 12 regexes
here (plus 5 in spec 11b) and added 1 missing catalog entry (`COPY_ATTACK`) — **this raised
the true content-tag count to 49, but Phase 4's own field-list section below was never
updated to match and still said 48 until the transcription pass caught the drift; fixed
now.** Final re-verified state: 310/310 rows covered across both specs, 285/285
tag-assignment pairs pass recall, 0 unintended false positives. **Amendment (2026-07-16,
during spec 11's base-field pass):** added `energy_cost`, a card-data-sourced (not
text-detected) field on attack rows only, widened same day to 9 dims (per-type, not
type-blind) — see "Energy cost" below. **Transcription amendment (2026-07-16, during code
transcription):** collapsed each content tag's presence-bit + magnitude-scalar pair into one
scalar (verified lossless against the actual 201-row table — no magnitude-bearing tag is
ever assigned exactly `0` while present), and corrected the stale 48→49 tag count. Total
per-attack-row width now **70** (ability rows: **61**) — see "Phase 4" below for the
corrected math. Ready to feed spec 11's static template. Next: spec 11b (Trainer/Energy
vocabulary) — already complete as of this same pass.

## Purpose

Design the widened attack/ability tag vocabulary that makes up the effect half of the
Pokémon static template (see spec 11). This replaces the old 16-attack-tag/11-ability-tag
scheme, which left 76 of 201 real audited Pokémon effect rows as an all-zero vector. The
goal is a vocabulary that covers the audited meta *nearly* losslessly — explicit,
reviewed gaps are fine; silent zero-vectors are not — without growing so wide it hurts
training on a model in the 100K–1M parameter range.

**This is a planning deliverable, not a parser.** The concrete output is: (1) a catalog of
tag names and their meanings; (2) for each tag, a detection rule (regex and/or keyword
logic) ready to hand to a future implementation pass, meant to fire on never-before-seen
Pokémon; (3) a complete manual tag assignment for all 201 audited attack/ability/effect
rows, built directly from the registry's exact ground truth rather than by running the
detection rules; and (4) that manual assignment doubling as the production lookup table
for the 115 known meta Pokémon — the detection rules are only ever exercised on Pokémon
outside that vocabulary. No code is written as part of this spec.

## Behavior — the review process

**Phase 0 — Starting vocabulary from the operation-kind census.** The spec-12 registry
already shows the shape of the problem. Across all 115 audited Pokémon (201 attack/
ability rows — `kind in ("attack", "ability")`; a separate 4-row `tera` effect section
exists on 4 Ogerpon-line/Dragapult cards and is out of this 201-row count, see note below),
operation-kind usage is:

| Operation kind | Occurrences |
|---|---:|
| `deal_damage` | 136 |
| `move_cards` | 47 |
| `shuffle_cards` | 19 |
| `modify_action_rule` | 15 |
| `attach_card` | 11 |
| `place_damage_counters` | 10 |
| `modify_damage_rule` | 9 |
| `switch_active` | 6 |
| `apply_special_condition` | 5 |
| `modify_card_rule` | 4 |
| `modify_stat` | 4 |
| `remove_damage_counters` | 2 |
| `reveal_or_inspect` | 2 |
| `knock_out` | 2 |
| `evolve`, `copy_or_use_attack`, `modify_prize_rule`, `copy_and_execute_attack_program`, `heal_damage`, `modify_energy_provision` | 1 each |

Node-count distribution across those 201 rows: 131 rows need 1 operation, 61 need 2, 7 need
3 (Dudunsparce, Drakloak, Cinderace, Chi-Yu, Tatsugiri, N's Darmanitan, Toxtricity), and 1
needs 4 (Wellspring Mask Ogerpon ex, `card:108:attack:1`, a genuine two-`deal_damage`
sequence, not a conditional artifact). 25 of the 201 rows (12%) use a `conditional` branch,
with a maximum nesting depth of 2.

**Correction (found while walking Mega Kangaskhan ex as a worked example, 2026-07-16):** an
earlier draft of this note claimed 1 row (`card:756:attack:0`, "Flip a coin until you get
tails...") parses to 0 operations. That was wrong — an artifact of the census extraction
script only walking `sequence`/`conditional` node kinds, with no case for this row's actual
top-level `repeat` node kind. The registry does not have a gap here; the extraction script
did. See the row's own entry in batch 1 below for what it actually contains (a fully
resolved, human-reviewed dynamic formula, not a parse failure).

**Correction note (2026-07-16):** the numbers above were re-derived directly from
`Imitation-Learning/meta-card-registry/registry.json` and differ from the original
Phase 0 draft (which reported 125/42/17/12/9/9/3/3 and a 201-row, max-3-node census with
only 5 three-node rows). Two methodology issues explain the gap: (1) the original count
implicitly excluded the 4 `tera`-kind rows differently than assumed — confirmed here as
cleanly out-of-scope, restoring the 201-row total; (2) more importantly, the original pass
appears to have summed operations across **both** branches of every `conditional` node,
double-counting rows like Chi-Yu's Ground Melter (120 dmg + discard Stadium **if** a
Stadium is in play, **else** 60 dmg — one logical gated action, counted as two). This
spec's stated Phase 1 conditional policy ("assign the tag(s) for the gated operation as if
it fires... drop the predicate") only ever needs the `then` branch, so the corrected census
above counts `then` only. This also surfaced 3 operation kinds absent from the original
table entirely (`modify_prize_rule`, `heal_damage`, plus the 0-node coin-flip gap) and
raised `deal_damage`, `move_cards`, and `modify_action_rule` further above their original
counts than the double-counting fix alone accounts for — the residual gap is not fully
reconciled and is not worth further forensic effort now, since Phase 1 tags rows directly
from registry ground truth per-row, not from this aggregate table. The table exists to seed
the vocabulary, not to gate correctness.

Draft one candidate named tag family per recurring operation kind as the seed list —
e.g. `SNIPE`, `DRAW`, `DISCARD_SELF`, `DISCARD_OPP`, `MILL`, `SEARCH_ATTACH`,
`ENERGY_ACCEL`, `HEAL`, `COUNTER_PLACE`, `ITEM_LOCK`, `COOLDOWN`, `RETREAT_LOCK`,
`ATTACK_IMMUNITY`, `STAT_BUFF`, `STAT_DEBUFF`, `SWITCH_FORCE`, `SELF_KO`, `REVEAL_DIG`,
`COPY_ATTACK`. This is a starting point, not a commitment — several of these may merge,
split, or get dropped once the batch walkthrough runs.

**Phase 1 — Batched card-by-card walkthrough, producing the manual tag assignment.** Same
batching discipline spec 12 used: frequency-then-ID order, ≤20 cards per batch (roughly 6
batches for 115 cards). Per row: assign the tag(s) that describe it from the current
vocabulary, using the registry's exact `program`/`damage_profile` data as ground truth
(not the card's English text, and not the old encoder's tags); add a new tag or merge two
existing ones when the current vocabulary doesn't fit; and log a deliberate, explicit drop
when a row's nuance genuinely isn't worth a tag. This pass **is** the manual tagging — its
output is the row-by-row assignment table that becomes the production lookup table for
the 115 known Pokémon (see Interfaces). Conditionals get one fixed policy decided once
during this phase (for example: assign the tag(s) for the gated operation as if it fires,
plus a `CONDITIONAL` flag, and drop the predicate itself) rather than bespoke per-card
handling.

**Phase 2 — Coverage pass, then draft detection rules for the fallback path.** First,
re-run the assignment against all 201 rows and confirm the target bar: no all-zero rows.
Anything still meaningfully lossy after the pass gets listed explicitly for sign-off — not
silently accepted. Then, for each locked tag, draft its detection rule (regex and/or
keyword-bag logic, per the schema below) and check it against the *English card text* of
every meta-card row already manually assigned that tag — the manual assignment is the test
set the detection rule has to reproduce a reasonable approximation of, even though
production never routes known cards through it.

**Phase 3 — Non-meta sanity spot-check.** The same parser will run on cards outside the
115-ID vocabulary too (any Pokémon from a deck the audit never saw). Spot-check the
drafted vocabulary against a handful of non-meta Pokémon to confirm it isn't overfit to
exactly this sample. Loss here is explicitly more acceptable than loss on the audited 115
— this phase is a sanity check, not a second exhaustive audit.

**Phase 4 — Lock the field list, widths, and normalization**, plus the explicit "known
gaps" list from Phase 2.

## Deliverable format

Per tag, the spec records:

- **Name** — e.g. `SNIPE`.
- **Meaning** — one line, plain language.
- **Detection rule** — regex and/or keyword-bag logic intended to fire on never-before-seen
  card text. May combine multiple patterns (an ANY-of or ALL-of group), not forced into one
  regex.
- **Magnitude capture** — if the tag carries a parameter (cards drawn, damage amount,
  counters placed), the capture group or extraction logic that pulls it out as part of the
  same rule, not a separate follow-up step.
- **Assigned rows** — every one of the 201 audited attack/ability/effect rows that receives
  this tag, by card ID and effect ID, from the Phase 1 manual assignment.

Example shape:

```text
Tag: SNIPE
Meaning: deals damage to a Benched Pokemon (either side) rather than only the Active.
Detection rule: /(\d+)\s+damage\s+to\s+1\s+of\s+(your|your opponent'?s)\s+Benched/i
Magnitude capture: group 1 = damage amount; group 2 = own-bench vs opponent-bench
Assigned rows: card:258 attack:0 (N's Darmanitan, Flamebody Cannon, 90 to opponent bench);
  card:743 attack:0 (Alakazam, Powerful Hand, hand-scaled counters to opponent active —
  NOT snipe, listed here only to show a near-miss the rule must not match); ...
```

The full 201-row table itself (every row's final tag assignment) lives in this file as the
output of Phase 1/2 — it is both the audit record and the runtime lookup table described
in Interfaces below.

## Working design decisions (established during batch 1)

Two decisions, not explicitly settled before Phase 1 started, that materially shape every
row's tagging and are recorded here so later batches stay consistent:

1. **A base `DAMAGE` tag exists and fires on every row containing at least one `deal_damage`
   operation**, carrying the damage amount as its magnitude. Without it, the large share of
   rows that are "just" a plain attack (e.g. Kadabra's 30-damage Confuse Ray-style attack
   with no other text) would be indistinguishable from a row with no attack at all, which
   directly conflicts with spec 11's "effectively zero all-zero assignments" success
   criterion. `DAMAGE` is the default/plain case; IGNORES_WR, etc. are modifiers that
   co-occur with it when a row's damage isn't vanilla.

   **Amendment (post-transcription correction):** `SNIPE` is the one exception to "co-occurs
   with DAMAGE" — `DAMAGE` and `SNIPE` are independent numbers, never mirrored copies of each
   other. Two shapes: (a) **additive**, a fixed base attack damage plus a *separate* bonus hit
   to a Benched Pokemon ("...also does N damage to 1 of your opponent's Benched Pokemon") —
   both tags fire, each with its own number (N's Darmanitan, `card:258:attack:1`: `DAMAGE=90,
   SNIPE=90`, two Pokemon hit); (b) **sole redirect**, the attack's entire damage is one
   freely-targetable hit with no separate base ("this attack does N damage to 1 of your
   opponent's Pokemon," no "also") — only `SNIPE` fires, `DAMAGE` stays 0 (Fezandipiti ex,
   `card:140:attack:0`, "Cruel Arrow": `SNIPE=100` only, one Pokemon hit). Originally
   transcribed as `DAMAGE=100, SNIPE=100` for Fezandipiti ex on the mistaken assumption that
   any row tagged with both always shares one number — caught because it made a 1-Pokemon-hit
   row indistinguishable from a 2-Pokemon-hit row like Darmanitan's in the tag block.
2. **The tag block encodes effect *content* (what happens when a row resolves), not
   activation *triggers/conditions*** (when/whether a player may resolve it — "once during
   your turn," "if this Pokémon has any {D} Energy attached," "when you play this Pokémon
   from your hand to evolve," "during Pokémon Checkup"). Those conditions gate legality and
   are assumed to already be owned by the live board state / legal-action system elsewhere
   in the architecture (spec 11's live-state fields, action masking), not duplicated here.
   This keeps the vocabulary from exploding into one bespoke trigger-tag per card. The
   existing Phase 1 conditional policy (tag the gated operation as if it fires, plus a
   `CONDITIONAL` flag, drop the predicate) is the one exception: it applies specifically to
   in-program `conditional` branches (a row's *effect* differs by branch, e.g. Chi-Yu's
   120-vs-60 damage), not to activation gating.

## Tag catalog (working — v1, after batch 1 of 6)

Seed-list tags not yet observed (`MILL`, `ITEM_LOCK`, `COOLDOWN`, `RETREAT_LOCK`,
`ATTACK_IMMUNITY`, `STAT_BUFF`, `STAT_DEBUFF`, `SELF_KO`, `REVEAL_DIG`, `COPY_ATTACK`,
`ENERGY_ACCEL`, `DISCARD_OPP`) are carried forward unchanged and are expected to fire in
later batches; they are omitted from the table below until a real row exercises them, to
keep detection-rule drafting grounded in actual card text (Phase 2 policy) rather than
speculative regexes.

*(Historical snapshot as of batch 1 — by the end of Phase 1 every tag in this list except
`ATTACK_IMMUNITY` had a real row and a formal catalog entry. `COPY_ATTACK` was the one
exception that slipped through: it was exercised in batches 2 and 5 but never actually
promoted to the table below until a code-review audit caught the gap — see its entry
above, now fixed.)*

| Tag | Meaning | Detection rule (draft) | Magnitude capture |
|---|---|---|---|
| `DAMAGE` | Row deals damage guaranteed to land on the active target of a normal attack. Default/plain case of any attack — **except** when the entire attack is a `SNIPE`-shaped sole redirect (see below), in which case `DAMAGE` does not fire at all, since there is no guaranteed-active number independent of the redirect. | `/(?:does|deals?)\s+(\d+)\s+damage/i` or a bare printed damage value with no qualifying clause | printed/credible damage amount |
| `SNIPE` | Damage delivered via a bench-eligible redirect/choice mechanism, independent of `DAMAGE`. Two shapes: **additive** — a separate bonus hit to a Benched Pokémon on top of the attack's own base active damage ("...also does N damage to 1 of your opponent's Benched Pokémon"), `DAMAGE` and `SNIPE` both fire with their own distinct numbers; **sole redirect** — the attack's entire damage is one freely-targetable hit, no "also," no separate base ("this attack does N damage to 1 of your opponent's Pokémon"), only `SNIPE` fires. (Amended post-transcription: originally `DAMAGE`/`SNIPE` were assumed to always co-occur and share one number when the table gave only one — wrong, since it made a 1-Pokémon-hit row like Fezandipiti ex's Cruel Arrow indistinguishable from a 2-Pokémon-hit row like Darmanitan's Flamebody Cannon.) | `/(\d+)\s+damage\s+to\s+1\s+of\s+your\s+opponent'?s\s+(?:Benched\s+)?Pok[eé]mon/i` — "Benched" made optional after Phase 2e validation found Fezandipiti ex's variant phrasing ("100 damage to 1 of your opponent's Pokémon," with the Benched qualifier only in a parenthetical) didn't match the stricter original pattern | group 1 = bench/target damage amount |
| `IGNORES_WEAKNESS` | This attack's damage isn't affected by Weakness. Co-occurs with `IGNORES_RESISTANCE` when text says "Weakness **or** Resistance"; some cards (e.g. Cynthia's Gible) name only one. | `/damage isn'?t affected by Weakness/i` | none |
| `IGNORES_RESISTANCE` | This attack's damage isn't affected by Resistance. | `/damage isn'?t affected by (?:Weakness or )?Resistance/i` — broadened after Phase 2e found "Weakness or Resistance" phrasing (Resistance as the second alternative, not immediately after "affected by") failed the original stricter pattern | none |
| `IGNORES_ACTIVE_EFFECTS` | This attack's damage isn't affected by *any effects* on the opponent's Active (strictly broader than `IGNORES_WR`; subsumes it when both phrases could apply). | `/damage isn'?t affected by .*any effects on (?:your opponent'?s\|your) Active Pok[eé]mon/i` — added a wildcard gap after Phase 2e found cards that chain "isn't affected by Weakness or Resistance, **or by** any effects on..." with intervening text | none |
| `DAMAGE_IMMUNE_FROM` | Prevents all damage done *to* this Pokémon (or a named scope: self / non-Rule-Box bench / Basic-line family) by opponent attacks. Also covers the single-instance coin-flip-gated phrasing ("prevent **that** damage," referring back to one just-mentioned hit) as a separate alternative, distinct from the blanket "prevent all damage" form. | `/prevent(?:s)? all damage (?:from (?:and effects of )?attacks.*?)?done to\|prevent that damage/i` — widened twice during Phase 2e: once to allow "damage from attacks done to" word order, again to allow an arbitrary infix clause (e.g. "...attacks from your opponent's Pokémon done to...") | captured group = scope (self / bench-no-rulebox / named family); optional qualifier = attacker restriction (e.g. only vs `{ex}`); qualifier = single-instance vs. blanket |
| `EFFECT_IMMUNE` | Blocks non-damage attack *effects* (status, a specific effect category like counter-placement, etc.) from landing on a named scope; damage itself still applies. | `/prevent(?:s)? all (?:damage from and )?effects of attacks\|prevent all damage counters from being placed .+ by effects of attacks/i` — broadened after Phase 2e found the common combined phrasing "prevent all damage from and effects of attacks..." doesn't lead with "effects" the way the original pattern assumed; spec 11b's validation added the second alternative for a Stadium that blocks one specific effect category (counter-placement) rather than non-damage effects broadly | scope; effect-category restriction if narrower than "all non-damage effects" |
| `RECOIL` | Attack also damages the user's own Pokémon. | `/also does (\d+) damage to itself/i` | group 1 = self-damage amount |
| `DRAW` | Draw N cards (N may be "up to", "until hand size N", or unspecified as in "draw a card"). | `/draw (\d+) cards?\|draws? \d+ cards?\|draw a card\|draw cards until/i` — the original numeric-only pattern missed "draw **a** card" (no digit), "draw cards **until**..." (open-ended to a hand-size target), and "**each player** draws" phrasing; a code-review audit found 9 assigned rows failing the original pattern, including both the Pokémon (Marnie's Impidimp, Cynthia's Garchomp ex, Comfey, Ralts) and Trainer (Team Rocket's Ariana, Judge, Surfer, Iris's Fighting Spirit, Morty's Conviction) sides | group 1 = count |
| `SELF_SWITCH` | Repositions the user's own Active Pokémon, pulling a Benched Pokémon into Active — not a forced opponent switch (`SWITCH_FORCE`). Two shapes, distinguished by a `self_referential` qualifier: `true` (default) = the effect-holder swaps *itself* out for a chosen Benched Pokémon (Abra/Dunsparce/Buneary's "switch this Pokémon with 1 of your Benched Pokémon"); `false` = the effect-holder stays wherever it is and instead lets the player promote *any other* chosen own Pokémon into Active, independent of the holder's own position (Pecharunt ex's ability explicitly excludes itself from the swap — found during a Phase 2 tag-conflation spot-check, since the original definition only actually described the first shape). | `/switch this Pok[eé]mon with 1 of your Benched Pok[eé]mon/i` (self-referential) or `/you may switch 1 of your Benched .+ with your Active Pok[eé]mon\|switch (?:your\|their) Active .*Pok[eé]mon with 1 of (?:your\|their) Benched .*Pok[eé]mon/i` (free-choice) — the free-choice pattern originally only recognized "you may switch 1 of your Benched X with your Active Pokémon"; a code-review audit found most real Trainer instances (including Pecharunt ex, the card the qualifier was designed around) phrase it in the reverse order with no "you may" ("Switch your Active Pokémon with 1 of your Benched Pokémon"), so that shape was added as a second alternative | `self_referential` qualifier |
| `SELF_MILL` | Shuffles this Pokémon (and/or its attachments) back into its owner's own deck, typically as a cost/consequence of an ability. | `/shuffle (?:this Pok[eé]mon\|it) (?:and all attached cards )?into your deck/i` — widened to accept the pronoun "it" after an audit found Abra's own ability text refers back to itself that way rather than repeating "this Pokémon" | none |
| `COUNTER_PLACE` | Places damage counters directly (not via the normal attack-damage formula). | `/place (\d+) damage counters? on\|put (\d+) damage counters? on/i` — the "put" alternative was validated in the session's working scripts but never written into this row until a later audit caught the gap; several assigned cards (including Dragapult ex's Phantom Dive) use "put," not "place" | group 1 = counter count, or scaling-basis text when dynamic; `distribution` qualifier (see below) |
| `COUNTER_MOVE` | Moves existing damage counters from one Pokémon to another. Optional `conserved` qualifier: `false` (default) = a net transfer that changes total board damage (e.g. own → opponent); `true` = a same-side reshuffle that conserves total damage (opponent-internal, zero net change) — see Phase 2a finding on Alakazam's Strange Hacking vs. Munkidori. | `/move (?:up to )?(\d+\|any number of\|all) damage counters? (?:from\|on) .+ to/i` — added "all" as a quantity alternative after Phase 2e found Team Rocket's Wobbuffet's "Move **all** damage counters..." didn't match a numbers-only pattern; a later audit found Alakazam's own Strange Hacking — the card `conserved` was defined around — used "damage counters **on** X to Y" rather than "from," so "on" was added as a second preposition alternative | group 1 = counter count; `conserved` qualifier; `distribution` qualifier (see below) |
| `CONDITION` | Inflicts a special condition (Confused, Asleep, Paralyzed, Poisoned, Burned) on the opponent's Active. | `/(?:is now\|becomes)\s+(Confused\|Asleep\|Paralyzed\|Poisoned\|Burned)\|[Mm]ake (?:your opponent'?s\|your) Active Pok[eé]mon (Confused\|Asleep\|Paralyzed\|Poisoned\|Burned)/i` — added the "Make X Confused" alternative after Phase 2e found Brambleghast's ability uses this third grammatical form, not "is now"/"becomes" | captured condition name |
| `EVOLVE_SEARCH` | Searches the deck for a card that evolves this Pokémon (or, in a scaled variant, each of several named Pokémon) and evolves it directly, mid-effect. | `/search (?:your\|their) deck for .*evolves from (?:this\|that\|1 of (?:your\|their)) .*Pok[eé]mon/i` — widened during Phase 3 to accept "that Pokémon" after the non-meta card Reuniclus's ability used the same mechanism scaled across the whole Bench; widened again during a later audit after Salvatore ("evolves from **1 of your** Pokémon") and Grand Tree (names the specific stage — "a Stage 2 Pokémon that evolves from..." — instead of the generic word "card," and uses "their" for symmetric Stadium usability) both failed the original pattern, which was over-fit to Dwebble's exact original phrasing ("a card that evolves from") | none; scaling basis (e.g. "per own Benched Pokémon") noted separately when present |
| `SEARCH_ATTACH` | Searches the deck for card(s) and attaches them directly (typically Energy) — including the "look at the top N" variant of deck search, not only "search your deck for." Requires a genuine search/dig context, not just a bare "attach X to Y," to avoid colliding with `ENERGY_ACCEL` (attaches from an off-board source, no search). | `/search (?:your\|their) deck for .*attach\|reveal them,? and put 1 of them into (?:your\|their) hand\.\s*Attach the other\|look at the top \d+ cards? of (?:your\|their) deck and attach/i` — the original pattern only recognized "search your deck for ... and attach" phrasing; widened during spec 11b's Trainer-corpus validation to add two more real phrasings of the same mechanism it had never been tested against: a split-outcome search ("...put 1 of them into your hand. Attach the other...") and a "look at the top N and attach" dig variant. (A loose "attach ... to 1 of" alternative appeared transiently in the validation script while drafting this fix and was caught and removed before being adopted — it was never actually written into this catalog, but is worth naming here so a future implementer doesn't reintroduce it: it collided with plain `ENERGY_ACCEL` text that has no search context at all.) | count (if capped); target/type restriction from surrounding text; `distribution` qualifier (see below) |
| `HEAL` | Heals damage from a Pokémon (a fixed amount, or all of it). | `/heal (\d+\|all) damage/i` — widened during spec 11b's cross-vocabulary validation, which found a Trainer card ("Heal all damage from...") the numeric-only pattern couldn't match | group 1 = amount, or "all" |
| `RNG_SCALING_DAMAGE` | Damage scales with an open-ended random (repeat-until) process. Magnitude capture carries the *already-computed, human-approved* summary statistics from the registry's own dynamic-formula resolution, not just the raw per-flip literals — see the worked correction below for why that distinction matters. | `/flip a coin until you get tails.*more damage for each heads/i` (narrow, written for the one known instance; needs generalizing once more RNG-scaling cards are seen) | base damage; per-flip increment; `expected_value`; `credible_max` (the registry's approved practical ceiling); `theoretical_max` flag (unbounded) |
| `CONDITIONAL` | Companion flag: this row's tagged effect only fires under a program-level **board/game-state** condition (the predicate itself is dropped per the fixed Phase 1 policy). Reserved for non-RNG gating (energy attached, Stadium in play, hand size, etc.) — a coin-flip-gated effect gets a dedicated `COIN_FLIP_*`/`RNG_SCALING_DAMAGE` tag instead, since that conveys strictly more information than the generic flag. Optional qualifier `voluntary_cost` marks the rarer case where the gate is the player's own choice to pay a stated cost rather than a hidden/observed board fact (see `card:108:attack:1`, Phase 2a) — the model needs no extra board information to know this bonus is reachable, unlike a true board-state gate. Optional qualifier `near_always_true` marks a gate that only fails in a degenerate edge case (e.g. an empty deck), not a meaningfully variable condition (see `card:66:ability:0`). | n/a — set programmatically from the registry's `conditional` node presence, not derived from text at inference time for known cards; for unseen cards, the detection-rule layer does not attempt to reconstruct this flag from English text (out of scope — see Phase 2) | qualifier: default (board-state) / `voluntary_cost` / `near_always_true` |
| `COIN_FLIP_DAMAGE` | A single coin flip grants a fixed bonus (or sets) damage amount if heads — the common "flip a coin, if heads do N more damage" pattern. Distinct from `RNG_SCALING_DAMAGE`'s open-ended flip-until-tails loop. | `/flip a coin\.?\s*if heads,?\s*this attack does (\d+) more damage/i` | group 1 = bonus amount |
| `ENERGY_ACCEL` | Attaches Energy to a Pokémon outside the normal one-per-turn-from-hand rule — from the discard pile, hand (via an Ability, beyond the standard turn action), deck, or another off-rule source. | `/attach .*Energy card(?:s)? from (?:your\|their) discard pile\|attach a Basic .*Energy card from (?:your\|their) hand/i` — the original pattern required a singular "a/an" article and covered only the discard-pile source; a code-review audit found 6 assigned rows failing it, all either using a plural "up to N ... cards" count (Archaludon ex, Mega Lucario ex) or a hand source (Teal Mask Ogerpon ex, Barbaracle, Hydrapple ex, Rosa's Encouragement) | source zone (discard/deck/other); target (self/any); `distribution` qualifier (see below) |
| `SEARCH_HAND` | Searches the deck for a card matching stated criteria and puts it into hand (not directly attached/played — contrast `SEARCH_ATTACH`, `EVOLVE_SEARCH`). | `/search (?:your\|their) deck for .*put (?:it\|them\|1 of them) into (?:your\|their) hand/i` — the `1 of them` alternative added during spec 11b's validation for split-outcome search cards ("...put 1 of them into your hand. Attach the other...") | captured group = search criteria text; count if capped |
| `REVEAL_DIG` | Looks at the top (or, rarer, bottom) N cards of the deck and selectively keeps/reorders a subset (put some to hand, rest to bottom/back). | `/look at the (?:top\|bottom) (\d+) cards? of (?:your\|their) deck/i` — widened after an audit found Dusk Ball's "Look at the **bottom** 7 cards of your deck..." failed the top-only original pattern | group 1 = cards examined; top/bottom qualifier; destination split from surrounding text |
| `STAT_BUFF` | Passively increases damage output (or another stat) for a named scope of own Pokémon, typically a card-family, a type, or a single holder (Tool/Energy context: "the attacks it uses"). | `/attacks used by .+ do (\d+) more damage\|the attacks it uses do (\d+) more damage/i` — second alternative added during spec 11b's validation for Tool/Energy cards, which refer back to "the Pokémon this card is attached to" as "it" rather than naming a scope directly | scope (family name / type / holder); bonus amount |
| `DISCARD_SELF` | Discards card(s) from the user's own side (hand, or Energy attached to a stated Pokémon) — often paired with `DAMAGE` as a cost/consequence that scales the attack; also covers a symmetric "each player discards down to N" Trainer variant. | `/discard\b(?!\s+the\s+top).{0,40}?(?:Energy\|cards?)\b.{0,20}?\bfrom\b.{0,20}?(?:this Pok[eé]mon\|your (?:Benched )?Pok[eé]mon\|your hand)\|discard (?:a card from\|your hand)\|may discard\|each player discards cards from their hand until they have (\d+) cards/i` — Phase 2e's false-positive pass (running every rule against all 201 rows, not just its own assigned ones) found the original unbounded `.*` wildcard let this rule jump across an entire independent clause and false-fire on Great Tusk's "discard the **top card** of your opponent's deck... Supporter **card from** your hand" (a `MILL` row, not self-discard) by matching a coincidental "card from" later in the sentence. Replaced with bounded lazy quantifiers and an explicit exclusion for "discard the top." Also found (and removed) a stray `shuffle (\d+) Energy` alternative that had been copied in by mistake — that phrasing belongs only to `ENERGY_RETURN_TO_DECK`, which exists specifically to keep "shuffled into deck" distinct from "sent to discard"; leaving it in `DISCARD_SELF` contradicted that tag's own reason for existing and false-fired on Wellspring Mask Ogerpon ex. Spec 11b's validation later added the "each player discards... until they have N cards" alternative, anchored on "each player" specifically (not a bare "discards... until N cards") after an early draft of that addition briefly false-fired on a `DISCARD_OPP`-only row where the opponent alone does the discarding. | group 1 = count if capped, else "all"; or target hand size for the symmetric variant |
| `ITEM_LOCK` | Prevents the opponent from playing Item cards, typically for their next turn. | `/(?:they\|your opponent) can'?t play any Item cards? from (?:their\|your opponent'?s) hand/i` | duration (their next turn / while in play) |
| `SETUP_ALT_PLACEMENT` | This Pokémon may be placed face-down as the starting Active Pokémon during game setup, bypassing normal deployment rules. | `/if this Pok[eé]mon is in your hand when you are setting up to play, you may put it face down in the Active Spot/i` | none |
| `REVIVE_FROM_DISCARD` | Puts copies of this (or a named) Pokémon from the owner's discard pile directly onto the Bench. | `/put up to (\d+) .+ from your discard pile onto your Bench/i` | group 1 = count |
| `SELF_KO` | Using this effect knocks out the user's own Pokémon as a consequence. | `/if you use this Ability,? this Pok[eé]mon is Knocked Out/i` | none |
| `DOUBLE_ATTACK` | May use an attack a second time in the same turn (an extra-attack effect), typically gated by a board condition (`CONDITIONAL`). | `/may use an attack it has twice/i` | none |
| `RETREAT_LOCK` | Prevents a named Pokémon (typically the opponent's Defending/Active) from retreating, typically for their next turn. | `/the Defending Pok[eé]mon can'?t retreat/i` | scope + duration from surrounding text |
| `ATTACK_LOCK` | Prevents a named opponent Pokémon from using attacks at all, typically for their next turn. Distinct from `RETREAT_LOCK` (blocks retreat, not attacking). | `/the Defending Pok[eé]mon can'?t use attacks/i` | scope + duration |
| `SELF_NO_WEAKNESS` | Temporarily removes this Pokémon's own Weakness (the opponent's weakness bonus no longer applies to it), for a stated duration. Distinct from `DAMAGE_IMMUNE_FROM` (blocks damage outright) — this only nullifies the Weakness multiplier. | `/this Pok[eé]mon has no Weakness/i` | duration |
| `SELF_RETURN_TO_HAND` | Returns this Pokémon (and its attachments) to the owner's hand, typically as an attack consequence. | `/put this Pok[eé]mon and all attached cards into your hand/i` | none |
| `COOLDOWN` *(seed)* | This specific attack/ability can't be used again for a stated duration (self-imposed cooldown on itself, not a lock on the opponent). | `/this Pok[eé]mon can'?t use (?:\S.+\|attacks)/i` (named-attack or blanket self-reference) — the original pattern wrongly required "during/next" to appear *after* "can't use X," but Phase 2e found the duration clause almost always comes first ("**During your next turn**, this Pokémon can't use Mega Brave") — dropped that requirement since the duration is captured separately anyway | which attack/ability (or "all attacks"); duration |
| `MILL` *(seed)* | Forces card(s) from the **opponent's** deck into their discard pile without them being drawn. | `/discard the top (\d+)? ?cards? of your opponent'?s deck/i` | count (base + any conditional bonus) |
| `EXTRA_PRIZE` | Take an additional Prize card when a stated KO condition is met (often coin-flip-gated). | `/take (\d+) more Prize cards?/i` | group 1 = bonus count; gating qualifier noted separately |
| `RETREAT_COST_MOD` | Modifies (reduces, zeroes, or increases) the Retreat Cost for a stated scope of Pokémon — own, both sides, or (Tool context) a single holder. | `/no Retreat Cost\|Retreat Cost is (?:\{C\})+ (?:less\|more)\|Retreat Cost of .+ is (?:\{C\})+ (?:less\|more)/i` — widened during spec 11b's validation both to fix a quantifier-scoping bug (`\{C\}+` only repeated the closing brace, not the whole `{C}` unit — corrected to `(?:\{C\})+`) and to cover increases as well as decreases (a Stadium, Gravity Gemstone, raises retreat cost for both Active Pokémon) | scope; new cost or delta (signed) |
| `ATTACK_INHERIT` | Own evolved Pokémon may use attacks belonging to their own pre-evolution stage(s) (energy cost still required). | `/can use any attack from its previous Evolutions/i` | scope |
| `WEAKNESS_OVERRIDE` | Overrides the Weakness type of a stated scope of Pokémon (typically the opponent's, by type). | `/[Tt]he Weakness of (.+?) is now \{(\w)\}/i` | group 1 = scope; group 2 = new weakness type |
| `STADIUM_REMOVE` | Discards the Stadium currently in play (regardless of owner), typically as a bonus-damage consequence. | `/discard that Stadium/i` | none |
| `ATTACK_DISABLE` | Disables one specific, player-chosen attack belonging to the opponent's Active Pokémon, typically for their next turn. Distinct from `ATTACK_LOCK` (blocks *all* attacks, not just a chosen one). | `/[Cc]hoose 1 of your opponent'?s Active Pok[eé]mon'?s attacks.*can'?t use that attack/i` | duration |
| `HP_BUFF` | Increases (or, with a negative magnitude, decreases — a debuff) this Pokémon's max/current HP by a stated amount, typically gated by a board condition or scope restriction. | `/(?:gets\|get) [+-](\d+) HP/i` — originally required a literal `+`, contradicting this tag's own documented negative-magnitude convention (see Gravity Mountain in 11b's Stadium batch, "gets **-30** HP") until an audit caught that the regex was never actually updated to allow it | group 1 = HP delta (signed) |
| `SWITCH_FORCE` *(seed)* | Forces the **opponent's** Benched Pokémon into the Active Spot (a forced opponent switch), as opposed to `SELF_SWITCH` (repositioning the user's own side). | `/switch (?:out|in) (?:your opponent'?s|1 of your opponent'?s) .*(?:Active|Bench)/i` | who chooses the replacement (self/opponent) |
| `DISCARD_OPP` *(seed)* | Forces the **opponent** to discard card(s) from their hand — a single unspecified card, a fixed count, "down to" a target hand size, or (rarer) the acting player choosing which cards after the opponent reveals their hand. | `/your opponent discards? (?:a card\|cards?\|\d+ cards?) from their hand\|opponent discards first\|each player (?:shuffles their hand into their deck\|discards cards from their hand) until they have (\d+) cards\|you discard .+ you find (?:there\|in their hand)/i` — widened during spec 11b's Trainer-corpus validation to cover "discard down to N" and reveal-then-choose phrasings; a later audit found Team Rocket's Porygon's "your opponent discards **a card** from their hand" (singular, no count) still didn't match, so that alternative was added too | count, or target hand size; any gating condition |
| `ENERGY_AMPLIFY` | Passively increases the Energy value provided by a stated Energy type attached to a scope of own Pokémon (an energy multiplier, not an attachment). | `/each (?:Basic )?\{?\w+\}? Energy attached to (.+?) provides \{(\w)\}\{\2\} Energy/i` | scope; energy type; multiplier |
| `STAT_DEBUFF` *(seed)* | Passively reduces a named opponent Pokémon's outgoing attack damage, typically for a duration. Opposite of `STAT_BUFF`. | `/attacks used by the Defending Pok[eé]mon do (\d+) less damage/i` | group 1 = damage reduction; duration |
| `ENERGY_RETURN_TO_DECK` | Shuffles Energy attached to a stated Pokémon back into the owner's deck, typically paid as a cost enabling a bonus effect. Distinct from `DISCARD_SELF` (goes to discard, not deck). | `/shuffle (\d+) Energy attached to this Pok[eé]mon into your deck/i` | group 1 = count |
| `SEARCH_BENCH` | Searches the deck for Pokémon and places them directly onto the Bench, bypassing the hand. Distinct from `SEARCH_HAND` (goes to hand) and `SEARCH_ATTACH` (attaches Energy). | `/search (?:your\|their) deck for (?:up to )?(\d+) Basic .*Pok[eé]mon.*put (?:it\|them) onto (?:your\|their) Bench/i` — the original pattern required "Basic Pokémon" immediately followed by "and put," which broke on both an inserted qualifying clause (Buddy-Buddy Poffin: "Basic Pokémon **with 70 HP or less** and put...") and a typed-Energy-symbol variant (Telepath Psychic Energy: "Basic **{P}** Pokémon") | group 1 = count |
| `COPY_ATTACK` *(seed)* | Copies and uses one of another named Pokémon's attacks as this attack (the opponent's Active Tera Pokémon, or one of the user's own Benched Pokémon of a named family). **This row was missing entirely until a code-review audit found it** — the tag was in the original Phase 0 seed list and is actively used in the production lookup table for 2 real meta cards (Team Rocket's Mimikyu, N's Zoroark ex), but never got promoted to a formal catalog entry when those rows were tagged, leaving it with no detection rule at all for the unseen-card fallback path. | `/[Cc]hoose 1 of (?:your opponent'?s Active Tera Pok[eé]mon'?s\|your Benched .+'?s) attacks and use it as this attack/i` | captured group = source (opponent's Active Tera Pokémon / own Benched family) |

### `distribution` qualifier (Phase 2 addition, 2026-07-16)

Applies to any quantity-bearing tag whose cap can be split across more than one target in a
single resolution: `COUNTER_PLACE`, `COUNTER_MOVE`, `ENERGY_ACCEL`, `SEARCH_ATTACH` (`SNIPE`
has the same theoretical shape but no currently-tagged row exercises it — every `SNIPE` row
in this batch targets exactly one benched Pokémon per its text). Two values:

- `single` (default, not written explicitly) — the full amount goes to one target.
- `shared_cap_any_split` — the stated cap is a **pool**, freely partitioned by the acting
  player across multiple eligible targets in one resolution ("in any way you like" /
  `shared_total_cap` / `chosen_nonnegative_integer_partition` in the registry) — not N
  guaranteed per target.

Found by a systematic two-pass search (English-text pattern match for "any way you like" /
"any distribution", cross-checked against the registry's own `shared_total_cap` /
`any_distribution` structural fields) across all 201 rows, not by re-inspecting only the
two instances found via worked examples. Exactly 6 rows qualify — every one of them now
carries the qualifier explicitly in its row entry below:

`card:121:attack:1` (Dragapult ex, `COUNTER_PLACE`), `card:190:ability:0` (Archaludon ex,
`ENERGY_ACCEL`), `card:245:attack:0` (Alakazam, `COUNTER_MOVE`), `card:648:ability:0`
(Marnie's Grimmsnarl ex, `SEARCH_ATTACH`), `card:666:attack:0` (Cinderace, `SEARCH_ATTACH`),
`card:678:attack:0` (Mega Lucario ex, `ENERGY_ACCEL`).

## Phase 2e — detection-rule validation against assigned rows' text (2026-07-16)

Ran every tag's detection rule against the actual English text of every row assigned that
tag in the manual table (141 tag-assignment pairs, excluding the two structural/non-textual
flags `DAMAGE` and `CONDITIONAL`, which aren't meant to be regex-detected from text alone).
First pass: 43 failures. Root-caused before assuming any were real:

- **~29 of the 43 were a single systematic bug, not 29 separate problems.** Every regex in
  this catalog was drafted with an ASCII straight apostrophe (`'?`) for contractions like
  "isn't"/"can't"/"doesn't." Real card text — confirmed by inspecting the actual character
  codes — uses the Unicode right single quotation mark (`’`, U+2019) exclusively, never the
  ASCII apostrophe. `'?` never matches `’`, so almost every rule referencing a contraction
  would have silently failed against every real card, known or unseen, in a real
  implementation. **Any future implementation of these detection rules must match on a
  character class covering both (`['’]`), or normalize apostrophes before matching** — this
  is not optional polish, the vocabulary is largely non-functional without it.
- The remaining ~14 were genuine gaps in 8 distinct rules — real phrasing variants the
  drafted patterns didn't anticipate (parenthetical qualifiers, reordered clauses,
  additional inserted clauses, a third grammatical form for inflicting a condition, a
  missing "all" quantity word). Each is now fixed in the catalog above, with an inline note
  on what broke it and why. Two are worth flagging beyond the inline notes because they
  reveal a shape likely to recur in unseen cards, not just a one-off patch: (1) attacks that
  say "damage to 1 of your opponent's Pokémon" *without* the word "Benched" still function
  as `SNIPE` — real TCG text sometimes states the bench-eligibility only in a parenthetical
  rules clarification, not inline; (2) duration clauses ("During your next turn...") come
  *before* the effect they gate far more often than after it — several draft regexes had
  baked in the opposite assumption.
- After all 8 fixes, re-ran the full 141-pair validation: **0 failures.** Also spot-checked
  that the two broadened rules (`SNIPE`, `DAMAGE_IMMUNE_FROM`) still correctly reject the
  documented near-miss cases from this file's own examples (Alakazam's hand-scaled-counter
  attack does not trip the broadened `SNIPE` pattern).
- **Also ran the false-positive direction**, beyond what Phase 2 strictly requires: every
  tag's rule against all 201 rows' text, not just the rows assigned that tag. First pass
  found 6 unwanted matches. Two are a deliberate, accepted policy artifact, not bugs: `IGNORES_ACTIVE_EFFECTS`
  is defined as strictly broader than and subsuming `IGNORES_WEAKNESS`/`IGNORES_RESISTANCE`
  (see that tag's own catalog entry), so the two known-card rows using the combined phrasing
  ("isn't affected by Weakness or Resistance, **or by** any effects on...") are deliberately
  tagged with only the broader tag in the manual table — but the narrower rules' regexes
  still correctly detect that their literal phrase is *present* in the text, since the
  subsumption is a manual-tagging policy choice, not a fact about the English text. Left
  as-is: if an unseen card trips both the narrow and broad rules together, that's harmless,
  truthful redundancy, not wrong information, and production only ever runs unseen cards
  through the regex path in the first place. The other 4 (all on `DISCARD_SELF`) were real
  bugs, fixed above.

## Code-review audit and fix pass (2026-07-16)

A `/code-review` pass re-extracted every regex and every assignment **directly from the
current file text** (not from memory or the session's scratch validation scripts) and
re-ran coverage/recall/precision from scratch. This caught a real, systemic issue the
in-session Phase 2 write-ups had missed: several regexes were fixed and validated in
scratch Python scripts during the session but the fix was never actually written back into
this catalog — the "0 recall failures" claims elsewhere in this file describe the scratch
script's regex set, not always what's on the page. Found and fixed:

- `COPY_ATTACK` had **no catalog entry at all** despite being used in the production lookup
  table for 2 real cards (Team Rocket's Mimikyu, N's Zoroark ex) — added.
- `DRAW`, `COUNTER_PLACE`, `ENERGY_ACCEL`, `SELF_SWITCH`, `EVOLVE_SEARCH`, `HP_BUFF`,
  `COUNTER_MOVE`, `SELF_MILL`, `SEARCH_BENCH`, `DISCARD_OPP`, `REVEAL_DIG` all had regexes
  narrower than the text they were supposed to cover — each entry above now carries an
  inline note on exactly what broke and which card exposed it.
- Two apparent extra findings during the audit turned out to be artifacts of the audit
  tooling itself, not spec bugs, and were verified against raw source before being
  discarded: a mention of `HP_DEBUFF` inside `HP_BUFF`'s own explanatory qualifier text
  (not a real assignment), and the same pattern for a stray `ON_DAMAGED_TRIGGER` mention
  inside a Stadium row's qualifier prose (spec 11b).
- After all fixes: re-ran coverage (310/310 rows across both 11a and 11b, zero missing/
  duplicate), recall (285/285 tag-assignment pairs match), and precision (0 unintended
  false positives — the only 4 matches outside assigned rows are the already-documented
  `IGNORES_ACTIVE_EFFECTS` redundancy from Phase 2e, not new). Full audit tooling and
  methodology mirrored Phase 2e's approach but re-derived independently from the files
  rather than reusing session state, specifically to catch this class of drift.

## Phase 2f — targeted conflation re-check (2026-07-16)

Prompted by how many issues Phase 2a-2e surfaced: re-read the source text for every tag
with 3+ assignments (19 tags, the highest-conflation-risk group) side by side, specifically
checking whether the tag's *abstract catalog definition* — not just each row's individually
correct qualifier — actually holds for every instance. Found one real gap: `SELF_SWITCH`'s
definition ("switches the acting/using Pokémon itself... pulling up another owned
Pokémon") was written narrowly around 3 of its 4 assigned rows (Abra/Dunsparce/Buneary, all
literally "switch this Pokémon with 1 of your Benched Pokémon") and doesn't actually
describe the 4th: Pecharunt ex's ability explicitly *excludes itself* from the swap and
instead lets the player promote any other chosen Benched `{D}` Pokémon into Active. The
row's own qualifier text already said this correctly at assignment time, but the tag's
general definition — what an implementer or an unseen-card classifier would actually read —
did not. Fixed with a `self_referential` qualifier; both regex alternatives verified to
match exactly their 4 intended rows and no others.

The other 18 multi-instance tags were re-checked the same way and found consistent: their
apparent semantic variety (e.g. `DAMAGE_IMMUNE_FROM` spanning self-scope/bench-scope,
permanent/coin-flip-gated, unrestricted/attacker-restricted) is real but was already
captured accurately in each row's own qualifier prose, just not through a uniform named
field the way `COUNTER_MOVE`'s `conserved` or the new `distribution` qualifier are. Noted
as a Phase 4 formalization item (turn the ad hoc qualifier prose on `DAMAGE_IMMUNE_FROM`,
`EFFECT_IMMUNE`, and `COUNTER_PLACE` into named fields when the field list is locked) —
not a Phase 2 correctness issue, since no instance found was actually wrong, only
inconsistently formatted.

## Manual assignment table — Phase 1 progress

**Batch 1 of ~6 (20 highest-frequency Pokémon by `total_copies`, IDs 741/742/743/305/66/
344/345/756/112/646/343/140/648/647/860/1030/104/1031/414/400 — 34 rows).** Ground truth
taken directly from each row's `program`/`damage_profile`, not English text.

| Card | Effect ID | Tags assigned |
|---|---|---|
| Abra | `card:741:attack:0` | `DAMAGE`(10), `SELF_SWITCH` |
| Kadabra | `card:742:attack:0` | `DAMAGE`(30) |
| Kadabra | `card:742:ability:0` | `DRAW`(2) |
| Alakazam | `card:743:attack:0` | `COUNTER_PLACE`(2 × cards in hand — dynamic) |
| Alakazam | `card:743:ability:0` | `DRAW`(3) |
| Dunsparce | `card:305:attack:0` | `SELF_SWITCH` (0-damage repositioning attack — no `DAMAGE` tag) |
| Dunsparce | `card:305:attack:1` | `DAMAGE`(20) |
| Dudunsparce | `card:66:attack:0` | `DAMAGE`(90) |
| Dudunsparce | `card:66:ability:0` | `DRAW`(up to 3), `SELF_MILL`, `CONDITIONAL`(qualifier: **near-always-true** — fails only if the player's own deck was empty at draw time, not a meaningfully variable board condition) |
| Dwebble | `card:344:attack:0` | `EVOLVE_SEARCH` |
| Crustle | `card:345:attack:0` | `DAMAGE`(120), `IGNORES_ACTIVE_EFFECTS` |
| Crustle | `card:345:ability:0` | `DAMAGE_IMMUNE_FROM`(scope: self; qualifier: only vs `{ex}` attackers) |
| Mega Kangaskhan ex | `card:756:attack:0` | `RNG_SCALING_DAMAGE`(base 200, +50/heads, `expected_value`=250, `credible_max`=350 [registry-approved ceiling, `HR-B05-002`], `theoretical_max`=unbounded) — see worked correction below; earlier draft wrongly called this row a parse gap |
| Mega Kangaskhan ex | `card:756:ability:0` | `DRAW`(2) |
| Munkidori | `card:112:attack:0` | `DAMAGE`(60), `CONDITION`(Confused) |
| Munkidori | `card:112:ability:0` | `COUNTER_MOVE`(up to 3, qualifier: conserved=**false** — net transfer, own Pokémon → opponent's Pokémon, changes total board damage) |
| Marnie's Impidimp | `card:646:attack:0` | `DRAW`(1) |
| Marnie's Impidimp | `card:646:attack:1` | `DAMAGE`(10) |
| Shaymin | `card:343:attack:0` | `DAMAGE`(30) |
| Shaymin | `card:343:ability:0` | `DAMAGE_IMMUNE_FROM`(scope: benched Pokémon without a Rule Box) |
| Fezandipiti ex | `card:140:attack:0` | `DAMAGE`(100), `SNIPE` |
| Fezandipiti ex | `card:140:ability:0` | `DRAW`(3) |
| Marnie's Grimmsnarl ex | `card:648:attack:0` | `DAMAGE`(180), `SNIPE`(30) |
| Marnie's Grimmsnarl ex | `card:648:ability:0` | `SEARCH_ATTACH`(up to 5, Basic `{D}` Energy only, `distribution`=**shared_cap_any_split**) |
| Marnie's Morgrem | `card:647:attack:0` | `DAMAGE`(60) |
| Snorunt | `card:860:attack:0` | `DAMAGE`(10) |
| Staryu | `card:1030:attack:0` | `DAMAGE`(20) |
| Froslass | `card:104:attack:0` | `DAMAGE`(60) |
| Froslass | `card:104:ability:0` | `COUNTER_PLACE`(1 per Pokémon-with-Ability, both sides, self excluded) |
| Mega Starmie ex | `card:1031:attack:0` | `DAMAGE`(120), `SNIPE`(50) |
| Mega Starmie ex | `card:1031:attack:1` | `DAMAGE`(210), `IGNORES_ACTIVE_EFFECTS` |
| Team Rocket's Articuno | `card:414:attack:0` | `DAMAGE`(60 base / 120 if condition met), `CONDITIONAL` |
| Team Rocket's Articuno | `card:414:ability:0` | `EFFECT_IMMUNE`(scope: Basic Team Rocket's Pokémon family) |
| Team Rocket's Tarountula | `card:400:attack:0` | `DAMAGE`(30), `RECOIL`(10) |

Note on boilerplate folded into existing tags rather than given their own: "don't apply
Weakness/Resistance for Benched Pokémon" is standard game rules text accompanying `SNIPE`
(bench damage never applies W/R by default) and isn't treated as extra signal. "Shuffle
your deck" immediately after a deck search is folded into `SEARCH_ATTACH`/`EVOLVE_SEARCH`
as expected cleanup, not a separate tag — reserved for a future `MILL`-family tag only when
shuffling serves a distinct strategic purpose (e.g. disrupting opponent deck order).

**Batch 2 of ~6 (next 20 by frequency: IDs 401/379/380/341/434/119/120/342/381/235/431/666/
861/121/131/132/117/93/133/92 — 35 rows).**

| Card | Effect ID | Tags assigned |
|---|---|---|
| Team Rocket's Spidops | `card:401:attack:0` | `DAMAGE`(30 × own Team Rocket's Pokémon in play — dynamic) |
| Team Rocket's Spidops | `card:401:ability:0` | `ENERGY_ACCEL`(source: own discard pile → self) |
| Cynthia's Gible | `card:379:attack:0` | `DAMAGE`(20), `IGNORES_RESISTANCE` |
| Cynthia's Gabite | `card:380:attack:0` | `DAMAGE`(40) |
| Cynthia's Gabite | `card:380:ability:0` | `SEARCH_HAND`("a Cynthia's Pokémon") |
| Cynthia's Roselia | `card:341:attack:0` | `DAMAGE`(20) |
| Team Rocket's Mimikyu | `card:434:attack:0` | `COPY_ATTACK`(source: opponent's Active Tera Pokémon) |
| Dreepy | `card:119:attack:0` | `DAMAGE`(10) |
| Dreepy | `card:119:attack:1` | `DAMAGE`(40) |
| Drakloak | `card:120:attack:0` | `DAMAGE`(70) |
| Drakloak | `card:120:ability:0` | `REVEAL_DIG`(top 2, keep 1 to hand, other to bottom) |
| Cynthia's Roserade | `card:342:attack:0` | `DAMAGE`(80) |
| Cynthia's Roserade | `card:342:ability:0` | `STAT_BUFF`(scope: own Cynthia's-named Pokémon; +30 dmg to opponent Active, pre-W/R) |
| Cynthia's Garchomp ex | `card:381:attack:0` | `DAMAGE`(100), `DRAW`(to hand size 6), `CONDITIONAL` |
| Cynthia's Garchomp ex | `card:381:attack:1` | `DAMAGE`(260), `DISCARD_SELF`(all Energy on self) |
| Budew | `card:235:attack:0` | `DAMAGE`(10), `ITEM_LOCK`(opponent, their next turn) |
| Team Rocket's Mewtwo ex | `card:431:attack:0` | `DAMAGE`(160 base, +60 per Energy discarded, up to 2), `DISCARD_SELF`(up to 2, from Benched Pokémon) |
| Team Rocket's Mewtwo ex | `card:431:ability:0` | *(none — known gap, see below)* |
| Cinderace | `card:666:attack:0` | `DAMAGE`(50), `SEARCH_ATTACH`(up to 3, Basic Energy → own Bench, `distribution`=**shared_cap_any_split**) |
| Cinderace | `card:666:ability:0` | `SETUP_ALT_PLACEMENT` |
| Mega Froslass ex | `card:861:attack:0` | `DAMAGE`(50 × opponent's hand size — dynamic) |
| Mega Froslass ex | `card:861:attack:1` | `DAMAGE`(150), `CONDITION`(Asleep) |
| Dragapult ex | `card:121:attack:0` | `DAMAGE`(70) |
| Dragapult ex | `card:121:attack:1` | `DAMAGE`(200), `COUNTER_PLACE`(6, opponent's Bench, `distribution`=**shared_cap_any_split**) |
| Duskull | `card:131:attack:0` | `REVIVE_FROM_DISCARD`(up to 3, own discard → Bench) |
| Duskull | `card:131:attack:1` | `DAMAGE`(30) |
| Dusclops | `card:132:attack:0` | `DAMAGE`(50) |
| Dusclops | `card:132:ability:0` | `COUNTER_PLACE`(5, any opponent Pokémon), `SELF_KO` |
| Cornerstone Mask Ogerpon ex | `card:117:attack:0` | `DAMAGE`(140), `IGNORES_ACTIVE_EFFECTS` |
| Cornerstone Mask Ogerpon ex | `card:117:ability:0` | `DAMAGE_IMMUNE_FROM`(scope: self; qualifier: only vs Ability-holding attackers) |
| Dipplin | `card:93:attack:0` | `DAMAGE`(20 × own Bench count — dynamic) |
| Dipplin | `card:93:ability:0` | `DOUBLE_ATTACK`, `CONDITIONAL` (gated on Festival Grounds Stadium) |
| Dusknoir | `card:133:attack:0` | `DAMAGE`(150), `RETREAT_LOCK`(opponent's Defending Pokémon, their next turn) |
| Dusknoir | `card:133:ability:0` | `COUNTER_PLACE`(13, any opponent Pokémon), `SELF_KO` |
| Applin | `card:92:attack:0` | `DAMAGE`(10), `COIN_FLIP_DAMAGE`(+20 if heads) |

**Known gaps log (Phase 2 will re-confirm and finalize this list):**

- ~~`card:756:attack:0` (Mega Kangaskhan ex) — RNG-loop damage~~ — **retracted, not a gap.**
  Originally logged here as a coverage exception on the mistaken belief the registry's
  program parsed to zero operations. That was a bug in this spec's own extraction script
  (no case for the `repeat` node kind), not a registry gap — see the Phase 0 correction
  above and the worked example in the interview transcript (2026-07-16). The row is fully
  tagged with the registry's own human-approved `expected_value`/`credible_max` statistics.
- `card:431:ability:0` (Team Rocket's Mewtwo ex) — "This Pokémon can't attack unless you have
  4 or more Team Rocket's Pokémon in play." This row's entire content is an attack-legality
  gate, not a separate resolvable effect. Per this spec's working decision #2 (the tag block
  encodes effect content, not activation/legality triggers), attack-eligibility conditions
  are assumed to already be reflected in the live legal-action system elsewhere in the
  architecture and are deliberately left untagged here — a genuine, explicit all-zero row,
  not a silent gap.

**Batch 3 of ~6 (next 20 by frequency: IDs 89/90/387/247/169/190/164/506/689/65/1071/817/
678/677/848/849/676/245/818/58 — 35 rows).**

A recurring pattern in this batch: coin-flip- or board-condition-gated **non-damage**
effects (Dunsparce's coin-flip self-shield, Solrock's Lunatone-gated attack) reuse the
target tag (`DAMAGE_IMMUNE_FROM`, `EFFECT_IMMUNE`, `DAMAGE`, etc.) with a gating qualifier
noted in the assignment, rather than minting a new tag family per gate type — consistent
with `COIN_FLIP_DAMAGE` already being the dedicated exception for the damage-magnitude
case specifically.

| Card | Effect ID | Tags assigned |
|---|---|---|
| Grookey | `card:89:attack:0` | `DAMAGE`(10) |
| Grookey | `card:89:attack:1` | `DAMAGE`(30) |
| Thwackey | `card:90:attack:0` | `DAMAGE`(50) |
| Thwackey | `card:90:ability:0` | `SEARCH_HAND`(any card) |
| Cynthia's Spiritomb | `card:387:attack:0` | `DAMAGE`(10 × total damage counters on own Benched Cynthia's Pokémon — dynamic), `IGNORES_WEAKNESS` |
| Swirlix | `card:247:attack:0` | `COUNTER_PLACE`(2, any opponent Pokémon) |
| Swirlix | `card:247:ability:0` | `DOUBLE_ATTACK`, `CONDITIONAL` (gated on Festival Grounds Stadium) |
| Duraludon | `card:169:attack:0` | `DAMAGE`(30) |
| Duraludon | `card:169:attack:1` | `DAMAGE`(80 base, +10 per damage counter on self — dynamic) |
| Archaludon ex | `card:190:attack:0` | `DAMAGE`(220), `SELF_NO_WEAKNESS`(opponent's next turn) |
| Archaludon ex | `card:190:ability:0` | `ENERGY_ACCEL`(up to 2, Basic `{M}` Energy, own discard → own `{M}` Pokémon, `distribution`=**shared_cap_any_split**) |
| Comfey | `card:164:attack:0` | `DRAW`(3, both players) |
| Comfey | `card:164:attack:1` | `DAMAGE`(20), `COIN_FLIP_DAMAGE`(+20 if heads) |
| Cubchoo | `card:506:attack:0` | `DAMAGE`(10), `ATTACK_LOCK`(opponent's Defending Pokémon, their next turn) |
| Yveltal | `card:689:attack:0` | `DAMAGE`(20), `RETREAT_LOCK`(opponent's Defending Pokémon, their next turn) |
| Yveltal | `card:689:attack:1` | `DAMAGE`(110) |
| Dunsparce | `card:65:attack:0` | `DAMAGE`(10) |
| Dunsparce | `card:65:attack:1` | `DAMAGE`(30), `DAMAGE_IMMUNE_FROM`(scope: self; qualifier: coin-flip heads-gated; duration: opponent's next turn), `EFFECT_IMMUNE`(same qualifiers) |
| Meowth ex | `card:1071:attack:0` | `DAMAGE`(60), `SELF_RETURN_TO_HAND` |
| Meowth ex | `card:1071:ability:0` | `SEARCH_HAND`(a Supporter card) |
| Bramblin | `card:817:attack:0` | `COUNTER_PLACE`(1, any opponent Pokémon) |
| Mega Lucario ex | `card:678:attack:0` | `DAMAGE`(130), `ENERGY_ACCEL`(up to 3, Basic `{F}` Energy, own discard → own Bench, `distribution`=**shared_cap_any_split**) |
| Mega Lucario ex | `card:678:attack:1` | `DAMAGE`(270), `COOLDOWN`(this attack, next turn) |
| Riolu | `card:677:attack:0` | `DAMAGE`(30), `COOLDOWN`(this attack, next turn) |
| Buneary | `card:848:attack:0` | `SELF_SWITCH` |
| Buneary | `card:848:attack:1` | `DAMAGE`(20) |
| Mega Lopunny ex | `card:849:attack:0` | `DAMAGE`(60 base, 230 if condition met), `CONDITIONAL` (gated on: moved Bench→Active this turn) |
| Mega Lopunny ex | `card:849:attack:1` | `DAMAGE`(160), `IGNORES_ACTIVE_EFFECTS` |
| Solrock | `card:676:attack:0` | `DAMAGE`(70), `IGNORES_WEAKNESS`, `IGNORES_RESISTANCE`, `CONDITIONAL` (gated on: Lunatone present on own Bench; else no-op) |
| Alakazam (alt) | `card:245:attack:0` | `CONDITION`(Confused), `COUNTER_MOVE`(any amount, qualifier: conserved=**true** — opponent-internal redistribution only, zero net damage added/removed; contrast Munkidori's cross-side net transfer; `distribution`=**shared_cap_any_split**) |
| Alakazam (alt) | `card:245:attack:1` | `DAMAGE`(10 base, +50 per Energy attached to opponent's Active — dynamic) |
| Brambleghast | `card:818:attack:0` | `DAMAGE`(80) |
| Brambleghast | `card:818:ability:0` | `CONDITION`(Confused) |
| Great Tusk | `card:58:attack:0` | `MILL`(1 base, +3 conditional — up to 4), `CONDITIONAL` (gated on: played an Ancient Supporter this turn) |
| Great Tusk | `card:58:attack:1` | `DAMAGE`(160) |

**Batch 4 of ~6 (next 20 by frequency: IDs 675/649/791/214/959/184/57/745/432/73/74/174/272/
746/747/109/607/31/306/463 — 36 rows).**

| Card | Effect ID | Tags assigned |
|---|---|---|
| Lunatone | `card:675:attack:0` | `DAMAGE`(50) |
| Lunatone | `card:675:ability:0` | `DRAW`(3), `DISCARD_SELF`(1, Basic `{F}` Energy from hand — cost) |
| Marnie's Morpeko | `card:649:attack:0` | `DAMAGE`(20 base, +40 per `{D}` Energy attached to self — dynamic) |
| Moltres | `card:791:attack:0` | `DAMAGE`(20 base, 110 if condition met), `CONDITIONAL` (gated on: opponent's Active is a Pokémon `ex`) |
| Togekiss | `card:214:attack:0` | `DAMAGE`(140) |
| Togekiss | `card:214:ability:0` | `EXTRA_PRIZE`(+1, coin-flip heads-gated, on opponent's Active KO) |
| Togepi | `card:959:attack:0` | `DAMAGE`(30) |
| Latias ex | `card:184:attack:0` | `DAMAGE`(200), `COOLDOWN`(all own attacks, next turn) |
| Latias ex | `card:184:ability:0` | `RETREAT_COST_MOD`(scope: own Basic Pokémon; new cost: 0) |
| Relicanth | `card:57:attack:0` | `DAMAGE`(30) |
| Relicanth | `card:57:ability:0` | `ATTACK_INHERIT`(scope: own evolved Pokémon) |
| Ralts | `card:745:attack:0` | `DRAW`(1) |
| Ralts | `card:745:attack:1` | `DAMAGE`(10) |
| Team Rocket's Wobbuffet | `card:432:attack:0` | `COUNTER_MOVE`(all, own Benched Team Rocket's Pokémon → opponent's Active, qualifier: conserved=**false** — net transfer) |
| Team Rocket's Wobbuffet | `card:432:attack:1` | `DAMAGE`(70) |
| Rellor | `card:73:attack:0` | `DAMAGE`(30), `RECOIL`(10) |
| Rabsca | `card:74:attack:0` | `DAMAGE`(10 base, +30 per Energy attached to opponent's Active — dynamic) |
| Rabsca | `card:74:ability:0` | `DAMAGE_IMMUNE_FROM`(scope: own Bench), `EFFECT_IMMUNE`(scope: own Bench) |
| Fan Rotom | `card:174:attack:0` | `DAMAGE`(70), `CONDITIONAL` (gated on: no Stadium in play; else no-op) |
| Fan Rotom | `card:174:ability:0` | `SEARCH_HAND`(up to 3, `{C}`-type Pokémon with ≤100 HP) |
| Lillie's Clefairy ex | `card:272:attack:0` | `DAMAGE`(20 base, +20 per Benched Pokémon both sides combined — dynamic) |
| Lillie's Clefairy ex | `card:272:ability:0` | `WEAKNESS_OVERRIDE`(scope: opponent's `{N}`-type Pokémon in play; new weakness: `{P}`) |
| Kirlia | `card:746:attack:0` | `SEARCH_HAND`(up to 3, any Pokémon) |
| Kirlia | `card:746:attack:1` | `DAMAGE`(30) |
| Mega Gardevoir ex | `card:747:attack:0` | `SEARCH_ATTACH`(1 per own Benched Pokémon, Basic `{P}` Energy → that Pokémon) |
| Mega Gardevoir ex | `card:747:attack:1` | `DAMAGE`(50 × total `{P}` Energy attached across all own Pokémon — dynamic) |
| Abra (alt) | `card:109:attack:0` | `DAMAGE`(10) |
| Abra (alt) | `card:109:ability:0` | `SELF_MILL` |
| Terrakion | `card:607:attack:0` | `DAMAGE`(50 base, 130 if condition met), `CONDITIONAL` (gated on: an own Pokémon KO'd by attack damage during opponent's last turn) |
| Terrakion | `card:607:attack:1` | `DAMAGE`(100) |
| Chi-Yu | `card:31:attack:0` | `DRAW`(2) |
| Chi-Yu | `card:31:attack:1` | `DAMAGE`(60 base, 120 if condition met), `STADIUM_REMOVE`, `CONDITIONAL` (gated on: a Stadium in play) |
| Dudunsparce ex | `card:306:attack:0` | `DAMAGE`(60 × opponent's Pokémon-`ex` count in play — dynamic) |
| Dudunsparce ex | `card:306:attack:1` | `DAMAGE`(150), `IGNORES_ACTIVE_EFFECTS` |
| Team Rocket's Murkrow | `card:463:attack:0` | `SEARCH_HAND`(a Supporter card) |
| Team Rocket's Murkrow | `card:463:attack:1` | `DAMAGE`(30), `ATTACK_DISABLE`(opponent's Active, chosen attack, their next turn) |

**Batch 5 of ~6 (next 20 by frequency: IDs 891/116/122/183/597/96/673/674/292/293/1051/1052/
473/474/303/333/63/906/150/709 — 33 rows).**

| Card | Effect ID | Tags assigned |
|---|---|---|
| Team Rocket's Honchkrow | `card:891:attack:0` | `DAMAGE`(60 × Team-Rocket-named Supporters discarded — dynamic, uncapped), `DISCARD_SELF`(any number, Team-Rocket-named Supporters, from hand) |
| Team Rocket's Honchkrow | `card:891:attack:1` | `DAMAGE`(100) |
| Okidogi | `card:116:attack:0` | `DAMAGE`(70) |
| Okidogi | `card:116:ability:0` | `HP_BUFF`(+100), `STAT_BUFF`(scope: self; +100 dmg to opponent's Active, pre-W/R), `CONDITIONAL` (gated on: `{D}` Energy attached to self) |
| Tatsugiri | `card:122:attack:0` | `DAMAGE`(50) |
| Tatsugiri | `card:122:ability:0` | `REVEAL_DIG`(top 6; criteria: find and take a Supporter card) |
| Smoochum | `card:183:attack:0` | `SEARCH_ATTACH`(up to 2, Basic `{P}` Energy → 1 own Benched Pokémon) |
| Frillish | `card:597:attack:0` | `DAMAGE`(20), `ITEM_LOCK`(opponent, their next turn) |
| Teal Mask Ogerpon ex | `card:96:attack:0` | `DAMAGE`(30 base, +30 per Energy attached to both Active Pokémon combined — dynamic) |
| Teal Mask Ogerpon ex | `card:96:ability:0` | `ENERGY_ACCEL`(1, Basic `{G}` Energy, hand → self), `DRAW`(1, conditional), `CONDITIONAL` |
| Makuhita | `card:673:attack:0` | `DAMAGE`(10) |
| Makuhita | `card:673:attack:1` | `DAMAGE`(30) |
| Hariyama | `card:674:attack:0` | `DAMAGE`(210), `RECOIL`(70) |
| Hariyama | `card:674:ability:0` | `SWITCH_FORCE`(target: opponent's Bench → Active, user chooses) |
| N's Zorua | `card:292:attack:0` | `DAMAGE`(20) |
| N's Zoroark ex | `card:293:attack:0` | `COPY_ATTACK`(source: own Benched N's-named Pokémon's attack) |
| N's Zoroark ex | `card:293:ability:0` | `DISCARD_SELF`(1, any card, from hand — cost), `DRAW`(2) |
| Binacle | `card:1051:attack:0` | `DRAW`(2) |
| Binacle | `card:1051:attack:1` | `DAMAGE`(30) |
| Barbaracle | `card:1052:attack:0` | `DAMAGE`(80) |
| Barbaracle | `card:1052:ability:0` | `ENERGY_ACCEL`(1, Basic `{F}` Energy, hand → own `{F}` Pokémon) |
| Team Rocket's Porygon | `card:473:attack:0` | `DISCARD_SELF`(1, any card, from hand), `DISCARD_OPP`(1, conditional on self-discard), `CONDITIONAL` |
| Team Rocket's Porygon2 | `card:474:attack:0` | `DAMAGE`(20 × Team-Rocket-named Supporters in own discard pile — dynamic) |
| N's Reshiram | `card:303:attack:0` | `DAMAGE`(20 × damage counters on self — dynamic) |
| N's Reshiram | `card:303:attack:1` | `DAMAGE`(170) |
| Riolu (alt) | `card:333:attack:0` | `DAMAGE`(10), `COIN_FLIP_DAMAGE`(+20 if heads) |
| Raging Bolt ex | `card:63:attack:0` | `DISCARD_SELF`(all, hand), `DRAW`(6) |
| Raging Bolt ex | `card:63:attack:1` | `DAMAGE`(70 × Basic Energy discarded — dynamic, uncapped), `DISCARD_SELF`(any amount, Basic Energy, from own Pokémon) |
| N's Zekrom | `card:906:attack:0` | `DAMAGE`(70), `IGNORES_ACTIVE_EFFECTS` |
| N's Zekrom | `card:906:attack:1` | `DAMAGE`(250), `COOLDOWN`(all own attacks, next turn) |
| Hydrapple ex | `card:150:attack:0` | `DAMAGE`(30 base, +30 per `{G}` Energy attached across all own Pokémon — dynamic) |
| Hydrapple ex | `card:150:ability:0` | `ENERGY_ACCEL`(1, Basic `{G}`, hand → own Pokémon), `HEAL`(30, conditional), `CONDITIONAL` |
| Bayleef | `card:709:attack:0` | `DAMAGE`(50), `SWITCH_FORCE`(target: opponent's Active → Bench, opponent chooses replacement) |

**Batch 6 of 6 — final batch (remaining 15 by frequency: IDs 710/917/920/108/141/257/258/970/
655/827/828/42/833/834/829 — 28 rows). Phase 1 is now complete: all 115 Pokémon / 201
attack+ability rows tagged.**

| Card | Effect ID | Tags assigned |
|---|---|---|
| Meganium | `card:710:attack:0` | `DAMAGE`(140) |
| Meganium | `card:710:ability:0` | `ENERGY_AMPLIFY`(scope: all own Pokémon; type: Basic `{G}`; provides `{G}{G}`) |
| Chikorita | `card:917:attack:0` | `STAT_DEBUFF`(scope: opponent's Defending Pokémon; −20 dmg pre-W/R; their next turn) |
| Chikorita | `card:917:attack:1` | `DAMAGE`(30) |
| Tapu Bulu | `card:920:attack:0` | `DAMAGE`(220), `RECOIL`(30) |
| Wellspring Mask Ogerpon ex | `card:108:attack:0` | `DAMAGE`(20), `RETREAT_LOCK`(opponent's Defending Pokémon, their next turn) |
| Wellspring Mask Ogerpon ex | `card:108:attack:1` | `DAMAGE`(100), `SNIPE`(120, conditional), `ENERGY_RETURN_TO_DECK`(3, from self — cost), `CONDITIONAL`(qualifier: **voluntary_cost** — gated on the player's own choice to pay the Energy-return cost, not a hidden/observed board fact; contrast the other 17 board-state-gated `CONDITIONAL` rows) |
| Pecharunt ex | `card:141:attack:0` | `DAMAGE`(60 × Prize cards opponent has taken — dynamic) |
| Pecharunt ex | `card:141:ability:0` | `SELF_SWITCH`(qualifier: `self_referential`=**false** — the ability holder is explicitly excluded from the swap; target: chosen own Benched `{D}` Pokémon ↔ Active), `CONDITION`(Poisoned, conditional), `CONDITIONAL` |
| N's Darumaka | `card:257:attack:0` | `DAMAGE`(20) |
| N's Darumaka | `card:257:attack:1` | `DAMAGE`(50) |
| N's Darmanitan | `card:258:attack:0` | `DAMAGE`(30 × Basic Energy cards in opponent's discard pile — dynamic) |
| N's Darmanitan | `card:258:attack:1` | `DAMAGE`(90), `DISCARD_SELF`(all Energy on self), `SNIPE`(90) |
| Fezandipiti | `card:970:attack:0` | `DAMAGE`(30 × Energy attached to self — dynamic) |
| Fezandipiti | `card:970:ability:0` | `DAMAGE_IMMUNE_FROM`(scope: self; qualifier: single-instance, coin-flip heads-gated), `CONDITIONAL` (gated on: `{D}` Energy attached to self) |
| Celebi | `card:655:attack:0` | `SEARCH_HAND`(up to 3, any combination of `{G}`-type Pokémon and Stadium cards) |
| Celebi | `card:655:attack:1` | `DAMAGE`(30) |
| Carvanha | `card:827:attack:0` | `DAMAGE`(30), `RECOIL`(10) |
| Mega Sharpedo ex | `card:828:attack:0` | `DAMAGE`(70), `DRAW`(2) |
| Mega Sharpedo ex | `card:828:attack:1` | `DAMAGE`(120 base, 270 if condition met), `CONDITIONAL` (gated on: self has any damage counters) |
| Applin (alt) | `card:42:attack:0` | `SEARCH_HAND`(1, any Pokémon) |
| Applin (alt) | `card:42:attack:1` | `DAMAGE`(30) |
| Toxel | `card:833:attack:0` | `SEARCH_BENCH`(up to 2, Basic Pokémon) |
| Toxel | `card:833:attack:1` | `DAMAGE`(20) |
| Toxtricity | `card:834:attack:0` | `DAMAGE`(100) |
| Toxtricity | `card:834:ability:0` | `SEARCH_ATTACH`(1, Basic `{D}` Energy → 1 own Benched `{D}` Pokémon), `COUNTER_PLACE`(2, conditional, same target Pokémon), `CONDITIONAL` |
| Seviper | `card:829:attack:0` | `DAMAGE`(120) |
| Seviper | `card:829:ability:0` | `STAT_BUFF`(scope: self; +120 dmg to opponent's Active, pre-W/R), `CONDITIONAL` (gated on: an own `{D}` Mega Evolution Pokémon `ex` in play) |

## Open items surfaced by worked examples (2026-07-16), for Phase 2 to resolve

Three concrete cards, examined in detail after Phase 1 nominally finished, surfaced schema
gaps that a purely per-row pass didn't catch. Recorded here rather than silently patched,
since fixing all three properly means revisiting every prior batch's use of the affected
tags, which is exactly Phase 2's job, not a batch-1-through-6 patch job:

1. ~~Distribution shape is unrepresented.~~ — **resolved in Phase 2c.** Added a
   `distribution: single | shared_cap_any_split` qualifier to `COUNTER_PLACE`,
   `COUNTER_MOVE`, `ENERGY_ACCEL`, and `SEARCH_ATTACH`'s magnitude schema (`SNIPE` gets the
   schema slot too but no currently-tagged row needs it). Found by a systematic two-pass
   search (text pattern + registry structural fields) across all 201 rows rather than
   re-checking only the 2 rows found via worked examples — turned up 6 total, all now
   updated in the assignment tables. See the `distribution` qualifier subsection above the
   assignment tables for the full list and method.
2. ~~`COUNTER_MOVE` conflates two different mechanics.~~ — **resolved in Phase 2c.** Added a
   `conserved: bool` qualifier rather than splitting into two tags (only 2 of 201 rows use
   `COUNTER_MOVE` at all, both now explicitly marked: Munkidori and Wobbuffet are
   `conserved=false` net transfers, Alakazam/Strange Hacking is `conserved=true` same-side
   redistribution).
3. **The census extraction script has a real bug, now fixed in the census text but not
   re-verified for second-order effects.** It didn't handle the `repeat` program-node kind
   at all, which produced a false "0-operation gap" claim for Mega Kangaskhan ex's
   Rapid-Fire Combo (corrected above) and could plausibly have mis-measured other
   structural properties reported in the Phase 0 census (e.g. any row whose true node
   count involves a `repeat` body). A full re-scan for `repeat` nodes across all 201 rows
   found exactly 2 (Mega Kangaskhan ex, Alakazam/Strange Hacking) — both are now accounted
   for individually, so this is not currently believed to affect any other row's count, but
   it was discovered by manual spot-check rather than a systematic pass, which is a
   methodology gap Phase 2's coverage confirmation should close deliberately rather than
   rely on getting lucky a second time.

**Phase 2a addendum — full node-kind audit (2026-07-16).** Ran a systematic census of
every distinct program-node `kind` appearing anywhere across all 201 rows (34 distinct
values, full list on request) rather than relying on spot-checks. Findings:

- `coin_flip`, `choice`, and `choice_and_requirement` all showed up as *new* kind values
  beyond the already-fixed `repeat`. On inspection, `coin_flip` and `choice_and_requirement`
  only ever appear as the `condition.kind` of a `conditional` node — the extraction script
  already walks into `then` regardless of what `condition` contains, so these were never
  actually a blind spot; no fix needed there.
- `choice` is different: it showed up once as a **payload node** (Cynthia's Garchomp ex,
  `card:381:attack:0`, sitting inside `conditional.then` in place of the usual `sequence`).
  The extraction script has no case for a `choice` node's `options` list, so this row's
  automated op-count is wrong (reports 1 op, actually 2 — the nested `draw_until_six`
  operation inside the choice is invisible to it). Checked whether this also corrupted the
  actual *tag assignment* (not just the census count): it didn't — Phase 1's manual pass
  read this row from its English text and ground-truth fields directly, not from the
  automated op list, and already correctly assigned `DRAW`(to hand size 6). Confirmed by
  re-reading the full program: an outer board-state condition (`own_hand_count < 6`)
  gates a player `choice` between drawing up to 6 or declining — the existing `CONDITIONAL`
  flag is an adequate (if compressed) summary of that compound gate per the fixed Phase 1
  policy, and no retag is needed. Net effect: the census's aggregate node-count numbers are
  now known to still be approximate (this makes a second, independent reason not to treat
  them as authoritative, on top of the double-counting issue already noted in Phase 0) — but
  the actual per-row tag assignments, which are what Phase 2/production actually consume,
  are unaffected by either extraction bug found so far.
- The `conditional` nodes across all 201 rows were re-categorized by their true
  `condition.kind` to check whether `CONDITIONAL` was being applied uniformly: 17 are
  genuine board-state facts (`read`, or `compare` against a board-state count/flag — Stadium
  in play, Energy attached, own Pokémon KO'd last turn, etc.), 6 are coin-flip RNG (already
  correctly excluded from the generic flag, tagged via dedicated `COIN_FLIP_*`/qualifier
  conventions instead), and exactly 1 — Wellspring Mask Ogerpon ex, `card:108:attack:1` — is
  a **voluntary player cost-for-bonus** ("you may shuffle 3 Energy into your deck; if you do,
  +120 damage"), which had been tagged with the same bare `CONDITIONAL` flag as the 17 true
  board-state rows despite being a meaningfully different kind of gate: the model doesn't
  need to infer hidden board state to know this bonus is reachable, it only needs to know
  the player can choose to pay the cost. Fixed below with a qualifier rather than a new tag
  family, since one instance doesn't yet justify a fourth top-level gating tag — flagged to
  watch for more cost-for-bonus instances during spec 11b's Trainer/Energy pass, where
  "you may discard/pay X for Y" is a much more common Trainer pattern.
- Also verified Dudunsparce's `Run Away Draw` (`card:66:ability:0`) conditional in full:
  its `compare` condition checks `drawn_count > 0`, i.e. whether the preceding draw actually
  produced any cards — true only if the player's deck was completely empty at that moment.
  This is a near-always-true technicality, not a meaningfully variable board condition like
  the other 16 `read`/`compare` rows. Left tagged `CONDITIONAL` (correct in kind) but noted
  below with a qualifier so it doesn't read as equivalent-strength uncertainty to, say, "is a
  Stadium in play."

## Phase 3 — non-meta sanity spot-check (2026-07-16)

Source: `Decks/Deck-Builder/EN_Card_Data.csv` (2,022 rows total, one row per attack/ability,
same granularity as the registry). Filtered to `Stage (Pokémon)/Type` in Basic/Stage
1/Stage 2 and Card ID outside the 115-card meta vocabulary: **941 non-meta Pokémon**, 1,121
of their rows carry non-trivial effect text. Sampled 12 non-meta rows deliberately chosen to
stress different parts of the vocabulary (a "handful," per this phase's own scope — not a
second exhaustive audit) and ran the current detection rules against their raw English text,
exactly as the production fallback path would for a truly unseen card.

| Card | Text | Result |
|---|---|---|
| Ludicolo (Ability) | "All of your Pokémon in play get +40 HP..." | `HP_BUFF` fired correctly. Definition is written singular ("this Pokémon"); this instance is team-wide — reinforces the Phase 2f finding that `HP_BUFF` (like `DAMAGE_IMMUNE_FROM`, `EFFECT_IMMUNE`, `COUNTER_PLACE`) needs a formal scope qualifier at Phase 4, not a new bug. |
| Krokorok | "Your opponent discards 2 cards from their hand." | `DISCARD_OPP` fired correctly, including the numeric magnitude — confirms the earlier fix (adding an optional digit group after the Team Rocket's Porygon-only "a card" example) generalizes beyond its single source instance. |
| Floragato | "Flip a coin. If heads, this attack does 30 more damage, and heal 30 damage from this Pokémon." | `HEAL` + `COIN_FLIP_DAMAGE` both fired correctly on a combination neither was drafted against together. |
| Registeel ex | "Attach up to 2 Basic {M} Energy cards from your discard pile to this Pokémon." | `ENERGY_ACCEL` fired correctly. |
| Bronzong (Ability) | "Draw 3 cards." | `DRAW` fired correctly. |
| Slaking ex (Ability) | "If your opponent has no Pokémon {ex} or Pokémon {V} in play, this Pokémon can't attack." | Correctly fired **nothing** — same shape as Team Rocket's Mewtwo ex's deliberately-untagged attack-legality gate (working decision #2). Good sign: the principle generalizes to a card it was never written against, not just re-applied to the one card that prompted it. |
| Reuniclus | "For each of your Benched Pokémon, search your deck for a card that evolves from **that** Pokémon..." | Missed — `EVOLVE_SEARCH`'s pattern required "**this** Pokémon" literally. Same underlying mechanism as Dwebble's card (search + evolve directly), just scaled per-Bench-slot with a loop-variable reference instead of a self-reference. Cheap, low-risk fix applied above; verified it still matches Dwebble and now also matches Reuniclus. |
| Serperior ex | (untranslated Japanese source text) | Correctly fired nothing — not a vocabulary gap, a source-data quality issue: `EN_Card_Data.csv` has at least one row where the English translation wasn't populated. No detection rule can be expected to handle non-English text. Logged as a distinct gap *category* (data quality, not tag coverage) since a real implementation will hit this on other rows too and should have an explicit fallback (e.g. flag for human review) rather than silently emitting an all-zero vector and looking identical to "this card genuinely has no notable effect." |
| Tapu Koko | "If you have more Prize cards remaining than your opponent, this attack does 90 more damage." | Fired nothing in this test harness, but that's a test-harness gap, not a real one: production's two-path runtime still assigns the base `DAMAGE` tag structurally (a printed damage value is present) even when no qualifying regex matches — this spot-check only exercised the *qualifying* rules, not the structural `DAMAGE` fallback. The `CONDITIONAL` flag correctly does not fire from text alone, per the Interfaces note that it's set programmatically for known cards and is explicitly out of scope for the unseen-card text path. |
| Cobalion | "Discard a Special Energy from your opponent's Active Pokémon." | Genuine gap, logged, not fixed. Neither `DISCARD_SELF` (self-only) nor `DISCARD_OPP` (opponent's *hand* only) covers discarding from the **opponent's board** (their attached Energy). No row among the 115 meta Pokémon exercises this direction. |
| Frosmoth | "This attack does 20 damage to **each** of your opponent's Pokémon." | Genuine gap, logged, not fixed. A spread/AOE pattern (all of the opponent's Pokémon at once) distinct from `SNIPE` (one chosen target). Absent from the 115-card meta sample entirely — no top-ladder card in the audited window uses this shape. |
| Forretress | "You may move any amount of {M} Energy from your Pokémon to your other Pokémon in any way you like." | Genuine gap, logged, not fixed. Energy redistribution *within the user's own side* — structurally analogous to `COUNTER_MOVE`'s conserved-redistribution case, but for attached Energy instead of damage counters. Not covered by `ENERGY_ACCEL` (that's attachment from an off-board source, not board-internal movement). |

**Outcome:** 6 of 12 fired the correct existing tag with no changes needed, 1 correctly
fired nothing per an existing deliberate design decision, 1 correctly fired nothing due to a
source-data defect outside this spec's control, 1 was a cheap same-mechanism regex
broadening (applied), and 3 are genuine, real gaps — mechanics that never appeared anywhere
in the 115-card audited sample, so the current vocabulary was never asked to cover them.
Per this phase's own stated bar ("loss here is explicitly more acceptable... a sanity check,
not a second exhaustive audit"), these three are recorded as **explicit known gaps**, not
retrofitted into new tags now:

1. **Opponent-board discard** (Cobalion) — discarding from the opponent's attached
   cards/Energy, as opposed to their hand (`DISCARD_OPP`) or the user's own side
   (`DISCARD_SELF`).
2. **Spread/AOE damage** (Frosmoth) — damage to *all* of the opponent's Pokémon in one
   attack, as opposed to `SNIPE`'s single chosen target.
3. **Own-side Energy redistribution** (Forretress) — moving attached Energy between the
   user's own Pokémon, the Energy analogue of `COUNTER_MOVE`'s conserved damage-counter
   redistribution.

None of these were reachable from the 115-card meta sample by construction, so Phase 1/2's
"effectively zero all-zero assignments" bar — which is scoped to the audited 115 — is
unaffected. They're recorded here so Phase 4 (or spec 11b, if any of these shapes recur on
the Trainer/Energy side) can decide with full information whether they're worth adding.

## Phase 4 — locked field list, widths, and normalization (2026-07-16, corrected during code
transcription)

**Content tags: 49** (the full catalog above, minus `CONDITIONAL`, which is a per-row
companion flag rather than a content tag — see below). **Corrected from an earlier "48"**
that never accounted for `COPY_ATTACK` being added to the catalog after this section was
first written — caught by directly counting the catalog table's rows during code
transcription rather than trusting this section's own prior count, per this spec's own
"re-derive fresh from source" discipline.

Each content tag gets **one scalar**: `0.0` when absent, otherwise the (normalized)
magnitude — or `1.0` for the roughly one-third of the 49 with no natural numeric parameter
at all (e.g. `IGNORES_WEAKNESS`, `SELF_MILL`, `SELF_KO`, `DOUBLE_ATTACK`, pure booleans).

**Design history:** this section originally locked a *pair* per tag — a presence bit plus an
index-aligned magnitude scalar — reasoning that boolean-only tags needed *some* signal since
their magnitude is always a meaningless `0.0`. That's true, but checking the actual 201-row
manual assignment table during code transcription found no row anywhere assigns a
magnitude-bearing tag with magnitude exactly `0` while marking it present (e.g. Dunsparce's
0-damage repositioning attack simply isn't tagged `DAMAGE` at all) — so presence and
"magnitude nonzero" carry identical information for every magnitude-bearing tag in this
dataset, and the pair collapses losslessly into the single scalar above. Confirmed with the
user and applied; the two-slot design is retired.

Normalization, by magnitude family (a per-tag numeric constant, not a design axis — exact
caps are implementation-time calibration, not a planning decision, consistent with spec 11's
"tunable hyperparameter" treatment of the card-ID embedding width):
  - Damage-like (`DAMAGE`, `RECOIL`, `SNIPE`, `COIN_FLIP_DAMAGE`, `STAT_BUFF`,
    `STAT_DEBUFF`, `RNG_SCALING_DAMAGE`'s `expected_value`): divide by a shared damage cap
    (350 — the highest `credible_max` in the audited sample, Mega Kangaskhan ex) and clip.
  - Count-like (`DRAW`, `COUNTER_PLACE`, `COUNTER_MOVE`, `SEARCH_ATTACH`, `SEARCH_HAND`,
    `REVEAL_DIG`, `ENERGY_ACCEL`, `DISCARD_SELF`, `DISCARD_OPP`, `REVIVE_FROM_DISCARD`,
    `MILL`, `EXTRA_PRIZE`, `SEARCH_BENCH`, `ENERGY_RETURN_TO_DECK`): divide by a shared
    count cap (6) and clip; uncapped "any number/any amount" cases (Honchkrow, Raging Bolt,
    Alakazam/Strange Hacking) clip to 1.0 as an explicit "at or above cap" sentinel, since
    true uncapped scaling can't be normalized without live board state.
  - HP-like (`HP_BUFF`): divide by an HP-delta cap (150).
  - Multiplier-like (`ENERGY_AMPLIFY`): small integer (currently always 2 in the audited
    sample), divide by a cap of 3.

**`CONDITIONAL`: 1 presence bit + 2 qualifier bits** (`voluntary_cost`, `near_always_true`)
— both `0` is the default/board-state case, the common one (17 of 19 non-RNG conditional
rows). This one keeps its explicit presence bit even after the collapse above — its
qualifier defaults are themselves the common *present* case, so they'd collide with "absent"
if presence weren't tracked separately. Kept apart from the 49 content-tag scalars since it's
a property of the *gate*, applying to the row's other tag(s) collectively, not a content tag
itself.

**Shared cross-tag qualifier fields** (meaningful only when the associated tag is present,
`0`/default otherwise):

- `distribution` (1 bit) — `shared_cap_any_split` vs. `single` (default). Applies to
  `SNIPE`, `COUNTER_PLACE`, `COUNTER_MOVE`, `ENERGY_ACCEL`, `SEARCH_ATTACH`.
- `conserved` (1 bit) — meaningful only with `COUNTER_MOVE`.
- `self_referential` (1 bit) — meaningful only with `SELF_SWITCH`.
- `scope` (one-hot: `self` / `own_bench` / `own_team` / `opponent_named_subset` / `other` —
  **widened to a 6th value, `both_sides`, during spec 11b's Phase 4**, since 11b's Stadium
  cards made "both yours and your opponent's" a common category — 11 of 17 audited
  Stadiums use it — that never came up anywhere in the 115-card Pokémon sample. `scope` is
  a shared convention across both specs, not owned separately by each, so this file's width
  accounting (below) should be read as using the 6-value version even though no Pokémon row
  currently needs the 6th value) — applies to `DAMAGE_IMMUNE_FROM`, `EFFECT_IMMUNE`,
  `COUNTER_PLACE`, `HP_BUFF`, `STAT_BUFF`, `STAT_DEBUFF`, `RETREAT_COST_MOD`,
  `WEAKNESS_OVERRIDE`, `ENERGY_AMPLIFY`, `ATTACK_INHERIT`. **Explicit residual
  approximation, not silently accepted:** several
  scoped tags carry a finer attacker-restriction than this 5-way split captures — Crustle's
  `DAMAGE_IMMUNE_FROM` is scoped `self` but *also* restricted to only-vs-`{ex}` attackers;
  Cornerstone Mask Ogerpon ex's is `self` but only-vs-Ability-holders. A shared one-hot this
  narrow can't carry that second axis without its own field, and adding one now (for what
  is currently 2 of 201 rows) would widen every scoped tag's encoding to capture a detail
  only 1% of rows need. Left as a known, explicit gap — the attacker-restriction detail
  exists in the manual assignment table's prose (so it's not lost from the spec/audit
  record), just not from the currently locked numeric field list.

**Total width: 49 + 3 + 1 + 1 + 1 + 6 = 61 dimensions** (ability rows). Superseded numbers,
kept here for history: an initial 107 (48 tags × 2), corrected to 108 once `scope` grew to 6
values during spec 11b's Phase 4 (itself never updated for `COPY_ATTACK`'s addition, which
should have made it 110), then collapsed to the 61 above once the presence+magnitude pair
was retired and the 48→49 count was fixed, both during code transcription. Roughly 0.8× the
old 75-dimensional opponent attribute vector — narrower than the old scheme despite far
richer content, since the collapse removed more redundancy than the widened vocabulary
added.

## Energy cost (added 2026-07-16, during spec 11's base-field pass; widened same day)

**9 additional dimensions, attack rows only** — `energy_cost`: one dimension per type
(Grass, Fire, Water, Lightning, Psychic, Fighting, Darkness, Metal, Colorless — no Fairy,
no Dragon, same 9-type list as the weakness/resistance fields in spec 11's base schema),
each holding the count of that type's pips required to use this attack, `/ 5` clipped.
**Not a strict mutually-exclusive one-hot** — real attack costs routinely require more than
one type simultaneously (e.g. "2 Fire + 1 Colorless" sets both the Fire and Colorless
dimensions), so this is a per-type count vector, same pattern as `attached_energy_counts`.
Ability rows always encode all 9 dims as `0.0` (abilities have no Energy cost under real
rules — there is nothing to distinguish).

**The `Colorless` dimension here means generic pips, not the Colorless card type.** This is
a different semantic than `attached_energy_counts`' `Colorless` bucket (which counts
Colorless-*typed* Energy cards specifically): a cost's Colorless pips can be paid by *any*
attached Energy type, not only Colorless cards. Worth flagging explicitly so the two fields'
same-named dimension isn't read as meaning the same thing.

Unlike every tag field above, this is **not text-detected** — it's sourced directly from
card data (`program`/cost fields in the spec-12 registry, mirroring the old encoding's
`card_data.py`-sourced `energy_cost` in its now-superseded attack block, see
`02-observation-encoding.md`/`03-attack-ability-tagging.md`), the same way `DAMAGE`'s
magnitude is sourced from card data rather than regex-extracted. It sits alongside the 61
tag dimensions as a schema field, bringing the **per-attack-row total to 70** (61 + 9);
ability rows stay at 61 (their 9 `energy_cost` slots are always `0.0`, not meaningful
fields).

## Known gaps — final sign-off list (consolidated from Phases 2 and 3)

1. `card:431:ability:0` (Team Rocket's Mewtwo ex) — pure attack-legality gate, no separate
   effect content; deliberately untagged per working decision #2. Validated as a correctly
   generalizing principle in Phase 3 (Slaking ex, a non-meta card with the identical shape,
   correctly produced no tags without any code change).
2. Opponent-board discard (non-meta, Cobalion) — discarding from the opponent's attached
   cards, not covered by `DISCARD_SELF` or `DISCARD_OPP`. Not reachable from the 115-card
   meta sample; not retrofitted.
3. Spread/AOE damage to all of the opponent's Pokémon (non-meta, Frosmoth) — not covered by
   `SNIPE`. Not reachable from the 115-card meta sample; not retrofitted.
4. Own-side Energy redistribution between the user's own Pokémon (non-meta, Forretress) —
   the Energy analogue of `COUNTER_MOVE`'s conserved redistribution; no equivalent tag
   exists. Not reachable from the 115-card meta sample; not retrofitted.
5. Fine-grained attacker-restriction qualifiers (only-vs-`{ex}`, only-vs-Ability-holder) on
   scoped defensive tags — present in the audit prose, not in the locked numeric `scope`
   field (see Phase 4 above). Affects 2 of 201 rows.
6. Untranslated/non-English source text in `EN_Card_Data.csv` (non-meta, Serperior ex) — a
   data-quality issue in that corpus, not a vocabulary gap; flagged so a future
   implementation adds an explicit fallback (e.g. route to human review) rather than
   treating a silent all-zero result as equivalent to "no notable effect."
7. `RNG_SCALING_DAMAGE`'s truncated-tail approximation (`credible_max`=350, omitting the
   ≥4-heads case, ~6.25% probability) — inherited unchanged from spec 12's own approved
   exception `HR-B05-002`, not introduced by this spec, but flows directly into this tag's
   magnitude fidelity and is recorded here for completeness of the sign-off list.

None of these are silent — each has an owner (a spec, a phase, or an explicit "not
retrofitted" decision) and a reason. Items 2-4 are the ones most likely to matter if spec
11b's Trainer/Energy pass surfaces the same shapes on that side of the vocabulary (e.g. a
Trainer card that redistributes Energy would make gap 4 worth revisiting together).

## Data

Input corpus: `Imitation-Learning/meta-card-registry/registry.json`, filtered to
`identity.class == "pokemon"` (115 cards, 201 attack/ability/effect rows). Use the
registry's exact `program`/`damage_profile` fields as the ground truth for what each row
actually does — not the card's English text alone, and not the old encoder's existing
tags, both of which the registry audit already found to disagree with real behavior in
places.

For non-meta sanity-checking (Phase 3), any Pokémon card in `Decks/Deck-Builder/
EN_Card_Data.csv` outside the 115-ID vocabulary is fair game.

## Interfaces / seams

Feeds directly into spec 11's static template as the "attribute/effect tag block," with a
two-path runtime split:

- **Known 115 Pokémon:** looked up directly from the Phase 1/2 manual assignment table by
  card ID. No detection rule runs against these at inference time.
- **Everything else:** run through the Phase 2 detection rules against the card's English
  text.

Both paths emit the same tag vocabulary and shape — one schema, two ways of populating it.
Two consumers read the resulting tag block: the board word (static template + live state,
spec 11) and, if spec 13 adopts per-card zone words, a zone word (static template alone).
This spec does not decide field widths for either consumer — it produces the tag
vocabulary, the detection rules, and the manual assignment table only.

## Out of scope

- Trainer and Energy tag vocabularies — spec 11b.
- Live-state fields (HP fraction, status, energy count, threat ratios) — already defined
  in spec 11, not re-derived here.
- Zone-word or global-state design — spec 13.
- The compositional-AST/shared-node-function direction explored earlier and shelved.
- Implementing the parser itself (turning the detection rules into running code) and
  wiring the lookup table into `features.py`/its successor. This spec's deliverable is the
  vocabulary, the ready-to-implement detection rules, and the manual assignment table —
  not the code that executes them.

## Open questions

- The exact conditional-handling policy (Phase 1) is not decided yet — it's explicitly
  part of what this review is supposed to settle, not a precondition for starting it.
- Final field count/width is an output of Phase 4, not an input to this plan.
- How strictly a detection rule must reproduce the manual assignment on known-card text to
  be considered validated (Phase 2) is a judgment call to make during that phase, not
  fixed here.
