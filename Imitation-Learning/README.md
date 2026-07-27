# Imitation-Learning Workspace

The active development track is the deck-agnostic observation/action model and
imitation-learning pipeline under `observation/` and `policy/`. The completed
top-ladder exact-card-ID semantic registry remains the source for card identity and
effect semantics; start with [`meta-card-registry/README.md`](meta-card-registry/README.md)
when working on registry content.

## Active files

- `observation/` — 174-word any-deck observation encoder and live engine adapter.
- `policy/` — generalized action classification, model, scoring, live acting, cached
  imitation data loading, and supervised/RL training entry points.
- `build_example_cache.py` — parallel per-day extraction into reusable
  `Example` pickle caches with strict manifests.
- `build_sanitized_top_ladder_dataset.py` — filters raw ladder archives and marks
  forced single-option decisions as unusable supervision while preserving tracker
  history.
- `meta-card-registry/` — consumer package: canonical registry, formula registry,
  exact-ID vocabulary, override view, loaders, schema, provenance, and validation.
- `build_meta_card_registry.py` — regenerates the consumer package from frozen Spec 12
  inputs.
- `test_meta_card_registry.py` — active consumer/package acceptance suite.
- `build_dynamic_formula_registry.py` — executable reference used to parity-check the
  declarative formula scenarios.
- `meta-card-analysis/` — frozen audit evidence and reproducibility artifacts. This is
  provenance, not the recommended consumer entry point.
- `Top-ladder-data/` — original dated episode archives.
- `ptcg_engine.zip` and `ptcg_engine/` — privately approved competition-engine evidence.

The remaining root-level build and evidence scripts are the preserved Spec 12 generation
pipeline. They are retained so the audit can be reproduced, but ordinary registry users
do not need to run them.

## Archived development material

Historical Part A/B tests moved to `archive/spec12-development/tests/`. Run them through
the archive runner so their imports resolve against the preserved root-level builders:

```powershell
python Imitation-Learning/archive/spec12-development/run_archived_tests.py
```

The completed design specifications live under
`Ceruledge-RL/specs/completed/spec-12/`. Current spec navigation remains in
`Ceruledge-RL/specs/README.md`.

## Normal consumer validation

```powershell
python Imitation-Learning/build_meta_card_registry.py
python Imitation-Learning/test_meta_card_registry.py
```

Generated files under `meta-card-registry/` should not be edited manually. Change the
builder or approved source inputs, regenerate, and verify the artifact manifest instead.

## Full imitation-learning run

Build the reusable cache before launching multi-epoch training. The episode limit and
`max_steps` must match between the two commands:

```powershell
python Imitation-Learning/build_example_cache.py --source sanitized `
  --sanitized-dir Imitation-Learning/Top-ladder-data/sanitized `
  --cache-dir Imitation-Learning/Top-ladder-data/example-cache `
  --max-episodes-per-zip all --max-steps 300

python Imitation-Learning/policy/train.py --source sanitized `
  --sanitized-dir Imitation-Learning/Top-ladder-data/sanitized `
  --cache-dir Imitation-Learning/Top-ladder-data/example-cache `
  --days-per-chunk 1 --max-episodes-per-zip all --max-steps 300 `
  --epochs 3 --out Imitation-Learning/policy/out/il-run/checkpoint.pt
```

On AiMOS/NPL, submit `policy/submit-batch-build-cache.sh` once, then
`policy/submit-batch-il-train.sh`. Edit the `WORKDIR` and resource directives if the
cluster allocation differs. Full-day caches can be several gigabytes each; keep them
outside cloud-synced storage and pilot one full day before scaling.
