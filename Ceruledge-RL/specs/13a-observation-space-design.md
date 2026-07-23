# 13a — Card-Zone Observation Space Design

Part of [`13-card-zone-observation-space.md`](13-card-zone-observation-space.md).

Status: **design complete and transcribed into tested standalone code under
`Imitation-Learning/observation/` (2026-07-21). Structure, word budget (174), PAD/UNK
masking, and every field width are resolved, including the
downstream effect-baking pass (spec 14) and the `special_energy_id` fallback field it
added. Only minor implementation-time details remain open (see "Open questions") — none
structural. The live-engine adapter and training consumer remain open; 13b was deferred
and is to be written retroactively from implementation experience.**

## Purpose

Define the full observation structure surrounding the Pokémon board-slot word (spec 11):
word budget for every zone, how a card's representation behaves as it moves between zones
(deck → hand → board → attached → discard), and how attachment/evolution information is
represented without needing cross-token relational binding.

**This is a planning deliverable.** No parser, model code, or training loop is written as
part of 13a — that begins in 13b once this structure is signed off.

## Governing principle

Two representations are available for "a card exists somewhere in the game," and the
choice between them is driven by one question: **does this population have high identity
cardinality where which specific card occupies which specific slot matters, or is it
low-cardinality and fungible within ID?**

- **High cardinality, positionally significant → individual words.** Deck, hand, discard,
  and board Pokémon draw from up to 232 possible card IDs (115 Pokémon / 99 Trainer / 18
  Energy, per spec 12), and for board Pokémon specifically, *which* Pokémon sits in *which*
  slot is strategically meaningful. These all get one word per card via spec 11's static
  template (or the Trainer/Energy equivalent from spec 11b).
- **Low cardinality, fungible within ID → compact fields on the owning word.** Attached
  Energy (~18 possible IDs), attached Tool (at most 1 per Pokémon by rule), and evolution
  history (chain depth ~3) are all populations where multiple copies of the same ID are
  interchangeable — nothing about *which* physical copy is attached matters to game state
  or to any legal action. A full per-ID count vector (or bounded ID list) is exactly as
  lossless as individual words here, at far lower cost, and — unlike individual words —
  gives the model an *exact* count rather than one it has to recover through attention
  pooling (see "Why compact fields, not individual attachment words" below).

This principle replaces an earlier design pass (2026-07-16, same day) that gave every
attachment its own persistent word plus a location+role additive-embedding mechanism to
bind attachments to their host Pokémon. That mechanism is no longer needed: it solved a
cross-token binding problem that only exists if attachments get separate tokens in the
first place, and the fungibility argument above shows they don't need to.

## Zone structure: fixed-capacity padded arrays

Each zone (deck, hand, discard, prizes, board) is a **fixed-capacity array of words**,
sized to that zone's own maximum, padded when under capacity. A card changing zone (e.g.
Energy leaving hand to attach to a bench Pokémon) means: the card's word disappears from
the hand array (that slot becomes an explicit `PAD` token) and its information is folded
into the receiving Pokémon's compact attachment fields — no new word is created anywhere,
since attachments aren't separate words. For zone-to-zone moves that don't involve
attachment (e.g. a card drawn from deck to hand, or discarded from hand), the card's word
simply stops appearing in one zone's array and starts appearing in the other's.

This does **not** require tracking a persistent identity-to-slot binding for a specific
physical card across the whole game (an earlier framing this session considered and moved
away from) — each zone's array is repopulated by canonical order every time it's computed,
the same fixed-slot-count/variable-content pattern used elsewhere (e.g. DETR's object
queries). Total observation length is fixed because each array's *capacity* is fixed, not
because any single word has cross-zone continuity.

**Canonical ordering within an array:** cards within deck/hand/discard arrays are sorted by
static card-ID (deterministic tiebreak on ties) rather than any gameplay-derived order.
This matters most for the deck: deck order is hidden/random even to the owning player and
carries no real information, so a consistent canonical order avoids the model reading
spurious signal into array position.

## `PAD` vs `UNK` — two distinct null-like tokens, with different attention treatment

- **`PAD`** — this array slot holds no card at all; the zone is currently under its padded
  capacity.
- **`UNK`** — this slot holds a real card whose identity is hidden (own unrevealed prizes;
  reuses spec 11's existing UNK card-ID embedding).

Both get their own dedicated learned embedding — the model learns what each means through
training, the same role `[PAD]` plays in BERT-style masking or a "no object" class plays in
DETR. But they're treated differently in attention, because they mean different things:

- **`PAD` is masked out of attention entirely** (standard technique: add `−∞` to its
  attention logits before the softmax, both in the self-attention layers and — this is the
  easy-to-miss part — at the final attention-pooling step too, not just internally; a
  well-known gotcha in sentence-embedding-style pooling is forgetting to exclude pad
  positions there, letting a fixed, contentless vector dilute the real pooled signal). There
  is genuinely nothing at a `PAD` slot to inform the model about, so nothing should attend to
  it and its own output is never read.
- **`UNK` is not masked** — it represents a real card, just one whose identity is hidden,
  and that fact is itself informative (an unrevealed prize is a live resource; hand size is
  a standard TCG heuristic for available options even when contents are unknown). It
  participates in attention normally via its own dedicated "hidden card" embedding.

The closest architectural precedent for this whole pattern (fixed max-entity-count sequence,
masked-out absent slots) is transformer-based multi-agent RL more than NLP — e.g. AlphaStar's
unit encoder for StarCraft II, which is structurally close to this board/zone card-list
design.

## Word budget

| Zone | Capacity | Basis |
|---|---:|---|
| Friendly deck (remaining) | 47 | `60 − 7 (opening hand) − 6 (prizes)` — structural max for the overwhelming majority of the game; see deck overflow note below |
| Friendly prizes | 6 | Fixed by rule, no loophole (`EXTRA_PRIZE`-tagged effects deplete the same 6 faster, never grant more); `UNK` identity until taken |
| Friendly hand | 20 | Soft cap — see note below |
| Friendly discard | 40 | Soft cap — see note below |
| Opponent discard | 40 | Face-up/known; same mechanism as friendly discard |
| Board Pokémon (both sides) | 18 | `(1 active + 8 max bench via Area Zero Underdepths) × 2 sides` — exact structural max, no loophole |
| Stadium | 1 | The in-play Stadium card's own static template (spec 11b), or `PAD` if none is in play. Its own dedicated word, not folded into global state. |
| Global state | 1 | Turn metadata, opponent hidden-zone counts (opponent deck/hand/prize remaining counts, etc.) |
| Pooling query | 1 | No physical representation — attention-pooling target only ([[svn_v2_architecture]] Stage 6) |
| **Total** | **174** | Locked |

Opponent side gets individual words only for active/bench/discard (face-up); opponent deck,
hand, and prizes are represented as counts within the global-state word, not individual
arrays — this was already decided earlier in 13a and is unchanged.

**Hand and discard are soft caps, not exact structural maxima**, unlike deck/prizes/board.
20 for hand is chosen with headroom against stackable draw effects present in the audited
meta (Alakazam draws 3, Fezandipiti draws 3, Kadabra/Mega Kangaskhan draw 2, Comfey draws 3
to both players — per spec 11a's tag catalog). 40 for discard is a practical bound, not a
claim that a discard pile can never exceed it (in principle nearly the whole 60-card deck
could end up discarded over a long game).

**Deck's 47 cap has one known rare loophole, unlike prizes/board.** Deck size isn't strictly
monotonic — a few audited effects shuffle cards back into the deck mid-game (`SELF_MILL`:
"shuffle this Pokémon and all attached cards into your deck," per spec 11a). Since taking a
prize transfers 1-for-1 into hand (no net change to the "already left the deck" total), the
only way deck size can exceed 47 is a shuffle-back effect returning more to the deck than has
structurally accumulated elsewhere — an extreme, unlikely-in-practice edge case, but not a
hard rules-enforced ceiling the way prizes-at-6 or board-at-18 are. Given the overflow
mechanism below, it's extended to deck too as cheap insurance, expected to essentially never
fire.

**Overflow handling:** if real occupancy would exceed a capped zone's array (hand, discard,
or — in the rare case above — deck), the excess is not silently dropped. Add one explicit
overflow-count scalar per zone: "N cards beyond the padded array are also present here; their
individual identities aren't represented." Prizes and board Pokémon don't need this field —
those caps are true rules-enforced maximums with no loophole. This follows the no-silent-loss
convention already established in spec 11/spec 12 (explicit known gaps, never silent
zero-vectors).

## Why compact fields, not individual attachment words

An earlier pass this session gave each attached Energy/Tool and each buried evolution stage
its own persistent word, bound to its host Pokémon via an additive `(location, role)`
embedding pair. Revisiting that in light of the word-budget exercise surfaced a cleaner
alternative:

- **Fungibility.** Multiple copies of the same attached Energy ID are interchangeable —
  nothing in the rules or in the audited effect catalog (spec 11a) requires distinguishing
  *which* physical copy is attached, only how many of which type.
- **Action-space targeting doesn't need instance-level distinction either.** Effects that
  reference attached Energy (e.g. discard-cost effects, `ENERGY_AMPLIFY`-style per-count
  scaling) target by type or count, never by a specific physical instance among identical
  ones — so there's no future action-space need this would have uniquely served.
- **Compact fields are strictly better on the exact axis individual words were weak on.**
  The earlier design's own stated risk was that attention pooling (`softmax(scores) @
  words`) doesn't reliably preserve counts across duplicate identical tokens — three
  identical attached-Energy words stay identical through every permutation-equivariant
  transformer layer, and softmax normalization doesn't scale cleanly with duplicate count.
  A per-ID count vector sidesteps this by being an *exact*, precomputed value rather than
  something inferred through pooling — consistent with spec 11's own philosophy
  ("precompute arithmetic, don't make the model learn it").

Resolution: each board Pokémon word carries, directly as live-state fields (widening what
spec 11 already sketched):

- `attached_energy_counts` — a small vector bucketed by type/category rather than exact
  card ID (11-dim, locked in spec 11's "Base field schema" — 9 types + `Rainbow` +
  `Team Rocket Energy`, with an explicit Special Energy → bucket mapping), replacing the
  single scalar `attached Energy count`.
- `special_energy_id` — a 10-dim presence-based identity vector (one per meta Special
  Energy card), added during spec 14's audit as a fallback signal for Special Energy
  effects that don't fit any bakeable KO-math category — deliberately imperfect, same
  no-separate-token treatment as everything else here.
- `tool_template` — the attached Tool's full static template (spec 11b card-ID embedding +
  effect tags, complete), folded in as an input field rather than a separate token; see
  "Tools" below for why this differs slightly from a bare categorical ID.
- `evolved_from` — a small bounded list of prior-stage card IDs (chain depth ~3), for the
  handful of effects that reference pre-evolution identity (e.g. `ATTACK_INHERIT` in spec
  11a's catalog).

This makes each board Pokémon word fully self-contained — matching spec 11's original
live-state design intent, no cross-token binding required. The board-*position* role
embedding already established in spec 11/[[svn_v2_architecture]] (our-active / our-bench /
opponent-active / opponent-bench) is unaffected by this change; it was never part of the
attachment-binding problem, only the now-unnecessary attachment-to-host binding was.

### Tools specifically — fused, decided on different grounds than Energy/evolution

Tools don't have Energy's fungibility problem (at most 1 per Pokémon, so no duplicate-token
pooling issue exists to justify fusing on those grounds). The case for fusing anyway is
different, and worth recording distinctly since it was a live discussion, not an obvious
extension of the Energy/evolution reasoning:

- **No information-loss argument for separating it.** The only real case for a standalone
  Tool token is that giving the model multiple rounds of dedicated cross-attention might
  make Tool-interaction reasoning marginally easier to learn than disentangling one fused
  vector — a soft, empirical claim, not a correctness one. Nothing is actually lost by
  fusing, unlike the Energy pooling-count problem, which was a real information gap.
- **A Tool is semantically host-scoped, not a free-standing board entity** — it only ever
  matters in relation to the Pokémon it's attached to, unlike a benched Pokémon, which is
  meaningfully itself regardless of context. That's exactly the case spec 11/SVN v2's
  "MLP before attention" design already exists for: building one coherent entity
  representation before any cross-board reasoning.
- **Cost.** A separate per-position Tool slot (mirroring the 18-word board section) would
  cost up to +18 words for something that's `PAD` most of the time (most Pokémon on the
  board don't carry a Tool, especially early game) — a meaningful chunk of the 174-word
  budget for a usually-absent field.

**Implementation note for 13b, not a structural blocker here:** if the Tool's spec-11b
static template ends up comparably wide to Pokémon's own attribute/effect block (61 dims per
ability-shaped row, 70 per attack-shaped row, per spec 11a — narrowed from an earlier 108/117
once the presence+magnitude pair was collapsed during code transcription), concatenating it
raw into the host's attribute vector would meaningfully widen `D_ATTR` (currently 26, per
`MODEL-ARCHITECTURE.md`/the SVN v2 architecture notes). Likely resolution is a small
dedicated projection of the Tool's template to a fixed-width summary before fusing, rather
than raw concatenation — an open detail for 13b, not decided here.

## Compute / hyperparameters (recorded from this session's discussion)

- **`D_MODEL`** — staying at 128 for now. 64 considered plausible; treated as an open
  experiment for 13b, not a blocker here.
- **Transformer depth** — starting at 2 layers (current), expected to grow. Depth scales
  transformer-stack compute *linearly*: both the attention term (`O(L·n²·d)`) and the FFN
  term (`O(L·n·d·d_ff)`) are linear in layer count `L`. Going 2→3 layers is roughly +50%
  transformer-stack compute, not a multiplicative blowup. At `n≈173`, `d=128`, even 3-4
  layers remains a small computation (tens of millions of FLOPs per forward pass) for an RL
  policy needing fast self-play inference. The growth from ~62 to ~173 tokens (driven by
  attention's quadratic dependence on `n`) is the larger compute driver versus the original
  ~24-word model, more so than depth — worth benchmarking directly in 13b, not a design
  blocker now.

## Success criteria

- Every zone's word count is fixed at its stated capacity regardless of current occupancy;
  no zone's array grows or shrinks the total observation length.
- `PAD` (no card) and `UNK` (hidden card) remain distinguishable at every slot where both
  are possible.
- Deck, prizes, and board-Pokémon capacities are exact structural maxima (never exceeded by
  game rules); hand and discard capacities are explicit soft caps with an overflow-count
  field covering the rare excess case, not silent truncation.
- Every board Pokémon word is self-contained: attachment/evolution information lives as
  compact fields on that word, with no separate words or cross-token binding required to
  recover it.
- Opponent hidden zones (deck, hand, prizes) are represented as counts within global state,
  never individual words; opponent revealed zones (active, bench, discard) use the same
  per-card word mechanism as the friendly side.
- Deck/hand/discard array ordering is canonical (by static card-ID), not gameplay-derived,
  so equivalent game states produce equivalent representations.

## Open questions

- Exact overflow-count field format/placement for hand, discard, and (rare case) deck.
- `tool_template`'s exact projected width, and whether it needs a dedicated down-projection
  before fusing into the host's attribute vector (flagged in "Tools" above) — an
  implementation-time detail for 13b, not a structural blocker.
- Whether `special_energy_id` needs to be multi-hot (multiple different Special Energy IDs
  on one Pokémon at once) — presumed yes, not yet explicitly confirmed (spec 14).
- Real transformer depth and `D_MODEL`, to be benchmarked empirically once 13b is
  implemented (starting point: 2 layers, `D_MODEL=128`, per this session's discussion).
- Whether the action space eventually needs anything beyond type/count-level targeting for
  attachments — the fungibility argument above says no, but this is worth reconfirming once
  action-space design actually starts (out of scope for 13a).
- **Future experiment, explicitly not scoped for 13a:** temporary effect/status vectors
  (e.g. a general "can't attack this turn" flag beyond the specific locks/conditions spec
  11a's tag catalog already covers) — noted for later, not designed now.

## Explicitly out of scope

- Spec 11's Pokémon static-template/live-state field contents (already decided there,
  now extended per "Why compact fields" above).
- Effect baking (retreat cost, weakness, attack cost, flat damage deltas) — see
  [`14-effect-baking-audit.md`](14-effect-baking-audit.md), complete.
- Any code, parser, or model implementation — that's 13b, gated on this document being
  signed off.
- Action-space design (legal-action masking, how attachments get targeted by play
  decisions) beyond the single forward-looking note above.
