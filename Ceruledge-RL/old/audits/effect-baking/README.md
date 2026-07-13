# Effect-Baking Audit Archive

This bundle records the completed effective-stat baking audit behind specifications 06
and 07: engine probes, final per-card verdicts, generated reports, and
feature-regression snapshots. Empty review and intermediate worklist/count files were
discarded after completion.

The scripts import the current feature modules for reproducibility, but no active code
imports from this directory. Run commands from `Ceruledge-RL`, for example:

```powershell
python old/audits/effect-baking/dump_bakes.py
python old/audits/effect-baking/effect_bakes_snapshot.py old/audits/effect-baking/check.json
```
