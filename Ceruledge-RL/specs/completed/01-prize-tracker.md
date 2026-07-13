# PrizeTracker

## Purpose
Track which of our own 6 prize cards are which, by elimination, and keep that knowledge current as prizes are taken. Output is designed to be consumed directly as network features.

## Behavior

### State machine
Two states, latching:

- **UNKNOWN** (initial): we have never seen our full deck. `vector()` = `[0]*15 + [1]`.
- **KNOWN**: entered the first time `obs.select.deck` is non-empty (a deck search — Ultra Ball, Poké Pad, Brilliant Blender, Fighting Gong...). Never returns to UNKNOWN within a game. `reset()` returns to UNKNOWN.

### Internal state
- `prizes_known: bool`
- `prize_counts: Counter[int]` — card id → count still prized
- `known_serials: set[int]` — serials confirmed NOT to be prizes

### update(obs, our_idx) — called every step where it's our decision
1. Collect all visible own-side `(id, serial)` pairs ("seen"):
   - `ps.hand`, `ps.discard`
   - in-play Pokémon (`ps.active` + `ps.bench`, skipping `None`), and for each: its own id/serial plus `energyCards`, `tools`, `preEvolution`
   - `obs.select.deck` when present
   - **excluded:** `ps.prize` entries (those ARE prizes), everything on the opponent's side, and the shared `obs.current.stadium` / `obs.current.looking` zones — they carry no owner field, so in a mirror match an opponent card there would corrupt the counts. Our deck runs no stadium, and our own cards passing through `looking` are detected once they land in hand/discard/play.
2. If `obs.select.deck` is present (first time or resync):
   - Also count `obs.select.effect` — the trainer being resolved (e.g. the Ultra Ball itself) sits in **no zone** while its search executes; only `select.effect` references it. Omitting it overcounts prizes by exactly 1 (found empirically).
   - Dedupe seen cards by serial (the effect source may be an in-play Pokémon already counted).
   - `prize_counts = Counter(FULL_DECK) − Counter(deduped seen ids)`; `known_serials = {seen serials}`; `prizes_known = True`.
3. Else if `prizes_known`: for each seen serial not in `known_serials`, the card must be a former prize → `prize_counts[id] -= 1` (floor 0), add serial to `known_serials`.

### vector() → list[int], length 16
`[prize_counts[cid] for cid in DECK_CARDS] + [flag]` where flag = 0 if known else 1.
`DECK_CARDS` order (from features.py): Ceruledge ex, Charcadet, Solrock, Lunatone, Drilbur, Fire, Fighting, Night Stretcher, Brilliant Blender, Fighting Gong, Ultra Ball, Poké Pad, Boss's Orders, Explorer's Guidance, Carmine.

### Example
First Ultra Ball search: seen = hand(5) + discard(1, the Ultra Ball cost... etc) + in-play + revealed deck. If 60 − seen leaves {Fighting×3, Carmine×1, Ceruledge ex×1, Fire×1}, then
`vector() == [1,0,0,0,0,1,3,0,0,0,0,0,0,0,1,0]` (sum 6, flag 0).
Later we take a prize; a Fighting Energy with an unseen serial appears in hand → Fighting slot drops to 2, sum 5.

## Data
- Reads: `Observation` (from `cg_download.api`) — fields listed above.
- Reuses from `features.py`: `DECK_CARDS`, `FULL_DECK` (and `CARD_IDX` if convenient).
- Writes: nothing; pure in-memory state per game.

## Interfaces / seams
- Constructed and reset per game by whoever owns game state (later: `GameStateTracker` may hold one; not in v1).
- `update()` is idempotent for a repeated identical observation (serial logic makes re-processing safe).

## Out of scope
- Opponent prizes; decks other than the Ceruledge list; persistence.

## Test cases (smoke_test_prize_check.py)
Unit (namespace stubs, no sim):
1. Fresh tracker → `[0]*15 + [1]`.
2. Synthetic obs with `select.deck` covering 54 of 60 cards → correct 6-card counts, flag 0.
3. After (2), obs where a card with a new serial appears in hand → that slot decremented.
4. Re-seen known serial → no double decrement.
5. Evolved Pokémon with `preEvolution` attached → pre-evolution card not counted as prized.

Integration (full sim, pattern of `smoke_test_ceruledge_rl.py`):
- 5+ games, tracker updated on every step for our side.
- Invariants each step: pre-search vector is all-zeros+flag; post-search `sum(counts) == len(ps.prize)` and all counts ≥ 0.
- Print when prizes became known, composition, and each detected take.

## Open questions
- None.
