# Trainer/Energy Tag Transcription — Report

Deliverable for the plan "Transcribe Spec 11b's Trainer/Energy Tag Vocabulary into Code"
(`C:\Users\lashm\.claude\plans\structured-bouncing-graham.md`), the same 6-stage workflow
used for spec 11a's Pokémon pass
(`Imitation-Learning/observation/POKEMON_TAG_TRANSCRIPTION_REPORT.md`), applied to spec
11b's Trainer/Energy vocabulary.

## What changed

**New code**, all under `Imitation-Learning/observation/`:

- `trainer_energy_tag_catalog.py` — the 38 content tags (19 reused verbatim from
  `pokemon_tag_catalog.TAG_CATALOG` by direct import, no copy; 19 new, transcribed from
  spec 11b's own "Tag catalog additions" table) + `CONDITIONAL` (shared) + 3 new companion
  flags (`MULTI_CHOICE`, `ON_DAMAGED_TRIGGER`, `ON_ATTACH_TRIGGER`). Also
  `tag_unseen_trainer_energy()` — the regex-based fallback for any Trainer/Energy card
  outside the 117-card meta vocabulary.
- `trainer_energy_meta_tags.py` — all 109 Trainer/Energy effect rows (Supporter 39, Item
  32, Pokémon Tool 11, Stadium 17, Special Energy 10), re-derived directly from
  `registry.json`'s own effect text rather than trusted from spec 11b's prose table (which
  was used only as a starting map — matching this project's "re-derive fresh" convention,
  and the exact discipline that caught the Pokemon-side DAMAGE/SNIPE bug).
- `card_data.py` — extended with `get_trainer_energy_text()`, exposing the CSV's
  `Effect Explanation` field for any Trainer/Energy card (needed by Deliverable B for
  non-meta cards).
- `trainer_energy_static.py` — `TrainerEnergyStatic.tag_block` is no longer a zero-stub.
  Known meta card IDs resolve via `trainer_energy_meta_tags.META_TAGS`; everything else
  falls through to `tag_unseen_trainer_energy` run against `card_data.get_trainer_energy_text`.
- `test_encoder.py` — 3 new tests confirming the meta lookup, regex fallback, and the
  8 no-effect Basic Energy cards all produce correct (not silently wrong) values.

## Width correction (91 → 53) — the same class of finding as spec 11a's 108/117 → 61/70

Spec 11b's own Phase 4 section locked "1 presence bit + 1 magnitude scalar per content
tag" (`38×2 + 6 + 1 + 1 + 1 + 6 = 91`) — but that prose predates this session's own
Pokémon-side finding (see `pokemon_meta_tags.py`'s module docstring): across real assigned
data, no magnitude-bearing tag is ever assigned exactly `0` while present, so presence and
magnitude collapse losslessly into one scalar per tag. That collapse already applies to
spec 11a's Pokemon tag block; it applies here too. Re-verified across all 109 real rows
during this transcription (no row assigns a magnitude-bearing tag a literal `0` — the one
row whose true effect *is* an absolute zero, N's Castle's `RETREAT_COST_MOD`, "have no
Retreat Cost," is represented as boolean presence instead, precisely to avoid the
collision). Corrected total: **38 + 6 + 1 + 1 + 1 + 6 = 53** dimensions. Updated in spec
11b's status line and Phase 4 section, and `trainer_energy_static.py`'s
`TAG_BLOCK_WIDTH`.

## Known issues

**Two real regex bugs found and fixed during Stage 3's non-meta spot-check:**

1. **`ENERGY_MOVE`'s regex was too narrow**, missing two real phrasings: N's Plan ("Move
   up to 2 Energy from your Benched Pokemon to your Active Pokemon") and Scramble Switch
   ("move any amount of Energy from the Pokemon you moved to your Bench to the new Active
   Pokemon"). Notably, **spec 11b's own Phase 3 spot-check explicitly claims N's Plan
   "fired the correct tag (ENERGY_MOVE)... with no changes needed"** — a stale/incorrect
   claim, since the actual locked regex (transcribed byte-for-byte from spec 11b's own
   catalog table) does not match that text. Fixed by widening the regex to accept
   "up to N" / "any amount of" quantifiers and the Benched→Active / switch-context
   target phrasings, alongside the two originally-covered shapes (Energy Switch's plain
   own-side move, Handheld Fan's attacker-triggered move). Re-validated clean afterward
   (109/109 recall, 0 false positives).
2. **`COUNTER_PLACE`'s capture group pointed at the wrong alternative** — a bug in the
   *shared* catalog (`pokemon_tag_catalog.py`), found via Perilous Jungle's "put 2 more
   damage counters on" (non-meta Stadium). The old two-group pattern
   (`place (\d+)...|put (\d+)...`, `capture_group=1`) meant group 1 belonged to the
   "place" branch and group 2 to "put" — so `capture_group=1` always read the
   *unpopulated* group whenever the far more common "put" phrasing matched, silently
   falling back to boolean presence instead of the real count. This bug pre-dates the
   Trainer/Energy pass and affects Pokemon's own regex fallback too, though it evidently
   never surfaced during that pass's own spot-check. Fixed by combining both verbs into a
   single capture group (`(?:place|put) (\d+)(?: more)? damage counters? on`), which also
   picks up the "N *more* damage counters" phrasing Perilous Jungle needed. Re-validated
   clean on **both** vocabularies afterward: Pokemon's 201/201 rows (0 recall failures, 0
   false positives) and the full `test_encoder.py` suite (12/12 before this stage, 15/15
   after adding this pass's own tests).

**11 genuine, unretrofitted gaps found during the 49-card non-meta spot-check** (up from
spec 11b's own original 12-card/14-row design-time sample; logged per the no-silent-loss
convention, not retrofitted):

1. **Auto-reattachment from discard** (Boomerang Energy) — "if this card is discarded by
   an effect of an attack..., attach this card from your discard pile to that Pokemon
   after attacking." No tag covers self-recovery-from-discard for an Energy card.
2. **Self-deck-top-discard** (Hole-Digging Shovel, "discard the top 2 cards of your
   deck") — distinct from `MILL` (opponent's deck only). No tag for milling your own deck.
3. **Discard-pile ↔ in-play Pokemon swap** (Ogre's Mask) — no tag covers swapping a
   discard-pile Pokemon with one already in play (plus all its attachments).
4. **Return any own Pokemon + attachments to hand, player's choice** (Scoop Up Cyclone) —
   the Trainer-side analogue of spec 11a's `SELF_RETURN_TO_HAND`, which is Pokemon
   ability-perspective only ("this Pokemon returns itself"). No Trainer-side equivalent.
5. **Discard Energy from your own in-play Pokemon, Trainer-triggered** (Super Potion,
   "discard an Energy from that Pokemon" as a side-effect of healing it) —
   `DISCARD_OPP_BOARD` only covers the opponent's board. No own-side equivalent.
6. **`SEARCH_BENCH` regex-narrowness**: requires an explicit digit (Precious Trolley's
   "search your deck for *any number of* Basic Pokemon" has none) — a regex fix, not a
   vocabulary gap, the same shape as spec 11a's own Scatterbug/Mimikyu finding.
7. **Search-then-discard, not search-then-hand** (Brilliant Blender, "search your deck for
   up to 5 cards and discard them") — no tag for this shape.
8. **Devolution** (Strange Timepiece) — a genuinely new mechanic, no analogue anywhere in
   either vocabulary.
9. **Single targeted opponent-hand card → bottom of their deck** (Energy Swatter) — a
   second, narrower instance of spec 11b's own already-logged Meddling Memo gap (whole
   hand → bottom of deck).
10. **`STAT_DEBUFF` was missing from spec 11b's own locked reused-tag list** (Antique Jaw
    Fossil, "attacks used by your opponent's Active Pokemon do 30 less damage") — the most
    structurally significant finding of the eleven: spec 11a's Pokemon-side `STAT_DEBUFF`
    tag exists for exactly this shape (an attacker-output nerf, not `DAMAGE_REDUCTION`'s
    defender-intake framing) but was never added to 11b's Phase 4 list of 19 reused tags.
    **Fixed** (see "Post-report addition" below) rather than left logged, per the user's
    follow-up request.
11. **`EFFECT_IMMUNE`'s regex is attack-only** (Antique Sail Fossil, "prevent all effects
    of *that card* done to this Pokemon" — a Supporter card's effects, not an attack's).
    Not a simple regex-narrowness fix like the others above: spec 11a's own written
    definition scopes `EFFECT_IMMUNE` to non-damage *attack* effects specifically, so
    widening the regex to also catch "effects of that card" would conflate two genuinely
    different immunity sources (attack-effects vs. Trainer-card-effects) under one flag.
    **Decided (user, 2026-07-21): leave it alone** — Antique Sail Fossil is a single
    instance, same as the other one-off gaps above; the card-ID embedding covers it.

**Already-known gaps reproduced (confirming spec 11b's own Phase 3 findings still hold):**
Team Rocket's Bother-Bot (Prize-card manipulation) and Meddling Memo
(opponent-hand-to-bottom-of-deck) both correctly fire nothing, matching spec 11b's own
logged gaps exactly.

**Documented, harmless false positives (not bugs), confirming spec 11b's own precedent:**
all three "Fossil" Items (Antique Root/Cover/Plume Fossil) fire both `DISCARD_SELF` (via
its intentionally loose "may discard" catch-all) and `SELF_CONSUME` (its own "discard this
card" pattern) on the same "you may discard this card from play" clause — exactly the
overlap spec 11b's own Phase 3 already found and accepted.

## Post-report addition: `STAT_DEBUFF` added as a 20th reused tag (2026-07-21)

Per the user's follow-up request, fixed finding #10 above rather than leaving it logged.
`STAT_DEBUFF` (spec 11a's "reduce opponent's outgoing attack damage" tag) is now imported
into `trainer_energy_tag_catalog.TAG_CATALOG` alongside the other 19 reused tags.
Its shared regex (`pokemon_tag_catalog.py`) needed widening too — the original pattern
only matched Pokemon-ability phrasing ("attacks used by **the Defending Pokemon** do N
less damage," Chikorita's own wording), but Antique Jaw Fossil's Trainer-card phrasing
("attacks used by **your opponent's Active Pokemon** do N less damage") doesn't use that
wording at all, since there's no ability-holder's perspective to phrase it from. Added as
an alternative branch, verified the original Pokemon-side phrasing still matches
unchanged.

**Content tags: 38 → 39, total width: 53 → 54.** Re-validated everything after the change:
- Pokemon's own 201-row recall/false-positive check: still 0/0.
- Trainer/Energy's 109-row recall/false-positive check: still 0/0 (no meta row needed
  `STAT_DEBUFF` — it was purely a non-meta-only gap).
- Re-ran the 49-card sample: Antique Jaw Fossil now fires `STAT_DEBUFF` correctly, and no
  other sampled card picked up a spurious match from the widened regex.
- Full test suite: **16/16 passing** (added `test_stat_debuff_reused_for_trainer_context_phrasing`,
  fixed `test_meta_trainer_tag_block_is_real`'s hardcoded width assertion from 53 to 54).

Updated spec 11b's own Phase 4 locked list and total-width line to include `STAT_DEBUFF`
and the corrected 54-dim total, so the spec and code stay in sync.

## Post-report addition: remaining regex gaps resolved (2026-07-21)

All 4 regex-narrowness findings from Stage 3 are now closed, not just logged:
`ENERGY_MOVE` and `COUNTER_PLACE` were fixed during Stage 3 itself (see "Known issues"
above); `SEARCH_BENCH`'s unquantified "any number of" was fixed in the same post-report
pass as `STAT_DEBUFF` (captures the literal word "any," special-cased to a magnitude of 5
per the user's explicit call, rather than the usual at-cap sentinel). `EFFECT_IMMUNE`'s
card-effect-vs-attack-effect gap was reviewed and **deliberately left alone** (user,
2026-07-21): widening its regex would conflate two genuinely different immunity sources
under one flag for the sake of a single non-meta card (Antique Sail Fossil) — the card-ID
embedding already covers single-instance mechanics like this, per the same standing
decision applied to the other one-off gaps logged above (Boomerang Energy, Ogre's Mask,
Scoop Up Cyclone, Super Potion, Brilliant Blender).

**Qualifier pruning: decided against (user, 2026-07-21) — "carries enough info."** Applies
to both vocabularies; none of the four qualifiers (`distribution`, `conserved`,
`self_referential`, `scope`) are pruned despite the low/zero usage rates in the Stage 5
table below.

## What's next

1. **A live engine adapter** — nothing in this package is wired to the actual competition
   engine yet; everything here assumes the `GameState`/`RawPokemon` input shape. (As of
   2026-07-21 this is also true of the newly-wired `attack_damage`/`attacks_survivable`/
   `attack_hits_opponent` fields — see `observation_encoder_implementation.md`.)
2. Wiring this vocabulary into the existing "zone MLP" consumer or spec 13's future
   zone-word design — explicitly out of scope for this pass, per spec 11b's own Out of
   scope section.

## Qualifier efficacy audit (Stage 5)

Recounted directly from the transcribed data (109 meta rows) and the same 49-card
non-meta sample used for Stage 3, not from spec 11b's own prose claims (which asserted
`self_referential`/`conserved` are unused here — reverified true, not assumed).

| Qualifier | Meta (109 rows) | Non-meta (49 cards) |
|---|---|---|
| `distribution` | 1 (0.9%) | 0 (0%) |
| `conserved` | 0 (0%) | 0 (0%) |
| `self_referential` | 0 (0%) | 0 (0%) |
| `scope` | 28 (25.7%) | 7 (14.3%) |

**Read (decided against pruning — see "Post-report addition" above):**

- `conserved` and `self_referential` are **entirely unused** in this vocabulary, confirming
  spec 11b's own prose exactly: `self_referential` because Trainer-context `SELF_SWITCH`
  never has an "itself" to reference (a Supporter/Item causes the swap, it isn't the
  swapped Pokemon), `conserved` because no currently-tagged row exercises `ENERGY_MOVE`'s
  conserved-redistribution case. Both are kept only for bit-compatibility with the shared
  schema (per spec 11b's own Phase 4 note) — the strongest pruning candidates of the four,
  more clear-cut here than on the Pokemon side.
- `distribution` is even rarer here than on the Pokemon side (0.9% vs. 3.0% meta, 0% vs.
  0% non-meta) — consistent with the user's decision to keep it there for now, but if a
  pruning decision is ever made, this vocabulary provides no counter-evidence.
- `scope` is clearly the load-bearing qualifier here too (25.7% meta, 14.3% non-meta,
  spread across many tags — `STAT_BUFF`, `DAMAGE_IMMUNE_FROM`, `HP_BUFF`,
  `RETREAT_COST_MOD`, `SUPPRESS_TOOLS`, `CONDITION_IMMUNITY`, `EVOLUTION_RULE_MOD`,
  `SUPPRESS_ABILITIES`, `BENCH_CAPACITY_MOD`, `DAMAGE_REDUCTION`, `ATTACK_COST_MOD`,
  `ENERGY_MOVE`) — the clearest case for keeping as-is, matching the Pokemon side's own
  finding.

## Test log

- **Stage 0** — catalog built and verified: 42 total entries (38 content + `CONDITIONAL` +
  3 companion flags), 38 content tags confirmed by direct count against spec 11b's own
  Phase 1 batch tables (not trusted from the Phase 4 prose alone). Width formula
  `38+6+1+1+1+6=53` confirmed by direct arithmetic.
- **Stage 1** — 109/109 rows transcribed, 109/109 card IDs with effect rows covered (the
  remaining 8 of the 117 known IDs are Basic Energy cards with no effect row at all, and
  correctly need no `META_TAGS` entry). 0 wrong-width rows, 0 unintentional all-zero rows.
  One real bug caught and fixed during this stage: `_normalize`'s `magnitude is None`
  branch only returned `1.0` for `family=="boolean"`, silently zeroing N's Castle's
  intentionally-`None` `RETREAT_COST_MOD` presence marker — fixed to return `1.0`
  universally for `None`, matching the exact convention already established on the
  Pokemon side.
- **Stage 2** — full recall + false-positive validation across all 38 content tags (+ 2
  text-detectable companion flags) against all 109 rows' real registry text: **0 recall
  failures, 0 false positives on the first pass** (better than the Pokemon pass's initial
  104 failures, attributable to front-loading that pass's own lessons — uniform
  magnitude-or-presence handling, careful capture-group indexing — from the start).
- **Stage 3** — 49-card non-meta spot-check (proportional across all 5 subtypes, from a
  ~100-row non-meta pool matching spec 11b's own count). Found and fixed 2 real regex bugs
  (`ENERGY_MOVE`, `COUNTER_PLACE` — the latter affecting the *shared* Pokemon-side catalog
  too, re-validated clean on both vocabularies afterward); logged 11 genuine gaps; confirmed
  2 already-known gaps and 1 documented harmless overlap (×3 cards) still reproduce exactly
  as spec 11b's own Phase 3 found.
- **Stage 4** — `trainer_energy_static.py` wired to real data; `card_data.py` extended with
  `get_trainer_energy_text`. 3 new tests added: `test_meta_trainer_tag_block_is_real`
  (Cheren's `DRAW(3)`), `test_non_meta_trainer_uses_regex_fallback` (Love Ball's
  `SEARCH_HAND` via the regex path), `test_basic_energy_has_no_effect_tags` (all-zero,
  not an error, for the 8 no-effect Basic Energy IDs). **Full suite: 15/15 passing**
  (12 from the Pokemon pass + 3 new).
- **Stage 5** — qualifier tallies above; reporting-only stage, no pruning decision made.
