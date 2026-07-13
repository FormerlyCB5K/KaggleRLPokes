# 05 — Full-Database Integration of New Attack Tags

Status: **COMPLETE — implemented, audited, and regression-tested (2026-07-11)**

## Purpose

Populate the three new attack fields—`retreat_lock`, `immunity`, and `recoil`—across
the complete Pokémon card database. Use conservative reusable extraction rules where
the card text is unambiguous, manual overrides where a generic rule would be unsafe,
and a human-review list where the intended encoding is debatable.

This is one exhaustive pass over every Pokémon attack, not a random sample. The task
must not change unrelated tags or the ability schema.

## Existing representation

Each opponent Pokémon has two 18-dimensional attack blocks:

1. `energy_cost`
2. `damage`
3. the 16 fields in `effect_features.ATTACK_TAG_FIELDS`

The three new fields are the final entries:

- `retreat_lock`
- `immunity`
- `recoil`

Cards with more complicated or copied behavior may use `virtual_attacks` in
`attack_overrides.py`. `retreat_lock` and `immunity` are Boolean. `recoil` stores raw
self-damage HP and is normalized by `/70`, clipped to `[0, 1]`, in the network block.

## Authoritative tag semantics

### `retreat_lock`

Set to `1` when using the attack can prevent the opponent's Defending/Active Pokémon
from retreating during the opponent's next turn.

Include:

- “During your opponent's next turn, the Defending Pokémon can't retreat.”
- Equivalent wording referring to “that Pokémon” or the opponent's Active Pokémon.
- An attack that both inflicts a Special Condition and prevents retreat.
- A coin-flip or other conditional retreat lock; also retain the appropriate
  `probabilistic` or `conditional` tag.

Exclude:

- The attacker being unable to retreat.
- Retreat Cost increases without an actual prohibition.
- Abilities, Tools, and Stadiums; this field belongs to attack blocks only.
- Switching or gust effects that move a Pokémon immediately.

Borderline cases go to human review rather than being forced into the tag.

### `immunity`

Set to `1` when using the attack can cause the attacking Pokémon to receive no attack
damage during the opponent's next turn.

Include:

- “During your opponent's next turn, prevent all damage from attacks done to this
  Pokémon.”
- Equivalent complete attack-damage prevention wording.
- Coin-flip-gated prevention; also retain `probabilistic`.
- Prevention that includes both damage and effects.

Exclude:

- Fixed damage reduction such as “takes 30 less damage.”
- Prevention of effects only when damage can still be dealt.
- Protection limited to the Bench, a Pokémon type, or another Pokémon unless the
  attack specifically protects its user from all attack damage.
- Weakness removal, Resistance changes, Barrier-style abilities, and Sturdy effects.
- Effects that prevent damage only from one named attack or narrow source. Record
  these for human review if strategically important.

`immunity` means the attack can create a full next-turn damage shield; it does not mean
the shield is currently active. Live effect tracking is outside this spec.

### `recoil`

Store the amount of self-damage, in raw HP, when resolving the attack directly damages
its user or places damage counters on its user. Damage counters are converted to HP at
10 HP per counter.

Include:

- “This Pokémon also does N damage to itself.”
- “Put/place N damage counters on this Pokémon” as part of resolving the attack.
- Conditional or optional self-damage; retain `conditional`/`probabilistic` when
  applicable.

Exclude:

- Discarding attached Energy or cards.
- Moving existing damage counters rather than creating new self-damage.
- Damage received later as retaliation from an opponent.
- “Knock Out this Pokémon” or other explicit self-KO effects. Record these separately
  because a clipped recoil magnitude understates them.
- Self-damage from Abilities, Tools, or Special Energy.

If an attack has variable recoil that cannot be resolved from its text, use a reviewed
override or send it to human review. The network value is `min(raw_recoil / 70, 1)`.

## Source pool

Audit every card whose CSV stage is one of:

- Basic Pokémon
- Stage 1 Pokémon
- Stage 2 Pokémon

Review every parsed attack on those cards, including attacks with blank printed
damage. Exclude Trainer and Energy rows. Playable Fossil Items remain outside this pass
because they do not expose attacks while acting as Fossils.

The current database contains 1,056 Pokémon and 1,555 parsed attacks; implementation
must report the actual counts observed at run time in case the CSV changes.

## Implementation workflow

### Phase 1 — Freeze the baseline

1. Run all existing feature/tag tests.
2. Snapshot raw tags for the entire card pool.
3. Record the current database hash or file size and card/attack counts.
4. Generate three candidate lists using broad searches, one per new tag. Candidate
   searches are discovery tools only and must not determine final tags automatically.

### Phase 2 — Full semantic audit

Read every Pokémon attack row and assign one verdict for each new tag:

- `0` — tag does not apply.
- `regex` — tag applies and wording/value is safe for a reusable parser rule.
- `override` — tag applies but should be encoded with a card override.
- `review` — meaning or desired representation is ambiguous.

The audit artifact must contain every positive, override, and review case with:

- card ID and name;
- attack number and name;
- exact effect text;
- proposed tag(s);
- extraction method (`regex` or `override`);
- one-sentence rationale.

Cards receiving none of the three tags may be summarized by count rather than listed
individually, provided every attack was inspected.

### Phase 3 — Design conservative extraction rules

For each reusable wording family:

1. Add a narrowly scoped `_RX_TAG_*` pattern in the spec-03 section of
   `effect_features.py`.
2. Update `attack_tags()` without touching the legacy modifier-vector parser.
3. Add positive and negative self-tests. Every rule needs at least:
   - one direct positive;
   - one wording-variant positive;
   - one nearby negative that must not match.
4. Do not add a broad rule when a short override list is safer.

Expected initial pattern families:

- retreat lock: next-turn + Defending/opponent Active + can't retreat;
- immunity: next-turn + prevent all damage from attacks + this Pokémon;
- recoil: this Pokémon + does N damage to itself;
- recoil counters: put/place N damage counters on this Pokémon.

These are starting families, not permission to skip the full audit.

### Phase 4 — Add manual overrides

Add approved `attacks` overrides for positive cases that cannot be safely generalized.
Because an `attacks` override fully replaces keyword extraction for every listed attack,
each override must preserve all existing correct tags on that attack.

Before writing an override:

- dump the card's current tags;
- copy every correct existing tag into the replacement dict;
- add the new tag;
- verify attack order against `card_data.py`'s cheapest-first order.

Do not modify unrelated max-damage values or ability tags during this pass.

### Phase 5 — “But no more” regression gate

1. Snapshot the full pool after edits.
2. Diff pre/post snapshots.
3. Review every changed card and every changed field.
4. A permitted change is only:
   - one of the three new tags changing from 0 to 1; or
   - preservation/restoration of an existing tag required by a new full override.
5. Any unrelated tag or max-damage change fails the gate and must be investigated.
6. Run:
   - `effect_features.py` self-test;
   - `opponent_tags.py` self-test;
   - `test_features.py`;
   - model shape smoke test;
   - policy-vs-random smoke test.

## Required output files

Implementation should produce:

1. `old/audits/tagging/new-tags-full-audit.md`
   - database/card/attack counts;
   - every positive and ambiguous case;
   - method and rationale;
   - totals by tag and method.
2. `old/audits/tagging/new-tags-human-review.md`
   - only unresolved semantic decisions.
3. Pre/post snapshot files used for the regression diff.
4. Updated parser tests and approved overrides.

The final user report must state:

- number of attacks reviewed;
- counts tagged as retreat lock, immunity, and recoil;
- number handled by regex versus override;
- number left for human review;
- every test command and result;
- confirmation that no unrelated tag fields changed.

## Acceptance criteria

The task is complete only when:

- all Pokémon attacks in the current database were reviewed once;
- every positive case is implemented or explicitly awaiting human review;
- `retreat_lock` and `immunity` remain Boolean;
- recoil is stored as non-negative raw HP and normalized by `/70`, clipped to `[0, 1]`;
- no unrelated tags, abilities, damage values, or model shapes changed;
- every changed card in the full-pool diff was manually verified;
- all tests and live smoke tests pass;
- audit artifacts are sufficiently detailed for a later reviewer to reproduce each
  decision.

## Explicitly out of scope

- Adding new tags beyond these three.
- Tracking whether a next-turn lock or immunity effect is currently active.
- Ability, Tool, Stadium, or Energy effect tagging.
- Reworking `max_damage` or other reviewed dynamic-damage formulas.
- Changing the number of attack blocks, Pokémon words, or Transformer words.
- Training or opponent-pool integration.
