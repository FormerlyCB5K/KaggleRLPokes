# Pokémon Tag Transcription — Report

Deliverable C for the plan "Transcribe Spec 11a's Pokémon Tag Vocabulary into Code"
(`C:\Users\lashm\.claude\plans\we-can-start-on-quirky-goblet.md`). Covers Stages 0-5:
width sync, the tag catalog, the 201-row meta table (Deliverable A), the regex parser
(Deliverable B), the non-meta spot-check, and the qualifier efficacy audit.

## What changed

**New code**, all under `Imitation-Learning/observation/`:

- `pokemon_tag_catalog.py` — the 49 content tags + `CONDITIONAL`, transcribed from spec
  11a's catalog table: name, magnitude family/cap, regex (apostrophe-normalized),
  capture-group index, applicable qualifiers. Also `tag_unseen_pokemon()` — Deliverable B,
  the regex-based fallback for any Pokémon outside the 115-card meta vocabulary.
- `pokemon_meta_tags.py` — Deliverable A: all 201 attack/ability rows for the 115 meta
  Pokémon, transcribed from spec 11a's manual assignment table (6 batches), each resolved
  to a concrete 70-dim (attack) or 61-dim (ability) vector. Documents its own
  dynamic-magnitude policy (6 rules) for rows whose true value depends on live board state.
- `card_data.py` — extended with `get_card_moves()`, exposing per-move printed
  text/cost/damage for any Pokémon (needed by Deliverable B for non-meta cards; the meta
  cards use the registry instead).
- `static_template.py` — `PokemonStatic.tag_block` is no longer a zero-stub. Known meta
  card IDs resolve via `pokemon_meta_tags.META_TAGS`; everything else falls through to
  `tag_unseen_pokemon` run against `card_data.get_card_moves()`.
- `test_encoder.py` — two new tests (`test_meta_pokemon_tag_block_is_real`,
  `test_non_meta_pokemon_uses_regex_fallback`) confirming the tag block is real for both
  paths, not just correctly shaped.

**Width correction**, propagated everywhere it was referenced: spec 11a's own Phase 4
section had gone stale — it said "48 content tags" and a "108-dimension" total, but a prior
code-review pass had already added `COPY_ATTACK` as the 49th tag without updating that
section's count or formula. Caught during Stage 0 by directly counting the catalog table
rather than trusting the prose. Separately, checking the actual 201-row table found that no
magnitude-bearing tag is ever assigned exactly `0` while present, so the locked
presence-bit + magnitude-scalar pair per tag collapses losslessly into one scalar — confirmed
with the user directly since it changes a width referenced elsewhere. Combined effect:
**108/117 → 61/70** (ability-shaped / attack-shaped rows). Updated in:
`Ceruledge-RL/specs/11-pokemon-word-observation-encoding.md`,
`11a-pokemon-attribute-tag-vocabulary.md` (status line, Phase 4 section, Energy Cost
section), `13a-observation-space-design.md`, and three project-memory files
(`observation_encoder_implementation.md`, `spec11_base_field_schema.md`,
`spec13_card_zone_observation.md`), plus `static_template.py`'s `TAG_BLOCK_WIDTH_ATTACK`/
`_ABILITY` constants.

## Known issues

**Real, unresolved gaps found during the non-meta spot-check** (Stage 3), logged per spec
11a's own no-silent-loss convention — not retrofitted, since Deliverable B is meant to be
"nearly lossless," not lossless:

1. **Discard-to-hand Pokémon retrieval has no tag.** Iron Leaves' "Recovery Net": "Put up to
   2 Pokémon from your discard pile into your hand." `REVIVE_FROM_DISCARD` only covers
   discard→Bench, not discard→hand. A new tag would be needed to cover this cleanly.
2. **`SEARCH_BENCH`'s regex requires an explicit count, but real cards often don't state
   one.** Scatterbug and Mimikyu's "Call for Family": "Search your deck for a Basic Pokémon
   and put it onto your Bench" (no digit — implicitly 1) fails the current `(\d+)\s+Basic`
   pattern. A regex fix (make the count optional, default 1), not a vocabulary gap.
3. **Energy redistribution between Pokémon has no Pokémon-side tag** (Elgyem's "Slight
   Shift": "Move an Energy from 1 of your opponent's Pokémon to another of their Pokémon").
   This reinforces spec 11a's own already-documented known gap #4 (the Forretress-shaped
   gap) — same missing mechanism, now confirmed to recur on a second non-meta card.
4. **No Pokémon-side partial damage-reduction tag family.** Empoleon ex's "Iron Feathers":
   "this Pokémon takes 60 less damage from attacks." `DAMAGE_IMMUNE_FROM` only covers full
   immunity; there's no partial-reduction equivalent on the Pokémon side (spec 11b's
   Trainer/Stadium vocabulary has `DAMAGE_REDUCTION` for exactly this shape — Full Metal
   Lab — but spec 11a's Pokémon vocabulary never got the analogous tag). Arguably the most
   significant of the four, since damage reduction is a common real card pattern.

**Three implementation bugs found and fixed during Stages 2-3** (documented here since they
affected the parser's behavior, not the design):

1. `DAMAGE`'s own documented default case ("or a bare printed damage value with no
   qualifying clause") was never implemented in `tag_unseen_pokemon` — caused 104 of 201
   meta rows to fail recall validation before the fix (traced to one root cause, not 104
   separate phrasing gaps; many attack rows carry a damage number with no prose describing
   it at all).
2. Any tag with `capture_group=None` (8 tags: `SEARCH_ATTACH`, `RNG_SCALING_DAMAGE`,
   `ENERGY_ACCEL`, `SEARCH_HAND`, `DISCARD_SELF`, `RETREAT_COST_MOD`, `DISCARD_OPP`,
   `ENERGY_AMPLIFY`) was silently zeroed on match, indistinguishable from absent — caught by
   Wiglett's clear `SEARCH_HAND` case in the non-meta spot-check.
3. The same root cause recurred even for tags *with* a wired capture group, when a
   different regex alternative matched than the one the group index was written for (e.g.
   `DRAW`'s "draw a card" alternative has no numeric group) — caught by Meditite's "Draw a
   card."

**Documented, harmless false positives (not bugs):** `IGNORES_ACTIVE_EFFECTS` subsuming
`IGNORES_WEAKNESS`/`IGNORES_RESISTANCE` (4 rows, already known from spec 11a's own Phase 2e)
plus one newly-found analogous case: Mega Kangaskhan ex's `DAMAGE` fallback fires alongside
`RNG_SCALING_DAMAGE` because `printed_damage=200` is a real base-damage number, just
redundant with the richer RNG tag.

**A likely-stale count elsewhere in spec 11a**, not corrected (out of this pass's scope,
flagged for whoever next touches that section): the `conserved` qualifier's own prose says
"only 2 of 201 rows use `COUNTER_MOVE` at all" but then names three cards (Munkidori,
Team Rocket's Wobbuffet, Alakazam/Strange Hacking); this transcription's own recount from
the table found 3, matching the named cards, not the stated "2."

**Fourth bug found and fixed post-report (user-caught, not part of the original Stage 2/3
validation passes): `DAMAGE`/`SNIPE` conflation on "sole redirect" attacks.** The original
working design (spec 11a's decision #1) treated `SNIPE` as a modifier that always co-occurs
with `DAMAGE`, sharing one number when the manual table gave only one. This was wrong for
attacks whose *entire* damage is a single freely-targetable hit (no separate base, no
"also") — Fezandipiti ex's "Cruel Arrow" (`card:140:attack:0`, "does 100 damage to 1 of your
opponent's Pokemon") was transcribed as `DAMAGE=100, SNIPE=100`, making it indistinguishable
from N's Darmanitan's "Flamebody Cannon" (`card:258:attack:1`, "also does 90 damage to 1 of
your opponent's Benched Pokemon"), which genuinely hits two Pokemon (90 active + 90 bench)
rather than one. Fixed by redefining the two tags as independent: `DAMAGE` = guaranteed
active damage, `SNIPE` = damage via a bench-eligible redirect; a "sole redirect" clause (no
"also") sets `SNIPE` only, an "additive" clause ("also does N damage to ... Benched
Pokemon") sets both, each with its own number. Audited all 5 meta rows where `SNIPE` fires
(`card:140:attack:0`, `card:258:attack:1`, `card:648:attack:0`, `card:1031:attack:0`,
`card:108:attack:1`) against the registry's raw text — only `card:140:attack:0` needed the
fix; the other 4 were already correct additive shapes. The regex fallback
(`pokemon_tag_catalog.tag_unseen_pokemon`, via the new `_classify_snipe` helper) carries the
equivalent fix for non-meta cards, since the same conflation would otherwise occur on any
future "single free-choice hit" attack. Test added:
`test_sole_redirect_snipe_does_not_also_set_damage`. **12/12 tests passing.**

## What's next

1. **Spec 11b's analogous pass** (Trainer/Energy, 91 dims, 109 rows) — same pattern, not
   started.
2. **A live engine adapter** into `encoder.GameState`/`live_state.RawPokemon` — nothing in
   this package is wired to the actual competition engine yet; everything here assumes that
   input shape.
3. **The qualifier-pruning decision**, informed by Stage 5's data below — genuinely the
   user's call, not decided here.
4. The four logged gaps above, if/when they matter enough to add.
5. `energy_cost`'s own richness (type-blind vs. per-type) was flagged as "cheap to revisit"
   in spec 11 — unaffected by this pass, still open.

## Qualifier efficacy audit (Stage 5)

Recounted directly from the transcribed data (201 meta rows) and a fresh 50-card non-meta
sample (84 attack/ability rows), not from spec 11a's own prose claims.

| Qualifier | Meta (201 rows) | Non-meta (84 rows / 50 cards) |
|---|---|---|
| `distribution` | 6 (3.0%) | 0 (0%) |
| `conserved` | 1 of 3 `COUNTER_MOVE` rows | 0 of 0 `COUNTER_MOVE` rows |
| `self_referential` | 4 rows have `SELF_SWITCH` at all; 3 of those `True` | 1 row has `SELF_SWITCH`; that one `True` |
| `scope` | 21 (10.4%) — self:7, own_bench:2, own_team:4, opponent_named_subset:8, both_sides:0, other:0 | 7 (8.3%) — self:1, own_bench:0, own_team:0, opponent_named_subset:5, both_sides:1, other:0 |

**Read (not a decision — the user's call, per the plan's explicit scope):**

- `distribution` is the weakest of the four by a clear margin: already rare in the curated
  meta sample (3%), and *zero* hits across 84 non-meta rows. The strongest pruning
  candidate. **Decision: keep it for now** (user call, 2026-07-21) — not pruned.
- `conserved` is only ever meaningful alongside `COUNTER_MOVE`, itself rare (3/201 meta,
  0/84 non-meta) — a narrow qualifier riding on a narrow tag. A similarly weak candidate,
  though its marginal cost is also low since it's almost always `0` regardless.
- `self_referential` is rarer in absolute terms but rides on `SELF_SWITCH`, a
  moderately-common tag family — dropping it would lose real (if uncommon) distinguishing
  information (Pecharunt ex's excluded-self case) for a tag that isn't rare itself. Less
  clear-cut than `distribution`/`conserved`.
- `scope` shows the most consistent usage of the four, at a comparable rate in both samples
  (~8-10%), spread across 10 different tags. The clearest case for keeping as-is.

## Test log

- **Stage 0** — width references: found and fixed in 3 specs + 3 memory files + 1 code
  constant. Verified via grep that no stale `108`/`117` reference (outside card IDs and
  intentional historical notes) remained.
- **Stage 1** — 201/201 rows transcribed, 115/115 cards, all vectors at the correct width
  (0 mismatches). Known-gap row (`card:431:ability:0`) verified exactly all-zero (caught and
  fixed one bug here: `self_referential` was defaulting to `1.0` even when `SELF_SWITCH`
  wasn't present at all). `DAMAGE`-vs-`registry.damage_profile.printed_base` parity check:
  127 `DAMAGE`-tagged attack rows checked, 2 flagged discrepancies, both resolved on manual
  inspection as correct (not bugs) — see the module's own docstring for the Fezandipiti
  ex / Team Rocket's Mewtwo ex detail.
- **Stage 2** — full recall + false-positive validation across all 48 (+`CONDITIONAL`) tags
  against all 201 rows' registry text. First pass: 104 recall failures (root-caused to one
  systemic gap, fixed), 4 false positives (documented `IGNORES_ACTIVE_EFFECTS` exception).
  Final clean pass: **0 recall failures, 5 false positives** (the original 4, plus one newly
  found and equally harmless — Mega Kangaskhan ex's `DAMAGE`/`RNG_SCALING_DAMAGE`
  co-detection).
- **Stage 3** — 50-card non-meta spot-check (increased from the originally-planned ~12).
  Found and fixed 2 more systemic bugs (see "Known issues" above); logged 4 genuine,
  unretrofitted gaps.
- **Stage 4** — existing `test_encoder.py` suite (9 tests) stayed green throughout every
  stage above. 2 new tests added, both passing: `test_meta_pokemon_tag_block_is_real`
  (Alakazam's ability-row `DRAW` magnitude), `test_non_meta_pokemon_uses_regex_fallback`
  (Croconaw's `SELF_SWITCH` via the regex path). **Final suite: 11/11 passing.**
- **Stage 5** — qualifier tallies above; no test assertions, a reporting-only stage per the
  plan.
