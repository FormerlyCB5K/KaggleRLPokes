# Engine-native reference artifacts

These files are the executable v3 handoff used to pin the Python implementation.
`installed-manifest.json` records full SHA-256 hashes for the retained files, while
`MANIFEST.json` is the original supplied manifest.

Runtime imitation-data construction uses `frozen_tables.pt`. The reference checkpoint,
golden replay, and golden outputs are retained because reproducing the exact 98.3M-step
weights would require retraining and they are required by the permanent parity test.

Generated imitation caches do not duplicate these artifacts.
