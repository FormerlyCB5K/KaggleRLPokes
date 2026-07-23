# Imitation-Learning Registry Workspace

The active deliverable in this folder is the completed top-ladder exact-card-ID semantic
registry. Start with [`meta-card-registry/README.md`](meta-card-registry/README.md).

## Active files

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
