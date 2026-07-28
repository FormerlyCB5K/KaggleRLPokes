from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from cg_download.api import Observation
from cg_download.utils import to_dataclass
from engine_native_policy import (
    EngineNativeNet,
    FrozenTables,
    decode_batch,
    encode,
    featurize,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"


def test_reference_replay_flat_and_checkpoint_outputs() -> None:
    expected = json.loads(
        (ARTIFACTS / "reference" / "golden_outputs.json").read_text()
    )
    replay_path = ARTIFACTS / "samples" / expected["replay"]
    with gzip.open(replay_path, "rt", encoding="utf-8") as handle:
        replay = json.load(handle)

    frame = replay["frames"][expected["frame_index"]]
    seat = expected["seat"]
    observation = to_dataclass(frame["obs"], Observation)
    deck = replay["agents"][seat]["deck"]
    flat = encode(featurize(observation, deck))

    assert hashlib.sha256(flat.tobytes()).hexdigest()[:16] == expected["flat_sha256_16"]
    assert float(flat.sum()) == pytest.approx(expected["flat_sum"], abs=1e-6)
    assert int(np.count_nonzero(flat)) == expected["flat_nonzero"]
    assert int(flat[1918]) == expected["n_options"]

    tables = FrozenTables.load(ARTIFACTS / "frozen_tables.pt")
    network = EngineNativeNet(tables=tables)
    checkpoint = torch.load(
        ARTIFACTS / "reference" / "step_98304000.pt",
        map_location="cpu",
        weights_only=True,
    )
    network.load_state_dict(checkpoint["state_dict"], strict=True)
    network.eval()
    with torch.inference_mode():
        output = network(decode_batch(flat[None, :]))

    n = expected["n_options"]
    np.testing.assert_allclose(
        output.logits[0, :n].numpy(), expected["logits_live"], atol=1e-5
    )
    np.testing.assert_allclose(
        output.incl[0, :n].numpy(), expected["incl_live"], atol=1e-5
    )
    assert float(output.value[0]) == pytest.approx(expected["value"], abs=1e-5)
    assert int(output.logits[0, :n].argmax()) == expected["argmax_option"]
