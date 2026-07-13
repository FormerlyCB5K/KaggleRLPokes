"""
stat_bakes.py — Tool / ability / stadium static effects folded into KO math.

Spec: specs/completed/06-effect-baking.md (representation) +
specs/completed/07-effect-baking-audit.md (audit).

Hand-authored `BAKES` table maps a card_id (Tool, ability-holder Pokemon, or Stadium) to
a list of stat Modifiers. features.py routes its derived combat features through the
`effective_*` helpers here so the "# hits to KO" features account for these effects
exactly. No vector-shape change.

Modifier = {
    "stat":      hp_delta | damage_taken_delta | damage_dealt_delta |
                 weak_fire | weak_fighting | resist_fire | resist_fighting |
                 retreat_delta | retreat_set | attack_cost_delta,
    "value":     number (delta / absolute / 1|0 flag),
    "scope":     "self" (default) | "your_side" | "all",   # who the mod reaches
    "condition": predicate key or None,                    # evaluated live per candidate
}

Double-count rule (Phase-0 probe, old/audits/effect-baking/effect-bakes-phase0.md): HP **Tools** are already
in observed maxHp/hp, so the table NEVER contains a Tool hp_delta — only ability/stadium
HP auras get hp_delta. Retreat / weakness / resistance come from static card_data (or have
no live field), so baking them cannot double-count.

    python stat_bakes.py        # self-test
"""
from __future__ import annotations

import card_data as cd

RESIST = 30.0
FIRE = cd.FIRE_SYM          # "{R}"
FIGHTING = cd.FIGHTING_SYM  # "{F}"
_METAL = "{M}"


def _st(card_id):
    return cd.CardRegistry.load().get(card_id)


_NAMES: dict[int, str] = {}
_CATEGORIES: dict[int, str] = {}
_TERA_IDS: set[int] = set()


def _name(card_id) -> str:
    if not _NAMES:
        import csv
        with open(cd._default_csv(), encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                _NAMES.setdefault(int(row["Card ID"]), row.get("Card Name", ""))
    return _NAMES.get(int(card_id), "")


def _category(card_id) -> str:
    if not _CATEGORIES:
        import csv
        with open(cd._default_csv(), encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                _CATEGORIES.setdefault(int(row["Card ID"]), row.get("Category", ""))
    return _CATEGORIES.get(int(card_id), "")


def _is_tera(poke) -> bool:
    if not _TERA_IDS:
        import csv
        with open(cd._default_csv(), encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("Move Name") or "").strip() == "[Tera]":
                    _TERA_IDS.add(int(row["Card ID"]))
    return int(poke.id) in _TERA_IDS


def _name_has(poke, needle) -> bool:
    return needle.lower() in _name(poke.id).lower()


# ── condition predicates ────────────────────────────────────────────────────────
# Each predicate(holder, attacker, board) -> bool. `holder` is the Pokemon the mod is
# being applied to (usually the defender); `attacker` is the Pokemon hitting it (may be
# None when the mod isn't in a damage context). Both are live `Pokemon` objects.

def _attacker_type(attacker):
    return _st(attacker.id).type_sym if attacker is not None else None


def _is_basic(poke):    return _st(poke.id).stage == "Basic Pokémon"
def _is_stage2(poke):   return _st(poke.id).stage == "Stage 2 Pokémon"
def _has_ability(poke): return bool(_st(poke.id).abilities)
def _is_ex(poke):       s = _st(poke.id); return s.is_ex or s.is_mega_ex
def _energy_types(poke): return {_st(e.id).type_sym for e in (poke.energyCards or [])}
def _has_energy_type(poke, sym): return sym in _energy_types(poke)
def _is_evolution(poke): return _st(poke.id).stage in ("Stage 1 Pokémon", "Stage 2 Pokémon")


def _source_has_other_bouffalant(source, _attacker, board):
    if source is None:
        return False
    side = board.our_pokes if source in board.our_pokes else board.opp_pokes
    return any(p.id == 175 and p.serial != source.serial for p in side)


_PREDICATES = {
    None:                    lambda h, a, b: True,
    "is_active":             lambda h, a, b: b.is_active(h),
    "full_hp":               lambda h, a, b: (h.hp or 0) >= (h.maxHp or 0) > 0,
    "has_tool":              lambda h, a, b: bool(h.tools),
    "has_no_energy":         lambda h, a, b: not (h.energyCards or []),
    "has_fighting_energy":   lambda h, a, b: _has_energy_type(h, FIGHTING),
    "has_metal_energy":      lambda h, a, b: _has_energy_type(h, _METAL),
    "has_water_energy":      lambda h, a, b: _has_energy_type(h, "{W}"),
    "has_dark_energy":       lambda h, a, b: _has_energy_type(h, "{D}"),
    "has_special_energy":    lambda h, a, b: any(e.id > 10 for e in (h.energyCards or [])),
    "is_damaged":            lambda h, a, b: (h.hp or 0) < (h.maxHp or 0),
    "hp_30_or_less":         lambda h, a, b: 0 < (h.hp or 0) <= 30,
    "source_has_other_bouffalant": _source_has_other_bouffalant,
    # attacker-typed conditions (damage-reduction "from {X} Pokémon")
    "attacker_is_fire":      lambda h, a, b: _attacker_type(a) == FIRE,
    "attacker_is_fighting":  lambda h, a, b: _attacker_type(a) == FIGHTING,
    "attacker_is_psychic":   lambda h, a, b: _attacker_type(a) == "{P}",
    "attacker_is_dragon":    lambda h, a, b: _attacker_type(a) in ("{N}", "竜"),
    "attacker_is_grass_fire_water_lightning": lambda h, a, b: (
        _attacker_type(a) in ("{G}", FIRE, "{W}", "{L}")),
    "attacker_has_ability":  lambda h, a, b: a is not None and _has_ability(a),
    "attacker_is_ex":        lambda h, a, b: a is not None and _is_ex(a),
    # holder filters (stadium/aura type / stage / trainer-name auras)
    "holder_is_metal":       lambda h, a, b: _st(h.id).type_sym == _METAL,
    "holder_is_fire":        lambda h, a, b: _st(h.id).type_sym == FIRE,
    "holder_is_fighting":    lambda h, a, b: _st(h.id).type_sym == FIGHTING,
    "holder_is_basic":       lambda h, a, b: _is_basic(h),
    "holder_is_stage2":      lambda h, a, b: _is_stage2(h),
    "holder_is_evolution":   lambda h, a, b: _is_evolution(h),
    "holder_is_colorless":   lambda h, a, b: _st(h.id).type_sym == "{C}",
    "holder_is_dragon":      lambda h, a, b: _st(h.id).type_sym in ("{N}", "竜"),
    "holder_is_grass_or_fire": lambda h, a, b: _st(h.id).type_sym in ("{G}", FIRE),
    "holder_is_fire_evolution": lambda h, a, b: _st(h.id).type_sym == FIRE and _is_evolution(h),
    "source_is_benched":     lambda h, a, b: not b.is_active(h),
    "source_is_active":      lambda h, a, b: b.is_active(h),
    "holder_is_ns":          lambda h, a, b: _name_has(h, "N’s ") or _name_has(h, "N's "),
    "holder_is_stevens":     lambda h, a, b: _name_has(h, "Steven"),
    "holder_is_hops":        lambda h, a, b: _name_has(h, "Hop"),
    "holder_is_cynthias":    lambda h, a, b: _name_has(h, "Cynthia"),
    "holder_is_future_not_iron_crown": lambda h, a, b: (
        _category(h.id).lower() == "future" and h.id != 80),
    "holder_is_tera":        lambda h, a, b: _is_tera(h),
    "more_prizes_remaining": lambda h, a, b: (
        b.prizes_remaining(h in b.our_pokes) > b.prizes_remaining(h not in b.our_pokes)),
    # defender-is-ex, for damage_dealt bonuses gated on the target
    "defender_is_ex":        lambda h, a, b: a is not None and _is_ex(a),
    "defender_has_ability":  lambda h, a, b: a is not None and _has_ability(a),
    "defender_is_evolution": lambda h, a, b: a is not None and _is_evolution(a),
    "holder_plain_defender_ex": lambda h, a, b: (
        not _is_ex(h) and a is not None and _is_ex(a)),
    "holder_pikachu_ex_defender_ex": lambda h, a, b: (
        _name_has(h, "Pikachu ex") and a is not None and _is_ex(a)),
    "holder_dragon_attacker_gfwl": lambda h, a, b: (
        _st(h.id).type_sym in ("{N}", "竜") and
        _attacker_type(a) in ("{G}", FIRE, "{W}", "{L}")),
    "side_has_grass_mega": lambda h, a, b: any(
        _st(p.id).type_sym == "{G}" and _st(p.id).is_mega_ex
        for p in (b.our_pokes if h in b.our_pokes else b.opp_pokes)),
}


def _cond(key):
    return _PREDICATES[key]


# ── BAKES table (see specs/completed/07 for the full-audit worklist) ─────────────
# Values are RAW. hp_delta applies to both hp_max and hp_curr. damage_taken_delta is
# added to incoming damage (negative = reduction). damage_dealt_delta is added to the
# holder's own attack damage. retreat_set overrides retreat cost absolutely.

BAKES: dict[int, dict] = {
    # ---- HP auras (abilities/stadiums only; NEVER tools) ----
    262:  {"kind": "ability", "mods": [                       # Ludicolo — Vibrant Dance
        {"stat": "hp_delta", "value": 40, "scope": "your_side"}]},
    1251: {"kind": "stadium", "mods": [                       # Lively Stadium
        {"stat": "hp_delta", "value": 30, "scope": "all", "condition": "holder_is_basic"}]},
    1252: {"kind": "stadium", "mods": [                       # Gravity Mountain
        {"stat": "hp_delta", "value": -30, "scope": "all", "condition": "holder_is_stage2"}]},
    530:  {"kind": "ability", "mods": [                       # Conkeldurr: +40 per {F}
        {"stat": "hp_per_fighting_energy", "value": 40}]},
    116:  {"kind": "ability", "mods": [                       # Okidogi with Darkness Energy
        {"stat": "hp_delta", "value": 100, "condition": "has_dark_energy"},
        {"stat": "damage_dealt_delta", "value": 100, "condition": "has_dark_energy"}]},
    44:   {"kind": "ability", "mods": [                       # Bloodmoon Ursaluna ex
        {"stat": "attack_cost_per_prize_taken", "value": -1,
         "attack_name": "Blood Moon"}]},
    79:   {"kind": "ability", "mods": [                       # Incineroar ex
        {"stat": "attack_cost_per_opponent_bench", "value": -1}]},
    1054: {"kind": "ability", "mods": [                       # Tyrantrum with Special Energy
        {"stat": "hp_delta", "value": 150, "condition": "has_special_energy"}]},

    # ---- flat damage reduction (self abilities) ----
    383:  {"kind": "ability", "mods": [{"stat": "damage_taken_delta", "value": -30}]},  # Mudsdale
    631:  {"kind": "ability", "mods": [{"stat": "damage_taken_delta", "value": -30}]},  # Bouffalant ex
    766:  {"kind": "ability", "mods": [{"stat": "damage_taken_delta", "value": -30}]},  # Mega Diancie ex

    # ---- damage reduction: conditional / aura ----
    799:  {"kind": "ability", "mods": [                       # Dewgong — Thick Fat
        {"stat": "damage_taken_delta", "value": -30, "condition": "attacker_is_fire"}]},
    637:  {"kind": "ability", "mods": [                       # Steven's Carbink — Stone Palace
        {"stat": "damage_taken_delta", "value": -30, "scope": "your_side",
         "condition": "holder_is_stevens", "source_condition": "source_is_benched",
         "stack_key": "stone_palace"}]},                      # text says effect does not stack
    175:  {"kind": "ability", "mods": [                       # Bouffalant — Curly Wall
        {"stat": "damage_taken_delta", "value": -60, "scope": "your_side",
         "condition": "holder_is_colorless", "source_condition": "source_has_other_bouffalant",
         "stack_key": "curly_wall"}]},
    623:  {"kind": "ability", "mods": [                       # Klinklang — Metal Shield
        {"stat": "damage_taken_delta", "value": -20, "scope": "your_side",
         "condition": "has_metal_energy"}]},
    1033: {"kind": "ability", "mods": [                       # Aurorus — Tundra Wall
        {"stat": "damage_taken_delta", "value": -50, "scope": "your_side",
         "condition": "has_water_energy", "stack_key": "tundra_wall"}]},

    # ---- damage reduction: tools ----
    1177: {"kind": "tool", "mods": [                          # Sacred Charm
        {"stat": "damage_taken_delta", "value": -30, "condition": "attacker_has_ability"}]},
    1164: {"kind": "tool", "mods": [                          # Payapa Berry
        {"stat": "damage_taken_delta", "value": -60, "condition": "attacker_is_psychic"}]},
    1170: {"kind": "tool", "mods": [                          # Haban Berry
        {"stat": "damage_taken_delta", "value": -60, "condition": "attacker_is_dragon"}]},
    1179: {"kind": "tool", "mods": [                          # Thick Scale
        {"stat": "damage_taken_delta", "value": -50,
         "condition": "holder_dragon_attacker_gfwl"}]},

    # ---- damage reduction: stadiums ----
    1244: {"kind": "stadium", "mods": [                       # Full Metal Lab — {M} both sides
        {"stat": "damage_taken_delta", "value": -30, "scope": "all", "condition": "holder_is_metal"}]},
    1258: {"kind": "stadium", "mods": [                       # Granite Cave — Steven's both sides
        {"stat": "damage_taken_delta", "value": -30, "scope": "all", "condition": "holder_is_stevens"}]},

    # ---- outgoing damage bonus ----
    685:  {"kind": "ability", "mods": [                       # Garganacl — aura: your {F} do +30
        {"stat": "damage_dealt_delta", "value": 30, "scope": "your_side",
         "condition": "holder_is_fighting"}]},
    80:   {"kind": "ability", "mods": [                       # Iron Crown ex — Future +20
        {"stat": "damage_dealt_delta", "value": 20, "scope": "your_side",
         "condition": "holder_is_future_not_iron_crown"}]},
    126:  {"kind": "ability", "mods": [                       # Galvantula +50 vs Ability
        {"stat": "damage_dealt_delta", "value": 50, "condition": "defender_has_ability"}]},
    155:  {"kind": "ability", "mods": [                       # Carracosta +30 vs Evolution
        {"stat": "damage_dealt_delta", "value": 30, "scope": "your_side",
         "condition": "defender_is_evolution"}]},
    202:  {"kind": "ability", "mods": [                       # Victini: Evolution Fire +10
        {"stat": "damage_dealt_delta", "value": 10, "scope": "your_side",
         "condition": "holder_is_fire_evolution"}]},
    304:  {"kind": "ability", "mods": [                       # Hop's Snorlax +30, nonstacking
        {"stat": "damage_dealt_delta", "value": 30, "scope": "your_side",
         "condition": "holder_is_hops", "stack_key": "extra_helpings"}]},
    322:  {"kind": "ability", "mods": [                       # Lilligant: Grass/Fire +20
        {"stat": "damage_dealt_delta", "value": 20, "scope": "your_side",
         "condition": "holder_is_grass_or_fire"}]},
    342:  {"kind": "ability", "mods": [                       # Cynthia's Roserade +30
        {"stat": "damage_dealt_delta", "value": 30, "scope": "your_side",
         "condition": "holder_is_cynthias"}]},
    439:  {"kind": "ability", "mods": [                       # Annihilape +120 when damaged
        {"stat": "damage_dealt_delta", "value": 120, "condition": "is_damaged"}]},
    49:   {"kind": "ability", "mods": [                       # Feraligatr: user chose always-on
        {"stat": "damage_dealt_delta", "value": 120}]},
    901:  {"kind": "ability", "mods": [                       # Kingambit: +30 / Prize taken
        {"stat": "damage_per_prize_taken", "value": 30}]},
    829:  {"kind": "ability", "mods": [                       # Seviper +120 with Grass Mega
        {"stat": "damage_dealt_delta", "value": 120, "condition": "side_has_grass_mega"}]},
    716:  {"kind": "ability", "mods": [                       # Pyroar active: foe does -30
        {"stat": "damage_dealt_delta", "value": -30, "scope": "opponent_side",
         "source_condition": "source_is_active"}]},
    1150: {"kind": "ability", "mods": [                       # Antique Jaw Fossil
        {"stat": "damage_dealt_delta", "value": -30, "scope": "opponent_side",
         "source_condition": "source_is_active"}]},
    1255: {"kind": "stadium", "mods": [                       # Postwick — Hop's do +30
        {"stat": "damage_dealt_delta", "value": 30, "scope": "all", "condition": "holder_is_hops"}]},
    1158: {"kind": "tool", "mods": [                          # Maximum Belt — +50 vs ex
        {"stat": "damage_dealt_delta", "value": 50, "condition": "defender_is_ex"}]},
    1171: {"kind": "tool", "mods": [                          # Hop's Choice Band — +30, cost -1
        {"stat": "damage_dealt_delta", "value": 30, "condition": "holder_is_hops"},
        {"stat": "attack_cost_delta", "value": -1,
         "condition": "holder_is_hops"}]},
    1175: {"kind": "tool", "mods": [                          # Brave Bangle +30 non-rulebox vs ex
        {"stat": "damage_dealt_delta", "value": 30,
         "condition": "holder_plain_defender_ex"}]},
    1178: {"kind": "tool", "mods": [                          # Light Ball: Pikachu ex +50 vs ex
        {"stat": "damage_dealt_delta", "value": 50,
         "condition": "holder_pikachu_ex_defender_ex"}]},
    1162: {"kind": "tool", "mods": [                          # Binding Mochi: user chose always-on
        {"stat": "damage_dealt_delta", "value": 40}]},

    # ---- retreat ----
    1174: {"kind": "tool", "mods": [{"stat": "retreat_delta", "value": -2}]},           # Air Balloon
    1157: {"kind": "tool", "mods": [                          # Rescue Board
        {"stat": "retreat_delta", "value": -1},
        {"stat": "retreat_set", "value": 0, "condition": "hp_30_or_less"}]},
    1166: {"kind": "tool", "mods": [                          # Gravity Gemstone
        {"stat": "retreat_delta", "value": 1, "scope": "all",
         "condition": "is_active", "source_condition": "source_is_active"}]},
    170:  {"kind": "ability", "mods": [                       # Archaludon
        {"stat": "retreat_set", "value": 0, "scope": "your_side",
         "condition": "has_metal_energy"}]},
    184:  {"kind": "ability", "mods": [                       # Latias ex
        {"stat": "retreat_set", "value": 0, "scope": "your_side",
         "condition": "holder_is_basic"}]},
    356:  {"kind": "ability", "mods": [                       # Ethan's Magcargo
        {"stat": "retreat_set", "value": 0, "condition": "has_no_energy"}]},
    788:  {"kind": "ability", "mods": [                       # Charmander
        {"stat": "retreat_set", "value": 0, "condition": "has_no_energy"}]},
    1253: {"kind": "stadium", "mods": [                       # N's Castle — N's Pokemon, no retreat
        {"stat": "retreat_set", "value": 0, "scope": "all", "condition": "holder_is_ns"}]},

    # ---- suppression-only stadiums (handled by Board; empty modifier lists) ----
    1246: {"kind": "stadium", "mods": []},                    # Jamming Tower: Tools off
    1256: {"kind": "stadium", "mods": []},                    # TR Watchtower: {C} Abilities off
    1266: {"kind": "stadium", "mods": [                       # Nighttime Mine; opponent vector only
        {"stat": "attack_cost_delta", "value": 1, "scope": "all",
         "condition": "holder_is_tera"}]},
    1099: {"kind": "ability", "mods": [                       # Antique Root Fossil active
        {"stat": "attack_cost_delta", "value": 1, "scope": "opponent_side",
         "condition": "holder_is_basic", "source_condition": "source_is_active"}]},

    # ---- attack cost (wired to opponent attack-cost features only) ----
    1165: {"kind": "tool", "mods": [                          # Sparkling Crystal
        {"stat": "attack_cost_delta", "value": -1, "condition": "holder_is_tera"}]},
    1168: {"kind": "tool", "mods": [                          # Counter Gain
        {"stat": "attack_cost_delta", "value": -1,
         "condition": "more_prizes_remaining"}]},
}

# ── board context ────────────────────────────────────────────────────────────────

class Board:
    """Lightweight per-observation context passed to the effective_* helpers."""

    __slots__ = ("our_pokes", "opp_pokes", "stadium_id", "our_prizes", "opp_prizes",
                 "_active_serials")

    def __init__(self, our_pokes, opp_pokes, stadium_id, our_prizes=6, opp_prizes=6):
        self.our_pokes = [p for p in our_pokes if p is not None]
        self.opp_pokes = [p for p in opp_pokes if p is not None]
        self.stadium_id = stadium_id
        self.our_prizes = int(our_prizes)
        self.opp_prizes = int(opp_prizes)
        # actives are position 0 of each side's active list — caller marks them
        self._active_serials = set()

    def mark_active(self, poke):
        if poke is not None:
            self._active_serials.add(poke.serial)

    def is_active(self, poke):
        return poke is not None and poke.serial in self._active_serials

    def side_pokes(self, is_ours: bool):
        return self.our_pokes if is_ours else self.opp_pokes

    def prizes_remaining(self, is_ours: bool):
        return self.our_prizes if is_ours else self.opp_prizes

    def tools_enabled(self):
        """Jamming Tower disables every attached Tool on both sides."""
        return self.stadium_id != 1246

    def ability_enabled(self, poke):
        """Team Rocket's Watchtower disables Abilities on Colorless Pokemon."""
        return not (self.stadium_id == 1256 and _st(poke.id).type_sym == "{C}")


def _entry_mods(card_id, kind):
    e = BAKES.get(int(card_id)) if card_id is not None else None
    return e["mods"] if (e and e["kind"] == kind) else []


def _applies(mod, holder, attacker, board):
    return _cond(mod.get("condition"))(holder, attacker, board)


def _gather(defender, defender_is_ours, attacker, board, stat_keys):
    """All active mods with stat in `stat_keys` that reach `defender`."""
    out = []
    same = board.side_pokes(defender_is_ours)
    other = board.side_pokes(not defender_is_ours)
    seen_stack_keys = set()

    def take(mods, holder, source=None):
        for m in mods:
            source_ok = (not m.get("source_condition") or
                         _cond(m["source_condition"])(source, attacker, board))
            stack_key = m.get("stack_key")
            if (m["stat"] in stat_keys and source_ok and
                    _applies(m, holder, attacker, board) and
                    (not stack_key or stack_key not in seen_stack_keys)):
                out.append(m)
                if stack_key:
                    seen_stack_keys.add(stack_key)

    # defender's own tools + own ability (scope self)
    if board.tools_enabled():
        for tool in (defender.tools or []):
            take([m for m in _entry_mods(tool.id, "tool") if m.get("scope", "self") == "self"],
                 defender, defender)
    if board.ability_enabled(defender):
        take([m for m in _entry_mods(defender.id, "ability") if m.get("scope", "self") == "self"],
             defender, defender)
    # team-aura abilities on the defender's side (scope your_side / all)
    for src in same:
        if board.ability_enabled(src):
            take([m for m in _entry_mods(src.id, "ability")
                  if m.get("scope", "self") in ("your_side", "all")], defender, src)
    # hostile auras originating on the other side
    for src in other:
        if board.ability_enabled(src):
            take([m for m in _entry_mods(src.id, "ability")
                  if m.get("scope", "self") == "opponent_side"], defender, src)
    # Tool auras are rare but real (Gravity Gemstone affects both Active Pokemon).
    if board.tools_enabled():
        for src in board.our_pokes + board.opp_pokes:
            for tool in (src.tools or []):
                take([m for m in _entry_mods(tool.id, "tool")
                      if m.get("scope", "self") in ("your_side", "opponent_side", "all")],
                     defender, src)
    # stadium mods (shared) with holder = defender
    take([m for m in _entry_mods(board.stadium_id, "stadium")
          if m.get("scope", "self") in ("your_side", "all", "opponent_side")], defender)
    return out


# ── effective stats ──────────────────────────────────────────────────────────────

def hp_aura(defender, defender_is_ours, board):
    """Summed ability/stadium HP-aura delta reaching `defender` (Tools excluded — they
    are already in observed maxHp per the Phase-0 probe). May be negative."""
    mods = _gather(defender, defender_is_ours, None, board,
                   {"hp_delta", "hp_per_fighting_energy"})
    total = 0
    for m in mods:
        if m["stat"] == "hp_per_fighting_energy":
            total += m["value"] * sum(
                1 for e in (defender.energyCards or []) if _st(e.id).type_sym == FIGHTING)
        else:
            total += m["value"]
    return total


def damage_taken_reduction(defender, defender_is_ours, attacker, board):
    """Summed damage_taken_delta reaching `defender` from `attacker` (negative = less
    damage taken)."""
    return sum(m["value"] for m in _gather(defender, defender_is_ours, attacker, board,
                                           {"damage_taken_delta"}))


def effective_hp(defender, defender_is_ours, board):
    """(effective_max_hp, effective_curr_hp) with ability/stadium HP auras applied to
    BOTH. Observed HP already includes Tool HP (Phase-0 probe), so tools are not baked."""
    delta = hp_aura(defender, defender_is_ours, board)
    eff_max = max(1, (defender.maxHp or 0) + delta)
    eff_curr = min(max(0, (defender.hp or 0) + delta), eff_max)
    return eff_max, eff_curr


def effective_retreat(defender, defender_is_ours, board, base_retreat):
    mods = _gather(defender, defender_is_ours, None, board,
                   {"retreat_delta", "retreat_set"})
    sets = [m["value"] for m in mods if m["stat"] == "retreat_set"]
    # Absolute "has no Retreat Cost" effects win over additive modifiers regardless
    # of source iteration order. Multiple absolute setters resolve conservatively low.
    r = min(sets) if sets else base_retreat + sum(
        m["value"] for m in mods if m["stat"] == "retreat_delta")
    return max(0, r)


def effective_weak_resist(defender, defender_is_ours, board):
    """(weak_fire, weak_fighting, resist_fire, resist_fighting) after baked overrides,
    starting from the card's printed flags."""
    st = _st(defender.id)
    flags = {"weak_fire": st.weak_fire, "weak_fighting": st.weak_fighting,
             "resist_fire": st.resist_fire, "resist_fighting": st.resist_fighting}
    for m in _gather(defender, defender_is_ours, None, board,
                     set(flags)):
        flags[m["stat"]] = bool(m["value"])
    return flags["weak_fire"], flags["weak_fighting"], flags["resist_fire"], flags["resist_fighting"]


def damage_dealt_bonus(attacker, attacker_is_ours, defender, board):
    """Sum of damage_dealt_delta mods active on `attacker` (some gated on the defender)."""
    if attacker is None:
        return 0
    # attacker's own tools + own ability + its side auras; conditions see defender as `a`
    total = 0
    for m in _gather(attacker, attacker_is_ours, defender, board,
                     {"damage_dealt_delta", "damage_per_prize_taken"}):
        if m["stat"] == "damage_per_prize_taken":
            taken = 6 - board.prizes_remaining(not attacker_is_ours)
            total += m["value"] * max(0, taken)
        else:
            total += m["value"]
    return total


def effective_attack_costs(poke, poke_is_ours, board):
    """Live total Energy cost for each printed attack, preserving damage capability.

    This only rewrites the existing opponent attack-cost features. It deliberately does
    not gate damage on attached Energy and is not consumed by our-side vectors.
    """
    attacks = _st(poke.id).attacks
    mods = _gather(poke, poke_is_ours, None, board,
                   {"attack_cost_delta", "attack_cost_per_prize_taken",
                    "attack_cost_per_opponent_bench"})
    out = []
    for attack in attacks:
        delta = 0
        for m in mods:
            if m.get("attack_name") and m["attack_name"] != attack.name:
                continue
            if m["stat"] == "attack_cost_per_prize_taken":
                delta += m["value"] * max(
                    0, 6 - board.prizes_remaining(not poke_is_ours))
            elif m["stat"] == "attack_cost_per_opponent_bench":
                opposing = board.opp_pokes if poke_is_ours else board.our_pokes
                delta += m["value"] * sum(not board.is_active(p) for p in opposing)
            else:
                delta += m["value"]
        out.append(max(0, attack.total_cost + delta))
    return out


def effective_damage(base_dmg, attacker_type, attacker, attacker_is_ours,
                     defender, defender_is_ours, board):
    """Effective HP damage `attacker` deals to `defender` on this board:
    base + damage_dealt bonuses, ×2 Weakness / −30 Resistance for the attacker's type
    (printed flags + baked overrides), then − defender damage-reduction."""
    d = float(base_dmg) + damage_dealt_bonus(attacker, attacker_is_ours, defender, board)
    wf, wfi, rf, rfi = effective_weak_resist(defender, defender_is_ours, board)
    if attacker_type == FIRE:
        if wf:  d *= 2.0
        if rf:  d -= RESIST
    elif attacker_type == FIGHTING:
        if wfi: d *= 2.0
        if rfi: d -= RESIST
    d += sum(m["value"] for m in _gather(defender, defender_is_ours, attacker, board,
                                         {"damage_taken_delta"}))
    return max(0, int(d))


# ── self-test ────────────────────────────────────────────────────────────────────
def _selftest():
    from types import SimpleNamespace as NS

    def poke(cid, hp=None, maxhp=None, tools=(), energy=(), serial=None):
        st = _st(cid)
        mx = maxhp if maxhp is not None else (st.max_hp or 100)
        return NS(id=cid, serial=serial if serial is not None else cid * 1000 + (hp or mx),
                  hp=hp if hp is not None else mx, maxHp=mx,
                  tools=[NS(id=t) for t in tools], energyCards=[NS(id=e) for e in energy])

    # sanity: table stats are valid
    valid = {"hp_delta", "hp_per_fighting_energy", "damage_taken_delta", "damage_dealt_delta",
             "damage_per_prize_taken", "attack_cost_per_prize_taken",
             "attack_cost_per_opponent_bench", "weak_fire",
             "weak_fighting", "resist_fire", "resist_fighting", "retreat_delta",
             "retreat_set", "attack_cost_delta"}
    for cid, e in BAKES.items():
        assert e["kind"] in ("tool", "ability", "stadium"), (cid, e)
        for m in e["mods"]:
            assert m["stat"] in valid, (cid, m)
            assert _cond(m.get("condition")) is not None, (cid, m)

    # Ludicolo +40 HP aura to your side
    ludi = poke(262)
    other = poke(383, hp=150, maxhp=150)        # Mudsdale on the same side
    board = Board([ludi, other], [], stadium_id=None)
    em, ec = effective_hp(other, True, board)
    assert em == 190 and ec == 190, (em, ec)    # 150 + 40
    # not on the opponent side
    board2 = Board([ludi], [other], stadium_id=None)
    em2, _ = effective_hp(other, False, board2)
    assert em2 == 150, em2

    # Lively Stadium +30 to Basics only (use a plain Stage-2 with no bake of its own)
    basic = poke(796)                            # Charcadet (Basic, 70 HP)
    st2 = poke(98)                               # Chandelure (Stage 2, no bake)
    b = Board([basic, st2], [], stadium_id=1251)
    assert effective_hp(basic, True, b)[0] == 100    # 70 + 30
    assert effective_hp(st2, True, b)[0] == _st(98).max_hp   # Stage 2, no +30

    # Gravity Mountain -30 to Stage 2
    b = Board([st2], [], stadium_id=1252)
    assert effective_hp(st2, True, b)[0] == _st(98).max_hp - 30

    # Mudsdale -30 damage reduction (self)
    muds = poke(383)
    b = Board([], [muds], stadium_id=None)
    # a 100-damage Fire attacker vs Mudsdale (Mudsdale is {F}, weak to {G}, not fire)
    d = effective_damage(100, FIRE, poke(320), True, muds, False, b)
    assert d == 70, d                            # 100 - 30

    # Full Metal Lab -30 to Metal Pokemon (both sides)
    metal = poke(766)                            # Mega Diancie ex is {P}? use a metal card
    # find a metal-typed card for the test
    reg = cd.CardRegistry.load()
    metal_id = next(cid for cid, s in reg.stats.items() if s.type_sym == _METAL and s.max_hp)
    m = poke(metal_id)
    b = Board([], [m], stadium_id=1244)
    base = effective_damage(100, None, poke(320), True, m, False, b)
    assert base == 100 - 30, base                # metal + stadium reduction (no weakness term)

    # weakness ×2 applied: a fire-weak defender takes double from a Fire attacker
    fire_weak = next(cid for cid, s in reg.stats.items() if s.weak_fire and s.max_hp)
    fw = poke(fire_weak)
    b = Board([], [fw], stadium_id=None)
    assert effective_damage(60, FIRE, poke(320), True, fw, False, b) == 120

    # Maximum Belt +50 vs ex
    belt_holder = NS(id=999999, serial=1, hp=100, maxHp=100, tools=[NS(id=1158)])
    ex_def = poke(320)                           # Ceruledge ex (has a rule box)
    b = Board([belt_holder], [ex_def], stadium_id=None)
    assert damage_dealt_bonus(belt_holder, True, ex_def, b) == 50
    non_ex = poke(796)                           # Charcadet (not ex)
    assert damage_dealt_bonus(belt_holder, True, non_ex, b) == 0

    # Air Balloon retreat -2
    ab = NS(id=888888, serial=2, hp=100, maxHp=100, tools=[NS(id=1174)])
    b = Board([ab], [], stadium_id=None)
    assert effective_retreat(ab, True, b, 3) == 1
    assert effective_retreat(ab, True, b, 1) == 0    # clip at 0

    # Jamming Tower suppresses Tool bakes.
    jam = Board([ab], [], stadium_id=1246)
    assert effective_retreat(ab, True, jam, 3) == 3

    # Team Rocket's Watchtower suppresses a Colorless source Ability.
    bouf1 = poke(175, serial=175001)
    bouf2 = poke(175, serial=175002)
    target = poke(174)  # Colorless Basic
    live = Board([bouf1, bouf2, target], [], stadium_id=None)
    assert damage_taken_reduction(target, True, poke(320), live) == -60
    watch = Board([bouf1, bouf2, target], [], stadium_id=1256)
    assert damage_taken_reduction(target, True, poke(320), watch) == 0

    # Stone Palace applies only while the source Carbink is Benched and never stacks.
    carb1 = poke(637, serial=637001)
    carb2 = poke(637, serial=637002)
    steven = carb1
    stone = Board([carb1, carb2, steven], [], stadium_id=None)
    stone.mark_active(steven)
    assert damage_taken_reduction(steven, True, poke(320), stone) == -30
    stone.mark_active(carb2)
    assert damage_taken_reduction(steven, True, poke(320), stone) == 0

    # Gravity Gemstone reaches both Active Pokemon; absolute no-retreat still wins.
    gem_holder = poke(796, tools=[1166])
    foe = poke(383)
    gem = Board([gem_holder], [foe], stadium_id=None)
    gem.mark_active(gem_holder); gem.mark_active(foe)
    assert effective_retreat(foe, False, gem, 2) == 3

    # Opponent attack-cost features: dynamic reductions/increases never touch damage.
    ursa = poke(44)
    cost_board = Board([], [ursa], None, our_prizes=3, opp_prizes=6)
    assert effective_attack_costs(ursa, False, cost_board) == [2]  # 5 - 3 prizes taken
    watch_ursa = Board([], [ursa], 1256, our_prizes=3, opp_prizes=6)
    assert effective_attack_costs(ursa, False, watch_ursa) == [5]  # Ability suppressed

    inci = poke(79)
    a0, b1, b2 = poke(796, serial=1), poke(796, serial=2), poke(796, serial=3)
    bench_board = Board([a0, b1, b2], [inci], None)
    bench_board.mark_active(a0); bench_board.mark_active(inci)
    assert effective_attack_costs(inci, False, bench_board) == [3]

    counter = poke(796, tools=[1168])
    counter_board = Board([], [counter], None, our_prizes=3, opp_prizes=5)
    assert effective_attack_costs(counter, False, counter_board)[0] == max(
        0, _st(796).attacks[0].total_cost - 1)

    fossil = poke(1099)
    basic_attacker = poke(796)
    fossil_board = Board([fossil], [basic_attacker], None)
    fossil_board.mark_active(fossil); fossil_board.mark_active(basic_attacker)
    assert effective_attack_costs(basic_attacker, False, fossil_board)[0] == \
        _st(796).attacks[0].total_cost + 1

    tera = poke(320)  # Ceruledge ex is Tera; Charcadet is not.
    mine = Board([], [tera], 1266)
    assert effective_attack_costs(tera, False, mine)[0] == _st(320).attacks[0].total_cost + 1
    char_mine = Board([], [basic_attacker], 1266)
    assert effective_attack_costs(basic_attacker, False, char_mine)[0] == \
        _st(796).attacks[0].total_cost

    # Exact prize-scaled damage and the two user-approved unconditional approximations.
    king = poke(901)
    king_board = Board([], [king], None, our_prizes=2, opp_prizes=6)
    assert damage_dealt_bonus(king, False, a0, king_board) == 120
    assert damage_dealt_bonus(poke(49), False, a0, Board([], [], None)) == 120
    mochi = poke(796, tools=[1162])
    assert damage_dealt_bonus(mochi, False, a0, Board([], [mochi], None)) == 40

    # N's Castle retreat 0 for N's Pokemon only (name filter)
    reg2 = cd.CardRegistry.load()
    ns_id = next((cid for cid in reg2.stats if _name_has(NS(id=cid), "N’s ")), None)
    if ns_id is not None:
        ns_poke = poke(ns_id)
        non_ns = poke(796)                       # Charcadet — not N's
        b = Board([ns_poke, non_ns], [], stadium_id=1253)
        assert effective_retreat(ns_poke, True, b, 3) == 0    # N's -> 0
        assert effective_retreat(non_ns, True, b, 3) == 3     # non-N's unaffected

    print("stat_bakes self-test PASSED")


if __name__ == "__main__":
    _selftest()
