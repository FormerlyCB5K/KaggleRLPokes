# Observation Encoder TODO

Deferred items from the known-errors review (2026-07-23/26). Intentionally not being
worked on right now — see PROJECT_MEMORY.md / `observation_known_errors` memory for
full history and priority rationale.

## Deferred

- **Deck order representation.** Effects that pin a card's position (e.g. put on
  bottom of deck) mean we know it's *not* drawable next, but the encoding has no
  ordering concept for deck contents — canonical sort-by-card-ID was chosen assuming
  gameplay order didn't matter, which this falsifies. Affects draw-odds-relevant
  information the model currently can't see. Depends on the deck/Prize identity work
  (`zones.py` / `encoder.py` deck-building) being settled first.

- **Legal-action / available-options representation.** The observation is purely
  board/zone state; there's no field encoding what moves are currently legal. Would
  need a new word/field design (not yet scoped).
