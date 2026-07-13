"""
effect_features.py — Structured attack/ability effect-model parser.

Parses an attack/ability's free-text "Effect Explanation" into a fixed-width structured
MODIFIER vector (MODIFIER_DIM = 27) instead of leaving effect text as an opaque string.
The realized value of a conditional/scaling modifier (does the bonus fire on THIS board?
what does it scale to right now?) is a board-evaluated concern handled by pokemon_encoder;
this module emits only the *static spec* (what the attack CAN do).

Ported from the sibling ptcg-kaggle-fork's learn/effect_features.py (same regex patterns,
same vocab), with two additions on top of the fork's 26-dim vector:
  - a `coin_flip` CONDITION entry (26 -> 27 dims), so a coin-flip-gated bonus_flat
    ("Flip a coin. If heads, this attack does 50 more damage.") is distinguishable from
    an unconditional one — the fork's parser had no way to tell these apart.
  - `expected_heads(text)`, a deliberately primitive coin-flip expected-value helper that
    only distinguishes a BOUNDED flip ("flip 2 coins" -> N*0.5 heads expected) from an
    UNBOUNDED one ("flip until you get tails" -> 1.0 heads expected, by the standard
    geometric-distribution memorylessness argument). Nothing fancier than that split.

Pure-Python, regex-only (no torch/numpy/csv).

    python effect_features.py        # self-test / spot-checks
"""
from __future__ import annotations

import re

# --- vocab --------------------------------------------------------------------
SCALE_VARS = ["energy", "benched", "heads", "discard", "counters",
              "pokemon", "prizes", "hand", "tools", "status"]
BYPASS = ["ignore_weakness", "ignore_resistance", "ignore_target_effects"]
CONDITIONS = ["target_status", "energy_count", "bench_count", "self_has_damage",
              "target_type", "target_is_ex", "stadium_in_play", "self_status",
              "coin_flip"]

MAX_DAMAGE = 400.0
MAX_TARGETS = 6.0
_COUNTER = 10.0

# Ability-effect / non-damage-effect keyword bag (fork's card_features.EFFECT_KEYWORDS,
# kept verbatim per the decision to leave abilities on the simple keyword-flag
# representation rather than the structured modifier vector — flagged for later manual
# revision once the meta-deck review pass happens).
EFFECT_KEYWORDS = [
    "draw", "search your deck", "discard", "bench", "retreat", "switch",
    "damage counter", "poison", "burn", "paralyzed", "confused", "asleep",
    "flip a coin", "heads", "tails",
    "heal", "remove damage",
    "attach", "energy",
    "evolve", "knock out",
    "active spot", "benched pokémon",
    "can't attack", "can't retreat",
    "during your next turn", "opponent's next turn",
    "prize", "extra prize",
    "shuffle", "look at the top",
    "your hand", "opponent's hand",
    "both active pokémon",
    "leave the active spot",
    "ancient", "future",
    "rule box",
    "special condition",
    "ability",
]


# MODIFIER vector layout:
#   bonus_flat(1) | scale_onehot(10) | scale_amount(1) | bench_dmg(1) | bench_targets(1)
#   | self_dmg(1) | bypass(3) | condition_onehot(9)
MODIFIER_DIM = 1 + len(SCALE_VARS) + 1 + 1 + 1 + 1 + len(BYPASS) + len(CONDITIONS)
assert MODIFIER_DIM == 27, MODIFIER_DIM


def modifier_schema() -> list:
    out = ["bonus_flat"]
    out += [f"scale:{v}" for v in SCALE_VARS]
    out += ["scale_amount", "bench_dmg", "bench_targets", "self_dmg"]
    out += [f"bypass:{b.split('_', 1)[1]}" for b in BYPASS]
    out += [f"cond:{c}" for c in CONDITIONS]
    assert len(out) == MODIFIER_DIM
    return out


def _norm(text) -> str:
    if not text or text == "n/a":
        return ""
    return (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"'))


# --- patterns -------------------------------------------------------------------
_RX_SCALE = re.compile(r"(\d+)\s+(?:more\s+)?damage\s+for each\s+([^.]{0,60})", re.I)
_RX_BONUS = re.compile(r"(\d+)\s+more damage(?!\s+for each)(?!\s+counter)", re.I)
_RX_SELF_DMG = re.compile(r"(\d+)\s+damage to itself", re.I)
_RX_SELF_CTR = re.compile(r"put (?:up to )?(\d+)\s+damage counters? on this Pok", re.I)
_RX_BENCH = re.compile(r"(\d+)\s+damage to (each|all|\d+)\b", re.I)
_RX_BYPASS_WR = re.compile(r"isn't affected by Weakness or Resistance", re.I)
_RX_BYPASS_EFF = re.compile(r"by any effects on", re.I)

# coin-flip phrasing, used both for the coin_flip condition gate and expected_heads()
_RX_FLIP_UNTIL_TAILS = re.compile(r"flip a coin until you get tails", re.I)
_RX_FLIP_N = re.compile(r"flip (\d+) coins?", re.I)
_RX_FLIP_ONE = re.compile(r"flip a coin\b", re.I)
_RX_FLIP_HEADS_GATE = re.compile(r"flip a coin\.?\s*if heads", re.I)


def _scale_var(tail: str):
    tl = tail.lower()
    if "heads" in tl:
        return "heads"
    if "discard" in tl:
        return "discard"
    if "damage counter" in tl:
        return "counters"
    if "prize" in tl:
        return "prizes"
    if "tool" in tl:
        return "tools"
    if "special condition" in tl:
        return "status"
    if "hand" in tl:
        return "hand"
    if "bench" in tl:
        return "benched"
    if "energy" in tl:
        return "energy"
    if "pok" in tl:
        return "pokemon"
    return None


def expected_heads(text) -> float:
    """Primitive coin-flip EV: expected number of heads.
    - unbounded ("flip a coin until you get tails") -> 1.0 (geometric-distribution EV)
    - bounded ("flip N coins" / "flip a coin") -> N * 0.5
    - no flip phrase found -> 1.0 (no-op multiplier; callers only invoke this when a
      coin-flip signal is already known to be present)."""
    t = _norm(text)
    if not t:
        return 1.0
    if _RX_FLIP_UNTIL_TAILS.search(t):
        return 1.0
    m = _RX_FLIP_N.search(t)
    if m:
        return int(m.group(1)) * 0.5
    if _RX_FLIP_ONE.search(t):
        return 0.5
    return 1.0


def parse_effect(text) -> dict:
    """Parse one effect string -> a structured-modifier dict (readable; for spot-checks).
    Numbers are RAW (un-normalized)."""
    t = _norm(text)
    out = {"bonus_flat": 0, "scale_var": None, "scale_amount": 0,
           "bench_dmg": 0, "bench_targets": 0, "self_dmg": 0,
           "bypass": [], "conditions": []}
    if not t:
        return out

    best = None
    for m in _RX_SCALE.finditer(t):
        amt = int(m.group(1))
        if best is None or amt > best[0]:
            best = (amt, _scale_var(m.group(2)))
    if best is not None:
        out["scale_amount"], out["scale_var"] = best

    bonuses = [int(m.group(1)) for m in _RX_BONUS.finditer(t)
               if "take" not in t[max(0, m.start() - 14):m.start()].lower()]
    if bonuses:
        out["bonus_flat"] = max(bonuses)

    self_hp = [int(m.group(1)) for m in _RX_SELF_DMG.finditer(t)]
    self_hp += [int(m.group(1)) * int(_COUNTER) for m in _RX_SELF_CTR.finditer(t)]
    if self_hp:
        out["self_dmg"] = max(self_hp)

    bench = None
    for m in _RX_BENCH.finditer(t):
        amt, q = int(m.group(1)), m.group(2).lower()
        if bench is None or amt > bench[0]:
            bench = (amt, q)
    if bench is not None:
        out["bench_dmg"] = bench[0]
        out["bench_targets"] = -1 if bench[1] in ("each", "all") else int(bench[1])

    if _RX_BYPASS_WR.search(t):
        out["bypass"] += ["ignore_weakness", "ignore_resistance"]
    if _RX_BYPASS_EFF.search(t):
        out["bypass"].append("ignore_target_effects")

    has_damage_mod = (out["bonus_flat"] > 0 or out["scale_amount"] > 0 or out["bench_dmg"] > 0)
    conds = []
    if has_damage_mod:
        self_status = re.search(
            r"[Tt]his Pok\w* is (?!now)(?:Poisoned|Asleep|Burned|Paralyzed|Confused)", t)
        if self_status:
            conds.append("self_status")
        if (re.search(r"is (?!now)(?:Poisoned|Asleep|Burned|Paralyzed|Confused)", t, re.I)
                and not self_status):
            conds.append("target_status")
        if (re.search(r"[Ii]f [^.]{0,60}Energy attached", t)
                or re.search(r"at least \d+ (?:extra )?Energy", t, re.I)
                or re.search(r"\d+ or more (?:\{?\w?\}? )?Energy", t, re.I)):
            conds.append("energy_count")
        if re.search(r"[Ii]f [^.]{0,60}[Bb]ench", t):
            conds.append("bench_count")
        if re.search(r"this Pok\w* (?:already )?has (?:any|no|\d+)[^.]{0,30}damage counter", t, re.I):
            conds.append("self_has_damage")
        if (re.search(r"Active Pok\w* is an Evolution Pok", t, re.I)
                or re.search(r"Active Pok\w* is an? \{\w\} Pok", t, re.I)
                or re.search(r"same type as", t, re.I)):
            conds.append("target_type")
        if re.search(r"\{ex\}|\{V\}", t) or re.search(r"Active Pok\w* is (?:an? )?Pok\w* ex", t, re.I):
            conds.append("target_is_ex")
        if re.search(r"Stadium is in play", t, re.I):
            conds.append("stadium_in_play")
        if _RX_FLIP_HEADS_GATE.search(t):
            conds.append("coin_flip")
    out["conditions"] = conds
    return out


def effect_vector(text) -> list:
    p = parse_effect(text)
    v = [min(p["bonus_flat"], MAX_DAMAGE) / MAX_DAMAGE]
    v += [1.0 if p["scale_var"] == s else 0.0 for s in SCALE_VARS]
    v.append(min(p["scale_amount"], MAX_DAMAGE) / MAX_DAMAGE)
    v.append(min(p["bench_dmg"], MAX_DAMAGE) / MAX_DAMAGE)
    tgt = 1.0 if p["bench_targets"] == -1 else min(p["bench_targets"], MAX_TARGETS) / MAX_TARGETS
    v.append(tgt)
    v.append(min(p["self_dmg"], MAX_DAMAGE) / MAX_DAMAGE)
    v += [1.0 if b in p["bypass"] else 0.0 for b in BYPASS]
    v += [1.0 if c in p["conditions"] else 0.0 for c in CONDITIONS]
    assert len(v) == MODIFIER_DIM
    return v


def zero_vector() -> list:
    return [0.0] * MODIFIER_DIM


# =======================================================================================
# Spec-03 tag extraction — opponent attack/ability tag blocks
# (specs/completed/03-attack-ability-tagging.md; raw un-normalized values,
# tier-2 keyword layer)
# =======================================================================================

_WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3,
             "four": 4, "five": 5, "six": 6}
_NUM = r"(\d+|an?|one|two|three|four|five|six)"


def _num(tok: str) -> int:
    tok = tok.lower()
    return int(tok) if tok.isdigit() else _WORD_NUM.get(tok, 0)


# Attack tag fields in block order (dims 2-14; dims 0-1 are cost/damage from card data).
ATTACK_TAG_FIELDS = ["snipe", "counter_snipe", "conditional", "item_lock", "cooldown",
                     "energy_accel", "draws_cards", "discard_energy", "cubchoo",
                     "deckout", "probabilistic", "revenge", "outrage",
                     "retreat_lock", "immunity", "recoil"]

# Ability tag fields in block order.
ABILITY_TAG_FIELDS = ["draw", "damage", "immunity", "gust", "energy_active",
                      "energy_bench", "search", "barrier", "heal", "mill", "switch"]

# -- attack patterns --
_RX_TAG_SNIPE = re.compile(
    r"(\d+)\s+damage to [^.]{0,80}?(?:opponent's Benched Pok|of your opponent's Pok)", re.I)
# both-sides bench spread ("damage to each Benched Pokémon (both yours and your
# opponent's)"); self-only spreads read "each OF YOUR Benched" and stay untagged
_RX_TAG_SNIPE_SPREAD = re.compile(r"(\d+)\s+damage to each Benched Pok", re.I)
_RX_TAG_CSNIPE = re.compile(
    r"(?:put|place) " + _NUM + r" damage counters?[^.]{0,80}?opponent's[^.]{0,40}?Pok", re.I)
_RX_TAG_ITEMLOCK = re.compile(r"can't play any Item cards", re.I)
_RX_TAG_COOLDOWN = re.compile(r"During your next turn, this Pok\w+ can't (?:use|attack)", re.I)
# direct attach ("attach a/up-to-N (Basic) Energy") and search-then-attach.
# (?<!they ) excludes opponent-attaches-energy punish effects ("whenever they
# attach an Energy card … place damage counters") — that isn't OUR acceleration.
_RX_TAG_ACCEL = re.compile(
    r"(?<!they )attach (?:up to )?" + _NUM + r" (?:\w+ )?(?:\{\w\} )?Energy", re.I)
_RX_TAG_ACCEL_SEARCH = re.compile(
    r"search your deck for (?:up to )?" + _NUM + r" [^.]{0,40}?Energy cards? and attach", re.I)
# the DRAW / draws_cards tag means WE draw; the lookbehinds drop opponent-ONLY draws
# ("they draw 4 cards", "your opponent draws"). "Each player draws" is kept — it is
# symmetric and we do draw (Comfey, Frosmoth); the mill/deckout side is tagged separately.
_DRAWER = r"(?<!they )(?<!opponent )"
_RX_TAG_DRAWN = re.compile(_DRAWER + r"draws? " + _NUM + r" cards?", re.I)
_RX_TAG_DRAW1 = re.compile(_DRAWER + r"draws? a card", re.I)
_RX_TAG_DISC_N = re.compile(
    r"discard (?:up to )?" + _NUM + r" (?:basic )?(?:\{\w\} )?Energy", re.I)
_RX_TAG_DISC_ALL = re.compile(r"discard all (?:basic |special )?(?:\{\w\} )?Energy", re.I)
_RX_TAG_CUBCHOO = re.compile(r"the Defending Pok\w+ can't (?:use attacks|attack)", re.I)
# genuine mill/deck-out always DISCARDS from the opponent's deck; require that verb so
# "look at / reveal / shuffle into … your opponent's deck" (peeking, not milling) and
# "shuffle … INTO your opponent's deck" (devolve/bounce) don't count.
_RX_TAG_OPPDECK = re.compile(r"discard [^.]{0,40}?(?:of|from) your opponent's deck", re.I)
_RX_TAG_EACHDRAW = re.compile(r"Each player draws?", re.I)
# variable "draw cards until you have N cards in your hand" (attack or ability)
_RX_TAG_DRAW_UNTIL = re.compile(r"draw cards until [^.]*?(\d+)", re.I)
_RX_TAG_TOPDECK = re.compile(
    r"top (?:" + _NUM + r" )?cards? of (?:your|each player's) deck", re.I)
# multi-coin ("Flip 2 coins") and third-person ("Your opponent flips a coin") forms
_RX_TAG_FLIP = re.compile(r"flips? (?:a|\d+) coins?", re.I)
_RX_TAG_RANDOM = re.compile(r"\ba random\b", re.I)
_RX_TAG_KO = re.compile(r"Knocked Out", re.I)
_RX_TAG_LASTTURN = re.compile(r"opponent's last turn", re.I)
_RX_TAG_OUTRAGE = re.compile(r"each damage counter on this Pok", re.I)
# Plan 05 tags. These deliberately encode attack capability, not whether a
# next-turn effect is currently active.
_RX_TAG_RETREAT_LOCK = re.compile(
    r"during your opponent's next turn,[^.]{0,100}(?:can't|cannot) retreat", re.I)
# Require the generic protection sentence to end immediately after "attacks" or
# "this Pokemon". This excludes shields limited to Basic Pokemon and Harden-style
# thresholds ("if that damage is N or less").
# TODO(generalized-own-decks): reconsider immunity for 176 Terapagos ex, 253 Metapod,
# 599 Roggenrola, 737 Mega Manectric ex, 840 Archaludon, and 921 Dipplin. Their
# source/threshold shields do not matter to Ceruledge's planned attackers (apart from
# the accepted Solrock edge case), so they are intentionally excluded for this baseline.
_RX_TAG_IMMUNITY = re.compile(
    r"prevent all damage(?: from and effects of attacks)? done to this Pok\w+"
    r"(?: by attacks)?(?=[.)]|$)", re.I)
_RX_TAG_RECOIL = re.compile(
    r"(?:also )?do(?:es)? (\d+) damage to itself(?! for each)", re.I)


def attack_tags(text, total_cost: int = 0) -> dict:
    """One attack's effect text -> raw tag values (ATTACK_TAG_FIELDS keys).
    total_cost realizes "discard all Energy" (N = the attack's own cost).
    `conditional` is override-table-only and always 0 here."""
    t = _norm(text)
    out = {k: 0 for k in ATTACK_TAG_FIELDS}
    if not t:
        return out

    m = _RX_TAG_SNIPE.search(t) or _RX_TAG_SNIPE_SPREAD.search(t)
    if m:
        out["snipe"] = int(m.group(1))
    m = _RX_TAG_CSNIPE.search(t)
    if m:
        out["counter_snipe"] = _num(m.group(1)) * 10          # damage-equivalent HP
    if _RX_TAG_ITEMLOCK.search(t):
        out["item_lock"] = 1
    if _RX_TAG_COOLDOWN.search(t):
        out["cooldown"] = 1
    m = _RX_TAG_ACCEL.search(t) or _RX_TAG_ACCEL_SEARCH.search(t)
    if m:
        out["energy_accel"] = _num(m.group(1))
    m = _RX_TAG_DRAWN.search(t)
    if m:
        out["draws_cards"] = _num(m.group(1))
    elif _RX_TAG_DRAW1.search(t):
        out["draws_cards"] = 1
    else:
        m = _RX_TAG_DRAW_UNTIL.search(t)
        if m:
            out["draws_cards"] = int(m.group(1))          # target hand size
    if _RX_TAG_DISC_ALL.search(t):
        out["discard_energy"] = total_cost
    else:
        m = _RX_TAG_DISC_N.search(t)
        if m:
            out["discard_energy"] = _num(m.group(1))
    if _RX_TAG_CUBCHOO.search(t):
        out["cubchoo"] = 1
    if _RX_TAG_OPPDECK.search(t) or _RX_TAG_EACHDRAW.search(t):
        out["deckout"] = 1
    if (_RX_TAG_FLIP.search(t) or _RX_TAG_TOPDECK.search(t)
            or _RX_TAG_RANDOM.search(t)):
        out["probabilistic"] = 1
    if _RX_TAG_KO.search(t) and _RX_TAG_LASTTURN.search(t):
        out["revenge"] = 1
    if _RX_TAG_OUTRAGE.search(t):
        out["outrage"] = 1
    if _RX_TAG_RETREAT_LOCK.search(t):
        out["retreat_lock"] = 1
    if _RX_TAG_IMMUNITY.search(t):
        out["immunity"] = 1
    m = _RX_TAG_RECOIL.search(t)
    if m:
        out["recoil"] = int(m.group(1))
    return out


# -- ability patterns --
_RX_ABL_ONCE = re.compile(r"once during your turn", re.I)
_RX_ABL_DRAW_UNTIL = re.compile(r"draw cards until [^.]*?(\d+)", re.I)
# the ability DAMAGE tag means counters dealt to the OPPONENT; the (?! on this Pok…)
# lookahead drops self-counter costs ("put 5 damage counters on this Pokémon" to power
# up its own attack). \b forces the full "counters" so it can't shrink to "counter".
# "put" only (not "place"): the "place N counters" wording here is exclusively
# reactive/retaliation ("place N on the Attacking Pokémon") or self-side downsides,
# neither of which is a proactive opponent-damage ability.
_RX_ABL_DMGCTR = re.compile(
    r"put (?:up to )?" + _NUM
    + r" (?:more )?damage counters?\b(?! on (?:this Pok|itself))", re.I)
_RX_ABL_GUST = re.compile(r"switch in " + _NUM + r" of your opponent's Benched", re.I)
# any energy word (Basic / Spiky / Special) then Energy, so Special-Energy accel
# (e.g. "attach up to 2 Spiky Energy") is caught, not just Basic
_RX_ABL_ATTACH = re.compile(
    r"during your turn, you may attach (?:up to )?" + _NUM + r" \w+ (?:\{\w\} )?Energy", re.I)
# broader form: any "attach {N} <word> Energy card" in ability text (e.g. Oricorio's
# "Attach a Basic {R} Energy card from your hand to 1 of your Benched Pokémon"), which
# the rigid "during your turn, you may attach" anchor misses. (?<!they ) drops the
# opponent-attaches punish phrasing; requiring "card" avoids "Energy attached" scaling.
_RX_ABL_ATTACH_ANY = re.compile(
    r"(?<!they )attach (?:up to )?" + _NUM + r" \w+ (?:\{\w\} )?Energy card", re.I)
_RX_ABL_ATTACH_N = re.compile(r"attach (?:up to )?" + _NUM, re.I)
_RX_ABL_BENCHED = re.compile(r"Benched", re.I)
_RX_ABL_SEARCH = re.compile(r"Search your deck", re.I)
_RX_ABL_SEARCH_N = re.compile(r"Search your deck for (?:up to )?" + _NUM, re.I)
_RX_ABL_HEAL = re.compile(r"heal (?:up to )?" + _NUM + r" damage( counters?)?", re.I)
_RX_ABL_HEAL_ANY = re.compile(r"heal", re.I)
_RX_ABL_SWITCH_RC = re.compile(r"your [^.]{0,60}?Retreat Cost", re.I)
_RX_ABL_SWITCH_1 = re.compile(r"switch (?:1|one) of your (?!opponent)", re.I)
_RX_ABL_SWITCH_ACT = re.compile(r"switch your Active Pok", re.I)
# self-repositioning free switch ("Switch this Pokémon with your Active Pokémon")
_RX_ABL_SWITCH_SELF = re.compile(r"switch (?:this Pok\w+|it) with your Active", re.I)


def ability_tags(text) -> dict:
    """One ability's effect text -> raw tag values (ABILITY_TAG_FIELDS keys).
    `immunity` and `barrier` are override-table-only and always 0 here.
    Numeric tags with a trigger hit but no number use N=1 when the text says
    "once during your turn" (spec 03)."""
    t = _norm(text)
    out = {k: 0 for k in ABILITY_TAG_FIELDS}
    if not t:
        return out
    once = 1 if _RX_ABL_ONCE.search(t) else 0

    m = _RX_TAG_DRAWN.search(t)
    if m:
        out["draw"] = _num(m.group(1))
    else:
        m = _RX_ABL_DRAW_UNTIL.search(t)
        if m:
            out["draw"] = int(m.group(1))                     # target hand size
        elif _RX_TAG_DRAW1.search(t):
            out["draw"] = 1
    m = _RX_ABL_DMGCTR.search(t)
    if m:
        out["damage"] = _num(m.group(1)) * 10                 # damage-equivalent HP
    if _RX_ABL_GUST.search(t):
        out["gust"] = 1
    if _RX_ABL_ATTACH.search(t) or _RX_ABL_ATTACH_ANY.search(t):
        m = _RX_ABL_ATTACH_N.search(t)
        n = _num(m.group(1)) if m else once
        n = n or 1
        if _RX_ABL_BENCHED.search(t):
            out["energy_bench"] = n
        else:
            out["energy_active"] = n
    if _RX_ABL_SEARCH.search(t):
        m = _RX_ABL_SEARCH_N.search(t)
        out["search"] = (_num(m.group(1)) if m else 0) or once or 1
    m = _RX_ABL_HEAL.search(t)
    if m:
        n = _num(m.group(1))
        out["heal"] = n * 10 if m.group(2) else n             # counters -> HP
    elif _RX_ABL_HEAL_ANY.search(t) and once:
        out["heal"] = 10
    if _RX_TAG_EACHDRAW.search(t) or _RX_TAG_OPPDECK.search(t):
        out["mill"] = 1
    if (_RX_ABL_SWITCH_RC.search(t) or _RX_ABL_SWITCH_1.search(t)
            or _RX_ABL_SWITCH_ACT.search(t) or _RX_ABL_SWITCH_SELF.search(t)):
        out["switch"] = 1
    return out


def _selftest():
    import math
    for s in ("", "n/a", "This attack does 60 more damage.",
              "This attack does 30 damage for each heads.",
              "This Pokémon also does 20 damage to itself."):
        v = effect_vector(s)
        assert len(v) == MODIFIER_DIM
        assert all(math.isfinite(x) and 0.0 <= x <= 1.0 for x in v)
    assert effect_vector("n/a") == zero_vector()
    assert len(modifier_schema()) == MODIFIER_DIM

    # bounded vs unbounded coin flip EV — must differ for a non-2-coin bounded count
    bounded = "Flip 4 coins. This attack does 20 damage for each heads."
    unbounded = "Flip a coin until you get tails. This attack does 50 damage for each heads."
    single = "Flip a coin. This attack does 30 damage for each heads."
    assert expected_heads(bounded) == 2.0         # 4 * 0.5
    assert expected_heads(unbounded) == 1.0       # geometric EV
    assert expected_heads(bounded) != expected_heads(unbounded)
    assert expected_heads(single) == 0.5
    assert expected_heads("no coins here") == 1.0

    p_bounded = parse_effect(bounded)
    assert p_bounded["scale_var"] == "heads" and p_bounded["scale_amount"] == 20

    # coin_flip gated bonus
    gated = parse_effect("Flip a coin. If heads, this attack does 50 more damage.")
    assert gated["bonus_flat"] == 50 and "coin_flip" in gated["conditions"]
    ungated = parse_effect("This attack does 50 more damage.")
    assert ungated["bonus_flat"] == 50 and "coin_flip" not in ungated["conditions"]

    # --- spec-03 attack tags (real card texts) ---
    # Budew 235 / Frillish 597 — item lock
    tg = attack_tags("During your opponent’s next turn, they can’t play any Item cards from their hand.")
    assert tg["item_lock"] == 1, tg
    # Shaymin 45 — bench snipe
    tg = attack_tags("This attack does 60 damage to 1 of your opponent’s Benched Pokémon ex or Benched Pokémon V.")
    assert tg["snipe"] == 60, tg
    # Cubchoo 506 — attack lock
    tg = attack_tags("During your opponent’s next turn, the Defending Pokémon can’t use attacks.")
    assert tg["cubchoo"] == 1, tg
    # Chandelure 495 — discard all Energy realizes to the attack's own cost
    tg = attack_tags("Discard all Energy from this Pokémon.", total_cost=2)
    assert tg["discard_energy"] == 2, tg
    # Lampent 494 — "an Energy" word-number
    tg = attack_tags("Discard an Energy from this Pokémon.")
    assert tg["discard_energy"] == 1, tg
    # Tyranitar 290 attack — opponent's-deck mill
    tg = attack_tags("Discard the top 2 cards of your opponent’s deck.")
    assert tg["deckout"] == 1, tg
    # Comfey 164 — each-player-draws mill + our draw
    tg = attack_tags("Each player draws 3 cards.")
    assert tg["deckout"] == 1 and tg["draws_cards"] == 3, tg
    # coin flip -> probabilistic
    tg = attack_tags("Flip a coin. If heads, this attack does 20 more damage.")
    assert tg["probabilistic"] == 1, tg
    # untagged vanilla
    assert attack_tags("n/a") == {k: 0 for k in ATTACK_TAG_FIELDS}
    # round-1 fixes: multi-coin, third-person flip, numberless top-card, random,
    # "discard up to N Energy", both-sides bench spread
    assert attack_tags("Flip 2 coins. This attack does 20 damage for each heads.")["probabilistic"] == 1
    assert attack_tags("Your opponent flips a coin for each of their Benched Pokémon.")["probabilistic"] == 1
    assert attack_tags("Look at the top card of your deck. You may discard that card.")["probabilistic"] == 1
    assert attack_tags("Discard a random card from your opponent’s hand.")["probabilistic"] == 1
    assert attack_tags("Discard up to 3 Energy cards from your hand. This attack does "
                       "60 damage to 1 of your opponent’s Pokémon for each Energy card "
                       "you discarded in this way.")["discard_energy"] == 3
    spread = attack_tags("This attack also does 20 damage to each Benched Pokémon "
                         "(both yours and your opponent’s).")
    assert spread["snipe"] == 20, spread
    # self-only spread must NOT be snipe
    assert attack_tags("This attack does 10 damage to each of your Benched Pokémon.")["snipe"] == 0
    # round-2 fixes
    # typed "discard all {M} Energy" -> discard_energy = total_cost
    assert attack_tags("Discard all {M} Energy from this Pokémon.", total_cost=3)["discard_energy"] == 3
    # "place N damage counters" verb variant
    assert attack_tags("Place 3 damage counters on your opponent’s Active Pokémon.")["counter_snipe"] == 30
    # direct attach accel
    assert attack_tags("Attach a Basic Energy card from your hand to 1 of your Pokémon.")["energy_accel"] == 1
    # search-then-attach accel
    assert attack_tags("Search your deck for up to 2 Basic Energy cards and attach them "
                       "to 1 of your Pokémon.")["energy_accel"] == 2
    assert attack_tags("Search your deck for a Basic {G} Energy card and attach it to "
                       "this Pokémon.")["energy_accel"] == 1
    # opponent-attaches-energy punish effect must NOT count as our accel
    assert attack_tags("During your opponent’s next turn, whenever they attach an Energy "
                       "card from their hand to the Defending Pokémon, place 8 damage "
                       "counters on that Pokémon.")["energy_accel"] == 0
    # top card of each player's deck -> probabilistic
    assert attack_tags("Discard the top card of each player’s deck. This attack does 140 "
                       "more damage for each Energy card discarded in this way.")["probabilistic"] == 1
    # deckout FP fix: shuffle INTO opponent's deck must NOT set deckout
    assert attack_tags("Devolve each of your opponent’s evolved Pokémon by shuffling the "
                       "highest Stage Evolution card on it into your opponent’s deck.")["deckout"] == 0
    # but genuine mill ("discard … of your opponent's deck") still fires
    assert attack_tags("Discard the top 3 cards of your opponent’s deck.")["deckout"] == 1
    # round-3: look/reveal at opponent's deck is NOT deckout (no discard)
    assert attack_tags("Look at the top 5 cards of your opponent’s deck and put them "
                       "back in any order.")["deckout"] == 0
    assert attack_tags("Reveal the top 10 cards of your opponent’s deck. Shuffle the "
                       "revealed cards into your opponent’s deck.")["deckout"] == 0
    # round-3: attack draw-until
    assert attack_tags("You may draw cards until you have 6 cards in your hand.")["draws_cards"] == 6
    # round-5: our draw still fires; opponent-only draw does NOT; symmetric each-player kept
    assert attack_tags("Discard your hand and draw 6 cards.")["draws_cards"] == 6
    assert ability_tags("Your opponent shuffles their hand … If they put any cards on the "
                        "bottom of their deck in this way, they draw 4 cards.")["draw"] == 0
    assert ability_tags("Once during your turn … Each player draws a card.")["draw"] == 1

    # Plan 05: retreat_lock — opponent lock only, not self-lock or cost increase.
    assert attack_tags("During your opponent's next turn, the Defending Pokémon "
                       "can't retreat.")["retreat_lock"] == 1
    assert attack_tags("Your opponent's Active Pokémon is now Poisoned. During your "
                       "opponent's next turn, that Pokémon can't retreat.")["retreat_lock"] == 1
    assert attack_tags("During your next turn, this Pokémon can't retreat.")["retreat_lock"] == 0
    assert attack_tags("During your opponent's next turn, the Defending Pokémon's "
                       "Retreat Cost is {C} more.")["retreat_lock"] == 0

    # Plan 05: immunity — complete generic shield only. Narrow-source shields,
    # thresholds, and fixed reduction remain review/excluded cases.
    shield = attack_tags("Flip a coin. If heads, during your opponent's next turn, "
                         "prevent all damage from and effects of attacks done to this Pokémon.")
    assert shield["immunity"] == 1 and shield["probabilistic"] == 1, shield
    assert attack_tags("During your opponent's next turn, prevent all damage done to "
                       "this Pokémon by attacks.")["immunity"] == 1
    assert attack_tags("During your opponent's next turn, this Pokémon takes 30 less "
                       "damage from attacks.")["immunity"] == 0
    assert attack_tags("During your opponent's next turn, prevent all damage done to "
                       "this Pokémon by attacks from Basic Pokémon.")["immunity"] == 0
    assert attack_tags("During your opponent's next turn, prevent all damage done to "
                       "this Pokémon by attacks if that damage is 60 or less.")["immunity"] == 0

    # Plan 05: recoil — raw HP. Variable recoil and explicit self-KO are excluded.
    assert attack_tags("This Pokémon also does 30 damage to itself.")["recoil"] == 30
    assert attack_tags("You may have this Pokémon also do 60 damage to itself and make "
                       "your opponent's Active Pokémon Paralyzed.")["recoil"] == 60
    assert attack_tags("This Pokémon also does 10 damage to itself for each damage "
                       "counter on it.")["recoil"] == 0
    assert attack_tags("Knock Out this Pokémon.")["recoil"] == 0

    # --- spec-03 ability tags (real card texts) ---
    # Chandelure 98 Alluring Light — mill + draw 1 ("have each player draw a card")
    ab = ability_tags("Once during your turn, you may have each player draw a card.")
    assert ab["mill"] == 1 and ab["draw"] == 1, ab
    # Hariyama 674 / Hop's Dubwool 310 — gust
    ab = ability_tags("Once during your turn, when you play this Pokémon from your hand to "
                      "evolve 1 of your Pokémon, you may use this Ability. Switch in 1 of "
                      "your opponent’s Benched Pokémon to the Active Spot.")
    assert ab["gust"] == 1, ab
    # keyword layer must NOT set the override-only fields
    assert ab["immunity"] == 0 and ab["barrier"] == 0
    # search
    ab = ability_tags("Once during your turn, you may search your deck for a Basic Pokémon, "
                      "reveal it, and put it into your hand. Then, shuffle your deck.")
    assert ab["search"] == 1, ab
    assert ability_tags("n/a") == {k: 0 for k in ABILITY_TAG_FIELDS}
    # round-1 fixes: "attach up to 2 Basic" accel, "put N more damage counters"
    ab = ability_tags("When you play this Pokémon from your hand to evolve 1 of your "
                      "Pokémon during your turn, you may attach up to 2 Basic {M} "
                      "Energy cards from your discard pile to your {M} Pokémon in any "
                      "way you like.")
    assert ab["energy_active"] == 2 or ab["energy_bench"] == 2, ab
    ab = ability_tags("During Pokémon Checkup, put 3 more damage counters on your "
                      "opponent’s Burned Pokémon.")
    assert ab["damage"] == 30, ab
    # round-4: self-counter cost must NOT set the opponent-damage tag
    assert ability_tags("Once during your turn, you may put 5 damage counters on this "
                        "Pokémon. If you do, during this turn, attacks used by this "
                        "Pokémon do 120 more damage.")["damage"] == 0
    # counters on the opponent still fire, whether opponent is named before or after
    assert ability_tags("You may put 13 damage counters on 1 of your opponent’s "
                        "Pokémon.")["damage"] == 130
    assert ability_tags("Choose 2 of your opponent’s Pokémon and put 2 damage counters "
                        "on each of them.")["damage"] == 20
    # round-2: Special-Energy accel (not just Basic)
    ab = ability_tags("When you play this Pokémon from your hand to evolve 1 of your "
                      "Pokémon during your turn, you may attach up to 2 Spiky Energy "
                      "cards from your discard pile to this Pokémon.")
    assert ab["energy_active"] == 2 or ab["energy_bench"] == 2, ab
    # existing Basic-with-type accel still works
    ab = ability_tags("Once during your turn, you may attach up to 2 Basic {R} Energy "
                      "cards from your hand to 1 of your Benched Pokémon.")
    assert ab["energy_bench"] == 2, ab
    # round-3: ability accel outside the rigid anchor (Oricorio phrasing)
    ab = ability_tags("As often as you like during your turn, if you have any {R} Mega "
                      "Evolution Pokémon {ex} in play, you may use this Ability. Attach a "
                      "Basic {R} Energy card from your hand to 1 of your Benched {R} "
                      "Pokémon.")
    assert ab["energy_bench"] == 1, ab
    # round-3: free-switch ability
    assert ability_tags("Once during your turn, if this Pokémon is on your Bench, you "
                        "may switch it with your Active Pokémon.")["switch"] == 1
    # energy "move" ability must NOT count as accel
    assert ability_tags("Once during your turn, you may move a Basic Energy from 1 of "
                        "your Pokémon to another of your Pokémon.")["energy_active"] == 0

    print("effect_features self-test PASSED")


if __name__ == "__main__":
    _selftest()
