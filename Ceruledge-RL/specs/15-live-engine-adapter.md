# 15 — Live Engine Adapter for the Spec 13a Observation

**Status: implemented and validated 2026-07-22.** `Imitation-Learning/observation/live_adapter.py`
(`build_game_state`) implements the mapping below exactly as specced, including the
resolutions to all four open items. Covered by `test_live_adapter.py` (14 fixture-based
unit tests) and `test_live_adapter_replay.py` (runs the adapter + `build_observation`
against real recorded engine output from `Top-ladder-data/`, 2,170 real game states
across 8 full episodes, zero exceptions, direct-passthrough invariants hold). See
"Validation results" at the end of this document.

## Purpose

Spec 11/13/13a's `Imitation-Learning/observation/` package builds the any-deck, 174-word
observation from its own `GameState`/`RawPokemon` input types. Nothing constructs those
types from a real game yet — `encoder.py`'s own docstring calls this out directly:

> `GameState` is this module's own adapter boundary: whoever wires a live engine
> connection constructs one of these from `ToJson.h`'s `Current`/`PokemonJson` output.
> No such adapter exists yet — this module and its test construct `GameState` directly.

This spec is that adapter: a new module that takes the actual live wire format the
Ceruledge rollout already consumes (`cg_download.api.Observation`, as used today by
`Ceruledge-RL/features.py`) and produces `observation.encoder.GameState`, so
`build_observation()` can run against a real game instead of hand-built test fixtures.

## Scope

**In scope:** `Observation` (+ `our_idx`, + prize/turn tracker state) → `GameState` →
`build_observation()` → `list[Word]`, proven correct against live engine shapes.

**Out of scope:** consuming the resulting `list[Word]` in a model (tensor packing, role
embeddings, the SVN v2 architecture from memory) or wiring it into `train.py`'s PPO loop.
Spec 11's README already tracks "live-engine and training integration" as two separate
open items; this spec is the first one only. Model/training integration is a follow-up
spec once this adapter exists and is validated.

## Current state (confirmed by reading both sides)

- `cg_download/api.py` defines the actual wire types: `Pokemon` (`id`, `serial`, `hp`,
  `maxHp`, `appearThisTurn`, `energyCards: list[Card]`, `tools: list[Card]`,
  `preEvolution: list[Card]`), `PlayerState` (`active`, `bench`, `hand`, `discard`,
  `prize`, plus the 5 status booleans `asleep`/`paralyzed`/`burned`/`poisoned`/
  `confused` — these live on `PlayerState`, scoped to whichever Pokemon is Active, not
  per-`Pokemon`), and `State` (`turn`, `stadium`, `players`).
- `Ceruledge-RL/features.py` already does this mapping once, informally, for the old
  19/75/16/24 encoding — its `_in_play_card_ids`, `_status_flags`, `opp_active`
  resolution, and `GameStateTracker`/`PrizeTracker` usage are the reference behavior this
  adapter should reuse, not reinvent.
- `Imitation-Learning/observation/card_data.py` and `Ceruledge-RL/card_data.py` both
  parse the same `Decks/Deck-Builder/EN_Card_Data.csv`, keyed by the same CardData ID the
  engine emits as `Card.id`/`Pokemon.id`. **Card IDs are already a shared vocabulary
  across old and new code** — no ID crosswalk is needed in this adapter.
- `observation.live_state.RawPokemon` and `observation.encoder.GameState` are the target
  shapes (see `Imitation-Learning/observation/live_state.py` and `encoder.py`).

## Field-by-field mapping

### `RawPokemon` (per board Pokemon, both sides — the engine's `Pokemon` type is already
side-symmetric, matching the any-deck design)

| `RawPokemon` field | Source | Notes |
|---|---|---|
| `card_id` | `poke.id` | direct |
| `hp` / `max_hp` | `poke.hp` / `poke.maxHp` | direct; spec 14 confirmed these are already effect-resolved |
| `energy_cards` | `tuple(c.id for c in poke.energyCards)` | direct |
| `tool_card_id` | `poke.tools[0].id if poke.tools else None` | **open item** — see below, engine allows a `list`, schema wants one id |
| `pre_evolution_ids` | `tuple(c.id for c in poke.preEvolution)` | direct |
| `is_basic` | `len(poke.preEvolution) == 0` | derived — no explicit stage field on `Pokemon`; a Pokemon currently in basic form has never evolved, so an empty `preEvolution` is exact, not a heuristic |
| `is_active` | `poke is ps.active[0]` (by identity/serial) vs. bench membership | direct from which list it came from |
| `new_in_play` | `poke.appearThisTurn or poke.serial in tracker.evolved_serials` | reuse `GameStateTracker.evolved_serials` verbatim — same logic `features.py` already relies on |
| `special_conditions` | subset of `PlayerState`'s 5 booleans, **only when this Pokemon is that side's Active** | matches spec's own "Active only" rule; bench Pokemon always get `()` |

### `GameState` (whole-board)

| `GameState` field | Source |
|---|---|
| `our_deck` | not directly observable; per spec 13a's zone design this is the *remaining* deck, i.e. full 60-card list minus everything accounted for elsewhere — same deck-by-elimination this adapter must run (see Prize/deck tracking below) |
| `our_hand` | `ps.hand` (card ids); `None` for opponent hand, which `GameState` doesn't ask for anyway |
| `our_discard` | `ps.discard` card ids |
| `our_prizes_known` / `our_prizes_hidden_count` | from `PrizeTracker` (reused, see below), not from `ps.prize` directly — the engine's own `prize` list is `None`-elemented (face-down) for essentially all of our unrevealed prizes; `PrizeTracker`'s deck-by-elimination inference is what actually resolves identities, exactly as `features.py` already uses it |
| `opponent_discard` | `opp_ps.discard` card ids |
| `board` | one `BoardPokemonState` per `Pokemon` in `ps.active + ps.bench` (role `our_active`/`our_bench`) and `opp_ps.active + opp_ps.bench` (role `opponent_active`/`opponent_bench`) |
| `stadium_card_id` | `state.stadium[0].id if state.stadium else None` |
| `turn_number` | `state.turn` |

## Reused, not rebuilt

- **`PrizeTracker`** (`Ceruledge-RL/prize_check.py`) — its deck-by-elimination inference
  is orthogonal to observation *encoding*; spec 14 only re-audited stat baking, not prize
  logic. This adapter should take an existing tracker instance (or construct one
  internally, mirroring `train.py`'s one-tracker-per-episode pattern) rather than
  duplicate its serial-tracking logic.
- **`GameStateTracker`** (`Ceruledge-RL/features.py`) — same reasoning for
  `evolved_serials` (feeds `new_in_play`) and per-turn reset semantics.
- Both trackers are currently deck-specific (`DECK_CARDS`/`FULL_DECK` are Ceruledge's
  fixed 60). That's fine for this adapter's actual current use (still the Ceruledge
  policy's own rollout) even though the *target* schema (`GameState`) is deck-agnostic in
  shape. Making prize/deck tracking itself deck-agnostic is out of scope here.

## Open items — resolutions

1. **Multiple attached Tools.** Resolved as `poke.tools[0].id if poke.tools else None`
   (`live_adapter._raw_pokemon`). No further audit of spec 12's registry was done for
   dual-Tool meta cards; if one surfaces, this silently keeps the first and drops the
   rest — acceptable for now, revisit if it ever matters.
2. **`our_deck` construction.** Resolved with a dedicated `_deck_remainder` helper in
   `live_adapter.py` (not a `PrizeTracker` extension), running the same
   `Counter(FULL_DECK) - hand - discard - in_play - prize_counts` subtraction
   `features.py` already does inline. Returns `[]` before prize resolution — see "A gap
   found during implementation" below; this turned out to be a real representational
   gap, not just an implementation choice.
3. **`is_active` resolution when `ps.active` is empty.** Resolved: no special case
   needed. `_board_states` only emits a `BoardPokemonState` for slots that actually hold
   a Pokemon; `ps.active == [None]` (face-down or genuinely absent) simply contributes no
   `"our_active"` entry, and `encoder.build_observation` already pads any missing role to
   its full capacity via `_pad_word()`. Confirmed against real recorded data
   (`test_live_adapter_replay.py`), which contains many empty-active states.
4. **Opponent's own hand/deck.** Confirmed: `GameState` has no fields for them at all, so
   there was nothing to implement — the adapter simply never touches `opp_ps.hand`.

## A gap found during implementation (not in the original open-items list)

**`our_deck` has no way to represent "cards exist, identity unknown."** Spec 13a's deck
zone (unlike its prize zone) has no `hidden_count`/UNK mechanism — `encoder.py` calls
`build_zone_array(state.our_deck, DECK_CAPACITY)` with no hidden-count argument. Before
the prize tracker's first full-deck resolution, individual card identity genuinely cannot
be split between "remaining deck" and "prizes" (a real information limit, not a missing
feature), so `_deck_remainder` returns `[]` in that window — the deck zone reads as
entirely empty (all PAD) until the first search, rather than "N unresolved cards present."
This is a real, if minor, representational gap in the locked spec 13a design, called out
here rather than routed around by modifying the already-locked encoder.

## Validation results

- **Unit tests** (`test_live_adapter.py`, 13 tests): board/role mapping, Tool
  first-only, `is_basic` derivation, `new_in_play` via both `appearThisTurn` and the
  per-side evolved-serial trackers (including the opponent-perspective case — the one
  test that would fail if the adapter used only one tracker for both sides), special
  conditions scoped to Active only, hand/discard/stadium/turn direct passthrough,
  deck/prize resolution both before and after the first search, the `obs.current is
  None` guard, and one full `build_game_state` → `build_observation` round trip.
- **Real-episode validation** (`test_live_adapter_replay.py`): converts real recorded
  engine JSON from `Imitation-Learning/Top-ladder-data/7-12/` into genuine
  `cg_download.api.Observation` instances via the project's own existing
  `cg_download.utils.to_dataclass` bridge (not a new parser), runs `build_game_state` +
  `build_observation` across 8 full episodes (2,170 real `obs.current is not None`
  states, both perspectives, with per-episode tracker continuity matching `train.py`'s
  lifecycle), and asserts every board word's raw fields match its source Pokemon
  exactly. Zero exceptions, zero mismatches. Skips itself if the data archive isn't
  present in the checkout.
- **The originally planned old-vs-new cross-check against `features.py` did not apply.**
  Inspection of the recorded replay data found its card ids don't match
  `features.DECK_CARDS` at all — this Top-ladder data is general meta play, not
  Ceruledge games. `features.py`/`PrizeTracker`'s deck-by-elimination is inherently
  Ceruledge-specific, so running it against this data would misinterpret it rather than
  validate anything. The direct-passthrough invariant check above is the correctness
  signal that actually applies to arbitrary-deck data, and is arguably the more
  important one to have exercised given spec 13a's board/zone encoding is meant to be
  any-deck symmetric.
- All 24 pre-existing `observation/` tests still pass unmodified (no regressions).

## Interfaces / seams

- `Imitation-Learning/observation/live_adapter.py`, exporting one function:
  `build_game_state(obs: Observation, our_idx: int, prize_tracker: PrizeTracker,
  our_tracker: GameStateTracker, opponent_tracker: GameStateTracker) -> GameState`. Takes
  **two** trackers, not one — evolution-serial tracking is inherently per-side
  (`EVOLVE` logs carry the evolving player's index), so a correct opponent-side
  `new_in_play` needs `opponent_tracker.update(obs, 1 - our_idx)` run independently of
  the caller's own-perspective tracker. Both trackers are plain, already-tested
  `GameStateTracker` instances — this module owns calling `.update()` on both (and on
  `prize_tracker`) every call, so callers can't forget to.
- Adapter module lives under `Imitation-Learning/observation/` (alongside the package it
  feeds) but imports `Ceruledge-RL/prize_check.py` and `Ceruledge-RL/features.py` directly
  — first cross-directory import between the two trees. Resolved with the same
  `sys.path.insert` bootstrap `Ceruledge-RL/test_features.py` already uses for the
  opposite direction (repo root for `cg_download`, then `Ceruledge-RL` itself so its
  bare `import card_data`/`import stat_bakes` etc. resolve), not a package install.

## Out of scope

- Packing `list[Word]` into model input tensors, role/type embeddings, or any SVN v2
  model code (no such model exists yet — future spec).
- Wiring this adapter into `train.py`'s PPO rollout loop.
- Making `PrizeTracker`/`GameStateTracker` deck-agnostic.
- Anything about opponent hand/deck/prize identity (never modeled, per spec 13a).
