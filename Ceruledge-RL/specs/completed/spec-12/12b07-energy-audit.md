# 12b07 — Energy Effect Audit

Step B07 of [`12b`](12b-meta-card-semantics-audit.md). Depends on B06.

Status: **COMPLETE — the frozen 18-card batch passes; B08 may begin**

## Goal

Audit all 18 meta Energy cards, including Basic and Special Energy.

## Actions

1. Verify each Basic Energy's provided type and absence of additional semantics.
2. For each Special Energy, record provided type/count, attachment restrictions,
   modifiers, triggers, discard rules, suppression, and scope.
3. Compare exact text with engine implementation and current encoder assumptions.
4. Assign one verdict per atomic effect and queue any dynamic calculation for B08.
5. Add focused engine scenarios for every Special Energy effect.
6. Flag every unclear meaning, uncertain inclusion decision, approximate mapping, or
   non-tight boundary in the mandatory human-review ledger.

## Termination condition

All 18 Energy IDs and every effect row have final evidence-backed verdicts; zero
`unresolved` or pending human-review cases remain.

## Validation

- Energy audit ID set equals the 18-ID Part-A list.
- Basic/Special subtype counts match the catalog.
- Special Energy tests cover valid attachment, invalid/non-applying attachment, active
  effect, and suppression/discard where applicable.
- Generic-versus-approved diff has no unexplained field.
- Every dynamic item has a unique B08 formula key.

Stop if any Energy type/count behavior is ambiguous.

## Completion result

The audit covers exactly 18 card IDs: 8 Basic Energy and 10 Special Energy. The Basic
cards provide exactly one unit of their printed type and have no additional effect rows.
The Special cards contribute 10 effect rows. Verdict totals are 8 `ordinary_field`, 6
`override_static`, and 4 `override_dynamic`.

The four B08 calculations are Team Rocket's Energy payment allocation, Ignition Energy
stage-dependent provision and turn-end discard, Prism Energy's Basic-holder type
selection, and Legacy Energy's once-per-game Prize reduction. Card-ID-specific provision
branches are cross-referenced to `State::getEnergyInfo`; Team Rocket attachment legality
and illegal-holder discard are cross-referenced to the state and refresh handlers.

The complete 15,018-game scan found three distinct recorded attachments for every one
of the 18 Energy IDs. All IDs, source effect rows, subtype counts, provision types/counts,
holder conditions, trigger boundaries, and formula ownership checks pass. The canonical
JSON reproduces byte-for-byte; no human-review record is pending; and `HR-B05-002`
remains the sole approved approximation.
