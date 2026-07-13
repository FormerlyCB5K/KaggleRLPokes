"""Generate the spec-07 derived-feature regression battery.

Run from Ceruledge-RL:
    python old/audits/effect-baking/effect_bakes_snapshot.py old/audits/effect-baking/check.json
"""
from __future__ import annotations

import json
import os
import sys

ARCHIVE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(ARCHIVE_DIR)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WORKSPACE = os.path.dirname(ROOT)
if WORKSPACE not in sys.path:
    sys.path.append(WORKSPACE)

import card_data as cd
import features as ft
from features import extract_features
from test_features import mk_obs, mk_player, mk_poke
GameStateTracker = ft.GameStateTracker


OUR = {
    "hp_max": 0, "hp_curr_ratio": 1, "attacks_survivable": 11,
    "attack_damage": 12, "attack_hits_opponent": 13,
}
OPP = {
    "hp_max": 0, "hp_curr_ratio": 1, "retreat_cost": 6,
    "weak_fire": 17, "weak_fighting": 18,
    "resist_fire": 19, "resist_fighting": 20,
    "attacks_survivable_vs_ceruledge": 21,
    "attack0_cost": 28, "attack0_damage": 29,
}


def _row(tensor, indices):
    return {name: round(float(tensor[0][idx]), 8) for name, idx in indices.items()}


def capture(our, opp, stadium_id=None):
    ours, theirs, _, glob = extract_features(
        mk_obs(our, opp, stadium_id=stadium_id), 0, GameStateTracker())
    board = ft.sb.Board(ft._pokemon_in_play(our), ft._pokemon_in_play(opp), stadium_id,
                        our_prizes=len(our.prize or []), opp_prizes=len(opp.prize or []))
    our_active = our.active[0] if our.active else None
    opp_active = opp.active[0] if opp.active else None
    board.mark_active(our_active); board.mark_active(opp_active)
    threat = ft.opp_active_max_damage(opp_active, opp, our, board, our_active)
    return {
        "our_active": _row(ours, OUR),
        "opp_active": _row(theirs, OPP),
        "ceruledge_KO": round(float(glob[3]), 8),
        "opp_active_max_damage": int(threat),
    }


def battery():
    reg = cd.CardRegistry.load()
    fire_weak = next(cid for cid, st in reg.stats.items() if st.weak_fire and st.max_hp)
    metal = next(cid for cid, st in reg.stats.items() if st.type_sym == "{M}" and st.max_hp)
    stage2 = next(cid for cid, st in reg.stats.items()
                  if st.stage == "Stage 2 Pokémon" and st.max_hp)

    cer = mk_poke(ft.Ceruledge_ex, 270, 270, energy=[ft.Fire_Energy])
    char = mk_poke(ft.Charcadet, 80, 80)
    cases = {}

    def add(name, ours, theirs, stadium=None):
        cases[name] = capture(ours, theirs, stadium)

    add("vanilla", mk_player(active=cer, discard=[ft.Fire_Energy] * 2, player=0),
        mk_player(active=mk_poke(ft.Charcadet, 80, 80, player=1), player=1))
    fw_hp = reg.get(fire_weak).max_hp
    add("fire_weak_applies", mk_player(active=cer, discard=[ft.Fire_Energy] * 2, player=0),
        mk_player(active=mk_poke(fire_weak, fw_hp, fw_hp, player=1), player=1))
    add("damage_reduction_applies", mk_player(active=cer, discard=[ft.Fire_Energy] * 2, player=0),
        mk_player(active=mk_poke(383, 150, 150, player=1), player=1))
    add("damage_reduction_does_not_apply", mk_player(active=cer, discard=[ft.Fire_Energy] * 2, player=0),
        mk_player(active=mk_poke(ft.Charcadet, 150, 150, player=1), player=1))
    add("damage_reduction_our_side", mk_player(active=mk_poke(383, 150, 150), player=0),
        mk_player(active=mk_poke(ft.Charcadet, 80, 80, player=1), player=1))
    add("hp_stadium_applies", mk_player(active=char, player=0),
        mk_player(active=mk_poke(235, 30, 30, player=1), player=1), 1251)
    s2hp = reg.get(stage2).max_hp
    add("hp_stadium_does_not_apply", mk_player(active=char, player=0),
        mk_player(active=mk_poke(stage2, s2hp, s2hp, player=1), player=1), 1251)
    add("retreat_tool_applies", mk_player(active=char, player=0),
        mk_player(active=mk_poke(383, 150, 150, player=1, tools=[1174]), player=1))
    add("retreat_tool_suppressed", mk_player(active=char, player=0),
        mk_player(active=mk_poke(383, 150, 150, player=1, tools=[1174]), player=1), 1246)
    add("retreat_tool_our_side", mk_player(active=mk_poke(383, 150, 150, tools=[1174]), player=0),
        mk_player(active=mk_poke(ft.Charcadet, 80, 80, player=1), player=1))
    mhp = reg.get(metal).max_hp
    add("typed_stadium_applies", mk_player(active=cer, player=0),
        mk_player(active=mk_poke(metal, mhp, mhp, player=1), player=1), 1244)
    add("typed_stadium_does_not_apply", mk_player(active=cer, player=0),
        mk_player(active=mk_poke(ft.Charcadet, 80, 80, player=1), player=1), 1244)
    add("typed_stadium_our_side", mk_player(active=mk_poke(metal, mhp, mhp), player=0),
        mk_player(active=mk_poke(ft.Charcadet, 80, 80, player=1), player=1), 1244)
    add("bloodmoon_dynamic_cost", mk_player(active=char, prize_count=3, player=0),
        mk_player(active=mk_poke(44, 260, 260, player=1), prize_count=6, player=1))
    add("bloodmoon_watchtower_suppressed",
        mk_player(active=char, prize_count=3, player=0),
        mk_player(active=mk_poke(44, 260, 260, player=1), prize_count=6, player=1), 1256)
    add("nighttime_mine_opponent_tera", mk_player(active=char, player=0),
        mk_player(active=mk_poke(ft.Ceruledge_ex, 270, 270, player=1), player=1), 1266)
    add("nighttime_mine_charcadet_negative", mk_player(active=char, player=0),
        mk_player(active=mk_poke(ft.Charcadet, 80, 80, player=1), player=1), 1266)
    return cases


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: effect_bakes_snapshot.py OUTPUT.json")
    payload = {"csv_sha256": "A0EA63CF7ADCB65D35436CE0EB390DE6E2E35654A7C67C065A45F4ABAA00F373",
               "cases": battery()}
    with open(sys.argv[1], "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {len(payload['cases'])} cases -> {sys.argv[1]}")
