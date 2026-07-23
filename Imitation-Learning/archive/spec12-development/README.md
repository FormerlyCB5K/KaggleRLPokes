# Archived Spec 12 Development Tests

This directory preserves the phased Part A/B regression suites after completion of the
final registry package. They are historical validation—not the primary consumer API.

Use the runner from the repository root:

```powershell
python Imitation-Learning/archive/spec12-development/run_archived_tests.py
```

The runner adds `Imitation-Learning/` to the Python import path, then discovers every
test in `tests/`. This preserves the original builder imports without copying or
maintaining a second build pipeline.

The active registry acceptance suite remains
`Imitation-Learning/test_meta_card_registry.py`. The archived tests contribute 89 tests;
together the active and archived suites retain the verified 100-test Spec 12 baseline.
