# Tag Audit — Random Sample of 100 Cards

Seeded sample (`random.seed(42)`, 100 of 1267 cards with attacks/abilities), tags produced
by the current three-tier pipeline (`attack_overrides.py` → `effect_features.py` keyword
extraction → zeros). Raw (un-normalized) tag values shown.

**Legend:**
✅ = tagging correct · ❌ **FN** = false negative (tag missing) · ❌ **FP** = false positive
(tag wrongly set) · 🔶 = correct per spec (override-only tag / no schema category), but
flagged as an **override candidate** · ⬜ = Trainer/Energy card — never encoded (opponent
zones aren't encoded; only in-play Pokémon get tag blocks), tags are inert either way.

## Summary

**0 false positives. 12 cards with false negatives**, all from 5 systemic regex gaps:

| # | Gap | Cards hit | Suggested fix (in `effect_features.py`) |
|---|-----|-----------|------------------------------------------|
| 1 | `probabilistic` misses multi-coin ("Flip 2/3 coins") and third-person ("Your opponent flips a coin") | 136, 470, 822, 1035, 430 | Replace the `_RX_FLIP_ONE` check with `re.compile(r"flips? (?:a\|\d+) coins?", re.I)` — same coverage as `_RX_FLIP_N` + `_RX_FLIP_ONE` combined, plus the `flips` conjugation |
| 2 | `probabilistic` misses "top **card** of your deck" (no number) | 286 | `re.compile(r"top (?:\d+ )?cards? of your deck", re.I)` (Litwick 493 needed an override for exactly this text) |
| 3 | `probabilistic` misses no-coin random effects ("a random card") | 433, 470 | Add `re.compile(r"\ba random\b", re.I)` — in the full pool this phrase only appears in genuinely random effects |
| 4 | ability `energy_active/bench` misses "attach **up to 2** Basic" (regex demands "attach a Basic") | 190 | `_RX_ABL_ATTACH = re.compile(r"during your turn, you may attach (?:up to )?" + _NUM + r"? ?Basic", re.I)` — i.e. make the article/count flexible: `r"during your turn, you may attach (?:a\|an\|up to \d+\|\d+) Basic"` |
| 5 | `discard_energy` misses "Discard **up to** 3 Energy" | 52, 94 | `_RX_TAG_DISC_N = re.compile(r"discard (?:up to )?" + _NUM + r" (?:basic )?(?:\{\w\} )?Energy", re.I)` |
| 6 | `snipe` misses both-sides bench spread ("damage to each Benched Pokémon (both yours and your opponent's)") | 779 | Add alternative `re.compile(r"(\d+) damage to each Benched Pok", re.I)` — self-only spreads read "to each **of your** Benched", so the bare "each Benched" form is safe |
| 7 | ability `damage` misses "put 3 **more** damage counters" | 256 (minor) | `_RX_ABL_DMGCTR = re.compile(r"put (?:up to )?" + _NUM + r" (?:more )?damage counters?", re.I)` |

**Override candidates spotted** (correct per spec today — these tags are override-only or
the value isn't parseable): Milotic ex 207 (IMMUNITY vs Tera), Pikachu ex 210 (Sturdy →
IMMUNITY, to match the Crustle 533 seed), Shedinja 748 (no-prize-on-KO → BARRIER),
Iron Crown 192 / TR Nidoqueen 452 (conditional-bonus attacks), Wugtrio 52 / Sinistcha 94 /
N's Zoroark ex 293 / Quaxly 947 (max_damage understated on variable/copy attacks),
Cofagrigus 593 (move-ALL-counters snipe, amount unparseable).

## Per-card review

- **14 Spiky Energy** ⬜ — "If the Pokémon this card is attached to is in the Active Spot and is damaged by an attack from your opponent's Pokémon (even if this Pokémon is Knocked Out), put 2 damage counters on the Attacking Pokémon." | tags: ABL `{damage: 20}` | Special Energy, never encoded; the trigger technically matched (it's retaliation, not proactive counters), harmless.
- **52 Wugtrio ex** ❌ **FN** — ATK1 Tricolor Pump (c1/d60): "Discard up to 3 Energy cards from your hand. This attack does 60 damage to 1 of your opponent's Pokémon for each Energy card you discarded in this way." · ATK2 Numbing Hold (c2/d120): "During your opponent's next turn, the Defending Pokémon can't retreat." | tags: ATK1 `{snipe: 60}` | `snipe` is right, but `discard_energy` missed "Discard **up to** 3" (fix #5); also max_damage=120 understates the real 180 ceiling → `max_damage` override candidate.
- **55 Bronzong** ✅ — Evolution Jammer (c1/d30): "During your opponent's next turn, they can't play any Pokémon from their hand to evolve their Pokémon." | tags: none | Correct: evolution lock has no tag in the schema (only Item lock does), so zeros are the intended behavior.
- **62 Koraidon** ✅ — Primordial Beatdown (c2/d30): "This attack does 30 damage for each of your Ancient Pokémon in play." · Shred (c3/d130): "This attack's damage isn't affected by any effects…" | tags: none | Correct: scaling damage has no tag category; reads as vanilla with printed damage per spec.
- **66 Dudunsparce** ✅ — ABL: "Once during your turn, you may draw 3 cards. If you drew any cards in this way, shuffle this Pokémon and all attached cards into your deck." | tags: ABL `{draw: 3}` | Correct.
- **89 Grookey** ✅ — vanilla attacks, no effect text | tags: none | Correct.
- **94 Sinistcha** ❌ **FN** — Cursed Drop (c1/d0): "Put 4 damage counters on your opponent's Pokémon in any way you like." · Spill the Tea (c1/d70): "Discard up to 3 {G} Energy cards from your Pokémon. This attack does 70 damage for each card you discarded in this way." | tags: ATK1 `{counter_snipe: 40}` | `counter_snipe` correct; ATK2 missed `discard_energy` on "Discard **up to** 3 {G} Energy" (fix #5); real max 210 → `max_damage` override candidate.
- **115 Conkeldurr** ✅🔶 — Tantrum (c1/d80): "This Pokémon is now Confused." · Gutsy Swing (c4/d250): "If this Pokémon is affected by a Special Condition, ignore all Energy in this attack's cost." | tags: none | Correct per spec (`conditional` is override-only); Gutsy Swing is a conditional-cost override candidate.
- **136 Zorua** ❌ **FN** — Double Scratch (c2/d20): "Flip 2 coins. This attack does 20 damage for each heads." | tags: none | `probabilistic` missed because the regex only knows "flip **a** coin" (fix #1).
- **143 Varoom** ✅ — Rigidify (c1/d0): "During your opponent's next turn, this Pokémon takes 30 less damage from attacks…" | tags: none | Correct: damage reduction has no tag category.
- **147 Cradily** ✅ — Miasma Wind (c1/d100): "This attack does 100 damage for each Special Condition affecting your opponent's Active Pokémon." · ABL: "Once during your turn, you may flip a coin. If heads, choose Burned, Confused, or Poisoned…" | tags: none | Correct: scaling attack untagged per spec, and the ability block has no probabilistic field.
- **162 Slowpoke** ✅ — Dangle Tail (c1/d0): "Put a Pokémon from your discard pile into your hand." | tags: none | Correct: discard recovery has no tag category, and "put a Pokémon…" rightly didn't trip `counter_snipe`.
- **164 Comfey** ✅ (override) — Flower Shower (c1/d0): "Each player draws 3 cards." · Play Rough (c1/d20): "Flip a coin. If heads, this attack does 20 more damage." | tags: ATK1 `{draws_cards: 3, deckout: 1}`, ATK2 `{probabilistic: 1}` | Correct via seed override.
- **179 Black Kyurem ex** ✅ — Ice Age (c3/d90): "If your opponent's Active Pokémon is a {N} Pokémon, it is now Paralyzed." · Black Frost (c4/d250): "This Pokémon also does 30 damage to itself." | tags: none | Correct: conditional status and self-damage have no tag categories.
- **190 Archaludon ex** ❌ **FN** — Metal Defender (c3/d220): "During your opponent's next turn, this Pokémon has no Weakness." · ABL: "When you play this Pokémon from your hand to evolve 1 of your Pokémon during your turn, you may attach up to 2 Basic {M} Energy cards from your discard pile to your {M} Pokémon in any way you like." | tags: none | The ability is textbook energy acceleration but "attach **up to 2** Basic" fails the "attach **a** Basic" regex (fix #4) — should be `energy_active: 2`.
- **192 Iron Crown** ✅🔶 — Deleting Slash (c2/d40): "If your opponent has 3 or more Benched Pokémon, this attack does 80 more damage." | tags: none | Correct per spec (`conditional` is override-only); conditional-bonus override candidate (real ceiling 120).
- **199 Scatterbug** ✅ — Call for Family (c1/d0): "Search your deck for a Basic Pokémon and put it onto your Bench…" | tags: none | Correct: `search` exists only in the ability block; attack-level search isn't representable in the schema.
- **207 Milotic ex** 🔶 — Hypno Splash (c3/d160): "Your opponent's Active Pokémon is now Asleep." · ABL: "Prevent all damage from and effects of attacks from your opponent's Tera Pokémon done to this Pokémon." | tags: none | Correct per spec (IMMUNITY is override-only) — but this is a clear **IMMUNITY override candidate**.
- **210 Pikachu ex** ✅🔶 — Topaz Bolt (c3/d300): "Discard 3 Energy from this Pokémon." · ABL: "If this Pokémon has full HP and would be Knocked Out by damage from an attack, it is not Knocked Out, and its remaining HP becomes 10." | tags: ATK1 `{discard_energy: 3}` | Attack tag correct; the ability is the same Sturdy text that earned Crustle 533 an IMMUNITY override — **add Pikachu ex for consistency**.
- **229 Hydreigon ex** ✅ — Crashing Headbutt (c2/d200): "Discard the top 3 cards of your opponent's deck." · Obsidian (c4/d130): "This attack also does 130 damage to 2 of your opponent's Benched Pokémon…" | tags: ATK1 `{deckout: 1}`, ATK2 `{snipe: 130}` | Both correct.
- **256 Magmortar** ❌ **FN** (minor) — Searing Flame (c3/d90): "Flip a coin. If heads, your opponent's Active Pokémon is now Burned." · ABL: "During Pokémon Checkup, put 3 more damage counters on your opponent's Burned Pokémon." | tags: ATK1 `{probabilistic: 1}` | Attack correct; ability `damage` missed "put 3 **more** damage counters" (fix #7).
- **284 Larvitar** ✅ — Crunch (c2/d20): "Flip a coin. If heads, discard an Energy from your opponent's Active Pokémon." | tags: `{discard_energy: 1, probabilistic: 1}` | Correct per trigger; note `discard_energy` conflates self-cost discard with opponent energy denial — acceptable for now, worth a schema note.
- **286 Rockruff** ❌ **FN** — Dig It Up (c1/d0): "Look at the top card of your deck. You may discard that card." | tags: none | `probabilistic` missed "top **card**" with no number (fix #2) — the identical Litwick 493 text needed a hand override.
- **293 N's Zoroark ex** ✅🔶 — Night Joker (c2/d0): "Choose 1 of your Benched N's Pokémon's attacks and use it as this attack." · ABL: "You must discard a card from your hand… you may draw 2 cards." | tags: ABL `{draw: 2}` | Draw correct; copy-attack gives max_damage=0 → **max_damage override candidate** (meta deck).
- **319 Charcadet** ✅ — vanilla | tags: none | Correct.
- **327 Slowpoke** ✅ — vanilla | tags: none | Correct.
- **334 Sneasel** ✅ — vanilla | tags: none | Correct.
- **335 Bronzor** ✅ — vanilla | tags: none | Correct.
- **351 Rapidash** ✅ — ABL: "Once during your turn, you may draw a card." | tags: ABL `{draw: 1}` | Correct ("draw a card" → N=1).
- **394 Shroomish** ✅ — vanilla | tags: none | Correct.
- **408 Team Rocket's Houndour** ✅ — vanilla | tags: none | Correct.
- **430 Team Rocket's Hypno** ❌ **FN** — Bench Manipulation (c3/d80): "Your opponent flips a coin for each of their Benched Pokémon. This attack does 80 damage to your opponent's Active Pokémon for each tails…" | tags: none | `probabilistic` missed the third-person "flips a coin" (fix #1); correctly did NOT fire `snipe` (damage goes to the Active).
- **433 Team Rocket's Chingling** ❌ **FN** (borderline) — Chiming Commotion (c0/d0): "Discard a random card from your opponent's hand." | tags: none | Random effect without coin text — spec calls `probabilistic` "coin flips / random effects", so add the `a random` keyword (fix #3) or accept as override-only.
- **436 Team Rocket's Orbeetle** ✅ — Psychic (c3/d40): "This attack does 40 more damage for each Energy attached to your opponent's Active Pokémon." · ABL: "As often as you like during your turn, you may move 1 damage counter from 1 of your Team Rocket's Pokémon to another of your Pokémon." | tags: none | Correct: scaling untagged per spec, and moving counters among your own Pokémon is rightly neither `damage` nor `heal` (net zero).
- **441 Team Rocket's Pupitar** ✅ — Explosive Ascension (c1/d30): "Search your deck for a card that evolves from this Pokémon and put it onto this Pokémon to evolve it…" | tags: none | Correct: attack-level search isn't in the schema.
- **448 Team Rocket's Ekans** ✅ — Drag Down (c1/d0): "Flip a coin. If heads, your opponent's Active Pokémon is now Paralyzed." | tags: `{probabilistic: 1}` | Correct.
- **450 Team Rocket's Nidoran♀** ✅ — Surprise Attack (c1/d30): "Flip a coin. If tails, this attack does nothing." | tags: `{probabilistic: 1}` | Correct.
- **452 Team Rocket's Nidoqueen** ✅🔶 — Love Impact (c1/d60): "If a Pokémon that has 'Nidoking' in its name is on your Bench, this attack does 120 more damage." | tags: none | Correct per spec (`conditional` override-only); conditional + max_damage (180 real) override candidate.
- **458 Team Rocket's Crobat ex** ✅ — Assassin's Return (c2/d120): "You may put this Pokémon into your hand…" · ABL: "…you may choose 2 of your opponent's Pokémon and put 2 damage counters on each of them." | tags: ABL `{damage: 20}` | Trigger fired correctly; note the true total is 4 counters (2×2), so 20 undercounts — fine as a magnitude signal.
- **467 Zamazenta** ✅ — Strong Bash (c3/d70): "During your opponent's next turn, if this Pokémon is damaged by an attack…, put damage counters on the Attacking Pokémon equal to the damage done to this Pokémon." | tags: none | Correct: retaliation has no tag category and the numberless counter text rightly didn't trip `counter_snipe`.
- **470 Team Rocket's Meowth** ❌ **FN** — Paw-cket Pilfer (c1/d0): "Choose a random card from your opponent's hand. Your opponent reveals that card and shuffles it into their deck." · Fury Swipes (c2/d20): "Flip 3 coins. This attack does 20 damage for each heads." | tags: none | Two misses: "Flip **3** coins" (fix #1) and the random-card effect (fix #3).
- **477 Swellow** ✅ — Add On (c1/d0): "Draw 3 cards." | tags: `{draws_cards: 3}` | Correct.
- **502 Seismitoad** ✅ — Round (c3/d70): "This attack does 70 damage for each of your Pokémon in play that has the Round attack." | tags: none | Correct: scaling untagged per spec.
- **506 Cubchoo** ✅ (override) — Snotted Up (c1/d10): "During your opponent's next turn, the Defending Pokémon can't use attacks." | tags: `{cubchoo: 1}` | Correct via seed override.
- **539 Krokorok** ✅ — Tighten Up (c2/d40): "Your opponent discards 2 cards from their hand." | tags: none | Correct: hand disruption has no tag category (and `discard_energy` rightly didn't fire on card discard).
- **542 Mandibuzz** ✅ — ABL: "…Your opponent reveals their hand, and you put a Basic Pokémon with 70 HP or less that you find there onto your opponent's Bench." | tags: none | Correct: bench-filling disruption has no category; rightly not `gust` (no "switch in").
- **543 Escavalier** ✅ — Wild Lances (c1/d90): "This Pokémon also does 30 damage to itself." | tags: none | Correct.
- **547 Genesect ex** ✅ — ABL: "Once during your turn, you may search your deck for up to 2 Evolution {M} Pokémon, reveal them, and put them into your hand…" | tags: ABL `{search: 2}` | Correct.
- **549 Fraxure** ✅ — Boundless Power (c2/d90): "During your next turn, this Pokémon can't use attacks." | tags: `{cooldown: 1}` | Correct.
- **553 Unfezant** ✅ — Add On (c1/d0): "Draw 4 cards." · Swift Flight (c2/d120): "Flip a coin. If heads, during your opponent's next turn, prevent all damage…" | tags: `{draws_cards: 4}`, `{probabilistic: 1}` | Both correct.
- **564 Shelmet** ✅ — ABL: "If you have Karrablast in play, this Pokémon can evolve during your first turn or the turn you play it." | tags: none | Correct: evolution enabler has no category.
- **570 Pansear** ✅ — Collect (c1/d0): "Draw a card." | tags: `{draws_cards: 1}` | Correct.
- **593 Cofagrigus** ✅🔶 — Extended Damagriiigus (c2/d0): "Move all damage counters from 1 of your Benched Pokémon to 1 of your opponent's Pokémon." | tags: none | Correct per trigger ("all", no number, isn't parseable) — Munkidori-style heal+counter_snipe **override candidate**.
- **601 Gigalith** ✅ — Vengeful Cannon (c1/d20): "This attack does 20 damage for each damage counter on all of your Benched {F} Pokémon." | tags: none | Correct: scaling untagged; rightly not `outrage` (counts bench counters, not "on this Pokémon").
- **645 Marnie's Scrafty** ✅ — Wild Tackle self-damage | tags: none | Correct.
- **647 Marnie's Morgrem** ✅ — vanilla | tags: none | Correct.
- **665 Raboot** ✅ — Jumping Kick (c1/d40): "This attack does 40 damage to 1 of your opponent's Pokémon…" | tags: `{snipe: 40}` | Correct (free-target snipe).
- **690 Nickit** ✅ — vanilla | tags: none | Correct.
- **697 Tinkatink** ✅ — vanilla | tags: none | Correct.
- **705 Gumshoos** ✅ — ABL: "Once during your turn, you may use this Ability. Switch a card from your hand with the top card of your deck." | tags: none | Correct: card-swap rightly did NOT trip the `switch` tag (which is about Pokémon switching) — good no-false-positive case.
- **728 Inteleon** ✅ — Bring Down (c1/d0): "Choose a Pokémon in play… that has the least HP remaining… and it is Knocked Out." · Water Shot (c1/d110): "Discard an Energy from this Pokémon." | tags: ATK2 `{discard_energy: 1}` | Correct; auto-KO has no tag category (note: nothing represents Bring Down's threat — future tag or override thought).
- **736 Electrike** ✅ — self-damage | tags: none | Correct.
- **741 Abra** ✅ — Teleportation Attack (c1/d10): "Switch this Pokémon with 1 of your Benched Pokémon." | tags: none | Correct: `switch` exists only in the ability block; attack-level self-switch isn't representable.
- **742 Kadabra** ✅ — ABL: "Once during your turn, when you play this Pokémon from your hand to evolve…, you may use this Ability. Draw 2 cards." | tags: ABL `{draw: 2}` | Correct.
- **748 Shedinja** 🔶 — Damage Beat (c1/d20): "…20 damage for each damage counter on your opponent's Active Pokémon." · ABL: "If this Pokémon is Knocked Out by damage from an attack from your opponent's Pokémon {ex}, your opponent can't take any Prize cards for it." | tags: none | Correct per spec — but the ability is the textbook "rarely worth KOing" signal: **BARRIER override candidate**.
- **759 Lopunny** ✅ — Dashing Kick (c1/d50): "This attack does 50 damage to 1 of your opponent's Benched Pokémon…" | tags: `{snipe: 50}` | Correct.
- **776 Absol** ✅ — Allure (c1/d0): "Draw 2 cards." | tags: `{draws_cards: 2}` | Correct.
- **778 Oddish** ✅ — vanilla | tags: none | Correct.
- **779 Gloom** ❌ **FN** — Disperse Drool (c1/d20): "This attack also does 20 damage to each Benched Pokémon (both yours and your opponent's)…" | tags: none | Both-sides bench spread missed `snipe` — the text never says "opponent's Benched Pokémon" contiguously (fix #6).
- **811 Pawmot** ✅ — Voltaic Fist (c2/d130): "You may have this Pokémon also do 60 damage to itself and make your opponent's Active Pokémon Paralyzed." | tags: none | Correct: optional self-damage/status has no category.
- **818 Brambleghast** ✅ — ABL: "…when you play this Pokémon from your hand to evolve…, Make your opponent's Active Pokémon Confused." | tags: none | Correct: status infliction has no ability tag.
- **822 Trapinch** ❌ **FN** — Double Headbutt (c1/d10): "Flip 2 coins. This attack does 10 damage for each heads." | tags: none | `probabilistic` missed "Flip 2 coins" (fix #1).
- **860 Snorunt** ✅ — vanilla | tags: none | Correct.
- **865 Snom** ✅ — vanilla | tags: none | Correct.
- **866 Frosmoth** ✅ — Cold Cyclone (c2/d90): "Move a {W} Energy from this Pokémon to 1 of your Benched Pokémon." · ABL: "Once during your turn, if this Pokémon is in the Active Spot… Each player draws a card." | tags: ABL `{draw: 1, mill: 1}` | Correct: energy move rightly untagged (`energy_accel` = attach, not move); mill+draw right.
- **878 Hop's Phantump** ✅ — Splashing Dodge (c1/d10): "Flip a coin. If heads, during your opponent's next turn, prevent all damage…" | tags: `{probabilistic: 1}` | Correct.
- **920 Tapu Bulu** ✅ — self-damage | tags: none | Correct.
- **929 Magmar** ✅ — Searing Flame (c2/d30): "Flip a coin. If heads, your opponent's Active Pokémon is now Burned." | tags: `{probabilistic: 1}` | Correct.
- **940 Glalie** ✅ — Damage Beat scaling · Crazy Headbutt (c3/d140): "Discard an Energy from this Pokémon." | tags: ATK2 `{discard_energy: 1}` | Correct.
- **941 Spheal** ✅ — Powder Snow (c1/d10): "Your opponent's Active Pokémon is now Asleep." | tags: none | Correct: status infliction has no attack tag category.
- **947 Quaxly** ✅ — Aerial Ace (c1/d10): "Flip a coin. If heads, this attack does 20 more damage." | tags: `{probabilistic: 1}` | Tag correct; max_damage=10 vs real 30 — minor, generic to coin-bonus attacks.
- **1023 Fletchinder** ✅ — vanilla | tags: none | Correct.
- **1035 Shinx** ❌ **FN** — Double Scratch (c1/d10): "Flip 2 coins. This attack does 10 damage for each heads." | tags: none | Same "Flip N coins" miss (fix #1).
- **1094 Bug Catching Set** ⬜ — "Look at the top 7 cards of your deck…" | tags: none | Item card, never encoded.
- **1099 Antique Root Fossil** ⬜ — "Play this card as if it were a 60-HP Basic {C} Pokémon…" | tags: none | Item, but note: fossils can BE in play as Pokémon — if one shows up in an opponent slot, live `maxHp` covers HP and zero tags read as vanilla, which is fine.
- **1104 Megaton Blower** ⬜ — "Discard all Pokémon Tools and Special Energy from all of your opponent's Pokémon…" | tags: none | Item, never encoded; correctly no `discard_energy` (that's an attack tag).
- **1117 Potion** ⬜ — "Heal 30 damage from 1 of your Pokémon." | tags: ABL `{heal: 30}` | Item, never encoded; extraction incidentally correct.
- **1131 Team Rocket's Bother-Bot** ⬜ — "Turn 1 of your opponent's face-down Prize cards face up and choose a random card from your opponent's hand…" | tags: none | Item, never encoded.
- **1141 Premium Power Pro** ⬜ — "During this turn, attacks used by your {F} Pokémon do 30 more damage…" | tags: none | Item, never encoded.
- **1150 Antique Jaw Fossil** ⬜ — fossil text as 1099 | tags: none | Item; same fossil note as 1099.
- **1162 Binding Mochi** ⬜ — "Attacks used by the Poisoned Pokémon this card is attached to do 40 more damage…" | tags: none | **Tool** card: conditional damage boost isn't bakeable into stats, so per the tool decision it's covered by the bare `has_tool` flag — correct.
- **1183 Perrin** ⬜ — "Reveal up to 2 Pokémon in your hand and put them into your deck. If you do, search your deck for up to that many Pokémon…" | tags: ABL `{search: 1}` | Supporter, never encoded.
- **1196 Cassiopeia** ⬜ — "…Search your deck for up to 2 cards and put them into your hand…" | tags: ABL `{search: 2}` | Supporter, never encoded.
- **1198 Crispin** ⬜ — "Search your deck for up to 2 Basic Energy cards of different types…" | tags: ABL `{search: 2}` | Supporter, never encoded.
- **1207 Amarys** ⬜ — "Draw 4 cards. At the end of this turn, if you have 5 or more cards in your hand, discard your hand." | tags: ABL `{draw: 4}` | Supporter, never encoded.
- **1210 Brock's Scouting** ⬜ — "Search your deck for up to 2 Basic Pokémon or 1 Evolution Pokémon…" | tags: ABL `{search: 2}` | Supporter, never encoded.
- **1233 Canari** ⬜ — "…Search your deck for up to 4 {L} Pokémon…" | tags: ABL `{search: 4}` | Supporter, never encoded.
- **1237 Lucian** ⬜ — "Each player shuffles their hand and puts it on the bottom of their deck… If heads, that player draws 6 cards. If tails, they draw 3 cards." | tags: ABL `{draw: 6}` | Supporter, never encoded.
- **1248 Academy at Night** ⬜ — "Once during each player's turn, that player may put a card from their hand on top of their deck." | tags: none | Stadium, never encoded.
- **1267 Lumiose City** ⬜ — "Once during each player's turn, that player may search their deck for a Basic Pokémon and put it onto their Bench…" | tags: none | Stadium, never encoded; "search **their** deck" correctly didn't match the "search **your** deck" trigger.

## Tallies

- ✅ correct: 70 (of the 82 encodable Pokémon-side cards)
- ❌ false negatives: 12 cards (52, 94, 136, 190, 256, 286, 430, 433, 470, 779, 822, 1035) — all covered by the 7 regex fixes above
- ❌ false positives: **0**
- 🔶 override candidates: 207, 210, 748, 192, 452, 593, plus max_damage entries for 52, 94, 293
- ⬜ Trainer/Energy (never encoded): 18
