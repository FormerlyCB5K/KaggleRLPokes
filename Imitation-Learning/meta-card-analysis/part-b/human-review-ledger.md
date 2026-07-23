# Part-B Human Review Ledger

Status: **HR-B01-001 through HR-B05-003 resolved; no pending records**

This report retains every ambiguity, category change, approximate mapping, and other
non-tight decision raised during Spec 12b. Resolved entries remain in the final report.

## HR-B01-001 — Engine license and scope

The supplied README/license says the engine is not open-source and is available only
for competition use. Recommended decision: use it only in this local competition
workspace, cite paths/handlers, and report paraphrased conclusions without reproducing
engine code.

Decision: **approved** — use throughout the private working project; do not share the
engine code or derived work.

## HR-B01-002 — Engine version provenance

The datasets report module version `1.32.0`, but the ZIP has no Git metadata or embedded
version string. Source/database/simulator universes align at 1,267 card IDs, and source
and simulator each contain 1,556 attacks. Recommended decision: treat the ZIP as
authoritative only if it is the package governing those July competition games.

Decision: **confirmed** — `ptcg_engine.zip` is exactly the engine that ran the July
12–14 module-version `1.32.0` games.

## HR-B01-003 — Validation strategy without MSVC

The source targets Visual Studio 2022 C++20, but `msbuild` and `cl` are unavailable. The
installed `cg_download` simulator is executable and exposes the same card/attack counts.
Recommended decision: combine exact source traces with focused simulator scenarios and
retain the source/binary identity limitation as a provenance caveat.

Decision: **approved** — use exact source traces plus focused `cg_download` simulator
scenarios. Prefer engine-informed observation tracking that is faster and less prone to
breakage.

## HR-B04-001 — Canonical taxonomy restructure

The original canonical taxonomy has 16 attack tags and 11 ability tags, with overlapping
concepts split by source kind. Of 201 meta attack/ability rows, only 71 produce a
nonzero generic tag; 76 nonempty-text rows parse to all zero. It has no general-parser
path for the 99 Trainer, 10 Special Energy, or 4 Tera effect rows. The engine instead
expresses ordered targeting, conditions, costs, operations, triggers, durations, and
continuations, and a single effect may execute several operations.

Question: should the new registry make an ordered compositional effect program
canonical, expand the flat taxonomy as the canonical representation, or maintain both
as coequal semantic authorities?

Recommendation: make the compositional effect program canonical and derive convenient
flat compatibility tags from it. This preserves multi-step behavior, avoids duplicated
attack/ability concepts, and provides a structured fallback for unseen cards without
maintaining two independent sources of truth.

Decision: **approved option 1** — the ordered compositional effect program is the sole
canonical semantic representation. Flat tags may be generated as compatibility labels,
but are not maintained as an independent semantic authority.

## HR-B04-002 — Concrete category set

The engine-derived inventory contains 169 methods, 149 effect tokens, and 227 unique
handler signatures across 314 effects. The draft compositional language defines 7
program-node kinds, 24 semantic operations, 15 expression kinds, 8 observability
classes, and 19 overlapping audit families. All 314 effects have an engine-backed
family home; none are unassigned. The exhaustive original-to-proposed category diff is
in `category-diff-draft.json` and the readable contract is in
`semantic-schema-draft.md`.

Question: does this category set have the right semantic granularity for the canonical
registry, or should categories be renamed, split, or merged before effect-level audit?

Recommendation: approve it provisionally. Targets, parameters, expressions, timing,
and duration preserve exact distinctions without proliferating flat categories. Any
effect-level ambiguity still receives its own review record.

Decision: **approved provisionally** — the category set must demonstrate lossless
coverage of the complete observed meta-card set and efficient compilation for later
implementation. Failure of either condition reopens this decision and blocks B04.

## HR-B04-003 — Variable-damage maximum policy

Raging Bolt ex (`card_id: 63`) exposes a current-encoder mismatch. Bellowing Thunder
discards any number of Basic Energy attached across the player's Pokémon and deals 70
damage per discarded card; the engine implements selection plus damage scaling by the
selected count. The current encoder records `reviewed_max_damage=70`, which represents
only one discarded Energy.

Question: should variable attacks prioritize exact live formulas while keeping
deck/state-reachable credible maxima and legal theoretical maxima separate, use one
universal maximum, or use a manually chosen practical meta cap?

Recommendation: make the exact live formula primary; derive a credible maximum only
from explicit deck/state constraints; retain legal theoretical maximum separately; and
store `null` with a reason instead of guessing when a bound is not justified.

Decision: **approved with qualification** — store exact live formulas, credible maxima,
and theoretical maxima separately, and use `null` instead of unsupported guesses. Live
damage is not universally the most decision-relevant value: credible or theoretical
threat may be better, including hand-scaling Alakazam attacks after draw-heavy turns.

## HR-B05-001 — Damage counters versus attack damage

Alakazam, Munkidori, and Froslass place or move damage counters. Counters cause HP loss
but are not attack damage: Weakness, Resistance, and damage-only prevention/modifiers do
not apply.

Recommendation: store exact counter counts canonically and derive 10-HP-per-counter
values for KO/threat calculations, while always retaining
`damage_kind=damage_counters`.

Decision: **approved** — exact counter counts are canonical and 10 HP per counter is a
derived KO/threat value. `damage_kind=damage_counters` is always retained so ordinary
damage rules never apply.

## HR-B05-002 — Unbounded stochastic credible maximum

Mega Kangaskhan ex starts at 200 damage and adds 50 per heads while flipping until the
first tails. Expected damage is 250 and theoretical maximum is unbounded. Its damage
quantiles are p50=200, p90=350, p95=400, and p99=500.

Recommendation: store the exact distribution plus named quantiles instead of forcing
one arbitrary credible-maximum scalar. The later encoder can choose its risk tolerance
without losing information.

Decision: **approved with an explicit lossiness exception** — enumerate zero through
three consecutive heads only. For Mega Kangaskhan ex, retain practical outcomes 200,
250, 300, and optionally 350, with practical ceiling 350. Do not expand outcomes at
four or more heads for top-meta features; mark that tail as deliberately omitted. Any
other approximation requires separate human review before use.

## HR-B05-003 — Cursed Blast operation order

The English text for Dusclops and Dusknoir presents damage-counter placement before the
self-KO clause. The exact competition engine registers `effectKoMe()` first and the
5- or 13-counter effect second; its effect dispatcher executes those vector entries in
ascending order. The engine therefore resolves self-KO before counter placement, which
can expose a different intermediate public state and Prize-processing order.

Question: should the canonical ordered program preserve exact engine execution order,
natural-language presentation order, or treat the two operations as an unordered atomic
bundle?

Recommendation: preserve exact engine order—self-KO, then counter placement—because the
registry targets the engine that generated the training games. Keep the natural-text
discrepancy as evidence rather than changing runtime semantics.

Decision: **approved** — preserve exact competition-engine execution order: self-KO
first, then place the selected damage counters.
