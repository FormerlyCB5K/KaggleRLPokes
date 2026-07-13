# Full-Database Opponent-Tag Audit — One Pass

Date: 2026-07-11

## Scope and method

This is a single full-pool review of the current opponent-card encoding. No parser,
schema, or override code was changed. The pass covered all 1,267 card records in
`EN_Card_Data.csv`; 1,056 are Pokémon and therefore part of the normal opponent-board
encoding surface. Those Pokémon contain 1,555 encoded attacks and 221 encoded
abilities. Trainer and Energy rows were checked for edge cases but are normally inert
because opponent zones are not encoded.

The review compared the current `opponent_tags.py` output with independent searches by
effect family, then inspected candidate text. This report deliberately distinguishes:

- high-confidence extraction/override inconsistencies;
- cards that fit an existing tag but need a manual override;
- effects the current schema cannot express;
- systematic damage-estimation limitations.

Card-specific recommendations require human confirmation before implementation.

## A. High-confidence current inconsistencies

| Card | Current issue | Recommended fix |
|---|---|---|
| 386 Cornerstone Mask Ogerpon (non-ex) | Receives an `immunity` ability override but has no ability. | Remove the ability override. Keep immunity on card 117, the ex version. |
| 626 Patrat | Receives a `barrier` override but has no ability text supporting it. | Remove or document the external rule/source that justifies the override. |
| 858 Psyduck | `barrier` is used for an ability that removes self-KO abilities from all Pokémon. This is ability suppression, not bench protection or “rarely worth KOing.” | Remove `barrier`; add/use an `ability_lock` feature only if that effect is important enough for the schema. |
| 97 Litwick, 98 Chandelure, 493 Litwick, 494 Lampent, 495 Chandelure | The deck-out-line overrides mark attacks as `deckout` even when the individual attack searches, deals hand-scaling damage, discards own Energy, or otherwise does not mill. | Make overrides attack-semantic rather than archetype-semantic. Add `deckout` only to the attacks/abilities that actually reduce the opponent's deck. |

Vivillon 1019 is no longer an issue: opponent-only “they draw 4 cards” is correctly
excluded by the current draw parser and covered by a self-test.

## B. High-confidence misses within the existing schema

These effects already have a suitable field. They should be fixed by a conservative
parser extension when wording is broadly reusable, otherwise by a manual override.

### Attack tags

| Field | Cards | Issue | Recommended fix |
|---|---|---|---|
| `counter_snipe` | 56 Flutter Mane; 121 Dragapult ex; 223 Palossand ex; 876 Mismagius | Places counters on opposing Benched Pokémon but is not represented as counter-snipe. Palossand's amount is state-dependent. | Extend target-aware counter placement for the fixed values; use an override/derived estimate for Palossand. |
| `energy_accel` | 845 Smeargle | Coin-gated “attach up to the number of heads” is probabilistic but acceleration magnitude is absent. | Override with an expected or maximum acceleration value; document which convention is used. |
| `discard_energy` | 63 Raging Bolt ex; 790 Mega Charizard X ex | “Discard any amount” cannot be assigned a count by the regex. | Override with a documented practical cap/expected amount; also correct `max_damage`. |
| `probabilistic` | 1076 Furfrou | “Discard random cards” is random but the current `a random` trigger misses this plural/verb form. | Extend the random-effect pattern to `random cards?` with a regression diff. |

### Ability tags

| Field | Cards | Issue | Recommended fix |
|---|---|---|---|
| `energy_active` / `energy_bench` | 86 Metang; 357 Ethan's Ho-Oh ex; 512 Eelektrik; 750 Grumpig; 795 Oricorio ex; 834 Toxtricity; 1009 Larry's Komala | Genuine Energy acceleration is missed because of “any number,” ownership/placement phrasing, “as often as,” or search-and-attach wording. | Add narrowly targeted reusable patterns where safe; override the unbounded “any number” cases. Preserve active-vs-bench destination. |
| `heal` | 238 Whimsicott | “Heal all damage” has no numeric amount and is missed. | Override with a normalized cap or add a separate `full_heal` boolean; do not pretend the amount is always 10. |
| `switch` | 356 Ethan's Magcargo; 788 Charmander | Conditional no-retreat-cost abilities are not tagged as free switching. | Extend the retreat-cost pattern to “it has no Retreat Cost,” retaining the condition only as a coarse signal. |

## C. Protection/immunity candidates for manual classification

The existing `immunity` and `barrier` fields are broad. These cards clearly encode
protection, but the correct field depends on whether the desired meaning is
“hard-to-damage,” “bench-protected,” or “rarely worth KOing.”

| Cards | Effect class | Recommended fix |
|---|---|---|
| 28 Poltchageist; 223 Palossand ex; 362 Misty's Magikarp; 957 Miraidon ex; 979 Koraidon ex | Self is protected while on the Bench. | Prefer `barrier` if it means bench protection; otherwise introduce a distinct `bench_self_protected` flag. |
| 83 Farigiraf ex; 158 Drednaw; 207 Milotic ex; 504 Carracosta | Conditional incoming-damage immunity. | Add `immunity` overrides, accepting that the condition is not represented, or add a conditional-protection bit. |
| 210 Pikachu ex; 886 Mega Hawlucha ex | Sturdy/coin-sturdy survival at 10 HP. | Add `immunity` only if that field intentionally includes one-time survival; a `sturdy` flag is semantically cleaner. |

## D. Opponent maximum-damage estimation is systematically incomplete

`opp_active_max_damage` normally uses the largest printed base-damage number. It does
not evaluate most conditional, scaling, copied, counter-placement, or auto-KO attacks.
This directly corrupts our `attacks_survivable` feature and can make dangerous Pokémon
look harmless.

### Copy-attack cards

Cards 163 Slowking, 293 N's Zoroark ex, 378 Ethan's Sudowoodo, 434 Team Rocket's
Mimikyu, 471 Team Rocket's Persian ex, 615 Zoroark, and 958 Clefable can copy another
attack. A static printed maximum is invalid.

Recommended fix: use a board-derived maximum from the attacks currently eligible to
be copied. Until that exists, add conservative overrides for meta-relevant cards.

### Variable/scaling-damage cards

The following cards contain damage scaling that the printed-base fallback can
understate. This is a candidate list for derived evaluation or manual maximum overrides:

24, 30, 35, 51, 53, 61, 62, 63, 69, 74, 84, 93, 94, 95, 96, 98, 99, 110, 118,
128, 135, 136, 137, 141, 147, 150, 154, 169, 172, 176, 198, 203, 205, 212, 217,
223, 236, 237, 242, 244, 245, 254, 258, 264, 265, 272, 283, 287, 294, 296, 303,
306, 320, 329, 350, 354, 356, 363, 369, 376, 382, 387, 395, 396, 401, 411, 413,
417, 420, 431, 436, 460, 462, 465, 470, 472, 474, 475, 500, 501, 502, 503, 507,
513, 515, 520, 522, 524, 530, 531, 532, 555, 556, 561, 573, 575, 576, 582, 587,
601, 603, 611, 615, 617, 630, 649, 654, 672, 695, 699, 700, 702, 721, 723, 727,
739, 744, 747, 748, 749, 756, 766, 769, 786, 790, 792, 793, 799, 819, 822, 826,
837, 841, 842, 845, 852, 859, 861, 871, 877, 890, 891, 894, 914, 919, 922, 940,
951, 952, 956, 962, 964, 970, 978, 982, 986, 997, 1001, 1006, 1016, 1034, 1035,
1037, 1040, 1041, 1043, 1053, 1059, 1066, 1070, 1072.

Recommended fix: calculate board-realizable damage for common scale variables and
store both printed base and realizable/ceiling damage. Use overrides only for effects
that cannot be evaluated from the observation.

### Conditional bonus/damage-gate cards

The audit found roughly 200 attacks with explicit bonus, failure, or replacement-damage
conditions. `conditional` is override-only today, so most appear as unconditional
vanilla attacks with an understated or misleading damage value.

Recommended fix: populate `conditional` through the manual override pass for
meta-relevant cards. Longer term, derive it generically from well-bounded phrases such
as “If ..., this attack does N more damage,” while keeping condition identity separate
from the boolean.

## E. Important effects that the current schema cannot express

These are not regex bugs. Adding regex without adding a suitable field would mislabel
the cards.

### Gust attacks

Cards 221 Meowstic, 310 Hop's Dubwool, 385 Arven's Toedscruel, 438 Primeape,
508 Cryogonal, 674 Hariyama, and 1039 Clefairy gust through attacks. `gust` exists only
in the ability block.

Recommended fix: add an attack `gust` field or explicitly document that attack-based
gust is ignored.

### Retreat lock

Cards 47, 52, 108, 133, 146, 180, 223, 230, 255, 289, 332, 378, 460, 466, 504,
544, 618, 650, 689, 821, 869, 879, 975, 981, 993, 998, 1008, 1011, and 1012 can
prevent retreat. No attack tag represents this.

Recommended fix: add `retreat_lock`; do not reuse `cubchoo`, which means attacks are
disabled.

### Attack restrictions and locks

Cards 44, 75, 105, 107, 124, 170, 175, 184, 239, 241, 244, 261, 269, 326, 368,
506, 507, 549, 566, 640, 682, 777, 863, 906, 913, 943, 985, 1033, 1067, and 1068
have cooldowns or attack locks. Most self-cooldowns are represented, and full defending-
Pokémon locks sometimes use `cubchoo`, but partial, conditional, or broad locks are
collapsed inconsistently. Cards 232 Slaking ex, 431 Team Rocket's Mewtwo ex, and 463
Team Rocket's Murkrow add ability/partial-attack cases.

Recommended fix: retain `cooldown` for self-cooldown, retain `cubchoo` only for a full
defender attack lock, and add separate `conditional_attack_lock`/`partial_attack_lock`
semantics if these effects matter.

### Ability suppression

Cards 56 Flutter Mane, 858 Psyduck, and 859 Golduck suppress abilities in materially
different ways. There is no ability-lock field.

Recommended fix: add `ability_lock` with a separate condition/scope signal, or ignore
these cards explicitly rather than mapping them to `barrier`.

### Special-condition pressure

Ninety-one cards can directly inflict Asleep, Burned, Confused, Paralyzed, or Poisoned,
but attack/ability tags have no status-infliction field. The affected IDs are:

30, 34, 60, 77, 79, 110, 112, 115, 118, 134, 138, 141, 179, 197, 207, 224, 230,
245, 248, 254, 256, 267, 295, 358, 360, 409, 413, 427, 429, 448, 455, 456, 457,
460, 468, 471, 485, 488, 492, 513, 516, 517, 535, 537, 581, 582, 593, 613, 616,
636, 658, 663, 671, 692, 706, 716, 730, 731, 733, 740, 780, 813, 820, 821, 852,
854, 856, 861, 910, 911, 915, 929, 931, 935, 941, 944, 953, 968, 980, 981, 986,
990, 1009, 1012, 1026, 1032, 1038, 1043, 1060, 1061, 1072.

Recommended fix: add five status-infliction flags or one categorical/multi-hot status
block. A single generic `conditional` or `probabilistic` bit is not enough.

### Hand disruption

Cards 29, 103, 134, 212, 246, 273, 316, 348, 376, 433, 459, 470, 473, 538, 539,
540, 596, 609, 658, 687, 753, 824, 843, 895, 896, 954, 984, 1019, 1024, 1059,
and 1076 disrupt, replace, or randomly remove cards from the opponent's hand. No tag
captures this; importantly, Vivillon 1019 should remain *not* tagged as self-draw.

Recommended fix: add a `hand_disruption` field, optionally with a magnitude. Do not
overload `draw` or `deckout`.

### Opponent Energy denial

Cards 59, 100, 123, 196, 284, 337, 368, 442, 546, 565, 644, 698, 718, 839, 938,
969, and 1022 remove or move opponent Energy. The current `discard_energy` field
conflates this with paying one's own attack cost.

Recommended fix: split `self_energy_cost` from `opponent_energy_denial`. This is more
informative than attempting to refine the existing regex while retaining one field.

### Auto-KO and unusual prize rules

Auto-KO, mutual-KO, “set HP to 10,” and alternate-win effects are not reflected in
`max_damage`. Relevant high-risk cards include 224 Annihilape, 277 N's Sigilyph,
728 Inteleon, 864 N's Vanilluxe, and several self-KO/retaliation Pokémon.

Recommended fix: add `auto_ko`, `mutual_ko`, and `alternate_win` flags where justified;
never encode an auto-KO attack as zero threat merely because printed damage is zero.

## F. Retaliation abilities need one consistent policy

Cards such as 180 Bruxish, 233 Bouffalant, 255 Maractus, 467 Zamazenta, 688 Spiritomb,
896 Mega Scrafty ex, 993 Orthworm ex, and 1027 Turtonator punish attacks with counters,
status, Energy denial, or reflected damage. Current extraction depends on wording
(`put` versus `place`) and is inconsistent.

Recommended fix: add a `retaliation` boolean plus optional damage-equivalent magnitude.
Do not classify these as proactive ability `damage`; that loses the trigger semantics.

## G. In-play Fossil coverage gap

Items 1099 Antique Root Fossil, 1136 Antique Cover Fossil, 1138 Antique Plume Fossil,
1150 Antique Jaw Fossil, and 1151 Antique Sail Fossil can be played as Basic Pokémon.
Because their CSV stage is Item, the static Pokémon registry treats them as neutral
cards. Live HP is still visible, but type/rule/retreat/effect attributes are incomplete.

Recommended fix: create explicit pseudo-Pokémon registry entries for playable Fossils
or detect the engine's in-play Fossil representation and encode their live attributes.

## H. Tool baking is specified but not implemented generically

The opponent vector has `has_tool`, and live `maxHp` incidentally reflects HP changes,
but retreat and other encoded stats are taken from the base Pokémon. Tool effects such
as Rescue Board, Air Balloon, Gravity Gemstone, and conditional damage modifiers are
not baked into those values.

Recommended fix: build a small, audited Tool-effect layer for only the stats already
represented (HP, retreat, damage). Keep all other tools as `has_tool` until a dedicated
tool schema is approved.

## Recommended implementation order

1. Correct the three questionable/invalid existing overrides (386, 626, 858) after
   human confirmation.
2. Apply the manual override list, including copy/variable damage and protection cards.
3. Fix the narrow high-confidence extraction misses in section B with full-pool diffs.
4. Decide which section-E schema gaps belong in the baseline; prioritize max damage,
   retreat/attack locks, status pressure, and Energy denial.
5. Re-run a full-pool audit after the override and schema decisions.

