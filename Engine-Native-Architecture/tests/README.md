# Tests

Tests for the engine-native architecture live here.

The suite will be organized around:

- exact schema widths and field ordering;
- frozen card-table reproducibility;
- direct engine-observation encoding;
- hidden-information boundaries;
- legal-option and entity-pointer coverage;
- network shape, masking, and numerical stability;
- reference replay/checkpoint parity;
- sanitized replay pairing and complete multi-selection targets;
- deterministic tensor caches, hashes, and split integrity;
- mmap loading, resumable shard-aware batching, and supervised losses;
- interrupted/full behavior-cloning equivalence and checkpoint lifecycle; and
- CPU inference benchmarks.

Existing architecture tests remain in their current folders and are not moved or modified.

Run the focused suite from the repository root:

```powershell
.venv\Scripts\python.exe -m pytest Engine-Native-Architecture\tests -q
```
