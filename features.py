"""
Feature extraction for Pokémon TCG observations.

Adapted from the competition's RL+MCTS sample notebook.
Works directly on raw observation dicts — no cg library needed.
Produces the same 24-word SparseVector encoder input used by MyModel.

card_count should match the cg library when running on Kaggle:
    from cg.api import all_card_data
    all_card = all_card_data()
    card_count = max(all_card, key=lambda c: c.cardId).cardId + 1
"""

# CARD_COUNT must equal the cg library value when running on Kaggle:
#   from cg.api import all_card_data
#   card_count = max(all_card_data(), key=lambda c: c.cardId).cardId + 1
# The public training data max card ID is 1262, so 1263 is the floor.
# vocab_size_needed = 45 + 17 * CARD_COUNT — must be ≤ ENCODER_SIZE.
CARD_COUNT = 1263
NUM_WORDS_ENCODER = 24


class SparseVector:
    """Sparse input for torch.nn.EmbeddingBag (mode='sum')."""

    def __init__(self):
        self.index: list[int] = []
        self.value: list[float] = []
        self.offset: list[int] = []
        self.pos: int = 0

    def add(self, index: int, value: float | int | bool):
        v = float(value)
        if v != 0.0:
            self.index.append(self.pos + index)
            self.value.append(v)

    def add_pos(self, pos: int):
        self.pos += pos

    def add_single(self, value: float | int | bool):
        v = float(value)
        if v != 0.0:
            self.index.append(self.pos)
            self.value.append(v)
        self.pos += 1

    def word_start(self):
        self.offset.append(len(self.index))


# ---------------------------------------------------------------------------
# Primitive encoders — take raw dicts, not typed objects
# ---------------------------------------------------------------------------

def _add_card(sv: SparseVector, card: dict | None, card_count: int = CARD_COUNT):
    """Encode a single card's ID into the current vocabulary position."""
    if card is not None:
        sv.add(card["id"], 1)
    sv.add_pos(card_count)


def _add_cards(
    sv: SparseVector,
    cards: list[dict] | None,
    value: float,
    card_count: int = CARD_COUNT,
):
    """Encode a list of cards as a bag-of-ids with the given weight."""
    if cards:
        for card in cards:
            if card is not None:
                sv.add(card["id"], value)
    sv.add_pos(card_count)


def _add_pokemon(sv: SparseVector, poke: dict | None, card_count: int = CARD_COUNT):
    """
    Encode one Pokémon slot.

    Vocabulary layout per slot (shared across all bench positions):
      [0]            null flag (1 if slot empty)
      [1]            appearThisTurn flag (1 if appeared this turn)
      [2]            hp fraction (current_hp / 400)
      [3..3+C)       card ID one-hot
      [3+C..3+2C)    attached tool IDs (bag)
      [3+2C..3+3C)   attached energy card IDs (bag, weight 0.5)
    Total: 3 + 3 * card_count positions
    """
    if poke is None:
        sv.add_single(1)                        # null flag
        sv.add_pos(2 + 3 * card_count)
    else:
        sv.add_single(0)                        # null flag = 0
        sv.add_single(poke.get("appearThisTurn", False))  # appearThisTurn flag
        sv.add_single(poke["hp"] / 400)         # hp fraction
        _add_card(sv, poke, card_count)         # pokemon card id
        _add_cards(sv, poke.get("tools"), 1.0, card_count)
        _add_cards(sv, poke.get("energyCards"), 0.5, card_count)


def _add_player(sv: SparseVector, player: dict, card_count: int = CARD_COUNT):
    """
    Encode scalar player-state features + discard pile.

    Vocabulary layout:
      [0]      deck fraction
      [1]      discard count fraction
      [2]      hand count fraction
      [3]      bench size fraction
      [4..10)  prize count one-hot (0-6 prizes remaining)
      [10]     poisoned
      [11]     burned
      [12]     asleep
      [13]     paralyzed
      [14]     confused
      [15..15+C) discard pile card IDs (bag, weight 0.25)
    Total: 15 + card_count positions
    """
    prize = player.get("prize") or []
    discard = player.get("discard") or []

    sv.add_single(player["deckCount"] / 60)
    sv.add_single(len(discard) / 60)
    sv.add_single(player["handCount"] / 8)
    sv.add_single(len(player.get("bench") or []) / 5)
    sv.add(len(prize), 1)      # prize count → one-hot in 7-wide range
    sv.add_pos(7)              # skips the full prize range

    sv.add_single(player["poisoned"])
    sv.add_single(player["burned"])
    sv.add_single(player["asleep"])
    sv.add_single(player["paralyzed"])
    sv.add_single(player["confused"])

    _add_cards(sv, discard, 0.25, card_count)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_encoder_input(
    obs: dict,
    your_deck: list[int],
    card_count: int = CARD_COUNT,
) -> SparseVector:
    """
    Build the 24-word encoder SparseVector from a raw observation dict.

    Parameters
    ----------
    obs : dict
        A single observation dict from the training JSON:
        d['steps'][step_i][player_i]['observation']
    your_deck : list[int]
        Full list of card IDs in the current player's deck (60 cards).
        From training data: d['steps'][1][player_i]['action']
    card_count : int
        Vocabulary size for card IDs. Override if using cg library value.

    Returns
    -------
    SparseVector with NUM_WORDS_ENCODER=24 words.

    Word layout (same as the sample notebook):
      Words 0-7   : your bench slots (0-4 occupied, 5-7 padding)
      Words 8-15  : opponent bench slots
      Word 16     : your active Pokémon
      Word 17     : opponent active Pokémon
      Word 18     : your player state + discard
      Word 19     : opponent player state + discard
      Word 20     : your hand cards
      Word 21     : your deck composition
      Word 22     : stadium
      Word 23     : turn metadata
    """
    current = obs["current"]
    your_index = current["yourIndex"]
    players = current["players"]
    sv = SparseVector()

    # Words 0-7 (you) and 8-15 (opponent): bench slots
    for i in range(2):
        ps = players[i ^ your_index]
        bench = ps.get("bench") or []
        for j in range(8):
            sv.word_start()
            pos = sv.pos
            poke = bench[j] if j < len(bench) else None
            _add_pokemon(sv, poke, card_count)
            if j != 7:
                sv.pos = pos  # all bench slots share the same vocab range

    # Words 16-17: active Pokémon (you, then opponent)
    for i in range(2):
        ps = players[i ^ your_index]
        active = ps.get("active") or []
        sv.word_start()
        _add_pokemon(sv, active[0] if active else None, card_count)

    # Words 18-19: player state + discard (you, then opponent)
    for i in range(2):
        ps = players[i ^ your_index]
        sv.word_start()
        _add_player(sv, ps, card_count)

    # Word 20: your hand (opponent's hand is hidden in the observation)
    your_hand = players[your_index].get("hand") or []
    sv.word_start()
    _add_cards(sv, your_hand, 0.25, card_count)

    # Word 21: your deck composition
    sv.word_start()
    for card_id in your_deck:
        sv.add(card_id, 0.25)
    sv.add_pos(card_count)

    # Word 22: stadium
    stadium = current.get("stadium") or []
    sv.word_start()
    _add_cards(sv, stadium, 1.0, card_count)

    # Word 23: turn metadata
    sv.word_start()
    sv.add_single(1)                                        # bias
    sv.add_single(current.get("turn", 0) / 10)
    sv.add_single(current.get("firstPlayer") == your_index)

    return sv
