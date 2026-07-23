# Independent Audit Report — Kaggle Pokémon TCG Workspace

**Audit date:** 2026-07-22  
**Repository:** `C:\Users\lashm\OneDrive\Desktop\KagglePokesCompetition`  
**Brief:** `AUDIT_MEMO.md`  
**Audience:** Claude or another implementation agent

## Executive result

The memo's substantive observation-vocabulary claims are reproducible. Specs 11a/11b
have exact registry coverage, their only zero-tag row is the documented Mewtwo exception,
all 285 non-structural tag assignments pass recall, and the precision sweep produces
exactly the four documented overlaps.

The main discrepancies are status drift rather than semantic failures. Contrary to the
memo's planning-only description, the 11/13/14 designs have already been transcribed into
standalone code under `Imitation-Learning/observation/`, and all 24 focused encoder tests
pass. The old PyTorch blocker and `deck.csv` warning are also stale.

The wider Ceruledge-RL implementation is locally functional: architecture checks, all 100
Spec-12 tests, nine feature tests, opponent loading, a 20-episode Archaludon smoke, and a
mixed-pool/resume smoke passed. The remaining audit limitation is that the full live
`test_pool.py` and `test_dispatch.py` suites have no episode move/time cap. Individual
greedy games can run for minutes, so those two suites did not complete within bounded audit
runs and must not be represented as freshly green in full.

## Findings requiring follow-up

### P2 — Live episode tests have no deterministic runtime bound

**Evidence**

- `Ceruledge-RL/train.py::collect_episode` uses `while True` and exits only when the engine
  reports a terminal result. There is no maximum turn, selection, or elapsed-time guard.
- `test_pool.py` passed checks 1–4, entered its forced-error live game, then exceeded a
  180-second command bound after absorbing both injected opponent errors.
- `test_dispatch.py` exceeded a 300-second command bound after completing only the two
  `ceruledge_rules` side tests. It had not failed an assertion.
- In contrast, ordinary training smokes completed quickly, including 20 Archaludon games
  in about 20 seconds. The problem is reproducibility of the greedy live-test path, not a
  demonstrated failure of normal stochastic training.

**Impact**

The full success criteria for 09b's every-opponent dispatch and `test_pool.py`'s fallback
case cannot be reliably certified in CI or a bounded audit. A pathological policy/game can
stall a test indefinitely.

**Recommended fix (requires a small policy decision; not applied)**

Add a test-only episode limit or replace the long live-game assertions with deterministic
engine fixtures. If a production `collect_episode` limit is desired too, explicitly define
the limit and the reward/result assigned to a truncated game before implementing it.

**Acceptance criteria**

1. Both scripts terminate within a documented bound.
2. A bound breach produces a clear failure naming opponent, side, turn/selection count,
   and current selection context.
3. The normal training path is unchanged unless truncation semantics are separately
   approved.

### P3 — Active opponent specs lag later registry extensions

`09-opponent-pool.md` and some child-spec wording still describe the original six-member
seed. The current registry contains eight members, adding Archaludon and Garchomp.
Spec 10 documents Archaludon, but no memo-listed addendum explains Garchomp. Runtime code,
deployment notes, and pool validation all include Garchomp.

The concrete test omission was fixed during this audit by adding `garchomp` to
`test_dispatch.py`'s `SEED_ORDER` and `NON_CERULEDGE`. The historical/current wording of
spec 09 was left for Claude to reconcile because deciding whether to rewrite the original
scope or add an extension note is editorial/spec ownership, not a mechanical code fix.

**Acceptance criterion:** the active spec index makes clear that the original six-member
pool was subsequently extended by Spec 10/Archaludon and the intended Garchomp addition.

### P3 — CUDA virtual environment is broken, but the CPU environment is usable

`.venv-cuda/pyvenv.cfg` points to a missing user-local Python 3.12 executable. The normal
`.venv` uses Python 3.14.5 and contains CPU PyTorch 2.12.1, so no dependency installation
was needed and all audited local model tests ran there. Repair `.venv-cuda` only if CUDA
local execution is still intended; it did not block this audit.

## Claim-by-claim verification

### 1. Observation encoding: specs 11/11a/11b

| Claim | Verdict | Fresh evidence |
|---|---|---|
| A — complete, unique coverage | **Verified** | Registry/spec sets match exactly: 201 Pokémon rows and 109 Trainer/Energy rows; zero missing, extra, or duplicate IDs. |
| B — only one zero-tag row | **Verified** | The only empty assignment is `card:431:ability:0`. |
| C — recall | **Verified** | 141 Pokémon + 144 Trainer/Energy = 285 non-structural pairs; zero failures. |
| D — precision | **Verified** | Full 310-row sweep produced exactly four overlaps: `IGNORES_WEAKNESS` and `IGNORES_RESISTANCE` on `card:117:attack:0` and `card:1031:attack:1`. |
| E — qualifier-token trap | **Verified by parser design** | The independent extractor counted only backtick tag tokens at parenthesis depth zero; it found no unknown/invented assignments. |
| Known gaps | **Verified as documented** | 11a contains seven final items; 11b contains five, including its cross-reference to 11a. No listed gap was re-filed as new. |
| Character handling | **Verified** | Patterns were normalized to accept both ASCII apostrophe and U+2019 before matching registry text. |
| Planning-only/no code | **Refuted as current status** | `Imitation-Learning/observation/` contains the encoder/tag/static/live/zone/bake implementation and 24 passing tests. |

One mechanical memo correction was applied: `MULTI_CHOICE`, like `CONDITIONAL`, is
programmatically set and excluded from recall validation. The 11b validation total of 144
already implicitly excluded it. `DAMAGE` is also structural for the audited known-card
path, even though its catalog row contains a text fallback.

### 2. Wider Ceruledge-RL claims

#### Core policy architecture — verified

Code confirms:

- 23 words: 9 friendly board, 9 opponent board, 4 zones, 1 global;
- input widths 19/75/16/24 projected to `D_MODEL=64`;
- two transformer layers and two attention heads;
- attention-weighted pooling;
- 19 Stage-1 actions;
- dot-product Stage-2 candidate scoring with a learned STOP token.

PPO recomputes only Stage-1 log probabilities. Stage-2 targets, follow-up choices, and STOP
do not receive a direct policy-gradient objective. A stale `collect_episode` docstring that
claimed Stage-2 probabilities were folded into `Step.log_prob` was corrected; runtime
behavior was not changed.

#### Opponent pool, specs 09a–09e

| Part | Verdict | Evidence |
|---|---|---|
| 09a registry/loading | **Verified locally** | `opponents.py` self-test passed: five collision-prone `main.py` modules loaded distinctly; all eight decks resolved to 60 integers; casing and cache checks passed. |
| 09b side-aware dispatch | **Implemented; full suite not freshly completed** | Side-aware `battle_start` and dispatch are present. Archaludon and mixed-pool smokes completed. Full `test_dispatch.py` timed out as described above. |
| 09c sampling/CLI | **Verified locally** | Parser accepted valid input and rejected 12 malformed forms; a 10,000-draw 3:1 sample measured ~0.75; a six-episode three-member pool played all three opponents. Mutual-exclusion logic is present in `train.py`. |
| 09d startup/deploy | **Verified locally, cluster not audited** | Happy-path validation passed for all eight members; missing-folder and bad-length diagnostics passed; exact-casing guard passed; deploy notes enumerate all six file-agent folders. No cluster submission was made. |
| 09e metrics/resume | **Verified locally except external wandb delivery** | Mixed run printed reconciled per-opponent counts, saved curves and checkpoint histories, and resumed from update 1 to update 2 with continuous histories. Runs used `--no-wandb`; the namespaced wandb code path was inspected but not sent to the service. |

#### Spec 10 — Archaludon opponent: verified locally

- Registry resolution and 60-card deck validation passed.
- Pool and dispatch code recognize `archaludon`.
- A fresh 20-episode, one-update smoke completed with a separate
  `archaludon=5% (n=20)` row, checkpoint, and plot.

#### Spec 12 — top-ladder registry: verified

- Active registry suite: 11/11 tests passed.
- Archived development suite: 89/89 tests passed.
- Total: 100/100, matching the memo's category breakdown.
- Registry counts are 232 cards, 314 total effects, 79 formulas, and 237 scenarios;
  `validation.json` reports zero issues.

#### Specs 13/13a — design facts verified, status stale and corrected

- The 174-word budget is present in the specs and asserted by
  `Imitation-Learning/observation/types.py`.
- All 24 standalone observation tests passed, including word count, PAD/UNK behavior,
  zone overflow, tag lookup/fallback, damage math, weakness/resistance generalization,
  and bake scoping.
- A real engine adapter and training consumer remain unimplemented, consistent with the
  user's stated integration phase.
- Stale “No code” status lines in specs 11, 13, 13a and the spec index were corrected.

#### Spec 14 — effect-baking audit: verified

The spec and current standalone implementation agree:

- HP is read as engine-resolved and is not baked.
- Resistance is immutable in this engine and is not baked.
- Retreat cost, weakness, attack cost, and flat damage deltas remain bakeable.
- `observation/stat_bakes.py` contains the 12 locked candidates and the expected fold
  functions. Relevant observation tests passed.

#### Other tracks — existence verified only

The memo-listed rules agents, Evo-V2, SupervisedValueNetwork, Lucario-Baseline,
Imitation-Learning, submission scripts/artifacts, and `cg_download` directories exist.
Per the memo, no broader quality or completion status was inferred for them.

### 3. Carried-over cautions

- **Dirty worktree:** confirmed. Numerous modified and untracked files predated this
  audit; no unrelated file was reverted, staged, or committed.
- **`deck.csv`:** the warning is stale today. `Ceruledge-RL/deck.csv` and
  `features.FULL_DECK` are both 60 cards and have identical multisets. Project memory was
  corrected while retaining code/spec contracts as the future authority.
- **Large artifacts:** confirmed, including a ~102 MB ZIP and ~138 MB PDF, plus native and
  submission directories. They were not broadly scanned or rewritten.
- **Mojibake:** observed only in console rendering for some UTF-8 text. Source files were
  read as UTF-8 and were not mechanically normalized.

## Obvious fixes applied

1. Updated the active spec index for completed 11a/11b work and existing standalone code.
2. Updated stale status headers in specs 11, 13, and 13a without changing their designs.
3. Corrected the false Stage-2 probability statement in `train.py`'s docstring.
4. Added Garchomp to the current dispatch test roster.
5. Corrected project memory's PyTorch/test and `deck.csv` cautions; recorded fresh audit
   validation.
6. Corrected `AUDIT_MEMO.md`'s structural-tag recall instructions.

No model behavior, observation schema, vocabulary assignment, bake rule, or training
semantics was changed.

## Commands and outcomes

All Python commands used `.venv\Scripts\python.exe` from the repository unless noted.

- `work/audit_spec11.py` — pass; exact counts and expected four overlaps.
- `Ceruledge-RL/opponents.py` — pass.
- `Ceruledge-RL/test_features.py` — 9/9 pass.
- `Imitation-Learning/test_meta_card_registry.py` — 11/11 pass.
- `python -m unittest discover -s archive/spec12-development/tests` from
  `Imitation-Learning/` — 89/89 pass.
- Direct execution of all callables in `observation.test_encoder` — 24/24 pass.
- `Ceruledge-RL/test_pool.py` — first four checks passed; live fallback case exceeded
  180 seconds.
- `Ceruledge-RL/test_dispatch.py` — `ceruledge_rules` passed both sides; full suite
  exceeded 300 seconds before the next opponent completed.
- 20-episode Archaludon smoke — pass.
- Six-episode `archaludon,garchomp,random` pool smoke — pass; all three sampled.
- Resume smoke to update 2 — pass; aggregate and per-opponent history persisted.

## Proposed next audit areas — approval required before investigation

These were observed as natural follow-ups but were not audited because they are outside
the memo's named claims:

1. Independently compare the new observation implementation field-by-field against specs
   11/13/14, beyond its existing 24 tests.
2. Audit the missing live-engine adapter boundary from engine JSON to
   `observation.encoder.GameState`.
3. Audit whether all Stage-2 selection contexts can be trained correctly and propose a
   policy-gradient design.
4. Review unbounded-game behavior and define test/production truncation semantics.
5. Audit Garchomp's provenance, intended registry status, and missing spec/addendum.
6. Run a cluster deployment/wandb integration audit for 09d/09e.
