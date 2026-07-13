# Completed Audit Bundles

These directories preserve completed audit evidence and the utilities used to produce
it. They are historical evidence, not part of the runtime or deployment surface.

- [`tagging/`](tagging/) — attack/ability tag audit, snapshots, worklists, and reports.
- [`effect-baking/`](effect-baking/) — effective-stat bake audit, probes, verdicts, and
  regression snapshots.

The two bundles are separate because they validate different feature layers even
though the effect-baking audit used tagging snapshots as a regression check.
