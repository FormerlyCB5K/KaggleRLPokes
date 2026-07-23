# 12b04 — Semantic Schema and Engine Behavior Matrix

Step B04 of [`12b`](12b-meta-card-semantics-audit.md). Depends on B03.

Status: **COMPLETE — 2026-07-15**

## Goal

Define one raw, vector-layout-independent representation for every mechanic family
actually present in the meta-card worklist.

## Actions

1. Group effect rows by card wording and engine handler/opcode.
2. Define named fields for value/unit, targets, scope, conditions, timing, duration,
   optionality, stochasticity, observability, and history requirements.
3. Distinguish base damage, live calculable damage, credible maximum damage, and hidden
   or unbounded cases.
4. Build an engine-behavior matrix showing which values are already resolved in an
   observation and which require a registry calculation.
5. Map every effect row to a schema family or an explicit schema-review issue.
6. Add every category creation, split, merge, rename, narrowing, generalization,
   deprecation, or removal relative to the original encoder to the mandatory human-review
   ledger, even when the proposed change appears clearly beneficial.

## Termination condition

Every discovered mechanic has one representational home, and zero schema-review issues
remain. Every category-level change has an explicit human decision.

## Validation

- Schema validation accepts one known positive example per mechanic family.
- A nearby negative example proves each family is not overly broad.
- Apply/non-apply engine scenarios verify the observation-baked matrix.
- Round-trip serialization preserves every raw value and condition.
- No field encodes a final neural dimension or normalization constant.
- Original-versus-proposed category diff equals the category-change records in the
  human-review ledger exactly.

Stop for user review if a mechanic cannot be represented without semantic loss.

## Completion record

- The engine-derived inventory covers 314 effects, 169 methods, 149 referenced tokens,
  and 227 unique handler signatures. No engine method is structurally unclassified.
- All 314 effects have at least one schema-family home; no row is unassigned.
- `HR-B04-001` through `HR-B04-003` are resolved. The compositional category set is
  approved subject to lossless full-meta coverage and efficient later compilation.
- Three real-card programs validate ordered operations, branching, references, formulas,
  and round-trip JSON serialization. Invalid node and operation categories are rejected.
- Every active audit family has a positive and nearby negative effect example.
- The engine-observation matrix distinguishes direct, derived, public-history, hidden,
  stochastic, and static inputs. A real July player observation validated visible board/
  zone paths and hidden opponent-hand/prize identities.
- The runtime contract uses exact-ID lookup, one shared board/zone aggregation pass, and
  incremental history; it forbids observation-time game simulation and hidden-as-zero
  substitution.
- Fifteen focused tests pass. Eight generated B04 artifacts are byte-identical across
  consecutive generations. Validation-report SHA-256:
  `e31b29e0b6e04c31beeb440f653a0df58b5b46d67770b4358a159128a26a9feb`.
- Schema-level representational coverage is proven. Effect-level losslessness remains a
  blocking B05–B08 acceptance condition and is not presumed by this closure.
