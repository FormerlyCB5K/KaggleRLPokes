# Plan 05 Implementation Progress

Last updated: 2026-07-11

## Objective

Complete one exhaustive database pass for attack `retreat_lock`, attack `immunity`,
and numeric `recoil`, following
`specs/completed/05-new-attack-tags-full-audit.md`.

## Fixed decisions

- `retreat_lock`: Boolean capability tag.
- attack `immunity`: Boolean full next-turn attack-damage prevention capability.
- `recoil`: raw self-damage HP; damage counters ×10; network normalization `/70`
  clipped to `[0,1]`.
- Self-KO is not recoil.
- Existing unrelated tags and max-damage values must not change.
- Full overrides must preserve every existing correct tag on the affected attack.

## Resume checkpoint

- [x] Spec approved; implementation authorized.
- [x] Progress log created.
- [x] Pre-change snapshot and database fingerprint recorded.
- [x] `retreat_lock` full-pool audit complete.
- [x] attack `immunity` full-pool audit complete.
- [x] `recoil` full-pool audit complete.
- [x] Parser rules and overrides implemented.
- [x] Human-review artifact written.
- [x] Full pre/post diff reviewed.
- [x] Test and live-smoke gate passed.

## Work log

### 2026-07-11 — Start

- Began Plan 05 implementation.
- No Plan-05 parser or database-wide override edits have been made yet.
- Existing reviewed overrides for Hop's Phantump/Trevenant, Hop's Snorlax, Hariyama,
  and N's Zoroark predate this pass and are part of the frozen baseline.

### 2026-07-11 — Baseline frozen

- CSV: `Decks/Deck-Builder/EN_Card_Data.csv`
- Size: 359,151 bytes
- SHA-256: `A0EA63CF7ADCB65D35436CE0EB390DE6E2E35654A7C67C065A45F4ABAA00F373`
- Registry: 1,267 records; 1,056 Pokémon; 1,555 attacks; 221 abilities.
- Pre-change snapshot: `old/audits/tagging/new-tags-snap-pre.json`.
- Baseline tests passed: `effect_features.py`, `opponent_tags.py`, and
  `test_features.py`.

### 2026-07-11 — Full semantic pass and implementation

- Reviewed all 1,555 attacks for the three Plan-05 fields.
- Implemented conservative parser families in `effect_features.py` with positive and
  negative self-tests.
- Final positive totals: 27 retreat locks, 15 full immunities, 48 fixed-magnitude
  recoils, and 1 board-dependent Palafin recoil.
- Existing overrides cover Hop's Trevenant, Hop's Phantump, Hop's Snorlax, and
  Hariyama. No new Plan-05 override was required.
- Wrote `old/audits/tagging/new-tags-full-audit.md` with every positive and exact text.
- Wrote `old/audits/tagging/new-tags-human-review.md`; all 7 decisions are now resolved.
- Created `old/audits/tagging/new-tags-snap-post.json`; reviewed the full diff.
- Diff: 86 intended fields across 85 cards; no unrelated tag, ability, damage, or
  max-damage changes.

### 2026-07-11 — Final gate passed

- `effect_features.py`: passed.
- `opponent_tags.py`: passed across 1,267 cards; 631 cards now have tags.
- `test_features.py`: all generalized feature tests passed.
- Model shape/finite smoke: passed with `(2, 23, 64)` Transformer words and `(9, 75)`
  opponent inputs.
- Live policy-vs-random smoke: 5/5 games completed without errors.
- Plan 05 implementation is complete with no unresolved human-review decisions.
- Six narrow/threshold shields remain intentionally untagged, with a TODO beside the
  immunity extractor. Palafin recoil is evaluated live as `10 × damage counters`.
- Post-resolution verification passed again: all parser/tag/feature tests and 5/5 live
  smoke games completed without errors.

## Next exact action

Present the completed audit, test results, and 7 human-review decisions to the user.
