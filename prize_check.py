"""
prize_check.py — Infer prized cards by elimination during a deck search.

Call compute_prizes() when a deck search reveals obs.select.deck (i.e. during
an Ultra Ball, Poke Pad, Brilliant Blender, or similar search).  Returns a
Counter of {card_id: count} for cards that must be prized, or None if the deck
is not currently revealed in the observation.

Usage:
    from prize_check import compute_prizes
    prizes = compute_prizes(obs, MY_DECK, your_index)
    if prizes is not None:
        # prizes is now known; store it in agent state
"""

from collections import Counter
from cg_download.api import Observation, CardType, all_card_data

_all_cards = all_card_data()
_card_table = {c.cardId: c for c in _all_cards}


def compute_prizes(
    obs: Observation,
    deck_list: list[int],
    your_index: int,
) -> Counter | None:
    """
    Return a Counter of prized card IDs, or None if the deck is not revealed.

    The deck is only visible in obs.select.deck during an active search prompt.
    Call this function at that moment and cache the result in agent state.
    """
    visible_deck = obs.select.deck
    if not visible_deck:
        return None

    ps = obs.current.players[your_index]

    # Cards accounted for outside of prizes
    seen: Counter = Counter()

    # Hand
    for c in (ps.hand or []):
        seen[c.id] += 1

    # Discard
    for c in (ps.discard or []):
        seen[c.id] += 1

    # In play: active + bench (base card + attached energies)
    in_play = []
    if ps.active:
        in_play.extend(p for p in ps.active if p is not None)
    if ps.bench:
        in_play.extend(p for p in ps.bench if p is not None)
    for poke in in_play:
        seen[poke.id] += 1
        for e in (poke.energyCards or []):
            seen[e.id] += 1

    # Currently visible deck
    for c in visible_deck:
        seen[c.id] += 1

    # Prizes = full deck composition minus everything seen
    full_deck = Counter(deck_list)
    prizes = full_deck - seen  # Counter subtraction floors at 0

    return prizes
