# PrizeTracker

## Purpose
Track which of our own 6 prize cards are which, by elimination, and keep that knowledge
current as prizes are taken. The tracker accepts the player's authoritative submitted
60-card deck, so the elimination logic works for arbitrary decks. Its legacy `vector()`
layout remains the fixed Ceruledge feature order.

## Behavior

### State machine
Two states, latching:

- **UNKNOWN** (initial): we have never validated a full remaining-deck reveal.
  `vector()` = `[0]*15 + [1]`.
- **KNOWN**: entered after `obs.select.deck` passes every strict validation gate below.
  Never returns to UNKNOWN within a game. `reset()` returns to UNKNOWN.

### Internal state
- `prizes_known: bool`
- `prize_counts: Counter[int]` — card id → count still prized
- `known_serials: set[int]` — serials confirmed NOT to be prizes
- `full_deck: tuple[int, ...]` — the authoritative submitted 60-card deck supplied to
  `PrizeTracker(full_deck)`

### update(obs, our_idx) — called every step where it's our decision
1. Collect all visible own-side `(id, serial)` pairs ("seen"):
   - `ps.hand`, `ps.discard`
   - in-play Pokémon (`ps.active` + `ps.bench`, skipping `None`), and for each: its own id/serial plus `energyCards`, `tools`, `preEvolution`
   - `obs.select.deck` only when `obs.current.yourIndex == our_idx`
   - owned cards in the shared Stadium and looking zones, gated by `Card.playerIndex`
   - exact `MOVE_CARD` logs leaving `AreaType.PRIZE`, which can precede the taken card
     appearing in a normal visible zone
   - **excluded:** `ps.prize` entries (those ARE prizes), opponent-owned cards, and the
     acting player's selection data when this tracker belongs to the other side.
2. If our own `obs.select.deck` is present (first time or resync):
   - Require `len(obs.select.deck) == ps.deckCount`; otherwise raise
     `PrizeTrackerInvariantError`.
   - Also count `obs.select.effect` when `effect.playerIndex == our_idx` — an owned
     trainer being resolved (e.g. Ultra Ball) sits in **no zone** while its search
     executes; only `select.effect` references it. Do not count an opponent-owned
     shared Stadium effect: either player can use it to search their own deck, but the
     Stadium remains a card from its owner's deck.
   - Dedupe seen cards by serial (the effect source may be an in-play Pokémon already counted).
   - Require every visible card/count to be a subset of the supplied deck.
   - `prize_counts = Counter(full_deck) − Counter(deduped seen ids)`.
   - Require `sum(prize_counts.values()) == len(ps.prize)`.
   - Only after every check passes, set `known_serials` and `prizes_known = True`.
3. Else if `prizes_known`: for each seen serial not in `known_serials`, the card must be
   a former prize → decrement its count and record its serial. An impossible card/count
   raises immediately.
4. After every known-state update, require the inferred total to equal the engine's
   remaining Prize count. No invalid observation silently overwrites or advances state.

### vector() → list[int], length 16
`[prize_counts[cid] for cid in DECK_CARDS] + [flag]` where flag = 0 if known else 1.
`DECK_CARDS` order (from features.py): Ceruledge ex, Charcadet, Solrock, Lunatone, Drilbur, Fire, Fighting, Night Stretcher, Brilliant Blender, Fighting Gong, Ultra Ball, Poké Pad, Boss's Orders, Explorer's Guidance, Carmine.

### Example
First Ultra Ball search: seen = hand(5) + discard(1, the Ultra Ball cost... etc) + in-play + revealed deck. If 60 − seen leaves {Fighting×3, Carmine×1, Ceruledge ex×1, Fire×1}, then
`vector() == [1,0,0,0,0,1,3,0,0,0,0,0,0,0,1,0]` (sum 6, flag 0).
Later we take a prize; a Fighting Energy with an unseen serial appears in hand → Fighting slot drops to 2, sum 5.

## Data
- Reads: `Observation` (from `cg_download.api`) — fields listed above.
- Constructor input: the player's authoritative submitted 60-card list. Replay consumers
  extract this from the initial deck-submission action; live consumers pass the same list
  supplied to `battle_start`.
- Reuses from `features.py`: `DECK_CARDS` only for the legacy Ceruledge `vector()` order.
- Writes: nothing; pure in-memory state per game.

## Interfaces / seams
- Constructed and reset per game by whoever owns game state. `GameStateTracker` supplies
  Ceruledge's fixed deck by default but accepts an explicit arbitrary deck.
- `update()` is idempotent for a repeated identical observation. `GameStateTracker`
  retains the last observation object and compares by identity; retaining it prevents
  Python from recycling a freed object's numeric ID and silently skipping the next
  distinct replay observation.

## Out of scope
- Inferring a submitted deck that the caller did not provide; opponent-hidden deck
  composition; persistence.
- A generalized replacement for the legacy 15-card `vector()` layout. Generalized
  consumers use `prize_counts` directly.

## Test cases (smoke_test_prize_check.py)
Unit (namespace stubs, no sim):
1. Fresh tracker → `[0]*15 + [1]`.
2. Missing/invalid submitted deck → construction fails.
3. Partial `select.deck` reveal or mismatched submitted deck → loud invariant failure,
   tracker remains UNKNOWN.
4. Synthetic obs with a validated full-deck reveal → correct 6-card counts, flag 0.
5. After (4), obs where a card with a new serial appears in hand → that slot decremented.
6. Re-seen known serial → no double decrement.
7. Evolved Pokémon with `preEvolution` attached → pre-evolution card not counted as prized.
8. Real arbitrary-deck replay → uses each player's submitted deck and maintains
   `sum(prize_counts) == len(ps.prize)` through full-deck searches and prize takes.

Integration (full sim, pattern of `smoke_test_ceruledge_rl.py`):
- 5+ games, tracker updated on every step for our side.
- Invariants each step: pre-search vector is all-zeros+flag; post-search `sum(counts) == len(ps.prize)` and all counts ≥ 0.
- Print when prizes became known, composition, and each detected take.

## Open questions
- None.
