"""Spec 16b: POC policy model consuming spec 13a's 174-word observation.

Precision explicitly deprioritized per the confirmed v1 scope: placeholder widths/depths,
single Linear layers instead of MLPs. "Just needs to work as a proof of concept."
"""
from __future__ import annotations

import os
import sys

import torch
import torch.nn as nn

_HERE = os.path.dirname(os.path.abspath(__file__))
_IL_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _IL_ROOT)

from observation.encoder import Word  # noqa: E402

from . import action_space, layout, packing  # noqa: E402

D_MODEL = 128
N_HEADS = 2
N_LAYERS = 2
N_ATTACK_SLOTS = 2  # spec 11a's fixed cheapest-first 2-attack-row convention


class PolicyModel(nn.Module):
    def __init__(self, d_model: int = D_MODEL, n_heads: int = N_HEADS, n_layers: int = N_LAYERS):
        super().__init__()
        self.d_model = d_model

        self.kind_embed = nn.ModuleDict({
            kind: nn.Linear(width, d_model)
            for kind, width in packing.CONTENT_WIDTHS.items()
            if width > 0
        })
        self.pool_embed = nn.Parameter(torch.zeros(d_model))
        self.pad_embed = nn.Parameter(torch.zeros(d_model))
        self.role_embed = nn.Embedding(packing.N_ROLES, d_model)

        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=d_model * 2,
            dropout=0.1, activation="gelu", norm_first=True, batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(layer, num_layers=n_layers, enable_nested_tensor=False)

        self.pool_query = nn.Parameter(torch.zeros(d_model))
        self.stage1_head = nn.Linear(d_model, action_space.N_VERBS)
        self.attack_head = nn.Linear(d_model, N_ATTACK_SLOTS)
        self.compound_head = nn.Linear(2 * d_model, 1)

        self.number_embed = nn.Linear(1, d_model)
        self.yesno_embed = nn.Embedding(2, d_model)
        self.special_condition_embed = nn.Embedding(5, d_model)

        # Learned STOP token for variable-count (minCount < maxCount) sub-selections --
        # mirrors Ceruledge-RL/model.py's stage2_scores(include_stop=...). Model/scoring
        # capability only; wiring it into live sequential-pick inference is separate
        # (RL-scope) follow-on work, not this file.
        self.stop_embed = nn.Parameter(torch.zeros(d_model))

        self.value_head = nn.Linear(d_model, 1)

    def _word_embedding(self, kind: str, role: str | None, content: list[float]) -> torch.Tensor:
        if kind == "pool":
            v = self.pool_embed
        elif kind == "pad":
            v = self.pad_embed
        else:
            t = torch.tensor(content, dtype=torch.float32)
            v = self.kind_embed[kind](t)
        role_idx = torch.tensor(packing.role_index(role), dtype=torch.long)
        return v + self.role_embed(role_idx)

    def encode(self, words: list[Word]) -> tuple[torch.Tensor, torch.Tensor]:
        """One observation -> (word_embeddings (T, D), pooled (D,)). Batch size 1 --
        placeholder-precision v1 does not batch multiple observations through one
        transformer call (see 16c for how the training loop handles this)."""
        packed = packing.pack_words(words)
        embeds = torch.stack([
            self._word_embedding(kind, role, content) for kind, role, content, _ in packed
        ])  # (T, D)
        mask = torch.tensor([masked for _, _, _, masked in packed], dtype=torch.bool)  # (T,)

        x = embeds.unsqueeze(0)  # (1, T, D)
        out = self.transformer(x, src_key_padding_mask=mask.unsqueeze(0))
        out = out.squeeze(0)  # (T, D)

        scores = out @ self.pool_query  # (T,)
        scores = scores.masked_fill(mask, float("-inf"))
        weights = torch.softmax(scores, dim=0)
        pooled = weights @ out  # (D,)
        return out, pooled

    def stage1_logits(self, pooled: torch.Tensor) -> torch.Tensor:
        return self.stage1_head(pooled)

    def value(self, pooled: torch.Tensor) -> torch.Tensor:
        """V(state). Accepts a single pooled vector (D,) or a batch (N, D)."""
        return self.value_head(pooled).squeeze(-1)

    def attack_slot_logits(self, active_word_embedding: torch.Tensor) -> torch.Tensor:
        return self.attack_head(active_word_embedding)

    def board_embedding(self, word_embeddings: torch.Tensor, ref: action_space.BoardRef) -> torch.Tensor:
        return word_embeddings[layout.board_word_index(ref.role, ref.slot)]

    def zone_card_embedding(
        self, word_embeddings: torch.Tensor, words: list[Word], role: str, card_id: int | None,
        occurrence: int = 0,
    ) -> torch.Tensor | None:
        idx = layout.find_zone_word_index(words, role, card_id, occurrence)
        return None if idx is None else word_embeddings[idx]

    def literal_embedding(self, candidate: action_space.Candidate, option_type) -> torch.Tensor:
        from cg_download.api import OptionType
        if option_type == OptionType.NUMBER:
            v = torch.tensor([candidate.literal or 0.0], dtype=torch.float32)
            return self.number_embed(v)
        if option_type in (OptionType.YES, OptionType.NO):
            idx = 0 if option_type == OptionType.YES else 1
            return self.yesno_embed(torch.tensor(idx, dtype=torch.long))
        if option_type == OptionType.SPECIAL_CONDITION:
            idx = int(candidate.literal or 0)
            return self.special_condition_embed(torch.tensor(idx, dtype=torch.long))
        raise ValueError(f"not a literal option type: {option_type}")

    def encode_card_by_id(self, card_id: int) -> torch.Tensor:
        """A `zone_card`-shaped embedding built directly from a card_id, independent of
        any board/zone position -- used to condition scoring on the triggering effect
        card (`obs.select.effect`), which may not correspond to any single word in the
        current observation."""
        content = packing.pack_card_content(card_id)
        t = torch.tensor(content, dtype=torch.float32)
        return self.kind_embed["zone_card"](t)

    def condition_on_effect(self, pooled: torch.Tensor, effect_vec: torch.Tensor | None) -> torch.Tensor:
        """Bias the pooled state toward the card that triggered a sub-selection, so the
        scorer knows *why* it's picking (e.g. an Ultra Ball cost vs. a Brilliant Blender
        cost) -- mirrors `Ceruledge-RL/model.py`'s own `condition_on_effect` (plain sum,
        this project's established pattern for conditioning one vector on another).
        `effect_vec=None` (no triggering effect) leaves pooled unchanged."""
        if effect_vec is None:
            return pooled
        return pooled + effect_vec

    def candidate_score(self, pooled: torch.Tensor, candidate_vec: torch.Tensor) -> torch.Tensor:
        """Board-target / hand-card / literal candidates: dot product against pooled."""
        return torch.dot(pooled, candidate_vec)

    def stop_score(self, pooled: torch.Tensor) -> torch.Tensor:
        """Score for terminating a variable-count sub-selection early (e.g. Drilbur/
        Brilliant Blender-style 'pick up to N') -- same dot-product mechanism as any
        other candidate, scored against the learned STOP embedding."""
        return self.candidate_score(pooled, self.stop_embed)

    def compound_score(self, card_vec: torch.Tensor, target_vec: torch.Tensor) -> torch.Tensor:
        """ATTACH/EVOLVE compound (card, target) candidates: concat + small projection --
        chosen over sum/sequential picking for information-preservation (locked decision,
        `Ceruledge-RL/specs/16b-model-architecture.md`)."""
        return self.compound_head(torch.cat([card_vec, target_vec])).squeeze(-1)
