# Round 3 Audit — 100 cards (seed 103, Pokémon-only)

Edit applied before this batch: the 4 round-2 fixes (deckout requires a "discard …
opponent's deck" context; ability energy-accel broadened past the rigid anchor; attack
draw-until; free-switch ability). Full-pool diff: 23 cards changed, **all verified
correct, 0 new false positives**. Two tag *removals* (595 Gothorita, 1091 Accompanying
Flute) confirmed as genuine peek/reveal FPs; new draw-until (129/381/554/691), ability
accel (725/1052 + several inert Trainers), and switch (75/847/924) catches all legit.

**Legend:** ✅ correct · ❌ FN/FP · 🔶 override/worklist · ❓ human review.

## Queued regex fix for round 4

1. **ability `damage` self-counter FP**: `_RX_ABL_DMGCTR` matches "put N damage
   counters" without checking the target. **49 Feraligatr** — "put 5 damage counters
   on **this Pokémon**" (a self-cost to power up its own attack) is wrongly tagged
   `damage: 50`. The `damage` field means counters dealt to the OPPONENT. Fix: require
   an opponent target, mirroring `counter_snipe` →
   `(?:put|place) (?:up to )?{N} (?:more )?damage counters?[^.]{0,40}?opponent`.
   (Keeps Dusclops 132, Dusknoir 133, Pecharunt 230, Magmortar 256, Crobat ex 458 —
   all "on … your opponent's Pokémon".)

## Per-card review

Round-1/2/3 fixes confirmed on fresh cards: 554 (draws_cards 6, draw-until), 595
(Fortunate Eye look-at → deckout now 0), 1052 (ability accel 1), 138/194/336 (search-
then-attach energy_accel), 880 (place-verb counter_snipe 120 + discard_energy 3),
multi-coin probabilistic (172/350/761), typed discard-all (636/946/636).

Correct (vanilla / correct-by-trigger / correct zeros-per-spec): 33, 44 (cooldown ✓),
71 (discard_energy 1 ✓), 76🔶, 103 (probabilistic ✓), 121 (counter_snipe 60 ✓), 128,
132 (damage 50, opponent ✓), 138 (accel 2 ✓), 145 (search-to-HAND correctly NOT accel
✓), 148, 151, 158🔶, 172, 177, 181, 185, 191🔶, 194, 215 (counter_snipe 20 ✓), 261,
271 (draw 6 ✓), 285, 298 (snipe 50 ✓), 315, 321, 325, 332 (retreat), 336, 350, 364,
366 (snipe 30 ✓), 376, 401 (energy_active 1 ✓), 414🔶, 416, 420 (attack-heal correctly
untagged ✓), 421, 438 (attack-gust ❓ noted), 464 (snipe 20 ✓), 485, 499, 529 (deckout
✓), 550🔶, 551, 572, 600🔶, 607 (revenge ✓), 636 (discard_energy 3 ✓), 637, 654, 657,
660 (probabilistic ✓, top of YOUR deck), 679, 682 (snipe 20, cooldown ✓), 688 (deckout
✓), 689 (retreat), 695🔶, 700 (probabilistic ✓), 730 (snipe 20 to each opp ✓), 734🔶,
751, 760, 761, 784 (heal 60 ✓), 801, 821 (retreat), 825, 833, 842, 873, 880, 894
(discard_energy 1 ✓), 895 (probabilistic ✓), 898 (search 1 ✓), 933, 946 (snipe 120 +
discard_energy 3 ✓), 952, 964, 970 (coin-in-ability correctly untagged ✓), 973, 991,
995 (probabilistic, top of YOUR deck ✓), 996, 1001, 1022❓ (opp-energy discard), 1029
(energy "move" correctly NOT accel ✓), 1034, 1050 ("put Energy into hand" NOT discard
✓), 1052, 1057, 1071 (search 1 ✓), 1074 (self-bench spread correctly NOT snipe ✓).

### Issues

- **49 Feraligatr** ❌ **FP** — ABL: "you may put 5 damage counters on **this Pokémon**. If you do … attacks used by this Pokémon do 120 more damage." | `{damage: 50}` | Self-counter cost mis-tagged as opponent damage; fix #1.
- **750 Grumpig** 🔶 — ABL: "Look at the top 4 cards of your deck and attach **any number** of Basic Energy cards you find there to your Pokémon." | none | Genuine energy accel but "any number" is unparseable → override worklist.
- **845 Smeargle** 🔶 — Energizing Sketch: "Flip 3 coins. Attach an amount of Basic Energy up to the number of heads from your discard pile to your Benched Pokémon." | `{probabilistic: 1}` | Coin-gated variable accel; `probabilistic` right, the accel amount is unparseable → worklist.
- **864 N's Vanilluxe** 🔶 — Snow Coating: "Double the number of damage counters on each of your opponent's Pokémon." | none (Blizzard snipe 10 ✓) | Counter-doubling has no schema category → note.
- **362 Misty's Magikarp** 🔶 — ABL: "As long as this Pokémon is on your Bench, prevent all damage … done to this Pokémon." | none | Self-protection; a BARRIER-style override candidate (correct zeros per spec today).
- Conditional-bonus group (correct zeros; `conditional` override-only): 76 Slugma (+40 if Burned), 138 Okidogi ex (+130 if Poisoned), 158 Drednaw, 191 Gholdengo (+90), 414 TR Articuno (+60), 550 Haxorus (+80), 600 Boldore (+50), 695 Mega Mawile ex, 734 Magnezone (+120) → worklist group.
- Recurring, already filed: attack-gust (438 Primeape), opponent-energy discard (1022 Decidueye ex), retreat-lock (332, 689, 821).

## Tallies

- ✅ correct: 99 · ❌ FN: 0 · ❌ FP: 1 (49)
- 🔶 worklist: 750, 845, 864, 362 + conditional group (76, 138, 158, 191, 414, 550, 600, 695, 734)
- ❓ human review: none new (438, 1022, retreat-lock already filed)
