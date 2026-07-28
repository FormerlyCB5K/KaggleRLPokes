from __future__ import annotations

from copy import deepcopy

import numpy as np

from cg_download.api import AreaType, Card, Log, LogType, Option, OptionType
from engine_native_policy.featurize import featurize
from engine_native_policy.flat import decode_batch, encode
from engine_native_policy.spec import OPT_ENTITY_NONE, Role

from helpers import sample_deck, sample_observation


def test_entity_order_live_numerics_and_attachment_identity() -> None:
    frame = featurize(sample_observation(), sample_deck())
    assert frame.tok_card_id.tolist() == [100, 101, 200, 300, 301, 400]
    assert frame.tok_role.tolist() == [
        Role.MY_ACTIVE,
        Role.MY_BENCH,
        Role.OPP_ACTIVE,
        Role.MY_HAND,
        Role.MY_HAND,
        Role.STADIUM,
    ]
    active = frame.tok_num[0]
    assert active[0] == 1
    assert active[1] == 1
    assert active[2] == 0.75
    assert active[6] == 3 / 5
    assert active[7] == 1 / 2
    assert active[10] == 1
    assert active[17] == 2 / 5  # FIRE is typed-energy index 2, block starts at 15.
    assert frame.tok_tool_id[0] == 110
    assert frame.tok_senergy_id[0] == 9
    assert np.count_nonzero(frame.tok_num[3]) == 0


def test_option_resolution_uses_attacker_and_shared_entity_map() -> None:
    frame = featurize(sample_observation(), sample_deck())
    assert frame.opt_type.tolist() == [13, 8, 3, 7, 0]
    assert frame.opt_card.tolist() == [100, 300, 200, 301, 0]
    assert frame.opt_tgt.tolist() == [0, 101, 0, 0, 0]
    assert frame.opt_attack.tolist() == [55, 0, 0, 0, 0]
    assert frame.opt_ent.tolist() == [0, 1, 2, OPT_ENTITY_NONE, OPT_ENTITY_NONE]
    np.testing.assert_allclose(frame.opt_num[4], [0.2, 0.0, 0.1, 0.1])


def test_deck_zones_are_repeated_aggregate_counts() -> None:
    deck = [300] * 4 + [600] * 56
    frame = featurize(sample_observation(), deck)
    expected = np.asarray([0.25, 0.0, 0.0, 0.75], dtype=np.float32)
    np.testing.assert_array_equal(frame.deck_zone[:4], np.tile(expected, (4, 1)))


def test_global_fields_come_directly_from_current_and_select() -> None:
    frame = featurize(sample_observation(), sample_deck())
    expected = np.asarray(
        [
            4 / 30,
            3 / 20,
            1,
            1,
            0,
            1,
            0,
            1,
            5 / 6,
            48 / 60,
            49 / 60,
            2 / 12,
            6 / 12,
            1 / 30,
            0,
            4 / 20,
            2 / 10,
            1,
        ],
        dtype=np.float32,
    )
    np.testing.assert_allclose(frame.glob, expected)


def test_logs_and_prior_state_are_not_policy_inputs() -> None:
    plain = sample_observation()
    with_log = sample_observation(
        logs=[
            Log(
                type=LogType.MOVE_CARD,
                playerIndex=1,
                cardId=999,
                fromArea=AreaType.DECK,
                toArea=AreaType.HAND,
            )
        ]
    )
    np.testing.assert_array_equal(
        encode(featurize(plain, sample_deck())),
        encode(featurize(with_log, sample_deck())),
    )


def test_modulo_ids_and_symbolic_area_mapping() -> None:
    observation = deepcopy(sample_observation())
    observation.current.players[0].hand = [Card(id=1301, serial=80, playerIndex=0)]
    observation.current.players[0].handCount = 1
    observation.select.option = [
        Option(
            type=OptionType.CARD,
            area=AreaType.HAND,
            index=0,
            playerIndex=0,
        )
    ]
    frame = featurize(observation, [1301] + [1] * 59)
    assert frame.tok_card_id[-2] == 1  # Hand precedes the Stadium.
    assert frame.opt_card[0] == 1
    assert frame.opt_ent[0] == OPT_ENTITY_NONE
    batch = decode_batch(encode(frame))
    assert batch["n_options"].item() == 1
