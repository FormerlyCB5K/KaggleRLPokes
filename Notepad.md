# Ceruledge Policy Network — Feature Spec

## Pokemon Slots
12 total: your active (1) + your bench (5) + opp active (1) + opp bench (5)

Empty slots are zero-padded.

| Feature | Size | Normalization / Notes |
|---|---|---|
| `card_onehot` | 5 | Ceruledge=0, Charcadet=1, Solrock=2, Lunatone=3, Drilbur=4 |
| `hp_max` | 1 | /270 |
| `hp_current` | 1 | /270 |
| `fire_energy` | 1 | /4 |
| `fighting_energy` | 1 | /4 |
| `retreat_cost` | 1 | /2 (max in this deck) |
| `attack_damage` | 1 | /410 (deck max). Values: Charcadet=0, Solrock=70, Drilbur=20, Lunatone=50, Ceruledge=30+(20×total_energy_in_discard) |
| `can_attack` | 1 | binary |

**12 floats per slot. Total: 12 × 12 = 144 floats.**

---

## Global State Features
Single flat vector, not slotted.

| Feature | Normalization / Notes |
|---|---|
| `my_prizes_remaining` | /6 |
| `opp_prizes_remaining` | /6 |
| `my_deck_size` | /47 (start with cards in hand + prizes out) |
| `my_hand_size` | /10 |
| `opp_hand_size` | /10 |
| `energy_attached_this_turn` | binary |
| `lunar_cycle_used_this_turn` | binary |
| `supporter_used_this_turn` | binary |
| `solrock_lunatone_combo` | binary — 1 if both Solrock AND Lunatone are in play on your side |
| `fire_in_hand` | /4 |
| `fighting_in_hand` | /4 |
| `attacker_count` | /4 — sum of Ceruledge + Charcadet currently in play on your side |
| `turn_count` | min(turn, 10) / 10 |
| `turn_order` | 0.0 = we go first, 1.0 = we go second; 0.5 before firstPlayer resolves |

**14 floats.**

---

## Zone Words: Hand, Discard, Prize Cards
Three words, each encoded by the **same shared MLP** (16 → D_MODEL).

**Input: 16 floats**

| Feature | Size | Notes |
|---|---|---|
| `card_counts[15]` | 15 | One per unique card in deck, normalized by that card's count in the deck list. Set to -1 for all 15 when unknown. |
| `is_unknown` | 1 | 1 = counts are unknown; 0 = known. |

**Unknown behaviour:** when `is_unknown=1`, all 15 count dims are set to -1. This lets the MLP learn a distinct "I don't know" representation rather than conflating unknown with empty (all zeros).

**Prize tracking:** prizes start unknown (`is_unknown=1`). After any full deck search that populates `obs.select.deck`, call `compute_prizes()` (see `prize_check.py`) to infer prizes by elimination. Once known, maintain the prize Counter by subtracting each card as you take it (you see the card when you claim the prize).

Hand and discard are always known, so their `is_unknown` flag is permanently 0.

**Unique card order (indices 0–14):**

| Idx | Card | Count in deck |
|---|---|---|
| 0 | Ceruledge ex (320) | 4 |
| 1 | Charcadet (796) | 4 |
| 2 | Solrock (676) | 2 |
| 3 | Lunatone (675) | 2 |
| 4 | Drilbur (81) | 1 |
| 5 | Fire Energy (2) | 7 |
| 6 | Fighting Energy (6) | 13 |
| 7 | Night Stretcher (1097) | 4 |
| 8 | Brilliant Blender (1128) | 1 |
| 9 | Fighting Gong (1142) | 4 |
| 10 | Ultra Ball (1121) | 4 |
| 11 | Poke Pad (1152) | 4 |
| 12 | Boss' Orders (1182) | 3 |
| 13 | Explorer's Guidance (1185) | 4 |
| 14 | Carmine (1192) | 4 |

*(Verified against decklist. deck.csv is outdated — do not use it as source of truth.)*

---

## Architecture Hyperparameters

| Param | Value |
|---|---|
| `D_MODEL` | 64 |
| `D_HIDDEN` (MLP intermediate) | 2× input size per MLP |
| Transformer layers | 2 |
| Attention heads | 2 |
| Sequence length | 15 words |

**Three MLPs (all output D_MODEL=64):**
- **Pokemon MLP**: 13 → 26 → 64 (applied to each of 12 board slots)
- **Pile MLP**: 16 → 32 → 64 (shared weights across hand, discard, prize words)
- **Global MLP**: 12 → 24 → 64 (applied once)

All MLPs use GELU activation between layers.

**Type embedding**: learned (15, 64) table — one entry per word type — added to MLP output before transformer. Word type assignments TBD when we design the output head.

**Attention-weighted pooling** after transformer (same as SVN v2): learned query vector (64,), softmax over 15 words, weighted sum → (64,).

---

## Action Selection

### Stage 1 — Action type (fixed vocab)
Linear(64 → N_ACTIONS) over pooled representation. Mask illegal actions, argmax.

| Action | Stage 2? |
|---|---|
| PLAY [card] — one per unique card type in hand | Sometimes |
| ATTACH fire energy | Yes — target Pokemon |
| ATTACH fighting energy | Yes — target Pokemon |
| RETREAT | Yes — which Pokemon to switch into; if retreat cost=2, also pick 2 energy to discard |
| ATTACK | No |
| USE LUNATONE ABILITY | No |
| PASS | No |

### Stage 2 — Target selection (sequential dot-product)
When a Stage 1 action requires targets:

1. Take pooled board state (64-dim, fixed — no transformer re-run).
2. Encode each candidate to 64-dim (via appropriate MLP).
3. Dot each candidate vector against pooled state → scalar score per candidate.
4. Argmax → select candidate. Mask it from pool.
5. Repeat until enough picks made or STOP token wins.

**STOP token**: a single learned 64-dim embedding (no MLP input) that competes in each round's scoring. Used for variable-length selections (Drilbur discard up to 3, Brilliant Blender discard up to 5).

**Stage 2 triggers by card:**
| Card | Candidates | Max picks |
|---|---|---|
| Boss's Orders | Opponent bench slots | 1 |
| Ultra Ball | 2× discard from hand, then 1× search target from deck | 2 then 1 |
| Fighting Gong / Poke Pad / Night Stretcher | Search target from deck/discard | 1 |
| Brilliant Blender | Cards from hand to discard | up to 5 + STOP |
| Drilbur ability | Cards from hand to discard | up to 3 + STOP |
| Explorer's Guidance | 2 cards from top 6 of deck (sequential approximation of simultaneous pick) | 2 |
| Charcadet attack (Gather Strength) | 2 energy from deck to put in hand | 2 |
| Retreat (cost=2, e.g. Ceruledge) | 2 energy attached to active to discard | 2 |
| Promote after KO / Repel | Your bench slots | 1 |

**Note on Explorer's Guidance:** picks are simultaneous in the real game but modeled sequentially here. Information loss is minor in practice.

**Pokemon as search targets:** when a card (Ultra Ball, Poke Pad, Fighting Gong, Night Stretcher, Explorer's Guidance, etc.) presents Pokemon as candidates from the deck or discard, encode those Pokemon using the **Pile MLP** (16-dim zone vector), not the Pokemon MLP. The Pokemon MLP is only for cards actually on the board.

---

## Reward Structure

| Event | Reward |
|---|---|
| Taking a prize card | +0.01 |
| Winning the game | +1.0 |
| Losing the game | -1.0 |
| All other steps | 0 |

Win reward dominates heavily by design — prize reward exists only to give a tiny early training signal before the agent can win consistently. 100:1 ratio (win vs. single prize).

**Self-play opponent update frequency**: every N episodes, configurable before training starts.

---

## Training Experiments

Three runs, each tracking **reward vs. timesteps** and **win rate vs. timesteps**:

1. **Random opponent** — policy vs. a copy of the Ceruledge bot playing uniformly random legal actions. Establishes a baseline; easiest opponent, should converge fastest.
2. **Rules-based opponent** — policy vs. the existing Ceruledge rules-based agent (`Ceruledge-Agent/main.py`). Tests whether the policy can learn to exploit or match hand-coded strategy.
3. **Self-play** — policy vs. a periodically-updated copy of itself. Opponent adapts as policy improves; highest ceiling but least stable.

All three experiments use the same architecture and hyperparameters. Compare the three win rate curves to understand what each training regime teaches.

---

### Exploration during training
- **Inference**: argmax at every stage.
- **Training**: epsilon-greedy — with probability ε pick a uniformly random legal action at Stage 1; Stage 2 follows the policy normally. ε decays over training.
