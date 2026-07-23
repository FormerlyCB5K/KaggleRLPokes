# 16a — Action Classification

## Purpose

Turn `obs.select.option` (the engine's legal-move list at any decision point) into (a) a
Stage 1 verb, when the decision is a MAIN-context choice, and (b) a list of Stage 2
candidates with enough structure to build an embedding for each — for *any* deck, using
only the engine's own `OptionType`/`AreaType`/`SelectContext` vocabulary
(`cg_download/api.py`). No card ID ever appears in this module.

## Behavior

### Stage 1 verbs (MAIN context only)

`SelectContext.MAIN`'s own docstring in `cg_download/api.py` lists exactly which
`OptionType`s appear there: `PLAY, ATTACH, EVOLVE, ABILITY, DISCARD, RETREAT, ATTACK, END`
— 8 verbs, one per `OptionType` value. `build_action_map(obs, our_idx)` groups the legal
option indices by `option.type` directly:

```python
VERBS = (OptionType.PLAY, OptionType.ATTACH, OptionType.EVOLVE, OptionType.ABILITY,
         OptionType.DISCARD, OptionType.RETREAT, OptionType.ATTACK, OptionType.END)

def build_action_map(obs, our_idx):
    action_map: dict[OptionType, list[int]] = {}
    for i, o in enumerate(obs.select.option):
        if o.type in VERBS:
            action_map.setdefault(o.type, []).append(i)
    return action_map
```

No `_CARD_TO_ACTION` lookup, no per-card branching. Compare to
`Ceruledge-RL/actions.py`'s `build_action_map` (19 hardcoded actions) — this collapses to
8, matching the engine's own MAIN vocabulary exactly.

### Stage 2 candidates (every context, including MAIN's chosen verb)

The key simplification: **candidate shape is a function of `option.type`, never of
`SelectContext`.** A `SelectContext` only changes *how many* candidates must be picked
(`obs.select.minCount`/`maxCount`) and *why* (`obs.select.effect`), not what a candidate
looks like. This means one generic resolver handles literally every `SelectContext` the
engine defines (48+ as of this session — `TO_BENCH`, `HEAL`, `DEVOLVE`, `DAMAGE_COUNTER`,
`SWITCH_ENERGY_CARD`, etc.), not just the handful `Ceruledge-RL/actions.py` special-cased
(`TO_HAND`, `DISCARD`, `SWITCH`, `TO_ACTIVE`, `DISCARD_ENERGY_CARD`, `ACTIVATE`; everything
else silently fell into a random-choice fallback there).

Candidate kinds, by `option.type`:

| `OptionType` | Candidate references | Resolution |
|---|---|---|
| `CARD` | one card via `area`/`index`/`playerIndex` | resolve the actual card via a generalized version of `Ceruledge-RL/actions.py`'s `_get_card_from_area` that covers **every** `AreaType` (`DECK, HAND, DISCARD, ACTIVE, BENCH, PRIZE, STADIUM, ENERGY, TOOL, PRE_EVOLUTION, PLAYER, LOOKING`), not just the 5 Track A implemented |
| `TOOL_CARD` / `ENERGY_CARD` | a card attached to a Pokemon (`area`/`index`/`playerIndex`/`toolIndex` or `energyIndex`) | same resolver, offset into the Pokemon's `tools`/`energyCards` list |
| `ENERGY` | an attached energy unit (no card resolution — same energy card can back multiple energy units) | no card embedding; identity is positional only |
| `PLAY` / `ATTACH` (card side) | a hand card | resolve via `HAND` area, same as `CARD` |
| `ATTACH` (target side) / `EVOLVE` (target side) | a board Pokemon (`inPlayArea`/`inPlayIndex`) | resolve to the matching board `Word` |
| `RETREAT` / `DISCARD` (in-play) / `ABILITY` | a board Pokemon (`area`/`index`) | same as above |
| `ATTACK` | one of the active Pokemon's attacks (`attackId`, 0 or 1 per spec 11a's fixed 2-attack-row convention) | no separate card resolution — both attacks already live inside the acting Pokemon's own `Word` (spec 11a's tag block); candidate = attack slot, not a card |
| `SKILL` | an ordering choice over a `cardId`/`serial` | resolve via `serial` if it matches a known board Pokemon, else treat as a plain card reference |
| `NUMBER` | a literal count to pick | no card — encode the number itself as a scalar |
| `YES` / `NO` | a fixed binary choice | no card — small learned 2-way embedding |
| `SPECIAL_CONDITION` | one of 5 `SpecialConditionType` values | no card — small learned 5-way embedding |

Compound candidates: `ATTACH` and `EVOLVE` options each carry **two** references (card +
target) in one option. Both halves are resolved independently and returned as a pair —
scoring the pair is the model's job (16b), not this module's.

### Boss's-Orders-style targeting, generalized for free

Track A's `_handle_switch` special-cased `effect == Boss_Orders` to decide "opponent
bench" vs. "our bench." That hardcode disappears entirely here: every `CARD`-type option
already carries its own `playerIndex`/`area`, so which side's board a candidate belongs to
falls straight out of the generic resolver above — no effect-card check needed.

### Supporter-once-per-turn bookkeeping

The one thing this module still needs from card data (not the engine) is "is this hand
card a Supporter" — used only to update turn-state bookkeeping fed to the model as a
feature, not to gate legality (the engine's own `state.supporterPlayed` already excludes
illegal repeat-Supporter `PLAY` options from `obs.select.option`). Resolved via
`card_data.get_card_static(card_id).subtype == "Supporter"` — a one-line generic check,
replacing `Ceruledge-RL/actions.py`'s hardcoded `_SUPPORTER_IDS = frozenset({Boss_Orders,
Explorers_Guidance, Carmine})`.

## Data

Input: `cg_download.api.Observation`, `our_idx`. Output:
- MAIN context: `dict[OptionType, list[int]]` (verb -> legal option indices), plus per-verb
  candidate list (each candidate = one or two resolved references, per the table above).
- Non-MAIN context: a flat candidate list for `obs.select.option`, same resolution table,
  no verb.

## Interfaces / seams

- Consumes `cg_download.api.Observation` directly (same wire format spec 15's
  `live_adapter.py` already bridges) — this module and `live_adapter.py` can run side by
  side against the same recorded/live data.
- Candidate *embedding* (turning a resolved card/board reference into a vector) is 16b's
  job — this module only resolves *which* card/board-slot/attack-slot/literal each
  candidate refers to.

## Out of scope

- `SETUP_ACTIVE_POKEMON`/`SETUP_BENCH_POKEMON` (no scoring at all, matches Track A).
- Any notion of legality *enforcement* — `obs.select.option` is already the engine's own
  legal list; this module only classifies it.

## Open questions

- None currently blocking.
