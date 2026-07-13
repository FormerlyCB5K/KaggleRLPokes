# Effect-Baking — Phase 0: Engine-Behavior Probe (findings)

Spec: `specs/completed/07-effect-baking-audit.md` § Phase 0. Probe:
`old/audits/effect-baking/effect_bake_probe.py`
(random-vs-random, 60 games/deck, all in-play Pokémon inspected each observation).

## Result table — what the observation already reflects

| Effect kind | Reflected in observation? | Evidence | Baking rule |
|---|---|---|---|
| **HP Tool** (e.g. Cynthia's Power Weight +70) | **YES** — in `poke.maxHp` (and `poke.hp`) | Probe B: Gible 379 printed 70 → `maxHp=140` in **10,850/10,850** obs | **Never bake tool HP** — the encoder already reads `poke.maxHp`/`poke.hp` |
| Non-HP Tool (Maximum Belt / others) | n/a for HP | Probe A: 790 obs, `maxHp == printed` | — |
| **HP-aura ability/stadium** (e.g. Ludicolo +40) | **NO** (never observed inflating maxHp) | Both probes: **0** tool-free `maxHp > printed` | **Bake** `hp_delta` (to both hp_max and hp_curr) |
| Flat damage-reduction | **NO** — no live field; applied only when an attack resolves | (structural: `Pokemon` has no such field) | **Bake** `damage_taken_delta` |
| Weakness / Resistance | from **static `card_data`**, not the live obs | (encoder reads `cd` weak/resist) | **Bake** overrides freely |
| Retreat cost | from **static `card_data`** — the live `Pokemon` has **no** `retreatCost` field | (api.py `Pokemon` dataclass) | **Bake** `retreat_delta`/`retreat_set` freely |

## Conclusions

1. **Tools never get an `hp_delta` bake** — their HP is already in `poke.maxHp`/`poke.hp`,
   which the encoder consumes. Confirmed empirically (Probe B).
2. **Only ability/stadium HP auras get `hp_delta`** — they are not reflected in the
   observation (0 aura flags across 120 games of real evolving decks).
3. **Damage-reduction, weakness/resistance, and retreat cannot double-count** — they have
   no live observation field (retreat/weak/resist come from static `card_data`;
   damage-reduction is combat-time). Bake them without an observation cross-check.

## Double-count contract

For this frozen engine, `effective_max_hp = observed_maxHp + Σ applicable ability/
stadium hp_delta`, and current HP receives the same delta. Tool HP never enters the
bake table. This exactly follows the probe, including negative HP Stadiums.

There is no sound generic `max(observed, printed + aura)` future-engine safeguard: it
would mishandle negative auras and cannot distinguish an equal-sized HP Tool. If the
engine changes, rerun this probe and change the contract explicitly instead of guessing.

## Limitation

An HP-aura ability (Ludicolo 262, Stage 2) could not be forced into random self-play, so
its *non*-baking into `maxHp` is inferred (0 aura flags across all games) rather than
directly triggered. The probe's tool-free `maxHp > printed` counter remains a canary;
if it fires, the bake contract must be revalidated before training.
