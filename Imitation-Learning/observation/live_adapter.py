"""Spec 15: builds spec 13a's `GameState` from the real live/replayed engine wire format
(`cg_download.api.Observation`), so `encoder.build_observation()` can run against an
actual game instead of hand-built test fixtures.

See `Ceruledge-RL/specs/15-live-engine-adapter.md` for the full design, including the
mapping table this implements and how its open items were resolved:

- Tool multiplicity: `poke.tools[0]` -- the ruleset limits a Pokemon to one Tool.
- `our_deck` before prize resolution: deliberately `[]` (all PAD). Individual card
  identity can't be split between deck and prizes at all until the first full-deck
  search resolves the whole 60-card list at once, and spec 13a's deck zone (unlike its
  prize zone) has no UNK/hidden-count slot to represent "cards exist here, identity
  unknown" -- so there is no way to represent this state other than PAD or a guess, and
  guessing individual card identity would be worse than PAD.
- Opponent `new_in_play`: evolution-serial tracking is inherently per-side (`EVOLVE` logs
  carry the evolving player's index), so this adapter runs a second `GameStateTracker`
  from the opponent's own perspective (`.update(obs, 1 - our_idx)`) purely to reuse its
  already-tested `evolved_serials` bookkeeping -- not for any of its Ceruledge-specific
  fields.

This module needs `Ceruledge-RL`'s `features.GameStateTracker`/`prize_check.PrizeTracker`
(reused rather than duplicated) and `cg_download.api`'s wire types, none of which are
importable from here without the path insertion below -- this is the first module to
import across the `Imitation-Learning`/`Ceruledge-RL` tree boundary.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
_CERULEDGE_RL = os.path.join(_REPO_ROOT, "Ceruledge-RL")
sys.path.insert(0, _REPO_ROOT)     # repo root: cg_download
sys.path.insert(0, _CERULEDGE_RL)  # Ceruledge-RL first: its own bare imports resolve there

from cg_download.api import Observation, PlayerState, Pokemon  # noqa: E402
from features import FULL_DECK, GameStateTracker  # noqa: E402
from prize_check import PrizeTracker  # noqa: E402

from .encoder import BoardPokemonState, BoardRole, GameState
from .live_state import RawPokemon
from .types import SPECIAL_CONDITIONS


def _special_conditions(ps: PlayerState, is_active: bool) -> tuple[str, ...]:
    """Only the Active Pokemon carries conditions -- they don't persist on the Bench
    under the game rules, and the engine only exposes these 5 flags per-side, not
    per-Pokemon (`PlayerState.asleep`/etc., not `Pokemon.asleep`/etc.)."""
    if not is_active:
        return ()
    flags = (ps.asleep, ps.paralyzed, ps.burned, ps.poisoned, ps.confused)
    return tuple(name for name, flag in zip(SPECIAL_CONDITIONS, flags) if flag)


def _raw_pokemon(
    poke: Pokemon, ps: PlayerState, is_active: bool, tracker: GameStateTracker
) -> RawPokemon:
    pre_evolution_ids = tuple(c.id for c in (poke.preEvolution or ()))
    tools = poke.tools or ()
    return RawPokemon(
        card_id=poke.id,
        hp=poke.hp,
        max_hp=poke.maxHp,
        energy_cards=tuple(c.id for c in (poke.energyCards or ())),
        tool_card_id=tools[0].id if tools else None,
        pre_evolution_ids=pre_evolution_ids,
        # No explicit stage field on the engine's `Pokemon` -- a Pokemon currently in
        # its basic form has never evolved, so an empty pre-evolution list is exact.
        is_basic=len(pre_evolution_ids) == 0,
        is_active=is_active,
        new_in_play=poke.appearThisTurn or poke.serial in tracker.evolved_serials,
        special_conditions=_special_conditions(ps, is_active),
    )


def _in_play_ids(ps: PlayerState) -> list[int]:
    """All card ids bound up in this side's play: Pokemon + energy + tools +
    pre-evolutions -- mirrors `features.py`'s `_in_play_card_ids`, needed here again for
    deck-by-elimination rather than imported since that helper is private to `features`."""
    ids: list[int] = []
    for poke in list(ps.active or ()) + list(ps.bench or ()):
        if poke is None:
            continue
        ids.append(poke.id)
        ids += [c.id for c in (poke.energyCards or ())]
        ids += [c.id for c in (poke.tools or ())]
        ids += [c.id for c in (poke.preEvolution or ())]
    return ids


def _board_states(
    ps: PlayerState, active_role: BoardRole, bench_role: BoardRole, tracker: GameStateTracker
) -> list[BoardPokemonState]:
    """Only occupied slots are emitted -- `encoder.build_observation` pads the rest to
    `1 + MAX_BENCH` itself, matching `test_encoder.py`'s fixture convention."""
    entries: list[BoardPokemonState] = []
    active = ps.active[0] if (ps.active and ps.active[0] is not None) else None
    if active is not None:
        entries.append(BoardPokemonState(active_role, _raw_pokemon(active, ps, True, tracker)))
    for poke in (ps.bench or ()):
        if poke is not None:
            entries.append(BoardPokemonState(bench_role, _raw_pokemon(poke, ps, False, tracker)))
    return entries


def _prizes(prize_tracker: PrizeTracker) -> tuple[list[int], int]:
    """Binary by construction: `PrizeTracker` resolves the entire 60-card list at once
    (the first full-deck search), so prizes are either fully known or fully hidden --
    never partially. `our_prizes_hidden_count` supports partial resolution in principle;
    this adapter just never produces that case."""
    if not prize_tracker.prizes_known:
        return [], 6
    known = [cid for cid, count in prize_tracker.prize_counts.items() for _ in range(max(0, count))]
    return known, 0


def _deck_remainder(ps: PlayerState, prize_tracker: PrizeTracker) -> list[int]:
    """Deck-by-elimination -- same math `features.py` already performs inline for its
    own deck zone. Returns `[]` before the prize tracker resolves (see module docstring):
    that's a real information gap, not a shortcut -- individual card identity can't be
    attributed to "deck" vs. "prize" before the first full-deck search regardless of
    representation."""
    if not prize_tracker.prizes_known:
        return []
    hand_counts = Counter(c.id for c in (ps.hand or ()))
    discard_counts = Counter(c.id for c in (ps.discard or ()))
    in_play_counts = Counter(_in_play_ids(ps))
    deck_counts = (
        Counter(FULL_DECK) - hand_counts - discard_counts - in_play_counts - prize_tracker.prize_counts
    )
    return [cid for cid, count in deck_counts.items() for _ in range(max(0, count))]


def build_game_state(
    obs: Observation,
    our_idx: int,
    prize_tracker: PrizeTracker,
    our_tracker: GameStateTracker,
    opponent_tracker: GameStateTracker,
) -> GameState:
    """Build spec 13a's `GameState` from one live/replayed engine observation.

    `our_tracker`/`opponent_tracker` are plain `GameStateTracker` instances (the same
    class `Ceruledge-RL/train.py` already instantiates once per episode); this function
    calls `.update()` on both every time, from each side's own perspective
    (`opponent_tracker.update(obs, 1 - our_idx)`), so callers don't need to remember to.
    `GameStateTracker.update` is already guarded against double-processing the same
    observation, so calling this function more than once per decision is harmless.
    """
    if obs.current is None:
        raise ValueError(
            "build_game_state requires obs.current (not the initial deck-selection phase)"
        )

    our_tracker.update(obs, our_idx)
    opponent_tracker.update(obs, 1 - our_idx)
    prize_tracker.update(obs, our_idx)

    state = obs.current
    ps = state.players[our_idx]
    opp_ps = state.players[1 - our_idx]

    prizes_known, prizes_hidden = _prizes(prize_tracker)
    board = _board_states(ps, "our_active", "our_bench", our_tracker) + _board_states(
        opp_ps, "opponent_active", "opponent_bench", opponent_tracker
    )

    return GameState(
        our_deck=_deck_remainder(ps, prize_tracker),
        our_hand=[c.id for c in (ps.hand or ())],
        our_discard=[c.id for c in (ps.discard or ())],
        our_prizes_known=prizes_known,
        our_prizes_hidden_count=prizes_hidden,
        opponent_discard=[c.id for c in (opp_ps.discard or ())],
        board=board,
        stadium_card_id=state.stadium[0].id if state.stadium else None,
        turn_number=state.turn,
        supporter_played=state.supporterPlayed,
    )
