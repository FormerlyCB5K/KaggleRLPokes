# 07 — Effect-Baking Full-Database Audit

Status: **COMPLETE (2026-07-12); all human-review decisions resolved**

## Implementation note (for audit)

Done by Claude 2026-07-12 (**for Codex to audit**):
- **Phase 0** complete — `old/audits/effect-baking/effect_bake_probe.py`, findings in
  `old/audits/effect-baking/effect-bakes-phase0.md`.
- **Tooling** built — `old/audits/effect-baking/dump_bakes.py` emits a per-card worklist;
  observed counts: 28 tools / 26 stadiums / 223 ability-holders. The intermediate
  worklist was discarded after the final verdict table was completed.
- **Full semantic pass** complete: 276 unique cards / 277 source rows; 56 bake / 0
  review / 220 zero verdicts in `old/audits/effect-baking/effect-bakes-verdicts.tsv`.
- **Regression** passed (tag snapshot unchanged; unit + live smoke tests green).
- **Regression complete**: required derived snapshots exist, tag diff is zero, unit
  suites pass, and the final live smoke test passed 481 encoder checks across 10 games.

## Purpose

Populate `stat_bakes.py` (defined in `06-effect-baking.md`) by **manually reading every
Tool, every Stadium, and every ability** in the card database and recording the KO-relevant
static modifiers. This is one exhaustive pass, mirroring the Plan-05 audit
(`05-new-attack-tags-full-audit.md`): conservative, fully documented, regression-gated.

The pass must not change unrelated tags, ability blocks, attack blocks, or `max_damage`
values — only add effect-aware behavior to the derived features listed in spec 06.

## Source pool

Read every card whose CSV row is a:

- **Pokémon Tool** (`cardType == TOOL`),
- **Stadium** (`cardType == STADIUM`),
- **Pokémon with an ability** (any Basic/Stage-1/Stage-2 with ≥1 ability row).

Report the actual observed counts at run time (the CSV may change; the current frozen
hash is in `old/audits/tagging/new-tags-progress.md`). Trainer/Energy rows that aren't Tools or
Stadiums are skipped. Abilities are read in full even though most yield **no** modifier.

## Phase 0 — Engine-behavior probe (hard precondition)

Before authoring any modifier, determine empirically which effect kinds the observation
**already reflects**, so nothing is double-counted (spec 06 § Double-counting rule).

In the sim, set up and inspect the observed `maxHp` / `hp` / `retreatCost` / weakness /
resistance for at least:

- an **HP Tool** attached to a Pokémon (expected: already reflected, per handoff);
- an **HP-boosting ability/stadium** aura in play (e.g. "+40 HP to your Pokémon");
- a **flat damage-reduction** ability/tool/stadium (does the observation reduce anything,
  or only the resolved attack?);
- a **weakness/resistance-changing** effect;
- a **retreat-reducing** tool (e.g. Float Stone).

Record, per effect kind, exactly what the observation already applies. **Only bake
effects the engine does NOT already reflect.** This table gates the whole audit.

## Phase 1 — Freeze the baseline

1. Run existing feature/tag tests (`effect_features.py`, `opponent_tags.py`,
   `test_features.py`).
2. Snapshot the **derived features** for a fixed battery of board states (see
   "Regression snapshot" below) — this is the pre-change baseline, distinct from the
   tag snapshot used by Plan 05.
3. Record CSV hash + Tool/Stadium/ability counts.
4. Build three candidate lists via broad text searches (one per major category:
   HP/damage-taken, damage-dealt, weakness/resistance/retreat/cost) as discovery aids
   only — they do not decide final modifiers.

## Phase 2 — Full semantic audit

For every Tool, Stadium, and ability, assign a verdict:

- `0` — no KO-relevant static effect.
- `bake` — one or more modifiers; record them.
- `review` — meaning or board-evaluability is ambiguous.

Every `bake` and `review` entry records:

- card ID + name + kind (tool/ability/stadium);
- exact effect text;
- proposed `mods` (stat, value, scope, condition) per spec 06;
- whether the observation **already reflects** the effect (cross-check the Phase-0 table);
- one-sentence rationale.

Attack-cost modifiers rewrite the existing opponent attack-cost features only. They do
not gate damage; our-side attack-cost changes remain deliberately unrepresented.

Cards with no modifier may be summarized by count, provided each was inspected.

## Phase 3 — Predicates and folding math

1. Add any new condition predicates needed (spec 06 registry) as small pure functions
   with unit tests.
2. Implement `effective_stats` / `effective_damage` in `stat_bakes.py`; wire the derived
   features in `features.py` through it (our/opp Pokémon vectors, `opp_active_max_damage`,
   global `ceruledge_KO`).
3. Each predicate and each stat kind needs at least: one positive, one wording-variant
   positive, and one nearby negative that must NOT trigger.

## Phase 4 — "But no more" regression gate

1. Re-run the derived-feature snapshot battery.
2. Diff pre/post. A permitted change is only a derived feature moving because a **baked
   modifier** legitimately applies on that board state.
3. Any change on a board state with **no** applicable bake fails the gate — investigate.
4. Confirm the tag snapshot (Plan-05 `audit_tools.py snapshot`) is **unchanged**: this
   pass must not alter any attack/ability tag or `max_damage`.
5. Run: `effect_features.py`, `opponent_tags.py`, `test_features.py`, model shape smoke,
   and the live `smoke_test_encoder.py`.

## Regression snapshot (derived-feature battery)

Because bakes change *computed* features (not the tag table), the regression artifact is
a set of **hand-constructed board states** dumped to JSON, each recording the affected
derived features:

- our/opp `hp_max`, `hp_curr`
- our `attacks_survivable`, `attack_hits_opponent`, `attack_damage`
- opp `attacks_survivable_vs_ceruledge`, `retreat_cost`, weak/resist flags
- global `ceruledge_KO`
- `opp_active_max_damage()`

The battery must include, at minimum: a vanilla matchup (no bakes), a fire-weak
opponent, an opponent with a flat damage-reduction ability, an HP-aura ability, a
retreat-reducing tool, and a stadium that filters by type — each in both an "applies"
and a "doesn't apply" (condition false) configuration.

## Required output files

1. `old/audits/effect-baking/effect-bakes-audit.md` — counts; every `bake`/`review` case with text,
   mods, double-count note, rationale; totals by category and by kind.
2. `old/audits/effect-baking/effect-bakes-snap-pre.json` / `-post.json` — derived-feature battery.
3. `stat_bakes.py` populated; updated predicate/folding tests.

## Acceptance criteria

- Every Tool, Stadium, and ability inspected once.
- Every KO-relevant modifier implemented or explicitly in human-review.
- No attack/ability tag, `max_damage`, or vector shape changed.
- Every changed derived-feature value in the pre/post battery is explained by an
  applicable bake.
- All unit and live smoke tests pass.
- Audit artifacts let a later reviewer reproduce each decision.

## Explicitly out of scope

- New tags or new vector dims.
- Full-immunity / Sturdy ability flags (separate work).
- Recurring heal, exotic damage-caps.
- Tracking whether a next-turn effect is currently active (bakes are capability/state
  from the current observation only).
- Training / opponent-pool integration.

## Open questions

None — weakness/resistance, double-counting, and opponent-only attack-cost semantics were
resolved in review. Nighttime Mine's effect on our Ceruledge ex is documented future work.
