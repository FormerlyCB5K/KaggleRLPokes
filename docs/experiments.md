# Experiment Log

Use this file as the durable, append-only index of meaningful training and evaluation
runs. Detailed machine-generated logs and checkpoints should remain in their own output
directories; link or name them here.

## Entry template

### YYYY-MM-DD — Short run name

- Status: proposed | running | completed | failed
- Goal:
- Code/version or checkpoint:
- Opponent or opponent pool:
- Command/configuration:
- Random seed:
- Output location:
- Metrics:
- Validation/artifacts:
- Conclusion:
- Follow-up:

## Recorded runs

### 2026-07-15 — Spec 12a `7-12` top-ladder inventory pilot

- Status: completed
- Goal: Validate exact two-deck extraction, card classification, aggregation, and
  deterministic artifact generation on the required `7-12` pilot archive.
- Code/version: `Imitation-Learning/analyze_top_ladder_cards.py` schema 1 / script 1.0.0;
  `Imitation-Learning/verify_top_ladder_inventory.py` independent root-action verifier.
- Input: `Imitation-Learning/Top-ladder-data/7-12/pokemon-tcg-ai-battle-episodes-2026-07-12.zip`
  (736,685,052 bytes; SHA-256
  `fba2cc8fd028109ab038dda9b2aca09bd1323cf40200cd2797d66c351fc67646`).
- Commands:
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/analyze_top_ladder_cards.py --archive Imitation-Learning/Top-ladder-data/7-12/pokemon-tcg-ai-battle-episodes-2026-07-12.zip --output-dir Imitation-Learning/meta-card-analysis/7-12-pilot`
  - `python Imitation-Learning/verify_top_ladder_inventory.py --archive Imitation-Learning/Top-ladder-data/7-12/pokemon-tcg-ai-battle-episodes-2026-07-12.zip --output-dir Imitation-Learning/meta-card-analysis/7-12-pilot`
  - repeated the analyzer command and compared SHA-256 for every output file.
- Output: `Imitation-Learning/meta-card-analysis/7-12-pilot/`; manifest SHA-256
  `341a2435890144586f22e4f08b9645b423358d2ef54bf7a98d098cea3bf749db`.
- Results: 5,051 ZIP members = 5,050 JSON episodes + 1 non-JSON member; 5,050
  accepted, 0 rejected, 0 duplicates; 10,100 decks; 606,000 submitted card copies;
  214 unique exact card IDs = 100 Pokémon, 96 Trainer, 18 Energy.
- Validation: 12 focused unit tests passed. The independent root-action path recomputed
  all 214 per-card game/deck/copy/min/max aggregates and the complete ID union; class
  lists were pairwise disjoint and complete; 13 deterministic raw samples matched. All
  eight generated artifacts were byte-identical on the repeat run.
- Conclusion: pilot gate passed with zero error issues and zero unresolved card IDs.
- Follow-up: run all discovered dated archives (completed below).

### 2026-07-15 — Spec 12a full top-ladder card inventory

- Status: completed
- Goal: Produce the authoritative exact-card-ID catalog over every ZIP currently under
  `Imitation-Learning/Top-ladder-data/` after the pilot gate passed.
- Code/version: same Spec 12a analyzer/verifier as the pilot.
- Inputs:
  - `7-12`: SHA-256
    `fba2cc8fd028109ab038dda9b2aca09bd1323cf40200cd2797d66c351fc67646`
  - `7-13`: 737,831,265 bytes; SHA-256
    `972100430bce2fc877651fe50a2bdf990548e968405867da14b22f9e87c33464`
  - `7-14`: 737,949,050 bytes; SHA-256
    `4c844694ae8fc48e595f1e9d89a4c6b8dcdc9c702e8a3407f360be1a1c803f54`
  - card database SHA-256
    `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`.
- Commands:
  - `python Imitation-Learning/analyze_top_ladder_cards.py --all --output-dir Imitation-Learning/meta-card-analysis/all-datasets`
  - `python Imitation-Learning/verify_top_ladder_inventory.py --archive <7-12.zip> --archive <7-13.zip> --archive <7-14.zip> --output-dir Imitation-Learning/meta-card-analysis/all-datasets`
  - repeated the analyzer command and compared SHA-256 for every output file.
- Output: `Imitation-Learning/meta-card-analysis/all-datasets/`; manifest SHA-256
  `7d3b981b26f30c992070d3503a2ccb326fb9764e218bc04bf65a1357a2a85538`;
  canonical catalog SHA-256
  `f3019b5179a59e738000f3efd773d10855f1ee7a71a9087560e0f6dfa9258711`.
- Results: 15,018 JSON episodes accepted (5,050 / 5,039 / 4,929 by date), 0
  rejected, 0 duplicates; 30,036 decks; 1,802,160 submitted card copies; 232 unique
  exact card IDs = 115 Pokémon, 99 Trainer, 18 Energy. Relative to the pilot, later
  dates added 18 IDs (15 Pokémon, 3 Trainer, 0 Energy).
- Validation: the independent root-action path recomputed all 232 per-card aggregates
  and the exact union; 39 deterministic raw samples matched; stratified lists were
  disjoint and complete. All eight artifacts were byte-identical on the full repeat.
- Conclusion: Spec 12a is complete. The canonical catalog is ready to drive the
  exhaustive Part-B semantics audit.
- Follow-up: obtain and freeze the user-provided open-source engine before beginning
  Spec 12b.

### 2026-07-15 — Spec 12b engine intake, exact-ID crosswalk, and audit worklist

- Status: completed (B01–B03)
- Goal: Freeze the exact competition engine, map every top-ladder card to its active
  definition, and construct the deterministic atomic-effect audit worklist.
- Engine: `Imitation-Learning/ptcg_engine.zip`, module `1.32.0`, SHA-256
  `d1a824b2740e9447acb988cc54f9d5de70af77f2be4f54b891cfa2d74e2a3802`.
- Commands:
  - `python -m unittest discover -s Imitation-Learning -p test_part_b_inputs.py -v`
  - `python Imitation-Learning/build_part_b_inputs.py b01`
  - `python Imitation-Learning/build_part_b_inputs.py b02`
  - `python Imitation-Learning/build_part_b_inputs.py b03`
  - repeated B03 and compared SHA-256 for every generated output.
- Output: `Imitation-Learning/meta-card-analysis/part-b/`.
- Results: active source, binary bindings, and English database each contain IDs
  1–1267; source and binary expose 1,556 attacks; all 232 meta IDs mapped by exact ID,
  name, class, text, effect count, and Tera state. The B03 worklist contains 314 effects
  (155 attack / 46 ability / 99 Trainer / 10 Energy / 4 Tera) in 12 frozen batches.
- Current-encoder comparison coverage: 23 card overrides, 14 stat bakes, and hardcoded
  dynamic references for 15 meta IDs were attached to their dossiers.
- Validation: 8 focused tests passed; crosswalk and worklist issue ledgers are empty.
  All five B03 artifacts were byte-identical across two runs. Worklist SHA-256
  `338fbd810960461b423affed4e0c33a2714ef3dabb13afd57e82dba5fdfb801b`;
  batch-manifest SHA-256
  `1c4b31b2a9cae12a7a4f0601838df0509533c7f52ca3248a48a60470a0fae187`.
- Conclusion: B01–B03 gates passed with no unresolved engine or worklist discrepancy.
- Follow-up: derive the B04 mechanic inventory and submit every taxonomy change for
  mandatory human review before freezing the semantic schema.

### 2026-07-15 — Spec 12b B04 schema and B05 Pokémon batch one

- Status: completed for B04 and `pokemon-01`; B05 remains active.
- Goal: Freeze the compositional semantic language, verify efficient observation access,
  and close the first frequency-ordered Pokémon audit batch.
- Commands:
  - `python Imitation-Learning/build_part_b_schema.py all`
  - `python Imitation-Learning/collect_pokemon01_engine_evidence.py`
  - `python Imitation-Learning/build_pokemon_audit.py`
  - `python -m unittest discover -s Imitation-Learning -p test_*.py -v`
- B04 results: all 314 effects have a schema-family home; 169 engine methods, 149
  tokens, and 227 signatures are inventoried; schema positive/negative, malformed-node,
  serialization, and recorded-observation checks pass. Generated artifacts were
  deterministic; validation-report SHA-256
  `e31b29e0b6e04c31beeb440f653a0df58b5b46d67770b4358a159128a26a9feb`.
- `pokemon-01` results: 20 cards / 34 effects, with 9 ordinary, 4 generic-exact,
  16 static-override, and 5 dynamic-override verdicts. All records passed exact source
  contracts. Twelve nontrivial attacks each have three distinct recorded module-1.32.0
  executions. Alakazam's observed counter loss matched `20 × pre-attack hand count` in
  every collected sample.
- Approved approximation: `HR-B05-002` permits coin outcomes through three consecutive
  heads only; any `>=4`-head tail is explicitly omitted. This is the only registered
  lossiness exception.
- Validation: 32 focused tests passed at the decision checkpoint; dynamic formula keys
  are unique and assigned to B08.
- Conclusion: B04 and `pokemon-01` gates passed. `pokemon-02` may begin.

### 2026-07-15 — Spec 12b B05 Pokémon batch two draft

- Status: complete after resolution of `HR-B05-003`.
- Goal: audit all 20 cards / 38 atomic effects in frozen batch `pokemon-02`, preserve
  exact engine behavior, and queue non-obvious dynamic calculations to B08.
- Commands:
  - `python Imitation-Learning/collect_pokemon01_engine_evidence.py pokemon-02`
  - `python Imitation-Learning/build_pokemon_audit.py pokemon-02`
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
- Results: 10 ordinary, 3 generic-exact, 19 static-override, 5 dynamic-override,
  and 1 engine-baked verdict. Five unique formula keys are assigned to B08. Mega
  Froslass ex uses exact live damage `50 × opponent_hand_count`, theoretical legal-state
  maximum 2,900 (`50 × 58` in a 60-card deck), and an explicitly unresolved credible
  meta maximum.
- Recorded evidence: the optimized/resumable scan read all 15,018 episodes. Of 16
  nontrivial target attacks, 12 occurred: 11 yielded three distinct samples and
  Absolute Snow yielded one. Tuck Tail, Come and Get You, Shadow Bind, and Gemstone
  Mimicry were never executed. Those five sparse/absent cases retain exact source
  handler validation; the artifacts explicitly record their sample counts.
- Human review: `HR-B05-003` approved exact engine order for Cursed Blast—self-KO
  first, then counter placement—even though the English presentation lists counter
  placement first.
- Approximation policy: unchanged. `HR-B05-002` remains the only approved lossiness
  exception; batch two introduces none.
- Validation: 40 focused tests pass (12 Pokémon audit, 12 inventory, 16 Part-B
  source/schema/worklist). The default and bundled Python runtimes both lacked PyTorch,
  so `Ceruledge-RL/test_features.py` was not freshly runnable and is not included in the
  pass count.

### 2026-07-15 — Spec 12b B05 Pokémon batch three

- Status: complete; `pokemon-04` is next.
- Goal: audit all 20 cards / 34 atomic effects in frozen batch `pokemon-03`, including
  multi-attack, counter-relocation, stochastic, and live damage-scaling behavior.
- Commands:
  - `python Imitation-Learning/collect_pokemon01_engine_evidence.py pokemon-03`
  - `python Imitation-Learning/build_pokemon_audit.py pokemon-03`
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
- Results: 9 ordinary, 2 generic-exact, 10 static-override, 12 dynamic-override,
  and 1 engine-baked verdict. Twelve unique B08 questions cover Spiritomb counter
  scaling, both Alakazam attacks, both Festival Lead sources, Do the Wave, Wonder Kiss,
  Raging Hammer, Gale Thrust, two one-coin attacks, and Fighting Wings.
- Bound policy: Alakazam Psychic retains exact live damage
  `10 + 50 × opponent Active attached Energy units`; credible and theoretical maxima
  are null pending B08 because a one-Energy-unit-per-card assumption is not valid.
  Duraludon's printed-HP credible maximum is 200, with HP-modified theoretical maximum
  deferred. No unsupported scalar was guessed.
- Recorded evidence: all 15,018 games were scanned. Seventeen of 18 targeted attacks
  occurred; 16 have three distinct samples, Dunsparce's Dig has one, and Swirlix's
  Sneaky Placement has none. Sparse/absent counts and exact source fallbacks are explicit.
- Validation: 47 focused tests pass (19 Pokémon audit, 12 inventory, 16 Part-B
  source/schema/worklist). All canonical JSON artifacts parse successfully. No new
  approximation or pending human-review record was introduced.

### 2026-07-15 — Spec 12b B05 Pokémon audit closure

- Status: complete; all six frozen Pokémon batches pass and B06 may begin.
- Goal: finish `pokemon-04` through `pokemon-06`, verify every remaining source effect,
  collect exhaustive recorded-engine evidence, and prove global B05 set equality.
- Commands:
  - `python Imitation-Learning/collect_pokemon01_engine_evidence.py pokemon-04`
  - `python Imitation-Learning/collect_pokemon01_engine_evidence.py pokemon-05`
  - `python Imitation-Learning/collect_pokemon01_engine_evidence.py pokemon-06`
  - `python Imitation-Learning/build_pokemon_audit.py pokemon-04` (and `05`, `06`)
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
  - rebuilt all six canonical batches twice and compared SHA-256 byte hashes.
- Batch results:
  - `pokemon-04`: 20 cards / 34 effects; 8 ordinary, 6 generic-exact, 9 static,
    11 dynamic. Fourteen of 19 targeted attacks were observed in 15,018 games.
  - `pokemon-05`: 20 cards / 39 effects; 11 ordinary, 4 generic-exact, 14 static,
    10 dynamic. Fifteen of 20 targeted attacks were observed in 15,018 games.
  - `pokemon-06`: 15 cards / 26 effects; 7 ordinary, 4 generic-exact, 7 static,
    8 dynamic. Eight of 14 targeted attacks were observed in 15,018 games.
- Global result: exact union of 115 Pokémon IDs and 205 source effects; no duplicates
  or omissions. Verdict totals are 54 ordinary, 23 generic-exact, 75 static override,
  51 dynamic override, and 2 engine-baked. All 51 formula keys are unique and owned by
  B08. Sparse/absent recorded executions retain exact handler-source fallback evidence.
- Validation: 53 focused tests pass (25 Pokémon audit, 12 inventory, 16 Part-B
  source/schema/worklist). All 29 Pokémon-audit JSON artifacts parse as UTF-8 JSON;
  the 314-row audit CSV imports successfully. No human-review record is pending and
  `HR-B05-002` remains the only approved approximation.
- Determinism: all six canonical batch files were byte-identical on the clean repeat.
  SHA-256: `pokemon-01` `fb62b4142c3603f63a2175654082266557b7f85cac8fe8927e02974c0725a6af`;
  `pokemon-02` `2d0f065ba872f24a3f0e5ca8707d6b344d50f97ebcbef019497bc0a2fc5a3938`;
  `pokemon-03` `edf9dd5087754d0f3b9e1f34800651ffdd4081c09cfc87754368ae9127e56612`;
  `pokemon-04` `59e0040cd20dd2e90f99d76d4a5b9d4e37c9c10e8df60ca24ebd80f2dd622d58`;
  `pokemon-05` `6ee0a47530df6ade369337d0398af8fbd55d2d569700eed0e903b3fcd00c8ddb`;
  `pokemon-06` `5849c3487c8313f14adb519a453e17b76279c0b7f3da8392a8d9d09c6bbe6f68`.
- Conclusion: B05 termination and validation gates pass. The next gated task is B06,
  the frozen 99-card Trainer audit.

### 2026-07-15 — Spec 12b B06 Trainer audit closure

- Status: complete; all five frozen Trainer batches pass and B07 may begin.
- Goal: audit all 99 top-ladder Trainers against exact English text, current encoder
  behavior, card-level rules, and competition-engine handlers; collect recorded
  resolution evidence and prove global set equality.
- Commands:
  - `python Imitation-Learning/collect_trainer_engine_evidence.py all`
  - `python Imitation-Learning/build_trainer_audit.py trainer-01` (through `trainer-05`)
  - `python Imitation-Learning/test_trainer_audit.py`
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
  - rebuilt all five canonical Trainer batches and compared SHA-256 byte hashes.
- Results: exact coverage of 99 IDs / 99 source effects, subtype totals 32 Items / 39
  Supporters / 11 Pokémon Tools / 17 Stadiums. Verdict totals are 67 static overrides,
  24 dynamic calculations, and 8 existing engine/stat bakes verified as exact. All 24
  formula keys are unique and owned by B08.
- Recorded evidence: the unified pass scanned all 15,018 games and recognized both
  Trainer `Play` and Tool `Attach` logs. Ninety-eight cards were observed: 92 have three
  distinct traces, Larry's Skill has two, Survival Brace / Maximum Belt / Punk Helmet /
  Ciphermaniac's Codebreaking / Waitress have one each, and Janine's Secret Art has
  none. Sparse and absent cases retain exact handler-source fallback evidence.
- Important exact boundaries: Neutralization Zone includes the card-level
  `cannotToHandOrDeckInTrash` rule; Hand Trimmer resolves opponent discard first; Area
  Zero Underdepths resolves its owner first when leaving play; Tool triggers preserve
  even-if-KO behavior; damage-counter effects retain counter units under `HR-B05-001`.
- Validation: 60 focused tests pass (7 Trainer audit, 25 Pokémon audit, 12 inventory,
  16 Part-B source/schema/worklist). All 23 Trainer-audit JSON artifacts parse as UTF-8
  JSON. No human-review record is pending and `HR-B05-002` remains the sole approved
  approximation.
- Determinism SHA-256:
  - `trainer-01`: `1b72a96a1515b8d2bbaecb9533773ee17b21b0e835cded2dd6b338841c040aa7`
  - `trainer-02`: `a2e17e3585173d64fb0c5d2ebe261acd0202d0bac483bbe2099caa771e3ce9de`
  - `trainer-03`: `e3064f45a4f3178b476664a409c4400f3ce7076b6ad21f1f05dbc4b1619505ae`
  - `trainer-04`: `5a0167c62b7c20ba399262384f66fef019f2ec9e0c62183fc6e17ae771a4fa37`
  - `trainer-05`: `a92723764c7c7517e784aeb1addcc81c9a7257b9c3e66cf8e22161641a5f697f`
- Conclusion: B06 termination and validation gates pass. The next gated task is B07,
  the frozen 18-card Energy audit.

### 2026-07-15 — Spec 12b B07 Energy audit closure

- Status: complete; the frozen 18-card Energy batch passes and B08 may begin.
- Goal: verify every Basic and Special Energy card's exact provision type/count,
  restrictions, modifiers, triggers, duration, and source/runtime implementation.
- Commands:
  - `python Imitation-Learning/collect_energy_engine_evidence.py`
  - `python Imitation-Learning/build_energy_audit.py`
  - `python Imitation-Learning/test_energy_audit.py`
  - `python Imitation-Learning/test_trainer_audit.py`
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
  - rebuilt the canonical Energy registry and compared its SHA-256 byte hash.
- Results: exact coverage of 18 IDs: 8 Basic Energy and 10 Special Energy. The Basic
  cards each provide one unit of their printed type and have no effect rows. The ten
  Special Energy effects yield 6 static and 4 dynamic overrides. The dynamic B08 queue
  covers Team Rocket's Energy, Ignition Energy, Prism Energy, and Legacy Energy.
- Engine validation: Prism and Ignition provision use the exact card-ID branches in
  `State::getEnergyInfo`; Team Rocket's Energy uses `State::canAttachEnergy` plus the
  refresh-time illegal-holder discard; Legacy Energy retains its once-per-game Prize
  history; Mist/Rock prevention excludes damage and does not remove existing effects;
  Spiky retaliation retains exact damage-counter units.
- Recorded evidence: the complete 15,018-game scan found three distinct attachment
  traces for every Energy ID, including Legacy Energy and Basic Lightning Energy.
- Validation: 68 focused tests pass (8 Energy audit, 7 Trainer audit, 25 Pokémon audit,
  12 inventory, 16 Part-B source/schema/worklist). All five Energy-audit JSON artifacts
  parse as UTF-8 JSON. No human-review record is pending and `HR-B05-002` remains the
  sole approved approximation.
- Determinism: `energy-01.json` reproduced byte-for-byte with SHA-256
  `52a63a7644f42844b28cc704716659ddf266e9a810e5acf235ac441dcb0c52aa`.
- Conclusion: B07 termination and validation gates pass. B08 dynamic and cross-card
  formula validation is next.

### 2026-07-15 — Spec 12b B08 dynamic-formula closure

- Status: complete; B08 termination and validation gates pass and B09 may begin.
- Commands:
  - `python Imitation-Learning/build_dynamic_formula_registry.py`
  - `python Imitation-Learning/test_dynamic_formulas.py`
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_trainer_audit.py`
  - `python Imitation-Learning/test_energy_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
  - rebuilt both canonical B08 JSON artifacts and compared their SHA-256 hashes.
- Results: all 79 unique queued formulas close exactly: 51 Pokémon, 24 Trainer, and 4
  Energy. Each record declares raw inputs and sources, output units/bounds, timing,
  source-program order, explicit-unknown fallback, no-saturation behavior, exact engine
  evidence, and three executable validation cases.
- Scenario validation: 237/237 negative, positive, boundary, and applicable stacking,
  suppression, and conflict cases pass and reproduce identically.
- Accuracy boundaries: exact live formulas are retained when a safe card-text constant
  maximum does not exist; missing state raises `MissingFormulaInput` rather than being
  treated as zero. Copy attacks preserve Tera/N's Pokémon gates and referenced attack
  programs. Rare Candy uses the full Basic→Stage 1→Stage 2 relation. Area Zero preserves
  stadium-owner-first leave-play resolution.
- Human review: no record is pending, no effect category changed, and `HR-B05-002`
  remains the sole approved approximation. Mega Kangaskhan's exact evaluator accepts
  every nonnegative head count; only its practical probability table omits `>=4` heads.
- Validation: 81 focused tests pass after adding the serialized clean-room scenario
  regression (13 B08 + the prior 68 Spec-12 tests).
- Determinism SHA-256:
  - `dynamic-formulas.json`: `c94c7f88eddee1535194819ce6207fd4963520f0b4b28b1ae8bb8566ba4452cc`
  - `dynamic-formula-validation.json`: `92cd9f7219ce8a8cadcc53de0fc95e839ff3569904add91dff7021ad4edbc756`
- Conclusion: B08 is closed. B09 end-to-end coverage/evidence/determinism closure is the
  next gated task.

### 2026-07-15 — Spec 12b B09 audit closure and Part-C gate

- Status: complete; Part B is closed and its clean-room payload is ready for Part C.
- Commands:
  - `python Imitation-Learning/build_dynamic_formula_registry.py`
  - `python Imitation-Learning/build_part_b_closure.py`
  - `python Imitation-Learning/test_part_b_closure.py`
  - `python Imitation-Learning/test_dynamic_formulas.py`
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_trainer_audit.py`
  - `python Imitation-Learning/test_energy_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
  - regenerated all B09 outputs twice and compared SHA-256 hashes.
- Exact closure: 232 cards (115 Pokémon / 99 Trainer / 18 Energy) and 314 effects match
  across catalog, worklist, crosswalk, ledger, and handoff. Verdicts are 148 static
  overrides, 79 dynamic overrides, 54 ordinary fields, 23 generic-exact, and 10
  engine-baked. No verdict is unresolved.
- Semantic diff: all 237 changed or engine-baked rows have a written explanation; the
  UTF-8 BOM CSV contains all 314 rows for direct human inspection.
- Formula/clean-room validation: all 79 formulas join to exactly 79 dynamic effects and
  all 237 scenarios reexecute after JSON serialization. B09 found and fixed integer
  evolution-map keys becoming strings during JSON round-tripping for Grand Tree.
- Human review: all 9 records are resolved and reproduced with evidence,
  recommendation, and decision in the final report. No new ambiguity or category
  change was found. `HR-B05-002` is still the only approximation.
- Tests: all 89 focused Spec-12 tests pass.
- Deterministic SHA-256 highlights:
  - `canonical-audit-ledger.json`: `b1cc3e1450737f409b79450ae2192568e0b4e2aa9838f6e12397c5b11ab53313`
  - `semantic-diff.json`: `207fe0c42ae7970ec88e6412bc92103adb8dc3926bb600e33ccbb5e463534b9b`
  - `semantic-diff.csv`: `8eae888c517946e929949edd8ebeeae7e10ac3071fbb63c2f4962f430225a7f2`
  - `closure-source-manifest.json`: `aa8e35a62c03f9f79470d21fc71536ab443af5957814792ae1b41f454dc971bb`
  - `part-c-handoff.json`: `4bda7fbffbf2990025c10ed3ce298b29026bbb8f6254d8d7d8d19ac04a3b80e6`
  - `closure-validation.json`: `5f59edc9f6855b54adc07857a11e17f1a30c52c0f9ded7c3ec7032efa59e1f55`
  - `B09-FINAL-REPORT.md`: `124d36f6eac02abd2bc3dc2ec34145a45ede83d0d12d170594dab40a0d940a69`
  - `closure-artifact-manifest.json`: `41910fb48cfc14f6b5d4086e4f8710684327668f4a8f57e6f7de140678349057`
- Conclusion: B09 and Part B pass. Part C exact-card-ID registry compilation is next.

### 2026-07-15 — Spec 12c exact-card-ID registry and handoff closure

- Status: complete; C0–C5 and all Spec-12 acceptance criteria pass.
- Commands:
  - `python Imitation-Learning/build_meta_card_registry.py`
  - `python Imitation-Learning/test_meta_card_registry.py`
  - `python Imitation-Learning/test_part_b_closure.py`
  - `python Imitation-Learning/test_dynamic_formulas.py`
  - `python Imitation-Learning/test_pokemon_audit.py`
  - `python Imitation-Learning/test_trainer_audit.py`
  - `python Imitation-Learning/test_energy_audit.py`
  - `python Imitation-Learning/test_top_ladder_cards.py`
  - `python Imitation-Learning/test_part_b_inputs.py`
  - generated the package twice and compared every file hash.
- Canonical package: `Imitation-Learning/meta-card-registry/`, schema version `1.0.0`.
- Coverage: 232 numerically ordered exact card IDs, 314 effect rows, and no truncation.
  Stratified vocabulary counts are 115 Pokémon / 99 Trainer / 18 Energy.
- Derived views: 201 cards carry 237 static/dynamic/engine-baked special rows. The
  override view is mechanically derived and excludes exactly 31 cards with no special
  verdict. All 79 formulas have card/effect reverse indexes and 237 passing scenarios.
- Consumer contract: JSON and Python ID forms agree; `registry.py` loads cards and
  formulas; the README documents exact-ID precedence, generalized unseen fallback,
  explicit unknowns, engine-baked/ordinary double-count prevention, and deferred common
  fields. No tensor position, shape, or normalization is selected.
- Tests: all 100 focused Spec-12 tests pass (11 Part C + 89 Parts A/B).
- Deterministic SHA-256:
  - `registry.json`: `2ddbea197e2fece5274c00696cf5863afdc0fb82d839fd712ef004a9688c143b`
  - `formulas.json`: `279f1253accaaac8df5cc51a170c316b90211251e640f195c4cb95c0ccfb38c6`
  - `overrides.json`: `05181fe29230a0c44868eeca64ac1638e37677a06d9806297954fc78b6bc5c7a`
  - `card_ids.json`: `553a9017d2d196743d48b7b4d205fcbf2051761f2c56c27eed58c15f7b0f8b06`
  - `card_ids.py`: `61588e66e2ac022901699cbb8beedb7b706599373742e156afa8cb8324fba4aa`
  - `registry.py`: `61dbf705bcddf9fed1b98603088329577ac7c9bf3f0c4534e4b09c9e030fafbf`
  - `schema.json`: `43f54eadfc29026e2bdef424b6073f3eadf294b69a7484b5af65124b2ae64f65`
  - `provenance.json`: `d517ff7d377e2a2260991c150489bd9fdd636aa632d80d24762d1f57c6015a7c`
  - `validation.json`: `5255a1689a00ee4a4a342a49753fbfe82ad729a4001d91ffd34cb2aeac4bee85`
  - `README.md`: `d4fb70aa87ef8c97e75dd0996f72ef9b8382f8fe97187bc55bfe36d3f505975d`
  - `artifact-manifest.json`: `6e1a573d552bb6083562653772c898deaf16226c24561f9684e2a24e1a0f6a5d`
- Conclusion: Spec 12 is complete. The next work must be a new encoder/integration spec.

### 2026-07-16 — Spec 12 registry cleanup and attack-encoding guide

- Status: complete; final consumer files are prominent, phased material is archived,
  and the 100-test baseline remains green.
- Layout changes:
  - moved the 13 completed Spec 12 documents to
    `Ceruledge-RL/specs/completed/spec-12/` and added a completed-spec index;
  - moved 7 phased Part A/B test modules to
    `Imitation-Learning/archive/spec12-development/tests/`;
  - added `run_archived_tests.py`, which preserves the 89 archived tests against the
    original builders; and
  - added `Imitation-Learning/README.md` as a concise active/archive directory guide.
- Registry corrections: every attack record now preserves `printed_cost` and
  `printed_damage` from the audited row. Dynamic attack profiles take their resolved
  credible/theoretical bounds and unknown reason from the final formula record, so no
  pre-B08 `pending` placeholder remains.
- Documentation: the generated consumer README now explains the registry as identity,
  ordered attacks/abilities/effects, semantic AST programs, and live calculations. It
  includes Alakazam, Mega Kangaskhan ex, Wellspring Mask Ogerpon ex, Team Rocket's
  Mimikyu, and N's Zoroark ex examples, plus a plausible per-attack semantic token and
  Pokémon-level composition before concatenating the exact-card-ID one-hot. This is
  explicitly guidance rather than a final observation layout.
- Commands:
  - `python Imitation-Learning/build_meta_card_registry.py`
  - `python Imitation-Learning/test_meta_card_registry.py` — 11 passed
  - `python Imitation-Learning/archive/spec12-development/run_archived_tests.py` — 89 passed
- Validation: all 20 Part-C checks pass; the combined Spec 12 total remains 100 tests.
- Current deterministic SHA-256 (supersedes the initial Part-C package snapshot above):
  - `registry.json`: `5bc1d58b30d0817b7c08e88c83ead2d1479bb7ab88e558aadf4d3769baa9b16f`
  - `formulas.json`: `279f1253accaaac8df5cc51a170c316b90211251e640f195c4cb95c0ccfb38c6`
  - `overrides.json`: `819316ba1fa431c0323a5dcc711e1aecaa8a51a78b8c6bb51c7d4eafb7f50656`
  - `card_ids.json`: `553a9017d2d196743d48b7b4d205fcbf2051761f2c56c27eed58c15f7b0f8b06`
  - `card_ids.py`: `61588e66e2ac022901699cbb8beedb7b706599373742e156afa8cb8324fba4aa`
  - `registry.py`: `61dbf705bcddf9fed1b98603088329577ac7c9bf3f0c4534e4b09c9e030fafbf`
  - `schema.json`: `43f54eadfc29026e2bdef424b6073f3eadf294b69a7484b5af65124b2ae64f65`
  - `provenance.json`: `d517ff7d377e2a2260991c150489bd9fdd636aa632d80d24762d1f57c6015a7c`
  - `validation.json`: `98bb4f8717ff8356929743d138fab8430107f4115ce99e09540012a69968327a`
  - `README.md`: `13350cac5f1dacf90053ad0ec781b159eeda3c0ec745a8f53fad142dca7987a8`
  - `artifact-manifest.json`: `160715e691d27a6e54967917bbb4552beb491222eac9084573a6cec24d59eee9`
