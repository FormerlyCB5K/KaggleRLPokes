# How to Read the Prepared Card JSON

Start with `audit-worklist.json`. Its top-level `cards` array contains one dossier per
exact numeric card ID. Biological species is not identity: two printings with different
IDs are separate cards.

## Card dossier

Useful top-level fields are:

- `card_id`, `card_name`, `card_class`, and `subtype`: exact identity and class;
- `frequency`: games, decks, and submitted copies containing that exact ID;
- `crosswalk`: proof that the dataset, English database, engine binary, and engine
  source refer to the same card;
- `engine_card_source`: source file and line range for the complete card definition;
- `current_encoder`: old overrides, stat bakes, maximum damage, and hardcoded formulas;
- `effects`: every attack, ability, Tera rule, Trainer effect, or Energy effect in source
  order.

## Effect row

`effect_id` is stable and readable, such as `card:293:attack:0`. `kind` identifies the
source type; `ordinal` is zero-based within that kind. `text`, `printed_cost`, and
`printed_damage` are the English card fields.

`engine` is evidence, not the semantic answer. It records the exact handler line range,
method sequence, effect tokens, and a hash of the source chain. Read it together with
the English text.

`generic_extraction` shows what the old text parser inferred. `current_encoder` shows
the old effective override when one exists. Neither is authoritative; mismatches are
the reason for this audit.

`audit` begins as pending. Final entries will contain the semantic verdict, validation
references, and any human-review IDs.

## Companion files

- `schema-family-worklist.json` gives each effect one or more broad audit homes. These
  are routing hints, not final semantics.
- `semantic-schema-draft.json` defines the compositional program vocabulary.
- `mechanic-inventory.json` inventories raw engine methods, tokens, and signatures.
- `human-review-ledger.json` preserves every ambiguity and the human decision.
- `approved-approximations.json` lists every authorized lossiness exception. If an
  approximation is absent from this file, it is not permitted.

For machines, join files by `card_id` and `effect_id`; never join by name alone. For
humans, read English text first, then engine evidence, then the old encoder comparison,
and finally the audited program/verdict.
