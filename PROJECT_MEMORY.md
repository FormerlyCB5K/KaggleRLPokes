# Project Memory

Last refreshed: 2026-07-22

## Purpose

This repository explores agents for a Pokemon TCG Pocket Kaggle competition. It includes
rules-based agents, evolutionary tuning, supervised value-network work, submission
builders, and a reinforcement-learning policy centered on the Ceruledge deck.

## Current focus

An imitation-learning data/encoding track is now active under
`Imitation-Learning/`. Completed Spec 12
(`Ceruledge-RL/specs/completed/spec-12/12-top-ladder-meta-card-registry.md`)
defines a three-part workflow: extract an exact-card-ID catalog from dated top-ladder
episode archives; exhaustively audit every observed Pokémon, Trainer, and Energy card
against natural text and a user-provided open-source engine; and publish a versioned
semantic registry for a later encoder implementation spec. Exact card ID—not biological
species—is the intended categorical identity. The final tensor layout is explicitly out
of scope for Spec 12.

Spec 12a completed on 2026-07-15. The canonical catalog is
`Imitation-Learning/meta-card-analysis/all-datasets/top_ladder_card_catalog.json`: 15,018
episodes, 30,036 deck instances, 1,802,160 submitted card copies, and 232 exact IDs
(115 Pokémon / 99 Trainer / 18 Energy). There were zero rejected episodes, duplicates,
unresolved IDs, or class errors. Independent root-action verification and repeat-run
artifact hashes passed. See `docs/experiments.md` for commands and hashes.

Spec 12 as a whole completed on 2026-07-15. The canonical implementation handoff is
`Imitation-Learning/meta-card-registry/README.md`; `registry.json` contains every one of
the 232 exact IDs and all 314 effect rows, while `formulas.json` contains all 79 dynamic
calculations and 237 scenarios. The package also includes stratified ID vocabularies,
Python loaders, a 201-card/237-effect override view, schema, provenance, validation, and
deterministic hashes. The final tensor and encoder remain a separate future spec.

The most developed active track is `Ceruledge-RL/`. Its current phase is the multi-agent
opponent pool described by `Ceruledge-RL/specs/09-opponent-pool.md` and split into specs
`09a` through `09e`. The active-spec index is `Ceruledge-RL/specs/README.md`.

The opponent-pool phase covers:

- collision-safe opponent registration/loading and deck resolution;
- side-aware episode dispatch and deck selection;
- weighted per-episode opponent sampling and CLI configuration;
- startup validation and deployment of all required agent folders; and
- per-opponent metrics and plots.

Some related code and tests already exist (`opponents.py`, `test_dispatch.py`, and
`test_pool.py`), so confirm implementation status against each active spec before
assuming a subsection is unfinished or complete.

## Observation encoder track (specs 11/11a/11b/13/13a) — status as of 2026-07-21

Built on top of the completed spec-12 registry above: a generalized (any-deck) Pokémon TCG
observation encoder, replacing the old deck-specific `Ceruledge-RL/features.py` encoder.
Design docs: `Ceruledge-RL/specs/11-pokemon-word-observation-encoding.md` (Pokémon board-slot
word), `11a-pokemon-attribute-tag-vocabulary.md` (Pokémon attack/ability tag vocabulary,
49→50 tags incl. `CONDITIONAL`), `11b-trainer-energy-tag-vocabulary.md` (Trainer/Energy tag
vocabulary, 38→39 content tags, 20 reused from 11a), `13-card-zone-observation-space.md` /
`13a-observation-space-design.md` (zone-word structure, 174-word budget, PAD/UNK masking).
Spec `13b` (implementation) was never written separately — the user chose to go straight to
code and write it retroactively once there's implementation experience; that retroactive
write still hasn't happened.

**Code**: `Imitation-Learning/observation/` (new package this session; no code existed there
before). Key files: `types.py` (locked constants, `TOTAL_WORDS=174` asserted),
`card_data.py` (CSV-sourced printed static fields + per-card move/effect text),
`pokemon_tag_catalog.py` / `pokemon_meta_tags.py` (spec 11a's 49-tag catalog + 201-row meta
lookup table + `tag_unseen_pokemon` regex fallback), `trainer_energy_tag_catalog.py` /
`trainer_energy_meta_tags.py` (spec 11b's 39-tag catalog, 20 reused directly from
`pokemon_tag_catalog.TAG_CATALOG` + `tag_unseen_trainer_energy` fallback), `static_template.py`
/ `trainer_energy_static.py` (per-card static template + tag block, both wired to real data,
not stubs), `stat_bakes.py` (spec 14's 12 locked effect-baking modifiers, now with real
fold/combine functions — `effective_damage`, `damage_dealt_bonus`, `damage_taken_adjustment`,
`effective_weakness` — generalizing `Ceruledge-RL/stat_bakes.py`'s Fire/Fighting-only formula
to all 10 types), `board_context.py` (new: bridges `RawPokemon`/`PokemonStatic` into
`stat_bakes` queries), `live_state.py` (per-Pokemon live fields), `zones.py` (fixed-capacity
padded zone arrays), `encoder.py` (top-level `build_observation(GameState) -> list[Word]`
assembly — real `attack_damage`/`attacks_survivable`/`attack_hits_opponent`, not
placeholders), `test_encoder.py` (24 tests, all passing). No pytest installed — run via
`.venv/Scripts/python.exe -c "import observation.test_encoder as t; ..."` from
`Imitation-Learning/`, calling each `test_*` function directly.

**Full write-ups**: `Imitation-Learning/observation/POKEMON_TAG_TRANSCRIPTION_REPORT.md` and
`TRAINER_ENERGY_TAG_TRANSCRIPTION_REPORT.md` — bugs found+fixed, gaps logged, qualifier
efficacy data, full test logs.

**Locked decisions/gotchas a fresh session must know before touching this package:**
- Card-ID embedding is the *primary* signal for known meta cards (117 Trainer/Energy + 115
  Pokémon); the tag block is a deliberately lossy fallback/warm-start for unseen cards. Per
  explicit user decision, single-instance mechanics (a card whose effect appears on exactly
  one card in the whole ~209-row audited corpus) are left untagged — the card-ID embedding
  absorbs them — rather than growing the tag vocabulary for one-off cases.
- Width history (both collapsed from an original presence-bit + magnitude-scalar pair down
  to one scalar per tag, since no magnitude-bearing tag is ever assigned exactly 0 while
  present): Pokémon tag block 108/117 → 61/70. Trainer/Energy tag block 91 → 53 → 54 (the
  last step from adding `STAT_DEBUFF` as a 20th reused tag).
- `DAMAGE` and `SNIPE` are independent numbers, never mirrored — a "sole redirect" attack
  (entire damage is one freely-targetable hit, e.g. Fezandipiti ex) sets `SNIPE` only,
  `DAMAGE` stays 0; an "additive" attack (a separate bonus hit on top of guaranteed base
  damage, e.g. Darmanitan) sets both independently. Getting this backwards silently makes a
  1-Pokémon-hit row indistinguishable from a 2-Pokémon-hit row — this was a real bug, found
  and fixed this session.
- This whole project's dominant methodology: **re-derive ground truth fresh from
  `meta-card-registry/registry.json` / `EN_Card_Data.csv` each time, never trust a prior
  spec's own prose claim**, even the spec's own "0 recall failures" or "correctly fired"
  claims. This caught several real staleness bugs (a stale 48-vs-49 tag count, a stale
  2-vs-3 `COUNTER_MOVE` count, and — most notably — spec 11b's own Phase 3 spot-check
  claiming `ENERGY_MOVE` already fired correctly on a card where the actual regex,
  transcribed byte-for-byte from the same spec, provably didn't match).
- Qualifier pruning (`distribution`/`conserved`/`self_referential`/`scope`) was
  **explicitly decided against** by the user despite very low/zero usage rates for three of
  the four — do not revisit this without a new explicit request.
- Not every found gap got fixed: `EFFECT_IMMUNE`'s regex is deliberately attack-only (a
  Trainer-card-effect-immunity phrasing on one non-meta card, Antique Sail Fossil, was
  reviewed and left alone rather than conflating two different immunity sources under one
  flag) — a deliberate decision, not an oversight.
- A real, cross-vocabulary bug was found and fixed in the *shared* `pokemon_tag_catalog.py`
  (`COUNTER_PLACE`'s capture-group indexing) while working on the Trainer/Energy side —
  confirms bugs in shared code can hide until the second consumer exercises them; re-run
  *both* vocabularies' full recall/false-positive checks after touching any shared tag.

**Next steps, in priority order** (none started):
1. **The live engine adapter** — nothing in this package is wired to the actual competition
   engine yet. `encoder.GameState`/`live_state.RawPokemon` are hand-constructed everywhere
   (including in every test); a real adapter needs to build these from the engine's own
   `ToJson.h` `Current`/`PokemonJson` output (the shape `Ceruledge-RL/features.py`'s
   `extract_features(obs, ...)` already consumes for the old deck-specific encoder — a
   useful reference for the real `obs` object's shape). `board_context.py`'s
   `tools_suppressed`/`abilities_suppressed_types` detection (currently just two hardcoded
   stadium-ID checks) will also need real engine wiring once ability suppression can vary
   more richly.
2. **Write spec 13b retroactively** now that there's substantial implementation experience,
   per the user's own stated plan (13b was explicitly deferred, never written).
3. **Spec 11's own still-open question**: whether `attacks_survivable`'s opposing-board max
   damage should filter to only attacks the opposing Pokémon can *currently afford* (given
   attached Energy vs. the printed `energy_cost`) or count all printed attacks regardless of
   affordability (currently: the simpler "all attacks count" default, unrevisited).
4. **The recurring "hand-to-bottom-of-deck" gap** — found during a full-corpus recurrence
   check, appears on 3 real cards (Meddling Memo, Energy Swatter, Lucian), distinct from
   every existing tag (`HAND_RESET` shuffles into the deck, `DISCARD_TO_DECK` is
   discard-pile-only). Flagged to the user, not yet decided whether it earns a new tag.
5. Wiring either tag vocabulary into the existing "zone MLP" consumer, or spec 13's future
   per-card zone-word redesign — both explicitly out of scope for every pass so far.

## Ceruledge RL architecture snapshot

- The policy pilots the fixed Ceruledge deck but observes arbitrary opponent decks with
  a generalized opponent Pokemon representation.
- A state contains 23 logical transformer words: 9 friendly board slots, 9 opponent
  board slots, 4 friendly card-zone words, and 1 global word.
- Source widths are 19 friendly features, 75 opponent features, 16 zone features, and
  24 global features. Each is projected to width 64.
- The model is a two-layer, two-head actor-critic transformer with attention pooling and
  19 broad Stage 1 action categories.
- Stage 2 uses dot-product candidate scoring for targets and follow-up selections.
- Important current limitation: PPO directly trains Stage 1 only; Stage 2 target/STOP
  choices do not receive their own policy-gradient objective.
- Checkpoints from the older 16-word layout are incompatible with the current 23-word
  architecture and require a fresh training run.

Full details and accepted limitations are in `Ceruledge-RL/MODEL-ARCHITECTURE.md`.

## Important files

- `Ceruledge-RL/train.py` — PPO training loop and CLI.
- `Ceruledge-RL/model.py` — actor-critic transformer.
- `Ceruledge-RL/features.py` — observation encoding.
- `Ceruledge-RL/actions.py` — action translation and candidate selection.
- `Ceruledge-RL/opponents.py` — opponent registry/loading.
- `Ceruledge-RL/opponent_tags.py` — generalized opponent capability tags.
- `Ceruledge-RL/stat_bakes.py` — effective live stat modifiers.
- `Ceruledge-RL/effect_features.py` — effect extraction/features.
- `Ceruledge-RL/card_data.py` — card data support.
- `Ceruledge-RL/specs/` — current and completed implementation contracts.
- `Ceruledge-RL/old/` — historical/deferred material only.
- `cleanup-baselines/ceruledge-rl-phase0-2026-07-12/` — preserved phase-zero
  baseline artifacts and integrity/test records.

## Other project areas

- `Imitation-Learning/Top-ladder-data/` contains dated ZIP archives of top-ladder
  episode JSON. Preserve the archives; Spec 12a requires streaming them without bulk
  extraction and validating `7-12` before the full-folder run.
- `Ceruledge-Agent/`, `Clefable-Agent/`, and `Alakazam-Agent/` contain rules-based agents.
- `Evo-V2/` contains evolutionary weight tuning and its latest visible output.
- `SupervisedValueNetwork/` contains supervised value-network training work.
- `Lucario-Baseline/` contains a baseline agent.
- `build_submission_*.py` and `Submissions/` contain packaging scripts and artifacts.
- `cg_download/` contains the local game/simulation bindings and native libraries.

## Known cautions

- The worktree was already heavily modified and contained many untracked files when
  this memory was created. Preserve unrelated user work and inspect status before edits.
- Large PDFs, archives, native libraries, submissions, and generated outputs are present.
  Avoid broad scans or rewrites of binary/generated artifacts.
- As of 2026-07-22, `Ceruledge-RL/deck.csv` and `features.FULL_DECK` have identical
  60-card multisets. Keep using current code/spec contracts as the authority if either
  representation changes later.
- Text from some older files may display mojibake depending on console encoding. Do not
  mechanically rewrite those files merely to normalize display encoding.

## Current validation state

Historical completed specs and the phase-zero baseline report passing focused tests and
live smoke checks. A fresh audit on 2026-07-22 ran the focused checks described below;
consult `cleanup-baselines/ceruledge-rl-phase0-2026-07-12/` for the preserved baseline and
continue to run checks appropriate to any new change.

For completed Spec 12, 100 focused tests pass: 11 Part-C registry, 8 Part-B closure, 13
dynamic-formula, 25 Pokémon-audit, 7 Trainer-audit, 8 Energy-audit, 12 inventory, and
16 Part-B source/schema/worklist tests.
The canonical audits cover exactly 115 Pokémon IDs / 205 effects and 99 Trainer IDs /
99 effects, plus exactly 18 Energy IDs / 10 Special Energy effect rows. There are 51
Pokémon, 24 Trainer, and 4 Energy formula keys assigned to B08. Every
recorded-engine evidence pass scanned all 15,018 episodes. On 2026-07-22 the CPU
`.venv` contained PyTorch 2.12.1 and `Ceruledge-RL/test_features.py` passed all 9 focused
checks. The 11 active Spec-12 tests and 89 archived development tests also passed, as did
all 24 standalone observation-encoder tests. Opponent-registry self-tests, a 20-episode
Archaludon smoke run, and a mixed three-opponent pool/resume smoke run passed; the full
live `test_pool.py` and `test_dispatch.py` scripts were not completed because individual
greedy collection episodes can run for minutes and have no built-in move/time cap.

## Next handoff

For the imitation-learning track, Spec 12a is complete. The competition engine is
present at
`Imitation-Learning/ptcg_engine.zip`; the user confirmed it is exactly the engine that
ran the July `1.32.0` games and approved private-project use plus source-trace/
`cg_download` behavior validation. Specs 12b01 through 12b03 completed on 2026-07-15:
the source/binary/database universes align; all 232 meta IDs map with zero semantic text
or identity mismatch; and the frozen audit worklist contains all 314 atomic effects in
12 deterministic class-specific batches. Part-B evidence is under
`Imitation-Learning/meta-card-analysis/part-b/`. B04 completed with an approved
compositional effect-program schema, complete routing coverage for all 314 effects, and
an engine-observation efficiency matrix. B05 is complete: all six frozen Pokémon batches
cover exactly 115 cards / 205 effects, all records validate, and 51 unique formulas are
queued to B08. Each attack-evidence pass scanned all 15,018 games; sparse and absent
executions retain exact source fallbacks. `HR-B05-003` approved exact engine order for
Cursed Blast: self-KO first, then counter placement. `HR-B05-002` remains the sole
approved lossiness exception, and no human-review record is pending. B06 is also
complete: five frozen batches cover exactly 99 Trainer cards/effects (32 Items, 39
Supporters, 11 Pokémon Tools, 17 Stadiums), with 67 static overrides, 24 dynamic
calculations, and 8 verified engine/stat bakes. The unified Trainer evidence scan found
recorded resolutions for 98 of 99 cards; sparse/absent cases retain exact source proof.
B07 is complete: all 8 Basic Energy cards have exact one-type/one-unit ordinary
provision and no additional effects; all 10 Special Energy effects are explicit; all
18 IDs have three recorded attachment traces. B08 is complete: all 79 queued formulas
(51 Pokémon / 24 Trainer / 4 Energy) have declared raw inputs, timing, fallback and
engine evidence, and all 237 executable cases pass deterministically. The exact formula
registry is `Imitation-Learning/meta-card-analysis/part-b/dynamic-formulas.json`.
`HR-B05-002` remains the sole approximation, no human-review item is pending, and no
category changed. B09 is complete: catalog/worklist/crosswalk/ledger/handoff sets match
at exactly 232 cards and 314 effects; all 18 closure checks pass; all 8 closure artifacts
reproduce byte-for-byte. The clean-room Part-C payload is
`Imitation-Learning/meta-card-analysis/part-b/part-c-handoff.json`. Part B has no open
semantic decision. Part C is now complete: the versioned `1.0.0` registry package is
under `Imitation-Learning/meta-card-registry/`, all 20 Part-C acceptance checks pass,
and all 11 package files reproduce byte-for-byte. The package preserves printed attack
cost/damage alongside semantic programs and has no pre-B08 dynamic placeholder text.
The 11 active consumer tests remain at `Imitation-Learning/`; the 89 phased Part A/B
tests run from `Imitation-Learning/archive/spec12-development/run_archived_tests.py`.
Completed Spec 12 documents live under `Ceruledge-RL/specs/completed/spec-12/`. The next
task is a new spec for the full observation layout, masks, trackers, encoder wiring, and
imitation-learning integration—not an extension of Spec 12.
Human-review records remain mandatory for every ambiguity or category change. Do not
design the final observation tensor in Spec 12.

**That "next task" is now well underway** — see "Observation encoder track (specs
11/11a/11b/13/13a)" above for the full current state (as of 2026-07-21): both tag
vocabularies (specs 11a, 11b) are designed *and* transcribed into working, tested code
under `Imitation-Learning/observation/`, spec 13a's zone/word-budget design is locked, and
`encoder.py` produces a real `build_observation(GameState) -> list[Word]` including live
`attack_damage`/`attacks_survivable`/`attack_hits_opponent`. The single biggest remaining
piece before this can run against real games is the live engine adapter (item 1 in that
section's "Next steps") — nothing yet converts the actual engine's `obs` object into the
`GameState`/`RawPokemon` shape this package assumes.

For opponent-pool work, continue to verify specs `09a`-`09e` against current code/tests
before changing their completion state.
