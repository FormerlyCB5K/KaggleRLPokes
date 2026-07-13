# Plan 05 — Full-Database New Attack Tag Audit

Date: 2026-07-11

## Scope and totals

- Database SHA-256: `A0EA63CF7ADCB65D35436CE0EB390DE6E2E35654A7C67C065A45F4ABAA00F373`
- Registry records: 1,267
- Pokémon reviewed: 1,056
- Attacks reviewed: 1,555
- `retreat_lock`: 27 attacks (26 regex, 1 pre-existing override)
- attack `immunity`: 15 attacks (14 regex, 1 pre-existing override)
- numeric `recoil`: 49 attacks (46 regex, 2 pre-existing overrides, 1 dynamic)
- Human review: 0 unresolved; 7 decisions recorded in the resolved review file
- No new Plan-05 manual overrides were needed.

All 1,555 attacks were inspected against the three approved definitions. The 1,458
attacks not listed below or in `new-tags-human-review.md` do not receive any of these
three tags.

## `retreat_lock` positives

All values are Boolean `1`.

| Card | Attack | Method | Exact effect text |
|---|---|---|---|
| 47 Totodile | Big Bite (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 52 Wugtrio ex | Numbing Hold (2) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 108 Wellspring Mask Ogerpon ex | Sob (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 133 Dusknoir | Shadow Bind (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 146 Lileep | Bind Down (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 180 Bruxish | Big Bite (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 223 Palossand ex | Sand Tomb (2) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 230 Pecharunt | Poison Chain (1) | regex | Your opponent’s Active Pokémon is now Poisoned. During your opponent’s next turn, that Pokémon can’t retreat. |
| 255 Maractus | Corner (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 289 Hop’s Sandaconda | Rumble (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 332 Dhelmise | Bind Down (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 378 Ethan's Sudowoodo | Impound (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 460 Team Rocket's Muk | Gooped Up (1) | regex | Your opponent’s Active Pokémon is now Confused. During your opponent’s next turn, that Pokémon can’t retreat. |
| 504 Carracosta | Big Bite (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 544 Pawniard | Corner (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 618 Hydreigon ex | Dark Bite (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 650 Bulbasaur | Bind Down (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 689 Yveltal | Clutch (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 821 Gliscor | Poison Ring (1) | regex | Your opponent’s Active Pokémon is now Poisoned. During your opponent’s next turn, that Pokémon can’t retreat. |
| 869 Stunfisk | Pouncing Trap (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. During your next turn, the Defending Pokémon takes 100 more damage from attacks (after applying Weakness and Resistance). |
| 879 Hop's Trevenant | Corner (2) | override | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 975 Stunfisk ex | Big Bite (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 981 Whirlipede | Poison Ring (1) | regex | Your opponent’s Active Pokémon is now Poisoned. During your opponent’s next turn, that Pokémon can’t retreat. |
| 993 Orthworm ex | Rock Tomb (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 1008 Larry's Braviary | Clutch (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 1011 Spinarak | Gooey Thread (1) | regex | During your opponent’s next turn, the Defending Pokémon can’t retreat. |
| 1012 Ariados | Poison Ring (1) | regex | Your opponent’s Active Pokémon is now Poisoned. During your opponent’s next turn, that Pokémon can’t retreat. |

Reviewed negatives include self-retreat locks (466 Skarmory, 998 Slakoth), Retreat
Cost increases, immediate switching, gust, and bench-to-active damage conditions.

## Attack `immunity` positives

All values are Boolean `1`. Narrow-source and threshold shields are in the human-review
file rather than this table.

| Card | Attack | Method | Exact effect text |
|---|---|---|---|
| 65 Dunsparce | Dig (2) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 185 Flittle | Splashing Dodge (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 194 Altaria | Cotton Wings (2) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage done to this Pokémon by attacks. |
| 365 Cynthia's Feebas | Undulate (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 422 Barraskewda | Dive (2) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 484 Petilil | Hide (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 552 Tranquill | Fly (1) | regex | Flip a coin. If tails, this attack does nothing. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 553 Unfezant | Swift Flight (2) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 681 Marshadow | Shadowy Side Kick (1) | regex | If your opponent’s Pokémon is Knocked Out by damage from this attack, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 729 Snom | Hide (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 836 Bronzor | Iron Defense (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage done to this Pokémon by attacks. |
| 878 Hop's Phantump | Splashing Dodge (1) | override | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 908 Noivern | Agility (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 961 Marill | Hide (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |
| 1018 Spewpa | Hide (1) | regex | Flip a coin. If heads, during your opponent’s next turn, prevent all damage from and effects of attacks done to this Pokémon. |

Reviewed negatives include fixed damage reduction, outgoing damage reduction, Weakness
removal, and protection limited by source or damage threshold.

## Numeric `recoil` positives

Values below are raw self-damage HP. Network encoding is `min(value / 70, 1)`.

| Card | Attack | Raw recoil | Method | Exact effect text |
|---|---|---:|---|---|
| 50 Wiglett | Aqua Bomb (2) | 20 | regex | This Pokémon also does 20 damage to itself. |
| 51 Palafin | Vanguard Punch (1) | 10 × counters | dynamic | This Pokémon also does 10 damage to itself for each damage counter on it. |
| 73 Rellor | Slight Intrusion (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 82 Excadrill | Wild Tackle (2) | 50 | regex | This Pokémon also does 50 damage to itself. |
| 85 Beldum | Iron Tackle (2) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 91 Rillaboom | Wood Hammer (2) | 50 | regex | This Pokémon also does 50 damage to itself. |
| 114 Gurdurr | Superpower (2) | 30 | regex | You may do 30 more damage. If you do, this Pokémon also does 30 damage to itself. |
| 166 Klang | Iron Tackle (1) | 20 | regex | This Pokémon also does 20 damage to itself. |
| 179 Black Kyurem ex | Black Frost (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 266 Iono’s Electrode | Thump-Thump Boom (1) | 100 | regex | This Pokémon does 100 damage to itself. Flip a coin. If heads, your opponent’s Active Pokémon is Knocked Out. |
| 285 Pupitar | Take Down (1) | 20 | regex | This Pokémon also does 20 damage to itself. |
| 300 Bagon | Reckless Charge (2) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 304 Hop’s Snorlax | Dynamic Press (1) | 80 | override | This Pokémon also does 80 damage to itself. |
| 315 Azumarill | Double-Edge (1) | 50 | regex | This Pokémon also does 50 damage to itself. |
| 317 Eevee | Reckless Charge (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 328 Pikachu ex | Thunder (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 369 Dondozo ex | Dynamic Dive (2) | 50 | regex | You may do 120 more damage. If you do, this Pokémon also does 50 damage to itself. |
| 384 Arven's Toedscool | Slight Intrusion (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 385 Arven's Toedscruel | Reckless Charge (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 400 Team Rocket's Tarountula | Take Down (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 421 Arrokuda | Reckless Charge (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 469 Team Rocket's Raticate | Reckless Abandon (1) | 90 | regex | Flip 2 coins. If both of them are tails, this Pokémon also does 90 damage to itself. |
| 515 Zekrom ex | Voltage Burst (2) | 30 | regex | This attack does 50 more damage for each Prize card your opponent has taken. This Pokémon also does 30 damage to itself. |
| 543 Escavalier | Wild Lances (1) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 614 Zorua | Take Down (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 645 Marnie's Scrafty | Wild Tackle (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 667 Corphish | Take Down (2) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 674 Hariyama | Wild Press (1) | 70 | override | This Pokémon also does 70 damage to itself. |
| 680 Toxicroak | Reckless Charge (1) | 20 | regex | This Pokémon also does 20 damage to itself. |
| 736 Electrike | Thunder Jolt (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 752 Greavard | Take Down (2) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 794 Reshiram | Burning Flare (2) | 60 | regex | This Pokémon also does 60 damage to itself. |
| 811 Pawmot | Voltaic Fist (1) | 60 | regex | You may have this Pokémon also do 60 damage to itself and make your opponent’s Active Pokémon Paralyzed. |
| 819 Paldean Tauros | Double-Edge (2) | 20 | regex | This Pokémon also does 20 damage to itself. |
| 827 Carvanha | Reckless Charge (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 874 Team Rocket's Exeggutor | Double-Edge (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 885 Pancham | Reckless Charge (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 901 Kingambit | Double-Edged Slash (1) | 50 | regex | This Pokémon also does 50 damage to itself. |
| 909 Erika's Oddish | Reckless Charge (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 920 Tapu Bulu | Wood Hammer (1) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 932 Mega Emboar ex | Crimson Blast (1) | 60 | regex | This Pokémon also does 60 damage to itself. |
| 937 Totodile | Slight Intrusion (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 943 Walrein | Megaton Fall (2) | 50 | regex | This Pokémon also does 50 damage to itself. |
| 973 Groudon | Megaton Fall (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 1002 Zangoose ex | Wild Scissors (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 1008 Larry's Braviary | Brave Bird (2) | 30 | regex | This Pokémon also does 30 damage to itself. |
| 1014 Snivy | Reckless Charge (1) | 10 | regex | This Pokémon also does 10 damage to itself. |
| 1061 Drapion | Hazardous Tail (2) | 70 | regex | This Pokémon also does 70 damage to itself. Your opponent’s Active Pokémon is now Paralyzed and Poisoned. |
| 1069 Rattata | Take Down (1) | 10 | regex | This Pokémon also does 10 damage to itself. |

Reviewed negatives include explicit self-KO, Ability/Tool retaliation, moved existing
counters, and non-damage attack costs. Palafin's variable recoil is evaluated live.

## Regression-diff result

The pre/post full-pool diff contains 86 field changes across 85 cards:

- 26 new `retreat_lock` values; Hop's Trevenant was already overridden.
- 14 new attack `immunity` values; Hop's Phantump was already overridden.
- 46 new numeric `recoil` values; Hop's Snorlax and Hariyama were already overridden.
- Palafin's dynamic recoil is applied during observation generation and therefore does
  not appear in the static tag snapshot diff.
- 0 unrelated tag changes.
- 0 ability changes.
- 0 damage or max-damage changes.

Every changed card in the diff was checked against the exact text above.
