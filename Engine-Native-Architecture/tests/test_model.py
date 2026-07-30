from __future__ import annotations

import pytest
import torch

from engine_native_policy.featurize import featurize
from engine_native_policy.flat import decode_batch, encode
from engine_native_policy.model import EngineNativeNet, ModelConfig
from engine_native_policy.tables import FrozenTables

from helpers import sample_deck, sample_observation


EXPECTED_LEDGER = {
    "card": 48_720,
    "role_emb": 2_240,
    "num_proj": 6_272,
    "deckzone_proj": 1_120,
    "deck_film": 100_800,
    "glob_proj": 4_256,
    "encoder": 1_615_488,
    "out_norm": 448,
    "opt_type_emb": 3_808,
    "opt_eff_proj": 29_344,
    "optnum_proj": 1_120,
    "optent_proj": 50_400,
    "tool_gate": 50_176,
    "senergy_gate": 50_176,
    "score": 150_977,
    "incl": 150_977,
    "value": 50_625,
    "ora_zone_emb": 1_792,
    "ora_proj": 50_400,
    "registers": 896,
    "no_entity": 224,
}


def make_batch() -> dict[str, torch.Tensor]:
    frame = featurize(sample_observation(), sample_deck())
    return decode_batch(encode(frame))


def test_exact_parameter_count_and_module_ledger() -> None:
    net = EngineNativeNet()
    assert net.parameter_count() == 2_370_259
    assert net.parameter_ledger() == EXPECTED_LEDGER
    names = {name for name, _ in net.named_parameters()}
    assert not any("card_emb" in name or "attack_emb" in name for name in names)


def test_frozen_tables_are_not_checkpoint_parameters() -> None:
    net = EngineNativeNet()
    state = net.state_dict()
    for name in ("card.STAT", "card.ATK", "card.ABL", "card.PLAY", "card.PRIZE"):
        assert name not in state
    assert "card.stat_proj.weight" in state
    assert "ora_proj.weight" in state


def test_forward_shapes_masks_and_finite_live_outputs() -> None:
    torch.manual_seed(1)
    net = EngineNativeNet().eval()
    batch = make_batch()
    with torch.no_grad():
        output = net(batch)
    assert output.logits.shape == (1, 64)
    assert output.incl.shape == (1, 64)
    assert output.value.shape == (1,)
    assert torch.isfinite(output.logits[0, :5]).all()
    assert torch.isneginf(output.logits[0, 5:]).all()
    assert torch.equal(output.incl[0, 5:], torch.full((59,), -30.0))
    assert torch.isfinite(output.value).all()


def test_imitation_value_activation_is_bounded_without_changing_parameters() -> None:
    torch.manual_seed(1)
    net = EngineNativeNet(
        config=ModelConfig(value_activation="tanh")
    ).eval()
    with torch.no_grad():
        net.value[-1].weight.zero_()
        net.value[-1].bias.fill_(20.0)
        output = net(make_batch())
    assert net.parameter_count() == 2_370_259
    assert torch.all(output.value <= 1.0)
    assert torch.all(output.value >= -1.0)
    torch.testing.assert_close(output.value, torch.ones_like(output.value))


def test_unknown_value_activation_is_rejected() -> None:
    with pytest.raises(ValueError, match="value_activation"):
        EngineNativeNet(config=ModelConfig(value_activation="sigmoid"))


def test_zero_initialized_gates_film_and_oracle_projection() -> None:
    net = EngineNativeNet()
    assert torch.count_nonzero(net.tool_gate.weight) == 0
    assert torch.count_nonzero(net.senergy_gate.weight) == 0
    assert torch.count_nonzero(net.deck_film.to_gb.weight) == 0
    assert torch.count_nonzero(net.deck_film.to_gb.bias) == 0
    assert torch.count_nonzero(net.ora_proj.weight) == 0
    assert torch.count_nonzero(net.ora_proj.bias) == 0

    board = torch.randn(2, 40, 224)
    deck = torch.randn(2, 224)
    torch.testing.assert_close(net.deck_film(board, deck), board)


def test_inactive_oracle_path_matches_fog_value_exactly() -> None:
    torch.manual_seed(2)
    net = EngineNativeNet().eval()
    batch = make_batch()
    oracle_batch = dict(batch)
    oracle_batch.update(
        {
            "ora_id": torch.ones(1, 66, dtype=torch.int64),
            "ora_zone": torch.ones(1, 66, dtype=torch.int64),
            "ora_mask": torch.ones(1, 66, dtype=torch.bool),
        }
    )
    with torch.no_grad():
        fog = net(batch)
        oracle = net(oracle_batch)
    torch.testing.assert_close(fog.value, fog.value_fog, rtol=0, atol=0)
    torch.testing.assert_close(oracle.value, oracle.value_fog, rtol=0, atol=0)
    torch.testing.assert_close(fog.logits, oracle.logits, rtol=0, atol=0)


def test_option_effect_selection_uses_frozen_attack_ability_and_play_rows() -> None:
    tables = FrozenTables.placeholder()
    tables.attack[5, 1, 2] = 11
    tables.ability[5, 2] = 22
    tables.play[5, 2] = 33
    tables.attack_slot[7] = 1
    net = EngineNativeNet(tables=tables)
    option_type = torch.tensor([[13, 10, 7, 8]])
    card_id = torch.tensor([[5, 5, 5, 5]])
    attack_id = torch.tensor([[7, 0, 0, 0]])
    effect = net.card.option_effect(option_type, card_id, attack_id)
    assert effect[0, :, 2].tolist() == [11, 22, 33, 0]
