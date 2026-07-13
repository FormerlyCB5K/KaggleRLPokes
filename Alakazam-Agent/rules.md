# Alakazam Agent — Formalized Rules

## Deck Reference (60 cards)

| Qty | Card ID | Name | Notes |
|-----|---------|------|-------|
| 2 | 5 | Basic Psychic Energy | |
| 1 | 13 | Enriching Energy | Attach → draw 4 cards |
| 4 | 19 | Telepathic Energy | Attach to {P} Pokémon → bench up to 2 Basic {P} Pokémon from deck |
| 3 | 66 | Dudunsparce | **Run Away Draw**: draw 3 then shuffle self+attachments into deck |
| 1 | 140 | Fezandipiti ex | **Flip the Script**: draw 3 if any of YOUR Pokémon were KO'd last turn (1/turn max) |
| 1 | 142 | Genesect | **ACE Nullifier**: if Genesect has a Tool attached, opponent can't play ACE SPEC cards |
| 1 | 245 | **TWM** (Alakazam) | Attacks: Psychic (10+50 per opp. energy); Strange Hacking (confuse + move dmg counters) |
| 3 | 305 | Dunsparce | Trading Places (switch self with benched); Ram (20 dmg) |
| 1 | 343 | Shaymin | **Flower Curtain**: prevent all bench damage to non-rule-box Pokémon from opponent's attacks |
| 4 | 741 | Abra | Teleportation Attack: 10 dmg + switch with bench |
| 4 | 742 | Kadabra | **Psychic Draw**: draw 2 when played from hand to evolve |
| 3 | 743 | **ZAM** (Alakazam) | **Psychic Draw**: draw 3 when played from hand to evolve; **Powerful Hand**: 20 dmg × cards in hand |
| 4 | 1079 | Rare Candy | Evolve Basic → Stage 2, skipping Stage 1. Cannot use on first turn or on a Pokémon placed this turn |
| 4 | 1086 | Buddy-Buddy Poffin | Search deck for up to 2 Basics with 70 HP or less (= Dunsparce or Abra only) |
| 1 | 1097 | Night Stretcher | Retrieve 1 Pokémon OR 1 Basic Energy from discard pile to hand |
| 1 | 1129 | Sacred Ash | Shuffle up to 5 Pokémon from discard pile into deck |
| 4 | 1152 | Poké Pad | Search deck for any non-rule-box Pokémon (cannot fetch Fezandipiti ex) |
| 2 | 1156 | Lucky Helmet | While active: when damaged by opponent's attack, draw 2 cards |
| 1 | 1174 | Air Balloon | Pokémon Tool: retreat cost −2 |
| 2 | 1182 | Boss's Orders | Supporter: switch one of opponent's benched Pokémon to active spot |
| 1 | 1184 | Lana's Aid | Supporter: retrieve up to 3 non-rule-box Pokémon and/or Basic Energies from discard to hand |
| 4 | 1225 | Hilda | Supporter: search deck for 1 Evolution Pokémon + 1 Energy card |
| 4 | 1231 | Dawn | Supporter: search deck for 1 Basic + 1 Stage 1 + 1 Stage 2 Pokémon |
| 4 | 1264 | Battle Cage | Stadium: prevents damage counters placed on benched Pokémon by opponent's attacks AND abilities |

---

## Card Aliases

- **ZAM** = Alakazam (card 743): has Powerful Hand attack and Psychic Draw ability
- **TWM** = Alakazam (card 245): has Psychic attack and Strange Hacking attack
- **Telepathic Energy** = Telepath Psychic Energy (card 19)
- **Basic Psychic Energy** = card 5
- **Enriching Energy** = card 13
- **Tool** = Lucky Helmet (1156) or Air Balloon (1174)
- **"a tool in hand"** = Lucky Helmet or Air Balloon in hand

---

## State Variables

| Variable | Type | Reset | Description |
|----------|------|-------|-------------|
| `HAND` | integer | Each draw/play | Running count of cards in player's hand |
| `DECK_SIZE` | integer | Each shuffle/draw | Running count of cards remaining in deck |
| `STRANGE` | bool | OFF at game start | ON when opponent has/finds: Dwebble, Mist Energy, Team Rocket's Articuno |
| `CAGE` | bool | OFF at game start | ON when opponent has/finds: Munkidori, Dreepy, Froslass (non-ex), Duskull |
| `BARRIER` | bool | OFF at game start | ON when opponent has/finds: Staryu, Wellspring Mask Ogerpon ex, Slowking, N's Darumaka, Raging Bolt (non-ex) |
| `SUPPORTER_USED` | bool | FALSE each turn | TRUE after playing Hilda, Dawn, Boss's Orders, or Lana's Aid |
| `ATTACHED_ENERGY` | bool | FALSE each turn | TRUE after attaching an energy card this turn |
| `OPP_ACE_USED` | bool | OFF at game start | TRUE after opponent plays any ACE SPEC card |
| `OPP_KO_LAST_TURN` | bool | FALSE each turn | TRUE if any of your Pokémon were KO'd during opponent's last turn |

---

## Persistent Triggers

These are checked continuously throughout the entire game. Immediately update the variable whenever the triggering card is observed (in play, or known to be in opponent's hand via search).

```
if opponent reveals or plays Dwebble, Mist Energy, or Team Rocket's Articuno:
    STRANGE = ON

if opponent reveals or plays Munkidori, Dreepy, Froslass (non-ex), or Duskull:
    CAGE = ON

if opponent reveals or plays Staryu, Wellspring Mask Ogerpon ex, Slowking,
   N's Darumaka, or Raging Bolt (non-ex):
    BARRIER = ON

if opponent plays any ACE SPEC card:
    OPP_ACE_USED = ON
```

---

## Low-Deck Protection

**If `DECK_SIZE ≤ 5`, do NOT perform any of the following actions:**
1. Use Fezandipiti ex's Flip the Script ability
2. Use Dudunsparce's Run Away Draw ability
3. Attach Enriching Energy (it draws 4)
4. Choose to draw from Kadabra's Psychic Draw ability (you MAY still evolve Kadabra — just skip the draw)
5. Choose to draw from ZAM's Psychic Draw ability (you MAY still evolve ZAM — just skip the draw)
6. Play Hilda
7. Play Dawn
8. Attach Lucky Helmet
9. Play Poké Pad

---

## Game Setup

### First vs. Second
When given the choice, **always choose to go first**.

### Starting Active Pokémon Priority
Choose the starting active in this order (pick the highest available):
1. Dunsparce
2. Abra
3. Genesect
4. Shaymin
5. Fezandipiti ex

---

## Promote Priority

Whenever a Pokémon must be promoted to the active spot (after a KO or via Teleportation Attack / Trading Places), choose in this order:
1. ZAM with an energy attached
2. ZAM without an energy attached
3. Kadabra with an energy attached — **only if Kadabra was NOT evolved this turn**
4. Kadabra without an energy attached — **only if Kadabra was NOT evolved this turn**
5. Abra with an energy attached
6. Abra without an energy attached
7. Dunsparce
8. Shaymin
9. Genesect
10. Any Pokémon

---

## Turn 1 Loop

> **Loop rule**: After completing any single action, restart from the top of the loop.
> **Supporter rule**: Only one Supporter (Hilda, Dawn, Boss's Orders, Lana's Aid) may be played per turn.

```
LOOP {

  // ── Telepathic Energy attachment ───────────────────────────────────────────
  IF (an Abra is in play) AND (Telepathic Energy in hand) AND (NOT attached_energy_this_turn):
    Attach Telepathic Energy (ONLY to a Psychic-type Pokémon) in this priority:
      1. Abra in the active spot — only if we went FIRST
      2. Abra on the bench
      3. Any Abra
    After attaching, bench up to 2 Basic {P} Pokémon from the search (take the max available)
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Bench Abra ─────────────────────────────────────────────────────────────
  IF (Abra in hand) AND (≤2 Dunsparce on board):
    Bench Abra
    → RESTART LOOP

  // ── Bench Dunsparce ────────────────────────────────────────────────────────
  IF (Dunsparce in hand) AND (≤1 Dunsparce on board ... counting active + bench):
    // Note: one Dunsparce may be active. The rule means bench one if total Dunsparce ≤ 1.
    Bench Dunsparce
    → RESTART LOOP

  // ── Bench Shaymin (only if BARRIER ON) ────────────────────────────────────
  IF (BARRIER is ON) AND (Shaymin in hand):
    Bench Shaymin
    → RESTART LOOP

  // ── Bench Genesect ─────────────────────────────────────────────────────────
  IF (Genesect in hand) AND (OPP_ACE_USED is OFF) AND (a Tool in hand):
    Bench Genesect
    → RESTART LOOP

  // ── Buddy-Buddy Poffin ─────────────────────────────────────────────────────
  IF (Buddy-Buddy Poffin in hand):
    Use Buddy-Buddy Poffin; choose up to 2 Basics (≤70 HP) in this priority:
      SLOT 1:
        1. Dunsparce — if no Dunsparce currently in play
        2. Abra — if ≤1 Abra currently in play
        3. Abra — if ≤2 Abra currently in play
        4. Dunsparce
        5. Abra
      SLOT 2 (same list, re-evaluated after slot 1 is filled):
        Same priority as Slot 1
    → RESTART LOOP

  // ── Poké Pad (early — only if no Abra in play) ────────────────────────────
  IF (Poké Pad in hand) AND (no Abra in play) AND (DECK_SIZE > 5):
    Use Poké Pad; choose Abra
    → RESTART LOOP

  // ── Dawn ───────────────────────────────────────────────────────────────────
  IF (Dawn in hand) AND (no Abra in play) AND (SUPPORTER_USED is FALSE) AND (DECK_SIZE > 5):
    Use Dawn; choose 3 Pokémon:
      For the Basic slot:
        1. Abra (no Abra in play)
      For the Stage 1 slot:
        1. Kadabra — if no Kadabra in hand
        2. Dudunsparce — if no Dudunsparce in hand
        3. Kadabra
        4. Dudunsparce
      For the Stage 2 slot:
        1. TWM — if STRANGE is ON
        2. ZAM
        3. Any Pokémon
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Hilda ──────────────────────────────────────────────────────────────────
  IF (Hilda in hand) AND (SUPPORTER_USED is FALSE) AND (DECK_SIZE > 5):
    Use Hilda; choose 1 Energy + 1 Evolution Pokémon:
    ENERGY selection:
      1. Telepathic Energy — if (ATTACHED_ENERGY is FALSE) AND (≥1 Abra benched but fewer than 3)
      2. Enriching Energy  — if (ATTACHED_ENERGY is FALSE) AND (no Abra on bench)
      3. Enriching Energy
      4. Basic Psychic Energy
      5. Any energy (do not fail this part)
    POKEMON selection:
      1. ZAM    — if (no ZAM in hand) AND (Rare Candy in hand)
      2. Kadabra — if no Kadabra in hand
      3. Dudunsparce — if no Dudunsparce in hand
      4. TWM   — if STRANGE is ON
      5. ZAM   — if no ZAM in hand
      6. Kadabra
      7. Dudunsparce
      8. ZAM
      9. TWM
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Enriching Energy attachment ────────────────────────────────────────────
  IF (Enriching Energy in hand) AND (ATTACHED_ENERGY is FALSE) AND (DECK_SIZE > 5):
    Attach Enriching Energy in this priority:
      1. Benched Dunsparce
      2. Active Dunsparce
      3. Genesect
      4. Shaymin
      5. Abra
      6. Any Pokémon
    SET ATTACHED_ENERGY = TRUE
    // Draw 4 cards (Enriching Energy's effect)
    → RESTART LOOP

  // ── Dawn (second opportunity) ──────────────────────────────────────────────
  IF (Dawn in hand) AND (SUPPORTER_USED is FALSE) AND (DECK_SIZE > 5):
    Use Dawn; choose 3 Pokémon:
      For the Basic slot:
        1. Dunsparce — if no Dunsparce in play
        2. Shaymin   — if BARRIER is ON
        3. Abra      — if ≤1 Abra in play
        4. Genesect  — if a Tool in hand
        5. Dunsparce — if ≤1 Dunsparce in play
        6. Abra
        7. Dunsparce
        8. Genesect
        9. Fezandipiti ex
        10. Any Pokémon
      For the Stage 1 slot:
        1. Kadabra    — if no Kadabra in hand
        2. Dudunsparce — if no Dudunsparce in hand
        3. Kadabra
        4. Dudunsparce
      For the Stage 2 slot:
        1. TWM — if STRANGE is ON
        2. ZAM
        3. Any Pokémon
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Poké Pad (main) ────────────────────────────────────────────────────────
  // Use Poké Pad if any of these conditions are true (DECK_SIZE > 5 required):
  IF (Poké Pad in hand) AND (DECK_SIZE > 5) AND (any of below):
    Priority of search target:
      1. Abra     — if ≤1 Abra on board
      2. Shaymin  — if BARRIER is ON AND no Shaymin on board
      3. Dunsparce — if no Dunsparce on board
      4. Kadabra  — if no Kadabra in hand
      5. Genesect — if no Genesect on board AND a Tool in hand
      6. (fall through: only use Poké Pad if one of the above applies)
    If a target is found in deck, use Poké Pad with that target.
    If the desired target isn't in the deck, choose any Pokémon (do not fail the search).
    → RESTART LOOP

  // ── Basic Psychic Energy attachment ───────────────────────────────────────
  IF (Basic Psychic Energy in hand) AND (Abra in play) AND (ATTACHED_ENERGY is FALSE):
    Attach Basic Psychic Energy in this priority:
      1. Active Abra
      2. Any Abra
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Tool on Genesect ──────────────────────────────────────────────────────
  IF (Genesect in play) AND (Tool in hand) AND (OPP_ACE_USED is OFF):
    Attach tool to Genesect in this priority:
      1. Air Balloon
      2. Lucky Helmet
    → RESTART LOOP

  // ── Battle Cage ───────────────────────────────────────────────────────────
  IF (CAGE is ON) AND (Battle Cage in hand):
    Play Battle Cage
    → RESTART LOOP

  // ── Abra's Teleportation Attack ───────────────────────────────────────────
  IF (Abra is active) AND (Abra has a Psychic or Telepathic Energy attached):
    Attack with Teleportation Attack; promote in Promote Priority order:
      1. Dunsparce
      2. Genesect
      3. Abra
      4. Shaymin
      5. Any Shaymin
    → END TURN (attacking ends the turn)

} // end LOOP — no more actions available → pass
```

---

## Main Game Loop

> **Loop rule**: After completing any single action, restart from the top of this loop.
> **Turn-start resets**: Set `SUPPORTER_USED = FALSE`, `ATTACHED_ENERGY = FALSE`, `OPP_KO_LAST_TURN` = (any of your Pokémon was KO'd during opponent's last turn).
> **Supporter rule**: Only one Supporter per turn. If `SUPPORTER_USED` is TRUE, skip all Supporter plays.
> **DECK_SIZE ≤ 5** restrictions apply throughout.

```
LOOP {

  // ── Battle Cage / Watchtower ───────────────────────────────────────────────
  IF (Battle Cage in hand) AND (CAGE is ON OR Team Rocket's Watchtower is in play as stadium):
    Play Battle Cage
    → RESTART LOOP

  // ── Sacred Ash ─────────────────────────────────────────────────────────────
  IF (Sacred Ash in hand) AND (≥3 Pokémon in your discard pile):
    Use Sacred Ash; choose up to 5 Pokémon in this priority:
      1. Shaymin    — if BARRIER is ON
      2. TWM        — if STRANGE is ON
      3. Genesect   — if OPP_ACE_USED is OFF
      4. ZAM
      5. Abra
      6. Kadabra
      7. Dunsparce
      8. Dudunsparce
      9. Fezandipiti ex
      10. Any Pokémon
    → RESTART LOOP

  // ── Fezandipiti ex Flip the Script ─────────────────────────────────────────
  IF (Fezandipiti ex on board) AND (OPP_KO_LAST_TURN is TRUE) AND (DECK_SIZE > 5):
    Use Flip the Script — draw 3 cards
    → RESTART LOOP

  // ── Dudunsparce Run Away Draw (active) ─────────────────────────────────────
  IF (Dudunsparce is active) AND (DECK_SIZE > 5):
    Use Run Away Draw — draw 3, shuffle Dudunsparce back into deck
    // Board update: active spot becomes empty → promote per Promote Priority
    → RESTART LOOP

  // ── Evolve active Dunsparce → Dudunsparce ─────────────────────────────────
  IF (Dunsparce is active) AND (Dudunsparce in hand) AND (Dunsparce was NOT placed this turn):
    Evolve active Dunsparce into Dudunsparce
    → RESTART LOOP

  // ── Evolve Dunsparce with Enriching Energy → Dudunsparce ──────────────────
  IF (a Dunsparce with Enriching Energy attached is on board) AND (Dudunsparce in hand)
     AND (that Dunsparce was NOT placed this turn):
    Evolve that Dunsparce into Dudunsparce
    → RESTART LOOP

  // ── Evolve any Dunsparce → Dudunsparce ────────────────────────────────────
  IF (any Dunsparce on board, not placed this turn) AND (Dudunsparce in hand):
    Evolve that Dunsparce into Dudunsparce
    → RESTART LOOP

  // ── Bench Abra ─────────────────────────────────────────────────────────────
  IF (Abra in hand) AND (≤2 Dunsparce-line on board):
    // "≤2 Dunsparce on board" means total Dunsparce + Dudunsparce count ≤ 2
    Bench Abra
    → RESTART LOOP

  // ── Bench Dunsparce ────────────────────────────────────────────────────────
  IF (Dunsparce in hand) AND (≤1 Dunsparce-line on board):
    Bench Dunsparce
    → RESTART LOOP

  // ── Bench Shaymin (only if BARRIER ON) ────────────────────────────────────
  IF (BARRIER is ON) AND (Shaymin in hand):
    Bench Shaymin
    → RESTART LOOP

  // ── Bench Genesect ─────────────────────────────────────────────────────────
  IF (Genesect in hand) AND (OPP_ACE_USED is OFF) AND (a Tool in hand):
    Bench Genesect
    → RESTART LOOP

  // ── Evolve benched Abra → Kadabra ─────────────────────────────────────────
  IF (≥2 Abra on board) AND (Kadabra in hand):
    Evolve a benched Abra into Kadabra
    IF (DECK_SIZE > 5): draw 2 (Kadabra's Psychic Draw ability)
    → RESTART LOOP

  // ── Evolve active Kadabra → ZAM (STRANGE OFF) ─────────────────────────────
  IF (Kadabra is active) AND (ZAM in hand) AND (STRANGE is OFF)
     AND (Kadabra NOT evolved this turn):
    Evolve active Kadabra into ZAM
    IF (DECK_SIZE > 5): draw 3 (ZAM's Psychic Draw ability)
    → RESTART LOOP

  // ── Evolve active Kadabra → TWM (STRANGE ON) ──────────────────────────────
  IF (Kadabra is active) AND (TWM in hand) AND (STRANGE is ON)
     AND (Kadabra NOT evolved this turn):
    Evolve active Kadabra into TWM
    → RESTART LOOP

  // ── Rare Candy: Abra → ZAM (STRANGE OFF) ──────────────────────────────────
  IF (Rare Candy in hand) AND (ZAM in hand) AND (STRANGE is OFF):
    Use Rare Candy on target in this priority:
      1. Active Abra
      2. Benched Abra with a Basic Psychic Energy OR Telepathic Energy attached
      3. Any Abra
    (Abra must NOT have been placed this turn)
    Evolve target into ZAM
    IF (DECK_SIZE > 5): draw 3 (ZAM's Psychic Draw ability)
    → RESTART LOOP

  // ── Rare Candy: Abra → TWM (STRANGE ON) ──────────────────────────────────
  IF (Rare Candy in hand) AND (TWM in hand) AND (STRANGE is ON):
    Use Rare Candy on target in this priority:
      1. Active Abra
      2. Benched Abra with a Basic Psychic Energy OR Telepathic Energy attached
      3. Any Abra
    (Abra must NOT have been placed this turn)
    Evolve target into TWM
    → RESTART LOOP

  // ── Attach Telepathic Energy to active ZAM/TWM (no energy) ────────────────
  IF (active Pokémon is ZAM or TWM) AND (active has NO Basic Psychic Energy AND NO Telepathic Energy)
     AND (Telepathic Energy in hand) AND (ATTACHED_ENERGY is FALSE):
    Attach Telepathic Energy to active Pokémon; bench up to 2 Basic {P} Pokémon from search
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Attach Basic Psychic Energy to active ZAM/TWM (no energy) ──────────────
  IF (active Pokémon is ZAM or TWM) AND (active has NO Basic Psychic Energy AND NO Telepathic Energy)
     AND (Basic Psychic Energy in hand) AND (ATTACHED_ENERGY is FALSE):
    Attach Basic Psychic Energy to active Pokémon
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Evolve benched Kadabra → ZAM (STRANGE OFF) ────────────────────────────
  IF (ZAM in hand) AND (STRANGE is OFF) AND (benched Kadabra exists, not evolved this turn):
    Evolve that benched Kadabra into ZAM
    IF (DECK_SIZE > 5): draw 3 (ZAM's Psychic Draw ability)
    → RESTART LOOP

  // ── Night Stretcher: Shaymin (BARRIER ON) ─────────────────────────────────
  IF (Night Stretcher in hand) AND (BARRIER is ON) AND (Shaymin is in discard):
    Use Night Stretcher; take Shaymin
    → RESTART LOOP

  // ── Poké Pad: Shaymin (BARRIER ON, not on board or discard) ───────────────
  IF (BARRIER is ON) AND (no Shaymin on board) AND (Shaymin NOT in discard)
     AND (Poké Pad in hand) AND (DECK_SIZE > 5):
    Use Poké Pad; choose from priority:
      1. Shaymin
      2. Genesect — if Tool in hand
      3. Kadabra
      4. Dunsparce
      5. TWM — if STRANGE is ON
      6. ZAM
      7. Abra
      8. Dunsparce
      9. Genesect
      10. Any Pokémon
    → RESTART LOOP

  // ── Poké Pad: evolution setup (Abra/Dunsparce on board) ───────────────────
  IF (Poké Pad in hand) AND (DECK_SIZE > 5)
     AND (any Abra on board that was NOT placed this turn
          OR any Dunsparce on board that was NOT placed this turn):
    Use Poké Pad; choose from priority:
      1. ZAM       — if Rare Candy in hand AND STRANGE is OFF
      2. Kadabra   — if an Abra on board was not placed this turn
      3. Dudunsparce — if a Dunsparce on board was not placed this turn
      4. TWM       — if STRANGE is ON
      5. ZAM
      6. Kadabra
      7. Dunsparce
      8. Abra
      9. Dudunsparce
      10. Any Pokémon
    → RESTART LOOP

  // ── Poké Pad: Kadabra not evolved this turn ────────────────────────────────
  IF (Poké Pad in hand) AND (DECK_SIZE > 5)
     AND (a Kadabra on board was NOT evolved this turn):
    Use Poké Pad; choose from priority:
      1. ZAM
      2. Kadabra   — if an Abra on board was not placed this turn
      3. Dudunsparce — if a Dunsparce on board was not placed this turn
      4. TWM       — if STRANGE is ON
      5. Genesect
      6. Kadabra
      7. Dunsparce
      8. Abra
      9. Dudunsparce
      10. Any Pokémon
    → RESTART LOOP

  // ── Night Stretcher: Genesect (ACE Nullifier setup) ───────────────────────
  IF (Night Stretcher in hand) AND (OPP_ACE_USED is OFF)
     AND (Tool in hand) AND (Genesect in discard):
    Use Night Stretcher; take Genesect
    → RESTART LOOP

  // ── Night Stretcher: TWM (STRANGE ON) ─────────────────────────────────────
  IF (Night Stretcher in hand) AND (STRANGE is ON) AND (TWM in discard):
    Use Night Stretcher; take TWM
    → RESTART LOOP

  // ── Poké Pad: TWM (STRANGE ON, not in play or hand) ───────────────────────
  IF (STRANGE is ON) AND (no TWM in play or hand) AND (Poké Pad in hand) AND (DECK_SIZE > 5):
    Use Poké Pad; choose from priority:
      1. TWM
      2. Kadabra   — if an Abra on board was not placed this turn
      3. Dudunsparce — if a Dunsparce on board was not placed this turn
      4. ZAM
      5. Kadabra
      6. Dunsparce
      7. Abra
      8. Dudunsparce
      9. Any Pokémon
    → RESTART LOOP

  // ── Night Stretcher: ZAM (not in hand or play) ────────────────────────────
  IF (Night Stretcher in hand) AND (no ZAM in hand or in play) AND (ZAM in discard):
    Use Night Stretcher; take ZAM
    → RESTART LOOP

  // ── Lana's Aid: TWM (STRANGE ON, not in hand or play, in discard) ──────────
  IF (Lana's Aid in hand) AND (STRANGE is ON)
     AND (no TWM in hand or in play) AND (TWM in discard) AND (SUPPORTER_USED is FALSE):
    Use Lana's Aid; choose up to 3 cards from discard:
      1. TWM
      2. Any Energy
      3. Abra
      4. Kadabra
      5. Genesect
      6. Shaymin
      7. Dunsparce
      8. Dudunsparce
      9. Any eligible card
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Lana's Aid: ZAM (not in hand or play, in discard) ─────────────────────
  IF (Lana's Aid in hand) AND (no ZAM in hand or in play) AND (ZAM in discard)
     AND (SUPPORTER_USED is FALSE):
    Use Lana's Aid; choose up to 3 cards from discard:
      1. ZAM
      2. Any Energy
      3. Abra
      4. Kadabra
      5. Genesect
      6. Shaymin
      7. Dunsparce
      8. Dudunsparce
      9. Any eligible card
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Night Stretcher: Basic Psychic Energy (active ZAM/TWM has no energy) ──
  IF (Night Stretcher in hand) AND (active is ZAM or TWM) AND (active has no energy attached)
     AND (Basic Psychic Energy in discard):
    Use Night Stretcher; take Basic Psychic Energy
    → RESTART LOOP

  // ── Lana's Aid: Basic Psychic Energy (active ZAM/TWM has no energy) ────────
  IF (Lana's Aid in hand) AND (active is ZAM or TWM) AND (active has no energy attached)
     AND (Basic Psychic Energy in discard) AND (SUPPORTER_USED is FALSE):
    Use Lana's Aid; choose up to 3 cards in priority:
      1. Basic Psychic Energy
      2. ZAM
      3. TWM (if STRANGE is ON)
      4. Kadabra
      5. Abra
      6. Any eligible card
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Retreat to ZAM/TWM (bench has energized ZAM/TWM, active is passive) ───
  IF (a ZAM or TWM with energy attached is on the bench)
     AND (active Pokémon is Genesect OR Shaymin OR Fezandipiti ex):
    First, attach any energy to the active Pokémon to pay retreat cost if needed
    Retreat active Pokémon; promote the ZAM or TWM with energy attached
    → RESTART LOOP

  // ── Boss's Orders: pull high-value benched target ─────────────────────────
  // Condition A: opponent's active is too bulky but a benched target is KO-able
  damage = (HAND * 20) + (60 * count_of_dudunsparce_on_bench)
  damage_after_boss = damage - 20  // -1 for Boss's Orders card played from hand

  IF (Boss's Orders in hand) AND (active is ZAM with energy attached)
     AND (damage < opponent_active_HP)
     AND (damage_after_boss ≥ HP_of_at_least_one_opponent_benched_pokemon)
     AND (SUPPORTER_USED is FALSE):
    Use Boss's Orders; choose the opponent's benched Pokémon whose HP is closest to
    damage_after_boss WITHOUT EXCEEDING IT
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // Condition B: a benched opponent Pokémon is worth MORE prizes than the active
  IF (Boss's Orders in hand) AND (active is ZAM with energy attached)
     AND (any opponent's benched Pokémon is worth more prize cards than opponent's active)
     AND (damage_after_boss ≥ HP of that higher-value benched Pokémon)
     AND (SUPPORTER_USED is FALSE):
    Use Boss's Orders; choose the highest-value benched Pokémon whose HP is closest to
    damage_after_boss WITHOUT EXCEEDING IT
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Attach energy to active ZAM/TWM ───────────────────────────────────────
  IF (active is ZAM or TWM) AND (ATTACHED_ENERGY is FALSE):
    IF (Telepathic Energy in hand):
      Attach Telepathic Energy; bench up to 2 Basic {P} Pokémon from search
      SET ATTACHED_ENERGY = TRUE
      → RESTART LOOP
    ELSE IF (Basic Psychic Energy in hand):
      Attach Basic Psychic Energy to active Pokémon
      SET ATTACHED_ENERGY = TRUE
      → RESTART LOOP

  // ── Enriching Energy: attach to support Pokémon ───────────────────────────
  IF (Enriching Energy in hand) AND (active is ZAM or TWM with energy attached)
     AND (ATTACHED_ENERGY is FALSE) AND (DECK_SIZE > 5):
    Attach Enriching Energy in this priority:
      1. Benched Dudunsparce
      2. Benched Dunsparce
      3. Shaymin
      4. Genesect
      5. Fezandipiti ex
      6. Any Pokémon
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Hilda (first opportunity — if haven't attached yet) ───────────────────
  IF (Hilda in hand) AND (SUPPORTER_USED is FALSE) AND (DECK_SIZE > 5)
     AND (ATTACHED_ENERGY is FALSE):
    Use Hilda; choose 1 Energy + 1 Evolution Pokémon:
    ENERGY:
      1. Telepathic Energy — if active has no energy attached
      2. Basic Psychic Energy — if active has no energy attached
      3. Enriching Energy — if active has an energy attached
      4. Enriching Energy
      5. Basic Psychic Energy
      6. Any energy (do not fail)
    POKEMON:
      1. ZAM       — if (an Abra NOT placed this turn is on board) AND (Rare Candy in hand)
      2. ZAM       — if a Kadabra NOT placed this turn is on board
      3. Kadabra   — if no Kadabra in hand
      4. Dudunsparce — if no Dudunsparce in hand
      5. TWM       — if STRANGE is ON
      6. ZAM       — if no ZAM in hand
      7. Kadabra
      8. Dudunsparce
      9. ZAM
      10. TWM
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Dawn ──────────────────────────────────────────────────────────────────
  IF (Dawn in hand) AND (SUPPORTER_USED is FALSE) AND (DECK_SIZE > 5):
    Use Dawn; choose 3 Pokémon:
      For the Basic slot:
        1. Dunsparce   — if no Dunsparce in play
        2. Shaymin     — if BARRIER is ON
        3. Abra        — if ≤1 Abra in play
        4. Genesect    — if a Tool in hand
        5. Fezandipiti ex
        6. Dunsparce   — if ≤1 Dunsparce in play
        7. Abra
        8. Dunsparce
        9. Genesect
        10. Any Pokémon
      For the Stage 1 slot:
        1. Kadabra    — if an Abra NOT placed this turn is on board
        2. Dudunsparce — if a Dunsparce NOT placed this turn is on board
        3. Kadabra
        4. Dudunsparce
      For the Stage 2 slot:
        1. TWM — if STRANGE is ON
        2. ZAM
        3. Any Pokémon
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Hilda (second opportunity — unconditional) ─────────────────────────────
  IF (Hilda in hand) AND (SUPPORTER_USED is FALSE) AND (DECK_SIZE > 5):
    Use Hilda; choose 1 Energy + 1 Evolution Pokémon:
    ENERGY:
      1. Telepathic Energy — if active has no energy attached
      2. Basic Psychic Energy — if active has no energy attached
      3. Enriching Energy — if active has an energy attached
      4. Enriching Energy
      5. Basic Psychic Energy
      6. Any energy (do not fail)
    POKEMON:
      1. ZAM       — if (an Abra NOT placed this turn is on board) AND (Rare Candy in hand)
      2. ZAM       — if a Kadabra NOT placed this turn is on board
      3. Kadabra   — if no Kadabra in hand
      4. Dudunsparce — if no Dudunsparce in hand
      5. TWM       — if STRANGE is ON
      6. ZAM       — if no ZAM in hand
      7. Kadabra
      8. Dudunsparce
      9. ZAM
      10. TWM
    SET SUPPORTER_USED = TRUE
    → RESTART LOOP

  // ── Attach Psychic/Telepathic to benched Kadabra ──────────────────────────
  IF (benched Kadabra exists) AND (Psychic or Telepathic Energy in hand)
     AND (ATTACHED_ENERGY is FALSE):
    Attach to a benched Kadabra
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Attach Psychic/Telepathic to benched Abra ─────────────────────────────
  IF (benched Abra exists) AND (Psychic or Telepathic Energy in hand)
     AND (ATTACHED_ENERGY is FALSE):
    Attach to a benched Abra
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Attach Enriching Energy to benched Dudunsparce/Dunsparce ──────────────
  IF (Enriching Energy in hand) AND (ATTACHED_ENERGY is FALSE) AND (DECK_SIZE > 5):
    Attach Enriching Energy in this priority:
      1. Benched Dudunsparce
      2. Benched Dunsparce
    SET ATTACHED_ENERGY = TRUE
    → RESTART LOOP

  // ── Tool on Genesect (late — only if HAND is high enough to attack) ────────
  // (HAND * 20 - 40): -40 = -20 for the tool from hand, -20 for the Genesect bench cost
  // Actually: attach tool (-1 from HAND) then would have HAND-1 cards → (HAND-1)*20 damage
  // Rule: only attach if damage after attaching would still beat opp active HP
  IF (Genesect in play) AND (Tool in hand) AND (OPP_ACE_USED is OFF)
     AND ((HAND * 20 - 40) > opponent_active_HP):
    // Note: -40 = 2 cards removed from hand equivalent (tool itself + effective cost)
    Attach tool to Genesect in this priority:
      1. Air Balloon
      2. Lucky Helmet
    → RESTART LOOP

  // ── Bench Fezandipiti ex (draw setup) ────────────────────────────────────
  IF (HAND * 20 < opponent_active_HP) AND (STRANGE is OFF)
     AND (OPP_KO_LAST_TURN is TRUE) AND (Fezandipiti ex in hand):
    Bench Fezandipiti ex
    → RESTART LOOP

  // ── Dudunsparce Run Away Draw (bench) — when HAND is insufficient ─────────
  IF (HAND * 20 < opponent_active_HP) AND (STRANGE is OFF)
     AND (benched Dudunsparce WITH Enriching Energy attached exists) AND (DECK_SIZE > 5):
    Use that Dudunsparce's Run Away Draw — draw 3, shuffle Dudunsparce back into deck
    → RESTART LOOP

  IF (HAND * 20 < opponent_active_HP) AND (STRANGE is OFF)
     AND (any benched Dudunsparce exists) AND (DECK_SIZE > 5):
    Use that Dudunsparce's Run Away Draw — draw 3, shuffle Dudunsparce back into deck
    → RESTART LOOP

  // ── Buddy-Buddy Poffin (when HAND damage ≥ opp HP after −1 card) ──────────
  IF ((HAND * 20 - 20) ≥ opponent_active_HP) AND (Buddy-Buddy Poffin in hand):
    Use Buddy-Buddy Poffin; take max Dunsparce first, then Abra:
      SLOT 1: Dunsparce (if available); else Abra
      SLOT 2: Same priority
    → RESTART LOOP

  // ── Attach Lucky Helmet (when HAND damage ≥ opp HP after −1 card) ─────────
  IF ((HAND * 20 - 20) ≥ opponent_active_HP) AND (Lucky Helmet in hand)
     AND (ATTACHED_ENERGY is FALSE or this is a tool not energy):
    // Lucky Helmet doesn't count as energy attachment, always allowed if rules allow
    Attach Lucky Helmet to active Pokémon
    → RESTART LOOP

  // ── Attack ────────────────────────────────────────────────────────────────
  IF (active is ZAM with energy attached):
    Use Powerful Hand attack
    // Damage = HAND × 20
    → END TURN

  IF (active is TWM with energy attached):
    Use Psychic attack (NEVER use Strange Hacking)
    // Damage = 10 + (50 × number of energies on opponent's active Pokémon)
    → END TURN

} // end LOOP — no actions remain → pass turn
```

---

## Clarifications & Notes

### On "HAND" Tracking
`HAND` must be updated every time a card is drawn or played:
- Drawing a card: `HAND += 1`
- Playing a card from hand: `HAND -= 1`
- Enriching Energy attached: `HAND += 4` (after the draw trigger)
- Telepathic Energy attached: bench 2 Pokémon from deck (no hand size change from search)
- Kadabra evolve: `HAND += 2` (Psychic Draw, if DECK_SIZE > 5)
- ZAM evolve: `HAND += 3` (Psychic Draw, if DECK_SIZE > 5)
- Dudunsparce Run Away Draw: `HAND += 3` (then Dudunsparce leaves board to deck)
- Fezandipiti Flip the Script: `HAND += 3`
- Lucky Helmet trigger (when damaged): `HAND += 2`

### On Telepathic Energy
After attaching Telepathic Energy to a Psychic Pokémon, search the deck for up to 2 Basic Psychic ({P}) Pokémon. Always take the maximum available (both slots if there are 2 eligible Pokémon in deck). These go directly to the bench, NOT the hand. `HAND` does NOT change from this search.

### On Rare Candy
Rare Candy cannot be used:
- On your first turn of the game
- On a Pokémon that was put into play this turn

### On Evolution Restrictions
No Pokémon can be evolved on the same turn it was placed in play (Rare Candy has the same restriction). Kadabra cannot evolve on the same turn it evolved from Abra.

### On Supporters
Only one Supporter card can be played per turn. The order of preference within the main loop naturally handles this (first valid Supporter wins, `SUPPORTER_USED` prevents a second play).

### On "STRANGE is ON" Attack Choice for TWM
TWM should ONLY ever use the **Psychic** attack (10 + 50 per energy on opponent's active). **Never use Strange Hacking** (despite the STRANGE variable name — STRANGE refers to the opponent's board setup, not the attack). Strange Hacking is not part of the agent's attack plan.

### On Boss's Orders Damage Calculation
`damage = (HAND × 20) + (60 × count_of_benched_dudunsparce)`
The +60 per Dudunsparce represents using each one's Run Away Draw (+3 cards = +60 damage) before attacking. After playing Boss's Orders, `HAND` decreases by 1 (you played the card), so effective damage = `damage - 20`.
Only pull a benched target if the modified damage can KO it.

### On Buddy-Buddy Poffin Targets
Buddy-Buddy Poffin searches for Basics with **70 HP or less**. In this deck, that is only:
- Dunsparce (70 HP) ✓
- Abra (50 HP) ✓
- Shaymin (80 HP) ✗ — too high
- Genesect (110 HP) ✗ — too high

### On Prize Card Value
- Standard Pokémon: 1 prize
- ex / V Pokémon: 2 prizes
- Mega ex / VMAX Pokémon: 3 prizes
- Fezandipiti ex is worth 2 prizes

### On STRANGE vs BARRIER vs CAGE
These three variables are independent and can all be ON simultaneously:
- **STRANGE ON** → use TWM instead of ZAM as the primary attacker
- **BARRIER ON** → bench Shaymin for bench protection; prioritize Shaymin recovery
- **CAGE ON** → play Battle Cage as soon as possible

### On the Active Dunsparce Special Case
The "Bench Dunsparce" rule says bench if ≤1 Dunsparce on board. But one Dunsparce is likely your active. So this rule effectively says: bench a second Dunsparce if only one total is in play (active or bench). The intent is to have 1–2 Dunsparce available for evolution into Dudunsparce.

### On Sacred Ash
Sacred Ash requires ≥3 Pokémon in the discard pile to use. It shuffles up to 5 Pokémon back into the deck. Use it proactively to maintain deck size and recycle key Pokémon.
