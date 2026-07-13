# Iterative Tag-Audit Workflow — Repeatable Plan

Five rounds of regex refinement for `effect_features.py` tag extraction, each verified
against a fresh batch of never-audited Pokémon cards. Decisions confirmed 2026-07-11.

## Files (archived in `Ceruledge-RL/old/audits/tagging/`)

| File | Role |
|---|---|
| `PLAN.md` | this procedure |
| `audit_tools.py` | `snapshot` / `sample` / `diff` subcommands |
| `audited_ids.txt` | one id per line; the no-repeat ledger (seeded with round 0's 100) |
| `round-N-report.md` | per-round audit report (round 0 = `tag_audit_100.md`) |
| `SUMMARY.md` | running ≤5-sentence summary per round — the only carried context |
| `override-worklist.md` | cards needing hard-coded overrides (id, name, tag, value) |
| `human-review.md` | ambiguous cards for the user, presented at workflow end |

## Round procedure (rounds 1–5)

1. **Snapshot**: `python old/audits/tagging/audit_tools.py snapshot old/audits/tagging/snap_pre.json`
   (raw tags for the whole pool, from the CURRENT regexes).
2. **Edit**: apply the previous round's queued regex fixes to `effect_features.py`.
   Extend its `_selftest()` with one case per new pattern.
3. **Verify (the "but no more" gate)**:
   a. `python old/audits/tagging/audit_tools.py snapshot old/audits/tagging/snap_post.json`
   b. `python old/audits/tagging/audit_tools.py diff old/audits/tagging/snap_pre.json old/audits/tagging/snap_post.json`
   c. Review EVERY changed card: each must be an intended fix or a correct new catch;
      any wrong change → refine the regex and redo from (a).
   d. Run `effect_features.py`, `opponent_tags.py`, `test_features.py` self-tests.
4. **Sample**: `python old/audits/tagging/audit_tools.py sample <round>` — 100 unseen Pokémon-only
   cards, `random.seed(100 + round)`, pool minus `audited_ids.txt`; ids are appended
   to the ledger; dump goes to `old/audits/tagging/batch<round>.txt`.
5. **Audit**: read every card's text vs its tags. Verdicts:
   - ✅ correct · ❌ FN / FP (regex fix candidate, queued for next round's edit)
   - 🔶 override candidate → append to `override-worklist.md`
     (use when no regex can catch it without false positives)
   - ❓ unclear whether the tag SHOULD apply → append to `human-review.md`
6. **Report**: write `old/audits/tagging/round-N-report.md` (per-card: text, active tags,
   one-sentence verdict, suggested regex when wrong).
7. **Summarize + forget**: append ≤5 sentences to `SUMMARY.md` (what changed, what
   still recurs). From here on, use only SUMMARY.md — no per-card details carry over.

After round 5's audit: apply its queued fixes as a **final edit**, re-run step 3 in
full, then present `human-review.md` and totals to the user.

## Conventions

- Round seeds: 101, 102, 103, 104, 105. Round 0 (pre-workflow) was `seed(42)` over the
  attacks-or-abilities pool; later rounds use the Pokémon-only pool (CSV stage is
  Basic/Stage 1/Stage 2 — fossils and trainers excluded).
- Raw tag values in reports (un-normalized), same block fields as spec 03.
- Regex edits touch ONLY the spec-03 tag section of `effect_features.py` (the
  `_RX_TAG_*` / `_RX_ABL_*` patterns and `attack_tags`/`ability_tags`); the legacy
  MODIFIER-vector patterns stay frozen.
- `attack_overrides.py` is never edited by this workflow (worklist only).
- Batch size 100; if the unseen pool drops below 100, take what remains.
