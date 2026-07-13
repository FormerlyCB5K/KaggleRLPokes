# Tagging Audit Archive

This bundle records the completed full-card-pool review behind specifications 03 and
05. It retains round reports, final before/after snapshots, manual-review worklists,
the tag dump utility, and the final audit reports. Iterative batch dumps, diffs, spot
checks, and the completed no-repeat ledger were deliberately discarded as scratch.

The scripts import the current feature modules for reproducibility, but no active code
imports from this directory. Run commands from `Ceruledge-RL`, for example:

```powershell
python old/audits/tagging/dump_tags.py --ids 235 290
python old/audits/tagging/audit_tools.py snapshot old/audits/tagging/check.json
```

The retained `card-overrides.txt` is the audit field vocabulary; runtime overrides are
implemented in [`../../../attack_overrides.py`](../../../attack_overrides.py).
