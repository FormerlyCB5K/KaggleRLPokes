# Round 2 Audit — 100 cards (seed 102, Pokémon-only)

Edit applied before this batch: the 6 round-1 fixes (deckout "into"-FP guard, typed
"discard all {M} Energy", "place" counter verb, attack-level energy accel [direct +
search-then-attach], Special-Energy ability accel, "top card of each player's deck").
Full-pool diff: 34 cards changed. All intended fixes present; verification caught **2
new false positives** which were fixed on the spot before sampling:
- **738 Pachirisu** — "whenever *they* attach an Energy card … place 8 counters" wrongly
  got `energy_accel` (opponent attaches, not us). Fixed with a `(?<!they )` lookbehind.
- Confirmed **246 Espeon ex / 316 Sylveon ex** deckout removals are correct (both
  "shuffle … INTO your opponent's deck").

**Legend:** ✅ correct · ❌ FN/FP · 🔶 override/worklist · ❓ human review.

## Queued regex fixes for round 3

1. **deckout look/reveal FP**: bare "of/from your opponent's deck" still fires on
   non-mill peeking — 435 Dottler ("**Look at** the top 5 cards of your opponent's
   deck and put them back"), 471 Persian ex ("**Reveal** the top 10 … shuffle back").
   Genuine mill always says "**discard** … your opponent's deck". Fix: require a
   discard context → `discard [^.]{0,40}?(?:of|from) your opponent's deck` (keeps
   Deino/Durant/Flygon/Diglett; keeps EACHDRAW branch).
2. **ability energy-accel anchor too rigid**: 795 Oricorio ex — "As often as you like
   during your turn … **Attach** a Basic {R} Energy card from your hand to 1 of your
   Benched {R} Pokémon" is uncaught (anchor demands "during your turn, you may
   attach"). Broaden to catch "attach {N} … Energy … to … (Benched) Pokémon" in
   ability text, guarded against "move"/opponent phrasings.
3. **attack draw-until**: 125 Blissey ex, 813 Mismagius ex — "draw cards until you
   have 6 cards in your hand" (an ATTACK) isn't tagged `draws_cards`; the draw-until
   pattern exists only for abilities. Add it to `attack_tags` (value = target N).
4. **free-switch abilities** (minor): 847 Linoone, 924 Meowscarada — "Switch this
   Pokémon with your Active Pokémon" ability not tagged `switch`; current SWITCH regex
   wants "switch 1 of your" / "switch your Active". Low priority.

## Per-card review

Vanilla / correct-by-trigger (no issue): 73, 84 (discard_energy 2 ✓), 109, 133 (damage
130 ✓; "can't retreat" untagged), 175, 176, 182 (draw 5 via draw-until ✓), 198 (mill ✓),
203 (scaling "for each Benched" correctly NOT snipe ✓), 227, 230 (damage 50 ✓; retreat),
248 (discard_energy 3 ✓), 249, 265, 280, 299 (snipe 30, cooldown ✓), 304, 326 (accel 1,
cooldown ✓), 329, 355, 383, 411 (probabilistic ✓), 516, 524, 538, 567, 571, 573
(discard_energy 1 ✓), 581, 589, 627 (probabilistic ✓), 639, 652 (energy "move" correctly
NOT accel ✓), 663 ("put Energy into hand" correctly NOT discard ✓), 664, 675 (draw 3 ✓),
681, 685, 686, 693, 701, 702 (5 coins ✓), 718, 727, 740, 749, 774 (snipe 120 +
discard_energy 2 ✓), 786, 787, 789, 794, 797 (discard_energy 4 ✓), 800, 802
(discard_energy 2 ✓), 806 (discard_energy 2 ✓), 814, 824 (mill ✓), 856, 867 (snipe 20,
cooldown ✓), 874, 881 (deckout + probabilistic ✓), 883, 911 (heal 30 ✓), 913, 936, 950,
954 (discard_energy 2 ✓), 955, 1002, 1025, 1043, 1045 (search 2 ✓), 1046.

Round-1/2 fixes confirmed working on fresh cards: energy-accel (326, 386), typed
discard-all (248/797/806/954/806), "place" counter verb (none FP here), multi-coin
probabilistic (411/524/702/727/749/786), deckout precision (246/316 correctly zero).

### Issues

- **246 Espeon ex** ✅ — Amazez devolve-shuffle-into-opp-deck now **0** deckout (FP fixed); Psych Out "Discard a random card" → `probabilistic` ✓.
- **316 Sylveon ex** ✅ — Angelite shuffle-into-opp-deck now **0** tags (FP fixed).
- **435 Team Rocket's Dottler** ❌ **FP** — "Look at the top 5 cards of your opponent's deck and put them back in any order." | `{deckout: 1}` | Peeking isn't milling; fix #1.
- **471 Team Rocket's Persian ex** ❌ **FP** — "Reveal the top 10 cards of your opponent's deck … Shuffle the revealed cards into your opponent's deck." | `{deckout: 1}` | Reveal-and-shuffle-back isn't milling; fix #1. (Also copy-attack → max_damage understated → worklist.)
- **795 Oricorio ex** ❌ **FN** — ABL: "As often as you like during your turn … Attach a Basic {R} Energy card from your hand to 1 of your Benched {R} Pokémon." | none | Energy accel missed; anchor too rigid (fix #2).
- **125 Blissey ex** ❌ **FN** — Return: "You may draw cards until you have 6 cards in your hand." | none | Attack draw-until untagged (fix #3).
- **813 Mismagius ex** ❌ **FN** — Hexa-Magic: same "draw cards until you have 6" attack | none | fix #3.
- **847 Linoone** ❌ **FN** (minor) — ABL: "Switch this Pokémon with your Active Pokémon." | none | Free-switch ability untagged (fix #4).
- **924 Meowscarada** ❌ **FN** (minor) — ABL: "you may switch it with your Active Pokémon." | none | Same free-switch gap (fix #4); Rising Bloom conditional +90 → worklist.
- **480 Servine** ❓ — ATK1 effect text is **Japanese** in the EN CSV ("コインを1回投げオモテなら…") → 0 tags. Data-quality issue, not regex — a few cards carry untranslated text. Human review.
- **386 Cornerstone Mask Ogerpon** 🔶❓ — the seed override injects an `immunity` **ability**, but this non-ex card has **no ability** (only Rock Kagura + Mountain Ramming attacks). Phantom tag from a spec-seed over-inclusion; the ex (117) is the one with Cornerstone Stance. Flag for override correction.
- **277 N's Sigilyph** 🔶 — Victory Symbol: "If you use this attack when you have exactly 1 Prize card remaining, you win this game." | none | Alt-win-condition, no schema category → worklist/note.
- **982 Scolipede** 🔶 — Dastardly Jab: "Place damage counters on your opponent's Active Pokémon until its remaining HP is 10." | none | Variable counter placement, no parseable N → override.
- **565 Accelgor / 718 Centiskorch** ✅❓ — opponent-energy denial ("discard an Energy from your opponent's Active") sets `discard_energy`, same semantics question as round-0 Larvitar (already in human review).
- **508 Cryogonal** ✅❓ — Drag Off gust-as-attack ("Switch in 1 of your opponent's Benched…"), same attack-gust schema gap as round-1 385 Toedscruel (already in human review).
- Conditional-bonus group (correct zeros per spec; `conditional` is override-only): 583 Keldeo ex, 714 Dhelmise, 780 Vileplume, 802 Mamoswine (Wreck), 976 Carbink → worklist group.

## Tallies

- ✅ correct: 91 · ❌ FN: 5 (125, 795, 813 + minor 847, 924) · ❌ FP: 2 (435, 471)
- 🔶 worklist: 386 (override fix), 277, 982, 471/615 (copy-attack max), + conditional group (583, 714, 780, 802, 976)
- ❓ human review: 480 (Japanese CSV text), 386 (phantom ability)
