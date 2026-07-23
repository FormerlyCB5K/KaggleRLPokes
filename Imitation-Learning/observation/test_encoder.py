"""Acceptance tests for the spec 13a observation encoder, mirroring the old encoding's
verification convention (`smoke_test_encoder.py`): shape checks, PAD/UNK correctness, and a
few hand-verifiable values on a constructed board state.

Run with: python -m pytest observation/test_encoder.py -v
"""
from __future__ import annotations

from .board_context import GameBoardContext, raw_attack_damage_for, raw_pokemon_to_board_pokemon
from .encoder import BoardPokemonState, GameState, build_observation
from .live_state import RawPokemon, hits_ratio
from .pokemon_tag_catalog import CONTENT_TAGS
from .stat_bakes import Board, BoardPokemon, active_modifiers
from .static_template import TAG_BLOCK_WIDTH, build_pokemon_static
from .trainer_energy_static import TAG_BLOCK_WIDTH as TE_TAG_BLOCK_WIDTH, build_trainer_energy_static
from .trainer_energy_tag_catalog import CONTENT_TAGS as TE_CONTENT_TAGS
from .types import TOTAL_WORDS, WR_TYPE_INDEX
from .zones import build_zone_array


def _sample_state() -> GameState:
    return GameState(
        our_deck=[1, 2, 3, 4, 5],
        our_hand=[743, 190, 1174],
        our_discard=[121],
        our_prizes_known=[906],
        our_prizes_hidden_count=5,
        opponent_discard=[1266],
        board=[
            BoardPokemonState(
                "our_active",
                RawPokemon(card_id=743, hp=100, max_hp=140, energy_cards=(1, 1), is_active=True),
            ),
            BoardPokemonState(
                "our_bench",
                RawPokemon(card_id=190, hp=300, max_hp=300, tool_card_id=1174, is_basic=False),
            ),
            BoardPokemonState(
                "opponent_active",
                RawPokemon(card_id=121, hp=200, max_hp=320, is_active=True),
            ),
        ],
        stadium_card_id=1266,
        turn_number=4,
    )


def test_total_word_count_is_174():
    words = build_observation(_sample_state())
    assert len(words) == TOTAL_WORDS == 174


def test_pad_count_matches_occupancy():
    words = build_observation(_sample_state())
    # deck 5/47, hand 3/20, our_discard 1/40, opp_discard 1/40, board 3/18, prizes 6/6 (no pad)
    expected_pad = (47 - 5) + (20 - 3) + (40 - 1) + (40 - 1) + (18 - 3)
    assert sum(1 for w in words if w.attention_masked) == expected_pad


def test_unk_is_not_attention_masked():
    words = build_observation(_sample_state())
    prize_words = [w for w in words if w.role == "our_prizes"]
    assert len(prize_words) == 6
    known = [w for w in prize_words if w.static.card_id is not None]
    unk = [w for w in prize_words if w.static.card_id is None]
    assert len(known) == 1 and len(unk) == 5
    assert all(not w.attention_masked for w in unk), "UNK must not be masked"


def test_board_word_hp_curr_matches_raw():
    words = build_observation(_sample_state())
    our_active = next(w for w in words if w.role == "our_active")
    assert our_active.live["hp_curr"] == 100 / 140


def test_stadium_word_present_when_in_play():
    words = build_observation(_sample_state())
    stadium = next(w for w in words if w.kind == "stadium")
    assert stadium.static.card_id == 1266


def test_stadium_word_is_pad_when_absent():
    state = _sample_state()
    state = GameState(**{**state.__dict__, "stadium_card_id": None})
    words = build_observation(state)
    stadium_words = [w for w in words if w.kind == "stadium"]
    assert stadium_words == []  # became a plain pad word, not tagged "stadium"


def test_zone_overflow_is_flagged_not_dropped():
    zone = build_zone_array(list(range(1, 60)), capacity=47)
    assert zone.overflow_count == 12


def test_canonical_ordering_is_by_card_id():
    zone = build_zone_array([190, 1, 743], capacity=10)
    known = [s.card_id for s in zone.slots if s.kind == "CARD"]
    assert known == sorted(known)


def test_bake_source_target_scoping():
    """Latias ex's retreat-zeroing ability affects OTHER own Basic Pokemon, not just
    Latias ex itself -- the exact source/target bug this module was built to avoid."""
    latias = BoardPokemon(card_id=184, name="Latias ex")
    other_basic = BoardPokemon(card_id=57, name="Relicanth", is_basic=True)
    board = Board(holder=other_basic, attacker=None, own_side=(latias, other_basic), opponent_side=())
    mods = active_modifiers(board)
    assert [(m.stat, m.value) for m in mods] == [("retreat_set", 0)]


def test_meta_pokemon_tag_block_is_real():
    """Alakazam's ability row (card:743:ability:0) is DRAW(3) in spec 11a's manual
    assignment table -- confirms the tag block is the real transcribed lookup, not the
    zero-stub this module started as."""
    static = build_pokemon_static(743)
    assert len(static.tag_block) == TAG_BLOCK_WIDTH
    ability_start = 70 * 2  # 2 attack-shaped blocks precede the ability-shaped block
    draw_idx = ability_start + CONTENT_TAGS.index("DRAW")
    assert static.tag_block[draw_idx] == 3 / 6


def test_non_meta_pokemon_uses_regex_fallback():
    """Croconaw (non-meta) has "Switch this Pokemon with 1 of your Benched Pokemon" as its
    only attack text -- SELF_SWITCH should fire via Deliverable B's regex parser, proving
    the non-meta fallback path is wired, not silently skipped."""
    static = build_pokemon_static(48)
    assert len(static.tag_block) == TAG_BLOCK_WIDTH
    self_switch_idx = CONTENT_TAGS.index("SELF_SWITCH")
    assert static.tag_block[self_switch_idx] == 1.0


def test_sole_redirect_snipe_does_not_also_set_damage():
    """Fezandipiti ex's "Cruel Arrow" (card:140:attack:0) does 100 damage to 1 of your
    opponent's Pokemon -- a single freely-targetable hit, not a guaranteed active hit plus a
    separate bench bonus. DAMAGE must stay 0 so this 1-Pokemon-hit row isn't indistinguishable
    from a genuine 2-Pokemon-hit row like Darmanitan's (card:258:attack:1, DAMAGE=90 AND
    SNIPE=90, a real additive bonus hit)."""
    static = build_pokemon_static(140)
    damage_idx = CONTENT_TAGS.index("DAMAGE")
    snipe_idx = CONTENT_TAGS.index("SNIPE")
    assert static.tag_block[damage_idx] == 0.0
    assert static.tag_block[snipe_idx] == 100 / 350

    darmanitan = build_pokemon_static(258)
    attack1_start = 70  # attack:1 is the second attack-shaped block
    assert darmanitan.tag_block[attack1_start + damage_idx] == 90 / 350
    assert darmanitan.tag_block[attack1_start + snipe_idx] == 90 / 350


def test_meta_trainer_tag_block_is_real():
    """Cheren (card:1224, meta) is a plain "Draw 3 cards" Supporter -- confirms the
    Trainer/Energy tag block is the real transcribed lookup (trainer_energy_meta_tags),
    not a zero-stub."""
    static = build_trainer_energy_static(1224)
    assert len(static.tag_block) == TE_TAG_BLOCK_WIDTH == 54
    draw_idx = TE_CONTENT_TAGS.index("DRAW")
    assert static.tag_block[draw_idx] == 3 / 6


def test_non_meta_trainer_uses_regex_fallback():
    """Love Ball (non-meta Item) searches the deck for a Pokemon and puts it into hand --
    SEARCH_HAND should fire via Deliverable B's regex parser, proving the non-meta
    fallback path is wired for Trainer/Energy too."""
    static = build_trainer_energy_static(1083)
    assert len(static.tag_block) == TE_TAG_BLOCK_WIDTH
    search_hand_idx = TE_CONTENT_TAGS.index("SEARCH_HAND")
    assert static.tag_block[search_hand_idx] != 0.0


def _bp(card_id: int, is_active: bool, tool_card_id: int | None = None) -> tuple[RawPokemon, BoardPokemon]:
    raw = RawPokemon(card_id=card_id, hp=200, max_hp=200, is_active=is_active, tool_card_id=tool_card_id)
    return raw, raw_pokemon_to_board_pokemon(raw)


def test_attack_damage_plain_extraction_no_bakes():
    """Abra (card:741:attack:0, DAMAGE=10) vs Froslass -- no tools/stadiums/rule-box, no
    Weakness/Resistance match (Psychic vs Water/weak-to-Metal). Confirms the tag_block's
    real `DAMAGE` magnitude round-trips through denormalize -> effective_damage -> intact,
    with zero bake distortion."""
    _, attacker = _bp(741, True)
    _, defender = _bp(104, True)
    ctx = GameBoardContext(our_side=(attacker,), opponent_side=(defender,))
    attacker_static = build_pokemon_static(741)
    defender_static = build_pokemon_static(104)
    assert raw_attack_damage_for(attacker_static, attacker, True, defender_static, defender, ctx) == [10.0, 0.0]


def test_attack_damage_dealt_delta_respects_target_restriction():
    """Marnie's Impidimp (card:646:attack:1, DAMAGE=10) with Maximum Belt (+50 vs a
    rule-box defender, card:1158) -- Fezandipiti ex (rule-box `ex`) gets the bonus,
    Froslass (no rule box) doesn't. Neither defender's Weakness matches Darkness, so this
    isolates `damage_dealt_bonus`'s `target_restriction` gating specifically."""
    _, attacker = _bp(646, True, tool_card_id=1158)
    attacker_static = build_pokemon_static(646)

    _, rule_box_defender = _bp(140, True)  # Fezandipiti ex
    ctx1 = GameBoardContext(our_side=(attacker,), opponent_side=(rule_box_defender,))
    dmg1 = raw_attack_damage_for(attacker_static, attacker, True, build_pokemon_static(140), rule_box_defender, ctx1)
    assert dmg1[1] == 60.0  # 10 base + 50 Maximum Belt bonus

    _, plain_defender = _bp(104, True)  # Froslass, no rule box
    ctx2 = GameBoardContext(our_side=(attacker,), opponent_side=(plain_defender,))
    dmg2 = raw_attack_damage_for(attacker_static, attacker, True, build_pokemon_static(104), plain_defender, ctx2)
    assert dmg2[1] == 10.0  # no bonus -- target_restriction correctly withholds it


def test_damage_taken_delta_applies_after_weakness_multiplier():
    """Cinderace (Fire, card:666:attack:0, DAMAGE=50) vs Scizor ex (Metal, weak to Fire)
    with Full Metal Lab in play (-30, `ordering=\"post_wr\"`). Correct ordering gives
    (50*2)-30=70; if the -30 were wrongly applied before the multiplier it would be
    (50-30)*2=40 instead -- this test fails loudly under the wrong ordering."""
    _, attacker = _bp(666, True)
    _, defender = _bp(84, True)  # Scizor ex
    ctx = GameBoardContext(our_side=(attacker,), opponent_side=(defender,), stadium_card_id=1244)
    dmg = raw_attack_damage_for(build_pokemon_static(666), attacker, True, build_pokemon_static(84), defender, ctx)
    assert dmg[0] == 70.0


def test_weakness_and_resistance_generalize_beyond_fire_fighting():
    """`Ceruledge-RL/stat_bakes.py`'s original `effective_damage` hardcoded Weakness/
    Resistance to Fire/Fighting only. This module's version must work for any of the 10
    types: Darkness beats Psychic weakness (Impidimp vs Abra, 10*2=20) and Grass is resisted
    by Metal (Shaymin vs Scizor ex, 30-30=0) -- neither pair involves Fire or Fighting."""
    _, dark_attacker = _bp(646, True)  # Marnie's Impidimp, Darkness, attack:1 DAMAGE=10
    _, psychic_defender = _bp(741, True)  # Abra, weak to Darkness
    ctx1 = GameBoardContext(our_side=(dark_attacker,), opponent_side=(psychic_defender,))
    dmg1 = raw_attack_damage_for(
        build_pokemon_static(646), dark_attacker, True, build_pokemon_static(741), psychic_defender, ctx1,
    )
    assert dmg1[1] == 20.0

    _, grass_attacker = _bp(343, True)  # Shaymin, Grass, attack:0 DAMAGE=30
    _, metal_defender = _bp(84, True)  # Scizor ex, resists Grass
    ctx2 = GameBoardContext(our_side=(grass_attacker,), opponent_side=(metal_defender,))
    dmg2 = raw_attack_damage_for(
        build_pokemon_static(343), grass_attacker, True, build_pokemon_static(84), metal_defender, ctx2,
    )
    assert dmg2[0] == 0.0


def test_attacks_survivable_differs_per_board_slot():
    """The opponent (Marnie's Impidimp + Maximum Belt) threatens two of our Pokemon
    differently: Fezandipiti ex (rule-box) faces the +50 bonus, Froslass (no rule box)
    doesn't -- `attacks_survivable` must be computed per-slot, not once for our whole side,
    or these would come out identical."""
    opp_active = BoardPokemonState("opponent_active", RawPokemon(
        card_id=646, hp=100, max_hp=100, is_active=True, tool_card_id=1158,
    ))
    our_plain = BoardPokemonState("our_active", RawPokemon(card_id=104, hp=200, max_hp=200, is_active=True))
    our_rule_box = BoardPokemonState("our_bench", RawPokemon(card_id=140, hp=200, max_hp=200))

    state = GameState(
        our_deck=[], our_hand=[], our_discard=[], our_prizes_known=[], our_prizes_hidden_count=0,
        opponent_discard=[], board=[our_plain, our_rule_box, opp_active],
    )
    words = build_observation(state)
    plain_word = next(w for w in words if w.role == "our_active")
    rule_box_word = next(w for w in words if w.role == "our_bench")

    assert plain_word.live["attacks_survivable"] == hits_ratio(200, 10)   # no bonus
    assert rule_box_word.live["attacks_survivable"] == hits_ratio(200, 60)  # +50 bonus
    assert plain_word.live["attacks_survivable"] != rule_box_word.live["attacks_survivable"]


def test_attack_hits_opponent_matches_hits_ratio():
    """Cinderace (Fire, 50 dmg, no Weakness/Resistance vs Froslass) attacking Froslass
    (90 HP) -- `attack_hits_opponent` must equal `hits_ratio(90, 50)` computed directly."""
    state = GameState(
        our_deck=[], our_hand=[], our_discard=[], our_prizes_known=[], our_prizes_hidden_count=0,
        opponent_discard=[],
        board=[
            BoardPokemonState("our_active", RawPokemon(card_id=666, hp=160, max_hp=160, is_active=True)),
            BoardPokemonState("opponent_active", RawPokemon(card_id=104, hp=90, max_hp=90, is_active=True)),
        ],
    )
    words = build_observation(state)
    our_word = next(w for w in words if w.role == "our_active")
    assert our_word.live["attack_hits_opponent"] == hits_ratio(90, 50)


def test_sole_redirect_snipe_gives_zero_attack_damage_in_live_state():
    """Fezandipiti ex's sole-redirect `DAMAGE=0` (see `test_sole_redirect_snipe_does_not_
    also_set_damage`) must carry through into the live `attack_damage` field too, not just
    the static tag block -- confirms the DAMAGE/SNIPE fix and this wiring compose."""
    state = GameState(
        our_deck=[], our_hand=[], our_discard=[], our_prizes_known=[], our_prizes_hidden_count=0,
        opponent_discard=[],
        board=[
            BoardPokemonState("our_active", RawPokemon(card_id=140, hp=210, max_hp=210, is_active=True)),
            BoardPokemonState("opponent_active", RawPokemon(card_id=104, hp=90, max_hp=90, is_active=True)),
        ],
    )
    words = build_observation(state)
    our_word = next(w for w in words if w.role == "our_active")
    assert our_word.live["attack_damage"][0] == 0.0


def test_weakness_override_wired_into_board_word():
    """Lillie's Clefairy ex's ability overrides a Dragon-type opponent's Weakness to
    Psychic (`weakness_set`, spec 11's already-locked, previously-unwired aura-override
    requirement). Dragapult ex prints no Weakness at all -- the board word's own
    `weakness_onehot` must reflect the live override, not stay all-zero."""
    state = GameState(
        our_deck=[], our_hand=[], our_discard=[], our_prizes_known=[], our_prizes_hidden_count=0,
        opponent_discard=[],
        board=[
            BoardPokemonState("our_active", RawPokemon(card_id=272, hp=190, max_hp=190, is_active=True)),
            BoardPokemonState("opponent_active", RawPokemon(card_id=121, hp=320, max_hp=320, is_active=True)),
        ],
    )
    words = build_observation(state)
    opp_word = next(w for w in words if w.role == "opponent_active")
    assert opp_word.static.weakness_onehot[WR_TYPE_INDEX["Psychic"]] == 1.0
    assert sum(opp_word.static.weakness_onehot) == 1.0


def test_stat_debuff_reused_for_trainer_context_phrasing():
    """Antique Jaw Fossil (non-meta Item): "attacks used by your opponent's Active Pokemon
    do 30 less damage" -- STAT_DEBUFF was added as a 20th tag reused from spec 11a
    post-transcription (spec 11b's own locked list omitted it), and its shared regex was
    widened to accept this Trainer-context phrasing alongside the original Pokemon-side
    "the Defending Pokemon" wording."""
    static = build_trainer_energy_static(1150)
    assert len(static.tag_block) == TE_TAG_BLOCK_WIDTH
    stat_debuff_idx = TE_CONTENT_TAGS.index("STAT_DEBUFF")
    assert static.tag_block[stat_debuff_idx] == 30 / 350


def test_basic_energy_has_no_effect_tags():
    """Basic Energy cards (card_ids 1-8) have no effect row in the registry at all --
    confirms they fall through cleanly to an all-zero tag block rather than erroring or
    needing a special-cased entry in trainer_energy_meta_tags.META_TAGS."""
    static = build_trainer_energy_static(1)
    assert len(static.tag_block) == TE_TAG_BLOCK_WIDTH
    assert all(v == 0.0 for v in static.tag_block)
