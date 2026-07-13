# Round 4 Audit — 100 cards (seed 104, Pokémon-only)

Edit applied before this batch: the 1 round-3 fix (ability `damage` must target the
opponent — a `(?! on this Pok|itself)` lookahead drops self-counter costs). Kept the
verb as "put" only (not "place") after the diff showed "place N counters" is used
exclusively for reactive/retaliation or self-side effects, neither a proactive
opponent-damage ability. Full-pool diff: **exactly 1 card changed** (49 Feraligatr
`damage` 50→0, the intended FP removal), 0 collateral.

**Legend:** ✅ correct · ❌ FN/FP · 🔶 override/worklist · ❓ human review.

## Queued regex fix for round 5 (final edit)

1. **`draw` opponent-draw FP**: `_RX_TAG_DRAWN`/`_RX_TAG_DRAW1` match "draw(s) N cards"
   regardless of who draws. **1019 Vivillon** — ABL "… they draw 4 cards" (a hand-
   refresh **disruption** where the OPPONENT draws) is wrongly tagged `draw: 4`. Fix:
   guard the draw triggers so the drawer is us, e.g. chain lookbehinds
   `(?<!they )(?<!opponent )(?<!player )draws?` (and exclude "each player draws" which
   is already the mill branch). Keeps "you may draw N", "draw N cards" (imperative).

## Per-card review

Round-1..4 fixes confirmed on fresh cards: 738 Pachirisu now fully clean (round-2
`(?<!they )` accel guard holds — no energy_accel, no counter FP); 75 Iron Leaves ex
switch ✓; 725 Clawitzer ability accel 2 ✓; 534/561/634 energy_accel ✓; 63 draws_cards 6
✓; multi-coin probabilistic throughout; typed discard-all (144/167/721/1037/1040 ✓).

Correct (vanilla / correct-by-trigger / correct zeros-per-spec): 28🔶, 34, 41 (snipe 30
✓), 45 (snipe 60 ✓), 46 (Blaze-Blitz lockout ≠ next-turn cooldown, correct zeros), 50,
53, 54🔶, 57, 63, 72 (search 1 ✓), 75, 77, 107, 108 (snipe 120 ✓; retreat), 122 (dig ≠
"search your deck", correct zeros), 123 (search 1 ✓), 130🔶, 144, 157, 159, 167, 173
(search 2 ✓), 202, 212, 213🔶, 214 (coin-in-ability correctly untagged ✓), 222, 242
(outrage ✓), 244 (discard_energy 2, cooldown ✓), 247 (counter_snipe 20 ✓), 270, 274,
279, 289 (self-bench spread NOT snipe ✓; retreat), 300, 301, 303 (outrage ✓), 311🔶,
333, 337 (discard_energy 1 + probabilistic ✓), 338 (revenge ✓), 341, 354, 365, 375
(self-bench "1 of YOUR Benched" NOT snipe ✓), 397, 409 (discard_energy 1 ✓), 410
(draws_cards 1 ✓), 423, 488, 509 (snipe 10 ✓), 526, 534, 535, 561, 577🔶, 605, 617,
634, 667, 673, 677 (cooldown ✓), 707🔶, 721 (discard_energy 2 ✓), 725, 738, 756 (draw 2
✓), 762, 768, 777 (cooldown + probabilistic ✓), 791🔶, 792, 807, 808, 859, 863 (cubchoo
✓), 868 (snipe 60, discard_energy 2 ✓), 888, 890, 891, 899 (pseudo-whirlwind, opponent
chooses — correct zeros), 907, 926, 927, 938 (discard_energy 1 + probabilistic ✓), 961,
986, 1003 (search-to-HAND NOT accel ✓), 1011 (retreat), 1018, 1024 (coin-in-ability
untagged ✓), 1030, 1037, 1040, 1072🔶.

### Issues

- **1019 Vivillon** ❌ **FP** — ABL: "Your opponent shuffles their hand … **they draw 4 cards**." | `{draw: 4}` | Opponent-draw disruption mis-tagged as our draw; fix #1.
- **255 Maractus** ❓ — ABL: "If this Pokémon is KO'd …, **put** 6 damage counters on the Attacking Pokémon." | `{damage: 60}` | Retaliation is tagged because it uses "put"; but the "**place** … on the Attacking Pokémon" retaliation cards (Spiritomb, Mega Scrafty ex, Orthworm ex) stay untagged. Inconsistent put/place handling → human review: should retaliation abilities count as `damage` at all? (I kept put-only in round 4 specifically to avoid the Toxtricity "place counters on your OWN benched Pokémon" self-FP.)
- **219 Cofagrigus** 🔶 — Law of the Underworld: "Put 6 damage counters on each Pokémon that has an Ability (both yours and your opponent's)." | none | Both-sides ability-counter; `counter_snipe` missed (the "opponent's" isn't followed by "Pok") → override/note.
- **28 Poltchageist** 🔶 — self-protection-while-benched ability → BARRIER-style override candidate (like Misty's Magikarp).
- Unparseable-N accel/discard (correct probabilistic where coin-gated; the accel/discard amount can't be parsed): 63 Raging Bolt ex ("discard any amount"), 417 Gorebyss ("attach any number"), 1072 Snorlax (coin-gated attach) → worklist.
- Conditional-bonus group (correct zeros; override-only): 54 Bronzor, 130 Revavroom ex, 213 Tapu Koko, 311 Hop's Cramorant, 577 Basculin, 707 Tangrowth, 791 Moltres → worklist group.
- Recurring, already filed: opponent-energy discard (337 Lugia, 938 Croconaw, 123 Farfetch'd special-energy), retreat-lock (108, 289, 1011), attack-gust (899 pseudo).

## Tallies

- ✅ correct: 99 · ❌ FN: 0 · ❌ FP: 1 (1019)
- 🔶 worklist: 219, 28, 63, 417, 1072 + conditional group (54, 130, 213, 311, 577, 707, 791)
- ❓ human review: 255 (retaliation put/place consistency)
