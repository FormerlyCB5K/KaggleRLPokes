# Effect-Baking Full-Database Audit (specs 06 + 07)

Status: **complete; all human-review decisions resolved and implemented**

## Frozen source and coverage

- CSV SHA-256: `A0EA63CF7ADCB65D35436CE0EB390DE6E2E35654A7C67C065A45F4ABAA00F373`
- Source rows: 28 Tool rows, 26 Stadiums, 223 Ability holders = 277 rows.
- Unique cards: 276. Core Memory (1180) occupies two Tool rows (the Tool rule and its attack), which explains the one-row difference.
- Unique-card verdicts: **56 bake / 0 review / 220 zero**.
- Full card-by-card evidence: `effect-bakes-verdicts.tsv` (exact text, verdict, modifiers, and rationale).
- All review decisions are incorporated into this report and the verdict table; the
  empty zero-unresolved review file was discarded.

| Kind | Bake | Review | Zero | Unique total |
|---|---:|---:|---:|---:|
| Tool | 14 | 0 | 13 | 27 |
| Stadium | 9 | 0 | 17 | 26 |
| Ability holder | 33 | 0 | 190 | 223 |
| **Total** | **56** | **0** | **220** | **276** |

## Phase 0: engine behavior

`effect-bakes-phase0.md` records the probe. HP Tools are already present in observed
`maxHp`/`hp`, so they never receive `hp_delta`. Ability/Stadium HP effects, flat damage
modifiers, weakness/resistance overrides, and retreat changes are not exposed as live
observation fields and are baked here.

The current engine assumption is explicit: ability/Stadium HP auras are absent from
observed HP. `effective_hp` adds those auras once. The old prose claiming a general
future-engine `max(observed, printed + aura)` safeguard was removed because that formula
cannot correctly distinguish HP Tools or negative HP Stadiums.

## Implemented behavior

`stat_bakes.py` now contains the complete set of representable, in-scope verdicts found
by the pass. Categories include:

- ability/Stadium HP auras and energy-dependent HP;
- flat and conditional incoming-damage reduction;
- flat, conditional, team, and opposing-side outgoing-damage modifiers;
- weakness/resistance-aware hit math;
- additive and absolute retreat changes;
- dynamic opponent attack-cost feature adjustments (without damage gating);
- Jamming Tower Tool suppression and Team Rocket's Watchtower Colorless-Ability suppression.

Correctness fixes made during audit:

- our-side `attacks_survivable` now uses the same effective Weakness/Resistance and
  damage-reduction path as the other KO features;
- Stone Palace requires its source Carbink to be Benched and does not stack;
- Gravity Gemstone reaches both Active Pokemon;
- `opponent_side` ability auras are gathered from the opposing board;
- absolute no-retreat setters have deterministic precedence over additive modifiers;
- Hop's Choice Band and Sparkling Crystal now retain their holder conditions;
- Board now carries remaining Prize counts for Bloodmoon Ursaluna ex, Kingambit, and
  Counter Gain; Incineroar ex uses live opposing Bench count.
- Feraligatr's +120 and Binding Mochi's +40 are intentionally unconditional per user
  decision; their activation/Poison gates are not modeled.
- Antique Root Fossil and Nighttime Mine adjust opponent costs only. Nighttime Mine's
  effect on our Ceruledge ex remains deliberately unrepresented because our vector has
  no attack-cost field; Charcadet must not receive that increase.

## Resolved review decisions

The user directed Iron Thorns ex, Flutter Mane, Gastrodon, and Lillie's Clefairy ex to
zero/ignore. The remaining eight cases were implemented with the opponent-only cost and
explicit unconditional-damage assumptions above. No human-review cases remain.

Full immunity, Sturdy, probabilistic prevention, recurring healing, damage-counter
triggers, and exotic hard caps remain explicit spec-06/07 exclusions and have zero
verdicts with that rationale in the TSV.

## Regression artifacts

- `effect_bakes_snapshot.py` generates the derived-feature battery.
- `effect-bakes-snap-pre.json` / `effect-bakes-snap-post.json` contain vanilla,
  weakness, reduction, HP-aura, retreat, typed-Stadium, suppression, and negative cases.
- Post battery adds four decision-specific cases and the existing opponent attack-cost
  fields: Bloodmoon dynamic reduction, Watchtower suppression, Nighttime Mine on an
  opposing Tera, and the Charcadet negative case. Existing nonmatching board values are
  unchanged; the new cost values are exactly explained by their applicable modifiers.
- Tag snapshot: `audit_tools.py diff new-tags-snap-post.json bakes-tagcheck-final.json`
  reports **0 cards changed**.
- Tensor shape remains `9x19 / 9x75 / 4x16 / 18`.

## Verification (2026-07-12)

- `effect_features.py`: pass
- `opponent_tags.py`: pass (1267 cards, 631 tagged)
- `stat_bakes.py`: pass
- `test_features.py`: all tests pass
- `smoke_test_encoder.py`: pass, 481 encoder checks across 10 games, no invalid values

The PyTorch suites use the user-level CPU PyTorch runtime; sandbox-only Python does not
see that package.

## Reproduce

From `Ceruledge-RL`:

```text
python old/audits/effect-baking/build_effect_bake_audit.py
python old/audits/effect-baking/effect_bakes_snapshot.py old/audits/effect-baking/effect-bakes-snap-post.json
python old/audits/tagging/audit_tools.py snapshot old/audits/effect-baking/bakes-tagcheck-final.json
python old/audits/tagging/audit_tools.py diff old/audits/tagging/new-tags-snap-post.json old/audits/effect-baking/bakes-tagcheck-final.json
python effect_features.py
python opponent_tags.py
python stat_bakes.py
python test_features.py
python ../smoke_test_encoder.py
```
