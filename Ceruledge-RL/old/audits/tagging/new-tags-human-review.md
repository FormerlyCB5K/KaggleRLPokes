# Plan 05 — Human Review (Resolved)

All seven cases were resolved by the user on 2026-07-11. No Plan-05 decisions remain
open.

## Narrow or threshold immunity

| Card | Attack | Exact text | Resolution |
|---|---|---|---|
| 176 Terapagos ex | Crown Opal (attack 2) | During your opponent’s next turn, prevent all damage done to this Pokémon by attacks from Basic non-{C} Pokémon. | Intentionally untagged for the Ceruledge baseline. |
| 253 Metapod | Harden (attack 1) | During your opponent’s next turn, prevent all damage done to this Pokémon by attacks if that damage is 60 or less. | Intentionally untagged for the Ceruledge baseline. |
| 599 Roggenrola | Harden (attack 1) | During your opponent’s next turn, prevent all damage done to this Pokémon by attacks if that damage is 40 or less. | Intentionally untagged for the Ceruledge baseline. |
| 737 Mega Manectric ex | Flash Ray (attack 1) | During your opponent’s next turn, prevent all damage done to this Pokémon by attacks from Basic Pokémon. | Intentionally untagged for the Ceruledge baseline. |
| 840 Archaludon | Coated Attack (attack 1) | During your opponent’s next turn, prevent all damage done to this Pokémon by attacks from Basic Pokémon. | Intentionally untagged for the Ceruledge baseline. |
| 921 Dipplin | Coated Attack (attack 1) | During your opponent’s next turn, prevent all damage done to this Pokémon by attacks from Basic Pokémon. | Intentionally untagged for the Ceruledge baseline. |

## Variable recoil

| Card | Attack | Exact text | Resolution |
|---|---|---|---|
| 51 Palafin | Vanguard Punch (attack 1) | This Pokémon also does 10 damage to itself for each damage counter on it. | Implemented dynamically as `10 × current damage counters`, then normalized by `/70`. |
