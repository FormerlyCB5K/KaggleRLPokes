# 12a — Top-Ladder Card Inventory

Part A of [`12-top-ladder-meta-card-registry.md`](12-top-ladder-meta-card-registry.md).

Status: **COMPLETE (2026-07-15)**

Implementation/results:

- Analyzer: `Imitation-Learning/analyze_top_ladder_cards.py`
- Independent verifier: `Imitation-Learning/verify_top_ladder_inventory.py`
- Focused tests: `Imitation-Learning/archive/spec12-development/tests/test_top_ladder_cards.py`
  (12 passed; use the archived test runner)
- Pilot artifacts: `Imitation-Learning/meta-card-analysis/7-12-pilot/`
- Canonical full artifacts: `Imitation-Learning/meta-card-analysis/all-datasets/`
- Full result: 15,018 accepted episodes, 30,036 deck instances, 1,802,160 card
  copies, and 232 exact card IDs (115 Pokémon / 99 Trainer / 18 Energy), with zero
  rejected episodes, duplicates, unresolved IDs, or classification errors.
- Both pilot and full outputs passed independent root-action recomputation and
  byte-identical repeat-run hash checks. Exact commands, hashes, and counts are in
  `docs/experiments.md`.

## Purpose

Programmatically extract both submitted decks from every top-ladder episode and produce
a deterministic, stratified catalog of every exact card ID used. Validate the complete
workflow on the `7-12` archive before processing the remaining dated archives.

## Inputs

- Archives below `Imitation-Learning/Top-ladder-data/`, discovered recursively rather
  than hardcoded. At design time these are `7-12`, `7-13`, and `7-14` ZIPs.
- `Decks/Deck-Builder/EN_Card_Data.csv` for name, stage/type, and natural-text metadata.
- The episode JSON schema embedded in each archive. The observed `7-12` archive contains
  5,051 JSON members; this is a pilot validation checkpoint, not a universal constant.

ZIP members must be streamed directly. Do not bulk-extract thousands of episode files
into the worktree.

## Card-class rules

Use the card database's `Stage (Pokémon)/Type (Energy and Trainer)` value:

- `pokemon`: `Basic Pokémon`, `Stage 1 Pokémon`, `Stage 2 Pokémon`;
- `trainer`: `Item`, `Supporter`, `Pokémon Tool`, `Stadium`;
- `energy`: `Basic Energy`, `Special Energy`.

An observed ID missing from the card database, or a new subtype outside these sets, is
retained in an unresolved ledger and blocks successful completion until classified. It
must never be dropped from the union.

## Required implementation

Create a narrow analysis program under `Imitation-Learning/` with importable pure
functions and a CLI. Exact filenames may vary, but the interfaces must separately cover:

1. archive discovery and hashing;
2. one-episode deck extraction;
3. validation and issue recording;
4. card metadata/classification;
5. aggregation and deduplication; and
6. deterministic artifact writing.

The CLI must support selecting one archive/dataset date for the pilot and selecting all
discovered archives for the full run. Inputs and output directory must be explicit or
reported as resolved absolute paths.

## Deck-extraction contract

For each of the two agents, locate the initial submitted deck action rather than
assuming all future datasets use one absolute step index. The accepted value is the
first action for that agent that is a list of exactly 60 integer card IDs and occurs in
the episode's setup/deck-submission phase.

Validation requirements:

- exactly two deck submissions per accepted episode;
- exactly 60 integer IDs per deck, preserving duplicates;
- no Boolean values accepted as integers;
- all IDs positive;
- no later 60-element selection/action may be mistaken for a deck;
- when the episode includes an independent private/visualization copy of the starting
  decks, compare multisets and fail/report any disagreement;
- record the JSON member name, episode ID, agent index, and dataset date as provenance.

Do not infer deck contents from cards drawn or played; the submitted action is the exact
source of truth.

## Duplicate policy

- Use `info.EpisodeId` when present as the primary episode identity.
- Detect the same episode appearing in more than one archive. Keep one copy for global
  frequency totals, but retain every archive/date provenance reference.
- If one episode ID maps to different deck content, record a collision and fail the run.
- If `EpisodeId` is absent, use a documented deterministic fallback derived from the
  episode UUID/member identity and deck content.
- Identical deck lists from genuinely different episode IDs remain separate deck
  instances.

## Aggregates per exact card ID

The canonical catalog must include at least:

- `card_id`, `card_name`, `card_class`, and database subtype;
- dataset dates and source archive(s) where observed;
- unique games containing the card;
- deck instances containing the card;
- total copies across accepted deck instances;
- minimum and maximum copies in a containing deck;
- per-date game/deck/copy counts;
- first/last dataset date;
- whether metadata resolution and classification succeeded.

Keep definitions precise:

- `games_with_card` counts a game once even if both players use the card;
- `decks_with_card` counts each player deck containing at least one copy;
- `total_copies` sums the actual multiplicity in all accepted deck instances.

All card lists are sorted numerically by card ID. Dates and paths use stable ordering.

## Required artifacts

Write to a dedicated generated-artifact directory under `Imitation-Learning/`:

1. a canonical JSON catalog containing all cards and aggregate/provenance metadata;
2. a flat CSV view suitable for manual sorting and review;
3. deterministic ID-only JSON lists stratified as Pokémon, Trainer, and Energy;
4. a run manifest containing script/schema version, input paths/sizes/SHA-256 hashes,
   card-database hash, archive member counts, accepted/rejected/duplicate counts, deck
   and card-copy totals, output hashes, and exact command;
5. a machine-readable issue/rejection ledger, including zero-count categories; and
6. a concise Markdown summary with totals by date, class, and subtype.

Generated outputs must not contain absolute-machine-specific paths when a repo-relative
path suffices. Do not modify the input archives.

## Small-step implementation plan

### A0 — Freeze and inventory inputs

1. Discover ZIPs and calculate path, byte size, SHA-256, and JSON-member count.
2. Hash the English card database and report its unique card-ID count.
3. Record schema samples without writing extracted episode files.

Completion condition: every input has an immutable fingerprint and no archive is
silently omitted.

Validation: repeat discovery twice and assert identical ordered manifests.

### A1 — Implement one-episode extraction

1. Build a minimal synthetic valid episode fixture.
2. Extract two 60-ID decks and provenance.
3. Add malformed fixtures: invalid JSON, one missing deck, 59/61 cards, strings,
   Booleans, non-positive IDs, duplicate candidates, and mismatched redundant sources.

Completion condition: the valid fixture is accepted and every malformed fixture
produces a stable, specific issue code without crashing the archive run.

Validation: focused unit tests cover every issue code and prove card multiplicity is
preserved.

### A2 — Implement classification and aggregation

1. Resolve IDs against the card database and apply the class rules above.
2. Aggregate game/deck/copy counts independently.
3. Implement episode deduplication and collision detection.
4. Emit deterministic in-memory structures before adding file output.

Completion condition: synthetic examples with the same card in both decks, repeated
copies, repeated episodes, and ID collisions produce exact expected totals.

Validation: compare aggregates to a separate simple reference calculation on fixtures;
assert `sum(deck sizes) == 60 × accepted deck instances`.

### A3 — Deterministic artifact writer

1. Write all required JSON/CSV/Markdown artifacts.
2. Write to a temporary location and replace completed artifacts only after the full run
   succeeds, so a failed scan cannot masquerade as current output.
3. Include schema versions and cross-file hashes/references.

Completion condition: two runs over identical fixtures are byte-for-byte identical,
apart from an explicitly isolated runtime timestamp if one is retained.

Validation: hash every deterministic artifact across two runs and compare CSV/JSON card
ID sets for equality.

### A4 — Required `7-12` pilot

1. Run the program only on the `7-12` archive.
2. Confirm the archive member count against independent ZIP enumeration (5,051 at spec
   design time).
3. Reconcile `accepted + rejected/ignored = total JSON members`.
4. Confirm two decks and 120 submitted cards per accepted episode.
5. Independently recompute the unique-ID union and aggregate card-copy total using a
   small one-off/reference path; compare with the program's artifacts.
6. Inspect deterministic samples: first, middle, and last member plus at least ten
   seeded pseudo-random members. Compare extracted decks with raw JSON.
7. Review every issue-ledger entry and every unresolved card ID.

Completion condition: all counts reconcile, the independent union agrees, sample decks
match raw data, and no unexplained rejection or unresolved class remains.

Validation command/result and real counts are recorded in `docs/experiments.md` because
this is a meaningful dataset-analysis run.

### A5 — Full-folder run

Only after A4 passes:

1. Run all ZIPs discovered below `Top-ladder-data`.
2. Re-run all reconciliation, duplicate, classification, and referential-integrity
   checks globally and per archive/date.
3. Compare the full union with the `7-12` union and report added IDs by date/class.
4. Review every new issue and unresolved ID.

Completion condition: every discovered archive is accounted for, the global catalog is
deterministic and internally consistent, and all observed IDs are classified.

Validation: re-run the full scan once and require matching deterministic output hashes;
run focused unit tests again; record exact commands, hashes, counts, and conclusions in
`docs/experiments.md`.

## Part-A acceptance criteria

- The `7-12` pilot passes before any all-archive output is treated as authoritative.
- Every accepted deck has exactly 60 positive integer card IDs.
- Every archive member and any duplicate/collision has an explicit disposition.
- No unknown card or subtype is silently discarded.
- Pokémon/Trainer/Energy ID lists are pairwise disjoint and their union equals the
  canonical catalog ID set.
- Aggregate invariants hold globally and per date.
- Repeated runs are deterministic and output hashes match.
- The run manifest and experiment log contain enough evidence to reproduce the result.

## Out of scope

- Reading natural-language effects or deciding overrides (Part B).
- Encoding biological species or collapsing card variants.
- Defining observation-vector dimensions or normalizations.
- Modifying the current Ceruledge encoder.
