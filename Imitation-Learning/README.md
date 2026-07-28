# Imitation-Learning Workspace

The current successor is the isolated engine-native architecture under
`../Engine-Native-Architecture/`. It reads the sanitized corpus here but does not reuse
the 174-word observation/action model, trackers, examples, or pickle caches under
`observation/` and `policy/`. Its six-day tensor cache is written to
`Top-ladder-data/engine-native-cache-test-six-days/`. Full behavior-cloning checkpoints
and metrics are written to the ignored
`engine-native-training/test-six-days/seed-20260728/` directory by
`../Engine-Native-Architecture/scripts/train_il.py`.

The earlier deck-agnostic observation/action model and imitation-learning pipeline under
`observation/` and `policy/` remains a preserved baseline. The completed
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

## Legacy 174-word imitation-learning run

For historical 174-word AiMOS/NPL instructions, including submission, dependency,
monitoring, recovery, and artifact commands, use
[`../docs/IMITATION_LEARNING_CLUSTER_HANDOFF.md`](../docs/IMITATION_LEARNING_CLUSTER_HANDOFF.md).
The top of that handoff now contains the current engine-native cache/smoke commands; its
later sections preserve the old pipeline for provenance. The commands below are the
legacy local/production form.

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
  --epochs 3 --batch-size 256 --val-frac 0.1 --resume `
  --early-stopping-patience 5 `
  --out Imitation-Learning/policy/out/il-run/checkpoint.pt
```

On AiMOS/NPL, submit `policy/submit-batch-build-cache.sh` once, then
`policy/submit-batch-il-train.sh`. Edit the `WORKDIR` and resource directives if the
cluster allocation differs. Full-day caches can be several gigabytes each; keep them
outside cloud-synced storage and pilot one full day before scaling.

Training shuffles every cached game globally once to create a persistent 90/10
episode-level train/validation split. The exact split and reusable per-day validation
shards live beside the output checkpoint. One shuffled cached day is one resumable
mini-epoch; day order changes each full pass. The cluster scripts save latest state after
every mini-epoch and automatically submit a continuation before the six-hour walltime.
The best model remains `checkpoint.pt`; restart state is `checkpoint.resume.pt`.
