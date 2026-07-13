# 06 — Effect Baking (Tools / Abilities / Stadiums → KO math)

Status: **IMPLEMENTED + full semantic audit complete (2026-07-12); no open review cases**

## Implementation note (for audit)

Built by Claude on 2026-07-12; **for Codex to audit**. Summary:

- `stat_bakes.py` (new): `BAKES` table + Modifier schema + condition-predicate registry
  + `effective_hp / effective_damage / effective_retreat / effective_weak_resist /
  damage_dealt_bonus / damage_taken_reduction / hp_aura`. Self-test passes.
- `features.py` (wired): `_encode_our_pokemon`, `_encode_opp_pokemon`,
  `opp_active_max_damage`, and global `ceruledge_KO` now route through the effective_*
  helpers; a `sb.Board(our_in_play, opp_in_play, stadium_id)` is built per observation
  from `obs.current.stadium`. **No vector-shape change.**
- **Open questions resolved** exactly as written below: weakness/resistance now applied
  in the our-attacker hit-ratios; HP double-count settled by the Phase-0 probe
  (`old/audits/effect-baking/effect_bake_probe.py`, findings
  `old/audits/effect-baking/effect-bakes-phase0.md` — HP Tools ARE
  in observed maxHp so are never baked; only ability/stadium HP auras get `hp_delta`);
  opponent attack-cost modifiers now rewrite the existing attack-cost feature only;
  damage remains capability-based and our-side attack cost remains intentionally unwired.
- **Full pass complete**: 276 unique cards / 277 source rows received a `bake`, `review`,
  or `0` verdict. Final totals are 56 bake / 0 review / 220 zero. See
  `old/audits/effect-baking/effect-bakes-verdicts.tsv` and
  `old/audits/effect-baking/effect-bakes-audit.md`.
- **Regression**: attack/ability tag snapshot diff vs `new-tags-snap-post.json` = 0 cards
  changed (bakes touch no tags / max_damage). `test_features.py::test_effect_bakes`
  exercises damage-reduction + stadium HP aura + retreat tool end-to-end;
  final `smoke_test_encoder.py` run = 481 checks / 10 games clean.
- **Audit hot-spots resolved**: trainer-name predicates were checked against the frozen
  database; Steven's Carbink now requires a Benched source and does not stack; Tool and
  Colorless-Ability suppression are modeled. Twelve non-representable/dynamic cases are
  resolved by user decisions recorded in the audit artifacts.

## Purpose

Fold the **static, KO-relevant effects** of Tool cards, abilities, and Stadium cards
directly into the encoder's **derived combat features**, so the policy never has to
learn KO arithmetic — the "# of hits to KO" features become effect-exact.

This **complements** the existing attack tag blocks (spec 03) and the 11-dim ability
tag block (spec 03). Those keep representing action-relevant effects (draw, search,
gust, etc.). This spec only makes the *derived* stat features aware of effects that
change hit-count math.

**No vector-shape change.** The encoder stays `9×19 / 9×75 / 4×16 / 24` and 23 words.
Only the *computation* of a fixed set of derived features changes. Retrain for behavior,
not shape.

## Scope

### In scope — effect categories folded in

| Category | Folds into | Example wording |
|---|---|---|
| Max-HP change | `hp_max` **and** `hp_curr` (add to both) | "+40 HP to each of your Pokémon" |
| Incoming-damage change (flat) | effective damage in the hit-ratios | "takes 30 less damage from attacks" |
| Weakness add/remove | weak flags + ×2 in hit math | "this Pokémon has no Weakness" |
| Resistance add/remove | resist flags + −30 in hit math | "−30 from … (Resistance)" |
| Outgoing-damage change (flat) | attacker's effective damage → threat | "attacks do 30 more damage" |
| Retreat-cost change | `retreat_cost` | Float Stone (retreat 0) |
| Attack-cost / payability change | existing opponent attack-cost feature only | "attacks cost {C} less" |

### Out of scope (explicitly)

- **Full damage immunity / prevention** ("prevent all damage from attacks") — a
  separate ability flag handled elsewhere; do **not** fold it into the hit-ratios here.
- **Sturdy-style** survive-the-lethal-hit / "HP becomes 10".
- Recurring per-turn **heal** as durability.
- Exotic hard damage-caps.
- Any non-KO **action** effect (draw / search / energy accel / gust) — stays in the
  ability tag block.

Cards outside these categories contribute nothing here.

## Both sides

Effects are folded for **both** the opponent's Pokémon and our own fixed Ceruledge
cards. Our side is a known, tiny card list (hardcodable); the opponent side is the
general case.

## Data model — `stat_bakes.py` (new file)

Hand-authored, keyed by `card_id`:

```python
BAKES: dict[int, dict] = {
    card_id: {
        "kind": "tool" | "ability" | "stadium",
        "mods": [ Modifier, ... ],
    },
}
```

A `Modifier` is a dict:

```python
{
    "stat":      <stat key, see below>,
    "value":     <number>,          # HP/damage/retreat delta, or 1/0 for a flag set
    "scope":     "self" | "your_side" | "opponent_side" | "all",   # default "self"
    "condition": <predicate key or None>,   # applied per candidate Pokémon
}
```

- **Tools** attach to one Pokémon → `scope` is always `"self"` (the holder).
- **Abilities** default `"self"`; use `"your_side"` for team auras
  ("all of your Pokémon take 30 less…"), `"all"` for board-wide auras.
- **Stadiums** are shared; `scope` describes which side/all, and `condition` narrows
  to matching Pokémon (e.g. by type). A stadium mod applies to a candidate Pokémon P
  iff `scope` includes P's side **and** `condition(P)` holds.

### Stat keys (the modifier vocabulary)

| `stat` | Meaning | Value |
|---|---|---|
| `hp_delta` | add to **both** hp_max and hp_curr | raw HP, e.g. `+40` |
| `damage_taken_delta` | flat change to incoming attack damage (before the hit-count) | e.g. `-30` |
| `damage_dealt_delta` | flat change to this Pokémon's own attack damage | e.g. `+30` |
| `weak_fire` / `weak_fighting` | set/clear weakness flag | `1` or `0` |
| `resist_fire` / `resist_fighting` | set/clear resistance flag | `1` or `0` |
| `retreat_delta` | change retreat cost (clip ≥ 0) | e.g. `-2` |
| `retreat_set` | set retreat cost absolutely | e.g. `0` (Float Stone) |
| `attack_cost_delta` | adjust the existing opponent attack-cost feature; never gates damage | e.g. `-1` |

### Condition predicates

A predicate is a pure function of `(holder, attacker, board)` evaluated live. Roles:
when folding into a defender's durability, `holder` = the defender and `attacker` = the
Pokémon hitting it (opponent active for our-side math; our Ceruledge for opp-side math).

Initial predicate set (extend as the audit needs):

- `is_active` — holder is in the Active Spot.
- `full_hp` — holder at full HP (`hp == maxHp`).
- `has_tool` — holder has a Tool attached.
- `attacker_is_fire` / `attacker_is_fighting` — attacker's type.
- `attacker_is_basic` / `attacker_is_evolution` — attacker's stage.
- `attacker_has_rule_box` — attacker is ex / mega ex (our Ceruledge ex qualifies).
- `holder_is_fire` / `holder_is_fighting` / `holder_is_type:{X}` — for stadium type filters.

## How each derived feature consumes the mods

All hit-count math routes through **one** helper:

```
effective_damage(attacker, defender, board) -> int
    d = printed/credible attack damage of `attacker`
    d += Σ damage_dealt_delta mods active on `attacker`
    apply base Weakness (×2) / Resistance (−30) for the attacker's type
        AND any weak_*/resist_* overrides active on `defender`
    d += Σ damage_taken_delta mods active on `defender`   (negative = reduction)
    return max(d, 0)
```

Then the affected features become:

| Feature (current formula) | Effect-aware version |
|---|---|
| our `attacks_survivable` = `hits(hp_curr, opp_max_damage)` | `hits(effective_hp_curr, effective_damage(opp_active → us))` |
| our `attack_hits_opponent` = `hits(opp_hp, our_dmg)` | `hits(effective_opp_hp, effective_damage(us → opp))` |
| our `attack_damage` = `dmg/270` | `(dmg + our damage_dealt_delta)/270` |
| opp `attacks_survivable_vs_ceruledge` = `hits(hp_curr, ceruledge_dmg)` | `hits(effective_hp_curr, effective_damage(us → opp))` |
| opp `hp_max` / `hp_curr` | `+Σ hp_delta` (both) before `/340` and the ratio |
| opp `retreat_cost` = `retreat/4` | apply `retreat_delta` / `retreat_set`, then `/4` |
| opp weak/resist flags (dims 17–20) | apply `weak_*`/`resist_*` overrides |
| global `ceruledge_KO` = `ceruledge_dmg / opp_hp` | `effective_damage(us → opp) / effective_opp_hp` |
| `opp_active_max_damage()` (threat) | add `damage_dealt_delta` (`attack_cost_delta` is **not** wired in v1) |

`effective_hp_curr` / `effective_hp_max` = observed HP `+ Σ hp_delta` mods active on that
Pokémon.

**Attack cost.** Cost modifiers rewrite each existing opponent attack block's normalized
`energy_cost`. They do not gate or zero damage, and `opp_active_max_damage()` remains
payability-blind. Our 19-dimensional Pokemon vector has no attack-cost field, so our-side
cost changes are ignored. In particular, Nighttime Mine's +{C} cost on our Ceruledge ex
needs a future representation decision; it must not be overloaded onto another feature.

### Behavior change (confirmed in review)

Today the hit-ratios do **not** apply base Weakness/Resistance — the model sees the
weak/resist flags separately and must combine them itself. Routing through
`effective_damage` makes the hit-ratios **Weakness/Resistance-aware** (base ×2 / −30 for
Fire/Fighting **plus** baked overrides). This is an intended semantics change to those
features (still no shape change). The weak/resist flag dims stay as raw signals.

## Double-counting rule

Effects the engine **already reflects** in the observation must never be re-baked. The
July-11 handoff notes the engine live-bakes **HP Tools** into `maxHp`/`hp`, but it is
unknown whether it also reflects HP-boosting **abilities/stadiums** or other effect kinds
(damage reduction, weakness changes, retreat).

**Resolution: an empirical Phase-0 probe** (see `07-effect-baking-audit.md`) determines,
per effect kind, exactly what the observation already reflects. Only effects the engine
does **not** apply get a bake. This is a hard precondition before authoring any
`hp_delta` (or other observation-visible) modifier.

## Interfaces / seams

- New module `Ceruledge-RL/stat_bakes.py`: the `BAKES` table, predicate registry,
  and an `effective_stats(poke, board, side)` / `effective_damage(...)` API.
- `features.py` consumes it in `_encode_our_pokemon`, `_encode_opp_pokemon`,
  `opp_active_max_damage`, and the global `ceruledge_KO`. Stadium read live from
  `obs.current.stadium`; per-side in-play lists already available.
- The population workflow, dump script, and regression gate live in
  `07-effect-baking-audit.md`.

## Out of scope

- New raw modifier dims (we fold into derived features only).
- Changing the hit-ratio resolution/clip (`min(hits,4)/4`) — unchanged.
- The full-immunity and Sturdy ability flags (separate work).
- Training / opponent-pool integration.

## Open questions

Resolved during review:

1. **Weakness/Resistance in the hit-ratios** — YES, apply base ×2 / −30 plus baked
   overrides (see "Behavior change (confirmed in review)").
2. **HP double-count** — resolved via the Phase-0 empirical probe; bake only effects the
   engine does not already reflect.
3. **`attack_cost_delta`** — wired to opponent attack-cost features only; damage remains
   capability-based. Our-side cost representation is deferred.

None open.
