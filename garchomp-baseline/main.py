"""Cynthia's Garchomp ex — Rule-based agent

Pokemon:
  Cynthia's Gible (379)       - Basic {F} HP70. Rock Hurl {F}=20.
  Cynthia's Gabite (380)      - Stage 1 {F} HP100. [Ability] Champion's Call: search Cynthia's Pokemon.
                                 Dragonslice {F}=40.
  Cynthia's Garchomp ex (381) - Stage 2 {F} ex HP330. Corkscrew Dive {F}=100+draw6.
                                 Draconic Buster {F}{F}=260, discard all Energy.
  Cynthia's Roselia (341)     - Basic {G} HP70. Spike Sting {C}=20.
  Cynthia's Roserade (342)    - Stage 1 {G} HP130. [Ability] Cheer On to Glory: Cynthia's attacks +30.
                                 Leaf Step {C}{C}{C}=80.
  Cynthia's Spiritomb (387)   - Basic {D} HP70. Raging Curse {C}=10 x bench Cynthia damage counters.
                                 Weakness ignored (resistance still applies)

Damage modifiers:
  - Roserade Ability: Cynthia's attacks +30 per Roserade in play
  - PP (1141): +30 to Fighting attacks only (G-line only, not R-line/Spiritomb)
  - Weakness/Resistance: based on attacker's type
      G-line {F}: Fighting weakness x2 / Fighting resistance -30
      R-line {G}: Grass weakness x2 / Grass resistance -30
      Spiritomb {D}: weakness ignored / Dark resistance -30
  - FML (1244): -30 to all attacks vs Metal-type Pokemon

Trainers:
  Boss's Orders (1182) x4, Lillie (1227) x4, Larry (1206) x2, Petrel (1219) x1,
  Poke Pad (1152) x4, Poffin (1086) x4, Fighting Gong (1142) x3, Pokegear (1122) x2,
  PP (1141) x2, Switch (1123) x1, Unfair Stamp (1080) x1, Power Weight (1173) x4.

Energy: Basic {F} (6) x5, Rock Fighting (20) x4.

Source: Neddy Kosek, Regional Prague 2026-04-25, 3rd/1370 (12-2-2)
"""

import os, random, sys

try:
    ROOT = __file__
except NameError:
    ROOT = None
_here = os.path.dirname(os.path.abspath(ROOT)) if ROOT else None
for p in ([_here, os.path.dirname(_here)] if _here else []) + ["/kaggle_simulations/agent"]:
    if p and os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

try:
    from cg.api import (
        AreaType, LogType, OptionType, SelectContext,
        Pokemon, all_card_data, to_observation_class,
    )
except ImportError:  # local repo layout: package lives at <repo root>/cg_download
    from cg_download.api import (
        AreaType, LogType, OptionType, SelectContext,
        Pokemon, all_card_data, to_observation_class,
    )

# ── Card IDs ──
GIBLE = 379; GABITE = 380; GARCHOMP_EX = 381
ROSELIA = 341; ROSERADE = 342; SPIRITOMB = 387
BOSS = 1182; LILLIE = 1227; LARRY = 1206; PETREL = 1219
POKE_PAD = 1152; POFFIN = 1086; FIGHTING_GONG = 1142; POKEGEAR = 1122
PP = 1141; SWITCH = 1123; UNFAIR_STAMP = 1080; POWER_WEIGHT = 1173
F_ENERGY = 6; ROCK_F_ENERGY = 20

SUPPORTERS = {BOSS, LILLIE, LARRY, PETREL}
CARD_DB = {c.cardId: c for c in all_card_data()}

LINE_G = {GIBLE, GABITE, GARCHOMP_EX}
LINE_R = {ROSELIA, ROSERADE}
CYNTHIA_POKEMON = LINE_G | LINE_R | {SPIRITOMB}

# ── Static tables ──

CORKSCREW_DIVE = 531; DRACONIC_BUSTER = 532
ROCK_HURL = 529; DRAGONSLICE = 530
SPIKE_STING = 475; LEAF_STEP = 476; RAGING_CURSE = 540

ATTACKS = {
    GARCHOMP_EX: ((CORKSCREW_DIVE, 1, 100), (DRACONIC_BUSTER, 2, 260)),
    GABITE: ((DRAGONSLICE, 1, 40),),
    GIBLE: ((ROCK_HURL, 1, 20),),
    ROSELIA: ((SPIKE_STING, 1, 20),),
    ROSERADE: ((LEAF_STEP, 3, 80),),
}
BASE_DAMAGE = {(cid, aid): dmg for cid, xs in ATTACKS.items() for aid, _, dmg in xs}
FIGHTING_ATTACKS = {
    (GARCHOMP_EX, CORKSCREW_DIVE), (GARCHOMP_EX, DRACONIC_BUSTER),
    (GABITE, DRAGONSLICE), (GIBLE, ROCK_HURL),
}
MATCHUPS = (
    ("lucario",   {672, 673, 678}),
    ("starmie",   {1029, 1030, 1031}),
    ("dragapult", {119, 120, 121}),
    ("alakazam",  {741, 742, 743}),
    ("okidogi",   {116}),
    ("iono",      {265, 267, 269}),
    ("hop",       {878, 879}),
    ("crustle",   {344, 345}),
    ("arch",      {169, 190}),
)
OPP_MAX_DAMAGE = {
    "lucario": 270, "starmie": 210, "dragapult": 200, "alakazam": 200,
    "okidogi": 170, "iono": 200, "hop": 220, "crustle": 120, "arch": 220, "generic": 200,
}
SETUP_ACTIVE_SCORE = {ROSELIA: 100, GIBLE: 80}
MY_ACTIVE_SCORE = {GARCHOMP_EX: 20, GABITE: 10, GIBLE: 5}
ATTACH_FROM_SCORE = {GARCHOMP_EX: 20000, GABITE: 12000, GIBLE: 10000}
SUPPORTER_SCORE = {PETREL: 4, LARRY: 3, LILLIE: 2}
TOOL_SCORE = {GARCHOMP_EX: 16000, GABITE: 9000, GIBLE: 6000}
FALLBACK_HAND_SCORE = {
    GABITE: 50000, GARCHOMP_EX: 45000, ROSERADE: 40000,
    F_ENERGY: 30000, ROCK_F_ENERGY: 30000, POWER_WEIGHT: 25000,
    LILLIE: 20000, LARRY: 20000, PETREL: 20000, POKE_PAD: 20000, POKEGEAR: 20000,
}

# ── PP tracking ──

_pp_played_count = 0

def _update_pp_tracking(obs):
    global _pp_played_count
    _pp_played_count = 0
    for e in obs.logs:
        if e.type == LogType.TURN_START:
            _pp_played_count = 0
        elif (e.type == LogType.PLAY
              and e.playerIndex == obs.current.yourIndex
              and e.cardId == PP):
            _pp_played_count += 1

def read_deck_csv():
    paths = ["deck.csv", "/kaggle_simulations/agent/deck.csv"]
    if _here:
        paths.insert(0, os.path.join(_here, "deck.csv"))
    for fp in paths:
        if os.path.exists(fp):
            with open(fp) as f:
                return [int(x) for x in f.read().split() if x.strip()]
    return []

# ── View: cached board state ──

class View:
    def __init__(self, obs):
        self.obs = obs
        self.st = obs.current
        self.mi = self.st.yourIndex
        self.me = self.st.players[self.mi]
        self.opp = self.st.players[1 - self.mi]
        self.mine = [p for p in list(self.me.active or []) + list(self.me.bench or []) if p]
        self.opps = [p for p in list(self.opp.active or []) + list(self.opp.bench or []) if p]
        self.active = self.me.active[0] if self.me.active else None
        self.opp_active = self.opp.active[0] if self.opp.active else None
        self.opp_bench = [p for p in (self.opp.bench or []) if p]
        self.rose = sum(1 for p in self.mine if p.id == ROSERADE)
        self.gline = sum(1 for p in self.mine if p.id in LINE_G)
        self.rline = sum(1 for p in self.mine if p.id in LINE_R)
        self.g_basic = sum(1 for p in self.mine if p.id == GIBLE)
        self.r_basic = sum(1 for p in self.mine if p.id == ROSELIA)
        self.has_garchomp = any(p.id == GARCHOMP_EX for p in self.mine)
        self.evo = {
            cid: sum(1 for p in self.mine if p.id == cid and not getattr(p, "appearThisTurn", True))
            for cid in (GIBLE, GABITE, ROSELIA)
        }
        ids = {p.id for p in self.opps}
        self.matchup = next((name for name, line in MATCHUPS if ids & line), "generic")
        self.attacks = self._option_attacks() or self._estimated_attacks()
        self.fml = bool(self.st.stadium and self.st.stadium[0].id == 1244)
        self.rc_base = self._raging_curse_base()
        self.rc_dmg = self.rc_base + 30 * self.rose
        self.rc_target = self._raging_curse_target()
        self.spread_matchup = self.matchup in {"dragapult", "starmie"}
        self.has_spiritomb = any(p.id == SPIRITOMB for p in self.mine)
        self.can_retreat = any(o.type == OptionType.RETREAT for o in self.obs.select.option or [])
        self.rc_mode = self._raging_curse_mode()
        self.win = self._win_plan()

    def bench_has(self, cid, energy=0):
        return any(p.id == cid and self.energy(p) >= energy for p in self.me.bench or [] if p)

    def get(self, area, index, pi=None):
        if area is None or index is None:
            return None
        ps = self.st.players[self.mi if pi is None else pi]
        if area == AreaType.DECK:
            arr = self.obs.select.deck if self.obs.select else None
        else:
            arr = {
                AreaType.HAND: ps.hand, AreaType.ACTIVE: ps.active,
                AreaType.BENCH: ps.bench, AreaType.DISCARD: ps.discard,
            }.get(area)
        return arr[index] if arr and index < len(arr) else None

    def energy(self, p):
        if not p:
            return 0
        ec = getattr(p, "energyCards", None)
        return len(ec) if ec is not None else len(getattr(p, "energies", []) or [])

    def dmg_on(self, p):
        return 0 if not p else max(0, getattr(p, "maxHp", p.hp) - p.hp)

    def prize(self, p):
        data = CARD_DB.get(p.id) if p else None
        return 3 if data and getattr(data, "megaEx", False) else 2 if data and getattr(data, "ex", False) else 1

    def mod_damage(self, dmg, target, aid=None, attacker_id=None):
        data = CARD_DB.get(target.id) if target else None
        if not data:
            return dmg
        atk_id = attacker_id if attacker_id is not None else (self.active.id if self.active else None)
        if atk_id is not None:
            atk_data = CARD_DB.get(atk_id)
            atk_type = int(atk_data.energyType) if atk_data and getattr(atk_data, "energyType", None) is not None else None
            if atk_type is not None:
                w, r = getattr(data, "weakness", None), getattr(data, "resistance", None)
                if aid != RAGING_CURSE and w is not None and int(w) == atk_type:
                    dmg *= 2
                if r is not None and int(r) == atk_type:
                    dmg = max(0, dmg - 30)
        if self.fml and getattr(data, "energyType", None) is not None and int(data.energyType) == 8:
            dmg = max(0, dmg - 30)
        return dmg

    def _option_attacks(self):
        return [
            o.attackId for o in (self.obs.select.option or [])
            if o.type == OptionType.ATTACK and o.attackId is not None
        ]

    def _estimated_attacks(self):
        a = self.active
        if not a:
            return []
        e = self.energy(a)
        if a.id == SPIRITOMB and e >= 1:
            return [RAGING_CURSE]
        return [aid for aid, cost, _ in ATTACKS.get(a.id, ()) if e >= cost]

    def base_damage(self, aid):
        a = self.active
        if not a:
            return 0
        if a.id == SPIRITOMB and aid == RAGING_CURSE:
            return self.rc_base
        return BASE_DAMAGE.get((a.id, aid), 0)

    def damage(self, aid, target=None, extra_pp=0):
        a = self.active
        if not a:
            return 0
        dmg = self.base_damage(aid)
        if a.id in CYNTHIA_POKEMON and dmg > 0:
            dmg += 30 * self.rose
        if (a.id, aid) in FIGHTING_ATTACKS:
            dmg += 30 * (_pp_played_count + extra_pp)
        return dmg if target is None else self.mod_damage(dmg, target, aid, a.id)

    def can_ko_active(self, extra_pp=0):
        t = self.opp_active
        return bool(t) and any(self.damage(aid, t, extra_pp) >= t.hp for aid in self.attacks)

    def pp_unlocks_ko(self):
        return not self.can_ko_active(0) and self.can_ko_active(1)

    def should_boss(self):
        if not self.attacks or self.can_ko_active():
            return False
        return any(
            any(self.damage(aid, p) >= p.hp for aid in self.attacks)
            for p in self.opp_bench
        )

    def gline_base(self, p):
        e = self.energy(p)
        if p.id == GARCHOMP_EX:
            return 260 if e >= 2 else 100
        return 40 if p.id == GABITE else 20

    def bench_gline_can_ko(self):
        t = self.opp_active
        if not t:
            return False
        for p in (self.me.bench or []):
            if not p or p.id not in LINE_G:
                continue
            e = self.energy(p)
            if e < 1:
                continue
            if p.id == GARCHOMP_EX:
                aid = DRACONIC_BUSTER if e >= 2 else CORKSCREW_DIVE
            elif p.id == GABITE:
                aid = DRAGONSLICE
            else:
                aid = ROCK_HURL
            dmg = self.gline_base(p) + 30 * self.rose + 30 * _pp_played_count
            if self.mod_damage(dmg, t, aid, p.id) >= t.hp:
                return True
        return False

    def _raging_curse_base(self):
        return sum(self.dmg_on(p) for p in self.mine if p.id in CYNTHIA_POKEMON and p.id != SPIRITOMB)

    def _raging_curse_target(self):
        if self.rc_dmg < 260:
            return None
        xs = []
        for p in [self.opp_active] + self.opp_bench:
            if not p:
                continue
            real_rc = self.mod_damage(self.rc_dmg, p, RAGING_CURSE, SPIRITOMB)
            if real_rc < p.hp:
                continue
            if p is self.opp_active and self.active:
                if any(self.damage(aid, p) >= p.hp for aid in self.attacks):
                    continue
            if p.hp >= 250 or self.prize(p) >= 2:
                xs.append(p)
        return max(xs, key=lambda p: (self.prize(p), p.hp, self.energy(p)), default=None)

    def _raging_curse_mode(self):
        if not self.spread_matchup or self.has_spiritomb:
            return False
        if len(self.me.bench or []) >= 5 or self.st.energyAttached or not self.can_retreat:
            return False
        t = self.opp_active
        if not t or t.hp < 260 or self.rc_dmg < t.hp:
            return False
        if self.active and self.active.id == GARCHOMP_EX and self.energy(self.active):
            if self.damage(CORKSCREW_DIVE, t) >= t.hp:
                return False
        return True

    def wants_spiritomb_search(self):
        return not self.has_spiritomb and (self.rc_target or self.rc_mode)

    def wants_spiritomb_execute(self):
        return self.has_spiritomb and self.rc_target

    def is_win_ko(self, p):
        return bool(p) and (len(self.me.prize) <= self.prize(p) or (p is self.opp_active and len(self.opps) == 1))

    def plan_attacks(self):
        a = self.active
        if a and a.id == GARCHOMP_EX and not self.st.energyAttached:
            e = self.energy(a) + 1
            return [aid for aid, cost, _ in ATTACKS[GARCHOMP_EX] if e >= cost]
        return self.attacks

    def ko_attack(self, p, attacks=None, extra_pp=0):
        xs = [aid for aid in (attacks or self.attacks) if self.damage(aid, p, extra_pp) >= p.hp]
        if not xs:
            return None
        return CORKSCREW_DIVE if CORKSCREW_DIVE in xs else xs[0]

    def _can_use_pp(self):
        return (self.active and self.active.id in LINE_G
                and any(c and c.id == PP for c in self.me.hand or []))

    def _win_plan(self):
        attacks = self.plan_attacks()
        has_pp = self._can_use_pp()
        # Front KO
        p = self.opp_active
        if self.is_win_ko(p):
            aid = self.ko_attack(p, attacks)
            if aid:
                return (p, aid, False, False)
            if has_pp:
                aid = self.ko_attack(p, attacks, extra_pp=1)
                if aid:
                    return (p, aid, False, True)
        # Boss KO
        has_boss = not self.st.supporterPlayed and any(
            c and c.id == BOSS for c in self.me.hand or [])
        if not has_boss:
            return None
        for p in self.opp_bench:
            if self.is_win_ko(p):
                aid = self.ko_attack(p, attacks)
                if aid:
                    return (p, aid, True, False)
                if has_pp:
                    aid = self.ko_attack(p, attacks, extra_pp=1)
                    if aid:
                        return (p, aid, True, True)
        return None

    def to_hand_score(self, cid):
        if self.spread_matchup and not self.has_spiritomb and len(self.me.bench or []) >= 4:
            if cid in {GIBLE, ROSELIA, POFFIN}:
                return 1000
        eg, ega, er = self.evo[GIBLE], self.evo[GABITE], self.evo[ROSELIA]
        if cid == GIBLE:
            if self.g_basic < 2:
                return 90000 + 1000 * (2 - self.g_basic)
            if self.r_basic >= 2 and self.g_basic < 3:
                return 60000
            return 1000
        if cid == ROSELIA:
            if self.r_basic < 2:
                base = 88000 if self.g_basic >= 2 else 65000
                return base + 1000 * (2 - self.r_basic)
            if self.g_basic < 2:
                return 30000
            return 1000
        if cid == POFFIN:
            if self.g_basic < 2 or self.r_basic < 2:
                return 85000
            if self.g_basic < 3 and self.r_basic >= 2:
                return 50000
            return 1000
        if eg:
            if cid == GABITE:
                return 100000 + 1000 * eg
            if cid == POKE_PAD:
                return 99000
            if cid in {GARCHOMP_EX, ROSERADE}:
                return 1000
        if self.wants_spiritomb_search() and cid == SPIRITOMB:
            return 96000
        if ega and not self.has_garchomp:
            if cid == GARCHOMP_EX:
                return 95000 + 1000 * ega
        if cid == FIGHTING_GONG:
            if self.wants_spiritomb_search():
                return 97000
            if self.gline < 3:
                return 80000
        if er and cid == ROSERADE:
            return 70000 + 1000 * er
        if cid == PP and self.pp_unlocks_ko():
            return 24000
        if cid == BOSS:
            return 22000 if self.should_boss() else 5000
        return FALLBACK_HAND_SCORE.get(cid, 1000)

# ── Scorer ──

class Scorer:
    def __init__(self, v):
        self.v = v
        self.st = v.st
        self.me = v.me
        self.mi = v.mi
        self.ctx = v.obs.select.context

    def sc(self, o):
        t = o.type
        if t == OptionType.NUMBER: return o.number or 0
        if t == OptionType.YES:
            return 100 if self.ctx == SelectContext.IS_FIRST else 1
        if t == OptionType.NO: return 0
        if t == OptionType.CARD:   return self._sc_card(o)
        if t == OptionType.PLAY:   return self._sc_play(o)
        if t == OptionType.ATTACH: return self._sc_attach(o)
        if t == OptionType.EVOLVE: return self._sc_evolve(o)
        if t == OptionType.ABILITY:return self._sc_ability(o)
        if t == OptionType.RETREAT:return self._sc_retreat(o)
        if t == OptionType.ATTACK: return self._sc_attack(o)
        if t == OptionType.END:    return 0
        return 0

    def _sc_card(self, o):
        c = self.v.get(o.area, o.index, o.playerIndex if o.playerIndex is not None else self.mi)
        if c is None:
            return 0
        cid = c.id
        if self.ctx == SelectContext.SETUP_ACTIVE_POKEMON:
            return SETUP_ACTIVE_SCORE.get(cid, 1)
        if self.ctx == SelectContext.SETUP_BENCH_POKEMON:
            return -1
        if self.ctx in (SelectContext.SWITCH, SelectContext.TO_ACTIVE):
            pi = self.mi if o.playerIndex is None else o.playerIndex
            if not isinstance(c, Pokemon):
                return 0
            if pi != self.mi:
                if self.v.win and c is self.v.win[0]:
                    return 30000
                dmg = max((self.v.damage(aid, c) for aid in self.v.attacks), default=0)
                return 20000 + self.v.prize(c) * 3000 + self.v.energy(c) * 100 if dmg >= c.hp else 1000
            if cid == SPIRITOMB and self.v.wants_spiritomb_execute():
                return 40
            return MY_ACTIVE_SCORE.get(cid, 1) + c.hp / 1000
        if self.ctx == SelectContext.TO_HAND:
            return self.v.to_hand_score(cid)
        if self.ctx == SelectContext.ATTACH_FROM:
            return ATTACH_FROM_SCORE.get(cid, 0) if isinstance(c, Pokemon) else 0
        if self.ctx in (SelectContext.TO_FIELD, SelectContext.TO_BENCH):
            return self.v.to_hand_score(cid)
        return 0

    def _sc_play(self, o):
        c = self.v.get(AreaType.HAND, o.index, self.mi)
        if c is None:
            return 0
        cid = c.id
        if cid == SWITCH:
            has_status = (self.me.poisoned or self.me.burned or self.me.asleep
                          or self.me.paralyzed or self.me.confused)
            if (has_status or (not self.v.attacks and self.v.bench_gline_can_ko())
                    or (self.v.wants_spiritomb_execute() and self.v.bench_has(SPIRITOMB, 1))):
                return 18000
            return -1
        if cid == PP:
            if self.v.pp_unlocks_ko():
                return 18000
            if self.v.win and self.v.win[3]:
                return 18000
            return -1
        if cid == BOSS:
            if self.st.supporterPlayed:
                return -1
            if self.v.win and self.v.win[2]:
                return 30000
            if self.v.rc_target in self.v.opp_bench and self.v.bench_has(SPIRITOMB, 1):
                return 10007
            a = self.v.active
            if a and a.id == GARCHOMP_EX and self.v.energy(a) >= 1:
                if any(p.id == 269 and self.v.damage(CORKSCREW_DIVE, p) >= p.hp
                       for p in self.v.opp_bench):
                    return 10006
            return 10006 if self.v.should_boss() else -1
        if cid == UNFAIR_STAMP:
            return 12000
        if cid == SPIRITOMB:
            return 27000 if self.v.wants_spiritomb_search() else -1
        if cid in SUPPORTERS:
            if self.st.supporterPlayed:
                return -1
            if cid == LARRY:
                threshold = OPP_MAX_DAMAGE.get(self.v.matchup, 200)
                if self.me.handCount >= 3 and any(
                    p.id == GARCHOMP_EX and self.v.energy(p) >= 1 and p.hp > threshold
                    for p in self.v.mine):
                    return -1
            if cid == LILLIE and len(self.me.prize) == 6:
                return 10005
            return 10000 + SUPPORTER_SCORE.get(cid, 0)
        return 15000 + self.v.to_hand_score(cid)

    def _sc_evolve(self, o):
        c = self.v.get(AreaType.HAND, o.index, self.mi)
        if not c:
            return 0
        if self.v.matchup == "crustle" and c.id == GARCHOMP_EX:
            return -1
        score = 20000 + self.v.to_hand_score(c.id)
        # Prefer evolving bench Roselia (Active is more vulnerable)
        if c.id == ROSERADE and self.v.active and self.v.active.id == ROSELIA:
            bench_roselia = sum(1 for p in (self.me.bench or []) if p and p.id == ROSELIA)
            if bench_roselia > 0:
                score -= 1
        return score

    def _sc_attach(self, o):
        c = self.v.get(AreaType.HAND, o.index, self.mi)
        p = self.v.get(o.inPlayArea, o.inPlayIndex, self.mi)
        if c is None or not isinstance(p, Pokemon):
            return 0
        if c.id == POWER_WEIGHT:
            if getattr(p, "tools", None):
                return -1
            if self.v.matchup == "dragapult":
                if p.id == ROSELIA: return 16500
                if p.id == ROSERADE: return 15000
                if p.id == GABITE: return 12000
                if p.id == GIBLE: return 8000
                if p.id == GARCHOMP_EX: return 3000
                return -1
            if self.v.matchup == "crustle":
                if p.id == ROSELIA: return 18000
                if p.id == SPIRITOMB: return 16000
                return -1
            # Active Roselia gets Weight first (survives more hits as front wall)
            if p.id == ROSELIA and o.inPlayArea == AreaType.ACTIVE:
                return 19000
            return TOOL_SCORE.get(p.id, -1)
        if c.id not in {F_ENERGY, ROCK_F_ENERGY}:
            return 0
        if self.st.energyAttached:
            return -1
        e = self.v.energy(p)
        if e >= 3:
            return -1
        rock = int(c.id == ROCK_F_ENERGY and self.v.matchup == "alakazam")
        is_active = o.inPlayArea == AreaType.ACTIVE
        if self.v.win and p is self.v.active and p.id == GARCHOMP_EX:
            if self.v.win[1] == DRACONIC_BUSTER and e == 1:
                return 30000 + rock
            if self.v.win[1] == CORKSCREW_DIVE and e == 0:
                return 30000 + rock
        if p.id == GARCHOMP_EX:
            if is_active and e == 1:
                t = self.v.opp_active
                bust_ko = t and self.v.damage(DRACONIC_BUSTER, t) >= t.hp
                dive_ko = t and self.v.damage(CORKSCREW_DIVE, t) >= t.hp
                return (19000 if bust_ko and not dive_ko else 2000) + rock
            return (19000 if e == 0 else 2000) + rock
        if p.id == GABITE: return (19000 if e == 0 else 500) + rock
        if p.id == GIBLE: return (19000 if e == 0 else 500) + rock
        if p.id == SPIRITOMB:
            return 29500 + rock if self.v.wants_spiritomb_execute() and e == 0 else -1
        if p.id in LINE_R:
            if self.v.matchup == "crustle":
                return 19000 + rock if p.id == ROSELIA and e == 0 else -1
            if is_active and self.v.bench_gline_can_ko():
                return 19000
            return 1000
        return 500

    def _sc_ability(self, o):
        c = self.v.get(o.area, o.index, self.mi)
        return 30000 if c and c.id == GABITE else (1 if c else 0)

    def _sc_retreat(self, o):
        if self.st.retreated:
            return -1
        if self.v.can_ko_active():
            return -1
        a = self.v.active
        if not a:
            return -1
        if a.id in LINE_R and self.v.bench_gline_can_ko():
            return 19000
        if self.v.wants_spiritomb_execute() and self.v.bench_has(SPIRITOMB, 1):
            return 29003
        if a.id == GARCHOMP_EX:
            threshold = OPP_MAX_DAMAGE.get(self.v.matchup, 200)
            if a.hp <= threshold:
                for p in (self.me.bench or []):
                    if p and p.id == GARCHOMP_EX and p.hp > threshold:
                        return 19001
        return -1

    def _sc_attack(self, o):
        a, t = self.v.active, self.v.opp_active
        if not a:
            return 0
        if a.id == GARCHOMP_EX and o.attackId == DRACONIC_BUSTER:
            dive_ko = t and self.v.damage(CORKSCREW_DIVE, t) >= t.hp
            bust_ko = t and self.v.damage(DRACONIC_BUSTER, t) >= t.hp
            return 1001 if bust_ko and not dive_ko else 999
        return 1000


# ── Choose & Agent ──

def choose(obs):
    v = View(obs)
    s = Scorer(v)
    opts = obs.select.option
    chosen = []
    used = set()
    for _ in range(obs.select.maxCount):
        best, best_i = -1, -1
        for i, o in enumerate(opts):
            if i in used:
                continue
            sc = s.sc(o)
            if sc > best:
                best, best_i = sc, i
        if best_i < 0 or (best < 0 and len(chosen) >= obs.select.minCount):
            break
        chosen.append(best_i)
        used.add(best_i)
        # Update counts for next pick (G/R balance in Poffin multi-select)
        pi = getattr(opts[best_i], "playerIndex", None)
        if pi is None:
            pi = v.mi
        c = v.get(opts[best_i].area, opts[best_i].index, pi)
        if c:
            if c.id in LINE_G: v.gline += 1
            if c.id in LINE_R: v.rline += 1
            if c.id == GIBLE: v.g_basic += 1
            if c.id == ROSELIA: v.r_basic += 1
    if len(chosen) < obs.select.minCount:
        scores = [s.sc(o) for o in opts]
        ranked = sorted(range(len(opts)), key=lambda i: (-scores[i], i))
        chosen = ranked[:obs.select.minCount]
    return chosen


def agent(obs_dict):
    obs = to_observation_class(obs_dict)
    if obs.select is None:
        global _pp_played_count
        _pp_played_count = 0
        return read_deck_csv()
    _update_pp_tracking(obs)
    if not obs.select.option:
        return []
    try:
        return choose(obs)
    except Exception:
        return random.sample(list(range(len(obs.select.option))), obs.select.maxCount)
