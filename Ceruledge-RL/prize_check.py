"""
prize_check.py — Infer our prized cards by elimination, keep them current.

PrizeTracker latches prize composition at the first full deck search
(obs.select.deck visible) and afterwards detects taken prizes exactly via
card serial numbers: any own-side card whose serial was never seen outside
the prize zone must have come from prizes.

Usage:
    tracker = PrizeTracker()          # or tracker.reset() at game start
    tracker.update(obs, our_idx)      # every step
    vec = tracker.vector()            # 16 ints: 15 counts (DECK_CARDS order) + unknown flag

Spec: specs/completed/01-prize-tracker.md
"""
from __future__ import annotations
from collections import Counter

from features import DECK_CARDS, FULL_DECK


class PrizeTracker:
    def __init__(self):
        self.reset()

    def reset(self):
        self.prizes_known: bool = False
        self.prize_counts: Counter = Counter()
        self.known_serials: set[int] = set()

    def update(self, obs, our_idx: int) -> None:
        ps = obs.current.players[our_idx]
        seen: list = []  # (id, serial) pairs of cards confirmed not prized

        for c in (ps.hand or []):
            seen.append((c.id, c.serial))
        for c in (ps.discard or []):
            seen.append((c.id, c.serial))

        in_play = []
        if ps.active:
            in_play += [p for p in ps.active if p is not None]
        if ps.bench:
            in_play += [p for p in ps.bench if p is not None]
        for poke in in_play:
            seen.append((poke.id, poke.serial))
            for c in (poke.energyCards or []):
                seen.append((c.id, c.serial))
            for c in (poke.tools or []):
                seen.append((c.id, c.serial))
            for c in (poke.preEvolution or []):
                seen.append((c.id, c.serial))

        # obs.current.stadium and obs.current.looking are deliberately excluded:
        # they are shared zones with no owner field, so in a mirror match an
        # opponent card there would corrupt the counts. Our deck runs no
        # stadium, and our own cards passing through `looking` are detected
        # once they land in hand/discard/play.

        deck = obs.select.deck if obs.select else None
        for c in (deck or []):
            seen.append((c.id, c.serial))

        if deck:
            # The trainer being resolved (e.g. Ultra Ball) is in no zone while
            # its search executes — only obs.select.effect references it.
            eff = obs.select.effect
            if eff is not None:
                seen.append((eff.id, eff.serial))
            # Dedupe by serial (the effect source may also be in play).
            by_serial = dict((serial, cid) for cid, serial in seen)
            # Full deck revealed: (re)compute prizes by elimination.
            self.prize_counts = Counter(FULL_DECK) - Counter(by_serial.values())
            self.known_serials = set(by_serial)
            self.prizes_known = True
        elif self.prizes_known:
            for cid, serial in seen:
                if serial not in self.known_serials:
                    if self.prize_counts[cid] > 0:
                        self.prize_counts[cid] -= 1
                    self.known_serials.add(serial)

    def vector(self) -> list[int]:
        if not self.prizes_known:
            return [0] * len(DECK_CARDS) + [1]
        return [self.prize_counts[cid] for cid in DECK_CARDS] + [0]
