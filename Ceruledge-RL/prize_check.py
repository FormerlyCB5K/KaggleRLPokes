"""
prize_check.py — Infer our prized cards by elimination, keep them current.

PrizeTracker requires the player's authoritative submitted 60-card deck. It
latches prize composition at the first full remaining-deck reveal
(`obs.select.deck`) and afterwards detects taken prizes exactly via card serial
numbers: any own-side card whose serial was never seen outside the prize zone
must have come from prizes.

Usage:
    tracker = PrizeTracker(submitted_deck)
    tracker.update(obs, our_idx)      # every step
    vec = tracker.vector()            # fixed Ceruledge consumer layout; see vector()

Spec: specs/completed/01-prize-tracker.md
"""
from __future__ import annotations
from collections import Counter
from collections.abc import Iterable

from cg_download.api import AreaType, LogType
from features import DECK_CARDS


class PrizeTrackerInvariantError(RuntimeError):
    """The observation and supplied deck cannot describe one valid prize state."""


class PrizeTracker:
    def __init__(self, full_deck: Iterable[int]):
        self.full_deck = tuple(full_deck)
        if len(self.full_deck) != 60:
            raise ValueError(
                "PrizeTracker requires the authoritative 60-card submitted deck; "
                f"received {len(self.full_deck)} cards"
            )
        if any(not isinstance(cid, int) for cid in self.full_deck):
            raise TypeError("PrizeTracker deck entries must all be integer card IDs")
        self._full_counts = Counter(self.full_deck)
        self.reset()

    def reset(self):
        self.prizes_known: bool = False
        self.prize_counts: Counter = Counter()
        self.known_serials: set[int] = set()

    @staticmethod
    def _context(obs) -> str:
        select = getattr(obs, "select", None)
        context = getattr(select, "context", None)
        effect = getattr(select, "effect", None)
        effect_id = getattr(effect, "id", None)
        turn = getattr(getattr(obs, "current", None), "turn", None)
        return f"turn={turn}, context={context}, effect_id={effect_id}"

    def _raise(self, obs, message: str) -> None:
        raise PrizeTrackerInvariantError(f"{message} ({self._context(obs)})")

    def _dedupe_seen(self, obs, seen: list[tuple[int, int]]) -> dict[int, int]:
        by_serial: dict[int, int] = {}
        for cid, serial in seen:
            if serial is None:
                self._raise(obs, f"visible card {cid} has no serial")
            prior = by_serial.get(serial)
            if prior is not None and prior != cid:
                self._raise(
                    obs,
                    f"serial {serial} identifies conflicting card IDs {prior} and {cid}",
                )
            by_serial[serial] = cid
        return by_serial

    def _assert_prize_total(self, obs, ps, counts: Counter) -> None:
        expected = len(ps.prize or [])
        actual = sum(counts.values())
        if actual != expected:
            self._raise(
                obs,
                f"inferred {actual} prizes but engine reports {expected} remaining; "
                "the supplied deck or reveal is inconsistent",
            )

    def update(self, obs, our_idx: int) -> None:
        if obs.current is None:
            self._raise(obs, "cannot update without obs.current")
        if not 0 <= our_idx < len(obs.current.players):
            self._raise(obs, f"player index {our_idx} is out of range")

        ps = obs.current.players[our_idx]
        seen: list[tuple[int, int]] = []  # cards confirmed not prized

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

        # Stadium/looking are shared zones, but current engine Card records carry
        # playerIndex. Count only cards owned by this tracker; excluding an owned
        # Stadium would overcount prizes for arbitrary decks by one.
        for c in (obs.current.stadium or []):
            if c is not None and c.playerIndex == our_idx:
                seen.append((c.id, c.serial))
        for c in (obs.current.looking or []):
            if c is not None and c.playerIndex == our_idx:
                seen.append((c.id, c.serial))

        # A taken prize can leave `ps.prize` before it appears in hand or another
        # ordinary zone. The engine logs that transition with exact identity and
        # serial, so consume it immediately rather than temporarily violating the
        # remaining-prize invariant.
        for log in (obs.logs or []):
            if (
                log.type == LogType.MOVE_CARD
                and log.playerIndex == our_idx
                and log.fromArea == AreaType.PRIZE
                and log.cardId is not None
                and log.serial is not None
            ):
                seen.append((log.cardId, log.serial))

        # Selection data belongs only to `current.yourIndex`. Some consumers update
        # both sides' long-lived trackers from the same observation so logs stay in
        # sync; the non-acting side must never interpret the acting player's revealed
        # deck/effect as its own.
        is_our_selection = obs.current.yourIndex == our_idx
        deck = obs.select.deck if obs.select and is_our_selection else None
        for c in (deck or []):
            seen.append((c.id, c.serial))

        if deck:
            if len(deck) != ps.deckCount:
                self._raise(
                    obs,
                    f"select.deck exposes {len(deck)} cards but deckCount is {ps.deckCount}; "
                    "refusing to treat this as a full remaining-deck reveal",
                )
            # An owned trainer being resolved (e.g. Ultra Ball) is in no zone
            # while its search executes -- only obs.select.effect references it.
            # A shared Stadium effect may instead belong to the opponent.
            eff = obs.select.effect
            if eff is not None:
                effect_owner = getattr(eff, "playerIndex", None)
                if effect_owner == our_idx:
                    seen.append((eff.id, eff.serial))
                elif effect_owner not in range(len(obs.current.players)):
                    self._raise(
                        obs,
                        f"selection effect {eff.id} has invalid playerIndex {effect_owner}",
                    )
            # Dedupe by serial (the effect source may also be in play).
            by_serial = self._dedupe_seen(obs, seen)
            seen_counts = Counter(by_serial.values())
            unexpected = seen_counts - self._full_counts
            if unexpected:
                self._raise(
                    obs,
                    "visible cards are not a subset of the supplied deck: "
                    + ", ".join(
                        f"{cid}x{count}" for cid, count in sorted(unexpected.items())
                    ),
                )
            # Full deck revealed: (re)compute prizes by elimination.
            prize_counts = self._full_counts - seen_counts
            self._assert_prize_total(obs, ps, prize_counts)
            self.prize_counts = prize_counts
            self.known_serials = set(by_serial)
            self.prizes_known = True
        elif self.prizes_known:
            prize_counts = self.prize_counts.copy()
            known_serials = set(self.known_serials)
            for cid, serial in seen:
                if serial not in known_serials:
                    if prize_counts[cid] <= 0:
                        self._raise(
                            obs,
                            f"new serial {serial} for card {cid} cannot be a remaining prize",
                        )
                    prize_counts[cid] -= 1
                    known_serials.add(serial)
            self._assert_prize_total(obs, ps, prize_counts)
            self.prize_counts = prize_counts
            self.known_serials = known_serials

    def vector(self) -> list[int]:
        if not self.prizes_known:
            return [0] * len(DECK_CARDS) + [1]
        return [self.prize_counts[cid] for cid in DECK_CARDS] + [0]
