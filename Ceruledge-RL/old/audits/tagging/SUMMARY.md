# Audit Round Summaries

## Round 0 (pre-workflow, seed 42, report: tag_audit_100.md)
100 cards (82 encodable): 0 false positives, 12 false negatives, all from 7 regex gaps
now queued for round 1's edit: multi-coin/third-person flips, numberless "top card",
"a random" effects, "attach up to N Basic" accel, "discard up to N Energy",
both-sides bench spread snipe, and "put N MORE damage counters". Override candidates
and one schema ambiguity were filed to the worklist/human-review. Keyword tier proved
conservative: it under-fires on phrasing variants but never invents tags.

## Round 1 (seed 101, report: round-1-report.md)
Applied the 7 round-0 fixes; the full-pool diff changed 74 cards, all verified correct,
and exposed one pre-existing deckout FP ("shuffle INTO your opponent's deck" — devolve).
Fresh batch of 100: 88 correct, 9 FNs, 0 batch FPs — misses cluster on phrasing variants
again: typed "discard all {M} Energy", the verb "place" for damage counters, attack-level
energy attach (direct and search-and-attach), Special-Energy attach, and "top card of
each player's deck". Six regex fixes queued for round 2; conditional-bonus attacks keep
recurring and go to the override worklist as a group, not regex. New schema questions
(ACE-SPEC lock, gust-as-attack, partial attack lock, retreat lock) filed for human review.

## Round 2 (seed 102, report: round-2-report.md)
Applied the 6 round-1 fixes; the full-pool diff (34 cards) verified correct but exposed
2 fresh FPs fixed on the spot — 738 Pachirisu ("they attach energy" punish → added a
`(?<!they )` lookbehind) and confirmed the 246/316 deckout removals were right. Fresh
batch of 100: 91 correct, 5 FNs, 2 FPs. Persisting theme is deckout/accel PRECISION:
"look at/reveal … of your opponent's deck" still falsely mills (435, 471 — genuine mill
always says "discard"), and ability energy-accel misses phrasings outside the rigid
"during your turn, you may attach" anchor (795 Oricorio ex). Four fixes queued for round
3; new non-regex items surfaced (386 phantom-immunity mis-seed, Japanese CSV rows,
copy-attack max_damage) → worklist/human-review.

## Round 3 (seed 103, report: round-3-report.md)
Applied the 4 round-2 fixes; the full-pool diff (23 cards) was 100% clean — 0 new FPs,
with the 595/1091 peek-reveal removals and the new draw-until/accel/switch catches all
correct. Fresh batch of 100: 99 correct, 0 FNs, 1 FP. The deckout and energy-accel
precision work has largely converged — remaining misses are unparseable-N accel ("attach
any number", coin-gated amounts) that belong in overrides, not regex. The one new FP is
`ability damage` firing on SELF damage-counter costs (49 Feraligatr "put 5 counters on
this Pokémon"); fix queued for round 4 requires an opponent target, mirroring
counter_snipe. Worklist keeps absorbing the conditional-bonus group; no new human-review
questions this round.

## Round 4 (seed 104, report: round-4-report.md)
Applied the 1 round-3 fix; the full-pool diff changed exactly 1 card (49 Feraligatr
`damage` 50→0, intended). Deliberately kept the ability-damage verb as "put" only — a
brief "place" experiment newly caught 4 retaliation abilities but also mis-tagged 834
Toxtricity's self-counter, so I reverted to stay precise. Fresh batch of 100: 99 correct,
0 FNs, 1 FP (1019 Vivillon: "they draw 4 cards" = OPPONENT drawing, mis-tagged as our
`draw`). One draw-guard fix queued for round 5's final edit. New human-review item: the
put-vs-place retaliation-tagging inconsistency (255 Maractus tagged, place-worded ones
not) needs a policy decision. Regex precision is converging; residual misses are
unparseable-N (any amount / coin-gated) → overrides, and conditional-bonus → overrides.
