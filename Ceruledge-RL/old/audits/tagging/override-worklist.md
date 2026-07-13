# Override Worklist — cards needing hard-coded entries in attack_overrides.py

Format: card id | name | suggested override | reason.

## From round 0 (tag_audit_100.md)

- 207 | Milotic ex | ability {immunity: 1} | "Prevent all damage from and effects of attacks from your opponent's Tera Pokémon done to this Pokémon" — IMMUNITY is override-only
- 210 | Pikachu ex | ability {immunity: 1} | Sturdy text identical to Crustle 533's seeded IMMUNITY
- 748 | Shedinja | ability {barrier: 1} | "your opponent can't take any Prize cards for it" — textbook "rarely worth KOing"
- 192 | Iron Crown | atk1 {conditional: 1}, max_damage 120 | "+80 if opponent has 3+ Benched" — conditional is override-only
- 452 | Team Rocket's Nidoqueen | atk1 {conditional: 1}, max_damage 180 | "+120 if Nidoking on Bench"
- 593 | Cofagrigus | atk1 {heal-equivalent + counter_snipe} | "Move ALL damage counters from 1 of your Benched to 1 of opponent's" — amount unparseable
- 52 | Wugtrio ex | max_damage 180 | Tricolor Pump scales 60×3
- 94 | Sinistcha | max_damage 210 | Spill the Tea scales 70×3
- 293 | N's Zoroark ex | max_damage ~180 | Night Joker copies bench attacks; printed 0

## From round 1 (round-1-report.md)

- 99 | Hearthflame Mask Ogerpon ex | atk2 {conditional: 1}, max_damage 280 | "+140 if opponent's Active is an Evolution Pokémon"
- 193 | Alolan Exeggutor ex | atk1 {energy_accel: ~3} | "attach any number of Basic Energy cards" — N unparseable
- 201 | Wo-Chien | atk1 {conditional: 1} | snipe 120 gated on "3 or fewer cards in your deck"
- 790 | Mega Charizard X ex | atk1 {discard_energy: ~3}, max_damage ~270 | "Discard any amount of {R} Energy … 90 for each"
- 943 | Walrein | atk1 {cubchoo: 1} | "Pokémon that have 2 or less Energy attached can't use attacks" — conditional lock, unregexable
- 968 | Dachsbun ex | ability {heal: ~100} | "Heal ALL damage from each of your Evolution Pokémon" — amount unparseable (fallback gave 10)
- 1056 | Mega Zygarde ex | atk2 {snipe: 150} | per-opponent-Pokémon coin-flip 150 — "damage to that Pokémon" too generic to regex
- 224 | Annihilape | atk2 note | "Both Active Pokémon are Knocked Out" — mutual-KO, no category; consider conditional
- Conditional-bonus group (atk {conditional: 1} each; damage gate in parens): 312 Sandy Shocks (+70), 419 Abomasnow (+120), 490 Victini (does-nothing gate), 540 Krookodile (+120), 545 Bisharp (+60), 624 Durant (+20), 694 Steelix (+200), 876 Mismagius (counter-snipe gate), 884 Medicham (does-nothing gate), 897 Pangoro (+120), 1049 Hippowdon (deckout gate)

## From round 2 (round-2-report.md)

- 386 | Cornerstone Mask Ogerpon (non-ex) | REMOVE ability override | Seed injects a phantom `immunity` ability; this card has NO ability (only Rock Kagura + Mountain Ramming). The ex (117) is the immunity holder. Correct the seed.
- 277 | N's Sigilyph | note (no tag) | Victory Symbol alt-win-condition ("you win this game" if exactly 1 prize) — no schema category
- 982 | Scolipede | atk1 {counter_snipe: ~variable} | "Place damage counters until remaining HP is 10" — no parseable N
- 471 | Team Rocket's Persian ex | max_damage | Haughty Order copies an opponent attack; printed 0 for that attack
- 615 | Zoroark | max_damage | Foul Play copies opponent's attack; printed 0
- Conditional-bonus group (round 2): 583 Keldeo ex (+90 if moved to active), 714 Dhelmise (+50 if stadium), 780 Vileplume (+120 if healed), 802 Mamoswine (+120 if stadium), 976 Carbink (+100 if opp ≤2 prizes)

## From round 3 (round-3-report.md)

- 750 | Grumpig | ability {energy_active: ~variable} | "attach ANY NUMBER of Basic Energy … to your Pokémon" — N unparseable
- 845 | Smeargle | atk1 {energy_accel: ~variable} | "Attach an amount of Basic Energy up to the number of heads" — coin-gated, unparseable (probabilistic already set)
- 864 | N's Vanilluxe | atk1 note | "Double the number of damage counters on each of your opponent's Pokémon" — no schema category
- 362 | Misty's Magikarp | ability {barrier: 1} | self-protection while benched — BARRIER-style
- Conditional-bonus group (round 3): 76 Slugma (+40 if Burned), 138 Okidogi ex (+130 if Poisoned), 158 Drednaw, 191 Gholdengo (+90), 414 TR Articuno (+60), 550 Haxorus (+80), 600 Boldore (+50), 695 Mega Mawile ex, 734 Magnezone (+120)

## From round 4 (round-4-report.md)

- 219 | Cofagrigus | atk1 {counter_snipe: 60} | "Put 6 damage counters on each Pokémon that has an Ability (both sides)" — regex missed (opponent's not followed by Pok)
- 28 | Poltchageist | ability {barrier: 1} | self-protection while benched — BARRIER-style (same as 362 Misty's Magikarp)
- 63 | Raging Bolt ex | atk2 {discard_energy: ~variable} | "discard any amount of Basic Energy … 70 for each" — unparseable
- 417 | Gorebyss | atk1 {energy_accel: ~variable} | "attach any number of Basic {W} Energy … to this Pokémon" — unparseable
- 1072 | Snorlax | atk1 {energy_accel: ~variable} | coin-gated "attach up to heads" — unparseable (probabilistic set)
- Conditional-bonus group (round 4): 54 Bronzor (+30 if {P}), 130 Revavroom ex (+120 if moved), 213 Tapu Koko (+90 if prize-ahead), 311 Hop's Cramorant (does-nothing gate), 577 Basculin (does-nothing gate), 707 Tangrowth (+140 if extra energy), 791 Moltres (+90 if ex)
