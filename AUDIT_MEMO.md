# Audit Memo — Kaggle Pokémon TCG Workspace

**Purpose.** This memo is written for an independent agent (a different coding assistant,
with no access to the conversation that produced this work) to audit the current state of
this repository against what is claimed to be true. It makes concrete, checkable claims —
not narrative — and separates claims by confidence level: **Verified** means an agent in
this session directly re-derived the claim from source data in the same sitting it's being
reported; **Claimed** means it's asserted in a spec file or memory document but has not been
independently re-checked recently, and the auditor should treat it as a hypothesis to test,
not a fact.

Do not trust any status line inside a spec file at face value — several were found stale
during this session's own audit (see §1.5). Re-derive from source data wherever a
verification method is given below.

**Repository root:** `C:\Users\lashm\OneDrive\Desktop\KagglePokesCompetition` (Windows;
also referred to below with forward-slash relative paths).

**Git state as of this memo:** nothing in this memo's scope has been committed. `git status`
shows the spec files below as untracked/modified working-tree changes only. Do not assume
CI, a merge, or a review has happened — none has.

---

## 1. Observation-encoding track (specs 11 / 11a / 11b) — VERIFIED, highest confidence

This is the most recently and most rigorously checked part of the repository. It's a
**planning artifact, not code**: three markdown files that together define a tag vocabulary
for encoding Pokémon/Trainer/Energy card effects into a fixed-width observation vector for
an RL policy. No parser or encoder implementation exists yet — that's explicitly out of
scope for these specs.

### 1.1 Files and their relationship

- `Ceruledge-RL/specs/11-pokemon-word-observation-encoding.md` — overview/architecture,
  no tag data.
- `Ceruledge-RL/specs/11a-pokemon-attribute-tag-vocabulary.md` — Pokémon attack/ability tag
  vocabulary. 201 audited rows (115 Pokémon cards, `class == "pokemon"` in the registry).
- `Ceruledge-RL/specs/11b-trainer-energy-tag-vocabulary.md` — Trainer/Energy tag vocabulary.
  109 audited rows (117 cards, `class in ("trainer", "energy")`).
- Ground truth for both: `Imitation-Learning/meta-card-registry/registry.json`. This file
  (not the spec's prose, not English card text) is the authority for what each card
  actually does. It has an `effect_id` per attack/ability/effect row
  (`card:<id>:attack:<n>`, `card:<id>:ability:<n>`, `card:<id>:trainer_effect:<n>`,
  `card:<id>:energy_effect:<n>`).
- Secondary source for spot-checking generalization: `Decks/Deck-Builder/EN_Card_Data.csv`
  (one row per move/ability, `Card ID` column, includes ~2000 cards outside the 232-card
  audited "meta" set).

### 1.2 Claims that should hold, and how to check them

**Claim A — Coverage.** Every attack/ability row for the 115 audited Pokémon cards has
exactly one entry in 11a's manual assignment tables, and every effect row for the 117
audited Trainer/Energy cards has exactly one entry in 11b's. No row is missing, duplicated,
or references a card ID outside the registry.

*Verify:* parse `registry.json`, collect all `effect_id` values under
`identity.class == "pokemon"` (should be 201) and under `identity.class in ("trainer",
"energy")` (should be 109). Parse the markdown assignment tables in 11a/11b (rows of the
form `| Card Name | \`effect_id\` | tags |`) and diff the `effect_id` sets against the
registry's. Expect an exact match both directions, and no duplicate `effect_id` within
either file.

**Claim B — Zero unintended all-zero rows.** Every row has at least one tag, with exactly
one documented exception: `card:431:ability:0` (Team Rocket's Mewtwo ex) is deliberately
untagged — its entire text is an attack-legality gate ("can't attack unless you have 4+
Team Rocket's Pokémon in play"), not a separate effect, per a documented design decision
(11a, "Working design decisions," #2). Any *other* zero-tag row is a bug.

*Verify:* from the same parse as Claim A, check every row's tag list is non-empty except
that one `effect_id`.

**Claim C — Recall.** Every tag's detection regex, run against the English text of every
row that spec assigns it to, matches. 285 tag-assignment pairs total across both files (141
in 11a excluding structural flags, 144 in 11b).

*Verify:* parse the tag catalog tables (11a has one table; 11b's is titled "Tag catalog
additions" and only lists tags *new* to 11b — tags reused from 11a are not re-listed and
must be pulled from 11a's table). Each catalog row has a `` `/pattern/i` `` detection rule
in its 3rd column. **Two parsing traps found and fixed during the last audit, worth
re-checking**: (1) some cells contain more than one backtick-delimited `/…/i` span (e.g.
`SELF_SWITCH` has a "self-referential" and a "free-choice" alternative) — these must be
OR'd together, not just the first one taken; (2) markdown table cells escape `|` as `\|`
in most rows, but not universally — a parser that naively splits on unescaped `|` without
being backtick-aware will mis-split rows whose regex uses a literal, un-escaped `(?:a|b)`
inside a code span. Three structural companion tags are excluded from recall validation:
`DAMAGE`, `CONDITIONAL`, and 11b's `MULTI_CHOICE`. `DAMAGE` fires on any row with a printed
damage value present (11a's catalog includes a prose/regex fallback, but the audited
known-card path is set from the printed field). `CONDITIONAL` is set from the registry's
`conditional`-node presence, and `MULTI_CHOICE` from its top-level `choice` node presence;
neither is text-derived for known cards. Skip all three when reproducing the stated
141+144=285 recall-pair total.

**Claim D — Precision.** Running every tag's regex against the *full* 310-row corpus (not
just its own assigned rows) produces no unintended matches, except exactly 4 documented
ones: `IGNORES_WEAKNESS` and `IGNORES_RESISTANCE` each fire once extra on `card:117:attack:0`
and `card:1031:attack:1`, because those two rows' text literally contains "Weakness or
Resistance" as a sub-phrase of the broader `IGNORES_ACTIVE_EFFECTS` phrasing that's the tag
actually assigned there. This is disclosed in 11a's "Phase 2e" section as an accepted,
harmless redundancy (the manual table intentionally tags only the broadest applicable tag;
the narrower regex still correctly recognizes its own phrase is present in the text). Any
*other* false positive is a bug.

*Verify:* for each catalog tag, run its regex against every row's text where that row is
*not* in the tag's assigned set; expect zero hits outside the 4 named above.

**Claim E — Card-name-token traps.** A tag name mentioned inside a row's *qualifier prose*
(e.g. "...no separate `HP_DEBUFF` tag minted for one instance" or "...not formalized as a
companion flag the way `ON_DAMAGED_TRIGGER` was") is not an actual assignment. A naive
regex extraction of "any backtick-wrapped ALL-CAPS token in the tags cell" will produce
false assignment records. A correct parser must only count a tag token when it appears at
paren-depth 0 in the cell (not nested inside a `(...)` qualifier block).

*Verify:* if you write your own extractor, sanity-check it doesn't invent assignments —
cross-reference a few rows by eye against the rendered table.

### 1.3 Encoding-specific notes (character set, not logic)

Real Pokémon TCG card text uses the Unicode right single quotation mark (`’`, U+2019)
exclusively for contractions ("isn’t," "can’t"), never the ASCII apostrophe (`'`). Every
regex referencing a contraction must match a character class covering both
(`['’]`) or the file's convention of writing `'?` (optional ASCII apostrophe) is silently
broken against all real card text. This was found and fixed once already (11a "Phase 2e");
if any *new* regex is added later without this in mind, it will look correct against
hand-typed test strings and fail against real data.

### 1.4 Known, deliberately-accepted gaps — do not re-report these as bugs

Both files carry an explicit "known gaps" section. As of this memo:

- 11a: 7 items (see "Known gaps — final sign-off list"), including `card:431:ability:0`'s
  deliberate all-zero row (Claim B above), 3 mechanics with zero coverage because they
  never appear in the 115-card audited sample (opponent-board discard, spread/AOE damage,
  own-side Energy redistribution — found via non-meta spot-checking, *not* retrofitted by
  design), a residual approximation on the shared `scope` qualifier (drops a finer
  attacker-restriction detail on 2 of 201 rows), one untranslated-source-text row in the
  non-meta CSV (data quality, not a vocabulary gap), and the inherited RNG-truncation
  approximation on Mega Kangaskhan ex from an upstream spec (12).
- 11b: its own 5-item list, cross-referencing 11a's.

If an audit surfaces one of these again, it is not new information — check the "Known
gaps" sections before reporting.

### 1.5 Known stale cross-reference — real, unfixed as of this memo

`Ceruledge-RL/specs/README.md` (the spec index) still describes 11a and 11b as "review
plan[s]... not yet run" as of this memo's writing. That is false — both are complete
through Phase 4, and both were independently re-audited and had their detection rules
fixed (12 in 11a, 5 in 11b) as of a `/code-review` pass in the same session that produced
this memo. **This index file needs a one-line update per spec; it has not been done yet.**
Flag it, or fix it — either is reasonable, but don't treat the README as authoritative
over the spec files themselves for these two entries.

### 1.6 Suggested re-audit method (reusable)

The verification approach used in this session, condensed: (1) load `registry.json`,
build `effect_id → text` maps for both card-class groups; (2) parse each spec file's
catalog table into `tag → regex` (backtick-aware cell splitting, join multi-span rules
with `|`); (3) parse each assignment table into `effect_id → [tags]` (paren-depth-aware,
so qualifier prose doesn't get misread as assignments); (4) cross-check coverage
(Claim A/B); (5) for recall, `re.search(pattern, text, re.IGNORECASE)` for every
`(tag, effect_id)` pair from the assignment table, normalizing apostrophes to a
`['’]` class first; (6) for precision, run every tag's regex against every row's text
where the row isn't in that tag's assigned set. A clean run should print exactly the 4
named false positives in §1.2 Claim D and nothing else.

---

## 2. Wider Ceruledge-RL project — CLAIMED, not re-verified this session

Everything in this section is sourced from `PROJECT_MEMORY.md` and prior spec files, not
independently re-checked in the session that produced §1. Treat every bullet as something
to verify, not something to trust.

- **Core policy**: `Ceruledge-RL/` implements a PPO actor-critic transformer piloting a
  fixed Ceruledge deck, observing a 23-word state (9 friendly board, 9 opponent board, 4
  friendly zone, 1 global), each word projected to width 64. Two-layer, two-head,
  attention-pooled. 19 Stage-1 action categories; Stage-2 uses dot-product candidate
  scoring. **Known limitation, claimed accepted**: PPO trains Stage 1 only — Stage 2
  target/STOP choices have no policy-gradient objective of their own. Full detail
  claimed to live in `Ceruledge-RL/MODEL-ARCHITECTURE.md` (currently showing as modified
  in git, not diffed as part of this memo).
- **Opponent pool** (specs `09`, `09a`–`09e`): claimed "current phase," broken into 5
  independently-buildable parts (registry/loading, side-aware dispatch, weighted sampling,
  startup validation/deploy, per-opponent metrics). `opponents.py`, `test_dispatch.py`,
  `test_pool.py` claimed to exist with some coverage already. **Verify current
  implementation status against each `09x` spec's own success criteria before assuming
  any sub-part is finished or unfinished** — PROJECT_MEMORY.md explicitly warns not to
  assume.
- **Spec 10** (Archaludon opponent): claimed fully implemented and green (self-test, pool,
  dispatch, smoke train) as of 2026-07-15.
- **Spec 12** (top-ladder meta-card registry): claimed complete. Produced
  `Imitation-Learning/meta-card-registry/registry.json` — the same file §1 treats as
  ground truth — plus `formulas.json`, provenance/validation artifacts, and 100 claimed
  passing focused tests (11 Part-C, 8 Part-B closure, 13 dynamic-formula, 25
  Pokémon-audit, 7 Trainer-audit, 8 Energy-audit, 12 inventory, 16 Part-B misc). One
  specific caveat already on record: `Ceruledge-RL/test_features.py` could not be run in
  the environment that wrote PROJECT_MEMORY.md because PyTorch wasn't installed there —
  check whether that's still true in the auditor's environment before assuming test
  status either way.
- **Spec 13 / 13a** (card-zone observation space): claimed "design phase," a 174-word
  budget claimed "locked 2026-07-16." Builds on spec 11's Pokémon word (§1) — internally
  consistent with §1's own note that it explicitly defers zone-word design to spec 13.
- **Spec 14** (effect-baking audit): claimed complete — HP and resistance need no baking
  (engine resolves HP directly; resistance is immutable in this engine), retreat cost/
  weakness/attack-cost/flat-damage deltas still do.
- **Other agent tracks**, claimed to exist with no recent status attached in memory:
  `Ceruledge-Agent/`, `Clefable-Agent/`, `Alakazam-Agent/` (rules-based agents),
  `Evo-V2/` (evolutionary weight tuning), `SupervisedValueNetwork/`, `Lucario-Baseline/`,
  `Imitation-Learning/` (the imitation-learning track that spec 11/12 belong to), plus
  submission-packaging scripts (`build_submission_*.py`, `Submissions/`) and
  `cg_download/` (native game engine bindings). None of these were opened or checked in
  the session that produced this memo.

## 3. Cautions carried over from prior memory, still worth re-checking

- The working tree has untracked and modified files beyond what's described here (see
  `git status` for the live list) — this predates the session that wrote §1 and wasn't
  produced by it. Don't assume everything untracked is new/abandoned work; several are
  files this memo's own session edited (the 3 spec 11 files, `specs/README.md`) or that
  were already in that state at session start (`MODEL-ARCHITECTURE.md`, `actions.py`,
  `features.py`, `model.py`, `opponent_tags.py`, `opponents.py`,
  `submit-batch-ceruledge-ppo.sh`, `test_dispatch.py`, `test_features.py`, `test_pool.py`,
  `docs/experiments.md`).
- `Ceruledge-RL/deck.csv` is on record as outdated for some architecture-level deck
  counts — prefer current code/spec contracts as authoritative over that file.
- Large binaries/archives/native libraries are present in the repo (`cg_download/`,
  submission artifacts, etc.) — avoid broad scans or rewrites of those paths; they aren't
  meant to be human/agent-edited.
- Mojibake may appear in some older files depending on console encoding; this is a
  display artifact of those specific files, not something to "fix" by rewriting them.

---

## 4. What this memo is *not*

This is not a claim that the whole repository is in a good state — only §1 has been
freshly, mechanically re-verified. Sections 2–3 are handed to the auditor specifically
*because* they need independent checking, not because they're assumed fine. If the
auditor's time is limited, §1 (with its exact verification method in §1.6) is the
highest-confidence, cheapest-to-mechanically-check section and the best place to start;
§2's bullets each require actually opening and running something before they can be
marked verified or refuted.
