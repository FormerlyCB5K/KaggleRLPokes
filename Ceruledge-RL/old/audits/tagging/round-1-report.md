# Round 1 Audit — 100 cards (seed 101, Pokémon-only)

Edit applied before this batch: the 7 round-0 fixes (multi-coin/third-person flips,
numberless top-card, "a random", attach-up-to-N accel, discard-up-to-N, bench spread
snipe, "N more damage counters"). Full-pool diff: 74 cards changed, all verified
correct; the diff also exposed one PRE-EXISTING false positive (Espeon ex 246:
"shuffling … **into** your opponent's deck" trips `deckout`), queued below.

**Legend:** ✅ correct · ❌ FN/FP · 🔶 override candidate (worklist) · ❓ human review.

## Queued regex fixes for round 2

1. **deckout FP** (found via diff, not batch): bare `opponent's deck` matches devolve/shuffle-INTO effects → require `(?:of|from) your opponent's deck` (mill texts read "top N cards **of** your opponent's deck"; Espeon reads "**into**"). Keep the `Each player draws` branch.
2. **discard-all typed**: "Discard all **{M}** Energy" misses `discard all Energy` → `discard all (?:\{\w\} )?Energy` (118 Heatran, 587 Galvantula).
3. **counter_snipe verb**: texts use "**Place** N damage counters" as well as "Put" → `(?:put|place) (?:up to )?{N} damage counters?` (876 Mismagius, 1058 Haunter).
4. **attack-level energy accel**: (a) direct "Attach a Basic Energy card from your hand" → `attach (?:a|an|\d+) (?:basic )?(?:\{\w\} )?Energy` (124 Chansey); (b) search-and-attach "Search your deck for (up to) N … Energy card(s) and attach" → `for (?:up to )?{N} [^.]{0,30}?Energy cards? and attach` (239 Flareon ex, 653 Exeggcute).
5. **ability attach anchor**: "attach up to 2 **Spiky** Energy" fails the `Basic` anchor → drop it: `during your turn, you may attach (?:up to )?{N}` (287 Lycanroc).
6. **top-deck of each player**: "Discard the top card of **each player's** deck" → `top (?:{N} )?cards? of (?:your|each player's) deck` (30 Magcargo ex).

## Per-card review

- **27 Iron Leaves** ✅ — "If any of your Pokémon were Knocked Out … during your opponent's last turn, this attack does 60 more damage." | ATK2 `{revenge: 1}` | Correct.
- **30 Magcargo ex** ❌ **FN** — Ground Burn: "Discard the top card of each player's deck. This attack does 140 more damage for each Energy card discarded in this way." | none | Random-outcome damage missed `probabilistic` — top-deck regex demands "of your deck" (fix #6).
- **43 Eevee** ✅ — Ascension (deck search evolve), Quick Attack coin flip | ATK2 `{probabilistic: 1}` | Correct; attack-search has no schema field.
- **58 Great Tusk** ✅ — "Discard the top card of your opponent's deck…" | ATK1 `{deckout: 1}` | Correct.
- **74 Rabsca** ✅ (override) — Spherical Shield | ABL `{barrier: 1}` | Correct via seed.
- **90 Thwackey** ✅ — "…you may search your deck for a card and put it into your hand." | ABL `{search: 1}` | Correct.
- **93 Dipplin** ✅ — attack-twice-if-stadium ability | none | No schema category; acceptable zeros.
- **99 Hearthflame Mask Ogerpon ex** ✅🔶 — Wrathful Hearth: "20 damage for each damage counter on this Pokémon" → `{outrage: 1}`; Dynamic Blaze: "If your opponent's Active is an Evolution Pokémon, +140, and discard all Energy" → `{discard_energy: 3}` | Both tags right; conditional +140 (max 280) is override-only → worklist.
- **105 Finizen** ✅ — "During your next turn, this Pokémon can't use attacks." | `{cooldown: 1}` | Correct.
- **118 Heatran** ❌ **FN** — Steel Burst: "Discard all {M} Energy from this Pokémon. This attack does 50 damage for each card you discarded…" | none | `discard_energy` missed the typed "all **{M}** Energy" (fix #2).
- **124 Chansey** ❌ **FN** — Lucky Attachment: "Attach a Basic Energy card from your hand to 1 of your Pokémon." | ATK2 cooldown ✅ | Attack-level accel missed: `energy_accel` trigger only knows "attach up to {N}" (fix #4a).
- **142 Genesect** ❓ — ABL: "If this Pokémon has a Pokémon Tool attached, your opponent can't play any {ACE SPEC} cards from their hand." | none | ACE-SPEC lock ≈ partial item lock, but the ability block has no item_lock field — human review (schema gap).
- **188 Vibrava** ✅ — Screech vulnerability debuff | none | No category; correct zeros.
- **193 Alolan Exeggutor ex** ✅🔶 — Tropical Frenzy: "You may attach any number of Basic Energy cards from your hand…" → unparseable N → worklist (`energy_accel` override); Swinging Sphene coin-flip KO → `{probabilistic: 1}` ✅.
- **201 Wo-Chien** ✅🔶 — "If there are 3 or fewer cards in your deck, this attack also does 120 damage to 2 of your opponent's Benched…" → `{snipe: 120}`; "Discard the top 3 cards of your deck" → `{probabilistic: 1}` | Tags right; the deck-count gate is override-only `conditional` → worklist.
- **208 Shellos** ✅ — vanilla | none | Correct.
- **224 Annihilape** ✅ — Destined Fight: "Both Active Pokémon are Knocked Out." | none | Mutual-KO has no category; noted in worklist as a possible conditional.
- **236 Leafeon ex** ✅ — Moss Agate bench heal | none | Attack heals aren't in the schema (heal is ability-only).
- **237 Cottonee** ✅ — "Flip 3 coins…" | `{probabilistic: 1}` | Round-1 fix confirmed working.
- **239 Flareon ex** ❌ **FN** — Burning Charge: "Search your deck for up to 2 Basic Energy cards and attach them to 1 of your Pokémon." | ATK2 cooldown ✅ | Search-and-attach accel missed (fix #4b).
- **253 Metapod** ✅ — Harden | none | No category.
- **257 N's Darumaka** ✅ — vanilla | none | Correct.
- **258 N's Darmanitan** ✅ — Flamebody Cannon: "Discard all Energy from this Pokémon, and this attack also does 90 damage to 1 of your opponent's Benched…" | `{snipe: 90, discard_energy: 3}` | Both correct (untyped "all Energy" works).
- **260 Lotad** ✅ — vanilla | none | Correct.
- **262 Ludicolo** ✅ — Vibrant Dance +40 HP ability | none | HP buffs bake automatically via live maxHp; correct zeros.
- **268 Iono's Tadbulb** ✅ — vanilla | none | Correct.
- **275 Metang** ✅ — vanilla | none | Correct.
- **287 Lycanroc** ❌ **FN** — ABL: "…during your turn, you may attach up to 2 Spiky Energy cards from your discard pile to this Pokémon." | none | The `Basic` anchor blocks Special-Energy accel (fix #5).
- **305 Dunsparce** ✅ — Trading Places self-switch attack | none | Attack-switch not in schema.
- **312 Sandy Shocks** ✅🔶 — "If you have 3 or more Energy in play, +70…" | none | Conditional (override-only) → worklist group.
- **317 Eevee** ✅ — evolve-fast ability | none | No category.
- **330 Sylveon** ✅ (override) — Safeguard | ABL `{immunity: 1}` | Correct via seed.
- **343 Shaymin** ✅ (override) — Flower Curtain | ABL `{barrier: 1}` | Correct via seed.
- **360 Misty's Staryu** ✅ — coin-flip paralysis | `{probabilistic: 1}` | Correct.
- **382 Mudbray** ✅ — "Flip a coin until you get tails…" | `{probabilistic: 1}` | Correct.
- **385 Arven's Toedscruel** ❓ — Pull: "Switch in 1 of your opponent's Benched Pokémon to the Active Spot." | none | Boss's-Orders-as-attack; the ATTACK block has no gust field — human review (schema gap).
- **403 Dolliv** ✅ — Nutrients heal attack | none | Attack heals not in schema.
- **418 Snover** ✅ — vanilla | none | Correct.
- **419 Abomasnow** ✅🔶 — "If this Pokémon has 2 or more {G} Energy attached, +120" | none | Conditional → worklist group.
- **422 Barraskewda** ✅ — Dive coin flip | `{probabilistic: 1}` | Correct.
- **426 Team Rocket's Mareep** ✅ — Procurement search attack | none | Not in schema.
- **431 Team Rocket's Mewtwo ex** ✅ — Erasure Ball: "You may discard up to 2 Energy from your Benched Pokémon…" | `{discard_energy: 2}` | Round-1 fix working; the can't-attack-unless-4-TR ability has no category.
- **443 Nosepass** ✅ — vanilla | none | Correct.
- **463 Team Rocket's Murkrow** ❓ — Torment: "Choose 1 of your opponent's Active Pokémon's attacks. During your opponent's next turn, that Pokémon can't use that attack." | none | Single-attack lock — should partial locks set `cubchoo`? Human review.
- **474 Team Rocket's Porygon2** ✅ — scaling attack | none | Correct.
- **475 Team Rocket's Porygon-Z** ✅ — "…you may draw a card" (cost: discard 2) | ABL `{draw: 1}` | Correct.
- **490 Victini** ✅🔶 — "If you have 4 or fewer Benched Pokémon, this attack does nothing." | none | Conditional → worklist group.
- **494 Lampent** ✅ (override) — deckout line seed + `{discard_energy: 1}` | Correct.
- **495 Chandelure** ✅ (override) — deckout line seed | Correct.
- **503 Tirtouga** ✅ — scaling attack | none | Correct.
- **505 Alomomola** ✅ — bench-recovery ability | none | No category.
- **512 Eelektrik** ✅ — "…you may attach a Basic {L} Energy card from your discard pile to 1 of your Benched Pokémon." | ABL `{energy_bench: 1}` | Correct.
- **519 Duosion** ✅ — evolve-search attack | none | Not in schema.
- **540 Krookodile** ✅🔶 — hand discard + "if 3 or fewer cards in their hand, +120" | none | Conditional → worklist group.
- **545 Bisharp** ✅🔶 — "if … already has any damage counters, +60" | none | Conditional → worklist group.
- **552 Tranquill** ✅ — coin flip | `{probabilistic: 1}` | Correct.
- **556 Cinccino** ✅ — bench-scaling damage | none | Correct.
- **568 Pignite** ✅ — vanilla | none | Correct.
- **582 Vanilluxe** ✅ — "Flip 2 coins…" | `{probabilistic: 1}` | Round-1 fix confirmed.
- **587 Galvantula** ❌ **FN** — Discharge: "Discard all {L} Energy from this Pokémon…" | none | Same typed-all miss as Heatran (fix #2).
- **621 Klink** ✅ — damage reduction | none | No category.
- **624 Durant** ✅🔶 — "If Durant is on your Bench, +20" | none | Conditional → worklist group.
- **626 Patrat** ✅ (override) — BARRIER seed applies (ability block override; card prints no ability text so the dump omits the ABL line — display quirk only).
- **653 Exeggcute** ❌ **FN** — Jam-Packed: "Search your deck for a Basic {G} Energy card and attach it to this Pokémon." | none | Search-and-attach accel missed (fix #4b).
- **658 Shiftry** ✅ — coin-flip shuffle-away | ATK1 `{probabilistic: 1}` | Correct.
- **672 Tyrogue** ✅ — "Flip a coin until you get tails…" | `{probabilistic: 1}` | Correct.
- **694 Steelix** ✅🔶 — "If you have exactly 6 Prize cards remaining, +200" | none | Conditional → worklist group (big swing: 240 max).
- **719 Chi-Yu** ✅ — stadium discard/lock | none | No category.
- **733 Magneton** ✅ — coin-flip paralysis | `{probabilistic: 1}` | Correct.
- **752 Greavard** ✅ — vanilla + self-damage | none | Correct.
- **753 Houndstone** ✅ — "Flip a coin until you get tails. For each heads, choose a random card…" | `{probabilistic: 1}` | Correct.
- **765 Meloetta** ✅ — bench heal attack | none | Not in schema.
- **766 Mega Diancie ex** ✅ — "Discard up to 2 Energy cards from this Pokémon…" | `{discard_energy: 2}` | Round-1 fix confirmed; damage-reduction ability has no category.
- **770 Gastly** ✅ — vanilla | none | Correct.
- **785 Genesect** ✅ — "20 damage to 1 of your opponent's Pokémon for each {G} Energy attached…" | `{snipe: 20}` | Correct (base captured; scaling value is inherent limitation).
- **790 Mega Charizard X ex** 🔶 — Inferno X: "Discard any amount of {R} Energy from among your Pokémon, and this attack does 90 damage for each…" | none | "Any amount" is unparseable → worklist (`discard_energy` + `max_damage` override).
- **798 Seel** ✅ — self-heal attack | none | Not in schema.
- **810 Pawmo** ✅ — vanilla | none | Correct.
- **837 Bronzong** ✅ — "Draw 3 cards." | `{draws_cards: 3}` | Correct; Tool Drop scaling untagged per spec.
- **854 Dustox** ✅ — ability coin-flip energy bounce | none | Ability block has no probabilistic/denial fields; correct zeros per schema.
- **876 Mismagius** ❌ **FN** — "If your opponent's Active … is affected by a Special Condition, **place** 6 damage counters on 1 of your opponent's Benched Pokémon." | none | `counter_snipe` only knows the verb "put" (fix #3); the condition gate additionally → worklist group.
- **884 Medicham** ✅🔶 — "If you don't have exactly 7 cards in your hand, this attack does nothing." | none | Conditional → worklist group.
- **897 Pangoro** ✅🔶 — "If any of your Benched Pancham have damage counters, +120" | none | Conditional → worklist group.
- **901 Kingambit** ✅ — prize-scaling damage-boost ability | none | No category.
- **906 N's Zekrom** ✅ — "During your next turn, this Pokémon can't use attacks." | `{cooldown: 1}` | Correct.
- **910 Erika's Gloom** ✅ — poison infliction | none | Status has no tag; correct.
- **937 Totodile** ✅ — self-damage | none | Correct.
- **943 Walrein** 🔶 — Frigid Fangs: "During your opponent's next turn, Pokémon that have 2 or less Energy attached can't use attacks." | none | Conditional attack-lock, unregexable without FPs → worklist (`cubchoo: 1` override).
- **948 Pikachu** ✅ — vanilla | none | Correct.
- **968 Dachsbun ex** 🔶 — ABL: "Heal all damage from each of your Evolution Pokémon…" | `{heal: 10}` (once-rule fallback) | "All damage" isn't parseable; 10 badly understates → worklist (`heal` ≈ 100 override).
- **980 Venipede** ✅ — poison | none | Correct.
- **993 Orthworm ex** ✅❓ — retaliation-counters ability; Rock Tomb "can't retreat" | none | Retaliation has no category; "can't retreat" recurs (also Ariados, round-0 Wugtrio) with no tag — human review (schema question).
- **1004 Larry's Staravia** ✅ — vanilla | none | Correct.
- **1012 Ariados** ✅❓ — poison + "can't retreat" | none | Same retreat-lock schema question.
- **1032 Amaura** ✅ — sleep | none | Correct.
- **1042 Espurr** ✅ — self-heal | none | Correct.
- **1049 Hippowdon** ✅🔶 — "If you played Tarragon … discard the top 3 cards of your opponent's deck." | `{deckout: 1}` | Tag correct; conditional gate → worklist group.
- **1056 Mega Zygarde ex** 🔶 — Nullifying Zero: "For each of your opponent's Pokémon, flip a coin. If heads, this attack does 150 damage to that Pokémon." | `{probabilistic: 1}` | Flip caught; the all-board snipe ("damage to **that** Pokémon") is too generic to regex → worklist (`snipe: 150` override).
- **1058 Haunter** ❌ **FN** — Haunt: "Place 3 damage counters on your opponent's Active Pokémon." | none | Same "place" verb miss (fix #3).
- **1069 Rattata** ✅ — self-damage | none | Correct.

## Tallies

- ✅ correct: 88 · ❌ FN: 9 cards (30, 118, 124, 239, 287, 587, 653, 876, 1058) · ❌ FP: 0 in batch (1 pre-existing found via diff: 246)
- 🔶 worklist: 99, 193, 201, 790, 943, 968, 1056 + conditional group (312, 419, 490, 540, 545, 624, 694, 876, 884, 897, 1049, 224)
- ❓ human review: 142 (ACE-SPEC lock), 385 (attack-gust), 463 (single-attack lock), retreat-lock family (993, 1012, round-0 52)
