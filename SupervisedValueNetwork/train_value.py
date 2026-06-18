"""
Supervised value network trained on historical game data.

Each observation in a game is labeled with the final result from that
player's perspective (+1 win, -1 loss, 0 draw).

Architecture: same encoder + value head as the MCTS sample notebook,
stripped of the decoder/policy side.
"""

import glob
import json
import os
import random

import torch
import torch.nn
import torch.nn.functional
import torch.optim
from torch.utils.data import Dataset, DataLoader

from features import SparseVector, get_encoder_input, CARD_COUNT, NUM_WORDS_ENCODER


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

ENCODER_SIZE = 22000   # embedding vocabulary; must satisfy 43 + 17*CARD_COUNT ≤ this
D_MODEL = 128
NUM_HEADS = 2
D_FEEDFORWARD = 256
NUM_ENCODER_LAYERS = 1


class ValueModel(torch.nn.Module):
    """
    Encoder-only transformer that outputs a scalar board value in [-1, 1].

    Architecture is identical to the encoder path of MyModel in the
    sample notebook — weights are directly transferable.
    """

    def __init__(
        self,
        d_model: int = D_MODEL,
        num_heads: int = NUM_HEADS,
        d_feedforward: int = D_FEEDFORWARD,
        num_layers: int = NUM_ENCODER_LAYERS,
        encoder_size: int = ENCODER_SIZE,
    ):
        super().__init__()
        self.d_model = d_model
        self.encoder_bag = torch.nn.EmbeddingBag(encoder_size, d_model, mode="sum")
        encoder_layer = torch.nn.TransformerEncoderLayer(
            d_model, num_heads, d_feedforward, dropout=0, batch_first=False
        )
        self.encoder = torch.nn.TransformerEncoder(
            encoder_layer, num_layers, enable_nested_tensor=False
        )
        self.fc = torch.nn.Linear(d_model, 1)

    def forward(
        self,
        index: torch.Tensor,
        value: torch.Tensor,
        offset: torch.Tensor,
    ) -> torch.Tensor:
        """
        Parameters
        ----------
        index  : int32 flat list of nonzero embedding indices
        value  : float32 weights for each index
        offset : int32 where each of the 24*batch_size words starts in index

        Returns
        -------
        Tensor of shape (batch_size, 1) with values in [-1, 1]
        """
        x = self.encoder_bag(index, offset, value)
        # x: (24 * batch_size, d_model)
        x = x.reshape(-1, NUM_WORDS_ENCODER, self.d_model).transpose(0, 1)
        # x: (24, batch_size, d_model)
        x = self.encoder(x)
        x = self.fc(x)
        # mean across the 24 sequence positions, then tanh
        x = torch.tanh(x.mean(0))
        return x  # (batch_size, 1)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class GameSample:
    __slots__ = ("sv", "label")

    def __init__(self, sv: SparseVector, label: float):
        self.sv = sv
        self.label = label


def load_game(path: str) -> list[GameSample]:
    """
    Extract one (SparseVector, label) pair per observation step per player.

    Label is the final game result from that player's perspective:
      +1.0  win
      -1.0  loss
       0.0  draw
    """
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return []

    rewards = d.get("rewards", [0, 0])  # [p0_reward, p1_reward]
    steps = d.get("steps", [])
    if len(steps) < 2:
        return []

    # Deck submitted by each player at step 1
    decks: list[list[int]] = [[], []]
    for pi in range(2):
        action = steps[1][pi].get("action") or []
        decks[pi] = [c for c in action if isinstance(c, int)]

    samples: list[GameSample] = []
    for step in steps:
        for pi in range(2):
            obs = step[pi].get("observation", {})
            current = obs.get("current")
            if current is None:
                continue

            your_index = current.get("yourIndex")
            if your_index is None:
                continue

            deck = decks[your_index]
            if not deck:
                continue

            try:
                sv = get_encoder_input(obs, deck)
            except Exception:
                continue

            raw = rewards[your_index]
            if raw is None:
                continue
            samples.append(GameSample(sv, float(raw)))

    return samples


class PokemonValueDataset(Dataset):
    def __init__(self, game_files: list[str]):
        self.samples: list[GameSample] = []
        for path in game_files:
            self.samples.extend(load_game(path))
        print(f"Loaded {len(self.samples)} samples from {len(game_files)} games.")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> GameSample:
        return self.samples[idx]


# ---------------------------------------------------------------------------
# Collation — pack variable-length SparseVectors into a single batch tensor
# ---------------------------------------------------------------------------

def collate_fn(batch: list[GameSample]):
    flat_index: list[int] = []
    flat_value: list[float] = []
    flat_offset: list[int] = []
    labels: list[float] = []

    for sample in batch:
        sv = sample.sv
        count = len(flat_index)
        flat_index.extend(sv.index)
        flat_value.extend(sv.value)
        for o in sv.offset:
            flat_offset.append(o + count)
        labels.append(sample.label)

    return (
        torch.tensor(flat_index, dtype=torch.int32),
        torch.tensor(flat_value, dtype=torch.float32),
        torch.tensor(flat_offset, dtype=torch.int32),
        torch.tensor(labels, dtype=torch.float32).unsqueeze(1),
    )


# ---------------------------------------------------------------------------
# TD(λ) label computation
# ---------------------------------------------------------------------------

class Trajectory:
    """One player's ordered observations from a single game."""
    __slots__ = ("svs", "terminal")

    def __init__(self, svs: list[SparseVector], terminal: float):
        self.svs = svs          # chronological list of SparseVectors
        self.terminal = terminal  # +1 win, -1 loss, 0 draw


def load_game_trajectories(path: str) -> list[Trajectory]:
    """
    Like load_game but preserves per-player order needed for TD(λ).
    Returns up to 2 Trajectory objects (one per player).
    """
    try:
        with open(path) as f:
            d = json.load(f)
    except Exception:
        return []

    rewards = d.get("rewards", [0, 0])
    steps = d.get("steps", [])
    if len(steps) < 2:
        return []

    decks: list[list[int]] = [[], []]
    for pi in range(2):
        action = steps[1][pi].get("action") or []
        decks[pi] = [c for c in action if isinstance(c, int)]

    per_player: list[list[SparseVector]] = [[], []]
    for step in steps:
        for pi in range(2):
            obs = step[pi].get("observation", {})
            current = obs.get("current")
            if current is None:
                continue
            your_index = current.get("yourIndex")
            if your_index is None:
                continue
            deck = decks[your_index]
            if not deck:
                continue
            try:
                sv = get_encoder_input(obs, deck)
                per_player[your_index].append(sv)
            except Exception:
                continue

    trajectories = []
    for pi in range(2):
        if not per_player[pi]:
            continue
        raw = rewards[pi]
        if raw is None:
            continue
        trajectories.append(Trajectory(per_player[pi], float(raw)))

    return trajectories


def _pack_svs(svs: list[SparseVector]):
    """Pack a list of SparseVectors into flat batch tensors."""
    flat_index, flat_value, flat_offset = [], [], []
    for sv in svs:
        base = len(flat_index)
        flat_index.extend(sv.index)
        flat_value.extend(sv.value)
        for o in sv.offset:
            flat_offset.append(o + base)
    return (
        torch.tensor(flat_index, dtype=torch.int32),
        torch.tensor(flat_value, dtype=torch.float32),
        torch.tensor(flat_offset, dtype=torch.int32),
    )


def batch_predict(
    svs: list[SparseVector],
    model: "ValueModel",
    device,
    batch_size: int = 512,
) -> list[float]:
    """Run model on a list of SparseVectors; return scalar predictions."""
    model.eval()
    results: list[float] = []
    with torch.no_grad():
        for start in range(0, len(svs), batch_size):
            chunk = svs[start : start + batch_size]
            idx, val, offset = _pack_svs(chunk)
            preds = model(idx.to(device), val.to(device), offset.to(device))
            results.extend(preds.squeeze(1).cpu().tolist())
    return results


def apply_td_lambda(
    trajectories: list[Trajectory],
    model: "ValueModel",
    device,
    lambda_: float = 0.9,
) -> list[GameSample]:
    """
    Compute TD(λ) labels for a list of trajectories using the current model.

    For each trajectory, working backward from the terminal result:
        label[t]  = 0.5 * (carry + model_pred[t])
        carry     = λ * carry + (1 - λ) * model_pred[t]

    The carry starts at the true terminal result, so:
    - Steps near the end get labels ≈ terminal result
    - Steps near the start get labels ≈ model's own early estimate
      (anchored to later steps that are anchored to the terminal result)

    This matches the TD(λ) logic in the MCTS sample notebook (LAMBDA=0.9).
    """
    # Batch all SVs from all trajectories in one forward pass
    all_svs = [sv for traj in trajectories for sv in traj.svs]
    all_preds = batch_predict(all_svs, model, device)

    samples: list[GameSample] = []
    pred_cursor = 0
    for traj in trajectories:
        n = len(traj.svs)
        preds = all_preds[pred_cursor : pred_cursor + n]
        pred_cursor += n

        carry = traj.terminal
        td_labels = [0.0] * n
        for t in reversed(range(n)):
            td_labels[t] = (carry + preds[t]) * 0.5
            carry = lambda_ * carry + (1 - lambda_) * preds[t]

        for sv, label in zip(traj.svs, td_labels):
            samples.append(GameSample(sv, label))

    return samples


class TDLambdaDataset(Dataset):
    """
    Dataset that re-computes TD(λ) labels at the start of each epoch
    using the current model weights.

    Usage:
        ds = TDLambdaDataset(game_files)
        ds.relabel(model, device)   # call once per epoch before DataLoader
    """

    def __init__(self, game_files: list[str], lambda_: float = 0.9):
        self.lambda_ = lambda_
        self.trajectories: list[Trajectory] = []
        for path in game_files:
            self.trajectories.extend(load_game_trajectories(path))
        print(f"Loaded {len(self.trajectories)} trajectories from {len(game_files)} games.")
        self.samples: list[GameSample] = []

    def relabel(self, model: "ValueModel", device):
        """Recompute TD(λ) labels with current model. Call before each epoch."""
        self.samples = apply_td_lambda(self.trajectories, model, device, self.lambda_)
        random.shuffle(self.samples)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> GameSample:
        return self.samples[idx]


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(
    data_dir: str = "Training-Data",
    out_dir: str = "out",
    epochs: int = 10,
    batch_size: int = 128,
    lr: float = 3e-4,
    val_fraction: float = 0.1,
    seed: int = 42,
):
    random.seed(seed)
    torch.manual_seed(seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    game_files = sorted(glob.glob(os.path.join(data_dir, "*.json")))
    random.shuffle(game_files)
    split = max(1, int(len(game_files) * val_fraction))
    val_files = game_files[:split]
    train_files = game_files[split:]

    print(f"Train games: {len(train_files)}, Val games: {len(val_files)}")

    print("Loading training data...")
    train_ds = PokemonValueDataset(train_files)
    print("Loading validation data...")
    val_ds = PokemonValueDataset(val_files)

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, collate_fn=collate_fn
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn
    )

    model = ValueModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    loss_fn = torch.nn.HuberLoss(delta=0.2)

    os.makedirs(out_dir, exist_ok=True)
    best_val_loss = float("inf")

    for epoch in range(epochs):
        # --- train ---
        model.train()
        train_loss = 0.0
        for idx, value, offset, label in train_loader:
            idx = idx.to(device)
            value = value.to(device)
            offset = offset.to(device)
            label = label.to(device)

            optimizer.zero_grad()
            pred = model(idx, value, offset)
            loss = loss_fn(pred, label)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        # --- validate ---
        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for idx, value, offset, label in val_loader:
                idx = idx.to(device)
                value = value.to(device)
                offset = offset.to(device)
                label = label.to(device)

                pred = model(idx, value, offset)
                val_loss += loss_fn(pred, label).item()

                # directional accuracy: did we predict the right winner?
                pred_sign = pred.sign()
                label_sign = label.sign()
                # ignore draws (label == 0)
                mask = label_sign != 0
                correct += (pred_sign[mask] == label_sign[mask]).sum().item()
                total += mask.sum().item()

        val_loss /= len(val_loader)
        accuracy = 100 * correct / total if total > 0 else 0.0

        print(
            f"Epoch {epoch+1:03d}/{epochs} | "
            f"train_loss={train_loss:.4f} | "
            f"val_loss={val_loss:.4f} | "
            f"val_acc={accuracy:.1f}%"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), os.path.join(out_dir, "best_value_model.pth"))

    torch.save(model.state_dict(), os.path.join(out_dir, "value_model_final.pth"))
    print(f"Done. Best val loss: {best_val_loss:.4f}")


def train_td(
    data_dir: str = "Training-Data",
    out_dir: str = "out",
    epochs: int = 10,
    batch_size: int = 128,
    lr: float = 3e-4,
    val_fraction: float = 0.1,
    lambda_: float = 0.9,
    seed: int = 42,
):
    """
    Training loop using TD(λ) labels.

    Each epoch:
      1. Re-label all training trajectories using current model predictions
      2. Train one epoch on the new labels
      3. Evaluate on validation set (also re-labeled each epoch)
    """
    random.seed(seed)
    torch.manual_seed(seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    game_files = sorted(glob.glob(os.path.join(data_dir, "*.json")))
    random.shuffle(game_files)
    split = max(1, int(len(game_files) * val_fraction))
    val_files = game_files[:split]
    train_files = game_files[split:]

    print(f"Train games: {len(train_files)}, Val games: {len(val_files)}")

    print("Loading trajectories...")
    train_ds = TDLambdaDataset(train_files, lambda_=lambda_)
    val_ds = TDLambdaDataset(val_files, lambda_=lambda_)

    model = ValueModel().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    loss_fn = torch.nn.HuberLoss(delta=0.2)

    os.makedirs(out_dir, exist_ok=True)
    best_val_loss = float("inf")

    for epoch in range(epochs):
        # Re-label with current model before each epoch
        print(f"  [Epoch {epoch+1}] Computing TD(λ) labels...", flush=True)
        train_ds.relabel(model, device)
        val_ds.relabel(model, device)

        train_loader = DataLoader(
            train_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn
        )
        val_loader = DataLoader(
            val_ds, batch_size=batch_size, shuffle=False, collate_fn=collate_fn
        )

        # --- train ---
        model.train()
        train_loss = 0.0
        for idx, value, offset, label in train_loader:
            idx = idx.to(device)
            value = value.to(device)
            offset = offset.to(device)
            label = label.to(device)

            optimizer.zero_grad()
            pred = model(idx, value, offset)
            loss = loss_fn(pred, label)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        train_loss /= len(train_loader)

        # --- validate ---
        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for idx, value, offset, label in val_loader:
                idx = idx.to(device)
                value = value.to(device)
                offset = offset.to(device)
                label = label.to(device)

                pred = model(idx, value, offset)
                val_loss += loss_fn(pred, label).item()

                # directional accuracy against terminal result (not TD label)
                # use sign of TD label as proxy — still reflects who won
                mask = label.sign() != 0
                correct += (pred.sign()[mask] == label.sign()[mask]).sum().item()
                total += mask.sum().item()

        val_loss /= len(val_loader)
        accuracy = 100 * correct / total if total > 0 else 0.0

        print(
            f"Epoch {epoch+1:03d}/{epochs} | "
            f"train_loss={train_loss:.4f} | "
            f"val_loss={val_loss:.4f} | "
            f"val_acc={accuracy:.1f}%"
        )

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), os.path.join(out_dir, "best_value_model_td.pth"))

    torch.save(model.state_dict(), os.path.join(out_dir, "value_model_td_final.pth"))
    print(f"Done. Best val loss: {best_val_loss:.4f}")


if __name__ == "__main__":
    train_td()
