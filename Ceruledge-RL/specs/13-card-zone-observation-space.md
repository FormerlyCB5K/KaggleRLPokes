# 13 — Card-Zone Observation Space — Overview

Status: **design complete (13a) and transcribed into tested standalone code under
`Imitation-Learning/observation/` (2026-07-21). The 174-word structure is locked. A live
engine adapter and training integration remain open; the deferred 13b implementation spec
has not yet been written retroactively.**

## What this is

The observation design for everything spec 11 explicitly deferred: card-zone words
(hand/discard/deck/prizes), how a card's representation persists as it moves between zones
(including attaching to a Pokémon or evolving), and global/turn state. Spec 11 covers the
Pokémon board-slot word in isolation and built a static-template/live-state seam
specifically so this spec could reuse it for cards that aren't currently on the board.

This spec replaces the old zone-summary-word model (one word per zone: hand, deck, discard,
etc., holding aggregate features) with a persistent-per-card-slot model: every card in the
friendly 60-card deck gets one word, always present, whose content updates as the card
changes zone rather than being created or destroyed.

## Split

- **13a — observation space design.** Architecture only: word count and structure, how
  attachment/evolution relationships get represented, how hidden information (opponent
  cards, own prizes) is handled, what summary fields survive alongside individual words.
  No implementation.
- **13b — implementation.** Begins only once 13a is signed off.

## Components

- [`13a-observation-space-design.md`](13a-observation-space-design.md) — the design
  document itself.

## Relationship to spec 11

Spec 11 defines the Pokémon word's static template (card-ID embedding, attribute/effect
tags, static printed fields) and live board state (HP fraction, energy count, status,
threat features), deliberately split into two separately-callable pieces so a Pokémon
sitting in a non-board zone can use the static half alone. Spec 13 is the concrete consumer
of that seam: it decides how static templates get assembled into the full observation
across all 60 friendly cards regardless of where they currently are, and adds the
relational structure (location + role) needed to represent attachments and evolution
chains that spec 11 didn't need to solve for board-only Pokémon.
